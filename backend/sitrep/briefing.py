"""
M2: BLUF briefing generation.

Calls Anthropic SDK (claude-haiku-4-5) with the validated structured state
and ranked hazard flags in the analyst-brief voice.

HARD RULE: the model writes prose only and must NOT emit numeric values.
           Every figure shown on a slide binds to cached source data, not
           model text. The prompt instructs this explicitly.

Returns:
  {
    "bottom_line": str,
    "watch_for": [str, ...],
    "source": "model" | "template",
    "generated_at": str (ISO-8601),
    "sources": [str, ...],
  }

Fallback: if ANTHROPIC_API_KEY is absent, the call fails, or returns empty,
          a templated briefing is built from the ranked hazard flags.
          source is set to "template".
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

log = logging.getLogger(__name__)

_MODEL = "claude-haiku-4-5-20251001"

# ---------------------------------------------------------------------------
# Template fallback
# ---------------------------------------------------------------------------

_HAZARD_TEMPLATES: dict[str, dict[str, str]] = {
    "severe_weather": {
        "bottom_line": "Severe weather is the primary hazard today. Active alerts or elevated convective risk require heightened awareness before and during outdoor work.",
        "watch_for": "Active severe weather alert — follow shelter-in-place protocols until the threat clears",
    },
    "heat_index": {
        "bottom_line": "Heat is today's primary hazard. Apparent temperatures are in or approaching the danger band during work hours.",
        "watch_for": "High heat index during work hours — heat-illness risk, pace work, hydrate frequently",
    },
    "winter_weather": {
        "bottom_line": "Winter weather conditions are the primary concern. Ice or frozen precipitation create significant slip and traction hazards.",
        "watch_for": "Winter weather active — watch for ice, especially on bridges and overpasses",
    },
    "thunderstorms": {
        "bottom_line": "Thunderstorms are possible during work hours. Lightning risk warrants monitoring and a shelter plan.",
        "watch_for": "Thunderstorms possible — shelter plan ready; 30-30 rule applies",
    },
    "rain": {
        "bottom_line": "Rain is likely during work hours. Wet conditions create slip, mud, and visibility hazards.",
        "watch_for": "Rain expected — wet surfaces, reduced visibility, excavation/trench hazards",
    },
    "wind": {
        "bottom_line": "Wind is the primary hazard today. Elevated gusts affect aerial equipment and elevated work.",
        "watch_for": "Elevated winds — verify aerial lift and crane go/no-go against equipment wind limits",
    },
}

_NO_HAZARD_TEMPLATE = {
    "bottom_line": "No significant weather hazards are flagged for today. Conditions look routine for outdoor work.",
    "watch_for": "Monitor for afternoon convective development typical of the Atlanta area",
}


def _iso_now() -> str:
    return datetime.now(tz=timezone.utc).astimezone().isoformat(timespec="seconds")


def _build_template_briefing(
    ranked_hazards: list[dict],
    aqi_callout: Optional[dict],
    sources_used: list[str],
) -> dict[str, Any]:
    """Build a templated briefing from ranked hazards when the model is unavailable."""
    watch_list: list[str] = []
    bottom_line = ""

    if ranked_hazards:
        top = ranked_hazards[0]
        key = top.get("key", "")
        template = _HAZARD_TEMPLATES.get(key, {})
        bottom_line = template.get("bottom_line", f"Primary hazard: {top.get('label', key)}.")
        primary_watch = template.get("watch_for", top.get("label", ""))
        if primary_watch:
            watch_list.append(primary_watch)

        # Add remaining hazards to watch_for
        for h in ranked_hazards[1:]:
            hk = h.get("key", "")
            ht = _HAZARD_TEMPLATES.get(hk, {})
            w = ht.get("watch_for", h.get("label", hk))
            if w:
                watch_list.append(w)
    else:
        bottom_line = _NO_HAZARD_TEMPLATE["bottom_line"]
        watch_list.append(_NO_HAZARD_TEMPLATE["watch_for"])

    if aqi_callout:
        cat = aqi_callout.get("label", "Elevated AQI")
        watch_list.append(f"Air quality {cat} — pace sensitive crew members")

    return {
        "bottom_line": bottom_line,
        "watch_for": watch_list,
        "source": "template",
        "generated_at": _iso_now(),
        "sources": sources_used,
    }


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

def _build_prompt(state_summary: dict) -> str:
    """Build the analyst-brief prompt."""
    ranked = state_summary.get("ranked_hazards", [])
    aqi = state_summary.get("aqi_callout")
    alerts = state_summary.get("alerts", [])
    spc = state_summary.get("spc_outlook")
    mode = state_summary.get("mode", "morning")

    hazard_list = ""
    if ranked:
        hazard_list = "\n".join(f"  {i+1}. {h['key']} — {h['label']} (severity: {h['severity']})"
                                for i, h in enumerate(ranked))
    else:
        hazard_list = "  None flagged."

    aqi_line = ""
    if aqi:
        aqi_line = f"\nAir quality callout: {aqi['label']} ({aqi['category']})"

    alert_lines = ""
    if alerts:
        alert_lines = "\nActive NWS alerts:\n" + "\n".join(f"  - {a['event']}: {a['text']}" for a in alerts)

    spc_line = ""
    if spc:
        spc_line = f"\nSPC Day {spc.get('day', 1)} outlook: {spc.get('category', '')} risk"

    prompt = f"""You are writing the morning briefing for the Field SITREP Board, a hazard-forward situational awareness display for United Consulting field staff.

TIME OF DAY: {mode}

ACTIVE HAZARD FLAGS (ranked by priority):
{hazard_list}
{aqi_line}{alert_lines}{spc_line}

Write a short analyst's briefing in this structure:
1. A "bottom_line" sentence or two: lead with the primary hazard (or "no significant hazards" if none), summarize today's risk picture, then give one or two recommended actions. Assessment-driven, professional but not corporate or military. Measured tone.
2. A "watch_for" list of 2-4 bullet points (strings) — specific things the crew should watch for today. Field-relevant. Action-oriented.

CRITICAL RULE: Do NOT include any numbers, temperatures, percentages, wind speeds, AQI values, or any other numeric figures in your text. The board will display those figures directly from source data. Your text must be purely qualitative and descriptive.

Respond ONLY with valid JSON in this exact shape:
{{
  "bottom_line": "...",
  "watch_for": ["...", "...", "..."]
}}

No other text. No markdown. No explanation. Just the JSON object."""
    return prompt


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def generate_briefing(
    ranked_hazards: list[dict],
    aqi_callout: Optional[dict],
    alerts: list[dict],
    spc_outlook: Optional[dict],
    mode: str,
    sources_used: list[str],
) -> dict[str, Any]:
    """
    Generate the BLUF briefing.

    Tries Anthropic API first; falls back to template on any failure.
    Returns the contract-shaped dict.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")

    if not api_key:
        log.info("ANTHROPIC_API_KEY not set — using templated briefing")
        return _build_template_briefing(ranked_hazards, aqi_callout, sources_used)

    state_summary = {
        "ranked_hazards": ranked_hazards,
        "aqi_callout": aqi_callout,
        "alerts": alerts,
        "spc_outlook": spc_outlook,
        "mode": mode,
    }

    try:
        import anthropic  # lazy import — not required if no key
        # Bound the call: the SDK default timeout is minutes with retries, which
        # would stall the poll/initial-load thread. The board has a templated
        # fallback, so fail fast and use it rather than hang.
        client = anthropic.Anthropic(api_key=api_key, timeout=20.0, max_retries=1)
        prompt = _build_prompt(state_summary)

        message = client.messages.create(
            model=_MODEL,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )

        raw_text = message.content[0].text.strip()

        # Extract JSON from the response
        # Strip markdown code fences if present
        if raw_text.startswith("```"):
            lines = raw_text.splitlines()
            raw_text = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])

        data = json.loads(raw_text)
        bottom_line = data.get("bottom_line", "").strip()
        watch_for = data.get("watch_for", [])

        if not bottom_line:
            raise ValueError("model returned empty bottom_line")

        # Sanitize: ensure watch_for is a list of strings
        if not isinstance(watch_for, list):
            watch_for = [str(watch_for)]
        watch_for = [str(w).strip() for w in watch_for if w]

        log.info("Briefing generated by model (hazards: %d)", len(ranked_hazards))
        return {
            "bottom_line": bottom_line,
            "watch_for": watch_for,
            "source": "model",
            "generated_at": _iso_now(),
            "sources": sources_used,
        }

    except Exception as exc:
        log.warning("Briefing model call failed (%s) — falling back to template", exc)
        return _build_template_briefing(ranked_hazards, aqi_callout, sources_used)
