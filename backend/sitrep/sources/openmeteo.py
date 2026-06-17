"""
Open-Meteo poller — supplementary richer weather series.

Open-Meteo (https://open-meteo.com) is free and keyless. It supplies the data
the NWS feed doesn't expose conveniently: an hourly series (temp, apparent temp,
wind, gusts, precip probability, precip amount, visibility) plus today's
sunrise/sunset and UV index.

Authoritative-numbers note (CLAUDE.md): NWS remains the authoritative source for
observations and alerts; Open-Meteo only fills the hourly table, charts, and the
sunrise/sunset/UV/visibility status-strip items. All values render verbatim
(after unit conversion, same as nws.py converts C→F).

Auth:   none (keyless)
Limit:  generous free tier — poll ~15 min (config.polling_seconds.openmeteo)
Format: JSON with hourly[] + daily[] arrays keyed by ISO timestamps.

Returns a normalized dict consumed by state_builder.py:
  {
    "hourly": [
      {"time", "temp_f", "feels_like_f", "wind_mph", "gust_mph",
       "pop_pct", "precip_in"}, ...   # next ~12 hours from "now"
    ],
    "today": {"sunrise", "sunset", "uv_index", "visibility_mi"},
    "_ok": bool,
  }
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

log = logging.getLogger(__name__)

_BASE_URL = "https://api.open-meteo.com/v1/forecast"

# How many hours of the hourly series to keep (legible across the room).
_HOURLY_KEEP = 12

# meters → miles
_M_TO_MI = 0.000621371


def _round_or_none(v: Any, ndigits: int = 1) -> Optional[float]:
    if v is None:
        return None
    try:
        return round(float(v), ndigits)
    except (TypeError, ValueError):
        return None


def _int_or_none(v: Any) -> Optional[int]:
    if v is None:
        return None
    try:
        return int(round(float(v)))
    except (TypeError, ValueError):
        return None


def _timezone(config: Any) -> str:
    """IANA timezone for the Open-Meteo request (keeps arrays local-aligned)."""
    tz = config.get("weather", "timezone", default=None)
    return tz or "America/New_York"


def fetch(client: Any, config: Any) -> dict[str, Any]:
    """Fetch the Open-Meteo forecast and normalize it. Keyless."""
    result: dict[str, Any] = {"hourly": [], "today": {}, "_ok": False}

    params = {
        "latitude": config.lat,
        "longitude": config.lon,
        "hourly": ",".join([
            "temperature_2m",
            "apparent_temperature",
            "wind_speed_10m",
            "wind_gusts_10m",
            "precipitation_probability",
            "precipitation",
            "visibility",
        ]),
        "daily": "sunrise,sunset,uv_index_max",
        "temperature_unit": "fahrenheit",
        "wind_speed_unit": "mph",
        "precipitation_unit": "inch",
        "timezone": _timezone(config),
        "forecast_days": 2,
    }

    try:
        r = client.get(_BASE_URL, params=params, timeout=15)
        r.raise_for_status()
        payload = r.json()
    except Exception as exc:
        log.warning("Open-Meteo fetch failed: %s", exc)
        return result

    # ── Hourly series ────────────────────────────────────────────────────────
    try:
        hourly = payload.get("hourly", {}) or {}
        times = hourly.get("time", []) or []
        temps = hourly.get("temperature_2m", []) or []
        feels = hourly.get("apparent_temperature", []) or []
        winds = hourly.get("wind_speed_10m", []) or []
        gusts = hourly.get("wind_gusts_10m", []) or []
        pops = hourly.get("precipitation_probability", []) or []
        precs = hourly.get("precipitation", []) or []
        viss = hourly.get("visibility", []) or []

        # Start at the current local hour; Open-Meteo times are local (per tz).
        now_prefix = datetime.now().strftime("%Y-%m-%dT%H")
        start_ix = 0
        for i, t in enumerate(times):
            if str(t)[:13] >= now_prefix:
                start_ix = i
                break

        points: list[dict[str, Any]] = []
        for i in range(start_ix, min(start_ix + _HOURLY_KEEP, len(times))):
            def at(arr: list, ix: int = i) -> Any:
                return arr[ix] if ix < len(arr) else None
            points.append({
                "time": times[i],
                "temp_f": _round_or_none(at(temps)),
                "feels_like_f": _round_or_none(at(feels)),
                "wind_mph": _round_or_none(at(winds)),
                "gust_mph": _round_or_none(at(gusts)),
                "pop_pct": _int_or_none(at(pops)),
                "precip_in": _round_or_none(at(precs), 2),
            })
        result["hourly"] = points

        # Visibility "now" (first kept hour) → miles
        if start_ix < len(viss):
            result["today"]["visibility_mi"] = _round_or_none(viss[start_ix] * _M_TO_MI, 1)
    except Exception as exc:
        log.warning("Open-Meteo hourly parse failed: %s", exc)

    # ── Daily (today's sunrise/sunset/UV) ──────────────────────────────────────
    try:
        daily = payload.get("daily", {}) or {}
        sunrises = daily.get("sunrise", []) or []
        sunsets = daily.get("sunset", []) or []
        uvs = daily.get("uv_index_max", []) or []
        if sunrises:
            result["today"]["sunrise"] = sunrises[0]
        if sunsets:
            result["today"]["sunset"] = sunsets[0]
        if uvs:
            result["today"]["uv_index"] = _round_or_none(uvs[0], 1)
    except Exception as exc:
        log.warning("Open-Meteo daily parse failed: %s", exc)

    # Consider the poll OK if we got either an hourly series or any daily field.
    result["_ok"] = bool(result["hourly"] or result["today"])
    return result
