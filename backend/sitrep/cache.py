"""
In-memory last-good store per source.

Each source stores its last-good normalized data dict + fetch timestamp.
Computes stale/age_seconds/ok per source against config staleness_seconds.

Thread-safety: a single threading.Lock guards all mutations. The cache is
designed for one writer (the scheduler) and many readers (the state builder
and any concurrent request handlers). Reads return shallow copies to avoid
races on the returned dict.
"""
from __future__ import annotations

import copy
import logging
import threading
from datetime import datetime, timezone
from typing import Any, Optional

from .models import SourceBlock

log = logging.getLogger(__name__)

# Canonical source keys
SOURCE_KEYS = ("nws", "spc", "ga511", "airnow")

# Human-readable display names
SOURCE_NAMES = {
    "nws": "NWS FFC",
    "spc": "SPC",
    "ga511": "511GA",
    "airnow": "AirNow",
}


class SourceEntry:
    """A single source's last-good record."""

    __slots__ = ("key", "data", "fetched_at", "ok")

    def __init__(self, key: str) -> None:
        self.key: str = key
        self.data: Optional[dict[str, Any]] = None
        self.fetched_at: Optional[datetime] = None
        self.ok: bool = False

    def update(self, data: dict[str, Any]) -> None:
        """Record a successful fetch."""
        self.data = copy.deepcopy(data)
        self.fetched_at = datetime.now(tz=timezone.utc)
        self.ok = True

    def mark_failed(self) -> None:
        """Record a fetch failure (preserves last-good data)."""
        self.ok = False

    def to_source_block(self, staleness_seconds: int) -> SourceBlock:
        """Compute freshness and return a SourceBlock."""
        name = SOURCE_NAMES.get(self.key, self.key)
        if self.data is None or self.fetched_at is None:
            return SourceBlock.empty(name)

        now = datetime.now(tz=timezone.utc)
        age = int((now - self.fetched_at).total_seconds())
        stale = age > staleness_seconds

        fetched_iso = self.fetched_at.astimezone().isoformat(timespec="seconds")
        return SourceBlock(
            name=name,
            ok=self.ok,
            stale=stale,
            fetched_at=fetched_iso,
            age_seconds=age,
            last_good_at=fetched_iso,
        )


class StateCache:
    """Central in-memory cache for all source data."""

    def __init__(self, staleness_seconds: int = 3600) -> None:
        self._staleness = staleness_seconds
        self._lock = threading.Lock()
        self._entries: dict[str, SourceEntry] = {
            key: SourceEntry(key) for key in SOURCE_KEYS
        }
        # Store the last fully-assembled consolidated state dict
        self._last_state: Optional[dict[str, Any]] = None

    # ── source write ─────────────────────────────────────────────────────────

    def update(self, source_key: str, data: dict[str, Any]) -> None:
        """Record a successful fetch for source_key."""
        with self._lock:
            entry = self._entries.get(source_key)
            if entry is None:
                log.warning("Unknown source key: %s", source_key)
                return
            entry.update(data)
            log.debug("Cache updated: %s", source_key)

    def mark_failed(self, source_key: str) -> None:
        """Record that a fetch failed for source_key."""
        with self._lock:
            entry = self._entries.get(source_key)
            if entry:
                entry.mark_failed()
                log.debug("Cache marked failed: %s", source_key)

    # ── source read ──────────────────────────────────────────────────────────

    def get_data(self, source_key: str) -> Optional[dict[str, Any]]:
        """Return a deep copy of the last-good data for source_key, or None."""
        with self._lock:
            entry = self._entries.get(source_key)
            if entry and entry.data is not None:
                return copy.deepcopy(entry.data)
            return None

    def get_source_block(self, source_key: str) -> SourceBlock:
        """Return freshness metadata as a SourceBlock."""
        with self._lock:
            entry = self._entries.get(source_key)
            if entry is None:
                return SourceBlock.empty(SOURCE_NAMES.get(source_key, source_key))
            return entry.to_source_block(self._staleness)

    def get_all_source_blocks(self) -> dict[str, SourceBlock]:
        """Return freshness SourceBlocks for all sources."""
        with self._lock:
            return {
                key: entry.to_source_block(self._staleness)
                for key, entry in self._entries.items()
            }

    def is_source_ok(self, source_key: str) -> bool:
        """True if source has data and is not stale."""
        sb = self.get_source_block(source_key)
        return sb.ok and not sb.stale

    # ── consolidated state store ──────────────────────────────────────────────

    def set_state(self, state_dict: dict[str, Any]) -> None:
        """Store the latest assembled consolidated state."""
        with self._lock:
            self._last_state = copy.deepcopy(state_dict)

    def get_state(self) -> Optional[dict[str, Any]]:
        """Return a deep copy of the last assembled state, or None."""
        with self._lock:
            if self._last_state is not None:
                return copy.deepcopy(self._last_state)
            return None

    # ── staleness config reload ───────────────────────────────────────────────

    def set_staleness(self, seconds: int) -> None:
        with self._lock:
            self._staleness = seconds


# Module-level singleton
_cache: StateCache | None = None


def get_cache() -> StateCache:
    global _cache
    if _cache is None:
        from .config import get_config
        cfg = get_config()
        _cache = StateCache(staleness_seconds=cfg.staleness_default)
    return _cache
