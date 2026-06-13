# Decisions Needed / Open Questions — for Chris's review

This captures everything the build deferred for your input so you didn't have to
be in the loop during the one-shot. Nothing here blocks running the product in
**demo mode** (no keys). Items are grouped; check the box once resolved.

_Last updated by the build pass on 2026-06-13. The "Agent-reported" section is
appended from the sub-agents' findings._

## 1. Credentials (required for LIVE data; demo mode runs without them)
- [ ] **511GA developer key** — register at 511ga.org, put in `.env` as `GA511_API_KEY`. Rate limit 10 calls/60s (we poll ~90s).
- [ ] **EPA AirNow API key** — register at airnowapi.org, `.env` `AIRNOW_API_KEY`. 500 req/hr.
- [ ] **Anthropic API key** — `.env` `ANTHROPIC_API_KEY` for the BLUF. Without it the board uses the templated fallback briefing (still fully functional).
- [ ] **NWS User-Agent** — set a real contact in `NWS_USER_AGENT` (NWS asks for an identifying contact; no key needed).

## 2. Source/data confirmations (flagged in CLAUDE.md / PRD as "verify at build")
- [ ] **SPC feed format** — PRD §7.5 marks the exact SPC convective-outlook endpoint/format as "to confirm at build." See the backend agent's report for how the SPC parser was implemented (live vs. stub) and what needs confirming.
- [ ] **WFO FFC alert criteria (Verify tier, PRD §12)** — Heat Advisory / Extreme Heat Warning thresholds and the cold-weather (Cold Weather Advisory / Extreme Cold Warning) criteria vary by office. Current config uses the documented Southeast defaults; confirm exact FFC values and adjust `config/config.yaml`.
- [ ] **Default thresholds set "to taste" (PRD §12 Default tier)** — thunderstorm probability (30%), rain PoP (50%) / QPF (0.25 in), and wind-gust flag (30 mph) are operational defaults in `config.example.yaml`. Confirm against United's risk tolerance.

## 3. Operational / deployment (non-blocking for code; needed before M4 pilot)
- [ ] **Mini PC** — spec and purchaser (PRD O2). Any modest x86 mini PC running Debian/Ubuntu is fine.
- [ ] **Kiosk Linux user + install directory** — the deploy scripts use placeholders; pick the kiosk username and install path. See deploy agent's report.
- [ ] **Named maintainer + fallback** (PRD O3) — recommended before go-live so a silent break gets caught.
- [ ] **Go-live date** (PRD O4).
- [ ] **Location** — currently generic Atlanta metro single point (lat 33.749, lon -84.388) per A1/O1. Site/route geofencing is explicitly v2; confirm the single point is right, or give preferred coordinates.

## 4. Presentation choices (defaults chosen; change if you have preferences)
- [ ] **Branding** — no United Consulting logo/colors were supplied; the frontend uses a neutral high-contrast palette. Provide a logo + brand colors if you want them.
- [ ] **Mode switch time** — defaults to morning until 12:00, afternoon after (config `display.mode_windows`). Adjust to your muster schedule.
- [ ] **Dwell time** — 12s per slide (config `display.dwell_seconds`).

## Agent-reported items
<!-- Filled in after the sub-agents complete. -->
