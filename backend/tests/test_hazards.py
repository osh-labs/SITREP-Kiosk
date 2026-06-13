"""
Tests for deterministic hazard flag computation (hazards.py).

Covers:
  - Heat danger band triggers and severity escalation
  - Severe weather leads the ranking
  - Winter weather detection
  - Thunderstorms detection
  - Rain detection
  - Wind detection
  - AQI callout (separate from ranked chain)
  - Empty data produces no hazards
  - Ranking order is D5 (severe > heat > winter > thunder > rain > wind)
  - No literals — all thresholds come from config
"""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_nws(
    heat_index_f=None,
    pop_pct=None,
    summary="Clear",
    alerts=None,
    gust_mph=None,
    temp_f=72.0,
    hourly_summaries=None,
):
    """Build a minimal fake NWS source dict."""
    wind = {"dir": "SW", "speed_mph": 5, "gust_mph": gust_mph}
    return {
        "weather_current": {"temp_f": temp_f, "feels_like_f": temp_f, "wind": wind, "summary": summary},
        "weather_today": {
            "high_f": 90, "low_f": 70, "heat_index_f": heat_index_f,
            "pop_pct": pop_pct, "pop_window": None, "daylight_until": "20:51",
            "summary": summary,
        },
        "forecast_days": [],
        "alerts": alerts or [],
        "raw_hourly": [
            {"shortForecast": s, "temperatureUnit": "F", "temperature": 88,
             "relativeHumidity": {"value": 60},
             "probabilityOfPrecipitation": {"value": 20}}
            for s in (hourly_summaries or [])
        ],
        "_ok": True,
    }


def make_alert(event, severity="advisory"):
    return {"text": event, "event": event, "severity": severity}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestHeatIndex:
    def test_no_heat_no_flag(self, config):
        from sitrep.hazards import compute_hazards
        nws = make_nws(heat_index_f=80.0)  # below extreme_caution (90)
        result = compute_hazards(nws, None, None, config)
        keys = [h.key for h in result.ranked]
        assert "heat_index" not in keys

    def test_extreme_caution_triggers(self, config):
        from sitrep.hazards import compute_hazards
        # exactly at extreme_caution threshold (90°F)
        threshold = config.heat_threshold("extreme_caution")
        nws = make_nws(heat_index_f=threshold)
        result = compute_hazards(nws, None, None, config)
        keys = [h.key for h in result.ranked]
        assert "heat_index" in keys

    def test_danger_band_severity(self, config):
        from sitrep.hazards import compute_hazards
        # danger band >= 103°F
        threshold = config.heat_threshold("danger")
        nws = make_nws(heat_index_f=threshold)
        result = compute_hazards(nws, None, None, config)
        heat_flag = next(h for h in result.ranked if h.key == "heat_index")
        assert heat_flag.severity == "danger"

    def test_extreme_danger_severity(self, config):
        from sitrep.hazards import compute_hazards
        threshold = config.heat_threshold("extreme_danger")
        nws = make_nws(heat_index_f=threshold)
        result = compute_hazards(nws, None, None, config)
        heat_flag = next(h for h in result.ranked if h.key == "heat_index")
        assert heat_flag.severity == "extreme"

    def test_heat_alert_escalates(self, config):
        from sitrep.hazards import compute_hazards
        # Even without a high heat index, an active Heat Advisory triggers the flag
        nws = make_nws(heat_index_f=85.0, alerts=[make_alert("Heat Advisory", "advisory")])
        result = compute_hazards(nws, None, None, config)
        keys = [h.key for h in result.ranked]
        assert "heat_index" in keys

    def test_caution_band_severity(self, config):
        from sitrep.hazards import compute_hazards
        # Between extreme_caution and danger -> caution severity
        lo = config.heat_threshold("extreme_caution")
        hi = config.heat_threshold("danger") - 1
        nws = make_nws(heat_index_f=(lo + hi) / 2)
        result = compute_hazards(nws, None, None, config)
        heat_flag = next((h for h in result.ranked if h.key == "heat_index"), None)
        assert heat_flag is not None
        assert heat_flag.severity == "caution"


class TestSevereWeather:
    def test_tornado_warning_leads(self, config):
        from sitrep.hazards import compute_hazards
        nws = make_nws(alerts=[make_alert("Tornado Warning", "extreme")])
        result = compute_hazards(nws, None, None, config)
        assert result.ranked[0].key == "severe_weather"

    def test_flash_flood_watch_triggers(self, config):
        from sitrep.hazards import compute_hazards
        nws = make_nws(alerts=[make_alert("Flash Flood Watch", "watch")])
        result = compute_hazards(nws, None, None, config)
        keys = [h.key for h in result.ranked]
        assert "severe_weather" in keys

    def test_spc_slight_triggers(self, config):
        from sitrep.hazards import compute_hazards
        spc = {
            "_ok": True,
            "day1": {"category": "slight", "label": "SPC Day 1 Slight", "in_risk_area": True},
            "day2": None, "day3": None,
            "highest_day": 1, "highest_category": "slight",
            "triggers_hazard": True,
        }
        nws = make_nws()
        result = compute_hazards(nws, spc, None, config)
        keys = [h.key for h in result.ranked]
        assert "severe_weather" in keys

    def test_spc_marginal_no_trigger(self, config):
        from sitrep.hazards import compute_hazards
        spc = {
            "_ok": True,
            "day1": {"category": "marginal", "label": "SPC Day 1 Marginal", "in_risk_area": True},
            "day2": None, "day3": None,
            "highest_day": 1, "highest_category": "marginal",
            "triggers_hazard": False,  # marginal < slight threshold
        }
        nws = make_nws()
        result = compute_hazards(nws, spc, None, config)
        keys = [h.key for h in result.ranked]
        assert "severe_weather" not in keys


class TestWinterWeather:
    def test_winter_alert_triggers(self, config):
        from sitrep.hazards import compute_hazards
        nws = make_nws(alerts=[make_alert("Winter Storm Warning", "danger")])
        result = compute_hazards(nws, None, None, config)
        keys = [h.key for h in result.ranked]
        assert "winter_weather" in keys

    def test_snow_in_summary_triggers(self, config):
        from sitrep.hazards import compute_hazards
        nws = make_nws(summary="Snow likely")
        result = compute_hazards(nws, None, None, config)
        keys = [h.key for h in result.ranked]
        assert "winter_weather" in keys

    def test_freezing_temp_with_precip_triggers(self, config):
        from sitrep.hazards import compute_hazards
        threshold = config.winter_temp_precip_threshold()
        nws = make_nws(temp_f=threshold - 1, pop_pct=40)
        result = compute_hazards(nws, None, None, config)
        keys = [h.key for h in result.ranked]
        assert "winter_weather" in keys

    def test_normal_cold_no_precip_no_trigger(self, config):
        from sitrep.hazards import compute_hazards
        nws = make_nws(temp_f=28.0, pop_pct=0)
        result = compute_hazards(nws, None, None, config)
        keys = [h.key for h in result.ranked]
        assert "winter_weather" not in keys


class TestThunderstorms:
    def test_thunder_in_summary_triggers(self, config):
        from sitrep.hazards import compute_hazards
        nws = make_nws(summary="Thunderstorm likely")
        result = compute_hazards(nws, None, None, config)
        keys = [h.key for h in result.ranked]
        assert "thunderstorms" in keys

    def test_thunder_in_hourly_triggers(self, config):
        from sitrep.hazards import compute_hazards
        nws = make_nws(hourly_summaries=["Partly cloudy", "Isolated Thunderstorms", "Clear"])
        result = compute_hazards(nws, None, None, config)
        keys = [h.key for h in result.ranked]
        assert "thunderstorms" in keys

    def test_no_thunder_no_flag(self, config):
        from sitrep.hazards import compute_hazards
        nws = make_nws(summary="Mostly cloudy", pop_pct=20)
        result = compute_hazards(nws, None, None, config)
        keys = [h.key for h in result.ranked]
        assert "thunderstorms" not in keys


class TestRain:
    def test_high_pop_triggers(self, config):
        from sitrep.hazards import compute_hazards
        threshold = config.rain_pop_threshold()
        nws = make_nws(pop_pct=threshold)
        result = compute_hazards(nws, None, None, config)
        keys = [h.key for h in result.ranked]
        assert "rain" in keys

    def test_low_pop_no_flag(self, config):
        from sitrep.hazards import compute_hazards
        threshold = config.rain_pop_threshold()
        nws = make_nws(pop_pct=threshold - 10)
        result = compute_hazards(nws, None, None, config)
        keys = [h.key for h in result.ranked]
        assert "rain" not in keys


class TestWind:
    def test_high_gust_triggers(self, config):
        from sitrep.hazards import compute_hazards
        threshold = config.wind_gust_threshold()
        nws = make_nws(gust_mph=threshold + 5)
        result = compute_hazards(nws, None, None, config)
        keys = [h.key for h in result.ranked]
        assert "wind" in keys

    def test_low_gust_no_flag(self, config):
        from sitrep.hazards import compute_hazards
        threshold = config.wind_gust_threshold()
        nws = make_nws(gust_mph=threshold - 5)
        result = compute_hazards(nws, None, None, config)
        keys = [h.key for h in result.ranked]
        assert "wind" not in keys

    def test_wind_advisory_triggers(self, config):
        from sitrep.hazards import compute_hazards
        nws = make_nws(alerts=[make_alert("Wind Advisory", "advisory")])
        result = compute_hazards(nws, None, None, config)
        keys = [h.key for h in result.ranked]
        assert "wind" in keys


class TestAqiCallout:
    def test_aqi_above_threshold_callout(self, config):
        from sitrep.hazards import compute_hazards
        threshold = config.aqi_threshold()
        airnow = {"aqi": int(threshold) + 5, "category": "Unhealthy for Sensitive Groups",
                  "label": "Code Orange", "_ok": True}
        result = compute_hazards(None, None, airnow, config)
        assert result.aqi_callout is not None
        assert result.aqi_callout.aqi == int(threshold) + 5

    def test_aqi_below_threshold_no_callout(self, config):
        from sitrep.hazards import compute_hazards
        threshold = config.aqi_threshold()
        airnow = {"aqi": int(threshold) - 5, "category": "Moderate",
                  "label": "Code Yellow", "_ok": True}
        result = compute_hazards(None, None, airnow, config)
        assert result.aqi_callout is None

    def test_aqi_not_in_ranked_chain(self, config):
        from sitrep.hazards import compute_hazards
        airnow = {"aqi": 150, "category": "Unhealthy", "label": "Code Red", "_ok": True}
        result = compute_hazards(None, None, airnow, config)
        # AQI must never appear in the ranked chain
        ranked_keys = [h.key for h in result.ranked]
        assert "aqi" not in ranked_keys
        assert "aqi_callout" not in ranked_keys


class TestRankingOrder:
    def test_severe_weather_leads_over_heat(self, config):
        from sitrep.hazards import compute_hazards
        # Both severe weather alert AND high heat index present
        nws = make_nws(
            heat_index_f=110.0,
            alerts=[make_alert("Tornado Warning", "extreme")]
        )
        result = compute_hazards(nws, None, None, config)
        assert result.ranked[0].key == "severe_weather"

    def test_heat_leads_over_thunderstorms(self, config):
        from sitrep.hazards import compute_hazards
        # High heat + thunderstorms in summary, but no severe alert
        threshold = config.heat_threshold("danger")
        nws = make_nws(heat_index_f=threshold, summary="Thunderstorms possible")
        result = compute_hazards(nws, None, None, config)
        # heat should come before thunderstorms
        ranked_keys = [h.key for h in result.ranked]
        assert "heat_index" in ranked_keys
        assert "thunderstorms" in ranked_keys
        hi = ranked_keys.index("heat_index")
        ts = ranked_keys.index("thunderstorms")
        assert hi < ts

    def test_rank_numbers_are_sequential(self, config):
        from sitrep.hazards import compute_hazards
        # Multiple hazards active
        threshold = config.rain_pop_threshold()
        nws = make_nws(pop_pct=threshold, gust_mph=config.wind_gust_threshold() + 5)
        result = compute_hazards(nws, None, None, config)
        for i, h in enumerate(result.ranked):
            assert h.rank == i + 1

    def test_no_data_no_hazards(self, config):
        from sitrep.hazards import compute_hazards
        result = compute_hazards(None, None, None, config)
        assert result.ranked == []
        assert result.aqi_callout is None
