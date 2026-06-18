"""
Tests for the data-driven briefing-regeneration signature in scheduler.py.

The briefing must only change when the underlying state changes materially
(new/cleared alert, ranked-hazard set or severity shift, AQI category change,
new/upgraded SPC outlook, or a morning/afternoon mode switch). An unchanged
signature means no LLM call.
"""
from __future__ import annotations

from sitrep.models import RankedHazard, AqiCallout, HazardsBlock
from sitrep.scheduler import _briefing_signature


def _hazards(ranked=None, aqi=None) -> HazardsBlock:
    return HazardsBlock(ranked=ranked or [], aqi_callout=aqi)


class TestBriefingSignatureStability:
    def test_identical_state_yields_identical_signature(self):
        nws = {"alerts": [{"event": "Heat Advisory", "severity": "advisory"}]}
        spc = {"_ok": True, "day1": {"category": "slight"}}
        haz = _hazards([RankedHazard("heat_index", 0, "Heat", "danger")])
        a = _briefing_signature(nws, spc, haz, "morning")
        b = _briefing_signature(nws, spc, haz, "morning")
        assert a == b

    def test_alert_order_does_not_matter(self):
        a1 = {"event": "Heat Advisory", "severity": "advisory"}
        a2 = {"event": "Wind Advisory", "severity": "advisory"}
        haz = _hazards()
        s1 = _briefing_signature({"alerts": [a1, a2]}, None, haz, "morning")
        s2 = _briefing_signature({"alerts": [a2, a1]}, None, haz, "morning")
        assert s1 == s2

    def test_empty_inputs_are_safe(self):
        sig = _briefing_signature(None, None, None, "afternoon")
        assert "mode=afternoon" in sig


class TestBriefingSignatureChanges:
    def test_new_alert_changes_signature(self):
        haz = _hazards()
        before = _briefing_signature({"alerts": []}, None, haz, "morning")
        after = _briefing_signature(
            {"alerts": [{"event": "Tornado Warning", "severity": "extreme"}]},
            None, haz, "morning",
        )
        assert before != after

    def test_hazard_severity_change_changes_signature(self):
        before = _briefing_signature(
            None, None, _hazards([RankedHazard("heat_index", 0, "Heat", "caution")]), "morning"
        )
        after = _briefing_signature(
            None, None, _hazards([RankedHazard("heat_index", 0, "Heat", "danger")]), "morning"
        )
        assert before != after

    def test_aqi_category_change_changes_signature(self):
        before = _briefing_signature(
            None, None, _hazards(aqi=AqiCallout(105, "Unhealthy for Sensitive Groups", "Code Orange")), "morning"
        )
        after = _briefing_signature(
            None, None, _hazards(aqi=AqiCallout(160, "Unhealthy", "Code Red")), "morning"
        )
        assert before != after

    def test_spc_outlook_upgrade_changes_signature(self):
        before = _briefing_signature(
            None, {"_ok": True, "day1": {"category": "marginal"}}, _hazards(), "morning"
        )
        after = _briefing_signature(
            None, {"_ok": True, "day1": {"category": "enhanced"}}, _hazards(), "morning"
        )
        assert before != after

    def test_mode_switch_changes_signature(self):
        haz = _hazards()
        assert _briefing_signature(None, None, haz, "morning") != _briefing_signature(None, None, haz, "afternoon")
