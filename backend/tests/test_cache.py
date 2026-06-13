"""
Tests for the state cache (cache.py).

Covers:
  - Staleness computation (age > threshold -> stale=True)
  - Degraded state (ok=False when source has never succeeded)
  - Update and mark_failed behavior
  - age_seconds computation
"""
from __future__ import annotations

import time
from datetime import datetime, timezone, timedelta

import pytest


class TestSourceEntry:
    def test_empty_entry_is_not_ok(self):
        from sitrep.cache import SourceEntry
        e = SourceEntry("nws")
        assert e.ok is False
        assert e.data is None
        assert e.fetched_at is None

    def test_update_marks_ok(self):
        from sitrep.cache import SourceEntry
        e = SourceEntry("nws")
        e.update({"temp_f": 75})
        assert e.ok is True
        assert e.data == {"temp_f": 75}
        assert e.fetched_at is not None

    def test_mark_failed_preserves_data(self):
        from sitrep.cache import SourceEntry
        e = SourceEntry("nws")
        e.update({"temp_f": 75})
        e.mark_failed()
        # ok goes False but data is preserved
        assert e.ok is False
        assert e.data == {"temp_f": 75}

    def test_source_block_fresh(self):
        from sitrep.cache import SourceEntry
        e = SourceEntry("nws")
        e.update({"temp_f": 75})
        sb = e.to_source_block(staleness_seconds=3600)
        assert sb.ok is True
        assert sb.stale is False
        assert sb.age_seconds is not None
        assert sb.age_seconds < 5  # just updated

    def test_source_block_stale_when_old(self):
        """Manually backdate the fetched_at to simulate staleness."""
        from sitrep.cache import SourceEntry
        e = SourceEntry("nws")
        e.update({"temp_f": 75})
        # Backdate by 2 hours
        e.fetched_at = datetime.now(tz=timezone.utc) - timedelta(hours=2)
        sb = e.to_source_block(staleness_seconds=3600)
        assert sb.stale is True
        assert sb.age_seconds > 3600

    def test_source_block_empty_returns_not_ok(self):
        from sitrep.cache import SourceEntry
        e = SourceEntry("spc")
        sb = e.to_source_block(staleness_seconds=3600)
        assert sb.ok is False
        assert sb.stale is True
        assert sb.fetched_at is None
        assert sb.age_seconds is None


class TestStateCache:
    def test_get_data_none_before_update(self, fresh_cache):
        result = fresh_cache.get_data("nws")
        assert result is None

    def test_update_and_get_data(self, fresh_cache):
        fresh_cache.update("nws", {"temp_f": 78})
        data = fresh_cache.get_data("nws")
        assert data == {"temp_f": 78}

    def test_get_data_returns_deep_copy(self, fresh_cache):
        original = {"temp_f": 78, "nested": [1, 2, 3]}
        fresh_cache.update("nws", original)
        data = fresh_cache.get_data("nws")
        data["nested"].append(4)
        data2 = fresh_cache.get_data("nws")
        # Should not be affected
        assert len(data2["nested"]) == 3

    def test_mark_failed_unknown_source_noop(self, fresh_cache):
        # Should not raise
        fresh_cache.mark_failed("nonexistent_source")

    def test_get_source_block_unknown_returns_empty(self, fresh_cache):
        sb = fresh_cache.get_source_block("nonexistent")
        assert sb.ok is False

    def test_state_store_and_retrieve(self, fresh_cache):
        state = {"generated_at": "2026-06-13T06:42:00-04:00", "display": {"mode": "morning"}}
        fresh_cache.set_state(state)
        retrieved = fresh_cache.get_state()
        assert retrieved["display"]["mode"] == "morning"

    def test_state_returns_none_before_set(self, fresh_cache):
        assert fresh_cache.get_state() is None

    def test_is_source_ok_after_update(self, fresh_cache):
        fresh_cache.update("nws", {"temp_f": 78})
        assert fresh_cache.is_source_ok("nws") is True

    def test_is_source_ok_when_stale(self, fresh_cache):
        from datetime import datetime, timezone, timedelta
        fresh_cache.update("nws", {"temp_f": 78})
        # Backdate
        fresh_cache._entries["nws"].fetched_at = (
            datetime.now(tz=timezone.utc) - timedelta(hours=2)
        )
        assert fresh_cache.is_source_ok("nws") is False

    def test_is_source_ok_false_after_mark_failed(self, fresh_cache):
        fresh_cache.update("nws", {"temp_f": 78})
        fresh_cache.mark_failed("nws")
        # ok=False since last fetch failed
        sb = fresh_cache.get_source_block("nws")
        assert sb.ok is False

    def test_all_source_blocks_returns_four_sources(self, fresh_cache):
        blocks = fresh_cache.get_all_source_blocks()
        assert set(blocks.keys()) == {"nws", "spc", "ga511", "airnow"}

    def test_staleness_update(self, fresh_cache):
        fresh_cache.set_staleness(60)
        fresh_cache.update("nws", {"temp_f": 78})
        # Backdate by 2 minutes
        from datetime import datetime, timezone, timedelta
        fresh_cache._entries["nws"].fetched_at = (
            datetime.now(tz=timezone.utc) - timedelta(minutes=2)
        )
        sb = fresh_cache.get_source_block("nws")
        assert sb.stale is True
