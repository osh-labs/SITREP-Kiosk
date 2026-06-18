"""
NWS api.weather.gov poller.

Fetches:
 - /points/{lat},{lon}  -> forecastUrl, forecastHourlyUrl, observationsUrl (nearest station)
 - forecastUrl          -> 7-day periods (today high/low, PoP, summary)
 - forecastHourlyUrl    -> hourly periods (heat index proxy, precip probability)
 - /alerts/active       -> active NWS alerts for the zone
 - observationsUrl      -> current conditions from nearest station

Returns a normalized dict consumed by state_builder.py.
Auth: User-Agent header only (NWS_USER_AGENT env var).
Timeout: 10 s per request; any failure returns partial/empty data.
"""
from __future__ import annotations

import logging
import math
import os
from typing import Any, Optional

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level cache of the NWS metadata URLs (avoid /points on every poll)
# ---------------------------------------------------------------------------
_nws_meta: dict[str, str] = {}


def _headers() -> dict[str, str]:
    ua = os.environ.get("NWS_USER_AGENT", "SITREP-Kiosk/1.0 (contact: admin@example.com)")
    return {"User-Agent": ua, "Accept": "application/geo+json"}


def _wind_dir(degrees: Optional[float]) -> Optional[str]:
    """Convert wind bearing to cardinal/intercardinal string."""
    if degrees is None:
        return None
    dirs = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
            "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    ix = round(degrees / 22.5) % 16
    return dirs[ix]


def _c_to_f(c: Optional[float]) -> Optional[float]:
    if c is None:
        return None
    return round(c * 9 / 5 + 32, 1)


def _ms_to_mph(ms: Optional[float]) -> Optional[float]:
    if ms is None:
        return None
    return round(ms * 2.23694, 1)


def _km_to_mph(km: Optional[float]) -> Optional[float]:
    if km is None:
        return None
    return round(km * 0.621371, 1)


def _heat_index_f(temp_f: float, rh: float) -> float:
    """Steadman (NWS simplified) heat index formula."""
    if temp_f < 80:
        return temp_f
    hi = (-42.379
          + 2.04901523 * temp_f
          + 10.14333127 * rh
          - 0.22475541 * temp_f * rh
          - 0.00683783 * temp_f ** 2
          - 0.05481717 * rh ** 2
          + 0.00122874 * temp_f ** 2 * rh
          + 0.00085282 * temp_f * rh ** 2
          - 0.00000199 * temp_f ** 2 * rh ** 2)
    return round(hi, 1)


def _feels_like(temp_f: Optional[float], rh: Optional[float], wind_mph: Optional[float]) -> Optional[float]:
    """Apparent temperature: heat index when hot, wind chill when cold."""
    if temp_f is None:
        return None
    if temp_f >= 80 and rh is not None:
        return _heat_index_f(temp_f, rh)
    if temp_f <= 50 and wind_mph is not None and wind_mph > 3:
        wc = (35.74 + 0.6215 * temp_f
              - 35.75 * (wind_mph ** 0.16)
              + 0.4275 * temp_f * (wind_mph ** 0.16))
        return round(wc, 1)
    return temp_f


def _icon_from_summary(summary: str) -> str:
    s = summary.lower()
    if any(k in s for k in ("snow", "flurr", "blizzard", "winter")):
        return "snow"
    if any(k in s for k in ("sleet", "freezing", "ice", "wintry mix")):
        return "sleet"
    if any(k in s for k in ("thunder", "storm", "t-storm")):
        return "storm"
    if "rain" in s or "shower" in s or "drizzle" in s:
        return "rain"
    if any(k in s for k in ("cloud", "overcast", "fog", "mist")):
        return "cloud"
    return "clear"


def _alert_severity(event: str) -> str:
    """Map NWS event name to severity vocab."""
    ev = event.lower()
    if any(k in ev for k in ("tornado warning", "flash flood warning", "severe thunderstorm warning",
                              "ice storm warning", "extreme cold warning")):
        return "extreme"
    if any(k in ev for k in ("warning",)):
        return "danger"
    if any(k in ev for k in ("watch",)):
        return "watch"
    if any(k in ev for k in ("advisory",)):
        return "advisory"
    return "info"


# ---------------------------------------------------------------------------
# Alert polygon resolution
# ---------------------------------------------------------------------------
# Most NWS alerts carry no inline geometry — they reference forecast/county zones
# by URL (properties.affectedZones). Each zone's individual endpoint returns its
# polygon (the batch /zones collection omits geometry), so we fetch each zone URL
# once and cache it for the process lifetime. Without this, zone-based alerts
# (often half of all active alerts) never draw on the map.
_zone_geom_cache: dict[str, Optional[dict]] = {}

# Max NEW individual zone fetches per poll, to stay polite with NWS. Cached zones
# are free; uncached overflow fills in over subsequent polls. Severity ordering
# (below) means the most urgent alerts' zones resolve first.
_ZONE_LOOKUP_CAP = 75

_SEV_RANK = {"extreme": 0, "danger": 1, "watch": 2, "advisory": 3, "info": 4}


def _resolve_zone_geometries(client: Any, zone_urls: list[str], cap: int = _ZONE_LOOKUP_CAP) -> None:
    """Fetch + cache geometry for any zone URLs not already cached, up to `cap`
    new network fetches. Cached entries (including None) are never re-fetched."""
    fetched = 0
    for url in dict.fromkeys(zone_urls):
        if url in _zone_geom_cache:
            continue
        if fetched >= cap:
            break
        fetched += 1
        try:
            r = client.get(url, headers=_headers(), timeout=10)
            r.raise_for_status()
            _zone_geom_cache[url] = r.json().get("geometry")
        except Exception as exc:
            log.debug("NWS zone geometry fetch failed (%s): %s", url, exc)
            _zone_geom_cache[url] = None


def _build_alerts_geojson(client: Any, features: list[dict]) -> dict[str, Any]:
    """Turn raw NWS alert features into a FeatureCollection with real geometry,
    resolving zone shapes for alerts that lack an inline polygon."""
    # Most-severe alerts first so their zones resolve within the per-poll cap.
    feats_sorted = sorted(
        features,
        key=lambda f: _SEV_RANK.get(_alert_severity((f.get("properties") or {}).get("event", "")), 9),
    )

    pending_zones: list[str] = []
    for f in feats_sorted:
        if f.get("geometry"):
            continue
        pending_zones.extend((f.get("properties") or {}).get("affectedZones", []) or [])
    if pending_zones:
        _resolve_zone_geometries(client, pending_zones)

    out: list[dict] = []
    for f in feats_sorted:
        props = f.get("properties", {}) or {}
        event = props.get("event", "")
        base_props = {
            "event": event,
            "severity": _alert_severity(event),
            "headline": props.get("headline", ""),
            "areaDesc": props.get("areaDesc", ""),
        }
        geom = f.get("geometry")
        if geom:
            out.append({"type": "Feature", "properties": base_props, "geometry": geom})
            continue
        # No inline geometry — emit one feature per resolved affected zone.
        for z in props.get("affectedZones", []) or []:
            zg = _zone_geom_cache.get(z)
            if zg:
                out.append({"type": "Feature", "properties": base_props, "geometry": zg})
    return {"type": "FeatureCollection", "features": out}


def _alerts_area(config: Any) -> str:
    """Comma-joined state codes the map alert overlay should cover."""
    area = config.get("weather_map", "alerts", "area", default=None)
    if isinstance(area, (list, tuple)) and area:
        return ",".join(str(a).strip().upper() for a in area if str(a).strip())
    return "GA,TN,AL,FL,SC,NC,KY"


def _get_nws_meta(client: Any, lat: float, lon: float) -> dict[str, str]:
    """Fetch /points and cache the URLs. Returns {} on failure."""
    global _nws_meta
    if _nws_meta:
        return _nws_meta

    url = f"https://api.weather.gov/points/{lat:.4f},{lon:.4f}"
    try:
        r = client.get(url, headers=_headers(), timeout=10)
        r.raise_for_status()
        props = r.json().get("properties", {})
        _nws_meta = {
            "forecast": props.get("forecast", ""),
            "forecastHourly": props.get("forecastHourly", ""),
            "forecastGridData": props.get("forecastGridData", ""),
            "cwa": props.get("cwa", ""),
            "gridId": props.get("gridId", ""),
            "gridX": str(props.get("gridX", "")),
            "gridY": str(props.get("gridY", "")),
            "radarStation": props.get("radarStation", ""),
            "observationStations": props.get("observationStations", ""),
        }
        return _nws_meta
    except Exception as exc:
        log.warning("NWS /points failed: %s", exc)
        return {}


def fetch(client: Any, config: Any) -> dict[str, Any]:
    """
    Main entry point.  Returns a normalized dict with keys:
      weather_current, weather_today, forecast_days, alerts, raw_hourly
    On any sub-failure the corresponding key is empty/None; the caller
    (state_builder) fills in nulls from these.
    """
    lat = config.lat
    lon = config.lon
    result: dict[str, Any] = {
        "weather_current": None,
        "weather_today": None,
        "forecast_days": [],
        "alerts": [],
        "alerts_geojson": {"type": "FeatureCollection", "features": []},
        "raw_hourly": [],
        "_ok": False,
    }

    meta = _get_nws_meta(client, lat, lon)
    if not meta:
        return result

    # ── Current observations ────────────────────────────────────────────────
    try:
        obs_stations_url = meta.get("observationStations", "")
        if obs_stations_url:
            r = client.get(obs_stations_url, headers=_headers(), timeout=10)
            r.raise_for_status()
            stations = r.json().get("observationStations", [])
            if stations:
                obs_url = stations[0] + "/observations/latest"
                r2 = client.get(obs_url, headers=_headers(), timeout=10)
                r2.raise_for_status()
                op = r2.json().get("properties", {})
                temp_c = op.get("temperature", {}).get("value")
                rh = op.get("relativeHumidity", {}).get("value")
                wind_dir_deg = op.get("windDirection", {}).get("value")
                wind_spd_ms = op.get("windSpeed", {}).get("value")
                wind_gst_ms = op.get("windGust", {}).get("value")
                desc = op.get("textDescription", "")

                temp_f = _c_to_f(temp_c)
                wind_mph = _ms_to_mph(wind_spd_ms)
                gust_mph = _ms_to_mph(wind_gst_ms)
                feels_f = _feels_like(temp_f, rh, wind_mph)

                result["weather_current"] = {
                    "temp_f": temp_f,
                    "feels_like_f": feels_f,
                    "wind": {
                        "dir": _wind_dir(wind_dir_deg),
                        "speed_mph": wind_mph,
                        "gust_mph": gust_mph,
                    },
                    "summary": desc or None,
                }
    except Exception as exc:
        log.warning("NWS observations failed: %s", exc)

    # ── 7-day forecast ──────────────────────────────────────────────────────
    try:
        forecast_url = meta.get("forecast", "")
        if forecast_url:
            r = client.get(forecast_url, headers=_headers(), timeout=10)
            r.raise_for_status()
            periods = r.json().get("properties", {}).get("periods", [])

            today_day = next((p for p in periods if p.get("isDaytime") and p.get("number", 0) <= 2), None)
            today_night = next((p for p in periods if not p.get("isDaytime") and p.get("number", 0) <= 3), None)

            if today_day or today_night:
                high_f = today_day["temperature"] if today_day and today_day.get("temperatureUnit") == "F" else None
                low_f = today_night["temperature"] if today_night and today_night.get("temperatureUnit") == "F" else None
                pop_val = None
                pop_win = None
                if today_day:
                    dp = today_day.get("probabilityOfPrecipitation", {})
                    if dp and dp.get("value") is not None:
                        pop_val = dp["value"]
                summary = today_day.get("shortForecast", "") if today_day else ""
                detail = today_day.get("detailedForecast", "") if today_day else ""
                # Try to extract precip window from detailed forecast
                if "after" in detail.lower():
                    for phrase in detail.split("."):
                        if "after" in phrase.lower() and any(k in phrase.lower() for k in ("storm", "rain", "shower")):
                            pop_win = phrase.strip()
                            break

                result["weather_today"] = {
                    "high_f": high_f,
                    "low_f": low_f,
                    "heat_index_f": None,  # computed from hourly below
                    "pop_pct": pop_val,
                    "pop_window": pop_win,
                    "daylight_until": None,
                    "summary": summary or None,
                }

            # Future days (skip today = periods 1-2, take next 3 days)
            future_days: list[dict] = []
            seen_names: set = set()
            for p in periods:
                if p.get("number", 0) <= 2:
                    continue
                if not p.get("isDaytime"):
                    continue
                name = p.get("name", "")
                if name in seen_names:
                    continue
                seen_names.add(name)
                high_f = p["temperature"] if p.get("temperatureUnit") == "F" else None
                # find matching night
                night = next((np for np in periods
                               if not np.get("isDaytime") and np.get("number", 0) == p.get("number", 0) + 1),
                              None)
                low_f = night["temperature"] if night and night.get("temperatureUnit") == "F" else None
                dp = p.get("probabilityOfPrecipitation", {})
                pop_pct = dp.get("value") if dp else None
                short = p.get("shortForecast", "")
                icon = _icon_from_summary(short)
                # Format name as "MON 16" style
                import datetime as dt
                try:
                    start_time = p.get("startTime", "")
                    d = dt.datetime.fromisoformat(start_time)
                    day_label = d.strftime("%a %-d").upper()
                except Exception:
                    day_label = name.upper()[:6]

                summary_str = short
                if pop_pct is not None:
                    if "storm" in short.lower() or "rain" in short.lower() or "shower" in short.lower():
                        summary_str = f"{short} {int(pop_pct)}%"

                future_days.append({
                    "name": day_label,
                    "high_f": high_f,
                    "low_f": low_f,
                    "summary": summary_str,
                    "icon": icon,
                })
                if len(future_days) >= 3:
                    break
            result["forecast_days"] = future_days
    except Exception as exc:
        log.warning("NWS forecast failed: %s", exc)

    # ── Hourly forecast (for heat index + PoP) ────────────────────────────────
    try:
        hourly_url = meta.get("forecastHourly", "")
        if hourly_url:
            r = client.get(hourly_url, headers=_headers(), timeout=10)
            r.raise_for_status()
            hourly_periods = r.json().get("properties", {}).get("periods", [])[:24]
            result["raw_hourly"] = hourly_periods

            # Find peak heat index today
            max_hi = None
            for hp in hourly_periods[:18]:  # first 18 hours
                t_f = hp.get("temperature") if hp.get("temperatureUnit") == "F" else None
                rh = hp.get("relativeHumidity", {}).get("value")
                if t_f is not None and rh is not None and t_f >= 80:
                    hi = _heat_index_f(t_f, rh)
                    if max_hi is None or hi > max_hi:
                        max_hi = hi
            if max_hi and result["weather_today"]:
                result["weather_today"]["heat_index_f"] = max_hi
    except Exception as exc:
        log.warning("NWS hourly failed: %s", exc)

    # ── Active alerts (point — drives hazards/briefing for our location) ───────
    try:
        alerts_url = f"https://api.weather.gov/alerts/active?point={lat},{lon}"
        r = client.get(alerts_url, headers=_headers(), timeout=10)
        r.raise_for_status()
        features = r.json().get("features", [])
        alerts = []
        for f in features:
            props = f.get("properties", {})
            event = props.get("event", "")
            headline = props.get("headline", "")
            ends = props.get("ends", props.get("expires", ""))
            severity = _alert_severity(event)
            # Build short text
            text = event
            if headline:
                text = headline
            elif ends:
                try:
                    import datetime as dt
                    end_dt = dt.datetime.fromisoformat(ends.replace("Z", "+00:00"))
                    text = f"{event} — until {end_dt.strftime('%-I %p').lstrip('0')}"
                except Exception:
                    text = event
            alerts.append({
                "text": text,
                "event": event,
                "severity": severity,
            })
        result["alerts"] = alerts
    except Exception as exc:
        log.warning("NWS alerts failed: %s", exc)

    # ── Alert polygons for the map (regional — covers the whole visible map) ───
    # NWS alerts are mostly zone-based with null geometry; _build_alerts_geojson
    # resolves the zone shapes so they actually draw. Querying by area (states)
    # rather than a single point means the regional map shows every active alert
    # in view, not just ones covering our point.
    try:
        area_url = f"https://api.weather.gov/alerts/active?area={_alerts_area(config)}"
        r = client.get(area_url, headers=_headers(), timeout=15)
        r.raise_for_status()
        area_features = r.json().get("features", [])
        result["alerts_geojson"] = _build_alerts_geojson(client, area_features)
        log.info("NWS alert polygons: %d shapes from %d alerts",
                 len(result["alerts_geojson"]["features"]), len(area_features))
    except Exception as exc:
        log.warning("NWS regional alert polygons failed: %s", exc)

    result["_ok"] = True
    return result
