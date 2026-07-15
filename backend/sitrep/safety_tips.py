"""
Safety-tips selection for the revolving "Safety Tips" card.

The tips *content* is authored offline and checked into a YAML file
(`config/safety_tips.yaml`, with `config/safety_tips.example.yaml` as the
committed fallback). No language model runs at render time — this module only
loads the static list and decides which tips are eligible right now.

Eligibility is deterministic and driven by tags. A small set of *conditional*
tags gate a tip on live weather:

  - ``heat``      — shown only on hot days      (today high / heat index high)
  - ``cold``      — shown only on cold days     (today low low)
  - ``lightning`` — shown only when thunderstorms / severe are in play

Every other tag (``ppe``, ``driving``, ``site-hazard``, …) is descriptive and
never gates. A tip with no conditional tags is always eligible.

Thresholds live in config (``safety_tips.conditions``), not in this file, per the
project's "no literals in logic" rule. The frontend shuffles the eligible pool
and revolves through it on a timer; this module never randomizes so the state
stays deterministic.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

import yaml

log = logging.getLogger(__name__)

# Repo root is two levels up from backend/sitrep/safety_tips.py
_REPO_ROOT = Path(__file__).resolve().parents[2]

# Tags that gate a tip on live weather. Anything outside this set is descriptive
# (a category) and never restricts when a tip may appear. Keys line up with
# config.safety_tips.conditions.
_CONDITIONAL_TAGS = ("heat", "cold", "lightning")

# Storm categories from SPC that count as "lightning weather".
_STORM_SPC_CATEGORIES = {"general", "marginal", "slight", "enhanced", "moderate", "high"}

# Cache the parsed tips file so we don't re-read/parse it every rebuild.
_tips_cache: Optional[list[dict]] = None
_tips_cache_path: Optional[Path] = None


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def _resolve_tips_path(config: Any) -> Optional[Path]:
    """Resolve the tips file: configured path -> safety_tips.yaml -> example.

    A relative configured path is taken relative to the repo root so the same
    value works regardless of the process's working directory.
    """
    configured = config.get("safety_tips", "file", default=None)
    candidates: list[Path] = []
    if configured:
        p = Path(configured)
        candidates.append(p if p.is_absolute() else _REPO_ROOT / p)
    candidates.append(_REPO_ROOT / "config" / "safety_tips.yaml")
    candidates.append(_REPO_ROOT / "config" / "safety_tips.example.yaml")

    for cand in candidates:
        if cand.exists():
            return cand
    return None


def _normalize_tip(raw: Any, index: int) -> Optional[dict]:
    """Coerce one raw YAML entry into a {id, category, text, tags} dict.

    Returns None for entries with no usable text so a malformed line can't blank
    the card. Tags are lowercased for stable matching against the gate set.
    """
    if not isinstance(raw, dict):
        return None
    text = raw.get("text")
    if not text or not str(text).strip():
        return None
    tags = raw.get("tags") or []
    if isinstance(tags, str):
        tags = [tags]
    tags = [str(t).strip().lower() for t in tags if str(t).strip()]
    tip_id = raw.get("id") or raw.get("category") or f"tip-{index:03d}"
    return {
        "id": str(tip_id),
        "category": str(raw.get("category", "") or ""),
        "text": str(text).strip(),
        "tags": tags,
    }


def load_tips(config: Any, force_reload: bool = False) -> list[dict]:
    """Load and cache the normalized tip list. Empty list if none is available."""
    global _tips_cache, _tips_cache_path

    path = _resolve_tips_path(config)
    if path is None:
        if _tips_cache is None:
            log.info("No safety_tips file found; safety-tips card will be empty")
        _tips_cache, _tips_cache_path = [], None
        return _tips_cache

    if not force_reload and _tips_cache is not None and _tips_cache_path == path:
        return _tips_cache

    try:
        with open(path) as fh:
            raw = yaml.safe_load(fh) or {}
        raw_tips = raw.get("tips", []) if isinstance(raw, dict) else []
        tips: list[dict] = []
        for i, entry in enumerate(raw_tips):
            norm = _normalize_tip(entry, i)
            if norm:
                tips.append(norm)
        log.info("Loaded %d safety tip(s) from %s", len(tips), path)
        _tips_cache, _tips_cache_path = tips, path
    except Exception as exc:
        log.error("Failed to load safety tips from %s: %s", path, exc)
        _tips_cache, _tips_cache_path = [], path
    return _tips_cache


# ---------------------------------------------------------------------------
# Weather-gated eligibility
# ---------------------------------------------------------------------------

def _active_conditional_tags(
    nws_data: Optional[dict],
    spc_data: Optional[dict],
    hazards: Any,
    config: Any,
) -> set[str]:
    """Return the subset of conditional tags whose weather condition is active."""
    conditions = config.get("safety_tips", "conditions", default={}) or {}
    active: set[str] = set()

    today = (nws_data or {}).get("weather_today", {}) or {}
    current = (nws_data or {}).get("weather_current", {}) or {}

    # ── heat: hot day ────────────────────────────────────────────────────────
    heat_cfg = conditions.get("heat", {}) or {}
    heat_at = heat_cfg.get("high_f_at_or_above")
    if heat_at is not None:
        candidates = [today.get("high_f"), today.get("heat_index_f")]
        if any(v is not None and v >= float(heat_at) for v in candidates):
            active.add("heat")

    # ── cold: cold day ───────────────────────────────────────────────────────
    cold_cfg = conditions.get("cold", {}) or {}
    cold_at = cold_cfg.get("low_f_at_or_below")
    if cold_at is not None:
        candidates = [today.get("low_f"), current.get("temp_f"), current.get("feels_like_f")]
        if any(v is not None and v <= float(cold_at) for v in candidates):
            active.add("cold")

    # ── lightning: thunderstorms / severe in play ────────────────────────────
    if "lightning" in conditions and _lightning_active(nws_data, spc_data, hazards):
        active.add("lightning")

    return active


def _lightning_active(
    nws_data: Optional[dict],
    spc_data: Optional[dict],
    hazards: Any,
) -> bool:
    """True when there is a thunderstorm/severe signal in the current state.

    Reuses the deterministic hazard flags (thunderstorms / severe_weather),
    the SPC convective outlook, and the NWS forecast summary — no new thresholds.
    """
    # Ranked hazard flags already computed deterministically upstream.
    if hazards is not None:
        for h in getattr(hazards, "ranked", []) or []:
            if h.key in ("thunderstorms", "severe_weather"):
                return True

    # SPC convective outlook (any storm category on day 1).
    if spc_data and spc_data.get("_ok"):
        day1 = spc_data.get("day1") or {}
        if str(day1.get("category", "")).lower() in _STORM_SPC_CATEGORIES:
            return True

    # NWS forecast summary keywords.
    summary = ((nws_data or {}).get("weather_today", {}) or {}).get("summary", "") or ""
    s = summary.lower()
    if "thunder" in s or "t-storm" in s or "tstorm" in s:
        return True

    return False


def select_tips(
    nws_data: Optional[dict],
    spc_data: Optional[dict],
    hazards: Any,
    config: Any,
) -> dict:
    """Build the safety-tips block for the consolidated state.

    Returns ``{enabled, rotation_seconds, tips: [...]}``. ``tips`` is the pool of
    currently-eligible tips (conditional tags satisfied), capped to
    ``safety_tips.max_pool``. The frontend shuffles and revolves through it.
    """
    st_cfg = config.get("safety_tips", default={}) or {}
    enabled = bool(st_cfg.get("enabled", True))
    rotation_seconds = int(st_cfg.get("rotation_seconds", 15))
    max_pool = int(st_cfg.get("max_pool", 30))

    if not enabled:
        return {"enabled": False, "rotation_seconds": rotation_seconds, "tips": []}

    all_tips = load_tips(config)
    active = _active_conditional_tags(nws_data, spc_data, hazards, config)
    conditional_universe = set(_CONDITIONAL_TAGS)

    eligible: list[dict] = []
    for tip in all_tips:
        # A tip is eligible when every conditional tag it carries is active now.
        gating = set(tip["tags"]) & conditional_universe
        if gating <= active:
            eligible.append(tip)

    if max_pool > 0:
        eligible = eligible[:max_pool]

    return {
        "enabled": True,
        "rotation_seconds": rotation_seconds,
        "tips": eligible,
    }
