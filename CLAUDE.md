# CLAUDE.md — Field SITREP Board

Orientation for Claude Code agents building this project. Read this first, then
`docs/PRD.md`, which is the source of truth. If this file and the PRD ever
disagree, the PRD wins — flag the discrepancy.

## What this is

A hazard-forward situational awareness board for the TV in the United Consulting
safety area. Field staff glance at it before heading out. Mornings show a hazard
briefing, weather, disruptions, and a 3-day look-ahead; afternoons show current
conditions, the PM commute, and the look-ahead. It is a general-information tool,
not a system of record — no auth, no sign-off, no data retention.

It runs entirely on one self-contained mini PC: a Python backend that ingests
data and serves a localhost endpoint, and a static frontend in a Chromium kiosk
pointed at that endpoint.

## Mission

Build the application described in `docs/PRD.md`. Ship in the milestone order
below. M1 must run end-to-end on real data with NO language model involved
before M2 introduces the briefing. Do not collapse M0–M2 into one pass.

## Architecture (PRD §7)

Three parts, one box:
1. Backend ingestion + cache (Python) — polls each source on its own schedule,
   validates and normalizes, computes ranked hazard flags (D5 order), writes one
   consolidated state object with per-source timestamps to a local cache.
2. Intelligence step (Python -> Anthropic API) — on schedule or material change,
   sends the validated structured state to Claude and stores the returned
   briefing prose alongside the state. Numbers are never taken from model output.
3. Presentation (static frontend in Chromium kiosk) — reads the consolidated
   state from the localhost endpoint, renders slides, rotates the carousel.

## Recommended stack

Not mandatory, but stay close to it and keep dependencies minimal:
- Python 3.11+
- Web/serving: FastAPI (serves the localhost JSON endpoint and the static
  frontend) with uvicorn. Flask is an acceptable substitute.
- HTTP client: httpx (or requests).
- Scheduling: APScheduler, or a simple asyncio loop.
- LLM: the official `anthropic` Python SDK. Model string `claude-sonnet-4-6`.
- Frontend: plain HTML/CSS/JS, no build step, no framework required. Carousel in
  vanilla JS. Prioritize legibility at across-the-room distance (PRD NFR-7).
- Config: a single YAML file (see `config/config.example.yaml`).

No Node runtime. No frontend build pipeline. One process tree.

## Data sources (auth + limits — respect these)

| Source | Auth | Limit | Notes |
|--------|------|-------|-------|
| NWS api.weather.gov | User-Agent header only (no key) | be polite | GeoJSON. Use /points -> forecast, /alerts, observations. Metro office is FFC (Peachtree City). |
| SPC | none (public) | — | Day 1–3 convective outlooks, watches, mesoscale discussions. Confirm feed format at build. |
| 511GA | developer key | 10 calls / 60 s | events, alerts, cameras, message signs. Poll traffic at ~90 s to stay under the limit. |
| EPA AirNow | API key | 500 req/hr per service | current AQI by lat/long, hourly NowCast. Poll ~hourly. |
| Anthropic | API key | n/a | briefing generation only. |
| Open-Meteo | none (public) | be polite (~15 min) | **Supplementary, sanctioned addition.** Hourly series, sunrise/sunset, UV, visibility for the dashboard. NWS stays authoritative for observations/alerts — Open-Meteo never overrides NWS numbers. |
| Map tiles (CARTO base + IEM NEXRAD radar) | none (public) | be polite (one kiosk, ~5 min) | **Sanctioned addition.** Loaded directly by the browser for the interactive Leaflet map (documented exception to loopback-only, for non-authoritative imagery). Authoritative alert polygons come from the loopback `/api/alerts.geojson`. |

Secrets come from environment variables — see `.env.example`. Never hardcode
keys, never put them in the frontend, never commit `.env`.

## Hazard logic (PRD §12)

- Hazard flags are computed deterministically from source data, NOT by the model.
- Ranking order (highest first): severe weather, heat index, winter weather,
  thunderstorms, rain, wind. AQI is a separate callout, not in the ranked chain.
- Trigger values live in `config/config.example.yaml`. Some are firm standards,
  some are FFC criteria to verify, some are operational defaults — the config
  comments say which. Make all of them config-driven, not literals in code.
- The ranked flags decide what the briefing leads with.

## Briefing (BLUF) contract (PRD §7.3)

- Input to the model: the validated structured state (alerts, SPC category,
  threshold crossings, key forecast figures, AQI) plus the ranked flags.
- Voice: an analyst's brief. Open with the bottom line and primary hazard,
  summarize conditions, then recommended actions. Measured, assessment-driven.
  Not military, not corporate, not folksy. See the wireframe in PRD §6.1 — tune
  the prompt against it.
- Hard rule: the model writes prose only. It must not emit numeric values. Every
  figure shown on any slide binds to cached source data, not to model text.
- Fallback: if the model call fails or returns empty, render a templated
  briefing built from the hazard flags so the board never goes wordless.

## Non-negotiables

- Authoritative numbers render verbatim from source. No model-generated figures.
- Never present stale data as current. Each source has a freshness timestamp; past
  its staleness limit, show the degraded state (PRD §6.6) with the data's age.
- Localhost only. No inbound network service, no ports exposed beyond the loopback.
- Respect the 511GA and AirNow rate limits.
- A failed single source must not blank the board; other slides keep running.

## Milestones (PRD §9) — build in this order

- M0 — Ingestion + cache: pollers for NWS, SPC, 511GA, AirNow; validation;
  ranked hazard flags; consolidated state inspectable locally.
- M1 — Static render: carousel shell, all slides on real cached data, freshness
  footer, degraded state. NO LLM. This must stand on its own.
- M2 — Briefing: Anthropic integration, analyst-voice prompt, templated fallback.
- M3 — Kiosk hardening: auto-restart, Chromium kiosk config, mode switching,
  config loading/reload. Survives reboot and a simulated outage over 24 h.
- M4 — Pilot: deploy to the safety-area TV, observe, tune thresholds and dwell.

## Proposed repo layout

```
field-sitrep-board/
  CLAUDE.md              # this file
  README.md
  .env.example
  docs/PRD.md            # source of truth
  config/config.example.yaml
  backend/               # Python: pollers, cache, ranking, LLM, localhost API
  frontend/              # static carousel: index.html, styles, app.js
  deploy/                # systemd unit + chromium kiosk launch script
```

## Kiosk / deployment notes (M3)

- Run the backend as a systemd service that restarts on failure.
- Launch Chromium in kiosk mode (`--kiosk --noerrdialogs
  --disable-session-crashed-bubble --incognito http://localhost:PORT`) via an
  autostart entry; relaunch on exit.
- Disable display sleep / screen blanking on the mini PC.

## Definition of done (v1)

- Board runs unattended on the mini PC and survives reboot.
- All slides render from live data with visible freshness; degraded state proven
  by killing a source.
- Morning/afternoon modes switch on the configured times.
- BLUF generates in the analyst voice with the templated fallback verified; no
  model-generated numbers reach a slide.
- Rate limits respected; secrets only in env.

## Open items (non-blocking — assume the default, flag if you need a decision)

- Location: assume generic Atlanta metro (single point). Geofencing specific
  sites/routes is a possible v2; do not build it now.
- Mini PC spec/purchaser, named maintainer, and go-live date are operational and
  do not block code.
