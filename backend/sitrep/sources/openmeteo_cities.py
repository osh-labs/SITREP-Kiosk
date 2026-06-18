"""
Open-Meteo city-temperature poller — feeds the map's temperature view.

The dashboard map rotates between radar, watch/warning polygons, and a
temperature view. NWS and the point Open-Meteo poller (openmeteo.py) only give
a single station temperature, which can't paint the regional map. This poller
reads the current temperature for a fixed list of major cities across the
visible region (TN/AL/GA/FL panhandle/SC/western NC at the kiosk's 4K zoom-8
framing) in one keyless Open-Meteo bulk request and returns them as a labeled
GeoJSON point FeatureCollection.

Authoritative-numbers note (CLAUDE.md): these city readings are non-authoritative
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
       "properties": {"name": "Atlanta", "temp_f": 91}}, ...
    ],
    "_ok": bool,
  }
"""
from __future__ import annotations

import logging
from typing import Any, Optional

log = logging.getLogger(__name__)

_BASE_URL = "https://api.open-meteo.com/v1/forecast"

# Default cities if config.weather_map.temps.cities is absent. Spread across the
# region the kiosk map shows at its 4K zoom-8 framing.
_DEFAULT_CITIES: list[dict[str, Any]] = [
    {"name": "Atlanta",      "lat": 33.749, "lon": -84.388},
    {"name": "Athens",       "lat": 33.961, "lon": -83.378},
    {"name": "Macon",        "lat": 32.841, "lon": -83.632},
    {"name": "Columbus",     "lat": 32.461, "lon": -84.988},
    {"name": "Augusta",      "lat": 33.471, "lon": -81.975},
    {"name": "Savannah",     "lat": 32.081, "lon": -81.091},
    {"name": "Valdosta",     "lat": 30.833, "lon": -83.278},
    {"name": "Tallahassee",  "lat": 30.438, "lon": -84.281},
    {"name": "Columbia",     "lat": 34.001, "lon": -81.035},
    {"name": "Greenville",   "lat": 34.853, "lon": -82.394},
    {"name": "Asheville",    "lat": 35.595, "lon": -82.551},
    {"name": "Chattanooga",  "lat": 35.046, "lon": -85.310},
    {"name": "Nashville",    "lat": 36.163, "lon": -86.781},
    {"name": "Huntsville",   "lat": 34.730, "lon": -86.586},
    {"name": "Birmingham",   "lat": 33.521, "lon": -86.809},
]


def _cities(config: Any) -> list[dict[str, Any]]:
    cfg = config.get("weather_map", "temps", "cities", default=None)
    if isinstance(cfg, list) and cfg:
        out: list[dict[str, Any]] = []
        for c in cfg:
            if isinstance(c, dict) and c.get("lat") is not None and c.get("lon") is not None:
                out.append({
                    "name": str(c.get("name", "")),
                    "lat": float(c["lat"]),
                    "lon": float(c["lon"]),
                })
        if out:
            return out
    return _DEFAULT_CITIES


def _int_or_none(v: Any) -> Optional[int]:
    if v is None:
        return None
    try:
        return int(round(float(v)))
    except (TypeError, ValueError):
        return None


def fetch(client: Any, config: Any) -> dict[str, Any]:
    """Fetch current temperatures for the city list as GeoJSON. Keyless."""
    result: dict[str, Any] = {"type": "FeatureCollection", "features": [], "_ok": False}

    cities = _cities(config)
    if not cities:
        return result

    params = {
        "latitude": ",".join(str(c["lat"]) for c in cities),
        "longitude": ",".join(str(c["lon"]) for c in cities),
        "current": "temperature_2m",
        "temperature_unit": "fahrenheit",
    }

    try:
        r = client.get(_BASE_URL, params=params, timeout=15)
        r.raise_for_status()
        payload = r.json()
    except Exception as exc:
        log.warning("Open-Meteo city-temps fetch failed: %s", exc)
        return result

    # A multi-coordinate request returns a list; a single coordinate returns a dict.
    items = payload if isinstance(payload, list) else [payload]

    features: list[dict[str, Any]] = []
    for i, city in enumerate(cities):
        if i >= len(items):
            break
        try:
            temp_f = _int_or_none((items[i].get("current") or {}).get("temperature_2m"))
            if temp_f is None:
                continue
            features.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [city["lon"], city["lat"]]},
                "properties": {"name": city["name"], "temp_f": temp_f},
            })
        except Exception:
            continue

    result["features"] = features
    result["_ok"] = bool(features)
    return result
