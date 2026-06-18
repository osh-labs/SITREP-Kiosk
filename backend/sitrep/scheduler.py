"""
APScheduler-based polling scheduler.

Polls each source on its own interval from config.polling_seconds.
Updates cache + rebuilds state after each poll cycle.

Briefing regeneration is data-driven, NOT time-driven. The briefing is
only regenerated when the underlying state changes materially — a new or
cleared NWS alert, a change in the ranked hazard set or its severity, an
AQI category shift, a new/upgraded SPC convective outlook, or a morning/
afternoon mode switch. This is captured by a content signature
(`_briefing_signature`); an unchanged signature means no LLM call.

The one exception is recovery: if the last briefing fell back to the
template (model unavailable, network error, missing key), it is retried on
the `briefing` interval so the board self-heals to a real briefing once the
model is reachable again. A steady-state board with a successful model
briefing makes no further calls until the data actually changes.
"""
from __future__ import annotations

import httpx
import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from .cache import StateCache, get_cache
from .config import get_config
from . import briefing as briefing_module
from . import hazards as hazards_module
from . import state_builder
from .sources import nws as nws_source
from .sources import spc as spc_source
from .sources import ga511 as ga511_source
from .sources import airnow as airnow_source
from .sources import openmeteo as openmeteo_source
from .sources import openmeteo_grid as openmeteo_grid_source

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Material-change detection
# ---------------------------------------------------------------------------

# Signature of the inputs that drove the last briefing. The briefing is
# regenerated only when this changes.
_last_briefing_signature: Optional[str] = None


def _alert_fingerprint(alert: dict) -> str:
    return f"{alert.get('event', '')}|{alert.get('severity', '')}"


def _briefing_signature(
    nws_data: Optional[dict],
    spc_data: Optional[dict],
    hazards: Any,
    mode: str,
) -> str:
    """Stable fingerprint of every input that should change the briefing.

    Covers: morning/afternoon mode, the active NWS alert set (event +
    severity), the ranked hazard set (key + severity, in rank order), the
    AQI callout category, and the SPC Day 1-3 convective outlook categories.
    A new or cleared advisory, an upgraded outlook, a severity shift, or a
    mode switch all change this string; nothing else does. When the signature
    is unchanged the briefing is reused and no LLM call is made.
    """
    parts: list[str] = [f"mode={mode}"]

    # NWS alerts (event + severity), order-independent
    alerts: list[str] = []
    if nws_data:
        alerts = sorted(_alert_fingerprint(a) for a in nws_data.get("alerts", []))
    parts.append("alerts=" + ",".join(alerts))

    # Ranked hazards (key + severity), in rank order
    ranked: list[str] = []
    if hazards and hazards.ranked:
        ranked = [f"{h.key}:{h.severity}" for h in hazards.ranked]
    parts.append("hazards=" + ",".join(ranked))

    # AQI callout category (a separate callout, not in the ranked chain)
    aqi_cat = ""
    if hazards and hazards.aqi_callout:
        aqi_cat = hazards.aqi_callout.category
    parts.append("aqi=" + aqi_cat)

    # SPC convective outlook categories — a new or upgraded outlook is material
    spc_parts: list[str] = []
    if spc_data and spc_data.get("_ok"):
        for day in ("day1", "day2", "day3"):
            d = spc_data.get(day)
            if d:
                spc_parts.append(f"{day}:{d.get('category', 'none')}")
    parts.append("spc=" + ",".join(spc_parts))

    return "|".join(parts)


# ---------------------------------------------------------------------------
# Shared HTTP client (created once per scheduler start)
# ---------------------------------------------------------------------------
_http_client: Optional[httpx.Client] = None


def _get_http_client() -> httpx.Client:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.Client(timeout=15.0, follow_redirects=True)
    return _http_client


# ---------------------------------------------------------------------------
# Poll functions (one per source)
# ---------------------------------------------------------------------------

def _poll_nws() -> None:
    cfg = get_config()
    cache = get_cache()
    client = _get_http_client()
    try:
        data = nws_source.fetch(client, cfg)
        if data.get("_ok"):
            cache.update("nws", data)
            # The map's authoritative overlay (alert GeoJSON) rides on NWS;
            # mark the weather_map source fresh whenever NWS succeeds.
            cache.update("weather_map", {"_ok": True})
            log.info("NWS poll OK")
        else:
            cache.mark_failed("nws")
            cache.mark_failed("weather_map")
            log.warning("NWS poll returned not-ok")
    except Exception as exc:
        cache.mark_failed("nws")
        cache.mark_failed("weather_map")
        log.error("NWS poll exception: %s", exc)


def _poll_spc() -> None:
    cfg = get_config()
    cache = get_cache()
    client = _get_http_client()
    try:
        data = spc_source.fetch(client, cfg)
        if data.get("_ok"):
            cache.update("spc", data)
            log.info("SPC poll OK (highest_category=%s)", data.get("highest_category"))
        else:
            cache.mark_failed("spc")
            log.warning("SPC poll returned not-ok")
    except Exception as exc:
        cache.mark_failed("spc")
        log.error("SPC poll exception: %s", exc)


def _poll_ga511() -> None:
    cfg = get_config()
    cache = get_cache()
    client = _get_http_client()
    try:
        data = ga511_source.fetch(client, cfg)
        if data.get("_ok"):
            cache.update("ga511", data)
            log.info("511GA poll OK (%d traffic events)", len(data.get("traffic", [])))
        else:
            cache.mark_failed("ga511")
            log.info("511GA poll: no key or not-ok (skipping)")
    except Exception as exc:
        cache.mark_failed("ga511")
        log.error("511GA poll exception: %s", exc)


def _poll_airnow() -> None:
    cfg = get_config()
    cache = get_cache()
    client = _get_http_client()
    try:
        data = airnow_source.fetch(client, cfg)
        if data.get("_ok"):
            cache.update("airnow", data)
            log.info("AirNow poll OK (AQI=%s)", data.get("aqi"))
        else:
            cache.mark_failed("airnow")
            log.info("AirNow poll: no key or not-ok (skipping)")
    except Exception as exc:
        cache.mark_failed("airnow")
        log.error("AirNow poll exception: %s", exc)


def _poll_openmeteo() -> None:
    cfg = get_config()
    cache = get_cache()
    client = _get_http_client()
    try:
        data = openmeteo_source.fetch(client, cfg)
        if data.get("_ok"):
            cache.update("openmeteo", data)
            log.info("Open-Meteo poll OK (%d hourly points)", len(data.get("hourly", [])))
        else:
            cache.mark_failed("openmeteo")
            log.warning("Open-Meteo poll returned not-ok")
    except Exception as exc:
        cache.mark_failed("openmeteo")
        log.error("Open-Meteo poll exception: %s", exc)


def _poll_temps() -> None:
    cfg = get_config()
    cache = get_cache()
    client = _get_http_client()
    try:
        data = openmeteo_grid_source.fetch(client, cfg)
        if data.get("_ok"):
            cache.update("temps", data)
            log.info("Temp-grid poll OK (%d points)", len(data.get("features", [])))
        else:
            cache.mark_failed("temps")
            log.warning("Temp-grid poll returned not-ok")
    except Exception as exc:
        cache.mark_failed("temps")
        log.error("Temp-grid poll exception: %s", exc)


# ---------------------------------------------------------------------------
# State + briefing rebuild
# ---------------------------------------------------------------------------

# Track last briefing generation time
_last_briefing_at: Optional[datetime] = None
_last_briefing: Optional[dict] = None


def _rebuild_state(force_briefing: bool = False) -> None:
    """Rebuild the consolidated state from current cache and update it."""
    global _last_briefing_at, _last_briefing, _last_briefing_signature

    cfg = get_config()
    cache = get_cache()

    nws_data = cache.get_data("nws")
    spc_data = cache.get_data("spc")
    ga511_data = cache.get_data("ga511")
    airnow_data = cache.get_data("airnow")
    openmeteo_data = cache.get_data("openmeteo")

    # Compute hazards
    hazards = hazards_module.compute_hazards(nws_data, spc_data, airnow_data, cfg)

    # Decide if we need to regenerate the briefing. Regeneration is driven by a
    # change in the underlying state (see _briefing_signature) — NOT by a timer.
    # The lone time-based path is recovery: a prior template fallback is retried
    # on the `briefing` interval so the board self-heals once the model is
    # reachable. A successful model briefing makes no further calls until the
    # data actually changes.
    now = datetime.now(tz=timezone.utc)
    mode = state_builder._compute_display_mode(cfg)
    signature = _briefing_signature(nws_data, spc_data, hazards, mode)

    retry_interval = cfg.polling_seconds.get("briefing", 1800)
    last_was_template = bool(_last_briefing) and _last_briefing.get("source") == "template"
    template_retry_due = (
        last_was_template
        and _last_briefing_at is not None
        and (now - _last_briefing_at).total_seconds() >= retry_interval
    )

    is_initial = force_briefing or _last_briefing is None
    need_briefing = (
        is_initial
        or signature != _last_briefing_signature
        or template_retry_due
    )

    if need_briefing:
        ranked_list = [h.to_dict() for h in hazards.ranked]
        aqi_dict = hazards.aqi_callout.to_dict() if hazards.aqi_callout else None
        alerts = nws_data.get("alerts", []) if nws_data else []
        spc_outlook = None
        if spc_data and spc_data.get("_ok"):
            day1 = spc_data.get("day1")
            if day1:
                spc_outlook = day1

        # Build sources_used list
        sources_used = []
        if cache.get_source_block("nws").ok:
            sources_used.append("NWS FFC")
        if cache.get_source_block("spc").ok:
            sources_used.append("SPC")
        if cache.get_source_block("ga511").ok:
            sources_used.append("511GA")
        if cache.get_source_block("openmeteo").ok:
            sources_used.append("Open-Meteo")

        _last_briefing = briefing_module.generate_briefing(
            ranked_hazards=ranked_list,
            aqi_callout=aqi_dict,
            alerts=alerts,
            spc_outlook=spc_outlook,
            mode=mode,
            sources_used=sources_used,
        )
        _last_briefing_at = now
        _last_briefing_signature = signature
        reason = "initial" if is_initial else "template-retry" if template_retry_due else "state-change"
        log.info("Briefing regenerated (source=%s, reason=%s)", _last_briefing.get("source"), reason)

    # Build full state
    state = state_builder.build_state(
        nws_data=nws_data,
        spc_data=spc_data,
        ga511_data=ga511_data,
        airnow_data=airnow_data,
        hazards=hazards,
        briefing=_last_briefing,
        cache=cache,
        config=cfg,
        openmeteo_data=openmeteo_data,
    )
    cache.set_state(state.to_dict())
    log.debug("Consolidated state rebuilt")


def _full_poll_cycle() -> None:
    """Run all source polls then rebuild state. Used for initial load."""
    _poll_nws()
    _poll_spc()
    _poll_ga511()
    _poll_airnow()
    _poll_openmeteo()
    _poll_temps()
    _rebuild_state(force_briefing=True)


# ---------------------------------------------------------------------------
# Scheduler lifecycle
# ---------------------------------------------------------------------------

_scheduler: Optional[BackgroundScheduler] = None


def start_scheduler() -> BackgroundScheduler:
    """
    Create and start the APScheduler with per-source intervals from config.
    Returns the running scheduler.
    """
    global _scheduler

    if _scheduler and _scheduler.running:
        return _scheduler

    cfg = get_config()
    ps = cfg.polling_seconds

    _scheduler = BackgroundScheduler(timezone="UTC")

    # Add per-source polling jobs
    _scheduler.add_job(
        _poll_nws,
        trigger=IntervalTrigger(seconds=ps.get("nws", 900)),
        id="poll_nws",
        name="NWS poller",
        replace_existing=True,
        coalesce=True,
        misfire_grace_time=60,
    )
    _scheduler.add_job(
        _poll_spc,
        trigger=IntervalTrigger(seconds=ps.get("spc", 1800)),
        id="poll_spc",
        name="SPC poller",
        replace_existing=True,
        coalesce=True,
        misfire_grace_time=120,
    )
    _scheduler.add_job(
        _poll_ga511,
        trigger=IntervalTrigger(seconds=ps.get("ga511", 90)),
        id="poll_ga511",
        name="511GA poller",
        replace_existing=True,
        coalesce=True,
        misfire_grace_time=30,
    )
    _scheduler.add_job(
        _poll_airnow,
        trigger=IntervalTrigger(seconds=ps.get("airnow", 1800)),
        id="poll_airnow",
        name="AirNow poller",
        replace_existing=True,
        coalesce=True,
        misfire_grace_time=120,
    )
    _scheduler.add_job(
        _poll_openmeteo,
        trigger=IntervalTrigger(seconds=ps.get("openmeteo", 900)),
        id="poll_openmeteo",
        name="Open-Meteo poller",
        replace_existing=True,
        coalesce=True,
        misfire_grace_time=120,
    )
    _scheduler.add_job(
        _poll_temps,
        trigger=IntervalTrigger(seconds=ps.get("temps", 900)),
        id="poll_temps",
        name="Temp-grid poller",
        replace_existing=True,
        coalesce=True,
        misfire_grace_time=120,
    )

    # State rebuild job (runs more frequently than briefing regen)
    _scheduler.add_job(
        _rebuild_state,
        trigger=IntervalTrigger(seconds=60),
        id="rebuild_state",
        name="State rebuilder",
        replace_existing=True,
        coalesce=True,
        misfire_grace_time=30,
    )

    _scheduler.start()
    log.info("Scheduler started (nws=%ds, spc=%ds, ga511=%ds, airnow=%ds)",
             ps.get("nws"), ps.get("spc"), ps.get("ga511"), ps.get("airnow"))

    return _scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        log.info("Scheduler stopped")


def initial_load() -> None:
    """Run an immediate full poll + state build before the scheduler takes over."""
    log.info("Running initial poll cycle...")
    try:
        _full_poll_cycle()
        log.info("Initial poll cycle complete")
    except Exception as exc:
        log.error("Initial poll cycle failed: %s", exc)


def get_last_briefing() -> Optional[dict]:
    return _last_briefing
