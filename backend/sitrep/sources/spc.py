"""
SPC (Storm Prediction Center) convective outlook poller.

TODO: The SPC public outlook feed format was not confirmable at build time.
      Two candidate endpoints exist:
        1. GeoJSON: https://www.spc.noaa.gov/products/outlook/day1otlk_cat.nolyr.geojson
           (and day2otlk_cat.nolyr.geojson, day3otlk_cat.nolyr.geojson)
        2. HTTPS HTML/text summary pages (not machine-readable)

This module implements against the public SPC GeoJSON endpoints.
If the endpoint is unreachable or the format changes, it returns a clean
failure dict so other sources are unaffected.

SPC categories (categorical):  TSTM, MRGL, SLGT, ENH, MDT, HIGH
These are mapped to: none, marginal, slight, enhanced, moderate, high

Rate limit: public, no key required. Poll at spc polling_seconds (default 1800).
"""
from __future__ import annotations

import logging
from typing import Any, Optional

log = logging.getLogger(__name__)

# SPC GeoJSON endpoints for Day 1-3 categorical outlooks
_SPC_URLS = {
    1: "https://www.spc.noaa.gov/products/outlook/day1otlk_cat.nolyr.geojson",
    2: "https://www.spc.noaa.gov/products/outlook/day2otlk_cat.nolyr.geojson",
    3: "https://www.spc.noaa.gov/products/outlook/day3otlk_cat.nolyr.geojson",
}

# SPC category string -> normalized label (ascending severity)
_SPC_CATEGORY_MAP = {
    "TSTM": "thunderstorm",
    "MRGL": "marginal",
    "SLGT": "slight",
    "ENH": "enhanced",
    "MDT": "moderate",
    "HIGH": "high",
}

# Minimum category to trigger a hazard flag (>=slight per PRD §12)
_HAZARD_THRESHOLD_CATEGORY = {"slight", "enhanced", "moderate", "high"}


def _point_in_polygon(lat: float, lon: float, coords: list) -> bool:
    """
    Ray-casting point-in-polygon test.
    coords is a list of [lon, lat] pairs (GeoJSON order).
    """
    x, y = lon, lat
    n = len(coords)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = coords[i][0], coords[i][1]
        xj, yj = coords[j][0], coords[j][1]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi):
            inside = not inside
        j = i
    return inside


def _point_in_geometry(lat: float, lon: float, geometry: dict) -> bool:
    """Check if lat/lon is inside a GeoJSON geometry (Polygon or MultiPolygon)."""
    if not geometry:
        return False
    gtype = geometry.get("type", "")
    coords = geometry.get("coordinates", [])
    if gtype == "Polygon":
        # coords[0] is the outer ring
        return bool(coords) and _point_in_polygon(lat, lon, coords[0])
    if gtype == "MultiPolygon":
        for polygon in coords:
            if polygon and _point_in_polygon(lat, lon, polygon[0]):
                return True
    return False


def _fetch_day_outlook(client: Any, day: int, lat: float, lon: float) -> Optional[dict]:
    """
    Fetch and parse the SPC categorical outlook for day N.
    Returns dict with category/label/in_risk_area or None on failure.
    """
    url = _SPC_URLS.get(day)
    if not url:
        return None

    try:
        r = client.get(url, timeout=15, headers={"Accept": "application/json"})
        r.raise_for_status()
        data = r.json()
    except Exception as exc:
        log.warning("SPC Day %d fetch failed: %s", day, exc)
        return None

    features = data.get("features", [])
    if not features:
        return {"category": "none", "label": "No severe weather risk", "in_risk_area": False}

    # Iterate features in reverse order — higher categories appear later in the file
    # or search for the highest category that contains our point
    best_category = None
    best_label = None

    category_order = ["HIGH", "MDT", "ENH", "SLGT", "MRGL", "TSTM"]

    for cat_code in category_order:
        for feature in features:
            props = feature.get("properties", {})
            # SPC GeoJSON uses LABEL or DN field for category
            label_val = props.get("LABEL", props.get("LABEL2", props.get("DN", "")))
            if not isinstance(label_val, str):
                label_val = str(label_val) if label_val else ""

            if label_val.upper() != cat_code:
                continue

            geometry = feature.get("geometry")
            if geometry and _point_in_geometry(lat, lon, geometry):
                best_category = cat_code
                best_label = _SPC_CATEGORY_MAP.get(cat_code, cat_code.lower())
                break

        if best_category:
            break

    if not best_category:
        return {"category": "none", "label": "No severe weather risk", "in_risk_area": False}

    normalized = _SPC_CATEGORY_MAP.get(best_category, best_category.lower())
    return {
        "category": normalized,
        "label": f"SPC Day {day}: {normalized.title()} risk",
        "in_risk_area": True,
        "raw_category": best_category,
    }


def fetch(client: Any, config: Any) -> dict[str, Any]:
    """
    Main entry point.
    Returns:
      {
        "day1": {category, label, in_risk_area} | None,
        "day2": {...} | None,
        "day3": {...} | None,
        "highest_day": int | None,
        "highest_category": str | None,
        "triggers_hazard": bool,
        "_ok": bool,
      }
    A single source failure returns _ok=False; partial results are preserved.
    """
    lat = config.lat
    lon = config.lon

    result: dict[str, Any] = {
        "day1": None,
        "day2": None,
        "day3": None,
        "highest_day": None,
        "highest_category": None,
        "triggers_hazard": False,
        "_ok": False,
    }

    any_ok = False
    category_rank = ["none", "thunderstorm", "marginal", "slight", "enhanced", "moderate", "high"]

    for day in (1, 2, 3):
        outlook = _fetch_day_outlook(client, day, lat, lon)
        if outlook is not None:
            result[f"day{day}"] = outlook
            any_ok = True
            cat = outlook.get("category", "none")
            if cat in category_rank:
                # Track the highest category across all days
                if (result["highest_category"] is None or
                        category_rank.index(cat) > category_rank.index(result["highest_category"])):
                    result["highest_category"] = cat
                    result["highest_day"] = day

    # Determine if a hazard flag should fire (Day 1 categorical >= slight, or any active warning)
    day1 = result.get("day1")
    if day1 and day1.get("category", "none") in _HAZARD_THRESHOLD_CATEGORY:
        result["triggers_hazard"] = True

    result["_ok"] = any_ok
    return result
