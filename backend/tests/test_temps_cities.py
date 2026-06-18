"""Tests for the city temperature layer: source parsing + /api/temps.geojson."""
from starlette.testclient import TestClient

from sitrep.app import create_app
from sitrep.config import get_config
from sitrep.sources import openmeteo_cities as cities


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeClient:
    """Echoes a temperature for each requested coordinate."""

    def __init__(self, capture=None):
        self._capture = capture

    def get(self, url, params=None, timeout=None):
        if self._capture is not None:
            self._capture.update(params or {})
        lats = params["latitude"].split(",")
        lons = params["longitude"].split(",")
        items = [
            {"latitude": float(la), "longitude": float(lo),
             "current": {"temperature_2m": 80.0 + i}}
            for i, (la, lo) in enumerate(zip(lats, lons))
        ]
        return _FakeResp(items)


def test_fetch_builds_labeled_geojson():
    cfg = get_config()
    out = cities.fetch(_FakeClient(), cfg)
    assert out["_ok"] is True
    assert out["type"] == "FeatureCollection"
    assert len(out["features"]) == len(cities._DEFAULT_CITIES)
    f0 = out["features"][0]
    assert f0["geometry"]["type"] == "Point"
    # GeoJSON is [lon, lat]; placement matches the first default city.
    lon, lat = f0["geometry"]["coordinates"]
    first = cities._DEFAULT_CITIES[0]
    assert (round(lat, 3), round(lon, 3)) == (round(first["lat"], 3), round(first["lon"], 3))
    assert f0["properties"]["name"] == first["name"]
    assert isinstance(f0["properties"]["temp_f"], int)
    # Every default city is rendered.
    names = {ft["properties"]["name"] for ft in out["features"]}
    assert {"Paducah", "St. Augustine", "Atlanta"} <= names


def test_fetch_requests_fahrenheit_current_temp():
    cfg = get_config()
    captured: dict = {}
    cities.fetch(_FakeClient(capture=captured), cfg)
    assert captured["temperature_unit"] == "fahrenheit"
    assert captured["current"] == "temperature_2m"
    # One coordinate per city in the bulk request.
    assert len(captured["latitude"].split(",")) == len(cities._DEFAULT_CITIES)


def test_config_cities_override_defaults():
    class _Cfg:
        def get(self, *keys, default=None):
            if keys == ("weather_map", "temps", "cities"):
                return [{"name": "Testville", "lat": 30.0, "lon": -83.0}]
            return default

    out = cities.fetch(_FakeClient(), _Cfg())
    assert len(out["features"]) == 1
    assert out["features"][0]["properties"]["name"] == "Testville"


def test_fetch_handles_failure_gracefully():
    class _Boom:
        def get(self, *a, **k):
            raise RuntimeError("network down")

    out = cities.fetch(_Boom(), get_config())
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
        assert "name" in f["properties"]


def test_state_weather_map_has_rotation_and_temps(demo_env):
    app = create_app()
    with TestClient(app) as client:
        wm = client.get("/api/state").json()["weather_map"]
        assert "rotation" in wm
        assert "temps" in wm["layers"]
        assert wm["rotation"]["interval_seconds"] == 20
        assert "temps" in wm["rotation"]["modes"]
