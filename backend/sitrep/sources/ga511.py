"""
511GA (Georgia 511) traffic events/alerts poller.

Auth:   GA511_API_KEY env var (developer key, register at 511ga.org)
Limit:  10 calls / 60 s — poll at ~90 s (config.polling_seconds.ga511)
Format: JSON events list

Returns normalized dict:
  {
    "traffic": [{"text": ..., "type": ..., "priority": int}, ...],  # sorted, worst first
    "alerts":  [{"text": ..., "event": ..., "severity": ...}, ...],
    "_ok": bool,
  }

Traffic events are ranked deterministically (see _priority) so the most
serious disruptions lead and minor ones fall to the bottom of the list.

Each fetch makes ONE call (events endpoint).  If no key is configured,
return a clean failure so demo mode / other sources are unaffected.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any

log = logging.getLogger(__name__)

# 511GA REST API base
_BASE_URL = "https://511ga.org/api/v2"

# Fallback road-classification patterns (overridable via config.traffic).
_DEFAULT_INTERSTATE_PATTERNS = [r"\bI[- ]?\d+\b", r"\binterstate\b"]
_DEFAULT_STATE_ROAD_PATTERNS = [
    r"\bUS[- ]?\d+\b",
    r"\bSR[- ]?\d+\b",
    r"\bGA[- ]?\d+\b",
    r"\bstate route\b",
    r"\bhwy\b",
    r"\bhighway\b",
]

# Road importance, highest first. Used both as the priority tier and as the
# tie-breaker within the "everything else" tail.
_ROAD_INTERSTATE = 2
_ROAD_STATE = 1
_ROAD_OTHER = 0


def _get_api_key() -> str | None:
    return os.environ.get("GA511_API_KEY") or None


def _compile(patterns: Any, fallback: list[str]) -> list[re.Pattern]:
    """Compile a list of case-insensitive regexes, falling back if unusable."""
    pats = patterns if isinstance(patterns, list) and patterns else fallback
    compiled: list[re.Pattern] = []
    for p in pats:
        try:
            compiled.append(re.compile(p, re.I))
        except re.error:
            log.warning("511GA: skipping invalid road pattern %r", p)
    return compiled


def _road_class(text: str, interstate: list[re.Pattern], state: list[re.Pattern]) -> int:
    """Grade a road by importance from its name/text. Interstate beats state."""
    if any(p.search(text) for p in interstate):
        return _ROAD_INTERSTATE
    if any(p.search(text) for p in state):
        return _ROAD_STATE
    return _ROAD_OTHER


def _priority(road_class: int, etype: str) -> int:
    """
    Deterministic traffic priority (higher = more important), per the ranked
    hierarchy: interstate closure > interstate accident > state-road closure >
    state-road accident > everything else. Within the tail, more important
    roads still float above local ones via the road-class tie-breaker.
    """
    is_closure = etype == "closure"
    is_accident = etype == "crash"
    if road_class == _ROAD_INTERSTATE and is_closure:
        return 50
    if road_class == _ROAD_INTERSTATE and is_accident:
        return 40
    if road_class == _ROAD_STATE and is_closure:
        return 30
    if road_class == _ROAD_STATE and is_accident:
        return 20
    return road_class  # 0–2: everything else, ordered by road importance


def _classify_event(event_type: str, subtype: str) -> str:
    """Map 511GA event/subtype to the board's traffic type vocab."""
    t = (event_type or "").lower()
    s = (subtype or "").lower()
    if "crash" in t or "accident" in t or "crash" in s:
        return "crash"
    if "construct" in t or "roadwork" in t or "construct" in s:
        return "construction"
    if "congestion" in t or "delay" in t or "slow" in s:
        return "congestion"
    if "closure" in t or "closed" in s:
        return "closure"
    if "incident" in t:
        return "incident"
    return "other"


def _event_to_text(event: dict) -> str:
    """Build a short human-readable traffic event text."""
    road = event.get("RoadwayName", "") or event.get("road", "") or ""
    direction = event.get("DirectionOfTravel", "") or event.get("direction", "") or ""
    location = event.get("LocationDescription", "") or event.get("location", "") or ""
    description = event.get("EventDescription", "") or event.get("description", "") or ""
    subtype = event.get("EventSubType", "") or event.get("subtype", "") or ""

    parts = []
    if road:
        parts.append(road)
    if direction:
        parts.append(direction)
    if location:
        parts.append(f"@ {location}")
    if not parts and description:
        return description[:120]

    summary = " ".join(parts)
    if subtype and subtype.lower() not in summary.lower():
        summary = f"{summary} — {subtype}"
    elif description:
        # Append a short snippet of description if it adds context
        desc_short = description[:80].rstrip()
        summary = f"{summary} — {desc_short}"

    return summary[:150]


def fetch(client: Any, config: Any) -> dict[str, Any]:
    """
    Fetch current events from 511GA.
    Returns {"traffic": [...], "alerts": [...], "_ok": bool}.
    """
    result: dict[str, Any] = {
        "traffic": [],
        "alerts": [],
        "_ok": False,
    }

    api_key = _get_api_key()
    if not api_key:
        log.info("GA511_API_KEY not set — skipping 511GA fetch")
        return result

    try:
        # Events endpoint: returns current incidents, construction, congestion
        url = f"{_BASE_URL}/get/event"
        params = {"key": api_key, "format": "json"}
        r = client.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
    except Exception as exc:
        log.warning("511GA events fetch failed: %s", exc)
        return result

    # The response may be a list or {"Events": [...]} depending on version
    if isinstance(data, list):
        events = data
    elif isinstance(data, dict):
        events = data.get("Events", data.get("events", []))
    else:
        events = []

    # Road-classification patterns (config-overridable).
    interstate_re = _compile(
        config.get("traffic", "interstate_patterns", default=None),
        _DEFAULT_INTERSTATE_PATTERNS,
    )
    state_re = _compile(
        config.get("traffic", "state_road_patterns", default=None),
        _DEFAULT_STATE_ROAD_PATTERNS,
    )

    traffic_items = []
    alert_items = []

    for ev in events:
        event_type = (ev.get("EventType", ev.get("type", "")) or "").strip()
        subtype = (ev.get("EventSubType", ev.get("subtype", "")) or "").strip()

        # Classify as traffic event or alert
        is_alert = "advisory" in event_type.lower() or "hazard" in event_type.lower()

        text = _event_to_text(ev)
        if not text:
            continue

        if is_alert:
            alert_items.append({
                "text": text,
                "event": event_type or subtype or "Traffic Alert",
                "severity": "advisory",
            })
        else:
            etype = _classify_event(event_type, subtype)
            road_class = _road_class(text, interstate_re, state_re)
            traffic_items.append({
                "text": text,
                "type": etype,
                "priority": _priority(road_class, etype),
            })

    # Worst disruptions lead; ties keep source order (stable sort).
    traffic_items.sort(key=lambda t: t["priority"], reverse=True)

    # Also try the alerts endpoint if available
    try:
        alert_url = f"{_BASE_URL}/get/alert"
        params = {"key": api_key, "format": "json"}
        r2 = client.get(alert_url, params=params, timeout=10)
        if r2.status_code == 200:
            adata = r2.json()
            if isinstance(adata, list):
                alerts_raw = adata
            elif isinstance(adata, dict):
                alerts_raw = adata.get("Alerts", adata.get("alerts", []))
            else:
                alerts_raw = []
            for a in alerts_raw:
                desc = a.get("Description", a.get("description", "")) or ""
                atype = a.get("AlertType", a.get("type", "Alert")) or "Alert"
                if desc:
                    alert_items.append({
                        "text": desc[:150],
                        "event": atype,
                        "severity": "advisory",
                    })
    except Exception:
        pass  # alerts endpoint is optional; silently skip

    result["traffic"] = traffic_items
    result["alerts"] = alert_items
    result["_ok"] = True
    return result
