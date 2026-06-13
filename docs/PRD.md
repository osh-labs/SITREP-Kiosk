# Product Requirements Document — Field SITREP Board

Working title: United Consulting Field Situational Awareness Dashboard
Version: v0.5 (Build-ready)
Date: 13 June 2026
Prepared for: Chris Lee, United Consulting
Status: Approved for development. Scope decisions are locked; remaining open items are non-blocking.

Changes from v0.4: hazard trigger thresholds finalized and added as Section 12; EPA AirNow added as a data source for AQI (Section 7, Section 8); open items pruned to non-blocking. This is the build-ready baseline handed to Claude Code.

---

## 0. Decisions Locked

| # | Decision | Resolution |
|---|----------|------------|
| D1 | Authority model | General information / advisory. Not a record, no sign-off, no retention. |
| D2 | Disruption content | Structured sources only (511GA events, NWS alerts). No freeform news. |
| D3 | Deployment | Single self-contained mini PC running backend, frontend, and kiosk browser. Network access is not a constraint. |
| D4 | BLUF voice | Analyst's brief — measured and assessment-driven. Leads with the bottom line and primary hazard, summarizes conditions, then recommended actions. Not military, not corporate. |
| D5 | Weather hazard priority (descending) | Severe weather, heat index, winter weather, thunderstorms, rain, wind. AQI called out separately. |

---

## 1. Product Overview

### 1.1 Purpose
A hazard-forward information board on the existing TV in the United Consulting safety area. It gives field staff a quick, plain-language read on weather, hazards, and traffic before they head out in the morning, and shifts to a commute-and-forecast view in the afternoon. It is a general awareness tool that complements, rather than replaces, how the crew already plans their day.

### 1.2 Target users
- Primary: United Consulting field staff getting ready for the workday.
- Secondary: the owner/maintainer who configures it and keeps it running.

### 1.3 Core functionality
- A full-screen, auto-rotating carousel on a Chromium kiosk.
- Two time-of-day modes: a morning briefing and an afternoon commute/forecast view.
- A short, friendly AI-written bottom-line briefing (BLUF) built from live source data, with the actual numbers shown straight from the source.
- Continuous polling of authoritative feeds with a clear indicator when data is current vs. stale.

### 1.4 Non-goals (v1)
- No scheduling, dispatch, or job assignment.
- No user interaction or acknowledgement.
- No freeform news interpretation.
- No mobile or multi-site distribution.

---

## 2. User Requirements

### 2.1 Field staff (primary)
| Need | Description |
|------|-------------|
| Glanceable | Readable across the safety area in a few seconds, no interaction. |
| Current | Reflects conditions now; says so plainly when data is old. |
| Briefed | Reads like an analyst's briefing — measured and assessment-driven, leads with the bottom line. |
| Hazard-forward | The most important thing for the day leads, every time. |
| Field-relevant | Weather framed around working outside, not meteorology trivia. |

Pain points addressed: weather, hazards, and traffic are currently checked ad hoc on personal phones with no shared morning baseline.

### 2.2 Maintainer (secondary)
| Need | Description |
|------|-------------|
| Configurable | Dwell times, mode windows, thresholds, and location set without code changes. |
| Self-recovering | Survives reboots and brief API outages unattended. |
| Observable | Simple logs and source-health status. |

---

## 3. Functional Requirements

### 3.1 Display and rotation
- FR-1: Render full-screen slides in a fixed carousel; per-slide dwell configurable (default 12 s).
- FR-2: Switch between Morning Mode and Afternoon Mode on configurable time windows (default: Morning until 12:00).
- FR-3: Light footer on each slide showing source(s) and last-updated time.

### 3.2 Morning Mode slides
- FR-4: Morning Briefing (BLUF) — a short cordial prose lead plus a "watch for" bullet list.
- FR-5: Weather — field-relevant current conditions and today's outlook.
- FR-6: Disruptions and Alerts — current 511GA traffic events/construction and active NWS alerts.
- FR-7: 3-Day Look Ahead — next three days plus the relevant SPC convective outlook.

### 3.3 Afternoon Mode slides
- FR-8: Weather — current conditions and near-term trend.
- FR-9: PM Commute — current conditions plus 511GA traffic relevant to the evening drive.
- FR-10: 3-Day Look Ahead (shared with FR-7).

### 3.4 Data and intelligence
- FR-11: Poll each source on its own schedule (see NFR-1) and cache the last-good response with a timestamp.
- FR-12: Generate the BLUF from validated, already-fetched data. The model writes the prose; the actual numbers on every slide come straight from source data, not from model text. This is for accuracy, not formality — the board should never show a figure the model invented.
- FR-13: Regenerate the BLUF on a schedule and on material change (alert issued/cleared, threshold crossed), not on every carousel loop.
- FR-14: Determine active hazards deterministically from source data, ranked in the D5 priority order: severe weather, heat index, winter weather, thunderstorms, rain, wind; AQI surfaced as a separate callout. This ranking decides what the BLUF leads with. Trigger values are specified in Section 12.

### 3.5 Resilience and configuration
- FR-15: Per-source freshness check; flag any source whose last-good data exceeds a configurable staleness limit.
- FR-16: Degraded state — when a source is unreachable, show the last-good value plainly marked as old, with its age (e.g., "as of 04:55"), and a short "check current conditions" note. Don't show old data as if it were live.
- FR-17: Config file for location, mode windows, dwell times, hazard thresholds, and staleness limits.

---

## 4. Non-Functional Requirements

| ID | Category | Requirement |
|----|----------|-------------|
| NFR-1 | Performance | Poll intervals: weather/alerts every 10–15 min; traffic every 1–2 min (within the 511GA limit of 10 calls/60 s). Slide render under 1 s. |
| NFR-2 | Reliability | Unattended operation. Backend and kiosk auto-restart on failure. A brief API outage must not blank the board. |
| NFR-3 | Data accuracy | Authoritative values shown verbatim. Old data clearly labeled as old. |
| NFR-4 | Security | Single self-contained box. Anthropic API key stored as a secret, never in source or frontend. |
| NFR-5 | Scalability | Single kiosk in v1. The 511GA limit (10 calls/60 s per key) would only matter on a future multi-display fan-out. |
| NFR-6 | Maintainability | Config-driven behavior; structured logging of fetches, failures, and LLM calls. |
| NFR-7 | Legibility | High-contrast palette, large type for cross-room viewing, hazard status not conveyed by color alone. |

---

## 5. Use Cases

UC-1 — Morning glance. The crew walks in; the board is in Morning Mode. The briefing leads with the day's top hazard in plain language. They get the gist in one dwell cycle.

UC-2 — Severe weather day. An NWS alert fires overnight. On the next poll the system flags it, ranks it at the top per D5, and the briefing leads with it; the look-ahead shows the SPC outlook.

UC-3 — Source outage. The 511GA endpoint times out. The disruptions slide shows the last-good events marked with their age; other slides keep running. The board never blanks or shows phantom-live data.

UC-4 — Afternoon transition. At the configured time the board switches to Afternoon Mode, drops the morning briefing, and surfaces PM commute conditions and the rolling 3-day forecast.

UC-5 — Maintainer tuning. The owner edits the config to change the heat-index threshold and the morning/afternoon switch time. Changes take effect on reload, no code change.

---

## 6. Wireframes (kiosk, 16:9 landscape)

### 6.1 Morning — Briefing (BLUF)
```
+----------------------------------------------------------+
|  MORNING BRIEFING                   Fri 13 Jun  06:42     |
|----------------------------------------------------------|
|  Bottom line: heat is today's primary hazard. Index      |
|  reaches 104 by early afternoon; thunderstorms develop   |
|  after 2 PM with a marginal lightning threat. Air        |
|  quality is Code Orange. Recommend heavy work before     |
|  noon, hourly hydration, and clearing elevated and       |
|  exposed work once storms move in.                       |
|                                                          |
|  WATCH FOR                                               |
|   - Heat index to ~104F after noon — heat illness risk   |
|   - PM thunderstorms after 2 PM — lightning              |
|   - Air quality Code Orange — pace the sensitive crew    |
|----------------------------------------------------------|
|  Sources: NWS FFC, SPC  ·  Updated 06:40                 |
+----------------------------------------------------------+
```

### 6.2 Morning — Weather (field-focused)
```
+----------------------------------------------------------+
|  WEATHER — ATLANTA METRO            Fri 13 Jun  06:42     |
|----------------------------------------------------------|
|   NOW      78F, feels 82F        Wind  SW 6 mph          |
|                                                          |
|   TODAY    High 96F              Rain  PM storms ~40%    |
|            Heat index to 104F          (after 2 PM)     |
|            Daylight til 8:51 PM                          |
|----------------------------------------------------------|
|  Source: NWS FFC  ·  Updated 06:35                       |
+----------------------------------------------------------+
```

### 6.3 Morning — Disruptions and Alerts
```
+----------------------------------------------------------+
|  DISRUPTIONS & ALERTS               Fri 13 Jun  06:42    |
|----------------------------------------------------------|
|   TRAFFIC (511GA)                                        |
|   * I-285 WB @ Ashford-Dunwoody — crash, 2 lanes blocked |
|   * I-75 NB @ MM 251 — construction, delays              |
|                                                          |
|   ALERTS (NWS)                                           |
|   * Heat Advisory — metro-wide, until 8 PM               |
|----------------------------------------------------------|
|  Sources: 511GA, NWS  ·  Updated 06:41                   |
+----------------------------------------------------------+
```

### 6.4 Look Ahead (shared)
```
+----------------------------------------------------------+
|  3-DAY LOOK AHEAD                   Fri 13 Jun  06:42    |
|----------------------------------------------------------|
|     SAT 14          SUN 15          MON 16               |
|     [icon]          [icon]          [icon]               |
|     H97 / L75       H94 / L73       H90 / L71            |
|     Storms 50%      Storms 30%      Clear                |
|                                                          |
|   SPC OUTLOOK: Slight risk Sat (metro edge)             |
|----------------------------------------------------------|
|  Sources: NWS FFC, SPC  ·  Updated 06:40                 |
+----------------------------------------------------------+
```

### 6.5 Afternoon — PM Commute
```
+----------------------------------------------------------+
|  PM COMMUTE                         Fri 13 Jun  15:20    |
|----------------------------------------------------------|
|   NOW    91F, feels 99F        Storms ending ~6 PM      |
|                                                          |
|   TRAFFIC (511GA)                                        |
|   * I-20 EB — heavy, about +18 min                      |
|   * GA-400 SB — incident @ Northridge                   |
|----------------------------------------------------------|
|  Sources: NWS, 511GA  ·  Updated 15:19                   |
+----------------------------------------------------------+
```

### 6.6 Degraded state (any slide)
```
+----------------------------------------------------------+
|  WEATHER — ATLANTA METRO            Fri 13 Jun  06:42    |
|----------------------------------------------------------|
|   Data as of 04:55 (about 2 hrs ago) — source is down,  |
|   so check current conditions before you rely on this.  |
|                                                          |
|   Last known: 74F, High 96F, PM storms 40%              |
|----------------------------------------------------------|
|  Source: NWS FFC  ·  last good 04:55                     |
+----------------------------------------------------------+
```

---

## 7. Technical Specifications

### 7.1 Architecture
Everything runs on one self-contained mini PC: the Python backend, a local web frontend, and the Chromium kiosk browser pointed at localhost. No external services to stand up, no network dependency beyond ordinary internet access for the source APIs.

1. Backend ingestion + cache (Python). Polls each source on its own schedule, validates and normalizes responses, computes the ranked hazard flags (D5 order), and writes a single consolidated state object with per-source timestamps to a local cache.
2. Intelligence step (Python → Anthropic API). On schedule/material change, sends the validated structured state to Claude Sonnet 4.6 and stores the returned briefing prose alongside the state. Numbers are not taken from model output.
3. Presentation (local frontend in Chromium kiosk). Reads the consolidated state from a localhost endpoint served by the backend, renders the slides, and rotates the carousel. Figures bind to cached source values; only the briefing prose binds to model output.

Rationale: Python covers ingestion, scheduling, and the API call and matches your stated preference. No Node runtime is needed — the same backend can serve a localhost JSON endpoint and the static frontend. One process tree, one box.

### 7.2 Data flow
```
NWS / SPC / 511GA / AirNow --> [Python pollers] --> validate / normalize / rank
                                   |
                                   v
                          [consolidated state + timestamps cache]
                                   |
                  schedule / material change
                                   v
                       [Anthropic Sonnet 4.6] --> briefing prose
                                   |
                                   v
        [localhost endpoint] <--- backend ---> [Chromium kiosk frontend]
```

### 7.3 BLUF / briefing contract
- Input: structured JSON of validated values and the ranked hazard flags (active alerts, SPC category, threshold crossings, key forecast figures, AQI).
- Task: write a short briefing in an analyst's voice — open with the bottom line and the primary hazard (top-ranked per D5), summarize the relevant conditions, then give recommended actions. Measured and assessment-driven.
- Constraints: professional but not military or corporate; no invented numbers. Frame as assessment and recommendation. Reference conditions; let the slide show the figures.
- Fallback: if the model call fails or returns nothing, fall back to a simple templated briefing built from the hazard flags so the board keeps working.

### 7.4 Integration points
| Source | Endpoint | Auth | Format |
|--------|----------|------|--------|
| NWS | api.weather.gov (points, forecast, alerts, observations) | User-Agent header only | GeoJSON |
| SPC | Convective outlook / mesoscale products | None (public) | To confirm at build |
| 511GA | 511ga.org REST API (events, alerts, cameras, message signs) | Developer key | JSON |
| AirNow | airnowapi.org current observations by lat/long | API key | JSON |
| Anthropic | Messages API, model claude-sonnet-4-6 | API key (secret) | JSON |

### 7.5 Verified source facts
- NWS api.weather.gov requires no API key — only a User-Agent header — and returns GeoJSON. Atlanta metro is served by WFO Peachtree City (FFC).
- 511GA exposes a REST API for cameras, message signs, events, and alerts; it requires a free developer key and is throttled to ten calls per 60 seconds.
- SPC products (Day 1–3 convective outlooks, mesoscale discussions, watches) are publicly available; exact feed format to be confirmed during build.
- EPA AirNow exposes a free API (account/key required) returning current AQI value and category by latitude/longitude on an hourly NowCast basis; rate-limited to 500 requests per hour per service.

---

## 8. Dependencies

External services
- NWS api.weather.gov — free, no key, User-Agent required.
- SPC public products — free.
- 511GA REST API — free developer key; 10 calls / 60 s.
- EPA AirNow API — free, account/key required; 500 req/hr per service. Source for AQI.
- Anthropic API (Sonnet 4.6) — paid, key required.

Hardware
- Mini PC (self-contained: backend + frontend + Chromium kiosk).
- Existing safety-area TV as the display.

---

## 9. Timeline and Milestones

Single developer; relative phases with estimated developer-hours. Assign calendar dates once an owner and start date are set.

| Milestone | Scope | Est. effort | Exit criteria |
|-----------|-------|-------------|---------------|
| M0 — Ingestion + cache | Pollers for NWS, SPC, 511GA; validation; ranked hazard flags; consolidated state | 16–24 h | Live data cached and inspectable locally |
| M1 — Static render | Carousel shell, all slides on real cached data, freshness footer, degraded state | 16–24 h | Board runs end-to-end on real data, no LLM |
| M2 — Briefing | Anthropic integration, plain-voice prompt, templated fallback | 8–12 h | Briefing generates on schedule/change; fallback verified |
| M3 — Kiosk hardening | Auto-restart, Chromium kiosk config, mode switching, config file | 8–16 h | Unattended 24 h run survives reboot and a simulated outage |
| M4 — Pilot | Deploy to safety-area TV, observe, tune thresholds and dwell | 8 h + observation | One week of stable operation |

M1 ships before M2 so the board has standalone value before the briefing layer is added.

---

## 10. Budget and Resource Allocation

Capital and recurring costs separated. Figures marked (assumption) need your confirmation.

### 10.1 Capital (one-time)
| Item | Cost basis | Notes |
|------|-----------|-------|
| Mini PC | ~$150–$500 | Self-contained host. Modest spec is sufficient. |
| Display (TV) | $0 (assumption) | Existing safety-area TV. |
| Development labor | 56–84 h (M0–M4) | Internal labor; cost = hours × loaded rate (rate not modeled). |

### 10.2 Recurring (monthly)
| Item | Cost basis | Notes |
|------|-----------|-------|
| NWS / SPC / 511GA | $0 | Free public sources. |
| Anthropic API | Low; dominated by token volume | See estimate below. |
| Maintenance labor | ~1–2 h/month (assumption) | Threshold tuning, source-change response. |
| Power | Negligible | Low-draw mini PC plus the display. |

Anthropic cost reasoning: at roughly 10–15 briefing generations per day, each on the order of low-thousands of input tokens plus a few hundred output tokens, total volume is tens of thousands of tokens per day — a small monthly total. Exact dollar cost depends on the current Sonnet 4.6 per-token rate, which should be confirmed against current Anthropic pricing rather than assumed here; the volume is low enough it is very unlikely to be a material line item.

### 10.3 Human resources
- Developer/owner: Chris Lee (assumption).
- Maintainer and fallback: open item. An info board still loses its value if it quietly breaks while you're in the field; name a fallback before the M4 pilot.

---

## 11. Assumptions and Open Items

Stated assumptions (correct any that are wrong)
- A1: Location target is generic Atlanta metro (single point/zone), not specific job sites or routes. Site/route geofencing is a candidate v2 enhancement.
- A2: Existing TV incurs no capital cost.
- A3: Single morning muster window; one morning/afternoon switch time suffices.
- A4: Chris is the developer/owner.

Open items (non-blocking for build; assume the defaults and flag if a decision is needed)
- O1: Generic-metro vs. specific sites/routes (refines A1). Build assumes generic Atlanta metro.
- O2: Mini PC procurement — spec and purchaser.
- O3: Named maintainer and fallback (recommended before the M4 pilot).
- O4: Target go-live date.

Resolved since v0.4
- Hazard trigger thresholds — finalized in Section 12.
- Disruptions vs. news scope — structured sources only (D2).

---

## 12. Hazard Trigger Thresholds

These thresholds drive the deterministic hazard flags (FR-14) and the D5 ranking that decides what the briefing leads with. Values are tiered by confidence: Firm = published, stable standards built against directly; Verify (FFC) = region-specific NWS alert criteria to confirm against current WFO Peachtree City directives at build time; Default = operational values set to United's risk tolerance and adjustable in config.

| # | Hazard | Source | Board trigger (appears / "watch for") | Escalation | Field note | Tier |
|---|--------|--------|----------------------------------------|------------|------------|------|
| 1 | Severe weather | NWS alerts + SPC outlook | Any active Tornado / Severe T-storm / Flash Flood Watch or Warning for the metro, or SPC Day 1 categorical >= Slight | Watch -> Warning; SPC Marginal -> Slight -> Enhanced -> Moderate -> High. Lead the BLUF on any active Warning | Deterministic from feeds; nothing inferred | Firm |
| 2 | Heat index | NWS forecast apparent temp + NWS heat alerts (HeatRisk optional) | Forecast heat index reaches Extreme Caution band (>=90F) during work hours | Danger band >=103F; Extreme Danger >=125F. Elevate on active Heat Advisory or Extreme Heat Warning | Key the callout on the work bands (actionable); use NWS alerts as an escalator | Bands firm; alert thresholds verify |
| 3 | Winter weather | NWS winter/cold alerts + forecast | Any active Winter Weather Advisory / Winter Storm or Ice Storm Warning / Cold Weather Advisory / Extreme Cold Warning; or any forecast frozen precip; or <=32F with precip | Advisory -> Warning. Any ice accretion flagged prominently | For Atlanta, ice on bridges/overpasses is the real hazard, not snow totals | Triggers firm; cold/wind-chill values verify |
| 4 | Thunderstorms (non-severe) | NWS forecast (lightning feed later) | Thunder in forecast during work hours, or thunderstorm probability >=30% | If it meets severe criteria it ranks as #1 instead | Crew rule of thumb: 30-30 — shelter when flash-to-bang <=30s, resume 30 min after last thunder. No live strike feed in current sources | 30-30 firm; 30% default |
| 5 | Rain | NWS forecast (PoP, QPF) | PoP >=50% during work hours, or QPF >=0.25 in | Flood Watch/Warning escalates to #1 | Relevance is slip/mud/excavation/visibility, not the rain itself | Operational default |
| 6 | Wind | NWS forecast + Wind/High Wind alerts | Active Wind Advisory or High Wind Warning, or forecast gusts >= set threshold | Advisory (sustained ~31–39 mph or gusts ~46 mph) -> High Wind Warning (sustained >=40 or gusts >=58) | Go/no-go for aerial lifts and cranes is set by the equipment manufacturer's wind limits, not this board. Many aerial platforms restrict around 28 mph; crane charts derate earlier. Board flags, manual decides | Alert values verify; field limits equipment-specific |
| – | AQI (separate callout) | EPA AirNow API | AQI >=101 (Code Orange / Unhealthy for Sensitive Groups) | 151–200 Unhealthy; 201–300 Very Unhealthy; 301+ Hazardous | Atlanta drivers are summer ozone and wildfire-smoke PM2.5 | Breakpoints firm |

Confidence tiers
- Firm: SPC categorical scale; NWS heat-index work bands (Caution 80–90F, Extreme Caution 90–103F, Danger 103–124F, Extreme Danger >=125F); EPA AQI breakpoints; NOAA 30-30 lightning guidance.
- Verify (FFC): NWS alert criteria vary by office. For the Southeast, a Heat Advisory is generally issued near a sustained heat index of 105F, with an Extreme Heat Warning near 110F; confirm exact FFC values and the cold-weather criteria at build. NWS also publishes a 0–4 HeatRisk scale and has renamed the cold products to Cold Weather Advisory and Extreme Cold Warning, so the system may key on either the headline or HeatRisk.
- Default: rain PoP/QPF, thunderstorm probability, and the wind gust field-trigger are configurable; conservative starting values are shown.

Decisions baked in
- Heat keying: key the heat callout on the NWS heat-index work bands for crew actionability, and elevate on an active NWS Heat Advisory or Extreme Heat Warning. HeatRisk optional as a secondary signal.
- Wind go/no-go: the board flags forecast wind only; the decision to operate aerial lifts or cranes is governed by the equipment manufacturer's wind limits and load charts.

---

End of v0.5 (build-ready).
