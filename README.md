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

Requirements approved. Application code not yet written — that is the build
agents' job, following CLAUDE.md and the PRD.
