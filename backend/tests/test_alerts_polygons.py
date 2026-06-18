"""Tests for NWS alert polygon resolution (zone geometry) and the AQI block."""
from starlette.testclient import TestClient

from sitrep.app import create_app
from sitrep.sources import nws as nws_source


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _ZoneClient:
    """Serves individual zone URLs (the affectedZones links), each with geometry."""

    def __init__(self):
        self.calls = 0

    def get(self, url, headers=None, timeout=None):
        self.calls += 1
        return _FakeResp({
            "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]},
        })


def test_inline_geometry_passthrough():
    nws_source._zone_geom_cache.clear()
    features = [{
        "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]},
        "properties": {"event": "Tornado Warning", "headline": "h", "areaDesc": "a"},
    }]
    gj = nws_source._build_alerts_geojson(_ZoneClient(), features)
    assert len(gj["features"]) == 1
    assert gj["features"][0]["properties"]["severity"] == "extreme"
    assert gj["features"][0]["geometry"]["type"] == "Polygon"


def test_zone_based_alert_resolves_geometry():
    """An alert with null geometry but affectedZones should still draw."""
    nws_source._zone_geom_cache.clear()
    features = [{
        "geometry": None,
        "properties": {
            "event": "Heat Advisory",
            "headline": "Heat Advisory until 8 PM",
            "areaDesc": "North and Central Georgia",
            "affectedZones": [
                "https://api.weather.gov/zones/forecast/GAZ021",
                "https://api.weather.gov/zones/forecast/GAZ022",
            ],
        },
    }]
    client = _ZoneClient()
    gj = nws_source._build_alerts_geojson(client, features)
    # One feature per resolved zone, all carrying the alert's properties.
    assert len(gj["features"]) == 2
    assert all(f["geometry"]["type"] == "Polygon" for f in gj["features"])
    assert all(f["properties"]["event"] == "Heat Advisory" for f in gj["features"])
    assert all(f["properties"]["severity"] == "advisory" for f in gj["features"])


def test_zone_geometry_is_cached():
    nws_source._zone_geom_cache.clear()
    features = [{
        "geometry": None,
        "properties": {"event": "Flood Warning",
                       "affectedZones": ["https://api.weather.gov/zones/county/GAC121"]},
    }]
    client = _ZoneClient()
    nws_source._build_alerts_geojson(client, features)
    first_calls = client.calls
    # Second build with the same zone makes no new network call.
    nws_source._build_alerts_geojson(client, features)
    assert client.calls == first_calls


def test_alerts_area_from_config():
    class _Cfg:
        def get(self, *keys, default=None):
            if keys == ("weather_map", "alerts", "area"):
                return ["ga", "tn"]
            return default

    assert nws_source._alerts_area(_Cfg()) == "GA,TN"

    class _CfgEmpty:
        def get(self, *keys, default=None):
            return default

    assert nws_source._alerts_area(_CfgEmpty()) == "GA,TN,AL,FL,SC,NC,KY"


def test_state_has_air_quality_demo_mode(demo_env):
    app = create_app()
    with TestClient(app) as client:
        state = client.get("/api/state?scenario=afternoon").json()
        assert "air_quality" in state
        aq = state["air_quality"]
        assert aq["aqi"] is not None
        assert aq["label"]
        assert "source" in aq
