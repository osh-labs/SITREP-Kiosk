"""
Assembles the consolidated state from cached source data + hazards + briefing.

Computes display.mode (morning/afternoon) from config mode windows and
current local time. Fills every source freshness block from the cache.
Output validates against the fixtures shape (STATE_CONTRACT.md).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo

from . import astro as astro_module
from .models import (
    AlertEvent,
    AstroBlock,
    BriefingBlock,
    CommuteBlock,
    CommuteCurrentConditions,
    ConsolidatedState,
    CurrentConditions,
    DisruptionsBlock,
    DisplayBlock,
    Forecast3DayBlock,
    ForecastDay,
    HazardsBlock,
    HourlyPoint,
    LocationBlock,
    MapBlock,
    SourcesMap,
    SpcOutlook,
    TodayForecast,
    TrafficEvent,
    WeatherBlock,
    WindInfo,
)

log = logging.getLogger(__name__)


def _compute_display_mode(config: Any) -> str:
    """Return 'morning' or 'afternoon' based on current time in the configured timezone."""
    morning_until = config.morning_until  # e.g. "12:00"
    try:
        h, m = morning_until.split(":")
        cutoff_minutes = int(h) * 60 + int(m)
    except Exception:
        cutoff_minutes = 12 * 60

    try:
        tz = ZoneInfo(config.timezone)
    except Exception:
        tz = ZoneInfo("America/New_York")

    now_local = datetime.now(tz=tz).time()
    now_minutes = now_local.hour * 60 + now_local.minute
    return "morning" if now_minutes < cutoff_minutes else "afternoon"


def _iso_now() -> str:
    return datetime.now(tz=timezone.utc).astimezone().isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------

def _build_weather(
    nws_data: Optional[dict],
    openmeteo_data: Optional[dict],
    nws_source_block: Any,
) -> WeatherBlock:
    """Build the weather block.

    NWS supplies current conditions + today high/low/heat-index/pop (authoritative
    observations/forecast). Open-Meteo supplies the hourly series and today's
    sunrise/sunset/UV/visibility. NWS numbers are never overwritten by Open-Meteo.
    """
    current = None
    today = None

    if nws_data:
        current_raw = nws_data.get("weather_current")
        today_raw = nws_data.get("weather_today")

        if current_raw:
            wind_raw = current_raw.get("wind", {}) or {}
            wind = WindInfo(
                dir=wind_raw.get("dir"),
                speed_mph=wind_raw.get("speed_mph"),
                gust_mph=wind_raw.get("gust_mph"),
            )
            current = CurrentConditions(
                temp_f=current_raw.get("temp_f"),
                feels_like_f=current_raw.get("feels_like_f"),
                wind=wind,
                summary=current_raw.get("summary"),
            )

        if today_raw:
            today = TodayForecast(
                high_f=today_raw.get("high_f"),
                low_f=today_raw.get("low_f"),
                heat_index_f=today_raw.get("heat_index_f"),
                pop_pct=today_raw.get("pop_pct"),
                pop_window=today_raw.get("pop_window"),
                daylight_until=today_raw.get("daylight_until"),
                summary=today_raw.get("summary"),
            )

    # ── Open-Meteo extras (hourly + sunrise/sunset/UV/visibility) ──────────────
    hourly: list[HourlyPoint] = []
    if openmeteo_data:
        for hp in openmeteo_data.get("hourly", []) or []:
            hourly.append(HourlyPoint(
                time=hp.get("time", ""),
                temp_f=hp.get("temp_f"),
                feels_like_f=hp.get("feels_like_f"),
                heat_index_f=hp.get("heat_index_f"),
                wind_mph=hp.get("wind_mph"),
                gust_mph=hp.get("gust_mph"),
                pop_pct=hp.get("pop_pct"),
                precip_in=hp.get("precip_in"),
            ))
        om_today = openmeteo_data.get("today", {}) or {}
        if om_today:
            if today is None:
                today = TodayForecast()
            today.sunrise = om_today.get("sunrise")
            today.sunset = om_today.get("sunset")
            today.uv_index = om_today.get("uv_index")
            today.visibility_mi = om_today.get("visibility_mi")

    return WeatherBlock(current=current, today=today, hourly=hourly, source=nws_source_block)


def _build_astro(now: Optional[datetime] = None) -> AstroBlock:
    """Compute moon phase deterministically (no source)."""
    data = astro_module.moon_phase(now)
    return AstroBlock(
        moon_phase=data["moon_phase"],
        illumination_pct=data["illumination_pct"],
        phase_fraction=data["phase_fraction"],
    )


_DEFAULT_MAP_CONFIG = {
    "enabled": True,
    "center": {"lat": 33.7490, "lon": -84.3880},
    "default_zoom": 8,
    "min_zoom": 6,
    "max_zoom": 10,
    "base_style": "dark",
    "layers": {
        "radar": {"default_on": True, "opacity": 0.7},
        "alerts": {"default_on": True},
        "temps": {"default_on": True, "opacity": 0.85},
    },
    "animation": {"enabled": True, "frames": 8, "interval_ms": 600, "refresh_seconds": 300},
    "rotation": {"enabled": True, "interval_seconds": 20, "modes": ["radar", "alerts", "temps"]},
    "temps": {"grid_rows": 7, "grid_cols": 7, "span_deg": 3.0},
}


def _build_weather_map(config: Any, source_block: Any) -> MapBlock:
    """Surface the weather_map config (with location fallback) + freshness."""
    cfg_map = config.get("weather_map", default=None)
    map_cfg = dict(_DEFAULT_MAP_CONFIG)
    if isinstance(cfg_map, dict):
        map_cfg = {**_DEFAULT_MAP_CONFIG, **cfg_map}
    # Default the map center to the configured location when unset.
    if not map_cfg.get("center"):
        map_cfg["center"] = {"lat": config.lat, "lon": config.lon}
    return MapBlock(config=map_cfg, source=source_block)


def _traffic_events(ga511_data: Optional[dict], max_events: Optional[int]) -> list[TrafficEvent]:
    """Build ranked TrafficEvents from 511GA data, worst first, capped to max_events."""
    items: list[TrafficEvent] = []
    if ga511_data:
        for ev in ga511_data.get("traffic", []):
            items.append(TrafficEvent(
                text=ev["text"],
                type=ev["type"],
                priority=int(ev.get("priority", 0)),
            ))
    # ga511 already sorts; re-sort defensively so cached/fixture data is ordered too.
    items.sort(key=lambda t: t.priority, reverse=True)
    if max_events is not None and max_events > 0:
        items = items[:max_events]
    return items


def _build_disruptions(
    nws_data: Optional[dict],
    ga511_data: Optional[dict],
    combined_source: Any,
    max_events: Optional[int] = None,
) -> DisruptionsBlock:
    alert_items: list[AlertEvent] = []
    traffic_items = _traffic_events(ga511_data, max_events)

    # NWS alerts
    if nws_data:
        for a in nws_data.get("alerts", []):
            alert_items.append(AlertEvent(
                text=a.get("text", ""),
                event=a.get("event", ""),
                severity=a.get("severity", "info"),
            ))

    return DisruptionsBlock(
        traffic=traffic_items,
        alerts=alert_items,
        source=combined_source,
    )


def _build_commute(
    nws_data: Optional[dict],
    ga511_data: Optional[dict],
    combined_source: Any,
    max_events: Optional[int] = None,
) -> CommuteBlock:
    traffic_items = _traffic_events(ga511_data, max_events)

    current = None
    if nws_data:
        current_raw = nws_data.get("weather_current")
        today_raw = nws_data.get("weather_today")
        if current_raw:
            current = CommuteCurrentConditions(
                temp_f=current_raw.get("temp_f"),
                feels_like_f=current_raw.get("feels_like_f"),
                summary=today_raw.get("summary") if today_raw else None,
            )

    return CommuteBlock(
        current=current,
        traffic=traffic_items,
        source=combined_source,
    )


def _build_forecast_3day(
    nws_data: Optional[dict],
    spc_data: Optional[dict],
    combined_source: Any,
) -> Forecast3DayBlock:
    days: list[ForecastDay] = []
    spc_outlook = None

    if nws_data:
        for d in nws_data.get("forecast_days", [])[:3]:
            days.append(ForecastDay(
                name=d.get("name", ""),
                high_f=d.get("high_f"),
                low_f=d.get("low_f"),
                summary=d.get("summary"),
                icon=d.get("icon"),
            ))

    if spc_data and spc_data.get("_ok"):
        # Build outlook text from highest-risk day
        highest_day = spc_data.get("highest_day")
        highest_cat = spc_data.get("highest_category")
        if highest_day and highest_cat and highest_cat not in ("none", "thunderstorm"):
            day_name = {1: "today", 2: "tomorrow"}.get(highest_day, f"day {highest_day}")
            spc_outlook = SpcOutlook(
                text=f"{highest_cat.title()} risk — {day_name}",
                category=highest_cat,
                day=highest_day,
            )

    return Forecast3DayBlock(
        days=days,
        spc_outlook=spc_outlook,
        source=combined_source,
    )


def _build_sources_map(
    nws_sb: Any, spc_sb: Any, ga511_sb: Any, airnow_sb: Any,
    openmeteo_sb: Any, weather_map_sb: Any,
) -> SourcesMap:
    return SourcesMap(
        nws=nws_sb,
        spc=spc_sb,
        ga511=ga511_sb,
        airnow=airnow_sb,
        openmeteo=openmeteo_sb,
        weather_map=weather_map_sb,
    )


def _combined_source(name: str, blocks: list[Any]) -> Any:
    """
    Create a combined source block from multiple source blocks.
    ok=False if any is not ok; stale=True if any is stale.
    Uses the oldest fetched_at from the set.
    """
    from .models import SourceBlock
    ok = all(b.ok for b in blocks if b is not None)
    stale = any(b.stale for b in blocks if b is not None)
    # Pick the most recent fetched_at
    fetched_at = None
    age_seconds = None
    last_good_at = None
    for b in blocks:
        if b and b.fetched_at:
            if fetched_at is None or (b.age_seconds or 0) < (age_seconds or 0):
                fetched_at = b.fetched_at
                age_seconds = b.age_seconds
                last_good_at = b.last_good_at
    return SourceBlock(
        name=name,
        ok=ok,
        stale=stale,
        fetched_at=fetched_at,
        age_seconds=age_seconds,
        last_good_at=last_good_at,
    )


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------

def build_state(
    nws_data: Optional[dict],
    spc_data: Optional[dict],
    ga511_data: Optional[dict],
    airnow_data: Optional[dict],
    hazards: HazardsBlock,
    briefing: Optional[dict],
    cache: Any,
    config: Any,
    openmeteo_data: Optional[dict] = None,
) -> ConsolidatedState:
    """
    Assemble the full consolidated state dict.

    Parameters
    ----------
    nws_data, spc_data, ga511_data, airnow_data:
        Last-good normalized dicts from the cache (may be None).
    hazards:
        Computed HazardsBlock.
    briefing:
        Briefing dict from briefing.generate_briefing (may be None for initial build).
    cache:
        StateCache instance (for source block freshness).
    config:
        Config instance.
    """
    now = _iso_now()

    # ── Source freshness blocks ──────────────────────────────────────────────
    nws_sb = cache.get_source_block("nws")
    spc_sb = cache.get_source_block("spc")
    ga511_sb = cache.get_source_block("ga511")
    airnow_sb = cache.get_source_block("airnow")
    openmeteo_sb = cache.get_source_block("openmeteo")
    weather_map_sb = cache.get_source_block("weather_map")

    # ── Display mode ─────────────────────────────────────────────────────────
    mode = _compute_display_mode(config)
    display = DisplayBlock(
        mode=mode,
        dwell_seconds=config.dwell_seconds,
        refresh_seconds=config.refresh_seconds,
    )

    # ── Location ─────────────────────────────────────────────────────────────
    location = LocationBlock(
        name=config.location_name,
        lat=config.lat,
        lon=config.lon,
    )

    # ── Briefing ─────────────────────────────────────────────────────────────
    if briefing:
        b_block = BriefingBlock(
            bottom_line=briefing.get("bottom_line", ""),
            watch_for=briefing.get("watch_for", []),
            source=briefing.get("source", "template"),
            generated_at=briefing.get("generated_at", now),
            sources=briefing.get("sources", []),
        )
    else:
        b_block = BriefingBlock(
            bottom_line="Briefing not yet available.",
            watch_for=[],
            source="template",
            generated_at=now,
            sources=[],
        )

    # ── Section blocks ────────────────────────────────────────────────────────
    weather = _build_weather(nws_data, openmeteo_data, nws_sb)

    max_traffic = config.get("traffic", "max_events", default=6)

    disruptions = _build_disruptions(
        nws_data, ga511_data,
        combined_source="511GA, NWS", # will be filled as SourceBlock by override below
        max_events=max_traffic,
    )
    # Override disruptions source with proper SourceBlock
    disruptions.source = _combined_source("511GA, NWS", [ga511_sb, nws_sb])

    commute = _build_commute(nws_data, ga511_data, None, max_events=max_traffic)
    commute.source = _combined_source("NWS, 511GA", [nws_sb, ga511_sb])

    forecast = _build_forecast_3day(nws_data, spc_data, None)
    forecast.source = _combined_source("NWS FFC, SPC", [nws_sb, spc_sb])

    astro = _build_astro()
    weather_map = _build_weather_map(config, weather_map_sb)

    sources_map = _build_sources_map(
        nws_sb, spc_sb, ga511_sb, airnow_sb, openmeteo_sb, weather_map_sb
    )

    return ConsolidatedState(
        generated_at=now,
        display=display,
        location=location,
        briefing=b_block,
        hazards=hazards,
        weather=weather,
        commute=commute,
        disruptions=disruptions,
        forecast_3day=forecast,
        astro=astro,
        weather_map=weather_map,
        sources=sources_map,
    )
