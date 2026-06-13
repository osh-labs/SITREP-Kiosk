"""
Tests for briefing.py — specifically the templated fallback.

No API keys are set (conftest.py ensures this), so all tests exercise
the template path. No network calls are made.
"""
from __future__ import annotations

import pytest


class TestTemplateFallback:
    def test_no_hazards_produces_text(self):
        from sitrep.briefing import generate_briefing
        result = generate_briefing(
            ranked_hazards=[],
            aqi_callout=None,
            alerts=[],
            spc_outlook=None,
            mode="morning",
            sources_used=["NWS FFC"],
        )
        assert result["source"] == "template"
        assert len(result["bottom_line"]) > 0
        assert isinstance(result["watch_for"], list)
        assert len(result["watch_for"]) > 0

    def test_heat_hazard_template(self):
        from sitrep.briefing import generate_briefing
        result = generate_briefing(
            ranked_hazards=[{
                "key": "heat_index",
                "rank": 1,
                "label": "Heat index to danger band",
                "severity": "danger",
            }],
            aqi_callout=None,
            alerts=[],
            spc_outlook=None,
            mode="morning",
            sources_used=["NWS FFC"],
        )
        assert result["source"] == "template"
        # Bottom line should reference heat
        assert "heat" in result["bottom_line"].lower()
        assert len(result["watch_for"]) >= 1

    def test_severe_weather_template(self):
        from sitrep.briefing import generate_briefing
        result = generate_briefing(
            ranked_hazards=[{
                "key": "severe_weather",
                "rank": 1,
                "label": "Tornado Warning",
                "severity": "extreme",
            }],
            aqi_callout=None,
            alerts=[],
            spc_outlook=None,
            mode="morning",
            sources_used=["NWS FFC", "SPC"],
        )
        assert result["source"] == "template"
        assert "severe" in result["bottom_line"].lower() or "weather" in result["bottom_line"].lower()

    def test_multiple_hazards_watch_for_list(self):
        from sitrep.briefing import generate_briefing
        result = generate_briefing(
            ranked_hazards=[
                {"key": "heat_index", "rank": 1, "label": "Heat index danger band", "severity": "danger"},
                {"key": "thunderstorms", "rank": 2, "label": "PM thunderstorms", "severity": "watch"},
            ],
            aqi_callout=None,
            alerts=[],
            spc_outlook=None,
            mode="morning",
            sources_used=["NWS FFC"],
        )
        # Should have at least 2 watch_for items (one per hazard)
        assert len(result["watch_for"]) >= 2

    def test_aqi_callout_added_to_watch_for(self):
        from sitrep.briefing import generate_briefing
        result = generate_briefing(
            ranked_hazards=[],
            aqi_callout={"aqi": 115, "category": "Unhealthy for Sensitive Groups", "label": "Code Orange"},
            alerts=[],
            spc_outlook=None,
            mode="morning",
            sources_used=["AirNow"],
        )
        # AQI should appear in watch_for
        combined = " ".join(result["watch_for"]).lower()
        assert "air" in combined or "aqi" in combined or "orange" in combined

    def test_generated_at_is_set(self):
        from sitrep.briefing import generate_briefing
        result = generate_briefing(
            ranked_hazards=[],
            aqi_callout=None,
            alerts=[],
            spc_outlook=None,
            mode="afternoon",
            sources_used=[],
        )
        assert result["generated_at"] is not None
        # ISO-8601 format check (rough)
        assert "T" in result["generated_at"]

    def test_sources_list_preserved(self):
        from sitrep.briefing import generate_briefing
        sources = ["NWS FFC", "SPC", "511GA"]
        result = generate_briefing(
            ranked_hazards=[],
            aqi_callout=None,
            alerts=[],
            spc_outlook=None,
            mode="morning",
            sources_used=sources,
        )
        assert result["sources"] == sources

    def test_template_source_when_no_key(self, monkeypatch):
        """Explicitly verify that missing ANTHROPIC_API_KEY uses template."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        from sitrep.briefing import generate_briefing
        result = generate_briefing(
            ranked_hazards=[{"key": "wind", "rank": 1, "label": "Wind Advisory", "severity": "advisory"}],
            aqi_callout=None,
            alerts=[],
            spc_outlook=None,
            mode="morning",
            sources_used=["NWS FFC"],
        )
        assert result["source"] == "template"
        assert "wind" in result["bottom_line"].lower() or "wind" in " ".join(result["watch_for"]).lower()
