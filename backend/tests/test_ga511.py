"""511GA traffic prioritization: ranked hierarchy and stable sort (no network)."""
import pytest

from sitrep.config import load_config
from sitrep.sources import ga511


def _cfg():
    return load_config(force_reload=True)


# ── unit: road classification + priority tiers ───────────────────────────────

def test_road_class_interstate_beats_state():
    inter = ga511._compile(None, ga511._DEFAULT_INTERSTATE_PATTERNS)
    state = ga511._compile(None, ga511._DEFAULT_STATE_ROAD_PATTERNS)
    assert ga511._road_class("I-285 SB @ Camp Creek", inter, state) == ga511._ROAD_INTERSTATE
    assert ga511._road_class("SR-400 NB ramp", inter, state) == ga511._ROAD_STATE
    assert ga511._road_class("US-78 @ Main St", inter, state) == ga511._ROAD_STATE
    assert ga511._road_class("Peachtree St @ 10th", inter, state) == ga511._ROAD_OTHER


def test_priority_follows_proposed_hierarchy():
    p = ga511._priority
    I, S, O = ga511._ROAD_INTERSTATE, ga511._ROAD_STATE, ga511._ROAD_OTHER
    # 1 > 2 > 3 > 4 > 5, all strictly descending
    interstate_closure = p(I, "closure")
    interstate_accident = p(I, "crash")
    state_closure = p(S, "closure")
    state_accident = p(S, "crash")
    minor = p(O, "construction")
    assert interstate_closure > interstate_accident > state_closure > state_accident > minor
    # within "everything else", a more important road still floats up
    assert p(I, "construction") > p(S, "construction") > p(O, "construction")


# ── integration: fetch sorts worst-first ─────────────────────────────────────

class _Resp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _Client:
    """Returns events on the /event endpoint, empty list on /alert."""
    def __init__(self, events):
        self._events = events

    def get(self, url, params=None, timeout=None):
        if url.endswith("/event"):
            return _Resp(self._events)
        return _Resp([])


def test_fetch_sorts_traffic_worst_first(monkeypatch):
    monkeypatch.setenv("GA511_API_KEY", "test-key")
    events = [
        {"RoadwayName": "Peachtree St", "EventType": "Congestion"},
        {"RoadwayName": "SR-400", "EventType": "Crash"},
        {"RoadwayName": "I-75", "EventType": "Closure"},
        {"RoadwayName": "US-78", "EventType": "Closure"},
        {"RoadwayName": "I-285", "EventType": "Crash"},
    ]
    out = ga511.fetch(_Client(events), _cfg())
    assert out["_ok"] is True
    roads = [t["text"].split()[0] for t in out["traffic"]]
    # I-75 closure, I-285 crash, US-78 closure, SR-400 crash, then the local street
    assert roads == ["I-75", "I-285", "US-78", "SR-400", "Peachtree"]
    # priorities are non-increasing
    prios = [t["priority"] for t in out["traffic"]]
    assert prios == sorted(prios, reverse=True)


def test_fetch_stable_within_same_priority(monkeypatch):
    monkeypatch.setenv("GA511_API_KEY", "test-key")
    events = [
        {"RoadwayName": "I-20", "EventType": "Closure", "LocationDescription": "exit 56"},
        {"RoadwayName": "I-85", "EventType": "Closure", "LocationDescription": "exit 90"},
    ]
    out = ga511.fetch(_Client(events), _cfg())
    # equal priority (both interstate closures) keeps source order
    assert [t["text"].split()[0] for t in out["traffic"]] == ["I-20", "I-85"]
