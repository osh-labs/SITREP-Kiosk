# Consolidated State Contract

This is the integration spine between the backend and the frontend. The backend
builds **one** consolidated state object on every poll cycle and serves it at
`GET /api/state`. The frontend polls that endpoint and renders slides from it.
Nothing else crosses the boundary.

> Authoritative numbers live in this object, sourced verbatim from feeds. The
> model only writes `briefing.bottom_line` and `briefing.watch_for`. Every other
> value binds to cached source data. (CLAUDE.md non-negotiables, PRD FR-12.)

## Endpoints

| Method | Path | Returns |
|--------|------|---------|
| GET | `/api/state` | the consolidated state JSON below |
| GET | `/healthz` | `{"ok": true}` liveness |
| GET | `/` | `frontend/index.html` |
| GET | `/assets/*`, `/app.js`, `/styles.css` | static frontend files |

The frontend re-fetches `/api/state` every `state.display.refresh_seconds`
(default 30) and re-renders. Carousel rotation is client-side using
`state.display.dwell_seconds`. The active slide set is chosen from
`state.display.mode`.

## Freshness / degraded state

Every data section carries a `source` block. When a source exceeds its staleness
limit the backend keeps serving the last-good values but sets `stale: true` and
fills `age_seconds`. The frontend renders the degraded layout (PRD §6.6) for any
section whose `source.stale` is true — last-good values, plainly labeled with age,
plus a "check current conditions" note. A failed/never-fetched source sets
`ok: false` and `value: null`-style empties; the slide still renders, degraded.

A `source` block:

```json
{
  "name": "NWS FFC",
  "ok": true,
  "stale": false,
  "fetched_at": "2026-06-13T06:35:00-04:00",
  "age_seconds": 300,
  "last_good_at": "2026-06-13T06:35:00-04:00"
}
```

## Consolidated state (full shape)

```json
{
  "generated_at": "2026-06-13T06:42:00-04:00",
  "display": {
    "mode": "morning",
    "dwell_seconds": 12,
    "refresh_seconds": 30
  },
  "location": { "name": "Atlanta Metro", "lat": 33.749, "lon": -84.388 },

  "briefing": {
    "bottom_line": "Heat is today's primary hazard. Index reaches the danger band by early afternoon; thunderstorms develop after 2 PM with a marginal lightning threat, and air quality is Code Orange. Recommend heavy work before noon, hourly hydration, and clearing elevated and exposed work once storms move in.",
    "watch_for": [
      "Heat index into the danger band after noon — heat-illness risk",
      "PM thunderstorms after 2 PM — lightning",
      "Air quality Code Orange — pace the sensitive crew"
    ],
    "source": "model",
    "generated_at": "2026-06-13T06:40:00-04:00",
    "sources": ["NWS FFC", "SPC"]
  },

  "hazards": {
    "ranked": [
      { "key": "heat_index", "rank": 1, "label": "Heat index to ~104°F after noon", "severity": "danger" },
      { "key": "thunderstorms", "rank": 2, "label": "PM thunderstorms after 2 PM", "severity": "watch" }
    ],
    "aqi_callout": { "aqi": 105, "category": "Unhealthy for Sensitive Groups", "label": "Code Orange" }
  },

  "weather": {
    "current": {
      "temp_f": 78, "feels_like_f": 82,
      "wind": { "dir": "SW", "speed_mph": 6, "gust_mph": null },
      "summary": "Partly cloudy"
    },
    "today": {
      "high_f": 96, "low_f": 75,
      "heat_index_f": 104,
      "pop_pct": 40, "pop_window": "after 2 PM",
      "daylight_until": "20:51",
      "summary": "PM storms",
      "sunrise": "2026-06-13T06:27", "sunset": "2026-06-13T20:51",
      "uv_index": 8.0, "visibility_mi": 9.0
    },
    "hourly": [
      { "time": "2026-06-13T07:00", "temp_f": 78.0, "feels_like_f": 82.0, "wind_mph": 6.0, "gust_mph": 13.0, "pop_pct": 10, "precip_in": 0.0 }
    ],
    "source": { "name": "NWS FFC", "ok": true, "stale": false, "fetched_at": "2026-06-13T06:35:00-04:00", "age_seconds": 300, "last_good_at": "2026-06-13T06:35:00-04:00" }
  },

  "commute": {
    "current": { "temp_f": 91, "feels_like_f": 99, "summary": "Storms ending ~6 PM" },
    "traffic": [
      { "text": "I-20 EB — heavy, about +18 min", "type": "congestion" },
      { "text": "GA-400 SB — incident @ Northridge", "type": "incident" }
    ],
    "source": { "name": "NWS, 511GA", "ok": true, "stale": false, "fetched_at": "2026-06-13T15:19:00-04:00", "age_seconds": 60, "last_good_at": "2026-06-13T15:19:00-04:00" }
  },

  "disruptions": {
    "traffic": [
      { "text": "I-285 WB @ Ashford-Dunwoody — crash, 2 lanes blocked", "type": "crash" },
      { "text": "I-75 NB @ MM 251 — construction, delays", "type": "construction" }
    ],
    "alerts": [
      { "text": "Heat Advisory — metro-wide, until 8 PM", "event": "Heat Advisory", "severity": "advisory" }
    ],
    "source": { "name": "511GA, NWS", "ok": true, "stale": false, "fetched_at": "2026-06-13T06:41:00-04:00", "age_seconds": 60, "last_good_at": "2026-06-13T06:41:00-04:00" }
  },

  "forecast_3day": {
    "days": [
      { "name": "SAT 14", "high_f": 97, "low_f": 75, "summary": "Storms 50%", "icon": "storm" },
      { "name": "SUN 15", "high_f": 94, "low_f": 73, "summary": "Storms 30%", "icon": "storm" },
      { "name": "MON 16", "high_f": 90, "low_f": 71, "summary": "Clear", "icon": "clear" }
    ],
    "spc_outlook": { "text": "Slight risk Sat (metro edge)", "category": "slight", "day": 1 },
    "source": { "name": "NWS FFC, SPC", "ok": true, "stale": false, "fetched_at": "2026-06-13T06:40:00-04:00", "age_seconds": 120, "last_good_at": "2026-06-13T06:40:00-04:00" }
  },

  "astro": { "moon_phase": "Waxing Gibbous", "illumination_pct": 82, "phase_fraction": 0.38 },

  "weather_map": {
    "enabled": true,
    "center": { "lat": 33.749, "lon": -84.388 },
    "default_zoom": 8, "min_zoom": 6, "max_zoom": 10,
    "base_style": "dark",
    "layers": { "radar": { "default_on": true, "opacity": 0.7 }, "alerts": { "default_on": true } },
    "animation": { "enabled": true, "frames": 8, "interval_ms": 600, "refresh_seconds": 300 },
    "source": { "name": "Weather Map", "ok": true, "stale": false, "fetched_at": "2026-06-13T06:35:00-04:00", "age_seconds": 300, "last_good_at": "2026-06-13T06:35:00-04:00" }
  },

  "sources": {
    "nws":         { "name": "NWS FFC",    "ok": true, "stale": false, "fetched_at": "2026-06-13T06:35:00-04:00", "age_seconds": 300, "last_good_at": "2026-06-13T06:35:00-04:00" },
    "spc":         { "name": "SPC",        "ok": true, "stale": false, "fetched_at": "2026-06-13T06:40:00-04:00", "age_seconds": 120, "last_good_at": "2026-06-13T06:40:00-04:00" },
    "ga511":       { "name": "511GA",      "ok": true, "stale": false, "fetched_at": "2026-06-13T06:41:00-04:00", "age_seconds": 60,  "last_good_at": "2026-06-13T06:41:00-04:00" },
    "airnow":      { "name": "AirNow",     "ok": true, "stale": false, "fetched_at": "2026-06-13T06:00:00-04:00", "age_seconds": 2520, "last_good_at": "2026-06-13T06:00:00-04:00" },
    "openmeteo":   { "name": "Open-Meteo", "ok": true, "stale": false, "fetched_at": "2026-06-13T06:35:00-04:00", "age_seconds": 300, "last_good_at": "2026-06-13T06:35:00-04:00" },
    "weather_map": { "name": "Weather Map","ok": true, "stale": false, "fetched_at": "2026-06-13T06:35:00-04:00", "age_seconds": 300, "last_good_at": "2026-06-13T06:35:00-04:00" }
  }
}
```

## Source bindings (which feed owns which field)

| Field(s) | Source | Authoritative |
|----------|--------|---------------|
| `weather.current.*`, `weather.today.high_f/low_f/heat_index_f/pop_pct/pop_window/summary`, `disruptions.alerts` | **NWS FFC** | yes |
| `weather.hourly[]`, `weather.today.sunrise/sunset/uv_index/visibility_mi` | **Open-Meteo** (`sources.openmeteo`) | supplementary |
| `disruptions.traffic`, `commute.traffic` | **511GA** | yes |
| `hazards.aqi_callout` | **AirNow** | yes |
| `forecast_3day.spc_outlook` | **SPC** | yes |
| `astro.*` | **computed** (deterministic, no feed) | n/a — exact |
| `weather_map.*` (config) + alert polygons via `GET /api/alerts.geojson` | config + **NWS** (`sources.weather_map`) | alert shapes authoritative |

> The single dashboard ignores `display.dwell_seconds` (a carousel relic). Map base
> + radar tiles load directly in the browser from CARTO/IEM — a documented
> exception to "loopback-only at render time" for non-authoritative imagery; the
> authoritative warning shapes still come from the loopback `/api/alerts.geojson`.

## Field notes

- **Severity vocab** (for `hazards.ranked[].severity` and alert chips):
  `info`, `watch`, `advisory`, `caution`, `danger`, `extreme`. The frontend maps
  these to a high-contrast style and an icon/shape — **never color alone**
  (PRD NFR-7).
- **`hazards.ranked`** is the D5 priority order, highest first; it decides what
  the briefing leads with. `aqi_callout` is separate (may be `null`).
- **`display.mode`** is `"morning"` or `"afternoon"`, computed by the backend
  from config mode windows. Morning slide set: Briefing, Weather, Disruptions,
  3-Day. Afternoon set: Weather, PM Commute (`commute`), 3-Day.
- Numbers may be `null` when a source has never succeeded; the frontend shows an
  em-dash / "—" rather than a fabricated value.
- All timestamps are ISO-8601 with the local offset.

Sample objects matching this contract live in
`backend/sitrep/fixtures/`: `sample_state_morning.json`,
`sample_state_afternoon.json`, `sample_state_degraded.json`. The frontend
develops against these; the backend emits them verbatim in **demo mode** (no API
keys required) so the whole product is demonstrable before keys are plugged in.
