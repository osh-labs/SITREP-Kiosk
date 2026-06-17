# Field SITREP Board — Frontend

Single unified, dark-themed situational dashboard for the United Consulting Field
Situational Awareness board. Plain HTML/CSS/JS — no build step, no framework, no
Node runtime. The only library is **Leaflet**, vendored locally in
`vendor/leaflet/` (not a CDN, so the kiosk survives reboot offline).

## Viewing standalone (dev / demo)

The page reads a `?fixture=` query parameter to load a local JSON fixture instead
of hitting `/api/state`. This lets you view all three scenarios with no backend.

1. Start a local HTTP server from the `frontend/` directory:

   ```
   cd frontend
   python3 -m http.server 8080
   ```

2. Open one of these URLs in a browser:

   | URL | What it shows |
   |-----|---------------|
   | `http://localhost:8080/?fixture=morning`   | Morning mode — Disruptions & Alerts in the left column |
   | `http://localhost:8080/?fixture=afternoon` | Afternoon mode — PM Commute promoted in the left column |
   | `http://localhost:8080/?fixture=degraded`  | Degraded state — per-card banners + map staleness overlay |
   | `http://localhost:8080/`                   | Production path — hits `/api/state` (requires backend) |

   Note: in `?fixture=` mode the map's alert overlay (`/api/alerts.geojson`) and the
   external base/radar tiles need the backend / network; the rest of the dashboard
   renders fully from the fixture.

## Production (normal operation)

The Python backend (FastAPI) serves:
- `GET /` → `frontend/index.html`
- `GET /styles.css`, `GET /app.js`, `GET /vendor/*`, `GET /assets/*` → static files
- `GET /api/state` → the consolidated state JSON
- `GET /api/alerts.geojson` → active NWS alert polygons for the map overlay

The page auto-polls `/api/state` every `state.display.refresh_seconds` (default 30 s)
and re-renders the whole dashboard in place. There is no carousel; `dwell_seconds`
is ignored.

## Layout

```
Header:   UC logo + FIELD SITREP · location + mode + clock · OVERALL RISK + ZeroHarm
Left:     Briefing · Hazards · Disruptions&Alerts / PM Commute (by mode)
Center:   Interactive Leaflet map (CARTO dark base + animated IEM radar + NWS alerts)
Right:    Temperature & Heat Index chart · 3-Day Look Ahead
Strip:    Temp · Forecast (high + heat index / low) · Precip · Air Quality · UV · Sunrise · Sunset · All Systems Go
```

- **OVERALL RISK** is derived deterministically from `hazards.ranked[0].severity`
  (LOW → SEVERE) and shown as icon + label + color (never color alone).
- **Mode** (`display.mode`) only swaps the left-column activity card between
  Disruptions & Alerts (morning) and PM Commute (afternoon).
- Cards size to their content and the columns are top-aligned, so panels don't
  clip. **Key conditions live in the bottom strip** (no separate card).
- The **Temperature chart** plots air temp (solid) and heat index (dashed); it's
  hand-rolled inline SVG (no chart library). Wind and the numeric hourly table
  were dropped as low-value for the across-the-room glance.

## Files

| File | Purpose |
|------|---------|
| `index.html` | Full-screen 16:9 dashboard shell — regions filled by `app.js` |
| `styles.css` | Dark theme; severity conveyed by icon+label+color |
| `app.js` | Data fetching, dashboard rendering, Leaflet map — vanilla JS only |
| `vendor/leaflet/` | Vendored Leaflet 1.9.4 (`leaflet.js`, `leaflet.css`, marker images) |
| `assets/` | UC + ZeroHarm logos |
| `fixtures/` | Dev-only copies of `backend/sitrep/fixtures/` for `?fixture=` mode |

## Degraded state

Any section whose `source.stale == true` OR `source.ok == false` renders a warning
banner with the last-known time, human-readable age, and a note to verify current
conditions. The map shows a "Radar as of … — verify current conditions" overlay.
The bottom strip's "All Systems Go" flips to a list of down sources. Null values
show an em-dash, never a fabricated number.
