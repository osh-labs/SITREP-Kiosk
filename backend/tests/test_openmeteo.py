"""Tests for the Open-Meteo poller normalizer (no network)."""
from datetime import datetime

import pytest

from sitrep.sources import openmeteo


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, payload=None, exc=None):
        self._payload = payload
        self._exc = exc
        self.last_params = None

    def get(self, url, params=None, timeout=None):
        self.last_params = params
        if self._exc:
            raise self._exc
        return _FakeResponse(self._payload)


def _sample_payload():
    # Build a 6-hour hourly series starting "now" so trimming keeps it all.
    now_hour = datetime.now().strftime("%Y-%m-%dT%H:00")
    base_day = now_hour[:11]
    hh = int(now_hour[11:13])
    times = [f"{base_day}{(hh + i) % 24:02d}:00" for i in range(6)]
    return {
        "hourly": {
            "time": times,
            "temperature_2m": [78.0, 80.1, 82.5, 84.0, 85.2, 86.0],
            "apparent_temperature": [82.0, 84.0, 88.0, 90.0, 92.0, 93.0],
            "relative_humidity_2m": [60, 62, 65, 68, 70, 72],
            "wind_speed_10m": [6.0, 7.0, 8.0, 9.0, 10.0, 11.0],
            "wind_gusts_10m": [12.0, 14.0, 16.0, 18.0, 20.0, 22.0],
            "precipitation_probability": [10, 20, 30, 40, 50, 60],
            "precipitation": [0.0, 0.0, 0.01, 0.05, 0.12, 0.08],
            "visibility": [16093.0, 16093.0, 12000.0, 9000.0, 8000.0, 8000.0],
        },
        "daily": {
            "sunrise": ["2026-06-13T06:27"],
            "sunset": ["2026-06-13T20:51"],
            "uv_index_max": [8.3],
        },
    }


@pytest.fixture
def cfg():
    from sitrep.config import load_config
    return load_config(force_reload=True)


def test_normalizes_hourly_and_daily(cfg):
    client = _FakeClient(payload=_sample_payload())
    out = openmeteo.fetch(client, cfg)

    assert out["_ok"] is True
    assert len(out["hourly"]) == 6
    first = out["hourly"][0]
    assert first["temp_f"] == 78.0
    assert first["feels_like_f"] == 82.0
    assert first["pop_pct"] == 10
    assert first["wind_mph"] == 6.0
    assert first["gust_mph"] == 12.0
    # Below 80°F the heat index equals the air temp (continuous line)
    assert first["heat_index_f"] == 78.0
    # When hot, heat index is computed and rises above the air temp
    hot = out["hourly"][3]   # 84°F, 68% RH
    assert hot["heat_index_f"] >= hot["temp_f"]

    today = out["today"]
    assert today["sunrise"] == "2026-06-13T06:27"
    assert today["sunset"] == "2026-06-13T20:51"
    assert today["uv_index"] == 8.3
    # 16093 m ≈ 10.0 mi
    assert today["visibility_mi"] == pytest.approx(10.0, abs=0.1)


def test_request_params_keyless_and_fahrenheit(cfg):
    client = _FakeClient(payload=_sample_payload())
    openmeteo.fetch(client, cfg)
    p = client.last_params
    assert p["temperature_unit"] == "fahrenheit"
    assert p["wind_speed_unit"] == "mph"
    assert p["precipitation_unit"] == "inch"
    assert "API_KEY" not in p and "apikey" not in p


def test_hourly_trim_to_twelve(cfg):
    payload = _sample_payload()
    now_hour = datetime.now().strftime("%Y-%m-%dT%H:00")
    base_day = now_hour[:11]
    hh = int(now_hour[11:13])
    # 20 hours of data — should be trimmed to 12.
    payload["hourly"]["time"] = [f"{base_day}{(hh + i) % 24:02d}:00" for i in range(20)]
    for key in ("temperature_2m", "apparent_temperature", "wind_speed_10m",
                "wind_gusts_10m", "precipitation_probability", "precipitation", "visibility"):
        payload["hourly"][key] = [1.0] * 20
    out = openmeteo.fetch(client := _FakeClient(payload=payload), cfg)
    assert len(out["hourly"]) == 12


def test_fetch_failure_returns_not_ok(cfg):
    client = _FakeClient(exc=RuntimeError("boom"))
    out = openmeteo.fetch(client, cfg)
    assert out["_ok"] is False
    assert out["hourly"] == []
