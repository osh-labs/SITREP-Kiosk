# Field SITREP Board — Frontend

Static carousel frontend for the United Consulting Field Situational Awareness Dashboard.
Plain HTML/CSS/JS — no build step, no framework, no Node runtime required.

## Viewing standalone (dev / demo)

The page reads a `?fixture=` query parameter to load a local JSON fixture instead of
hitting `/api/state`. This lets you view all three scenarios with no backend running.

1. Start a local HTTP server from the `frontend/` directory:

   ```
   cd frontend
   python3 -m http.server 8080
   ```

2. Open one of these URLs in a browser:

   | URL | What it shows |
   |-----|---------------|
   | `http://localhost:8080/?fixture=morning`   | Morning mode — Briefing, Weather, Disruptions, 3-Day |
   | `http://localhost:8080/?fixture=afternoon` | Afternoon mode — Weather, PM Commute, 3-Day |
   | `http://localhost:8080/?fixture=degraded`  | Degraded state — stale sources, last-known data banners |
   | `http://localhost:8080/`                   | Production path — hits `/api/state` (requires backend) |

   The fixture files live in `frontend/fixtures/` and are copies of the backend
   fixtures in `backend/sitrep/fixtures/`. They are for development only.

## Production (normal operation)

The Python backend (FastAPI/Flask) serves:
- `GET /` → `frontend/index.html`
- `GET /styles.css`, `GET /app.js`, `GET /assets/*` → static files
- `GET /api/state` → the consolidated state JSON

The page auto-polls `/api/state` every `state.display.refresh_seconds` (default 30 s)
and rotates slides every `state.display.dwell_seconds` (default 12 s).

No query parameter is needed in production; the `?fixture=` param is ignored by the
backend and only used by `app.js` for local dev.

## Files

| File | Purpose |
|------|---------|
| `index.html` | Full-screen 16:9 kiosk shell — HTML structure, no inline scripts or styles |
| `styles.css` | High-contrast, large-type styles; severity conveyed by icon+label+color |
| `app.js` | Data fetching, slide rendering, carousel rotation — vanilla JS only |
| `assets/` | Inline SVG icons (reserved; currently embedded in app.js) |
| `fixtures/` | Dev-only copies of `backend/sitrep/fixtures/` for `?fixture=` mode |

## Slide sets

**Morning** (`display.mode == "morning"`):
1. Morning Briefing — `briefing.bottom_line` + `briefing.watch_for` + hazard flags
2. Weather — current conditions + today's outlook
3. Disruptions & Alerts — `disruptions.traffic` + `disruptions.alerts`
4. 3-Day Look Ahead — `forecast_3day` + SPC outlook

**Afternoon** (`display.mode == "afternoon"`):
1. Weather — current conditions + near-term trend
2. PM Commute — `commute.current` + `commute.traffic`
3. 3-Day Look Ahead

## Degraded state

Any section whose `source.stale == true` OR `source.ok == false` renders a
warning banner with the last-known time, human-readable age, and a note to
verify current conditions. Null values show an em-dash, never a fabricated number.
