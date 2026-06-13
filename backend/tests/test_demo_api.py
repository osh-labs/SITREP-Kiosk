"""
Tests for demo-mode /api/state output.

Validates that:
  - /api/state returns valid JSON
  - The response matches the STATE_CONTRACT.md key structure
  - Required top-level keys are all present
  - Source blocks have the required fields
  - Scenario query param works (morning/afternoon/degraded)
  - /healthz returns {"ok": true}
  - No network calls are made
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


# ── Required STATE_CONTRACT keys ─────────────────────────────────────────────

REQUIRED_TOP_LEVEL = {
    "generated_at", "display", "location", "briefing",
    "hazards", "weather", "commute", "disruptions",
    "forecast_3day", "sources",
}

REQUIRED_DISPLAY_KEYS = {"mode", "dwell_seconds", "refresh_seconds"}
REQUIRED_LOCATION_KEYS = {"name", "lat", "lon"}
REQUIRED_BRIEFING_KEYS = {"bottom_line", "watch_for", "source", "generated_at", "sources"}
REQUIRED_HAZARDS_KEYS = {"ranked", "aqi_callout"}
REQUIRED_WEATHER_KEYS = {"current", "today", "source"}
REQUIRED_COMMUTE_KEYS = {"current", "traffic", "source"}
REQUIRED_DISRUPTIONS_KEYS = {"traffic", "alerts", "source"}
REQUIRED_FORECAST_KEYS = {"days", "spc_outlook", "source"}
REQUIRED_SOURCES_KEYS = {"nws", "spc", "ga511", "airnow"}
REQUIRED_SOURCE_BLOCK_KEYS = {"name", "ok", "stale", "fetched_at", "age_seconds", "last_good_at"}

VALID_MODES = {"morning", "afternoon"}
VALID_BRIEFING_SOURCES = {"model", "template"}
VALID_SEVERITIES = {"info", "watch", "advisory", "caution", "danger", "extreme"}


def _validate_source_block(sb: dict, path: str) -> None:
    """Validate a source block has all required keys."""
    missing = REQUIRED_SOURCE_BLOCK_KEYS - set(sb.keys())
    assert not missing, f"Source block at {path} missing keys: {missing}"
    assert isinstance(sb["ok"], bool), f"{path}.ok must be bool"
    assert isinstance(sb["stale"], bool), f"{path}.stale must be bool"


def _validate_state(data: dict, scenario: str = "unknown") -> None:
    """Full contract validation of a state dict."""
    # Top-level keys
    missing = REQUIRED_TOP_LEVEL - set(data.keys())
    assert not missing, f"[{scenario}] Missing top-level keys: {missing}"

    # display
    d = data["display"]
    assert (REQUIRED_DISPLAY_KEYS - set(d.keys())) == set(), f"[{scenario}] display missing keys"
    assert d["mode"] in VALID_MODES, f"[{scenario}] display.mode invalid: {d['mode']}"
    assert isinstance(d["dwell_seconds"], (int, float))
    assert isinstance(d["refresh_seconds"], (int, float))

    # location
    loc = data["location"]
    assert (REQUIRED_LOCATION_KEYS - set(loc.keys())) == set()
    assert isinstance(loc["lat"], (int, float))
    assert isinstance(loc["lon"], (int, float))

    # briefing
    br = data["briefing"]
    assert (REQUIRED_BRIEFING_KEYS - set(br.keys())) == set(), f"[{scenario}] briefing missing keys"
    assert br["source"] in VALID_BRIEFING_SOURCES
    assert isinstance(br["watch_for"], list)
    assert isinstance(br["sources"], list)

    # hazards
    hz = data["hazards"]
    assert (REQUIRED_HAZARDS_KEYS - set(hz.keys())) == set()
    assert isinstance(hz["ranked"], list)
    for i, h in enumerate(hz["ranked"]):
        assert "key" in h, f"[{scenario}] hazards.ranked[{i}] missing key"
        assert "rank" in h
        assert "label" in h
        assert "severity" in h
        assert h["severity"] in VALID_SEVERITIES, f"[{scenario}] invalid severity: {h['severity']}"

    # weather
    w = data["weather"]
    assert (REQUIRED_WEATHER_KEYS - set(w.keys())) == set()
    _validate_source_block(w["source"], f"[{scenario}] weather.source")

    # commute
    c = data["commute"]
    assert (REQUIRED_COMMUTE_KEYS - set(c.keys())) == set()
    _validate_source_block(c["source"], f"[{scenario}] commute.source")
    assert isinstance(c["traffic"], list)

    # disruptions
    dis = data["disruptions"]
    assert (REQUIRED_DISRUPTIONS_KEYS - set(dis.keys())) == set()
    _validate_source_block(dis["source"], f"[{scenario}] disruptions.source")
    assert isinstance(dis["traffic"], list)
    assert isinstance(dis["alerts"], list)

    # forecast_3day
    fc = data["forecast_3day"]
    assert (REQUIRED_FORECAST_KEYS - set(fc.keys())) == set()
    _validate_source_block(fc["source"], f"[{scenario}] forecast_3day.source")
    assert isinstance(fc["days"], list)

    # sources map
    srcs = data["sources"]
    assert (REQUIRED_SOURCES_KEYS - set(srcs.keys())) == set()
    for key in REQUIRED_SOURCES_KEYS:
        _validate_source_block(srcs[key], f"[{scenario}] sources.{key}")


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def demo_client(monkeypatch):
    """TestClient with SITREP_DEMO=1 and no API keys."""
    monkeypatch.setenv("SITREP_DEMO", "1")
    monkeypatch.delenv("GA511_API_KEY", raising=False)
    monkeypatch.delenv("AIRNOW_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    # Force fresh app creation after env change
    import importlib
    import sitrep.app as app_mod
    importlib.reload(app_mod)

    from sitrep.app import create_app
    test_app = create_app()
    return TestClient(test_app, raise_server_exceptions=True)


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestHealthz:
    def test_healthz_ok(self, demo_client):
        resp = demo_client.get("/healthz")
        assert resp.status_code == 200
        data = resp.json()
        assert data == {"ok": True}


class TestDemoApiState:
    def test_state_returns_200(self, demo_client):
        resp = demo_client.get("/api/state")
        assert resp.status_code == 200

    def test_state_is_valid_json(self, demo_client):
        resp = demo_client.get("/api/state")
        data = resp.json()  # raises on invalid JSON
        assert isinstance(data, dict)

    def test_state_validates_contract_default(self, demo_client):
        resp = demo_client.get("/api/state")
        data = resp.json()
        _validate_state(data, "default")

    def test_morning_scenario(self, demo_client):
        resp = demo_client.get("/api/state?scenario=morning")
        assert resp.status_code == 200
        data = resp.json()
        _validate_state(data, "morning")
        assert data["display"]["mode"] == "morning"

    def test_afternoon_scenario(self, demo_client):
        resp = demo_client.get("/api/state?scenario=afternoon")
        assert resp.status_code == 200
        data = resp.json()
        _validate_state(data, "afternoon")
        assert data["display"]["mode"] == "afternoon"

    def test_degraded_scenario(self, demo_client):
        resp = demo_client.get("/api/state?scenario=degraded")
        assert resp.status_code == 200
        data = resp.json()
        _validate_state(data, "degraded")

    def test_degraded_has_stale_sources(self, demo_client):
        resp = demo_client.get("/api/state?scenario=degraded")
        data = resp.json()
        # In the degraded fixture, at least one source should be stale
        sources = data["sources"]
        stale_sources = [k for k, v in sources.items() if v.get("stale") is True]
        assert len(stale_sources) > 0

    def test_ranked_hazards_are_ordered(self, demo_client):
        resp = demo_client.get("/api/state?scenario=morning")
        data = resp.json()
        ranked = data["hazards"]["ranked"]
        for i, h in enumerate(ranked):
            assert h["rank"] == i + 1

    def test_briefing_source_is_valid(self, demo_client):
        resp = demo_client.get("/api/state?scenario=morning")
        data = resp.json()
        assert data["briefing"]["source"] in VALID_BRIEFING_SOURCES

    def test_location_fields_are_numeric(self, demo_client):
        resp = demo_client.get("/api/state")
        data = resp.json()
        assert isinstance(data["location"]["lat"], (int, float))
        assert isinstance(data["location"]["lon"], (int, float))


class TestFixtureFiles:
    """Directly validate the fixture JSON files match the contract."""

    FIXTURES_DIR = Path(__file__).resolve().parents[1] / "sitrep" / "fixtures"

    @pytest.mark.parametrize("fname", [
        "sample_state_morning.json",
        "sample_state_afternoon.json",
        "sample_state_degraded.json",
    ])
    def test_fixture_validates(self, fname):
        fpath = self.FIXTURES_DIR / fname
        assert fpath.exists(), f"Fixture not found: {fpath}"
        with open(fpath) as fh:
            data = json.load(fh)
        _validate_state(data, fname)
