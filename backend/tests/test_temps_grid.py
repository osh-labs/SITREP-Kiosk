"""Tests for the gridded temperature layer: source parsing + /api/temps.geojson."""
from starlette.testclient import TestClient

from sitrep.app import create_app
from sitrep.config import get_config
from sitrep.sources import openmeteo_grid as grid


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeClient:
    """Echoes a temperature for each requested coordinate."""

    def __init__(self, payload=None, capture=None):
        self._payload = payload
        self._capture = capture

    def get(self, url, params=None, timeout=None):
        if self._capture is not None:
            self._capture.update(params or {})
        if self._payload is not None:
            return _FakeResp(self._payload)
        lats = (params["latitude"]).split(",")
        items = [
            {"latitude": float(la), "longitude": float(lo),
             "current": {"temperature_2m": 80.0 + i}}
            for i, (la, lo) in enumerate(zip(lats, params["longitude"].split(",")))
        ]
        return _FakeResp(items)


def test_grid_points_centered_and_sized():
    pts = grid._grid_points(33.749, -84.388, 7, 7, 3.0)
    assert len(pts) == 49
    # Centered: the midpoint of the corners is the center.
    assert pts[0] == (32.249, -85.888)
    assert pts[-1] == (35.249, -82.888)


def test_fetch_builds_geojson_from_multi_point_response():
    cfg = get_config()
    out = grid.fetch(_FakeClient(), cfg)
    assert out["_ok"] is True
    assert out["type"] == "FeatureCollection"
    assert len(out["features"]) == 49
    f0 = out["features"][0]
    assert f0["geometry"]["type"] == "Point"
    # GeoJSON is [lon, lat]; temps round to int.
    lon, lat = f0["geometry"]["coordinates"]
    assert (lat, lon) == (32.249, -85.888)
    assert isinstance(f0["properties"]["temp_f"], int)


def test_fetch_requests_fahrenheit():
    cfg = get_config()
    captured: dict = {}
    grid.fetch(_FakeClient(capture=captured), cfg)
    assert captured["temperature_unit"] == "fahrenheit"
    assert captured["current"] == "temperature_2m"


def test_fetch_handles_failure_gracefully():
    class _Boom:
        def get(self, *a, **k):
            raise RuntimeError("network down")

    out = grid.fetch(_Boom(), get_config())
    assert out["_ok"] is False
    assert out["features"] == []


def test_temps_geojson_demo_mode(demo_env):
    app = create_app()
    with TestClient(app) as client:
        r = client.get("/api/temps.geojson")
        assert r.status_code == 200
        data = r.json()
        assert data["type"] == "FeatureCollection"
        assert len(data["features"]) >= 1
        f = data["features"][0]
        assert f["geometry"]["type"] == "Point"
        assert "temp_f" in f["properties"]


def test_state_weather_map_has_rotation_and_temps(demo_env):
    app = create_app()
    with TestClient(app) as client:
        wm = client.get("/api/state").json()["weather_map"]
        assert "rotation" in wm
        assert "temps" in wm["layers"]
        assert wm["rotation"]["interval_seconds"] == 20
        assert "temps" in wm["rotation"]["modes"]
