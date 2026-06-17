"""Tests for the /api/alerts.geojson route and the new state fields."""
from starlette.testclient import TestClient

from sitrep.app import create_app


def test_alerts_geojson_demo_mode(demo_env):
    app = create_app()
    with TestClient(app) as client:
        r = client.get("/api/alerts.geojson")
        assert r.status_code == 200
        data = r.json()
        assert data["type"] == "FeatureCollection"
        assert len(data["features"]) >= 1
        assert data["features"][0]["geometry"]["type"] == "Polygon"


def test_state_has_new_keys_demo_mode(demo_env):
    app = create_app()
    with TestClient(app) as client:
        state = client.get("/api/state").json()
        assert "astro" in state
        assert "weather_map" in state
        assert "hourly" in state["weather"]
        assert len(state["weather"]["hourly"]) > 0
        # Open-Meteo today extras present
        today = state["weather"]["today"]
        for key in ("sunrise", "sunset", "uv_index", "visibility_mi"):
            assert key in today
        # New source blocks present
        assert "openmeteo" in state["sources"]
        assert "weather_map" in state["sources"]
        # Weather map carries config + freshness
        assert "source" in state["weather_map"]
        assert "center" in state["weather_map"]


def test_degraded_fixture_marks_new_sources_stale(demo_env):
    app = create_app()
    with TestClient(app) as client:
        state = client.get("/api/state?scenario=degraded").json()
        assert state["sources"]["openmeteo"]["stale"] is True
        assert state["sources"]["weather_map"]["stale"] is True
