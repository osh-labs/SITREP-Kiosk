"""
Open-Meteo gridded temperature poller — feeds the map's temperature layer.

The dashboard map rotates between radar, watch/warning polygons, and a
temperature view. NWS and the point Open-Meteo poller (openmeteo.py) only give
a single station/point temperature, which can't paint a map. This poller samples
a small lat/lon grid across the visible map area in one keyless Open-Meteo bulk
request and returns the readings as a GeoJSON point FeatureCollection.

Authoritative-numbers note (CLAUDE.md): these gridded values are non-authoritative
situational shading for the map only, the same class as the IEM radar imagery.
The authoritative "current temperature" shown elsewhere on the board still comes
from NWS; this layer never overrides it.

Auth:   none (keyless)
Limit:  generous free tier — one bulk request, poll ~15 min
        (config.polling_seconds.temps)
Format: Open-Meteo returns a JSON array (one object per coordinate) when given
        comma-separated latitude/longitude lists, each with current.temperature_2m.

Returns the GeoJSON dict consumed by /api/temps.geojson:
  {
    "type": "FeatureCollection",
    "features": [
      {"type": "Feature",
       "geometry": {"type": "Point", "coordinates": [lon, lat]},
       "properties": {"temp_f": 78}}, ...
    ],
    "_ok": bool,
  }
"""
from __future__ import annotations

import logging
from typing import Any, Optional

log = logging.getLogger(__name__)

_BASE_URL = "https://api.open-meteo.com/v1/forecast"

# Defaults if config.weather_map.temps is absent. A 7x7 grid spanning ~3 degrees
# centered on the location covers the zoom-8 metro view with one bulk request.
_DEFAULT_ROWS = 7
_DEFAULT_COLS = 7
_DEFAULT_SPAN_DEG = 3.0


def _temps_cfg(config: Any) -> dict[str, Any]:
    cfg = config.get("weather_map", "temps", default=None)
    return cfg if isinstance(cfg, dict) else {}


def _grid_points(
    lat: float, lon: float, rows: int, cols: int, span: float
) -> list[tuple[float, float]]:
    """A rows x cols lat/lon grid centered on (lat, lon), spanning `span` degrees."""
    pts: list[tuple[float, float]] = []
    for r in range(rows):
        for c in range(cols):
            la = lat - span / 2 + span * (r / (rows - 1)) if rows > 1 else lat
            lo = lon - span / 2 + span * (c / (cols - 1)) if cols > 1 else lon
            pts.append((round(la, 4), round(lo, 4)))
    return pts


def _int_or_none(v: Any) -> Optional[int]:
    if v is None:
        return None
    try:
        return int(round(float(v)))
    except (TypeError, ValueError):
        return None


def fetch(client: Any, config: Any) -> dict[str, Any]:
    """Fetch a temperature grid and return it as a GeoJSON FeatureCollection. Keyless."""
    result: dict[str, Any] = {"type": "FeatureCollection", "features": [], "_ok": False}

    tcfg = _temps_cfg(config)
    rows = int(tcfg.get("grid_rows", _DEFAULT_ROWS))
    cols = int(tcfg.get("grid_cols", _DEFAULT_COLS))
    span = float(tcfg.get("span_deg", _DEFAULT_SPAN_DEG))

    points = _grid_points(config.lat, config.lon, rows, cols, span)
    if not points:
        return result

    params = {
        "latitude": ",".join(str(p[0]) for p in points),
        "longitude": ",".join(str(p[1]) for p in points),
        "current": "temperature_2m",
        "temperature_unit": "fahrenheit",
    }

    try:
        r = client.get(_BASE_URL, params=params, timeout=15)
        r.raise_for_status()
        payload = r.json()
    except Exception as exc:
        log.warning("Open-Meteo grid fetch failed: %s", exc)
        return result

    # A multi-coordinate request returns a list; a single coordinate returns a dict.
    items = payload if isinstance(payload, list) else [payload]

    features: list[dict[str, Any]] = []
    for i, item in enumerate(items):
        try:
            temp_f = _int_or_none((item.get("current") or {}).get("temperature_2m"))
            if temp_f is None:
                continue
            # Prefer the requested coordinate for stable placement; fall back to
            # the (possibly grid-snapped) coordinate Open-Meteo echoes back.
            if i < len(points):
                la, lo = points[i]
            else:
                la, lo = item.get("latitude"), item.get("longitude")
            features.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lo, la]},
                "properties": {"temp_f": temp_f},
            })
        except Exception:
            continue

    result["features"] = features
    result["_ok"] = bool(features)
    return result
