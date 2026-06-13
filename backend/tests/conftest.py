"""
Pytest configuration and shared fixtures for SITREP backend tests.

All tests run with NO network and NO API keys.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Ensure the backend package is importable when running from the repo root
backend_dir = Path(__file__).resolve().parents[1]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

# Clear all API keys for test isolation
@pytest.fixture(autouse=True)
def no_api_keys(monkeypatch):
    """Strip all API keys so tests never make live calls."""
    monkeypatch.delenv("GA511_API_KEY", raising=False)
    monkeypatch.delenv("AIRNOW_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


@pytest.fixture
def demo_env(monkeypatch):
    """Enable demo mode."""
    monkeypatch.setenv("SITREP_DEMO", "1")


@pytest.fixture
def config():
    """Return a Config instance loaded from the example config."""
    from sitrep.config import load_config
    return load_config(force_reload=True)


@pytest.fixture
def fresh_cache():
    """Return a fresh StateCache (not the singleton)."""
    from sitrep.cache import StateCache
    return StateCache(staleness_seconds=3600)
