"""
Configuration loader for SITREP backend.

Loads YAML config + .env; provides typed access with sane defaults.
Config path: env SITREP_CONFIG -> config/config.yaml -> config/config.example.yaml
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

log = logging.getLogger(__name__)

# ── Repo root is three levels up from this file (backend/sitrep/config.py)
_REPO_ROOT = Path(__file__).resolve().parents[2]

# Load .env once at import time (does not override existing env vars)
load_dotenv(_REPO_ROOT / ".env", override=False)


def _config_path() -> Path:
    """Resolve config file: SITREP_CONFIG -> config/config.yaml -> config/config.example.yaml"""
    from_env = os.environ.get("SITREP_CONFIG")
    if from_env:
        p = Path(from_env)
        if p.exists():
            return p
        log.warning("SITREP_CONFIG=%s not found; falling back", from_env)

    primary = _REPO_ROOT / "config" / "config.yaml"
    if primary.exists():
        return primary

    fallback = _REPO_ROOT / "config" / "config.example.yaml"
    if fallback.exists():
        log.info("config/config.yaml not found; using config/config.example.yaml")
        return fallback

    raise FileNotFoundError("No config file found — copy config/config.example.yaml to config/config.yaml")


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base (returns new dict)."""
    result = dict(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


# ── Hard-coded defaults so the app works even with a minimal config ──────────
_DEFAULTS: dict[str, Any] = {
    "location": {
        "name": "Atlanta Metro",
        "lat": 33.7490,
        "lon": -84.3880,
    },
    "display": {
        "dwell_seconds": 12,
        "refresh_seconds": 30,
        "mode_windows": {"morning_until": "12:00"},
        "work_hours": {"start": "06:00", "end": "18:00"},
    },
    "weather": {
        "timezone": "America/New_York",
    },
    "weather_map": {
        "enabled": True,
        "center": {"lat": 33.7490, "lon": -84.3880},
        "default_zoom": 8,
        "min_zoom": 6,
        "max_zoom": 10,
        "base_style": "dark",
        "layers": {
            "radar": {"default_on": True, "opacity": 0.7},
            "alerts": {"default_on": True},
        },
        "animation": {
            "enabled": True,
            "frames": 8,
            "interval_ms": 600,
            "refresh_seconds": 300,
        },
    },
    "polling_seconds": {
        "nws": 900,
        "spc": 1800,
        "airnow": 1800,
        "ga511": 90,
        "openmeteo": 900,
        "briefing": 1800,
    },
    "staleness_seconds": {
        "default": 3600,
    },
    "hazard_thresholds": {
        "heat_index_f": {
            "extreme_caution": 90,
            "danger": 103,
            "extreme_danger": 125,
        },
        "thunderstorm_probability_pct": 30,
        "rain": {
            "pop_pct": 50,
            "qpf_in": 0.25,
        },
        "wind_gust_mph_flag": 30,
        "aqi_callout": 101,
        "winter": {
            "temp_f_with_precip": 32,
        },
    },
    "ranking_order": [
        "severe_weather",
        "heat_index",
        "winter_weather",
        "thunderstorms",
        "rain",
        "wind",
    ],
}


class Config:
    """Typed access to the merged YAML + defaults configuration."""

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    # ── top-level accessors ─────────────────────────────────────────────────

    @property
    def location(self) -> dict[str, Any]:
        return self._data["location"]

    @property
    def display(self) -> dict[str, Any]:
        return self._data["display"]

    @property
    def polling_seconds(self) -> dict[str, int]:
        return self._data["polling_seconds"]

    @property
    def staleness_seconds(self) -> dict[str, int]:
        return self._data["staleness_seconds"]

    @property
    def hazard_thresholds(self) -> dict[str, Any]:
        return self._data["hazard_thresholds"]

    @property
    def ranking_order(self) -> list[str]:
        return self._data["ranking_order"]

    # ── convenience getters ─────────────────────────────────────────────────

    @property
    def lat(self) -> float:
        return float(self.location["lat"])

    @property
    def lon(self) -> float:
        return float(self.location["lon"])

    @property
    def location_name(self) -> str:
        return str(self.location["name"])

    @property
    def dwell_seconds(self) -> int:
        return int(self.display.get("dwell_seconds", 12))

    @property
    def refresh_seconds(self) -> int:
        return int(self.display.get("refresh_seconds", 30))

    @property
    def morning_until(self) -> str:
        return self.display["mode_windows"].get("morning_until", "12:00")

    @property
    def work_start(self) -> str:
        return self.display["work_hours"].get("start", "06:00")

    @property
    def work_end(self) -> str:
        return self.display["work_hours"].get("end", "18:00")

    @property
    def staleness_default(self) -> int:
        return int(self.staleness_seconds.get("default", 3600))

    # ── hazard threshold shortcuts ───────────────────────────────────────────

    def heat_threshold(self, band: str) -> float:
        """band: 'extreme_caution' | 'danger' | 'extreme_danger'"""
        return float(self.hazard_thresholds["heat_index_f"][band])

    def thunderstorm_prob_threshold(self) -> float:
        return float(self.hazard_thresholds["thunderstorm_probability_pct"])

    def rain_pop_threshold(self) -> float:
        return float(self.hazard_thresholds["rain"]["pop_pct"])

    def rain_qpf_threshold(self) -> float:
        return float(self.hazard_thresholds["rain"]["qpf_in"])

    def wind_gust_threshold(self) -> float:
        return float(self.hazard_thresholds["wind_gust_mph_flag"])

    def aqi_threshold(self) -> float:
        return float(self.hazard_thresholds["aqi_callout"])

    def winter_temp_precip_threshold(self) -> float:
        return float(self.hazard_thresholds["winter"]["temp_f_with_precip"])

    def get(self, *keys: str, default: Any = None) -> Any:
        """Dot-path get from raw data, e.g. cfg.get('hazard_thresholds','rain','pop_pct')."""
        node: Any = self._data
        for k in keys:
            if not isinstance(node, dict):
                return default
            node = node.get(k, default)
        return node


# ── Module-level singleton + reload support ──────────────────────────────────

_cfg: Config | None = None


def load_config(force_reload: bool = False) -> Config:
    """Load (or reload) the config from disk. Thread-safe for reads after first load."""
    global _cfg
    if _cfg is None or force_reload:
        path = _config_path()
        log.info("Loading config from %s", path)
        with open(path) as fh:
            raw = yaml.safe_load(fh) or {}
        merged = _deep_merge(_DEFAULTS, raw)
        _cfg = Config(merged)
    return _cfg


def get_config() -> Config:
    """Return the loaded config, loading it on first call."""
    return load_config()
