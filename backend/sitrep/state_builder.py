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

from .models import (
    AlertEvent,
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
    LocationBlock,
    SourcesMap,
    SpcOutlook,
    TodayForecast,
    TrafficEvent,
    WeatherBlock,
    WindInfo,
)

log = logging.getLogger(__name__)


def _compute_display_mode(config: Any) -> str:
    """Return 'morning' or 'afternoon' based on current local time vs config."""
    morning_until = config.morning_until  # e.g. "12:00"
    try:
        h, m = morning_until.split(":")
        cutoff_minutes = int(h) * 60 + int(m)
    except Exception:
        cutoff_minutes = 12 * 60

    now_local = datetime.now().time()
    now_minutes = now_local.hour * 60 + now_local.minute
    return "morning" if now_minutes < cutoff_minutes else "afternoon"


def _iso_now() -> str:
    return datetime.now(tz=timezone.utc).astimezone().isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------

def _build_weather(nws_data: Optional[dict], nws_source_block: Any) -> WeatherBlock:
    if not nws_data:
        return WeatherBlock(source=nws_source_block)

    current_raw = nws_data.get("weather_current")
    today_raw = nws_data.get("weather_today")

    current = None
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

    today = None
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

    return WeatherBlock(current=current, today=today, source=nws_source_block)


def _build_disruptions(
    nws_data: Optional[dict],
    ga511_data: Optional[dict],
    combined_source: Any,
) -> DisruptionsBlock:
    traffic_items: list[TrafficEvent] = []
    alert_items: list[AlertEvent] = []

    # 511GA traffic events
    if ga511_data:
        for ev in ga511_data.get("traffic", []):
            traffic_items.append(TrafficEvent(text=ev["text"], type=ev["type"]))

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
) -> CommuteBlock:
    traffic_items: list[TrafficEvent] = []

    if ga511_data:
        for ev in ga511_data.get("traffic", []):
            traffic_items.append(TrafficEvent(text=ev["text"], type=ev["type"]))

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
    nws_sb: Any, spc_sb: Any, ga511_sb: Any, airnow_sb: Any
) -> SourcesMap:
    return SourcesMap(
        nws=nws_sb,
        spc=spc_sb,
        ga511=ga511_sb,
        airnow=airnow_sb,
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
    weather = _build_weather(nws_data, nws_sb)

    disruptions = _build_disruptions(
        nws_data, ga511_data,
        combined_source="511GA, NWS", # will be filled as SourceBlock by override below
    )
    # Override disruptions source with proper SourceBlock
    disruptions.source = _combined_source("511GA, NWS", [ga511_sb, nws_sb])

    commute = _build_commute(nws_data, ga511_data, None)
    commute.source = _combined_source("NWS, 511GA", [nws_sb, ga511_sb])

    forecast = _build_forecast_3day(nws_data, spc_data, None)
    forecast.source = _combined_source("NWS FFC, SPC", [nws_sb, spc_sb])

    sources_map = _build_sources_map(nws_sb, spc_sb, ga511_sb, airnow_sb)

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
        sources=sources_map,
    )
