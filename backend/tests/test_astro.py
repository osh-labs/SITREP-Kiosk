"""Tests for the deterministic moon-phase helper."""
from datetime import datetime, timezone

from sitrep import astro


def test_known_new_moon():
    # 2026-06-15 was a new moon — illumination near 0, phase name "New Moon".
    res = astro.moon_phase(datetime(2026, 6, 15, 6, 0, tzinfo=timezone.utc))
    assert res["moon_phase"] == "New Moon"
    assert res["illumination_pct"] <= 5


def test_known_full_moon():
    # ~2026-06-29 / 06-30 was a full moon — illumination near 100.
    res = astro.moon_phase(datetime(2026, 6, 29, 12, 0, tzinfo=timezone.utc))
    assert res["illumination_pct"] >= 95
    assert res["moon_phase"] == "Full Moon"


def test_illumination_bounds_and_keys():
    res = astro.moon_phase(datetime(2026, 6, 22, 0, 0, tzinfo=timezone.utc))
    assert set(res.keys()) == {"moon_phase", "illumination_pct", "phase_fraction"}
    assert 0 <= res["illumination_pct"] <= 100
    assert 0.0 <= res["phase_fraction"] <= 1.0
    assert res["moon_phase"] in astro._PHASE_NAMES


def test_naive_datetime_is_accepted():
    # Naive datetimes are treated as UTC, not rejected.
    res = astro.moon_phase(datetime(2026, 6, 15, 6, 0))
    assert res["moon_phase"] == "New Moon"
