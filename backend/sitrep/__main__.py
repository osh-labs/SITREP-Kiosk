"""
Entry point: python -m sitrep  (from backend/)
         or: python -m backend.sitrep  (from repo root)

Launches uvicorn on $SITREP_HOST:$SITREP_PORT (default 0.0.0.0:8080), so the
board is reachable from other devices on the facility LAN in addition to the
kiosk itself. Set SITREP_HOST=127.0.0.1 to restrict to loopback only.
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import uvicorn

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)

log = logging.getLogger(__name__)


def main() -> None:
    port = int(os.environ.get("SITREP_PORT", "8080"))
    host = os.environ.get("SITREP_HOST", "0.0.0.0")  # LAN-visible by default

    log.info("Starting SITREP backend on %s:%d", host, port)

    demo = os.environ.get("SITREP_DEMO", "")
    if demo == "1":
        log.warning("SITREP_DEMO=1 — demo mode active, serving fixture data")

    # Ensure the backend/ directory is on sys.path so uvicorn can import sitrep.app
    # regardless of whether we were invoked as `python -m sitrep` (from backend/)
    # or `python -m backend.sitrep` (from repo root).
    backend_dir = Path(__file__).resolve().parent.parent  # .../backend/
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))

    # Import the app object directly and pass it to uvicorn to avoid the
    # module-string import path issue when running from repo root.
    from sitrep.app import app  # noqa: F401  (triggers config load + demo detection)

    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info",
        reload=False,
    )


if __name__ == "__main__":
    main()
