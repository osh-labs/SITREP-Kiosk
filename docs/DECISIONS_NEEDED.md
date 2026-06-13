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

### Backend
- [ ] **SPC parser is unverified against the live feed.** Implemented against
  `https://www.spc.noaa.gov/products/outlook/day{1,2,3}otlk_cat.nolyr.geojson`
  with a point-in-polygon test. These URLs exist but weren't confirmable as
  stable at build time. If the structure differs, only `backend/sitrep/sources/spc.py`
  needs updating; it fails closed (`_ok=False`) so other sources are unaffected.
- [ ] **Heat threshold nuance.** Config `hazard_thresholds.heat_index_f.danger`
  is `103` — the NWS heat-index *work band* (firm). NWS issues a *Heat Advisory*
  around a heat index of ~105°F (the "verify against FFC" value). These are two
  different things and the code keys on both (work band + active alert name), so
  no code change is needed; just confirm the FFC numbers when you have them.
- [ ] **AirNow search radius** is hardcoded to 25 miles in `airnow.py`. Reasonable
  default; can be made config-driven if you want.

### Frontend
- [ ] **No visual/browser verification was possible** (no headless browser in the
  build environment). Logic was verified via 40+ Node assertions across all three
  scenarios, and I booted the real backend and confirmed it serves `index.html`,
  `app.js`, and `styles.css` (HTTP 200) alongside `/api/state`. Layout/legibility
  on the actual 1080p TV should be eyeballed during the M4 pilot.
- [ ] **AQI color categories** — the AQI callout currently uses one amber style;
  full EPA green→maroon category coloring would be more precise (minor enhancement).
- [ ] **Branding/palette/font** — neutral high-contrast dark theme, system fonts,
  no logo (see §4 above). Brand colors live in `:root` CSS variables; a logo would
  go in `frontend/assets/` with a small header edit. No web fonts (kiosk may be offline).

### Deploy
- [ ] **Kiosk username** (default `kiosk`) and **install directory** (default
  `/opt/sitrep`) — overridable via `install.sh --kiosk-user` / `--install-dir`.
- [ ] **Auto-login** must be enabled for the kiosk user on the display manager —
  a one-time manual step documented in `deploy/README.md` §2.5.
- [ ] **Distro** — install script/runbook target Debian/Ubuntu (`apt`); Fedora/RHEL
  need package-name swaps (logic is distro-neutral).
- Confirmed consistent across agents: backend entrypoint `python -m backend.sitrep`
  and health endpoint `/healthz` match what the systemd unit and kiosk launcher expect.

## Verified working (build pass, 2026-06-13)
- `pip install -r requirements.txt` clean; **69/69 backend tests pass**.
- Backend boots in demo mode and serves: `/healthz` → `{"ok":true}`,
  `/api/state` (all 10 contract keys, ranked hazards, morning/afternoon/degraded
  scenarios), and the frontend at `/` (`index.html` + `app.js` + `styles.css`, all 200).
- With **no API keys and no flags**, the backend auto-enables demo mode instead of
  crashing — the product is demonstrable today; plug keys into `.env` for live data.
