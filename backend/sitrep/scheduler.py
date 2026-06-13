"""
APScheduler-based polling scheduler.

Polls each source on its own interval from config.polling_seconds.
Regenerates briefing on schedule AND on material change.
Updates cache + rebuilds state after each poll cycle.

Also detects material changes (alert issued/cleared, threshold crossed)
to trigger an early briefing regeneration.
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

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Material-change detection
# ---------------------------------------------------------------------------

# Track alert fingerprints for change detection
_last_alert_set: set[str] = set()
_last_ranked_keys: list[str] = []


def _alert_fingerprint(alert: dict) -> str:
    return f"{alert.get('event', '')}|{alert.get('severity', '')}"


def _is_material_change(new_nws: Optional[dict], new_hazards_block: Any) -> bool:
    """Return True if alerts or top-ranked hazards changed since last check."""
    global _last_alert_set, _last_ranked_keys

    new_alerts = set()
    if new_nws:
        for a in new_nws.get("alerts", []):
            new_alerts.add(_alert_fingerprint(a))

    new_ranked = [h.key for h in (new_hazards_block.ranked if new_hazards_block else [])]

    changed = (new_alerts != _last_alert_set) or (new_ranked != _last_ranked_keys)
    if changed:
        _last_alert_set = new_alerts
        _last_ranked_keys = new_ranked
    return changed


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
            log.info("NWS poll OK")
        else:
            cache.mark_failed("nws")
            log.warning("NWS poll returned not-ok")
    except Exception as exc:
        cache.mark_failed("nws")
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


# ---------------------------------------------------------------------------
# State + briefing rebuild
# ---------------------------------------------------------------------------

# Track last briefing generation time
_last_briefing_at: Optional[datetime] = None
_last_briefing: Optional[dict] = None


def _rebuild_state(force_briefing: bool = False) -> None:
    """Rebuild the consolidated state from current cache and update it."""
    global _last_briefing_at, _last_briefing

    cfg = get_config()
    cache = get_cache()

    nws_data = cache.get_data("nws")
    spc_data = cache.get_data("spc")
    ga511_data = cache.get_data("ga511")
    airnow_data = cache.get_data("airnow")

    # Compute hazards
    hazards = hazards_module.compute_hazards(nws_data, spc_data, airnow_data, cfg)

    # Decide if we need to regenerate briefing
    now = datetime.now(tz=timezone.utc)
    briefing_interval = cfg.polling_seconds.get("briefing", 1800)
    need_briefing = (
        force_briefing
        or _last_briefing is None
        or _last_briefing_at is None
        or (now - _last_briefing_at).total_seconds() >= briefing_interval
        or _is_material_change(nws_data, hazards)
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

        mode = state_builder._compute_display_mode(cfg)

        # Build sources_used list
        sources_used = []
        if cache.get_source_block("nws").ok:
            sources_used.append("NWS FFC")
        if cache.get_source_block("spc").ok:
            sources_used.append("SPC")
        if cache.get_source_block("ga511").ok:
            sources_used.append("511GA")

        _last_briefing = briefing_module.generate_briefing(
            ranked_hazards=ranked_list,
            aqi_callout=aqi_dict,
            alerts=alerts,
            spc_outlook=spc_outlook,
            mode=mode,
            sources_used=sources_used,
        )
        _last_briefing_at = now
        log.info("Briefing regenerated (source=%s)", _last_briefing.get("source"))

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
    )
    cache.set_state(state.to_dict())
    log.debug("Consolidated state rebuilt")


def _full_poll_cycle() -> None:
    """Run all source polls then rebuild state. Used for initial load."""
    _poll_nws()
    _poll_spc()
    _poll_ga511()
    _poll_airnow()
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
