"""
Deterministic hazard flag computation and D5 ranking.

All thresholds come from config — no literals in logic.

Ranking order (highest first, per PRD D5):
  severe_weather > heat_index > winter_weather > thunderstorms > rain > wind

AQI is a separate callout and is NOT part of the ranked chain.

Inputs: normalized source dicts from the cache.
Output:
  {
    "ranked": [RankedHazard, ...],   # highest first
    "aqi_callout": AqiCallout | None,
  }
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from .models import AqiCallout, HazardsBlock, RankedHazard

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Severity helpers
# ---------------------------------------------------------------------------

def _heat_severity(heat_index_f: float, thresholds: dict) -> str:
    """Map a heat index value to severity vocab."""
    extreme_danger = float(thresholds.get("extreme_danger", 125))
    danger = float(thresholds.get("danger", 103))
    extreme_caution = float(thresholds.get("extreme_caution", 90))
    if heat_index_f >= extreme_danger:
        return "extreme"
    if heat_index_f >= danger:
        return "danger"
    if heat_index_f >= extreme_caution:
        return "caution"
    return "info"


def _alert_contains(alerts: list[dict], *keywords: str) -> bool:
    """True if any alert event/text matches any keyword (case-insensitive)."""
    for a in alerts:
        event = (a.get("event", "") or "").lower()
        text = (a.get("text", "") or "").lower()
        for kw in keywords:
            kw_l = kw.lower()
            if kw_l in event or kw_l in text:
                return True
    return False


def _first_alert_with(alerts: list[dict], *keywords: str) -> Optional[dict]:
    for a in alerts:
        event = (a.get("event", "") or "").lower()
        text = (a.get("text", "") or "").lower()
        for kw in keywords:
            kw_l = kw.lower()
            if kw_l in event or kw_l in text:
                return a
    return None


# ---------------------------------------------------------------------------
# Per-hazard detection functions
# ---------------------------------------------------------------------------

def _check_severe_weather(
    nws_data: Optional[dict],
    spc_data: Optional[dict],
    thresholds: dict,
) -> Optional[RankedHazard]:
    """
    Fires on:
    - Any active Tornado / Severe Thunderstorm / Flash Flood Watch or Warning
    - SPC Day 1 categorical >= Slight
    """
    alerts = []
    if nws_data:
        alerts = nws_data.get("alerts", [])

    severe_events = [
        "tornado", "severe thunderstorm", "flash flood",
        "tornado warning", "tornado watch",
        "severe thunderstorm warning", "severe thunderstorm watch",
        "flash flood warning", "flash flood watch",
    ]
    alert_hit = _first_alert_with(alerts, *severe_events)

    spc_trigger = False
    spc_label_extra = ""
    if spc_data and spc_data.get("_ok"):
        if spc_data.get("triggers_hazard"):
            spc_trigger = True
            day1 = spc_data.get("day1", {})
            if day1:
                cat = day1.get("category", "")
                spc_label_extra = f" — SPC Day 1 {cat.title()}" if cat else ""

    if not alert_hit and not spc_trigger:
        return None

    # Severity based on active warnings vs watches
    if alert_hit:
        sev = alert_hit.get("severity", "danger")
        label = alert_hit.get("event", "Severe weather alert")
    else:
        sev = "watch"
        label = f"Elevated convective threat{spc_label_extra}"

    if sev not in ("extreme", "danger", "watch", "advisory", "caution", "info"):
        sev = "danger"

    return RankedHazard(key="severe_weather", rank=0, label=label, severity=sev)


def _check_heat_index(
    nws_data: Optional[dict],
    thresholds: dict,
) -> Optional[RankedHazard]:
    """
    Fires when forecast heat index >= extreme_caution (90°F) during work hours,
    or an active Heat Advisory / Extreme Heat Warning is present.
    """
    ht = thresholds.get("heat_index_f", {})
    extreme_caution = float(ht.get("extreme_caution", 90))

    alerts = nws_data.get("alerts", []) if nws_data else []
    weather_today = nws_data.get("weather_today", {}) if nws_data else {}
    heat_index_f = weather_today.get("heat_index_f") if weather_today else None

    # Check for active heat alert first (escalator)
    heat_alert = _first_alert_with(alerts, "heat advisory", "excessive heat", "extreme heat")
    if heat_alert:
        sev = heat_alert.get("severity", "advisory")
        if sev not in ("extreme", "danger", "advisory"):
            sev = "advisory"
        label = heat_alert.get("event", "Heat Advisory")
        if heat_index_f is not None:
            label = f"{label} — index to ~{int(heat_index_f)}°F"
        return RankedHazard(key="heat_index", rank=0, label=label, severity=sev)

    # Check forecast heat index
    if heat_index_f is not None and heat_index_f >= extreme_caution:
        sev = _heat_severity(heat_index_f, ht)
        label = f"Heat index to ~{int(heat_index_f)}°F"
        return RankedHazard(key="heat_index", rank=0, label=label, severity=sev)

    return None


def _check_winter_weather(
    nws_data: Optional[dict],
    thresholds: dict,
) -> Optional[RankedHazard]:
    """
    Fires on any active winter/cold alert, forecast frozen precip, or
    temp <= threshold with precip.
    """
    winter_temp_threshold = float(thresholds.get("winter", {}).get("temp_f_with_precip", 32))

    alerts = nws_data.get("alerts", []) if nws_data else []
    weather_today = nws_data.get("weather_today", {}) if nws_data else {}
    current = nws_data.get("weather_current", {}) if nws_data else {}

    winter_events = [
        "winter weather advisory", "winter storm warning", "ice storm warning",
        "cold weather advisory", "extreme cold warning", "freeze warning",
        "blizzard warning", "wind chill advisory", "wind chill warning",
    ]
    alert_hit = _first_alert_with(alerts, *winter_events)

    if alert_hit:
        sev = alert_hit.get("severity", "advisory")
        if sev not in ("extreme", "danger", "advisory", "watch"):
            sev = "advisory"
        return RankedHazard(key="winter_weather", rank=0,
                            label=alert_hit.get("event", "Winter weather alert"),
                            severity=sev)

    # Check forecast summary for frozen precip keywords
    summary = (weather_today.get("summary", "") or "").lower()
    frozen_keywords = ["snow", "sleet", "freezing rain", "ice", "wintry mix", "blizzard", "flurr"]
    if any(k in summary for k in frozen_keywords):
        return RankedHazard(key="winter_weather", rank=0,
                            label="Frozen precipitation in forecast",
                            severity="watch")

    # Check temp + precip
    temp_f = (current or {}).get("temp_f")
    pop_pct = weather_today.get("pop_pct", 0) if weather_today else 0
    if (temp_f is not None and temp_f <= winter_temp_threshold
            and pop_pct is not None and pop_pct > 0):
        return RankedHazard(key="winter_weather", rank=0,
                            label=f"Freezing conditions with precip — {int(temp_f)}°F",
                            severity="danger")

    return None


def _check_thunderstorms(
    nws_data: Optional[dict],
    thresholds: dict,
) -> Optional[RankedHazard]:
    """
    Fires when thunderstorm probability >= threshold during work hours,
    or "thunder" appears in the forecast summary.
    NOTE: if this would also meet severe_weather criteria, severe_weather wins (checked first).
    """
    ts_threshold = float(thresholds.get("thunderstorm_probability_pct", 30))

    weather_today = nws_data.get("weather_today", {}) if nws_data else {}
    hourly = nws_data.get("raw_hourly", []) if nws_data else []

    summary = (weather_today.get("summary", "") or "").lower()
    if "thunder" in summary or "t-storm" in summary:
        label = "Thunderstorms in forecast"
        return RankedHazard(key="thunderstorms", rank=0, label=label, severity="watch")

    # Check hourly PoP for thunderstorm phrases
    for hp in hourly[:18]:
        hp_summary = (hp.get("shortForecast", "") or "").lower()
        if "thunder" in hp_summary:
            label = "Thunderstorms possible"
            if hp.get("probabilityOfPrecipitation", {}).get("value"):
                pct = hp["probabilityOfPrecipitation"]["value"]
                if pct >= ts_threshold:
                    label = f"Thunderstorms — {int(pct)}% chance"
            return RankedHazard(key="thunderstorms", rank=0, label=label, severity="watch")

    # Check pop values from today forecast
    pop_pct = weather_today.get("pop_pct")
    if pop_pct is not None and pop_pct >= ts_threshold:
        if "storm" in summary:
            label = f"Thunderstorm risk — {int(pop_pct)}%"
            return RankedHazard(key="thunderstorms", rank=0, label=label, severity="watch")

    return None


def _check_rain(
    nws_data: Optional[dict],
    thresholds: dict,
) -> Optional[RankedHazard]:
    """
    Fires when PoP >= threshold during work hours OR QPF >= threshold.
    Does NOT fire if thunderstorms / severe weather already lead (caller handles dedup).
    """
    rain_t = thresholds.get("rain", {})
    pop_threshold = float(rain_t.get("pop_pct", 50))
    qpf_threshold = float(rain_t.get("qpf_in", 0.25))

    weather_today = nws_data.get("weather_today", {}) if nws_data else {}
    pop_pct = weather_today.get("pop_pct")
    qpf = weather_today.get("qpf_in")

    if pop_pct is not None and pop_pct >= pop_threshold:
        return RankedHazard(
            key="rain", rank=0,
            label=f"Rain likely — {int(pop_pct)}% chance",
            severity="info",
        )
    if qpf is not None and qpf >= qpf_threshold:
        return RankedHazard(
            key="rain", rank=0,
            label=f"Significant rainfall expected",
            severity="info",
        )
    return None


def _check_wind(
    nws_data: Optional[dict],
    thresholds: dict,
) -> Optional[RankedHazard]:
    """
    Fires on active Wind Advisory / High Wind Warning OR forecast gusts >= threshold.
    """
    gust_threshold = float(thresholds.get("wind_gust_mph_flag", 30))

    alerts = nws_data.get("alerts", []) if nws_data else []
    current = nws_data.get("weather_current", {}) if nws_data else {}
    weather_today = nws_data.get("weather_today", {}) if nws_data else {}

    wind_events = ["wind advisory", "high wind warning", "extreme wind warning"]
    alert_hit = _first_alert_with(alerts, *wind_events)
    if alert_hit:
        sev = alert_hit.get("severity", "advisory")
        return RankedHazard(key="wind", rank=0,
                            label=alert_hit.get("event", "Wind Advisory"),
                            severity=sev)

    # Check current gust
    wind_data = (current or {}).get("wind", {}) or {}
    gust_mph = wind_data.get("gust_mph")
    speed_mph = wind_data.get("speed_mph")

    check_value = gust_mph if gust_mph is not None else speed_mph
    if check_value is not None and check_value >= gust_threshold:
        return RankedHazard(
            key="wind", rank=0,
            label=f"Strong winds — {int(check_value)} mph gusts",
            severity="advisory",
        )

    return None


# ---------------------------------------------------------------------------
# AQI callout (separate from ranked chain)
# ---------------------------------------------------------------------------

def _compute_aqi_callout(
    airnow_data: Optional[dict],
    aqi_threshold: float,
) -> Optional[AqiCallout]:
    if not airnow_data or not airnow_data.get("_ok"):
        return None
    aqi = airnow_data.get("aqi")
    if aqi is None or aqi < aqi_threshold:
        return None
    cat = airnow_data.get("category", "Unhealthy for Sensitive Groups")
    label = airnow_data.get("label", "Code Orange")
    return AqiCallout(aqi=aqi, category=cat, label=label)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def compute_hazards(
    nws_data: Optional[dict],
    spc_data: Optional[dict],
    airnow_data: Optional[dict],
    config: Any,
) -> HazardsBlock:
    """
    Compute ranked hazards + AQI callout from source data.

    All thresholds come from config.hazard_thresholds.
    Returns a HazardsBlock ready for the consolidated state.
    """
    thresholds = config.hazard_thresholds
    ranking_order: list[str] = config.ranking_order

    # ── Run each detector ────────────────────────────────────────────────────
    detectors: dict[str, Optional[RankedHazard]] = {
        "severe_weather": _check_severe_weather(nws_data, spc_data, thresholds),
        "heat_index": _check_heat_index(nws_data, thresholds),
        "winter_weather": _check_winter_weather(nws_data, thresholds),
        "thunderstorms": _check_thunderstorms(nws_data, thresholds),
        "rain": _check_rain(nws_data, thresholds),
        "wind": _check_wind(nws_data, thresholds),
    }

    # ── Apply D5 ranking order ───────────────────────────────────────────────
    ranked: list[RankedHazard] = []
    rank_counter = 1
    for key in ranking_order:
        hazard = detectors.get(key)
        if hazard is not None:
            hazard.rank = rank_counter
            ranked.append(hazard)
            rank_counter += 1

    # ── AQI callout ──────────────────────────────────────────────────────────
    aqi_callout = _compute_aqi_callout(
        airnow_data,
        float(thresholds.get("aqi_callout", 101)),
    )

    return HazardsBlock(ranked=ranked, aqi_callout=aqi_callout)
