# Field SITREP Board

A hazard-forward situational awareness board for the United Consulting safety-area
TV. Mornings: hazard briefing, weather, disruptions, 3-day look-ahead. Afternoons:
current conditions, PM commute, look-ahead. General-information tool, not a record.

Runs on a single self-contained mini PC: a Python backend (data ingestion +
localhost endpoint) and a static frontend in a Chromium kiosk.

## Start here

- `CLAUDE.md` — orientation for the build agents (read first).
- `docs/PRD.md` — the requirements and source of truth (v0.5, build-ready).
- `config/config.example.yaml` — settings and hazard trigger values.
- `.env.example` — required API keys and environment variables.

## Build order

M0 ingestion + cache, M1 static render (no LLM), M2 briefing, M3 kiosk
hardening, M4 pilot. See PRD Section 9.

## Data sources

NWS (api.weather.gov), SPC, 511GA, EPA AirNow, Anthropic API. Auth and rate
limits are in CLAUDE.md and PRD Section 7-8.

## Status

Requirements approved. First build pass complete (M0–M3): Python backend
(ingestion, deterministic hazard ranking, Anthropic briefing + templated
fallback, localhost API), static carousel frontend, and kiosk/deploy layer.
Runs end-to-end today in **demo mode** with no API keys (`SITREP_DEMO=1`, or
automatic when no keys are present). Plug keys into `.env` for live data.

Quick start:
```
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
SITREP_DEMO=1 .venv/bin/python -m backend.sitrep   # http://localhost:8080
```

Outstanding items for review are in `docs/DECISIONS_NEEDED.md`. M4 (pilot on the
safety-area TV) remains, plus verifying the SPC feed and FFC thresholds against
live data — see that file.
