"""
EPA AirNow API poller.

Auth:   AIRNOW_API_KEY env var (free, register at airnowapi.org)
Limit:  500 req/hr per service — poll hourly (config.polling_seconds.airnow)
Format: JSON array of observation records

Returns normalized dict:
  {
    "aqi": int | None,
    "category": str | None,    # e.g. "Unhealthy for Sensitive Groups"
    "label": str | None,       # e.g. "Code Orange"
    "pollutant": str | None,   # e.g. "O3"
    "_ok": bool,
  }

AQI category breakpoints (firm — EPA standard):
  0-50    Good               (Green)
  51-100  Moderate           (Yellow)
  101-150 Unhealthy for SG   (Orange)  <- callout threshold
  151-200 Unhealthy          (Red)
  201-300 Very Unhealthy     (Purple)
  301+    Hazardous           (Maroon)
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

log = logging.getLogger(__name__)

_BASE_URL = "https://www.airnowapi.org/aq/observation/latLong/current/"

# EPA AQI breakpoints — do not modify; these are the firm standard
_AQI_CATEGORIES = [
    (0, 50, "Good", "Code Green"),
    (51, 100, "Moderate", "Code Yellow"),
    (101, 150, "Unhealthy for Sensitive Groups", "Code Orange"),
    (151, 200, "Unhealthy", "Code Red"),
    (201, 300, "Very Unhealthy", "Code Purple"),
    (301, 999, "Hazardous", "Code Maroon"),
]


def _aqi_label(aqi: int) -> tuple[str, str]:
    """Return (category, label) for a given AQI value."""
    for lo, hi, cat, label in _AQI_CATEGORIES:
        if lo <= aqi <= hi:
            return cat, label
    return "Hazardous", "Code Maroon"


def _get_api_key() -> Optional[str]:
    return os.environ.get("AIRNOW_API_KEY") or None


def fetch(client: Any, config: Any) -> dict[str, Any]:
    """
    Fetch current AQI observation from AirNow.
    Returns {"aqi": int|None, "category": str|None, "label": str|None, "pollutant": str|None, "_ok": bool}.
    """
    result: dict[str, Any] = {
        "aqi": None,
        "category": None,
        "label": None,
        "pollutant": None,
        "_ok": False,
    }

    api_key = _get_api_key()
    if not api_key:
        log.info("AIRNOW_API_KEY not set — skipping AirNow fetch")
        return result

    lat = config.lat
    lon = config.lon

    params = {
        "format": "application/json",
        "latitude": lat,
        "longitude": lon,
        "distance": 25,
        "API_KEY": api_key,
    }

    try:
        r = client.get(_BASE_URL, params=params, timeout=15)
        r.raise_for_status()
        observations = r.json()
    except Exception as exc:
        log.warning("AirNow fetch failed: %s", exc)
        return result

    if not observations:
        log.info("AirNow returned empty observations for lat=%s lon=%s", lat, lon)
        return result

    # Pick the highest AQI reading across all reported pollutants
    best_aqi = None
    best_pollutant = None

    for obs in observations:
        aqi_val = obs.get("AQI")
        pollutant = obs.get("ParameterName", "")
        if aqi_val is not None:
            try:
                aqi_int = int(aqi_val)
            except (ValueError, TypeError):
                continue
            if best_aqi is None or aqi_int > best_aqi:
                best_aqi = aqi_int
                best_pollutant = pollutant

    if best_aqi is None:
        return result

    cat, label = _aqi_label(best_aqi)
    result["aqi"] = best_aqi
    result["category"] = cat
    result["label"] = label
    result["pollutant"] = best_pollutant
    result["_ok"] = True
    return result
