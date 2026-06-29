"""
Dataclasses mirroring the STATE_CONTRACT.md consolidated state shape.

All .to_dict() methods produce the exact JSON keys/nesting the frontend expects.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


# ── Source freshness block ────────────────────────────────────────────────────

@dataclass
class SourceBlock:
    name: str
    ok: bool = True
    stale: bool = False
    fetched_at: Optional[str] = None
    age_seconds: Optional[int] = None
    last_good_at: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "ok": self.ok,
            "stale": self.stale,
            "fetched_at": self.fetched_at,
            "age_seconds": self.age_seconds,
            "last_good_at": self.last_good_at,
        }

    @staticmethod
    def empty(name: str) -> "SourceBlock":
        """A source that has never succeeded."""
        return SourceBlock(name=name, ok=False, stale=True,
                           fetched_at=None, age_seconds=None, last_good_at=None)


# ── Display ───────────────────────────────────────────────────────────────────

@dataclass
class DisplayBlock:
    mode: str = "morning"          # "morning" | "afternoon"
    dwell_seconds: int = 12
    refresh_seconds: int = 30

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "dwell_seconds": self.dwell_seconds,
            "refresh_seconds": self.refresh_seconds,
        }


# ── Location ──────────────────────────────────────────────────────────────────

@dataclass
class LocationBlock:
    name: str = "Atlanta Metro"
    lat: float = 33.749
    lon: float = -84.388

    def to_dict(self) -> dict:
        return {"name": self.name, "lat": self.lat, "lon": self.lon}


# ── Briefing ──────────────────────────────────────────────────────────────────

@dataclass
class BriefingBlock:
    bottom_line: str = ""
    watch_for: list[str] = field(default_factory=list)
    source: str = "template"        # "model" | "template"
    generated_at: Optional[str] = None
    sources: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "bottom_line": self.bottom_line,
            "watch_for": self.watch_for,
            "source": self.source,
            "generated_at": self.generated_at,
            "sources": self.sources,
        }


# ── Hazards ───────────────────────────────────────────────────────────────────

@dataclass
class RankedHazard:
    key: str
    rank: int
    label: str
    severity: str   # info | watch | advisory | caution | danger | extreme

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "rank": self.rank,
            "label": self.label,
            "severity": self.severity,
        }


@dataclass
class AqiCallout:
    aqi: int
    category: str
    label: str

    def to_dict(self) -> dict:
        return {"aqi": self.aqi, "category": self.category, "label": self.label}


@dataclass
class AirQuality:
    """Current air quality, surfaced whenever AirNow has data (not threshold-gated).

    The prominent hazard callout (HazardsBlock.aqi_callout) only appears above the
    config threshold; this block carries the reading at all levels so the status
    strip can always show it instead of "No data" on a clean-air day.
    """
    aqi: Optional[int] = None
    category: Optional[str] = None
    label: Optional[str] = None
    pollutant: Optional[str] = None
    source: Optional[SourceBlock] = None

    def to_dict(self) -> dict:
        return {
            "aqi": self.aqi,
            "category": self.category,
            "label": self.label,
            "pollutant": self.pollutant,
            "source": self.source.to_dict() if self.source else SourceBlock.empty("AirNow").to_dict(),
        }


@dataclass
class HazardsBlock:
    ranked: list[RankedHazard] = field(default_factory=list)
    aqi_callout: Optional[AqiCallout] = None

    def to_dict(self) -> dict:
        return {
            "ranked": [h.to_dict() for h in self.ranked],
            "aqi_callout": self.aqi_callout.to_dict() if self.aqi_callout else None,
        }


# ── Weather ───────────────────────────────────────────────────────────────────

@dataclass
class WindInfo:
    dir: Optional[str] = None
    speed_mph: Optional[float] = None
    gust_mph: Optional[float] = None

    def to_dict(self) -> dict:
        return {"dir": self.dir, "speed_mph": self.speed_mph, "gust_mph": self.gust_mph}


@dataclass
class CurrentConditions:
    temp_f: Optional[float] = None
    feels_like_f: Optional[float] = None
    wind: Optional[WindInfo] = None
    summary: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "temp_f": self.temp_f,
            "feels_like_f": self.feels_like_f,
            "wind": self.wind.to_dict() if self.wind else None,
            "summary": self.summary,
        }


@dataclass
class TodayForecast:
    high_f: Optional[float] = None
    low_f: Optional[float] = None
    heat_index_f: Optional[float] = None
    pop_pct: Optional[float] = None
    pop_window: Optional[str] = None
    daylight_until: Optional[str] = None
    summary: Optional[str] = None
    # Open-Meteo-sourced extras (sun.* + UV + visibility). NWS still supplies
    # high/low/heat index/pop above. See sources.openmeteo + STATE_CONTRACT.md.
    sunrise: Optional[str] = None
    sunset: Optional[str] = None
    uv_index: Optional[float] = None
    visibility_mi: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "high_f": self.high_f,
            "low_f": self.low_f,
            "heat_index_f": self.heat_index_f,
            "pop_pct": self.pop_pct,
            "pop_window": self.pop_window,
            "daylight_until": self.daylight_until,
            "summary": self.summary,
            "sunrise": self.sunrise,
            "sunset": self.sunset,
            "uv_index": self.uv_index,
            "visibility_mi": self.visibility_mi,
        }


@dataclass
class HourlyPoint:
    """One hour of the Open-Meteo forecast series (verbatim, unit-converted)."""
    time: str
    temp_f: Optional[float] = None
    feels_like_f: Optional[float] = None
    heat_index_f: Optional[float] = None
    wind_mph: Optional[float] = None
    gust_mph: Optional[float] = None
    pop_pct: Optional[float] = None
    precip_in: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "time": self.time,
            "temp_f": self.temp_f,
            "feels_like_f": self.feels_like_f,
            "heat_index_f": self.heat_index_f,
            "wind_mph": self.wind_mph,
            "gust_mph": self.gust_mph,
            "pop_pct": self.pop_pct,
            "precip_in": self.precip_in,
        }


@dataclass
class WeatherBlock:
    current: Optional[CurrentConditions] = None
    today: Optional[TodayForecast] = None
    hourly: list[HourlyPoint] = field(default_factory=list)
    source: Optional[SourceBlock] = None

    def to_dict(self) -> dict:
        return {
            "current": self.current.to_dict() if self.current else None,
            "today": self.today.to_dict() if self.today else None,
            "hourly": [h.to_dict() for h in self.hourly],
            "source": self.source.to_dict() if self.source else SourceBlock.empty("NWS FFC").to_dict(),
        }


# ── Commute ───────────────────────────────────────────────────────────────────

@dataclass
class CommuteCurrentConditions:
    temp_f: Optional[float] = None
    feels_like_f: Optional[float] = None
    summary: Optional[str] = None

    def to_dict(self) -> dict:
        return {"temp_f": self.temp_f, "feels_like_f": self.feels_like_f, "summary": self.summary}


@dataclass
class TrafficEvent:
    text: str
    type: str   # crash | congestion | construction | incident | closure | other
    priority: int = 0   # ranked importance; higher floats to the top of the list
    lat: Optional[float] = None
    lon: Optional[float] = None
    lat2: Optional[float] = None   # secondary point for extended events
    lon2: Optional[float] = None
    polyline: str = ""             # encoded polyline of the event extent

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "type": self.type,
            "priority": self.priority,
            "lat": self.lat,
            "lon": self.lon,
            "lat2": self.lat2,
            "lon2": self.lon2,
            "polyline": self.polyline,
        }


@dataclass
class CommuteBlock:
    current: Optional[CommuteCurrentConditions] = None
    traffic: list[TrafficEvent] = field(default_factory=list)
    source: Optional[SourceBlock] = None

    def to_dict(self) -> dict:
        return {
            "current": self.current.to_dict() if self.current else CommuteCurrentConditions().to_dict(),
            "traffic": [t.to_dict() for t in self.traffic],
            "source": self.source.to_dict() if self.source else SourceBlock.empty("NWS, 511GA").to_dict(),
        }


# ── Disruptions ───────────────────────────────────────────────────────────────

@dataclass
class AlertEvent:
    text: str
    event: str
    severity: str   # info | watch | advisory | caution | danger | extreme

    def to_dict(self) -> dict:
        return {"text": self.text, "event": self.event, "severity": self.severity}


@dataclass
class DisruptionsBlock:
    traffic: list[TrafficEvent] = field(default_factory=list)
    alerts: list[AlertEvent] = field(default_factory=list)
    source: Optional[SourceBlock] = None

    def to_dict(self) -> dict:
        return {
            "traffic": [t.to_dict() for t in self.traffic],
            "alerts": [a.to_dict() for a in self.alerts],
            "source": self.source.to_dict() if self.source else SourceBlock.empty("511GA, NWS").to_dict(),
        }


# ── 3-Day Forecast ────────────────────────────────────────────────────────────

@dataclass
class ForecastDay:
    name: str
    high_f: Optional[float] = None
    low_f: Optional[float] = None
    summary: Optional[str] = None
    icon: Optional[str] = None   # clear | cloud | rain | storm | snow | sleet

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "high_f": self.high_f,
            "low_f": self.low_f,
            "summary": self.summary,
            "icon": self.icon,
        }


@dataclass
class SpcOutlook:
    text: str
    category: str   # none | marginal | slight | enhanced | moderate | high
    day: int = 1

    def to_dict(self) -> dict:
        return {"text": self.text, "category": self.category, "day": self.day}


@dataclass
class Forecast3DayBlock:
    days: list[ForecastDay] = field(default_factory=list)
    spc_outlook: Optional[SpcOutlook] = None
    source: Optional[SourceBlock] = None

    def to_dict(self) -> dict:
        return {
            "days": [d.to_dict() for d in self.days],
            "spc_outlook": self.spc_outlook.to_dict() if self.spc_outlook else None,
            "source": self.source.to_dict() if self.source else SourceBlock.empty("NWS FFC, SPC").to_dict(),
        }


# ── Astro (computed, not source-attributed) ──────────────────────────────────

@dataclass
class AstroBlock:
    moon_phase: Optional[str] = None        # e.g. "Waxing Gibbous"
    illumination_pct: Optional[int] = None  # 0–100
    phase_fraction: Optional[float] = None  # 0.0–1.0 through the synodic cycle

    def to_dict(self) -> dict:
        return {
            "moon_phase": self.moon_phase,
            "illumination_pct": self.illumination_pct,
            "phase_fraction": self.phase_fraction,
        }


# ── Weather map (config surfaced for the frontend + freshness) ────────────────

@dataclass
class MapBlock:
    """Surfaces the `weather_map` config block plus a freshness SourceBlock.

    Tiles load directly in the browser; the authoritative warning shapes are
    served from /api/alerts.geojson. This block carries no image bytes.
    """
    config: dict = field(default_factory=dict)
    source: Optional[SourceBlock] = None

    def to_dict(self) -> dict:
        d = dict(self.config)
        d["source"] = self.source.to_dict() if self.source else SourceBlock.empty("Weather Map").to_dict()
        return d


# ── Sources summary map ───────────────────────────────────────────────────────

@dataclass
class SourcesMap:
    nws: SourceBlock = field(default_factory=lambda: SourceBlock.empty("NWS FFC"))
    spc: SourceBlock = field(default_factory=lambda: SourceBlock.empty("SPC"))
    ga511: SourceBlock = field(default_factory=lambda: SourceBlock.empty("511GA"))
    airnow: SourceBlock = field(default_factory=lambda: SourceBlock.empty("AirNow"))
    openmeteo: SourceBlock = field(default_factory=lambda: SourceBlock.empty("Open-Meteo"))
    weather_map: SourceBlock = field(default_factory=lambda: SourceBlock.empty("Weather Map"))

    def to_dict(self) -> dict:
        return {
            "nws": self.nws.to_dict(),
            "spc": self.spc.to_dict(),
            "ga511": self.ga511.to_dict(),
            "airnow": self.airnow.to_dict(),
            "openmeteo": self.openmeteo.to_dict(),
            "weather_map": self.weather_map.to_dict(),
        }


# ── Top-level consolidated state ──────────────────────────────────────────────

@dataclass
class ConsolidatedState:
    generated_at: str
    display: DisplayBlock = field(default_factory=DisplayBlock)
    location: LocationBlock = field(default_factory=LocationBlock)
    briefing: BriefingBlock = field(default_factory=BriefingBlock)
    hazards: HazardsBlock = field(default_factory=HazardsBlock)
    air_quality: AirQuality = field(default_factory=AirQuality)
    weather: WeatherBlock = field(default_factory=WeatherBlock)
    commute: CommuteBlock = field(default_factory=CommuteBlock)
    disruptions: DisruptionsBlock = field(default_factory=DisruptionsBlock)
    forecast_3day: Forecast3DayBlock = field(default_factory=Forecast3DayBlock)
    astro: AstroBlock = field(default_factory=AstroBlock)
    weather_map: MapBlock = field(default_factory=MapBlock)
    sources: SourcesMap = field(default_factory=SourcesMap)

    def to_dict(self) -> dict:
        return {
            "generated_at": self.generated_at,
            "display": self.display.to_dict(),
            "location": self.location.to_dict(),
            "briefing": self.briefing.to_dict(),
            "hazards": self.hazards.to_dict(),
            "air_quality": self.air_quality.to_dict(),
            "weather": self.weather.to_dict(),
            "commute": self.commute.to_dict(),
            "disruptions": self.disruptions.to_dict(),
            "forecast_3day": self.forecast_3day.to_dict(),
            "astro": self.astro.to_dict(),
            "weather_map": self.weather_map.to_dict(),
            "sources": self.sources.to_dict(),
        }
