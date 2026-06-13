# Field SITREP Board — Backend

Python backend: ingests weather/traffic/AQI data, computes hazard flags, generates an analyst briefing, and serves the consolidated state at a localhost JSON endpoint.

## Requirements

- Python 3.11+
- Repo root: `/path/to/SITREP-Kiosk`

## Setup

```bash
# From repo root
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Copy the example config and (optionally) .env:
```bash
cp config/config.example.yaml config/config.yaml   # edit location, thresholds, etc.
cp .env.example .env                               # fill in API keys
```

## Run in demo mode (no API keys required)

Demo mode serves fixture data from `backend/sitrep/fixtures/`. It activates automatically when no API keys are present, or explicitly with `SITREP_DEMO=1`.

```bash
# From repo root, with venv active:
SITREP_DEMO=1 python -m backend.sitrep

# Or from backend/ directory:
cd backend
SITREP_DEMO=1 python -m sitrep
```

The server binds to `127.0.0.1:8080` (loopback only).

Check it is working:
```bash
curl http://127.0.0.1:8080/healthz
# {"ok":true}

curl http://127.0.0.1:8080/api/state | python3 -m json.tool | head -30

# Force a specific scenario:
curl "http://127.0.0.1:8080/api/state?scenario=morning"
curl "http://127.0.0.1:8080/api/state?scenario=afternoon"
curl "http://127.0.0.1:8080/api/state?scenario=degraded"
```

## Run in live mode (API keys in .env)

Fill in `.env`:
```
NWS_USER_AGENT="UnitedConsulting-FieldSITREP/1.0 (contact: you@example.com)"
GA511_API_KEY=your_511ga_key
AIRNOW_API_KEY=your_airnow_key
ANTHROPIC_API_KEY=your_anthropic_key
SITREP_PORT=8080
```

Then:
```bash
source .env   # or use python-dotenv (loaded automatically at startup)
python -m backend.sitrep
```

The scheduler polls NWS every 15 min, SPC every 30 min, 511GA every 90 s, and AirNow every 30 min. Briefings regenerate every 30 min and on material change (new alerts, hazard threshold crossings).

## Run tests

```bash
# From backend/ directory with venv active:
cd backend
pytest tests/ -v

# Or from repo root:
venv/bin/python -m pytest backend/tests/ -v
```

Tests run with no network and no API keys. All 69 tests should pass.

## Port override

```bash
SITREP_PORT=9090 SITREP_DEMO=1 python -m backend.sitrep
```

## Configuration

Edit `config/config.yaml` to change:
- `location` — lat/lon and display name
- `display.mode_windows.morning_until` — when afternoon mode starts (default `12:00`)
- `display.work_hours` — used for "during work hours" hazard checks
- `polling_seconds` — per-source poll intervals
- `staleness_seconds.default` — how old data must be before the degraded state shows
- `hazard_thresholds` — all trigger values; see comments in `config.example.yaml` for confidence tiers

No code changes are needed to adjust thresholds.

## Package structure

```
backend/
  sitrep/
    __init__.py
    __main__.py          # entry point (python -m sitrep)
    app.py               # FastAPI application, routes, demo mode
    briefing.py          # M2: Anthropic SDK call + templated fallback
    cache.py             # in-memory last-good store with staleness tracking
    config.py            # YAML + .env config loader, typed accessors
    hazards.py           # deterministic D5 hazard ranking from source data
    models.py            # dataclasses mirroring STATE_CONTRACT.md
    scheduler.py         # APScheduler polling loop + state/briefing rebuild
    state_builder.py     # assembles the consolidated state from cache
    sources/
      nws.py             # NWS api.weather.gov poller
      spc.py             # SPC convective outlook poller (GeoJSON)
      ga511.py           # 511GA traffic events/alerts poller
      airnow.py          # EPA AirNow AQI poller
    fixtures/
      sample_state_morning.json
      sample_state_afternoon.json
      sample_state_degraded.json
  tests/
    conftest.py
    test_hazards.py
    test_cache.py
    test_briefing.py
    test_demo_api.py
```

## Notes on SPC

The SPC convective outlook parser (`sources/spc.py`) targets the public GeoJSON endpoints at `spc.noaa.gov/products/outlook/day[1-3]otlk_cat.nolyr.geojson`. These endpoints were not directly verifiable at build time. If the live feed returns an unexpected structure, `spc.py` marks itself `_ok=False` and the rest of the board continues normally (forecast 3-day slide shows no SPC category; the `severe_weather` hazard flag still fires from NWS alerts if present). See the `TODO` comment at the top of `sources/spc.py`.
