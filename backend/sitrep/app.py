"""
FastAPI application for the Field SITREP Board.

Routes:
  GET /api/state   — consolidated state JSON (demo mode: fixture data)
  GET /healthz     — {"ok": true} liveness
  GET /            — serves frontend/index.html
  GET /assets/*    — static frontend files

Demo mode (SITREP_DEMO=1 or no API keys):
  Serves fixture JSON from backend/sitrep/fixtures/
  Supports ?scenario=morning|afternoon|degraded query param.

Binds to 127.0.0.1 only (loopback). Port from SITREP_PORT (default 8080).
"""
from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .cache import get_cache
from .config import get_config
from . import scheduler as sched_module
from .state_builder import _compute_display_mode

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Demo mode detection
# ---------------------------------------------------------------------------

_FIXTURES_DIR = Path(__file__).parent / "fixtures"
# Repo root is two levels up from backend/sitrep/
_REPO_ROOT = Path(__file__).resolve().parents[2]
_FRONTEND_DIR = _REPO_ROOT / "frontend"


def _demo_mode_active() -> bool:
    """
    Demo mode is active when:
      - SITREP_DEMO=1 is set, OR
      - No source API keys are present (GA511_API_KEY and AIRNOW_API_KEY both absent)
    """
    if os.environ.get("SITREP_DEMO", "").strip() == "1":
        return True
    # Auto-enable when no source API keys are configured
    has_any_key = bool(
        os.environ.get("GA511_API_KEY") or
        os.environ.get("AIRNOW_API_KEY") or
        os.environ.get("ANTHROPIC_API_KEY")
    )
    return not has_any_key


def _load_fixture(scenario: Optional[str], config: Any) -> dict:
    """Load the appropriate fixture for demo mode."""
    if scenario in ("morning", "afternoon", "degraded"):
        fname = f"sample_state_{scenario}.json"
    else:
        # Auto-select by current display mode
        mode = _compute_display_mode(config)
        fname = f"sample_state_{mode}.json"

    fpath = _FIXTURES_DIR / fname
    try:
        with open(fpath) as fh:
            return json.load(fh)
    except Exception as exc:
        log.error("Failed to load fixture %s: %s", fpath, exc)
        # Last-resort: return morning fixture
        fallback = _FIXTURES_DIR / "sample_state_morning.json"
        with open(fallback) as fh:
            return json.load(fh)


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Lifespan context manager: startup + shutdown."""
    cfg = get_config()
    demo = _demo_mode_active()

    if demo:
        reason = "SITREP_DEMO=1" if os.environ.get("SITREP_DEMO") == "1" else "no API keys detected"
        log.warning("=== DEMO MODE ACTIVE (%s) === /api/state serves fixture data", reason)
    else:
        log.info("Starting live mode — running initial poll cycle")
        try:
            sched_module.initial_load()
            sched_module.start_scheduler()
        except Exception as exc:
            log.error("Scheduler startup failed: %s", exc)

    yield  # app runs here

    sched_module.stop_scheduler()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Field SITREP Board",
        description="Hazard-forward situational awareness backend",
        version="0.1.0",
        docs_url="/docs",
        redoc_url=None,
        lifespan=_lifespan,
    )

    # ── Routes ────────────────────────────────────────────────────────────────

    @app.get("/healthz", tags=["system"])
    async def healthz() -> dict:
        return {"ok": True}

    @app.get("/api/state", tags=["data"])
    async def get_state(
        scenario: Optional[str] = Query(
            default=None,
            description="Demo scenario: morning | afternoon | degraded"
        )
    ) -> JSONResponse:
        cfg = get_config()

        if _demo_mode_active():
            data = _load_fixture(scenario, cfg)
            return JSONResponse(content=data)

        # Live mode: return from cache
        cache = get_cache()
        state = cache.get_state()

        if state is None:
            # Cache not populated yet — return degraded fixture
            log.warning("/api/state called before cache populated; returning degraded fixture")
            data = _load_fixture("degraded", cfg)
            return JSONResponse(content=data, status_code=503)

        return JSONResponse(content=state)

    @app.get("/api/alerts.geojson", tags=["data"])
    async def get_alerts_geojson() -> JSONResponse:
        """Active NWS alert polygons as GeoJSON, for the map overlay.

        Served from loopback so the authoritative warning shapes never depend on
        an external fetch at render time. Demo mode serves a static sample.
        """
        empty = {"type": "FeatureCollection", "features": []}

        if _demo_mode_active():
            sample = _FIXTURES_DIR / "sample_alerts.geojson"
            try:
                with open(sample) as fh:
                    return JSONResponse(content=json.load(fh))
            except Exception:
                return JSONResponse(content=empty)

        cache = get_cache()
        nws_data = cache.get_data("nws")
        if nws_data and nws_data.get("alerts_geojson"):
            return JSONResponse(content=nws_data["alerts_geojson"])
        return JSONResponse(content=empty)

    # ── Static frontend ───────────────────────────────────────────────────────
    if _FRONTEND_DIR.exists():
        # Mount specific asset paths before the catch-all
        app.mount(
            "/",
            StaticFiles(directory=str(_FRONTEND_DIR), html=True),
            name="frontend",
        )
        log.info("Frontend static files mounted from %s", _FRONTEND_DIR)
    else:
        # Frontend not present — serve a minimal placeholder
        @app.get("/", include_in_schema=False)
        async def root() -> JSONResponse:
            return JSONResponse(
                content={
                    "message": "SITREP backend running",
                    "api": "/api/state",
                    "health": "/healthz",
                    "note": "Frontend not found — deploy frontend/ directory",
                }
            )
        log.warning("Frontend directory not found at %s — serving placeholder", _FRONTEND_DIR)

    return app


# Module-level app instance for uvicorn
app = create_app()
