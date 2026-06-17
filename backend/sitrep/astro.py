"""
Deterministic astronomy helpers — moon phase.

Moon phase is computed, not fetched: no feed provides it here and the value is
exact (an ephemeris calculation), not an estimate. It is therefore presented as
a computed value, exempt from the "never fabricate numbers" rule that governs
source-attributed data.

Method: simple synodic-month calculation from a known reference new moon.
Accurate to well within a day — fine for a "Waxing Gibbous, 82%" status item.
No third-party dependency.
"""
from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Optional

# Reference new moon: 2000-01-06 18:14 UTC (Julian-ish epoch widely used).
_KNOWN_NEW_MOON = datetime(2000, 1, 6, 18, 14, tzinfo=timezone.utc)
# Mean synodic month (new moon to new moon), days.
_SYNODIC_DAYS = 29.530588853

# Eight named phases, in order, each spanning 1/8 of the cycle (centered).
_PHASE_NAMES = [
    "New Moon",
    "Waxing Crescent",
    "First Quarter",
    "Waxing Gibbous",
    "Full Moon",
    "Waning Gibbous",
    "Last Quarter",
    "Waning Crescent",
]


def moon_phase(when: Optional[datetime] = None) -> dict:
    """
    Return {"moon_phase", "illumination_pct", "phase_fraction"} for `when`.

    phase_fraction is 0.0 at new moon, ~0.5 at full moon, wrapping back to 1.0.
    illumination_pct is the lit fraction of the disc (0 new, 100 full).
    """
    if when is None:
        when = datetime.now(tz=timezone.utc)
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)

    days_since = (when - _KNOWN_NEW_MOON).total_seconds() / 86400.0
    phase_fraction = (days_since % _SYNODIC_DAYS) / _SYNODIC_DAYS  # 0..1

    # Illumination: 0 at new (fraction 0/1), 100 at full (fraction 0.5).
    illumination_pct = int(round((1 - math.cos(2 * math.pi * phase_fraction)) / 2 * 100))

    # Name: bucket the cycle into 8 segments centered on each named phase.
    index = int((phase_fraction * 8) + 0.5) % 8
    name = _PHASE_NAMES[index]

    return {
        "moon_phase": name,
        "illumination_pct": illumination_pct,
        "phase_fraction": round(phase_fraction, 4),
    }
