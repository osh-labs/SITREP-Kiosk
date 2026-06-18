"""State builder: Open-Meteo merge must not overwrite NWS-authoritative numbers."""
from sitrep import state_builder
from sitrep.cache import StateCache
from sitrep.config import load_config
from sitrep.models import HazardsBlock


def _cfg():
    return load_config(force_reload=True)


def _nws_data():
    return {
        "weather_current": {
            "temp_f": 78, "feels_like_f": 82,
            "wind": {"dir": "SW", "speed_mph": 6, "gust_mph": None},
            "summary": "Partly cloudy",
        },
        "weather_today": {
            "high_f": 96, "low_f": 75, "heat_index_f": 104,
            "pop_pct": 40, "pop_window": "after 2 PM",
            "daylight_until": "20:51", "summary": "PM storms",
        },
        "forecast_days": [],
        "alerts": [],
        "_ok": True,
    }


def _openmeteo_data():
    return {
        "hourly": [
            {"time": "2026-06-13T07:00", "temp_f": 79.0, "feels_like_f": 83.0,
             "wind_mph": 6.0, "gust_mph": 12.0, "pop_pct": 10, "precip_in": 0.0},
            {"time": "2026-06-13T08:00", "temp_f": 81.0, "feels_like_f": 85.0,
             "wind_mph": 7.0, "gust_mph": 14.0, "pop_pct": 20, "precip_in": 0.0},
        ],
        "today": {"sunrise": "2026-06-13T06:27", "sunset": "2026-06-13T20:51",
                  "uv_index": 8.3, "visibility_mi": 10.0},
        "_ok": True,
    }


def test_build_state_merges_openmeteo_without_clobbering_nws():
    cache = StateCache(staleness_seconds=3600)
    cache.update("nws", _nws_data())
    cache.update("openmeteo", _openmeteo_data())

    state = state_builder.build_state(
        nws_data=_nws_data(),
        spc_data=None,
        ga511_data=None,
        airnow_data=None,
        hazards=HazardsBlock(),
        briefing=None,
        cache=cache,
        config=_cfg(),
        openmeteo_data=_openmeteo_data(),
    ).to_dict()

    today = state["weather"]["today"]
    # NWS-authoritative numbers preserved
    assert today["high_f"] == 96
    assert today["heat_index_f"] == 104
    assert today["pop_pct"] == 40
    # Open-Meteo extras merged in
    assert today["sunrise"] == "2026-06-13T06:27"
    assert today["uv_index"] == 8.3
    assert today["visibility_mi"] == 10.0
    # Hourly series present, current conditions from NWS
    assert len(state["weather"]["hourly"]) == 2
    assert state["weather"]["current"]["temp_f"] == 78
    # Computed astro + map config present
    assert state["astro"]["moon_phase"] is not None
    assert state["weather_map"]["enabled"] is True
    assert state["sources"]["openmeteo"]["ok"] is True


def test_build_state_without_openmeteo_is_safe():
    cache = StateCache(staleness_seconds=3600)
    cache.update("nws", _nws_data())
    state = state_builder.build_state(
        nws_data=_nws_data(), spc_data=None, ga511_data=None, airnow_data=None,
        hazards=HazardsBlock(), briefing=None, cache=cache, config=_cfg(),
    ).to_dict()
    assert state["weather"]["hourly"] == []
    assert state["weather"]["today"]["sunrise"] is None


def test_traffic_events_sorts_and_caps():
    ga511_data = {
        "traffic": [
            {"text": "Local St", "type": "construction", "priority": 0},
            {"text": "I-75 NB", "type": "closure", "priority": 50},
            {"text": "SR-400", "type": "crash", "priority": 20},
        ],
    }
    # worst first, capped to 2
    items = state_builder._traffic_events(ga511_data, max_events=2)
    assert [t.text for t in items] == ["I-75 NB", "SR-400"]
    # max_events None / 0 keeps the full (sorted) list
    assert len(state_builder._traffic_events(ga511_data, None)) == 3
    assert len(state_builder._traffic_events(ga511_data, 0)) == 3
