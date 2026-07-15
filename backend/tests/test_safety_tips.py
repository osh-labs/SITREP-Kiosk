"""
Tests for safety-tips selection (safety_tips.py).

Covers:
  - Tips load + normalize from a YAML file (tags lowercased, bad rows dropped)
  - Untagged / descriptive-tag tips are always eligible
  - heat-tagged tips gate on a hot day (config threshold, no literals)
  - cold-tagged tips gate on a cold day
  - lightning-tagged tips gate on thunderstorm/severe signals (flags/SPC/forecast)
  - enabled: false / missing file degrade to an empty pool (card hides)
  - max_pool caps the eligible pool
"""
from __future__ import annotations

import textwrap

import pytest

from sitrep import safety_tips
from sitrep.config import load_config
from sitrep.models import HazardsBlock, RankedHazard


TIPS_YAML = textwrap.dedent("""
    tips:
      - id: general-01
        category: communication
        text: "Tell someone your route before heading out."
        tags: [communication]
      - id: heat-01
        category: heat
        text: "Drink water before you're thirsty."
        tags: [HEAT]          # upper-case on purpose — loader lowercases
      - id: cold-01
        category: cold
        text: "Layer up so you can shed as you warm."
        tags: [cold]
      - id: lightning-01
        category: lightning
        text: "When thunder rolls, head for hard cover."
        tags: [lightning]
      - id: bad-01              # no text — must be dropped
        category: broken
        tags: [ppe]
""")


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    """Real config, but point the tips loader at a controlled temp file."""
    tips_file = tmp_path / "safety_tips.yaml"
    tips_file.write_text(TIPS_YAML)
    monkeypatch.setattr(safety_tips, "_resolve_tips_path", lambda _cfg: tips_file)
    safety_tips.load_tips(load_config(force_reload=True), force_reload=True)
    return load_config(force_reload=True)


def _nws(high_f=75, low_f=60, heat_index_f=None, temp_f=68, summary="Clear"):
    return {
        "weather_current": {"temp_f": temp_f, "feels_like_f": temp_f},
        "weather_today": {
            "high_f": high_f, "low_f": low_f,
            "heat_index_f": heat_index_f, "summary": summary,
        },
        "_ok": True,
    }


def _ids(block):
    return {t["id"] for t in block["tips"]}


# ── Loading / normalization ──────────────────────────────────────────────────

def test_bad_rows_dropped_and_tags_lowercased(cfg):
    tips = safety_tips.load_tips(cfg, force_reload=True)
    ids = {t["id"] for t in tips}
    assert "bad-01" not in ids                     # textless row dropped
    heat = next(t for t in tips if t["id"] == "heat-01")
    assert heat["tags"] == ["heat"]                # lowercased


# ── Eligibility gating ───────────────────────────────────────────────────────

def test_mild_day_only_untagged_tip(cfg):
    """Mild, dry day: no conditional tags active → only the descriptive tip."""
    block = safety_tips.select_tips(_nws(high_f=72, low_f=55), None, HazardsBlock(), cfg)
    assert _ids(block) == {"general-01"}


def test_hot_day_includes_heat_tip(cfg):
    block = safety_tips.select_tips(_nws(high_f=96, low_f=75), None, HazardsBlock(), cfg)
    assert "heat-01" in _ids(block)
    assert "cold-01" not in _ids(block)
    assert "lightning-01" not in _ids(block)


def test_heat_index_alone_triggers_heat(cfg):
    """A modest air temp but a high heat index still counts as a hot day."""
    block = safety_tips.select_tips(
        _nws(high_f=84, low_f=70, heat_index_f=92), None, HazardsBlock(), cfg)
    assert "heat-01" in _ids(block)


def test_cold_day_includes_cold_tip(cfg):
    block = safety_tips.select_tips(_nws(high_f=45, low_f=28, temp_f=30), None, HazardsBlock(), cfg)
    assert "cold-01" in _ids(block)
    assert "heat-01" not in _ids(block)


def test_lightning_from_hazard_flag(cfg):
    hazards = HazardsBlock(ranked=[
        RankedHazard(key="thunderstorms", rank=1, label="PM storms", severity="watch"),
    ])
    block = safety_tips.select_tips(_nws(high_f=80, low_f=65), None, hazards, cfg)
    assert "lightning-01" in _ids(block)


def test_lightning_from_forecast_summary(cfg):
    block = safety_tips.select_tips(
        _nws(high_f=80, low_f=65, summary="Scattered thunderstorms"), None, HazardsBlock(), cfg)
    assert "lightning-01" in _ids(block)


def test_lightning_from_spc_outlook(cfg):
    spc = {"_ok": True, "day1": {"category": "slight"}}
    block = safety_tips.select_tips(_nws(high_f=80, low_f=65), spc, HazardsBlock(), cfg)
    assert "lightning-01" in _ids(block)


# ── Degraded / disabled behavior ─────────────────────────────────────────────

def test_disabled_returns_empty_pool(tmp_path, monkeypatch):
    tips_file = tmp_path / "safety_tips.yaml"
    tips_file.write_text(TIPS_YAML)
    monkeypatch.setattr(safety_tips, "_resolve_tips_path", lambda _cfg: tips_file)
    cfg = load_config(force_reload=True)
    cfg._data["safety_tips"]["enabled"] = False
    block = safety_tips.select_tips(_nws(), None, HazardsBlock(), cfg)
    assert block["enabled"] is False
    assert block["tips"] == []


def test_missing_file_is_safe(monkeypatch):
    monkeypatch.setattr(safety_tips, "_resolve_tips_path", lambda _cfg: None)
    cfg = load_config(force_reload=True)
    block = safety_tips.select_tips(_nws(high_f=96, low_f=75), None, HazardsBlock(), cfg)
    assert block["enabled"] is True
    assert block["tips"] == []


def test_max_pool_caps_eligible(cfg):
    cfg._data["safety_tips"]["max_pool"] = 1
    block = safety_tips.select_tips(_nws(high_f=96, low_f=75), None, HazardsBlock(), cfg)
    assert len(block["tips"]) == 1
