/* =========================================================================
   Field SITREP Board — app.js
   Plain vanilla JS, no build step, no framework. MapLibre GL JS is the only
   library (vendored locally). Fetches /api/state (or a local fixture for dev) and
   renders ONE unified situational dashboard (no carousel).

   Dev fixture usage:  ?fixture=morning | afternoon | degraded
   ========================================================================= */

'use strict';

/* ── Constants ──────────────────────────────────────────────────────────── */
const DEFAULT_REFRESH_S = 30;
const API_ENDPOINT      = '/api/state';
const ALERTS_ENDPOINT   = '/api/alerts.geojson';
const TEMPS_ENDPOINT    = '/api/temps.geojson';

/* app.js now uses MapLibre GL JS (vector tiles) instead of Leaflet. */

/* Severity metadata — icon shape + label so color is never the only cue */
const SEV_META = {
  info:     { icon: 'ℹ',  label: 'INFO',     cls: 'sev-info'     },
  watch:    { icon: '◉',  label: 'WATCH',    cls: 'sev-watch'    },
  advisory: { icon: '⚑',  label: 'ADVISORY', cls: 'sev-advisory' },
  caution:  { icon: '⚠',  label: 'CAUTION',  cls: 'sev-caution'  },
  danger:   { icon: '▲',  label: 'DANGER',   cls: 'sev-danger'   },
  extreme:  { icon: '◆',  label: 'EXTREME',  cls: 'sev-extreme'  },
};

/* Overall-risk label derived deterministically from the top ranked hazard.
   Reuses the severity palette classes — icon + label + color, never color alone. */
const RISK_FROM_SEVERITY = {
  info:     { label: 'LOW',      cls: 'sev-info'     },
  watch:    { label: 'GUARDED',  cls: 'sev-watch'    },
  advisory: { label: 'ELEVATED', cls: 'sev-advisory' },
  caution:  { label: 'MODERATE', cls: 'sev-caution'  },
  danger:   { label: 'HIGH',     cls: 'sev-danger'   },
  extreme:  { label: 'SEVERE',   cls: 'sev-extreme'  },
};

/* Traffic/alert event icons — shape reinforces meaning beyond color */
const EVENT_ICONS = {
  crash:        '✖',
  incident:     '⚠',
  construction: '⚒',
  congestion:   '≡',
  default:      '●',
};

/* Traffic incident pin metadata — icon + color by event type */
const TRAFFIC_PIN_META = {
  crash:        { icon: '✖', color: '#ef5350', label: 'Crash'        },
  incident:     { icon: '⚠', color: '#ed7a2f', label: 'Incident'     },
  construction: { icon: '⚒', color: '#e6b800', label: 'Construction' },
  congestion:   { icon: '≡', color: '#f59e0b', label: 'Congestion'   },
  closure:      { icon: '⊘', color: '#c0392b', label: 'Closure'      },
  other:        { icon: '●', color: '#6b7280', label: 'Other'        },
};

/* Atlanta metro bounding box [SW, NE] for the traffic map view.
   North edge sits at the GA/TN/NC state line (~35°N); covers all of
   metro Atlanta and the surrounding counties field crews operate in. */
const ATLANTA_METRO_BOUNDS = [[-85.2, 33.25], [-83.8, 35.0]];

/* Weather icon SVGs — inline, no network dependency */
const WEATHER_ICONS = {
  storm: `<svg viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" focusable="false">
    <ellipse cx="24" cy="20" rx="12" ry="9" fill="#8a97a6"/>
    <ellipse cx="18" cy="23" rx="8" ry="6" fill="#aab4c0"/>
    <polygon points="22,28 18,36 23,33 19,42 28,31 23,34" fill="#fbbf24"/>
  </svg>`,
  clear: `<svg viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" focusable="false">
    <circle cx="24" cy="24" r="9" fill="#fbbf24"/>
    <g stroke="#fbbf24" stroke-width="2.5" stroke-linecap="round">
      <line x1="24" y1="6" x2="24" y2="11"/>
      <line x1="24" y1="37" x2="24" y2="42"/>
      <line x1="6" y1="24" x2="11" y2="24"/>
      <line x1="37" y1="24" x2="42" y2="24"/>
      <line x1="11.5" y1="11.5" x2="15" y2="15"/>
      <line x1="33" y1="33" x2="36.5" y2="36.5"/>
      <line x1="36.5" y1="11.5" x2="33" y2="15"/>
      <line x1="15" y1="33" x2="11.5" y2="36.5"/>
    </g>
  </svg>`,
  rain: `<svg viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" focusable="false">
    <ellipse cx="24" cy="18" rx="13" ry="9" fill="#8a97a6"/>
    <ellipse cx="17" cy="21" rx="8" ry="6" fill="#aab4c0"/>
    <g stroke="#4aa3ff" stroke-width="2" stroke-linecap="round">
      <line x1="17" y1="30" x2="15" y2="38"/>
      <line x1="24" y1="30" x2="22" y2="38"/>
      <line x1="31" y1="30" x2="29" y2="38"/>
    </g>
  </svg>`,
  cloudy: `<svg viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" focusable="false">
    <ellipse cx="24" cy="22" rx="13" ry="9" fill="#8a97a6"/>
    <ellipse cx="16" cy="25" rx="8" ry="6" fill="#aab4c0"/>
    <ellipse cx="32" cy="26" rx="7" ry="5" fill="#aab4c0"/>
  </svg>`,
  snow: `<svg viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" focusable="false">
    <ellipse cx="24" cy="18" rx="13" ry="9" fill="#aab4c0"/>
    <g stroke="#9ad8ff" stroke-width="2" stroke-linecap="round">
      <line x1="16" y1="30" x2="16" y2="38"/>
      <line x1="12" y1="34" x2="20" y2="34"/>
      <line x1="24" y1="30" x2="24" y2="38"/>
      <line x1="20" y1="34" x2="28" y2="34"/>
      <line x1="32" y1="30" x2="32" y2="38"/>
      <line x1="28" y1="34" x2="36" y2="34"/>
    </g>
  </svg>`,
  wind: `<svg viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" focusable="false">
    <g stroke="#aab4c0" stroke-width="2.5" stroke-linecap="round">
      <path d="M8 18 Q28 14 36 18 Q42 21 38 24 Q34 27 30 22" fill="none"/>
      <path d="M8 24 Q24 21 32 24" fill="none"/>
      <path d="M8 30 Q20 27 28 30 Q34 33 30 36 Q27 38 24 34" fill="none"/>
    </g>
  </svg>`,
  unknown: `<svg viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" focusable="false">
    <circle cx="24" cy="24" r="16" stroke="#8a97a6" stroke-width="2"/>
    <text x="24" y="30" text-anchor="middle" font-size="18" fill="#aab4c0">?</text>
  </svg>`,
};

/* SPC category label map */
const SPC_LABELS = {
  general:  'General Thunder',
  marginal: 'Marginal Risk',
  slight:   'Slight Risk',
  enhanced: 'Enhanced Risk',
  moderate: 'Moderate Risk',
  high:     'High Risk',
};

/* CARTO / OSM base tile choices (keyless) */
/* OpenFreeMap vector tile style URLs — no API key required.
   Mapped from the base_style config names used by the Leaflet era. */
const VECTOR_STYLES = {
  dark:          'https://tiles.openfreemap.org/styles/dark',
  dark_nolabels: 'https://tiles.openfreemap.org/styles/dark',
  voyager:       'https://tiles.openfreemap.org/styles/liberty',
  light:         'https://tiles.openfreemap.org/styles/positron',
  osm:           'https://tiles.openfreemap.org/styles/liberty',
};

/* IEM NEXRAD N0Q composite radar tiles (keyless). offset 0 = most recent. */
function radarTileUrl(offsetMin) {
  const suffix = offsetMin > 0 ? `-m${String(offsetMin).padStart(2, '0')}m` : '';
  return `https://mesonet.agron.iastate.edu/cache/tile.py/1.0.0/nexrad-n0q-900913${suffix}/{z}/{x}/{y}.png`;
}

/* Decode a Google-encoded polyline string into GeoJSON [lon, lat] pairs. */
function decodePolyline(encoded) {
  if (!encoded) return [];
  const coords = [];
  let i = 0, lat = 0, lng = 0;
  while (i < encoded.length) {
    let b, shift = 0, result = 0;
    do { b = encoded.charCodeAt(i++) - 63; result |= (b & 0x1f) << shift; shift += 5; } while (b >= 0x20);
    lat += (result & 1) ? ~(result >> 1) : (result >> 1);
    shift = 0; result = 0;
    do { b = encoded.charCodeAt(i++) - 63; result |= (b & 0x1f) << shift; shift += 5; } while (b >= 0x20);
    lng += (result & 1) ? ~(result >> 1) : (result >> 1);
    coords.push([lng / 1e5, lat / 1e5]); // GeoJSON order: [lon, lat]
  }
  return coords;
}

/* ── State ──────────────────────────────────────────────────────────────── */
let currentState  = null;
let fetchTimer    = null;
let clockTimer    = null;
let reconnecting  = false;

/* Map state (created once, then refreshed in place) */
let map           = null;
let mapStyleLoaded = false;
let tempMarkers   = [];    // maplibregl.Marker instances for the temps view
let trafficMarkers = [];   // maplibregl.Marker instances for the traffic view
let radarFrameCount = 0;   // how many radar sources/layers are currently added
let radarTimer    = null;
let radarIdx      = 0;
let radarBuiltAt  = 0;     // epoch ms when frames last rebuilt
let mapInited     = false;
let mapCfg        = {};    // last weather_map config (for rotation handlers)
let mapMode       = null;  // active rotation view: 'radar' | 'alerts' | 'temps'
let mapModes      = [];    // ordered rotation views from config
let rotationTimer = null;
let alertPopup    = null;  // reusable popup for alert hover tooltips

/* ── DOM refs ────────────────────────────────────────────────────────────── */
const $loading   = document.getElementById('loading-screen');
const $errorScr  = document.getElementById('error-screen');
const $errorDet  = document.getElementById('error-detail');
const $app        = document.getElementById('app');
const $loc        = document.getElementById('header-location');
const $modeBadge  = document.getElementById('header-mode-badge');
const $datetime   = document.getElementById('header-datetime');
const $statusBar  = document.getElementById('status-bar');
const $statusTxt  = document.getElementById('status-text');
const $risk       = document.getElementById('overall-risk');
const $nextUpdate = document.getElementById('next-update');
const $summary    = document.getElementById('card-summary');
const $hazards    = document.getElementById('card-hazards');
const $activity   = document.getElementById('card-activity');
const $mapDegraded = document.getElementById('map-degraded');
const $chartTemp  = document.getElementById('card-chart-temp');
const $forecast   = document.getElementById('card-forecast');
const $strip      = document.getElementById('status-strip');

/* ── Utilities ───────────────────────────────────────────────────────────── */

/** Escape HTML entities to prevent XSS from data fields */
function esc(str) {
  if (str == null) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/** Render a value or an em-dash if null/undefined */
function val(v, suffix = '') {
  if (v == null) return '<span class="em-dash">&mdash;</span>';
  return esc(String(v)) + (suffix ? esc(suffix) : '');
}

/* All time display is locked to Eastern time (America/New_York) so the board
   shows the correct local time regardless of the server/OS timezone. Intl
   handles EDT/EST transitions automatically. */
const DISPLAY_TZ = 'America/New_York';

/** Extract named date/time parts for a Date in the display timezone. */
function tzParts(date, opts) {
  return new Intl.DateTimeFormat('en-US', { timeZone: DISPLAY_TZ, ...opts })
    .formatToParts(date)
    .reduce((acc, p) => { acc[p.type] = p.value; return acc; }, {});
}

/** HH:MM string (24-hour, Eastern) for a Date. */
function tzHHMM(date) {
  const p = tzParts(date, { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });
  return `${p.hour}:${p.minute}`;
}

/** YYYY-MM-DD string (Eastern) for same-day comparisons. */
function tzDateKey(date) {
  const p = tzParts(date, { year: 'numeric', month: '2-digit', day: '2-digit' });
  return `${p.year}-${p.month}-${p.day}`;
}

/** Format an ISO-8601 timestamp as HH:MM (same day) or "Mon D HH:MM" in Eastern time. */
function fmtTime(isoStr) {
  if (!isoStr) return '&mdash;';
  try {
    const d = new Date(isoStr);
    if (tzDateKey(d) === tzDateKey(new Date())) return tzHHMM(d);
    const p = tzParts(d, { month: 'short', day: 'numeric' });
    return `${p.month} ${p.day} ${tzHHMM(d)}`;
  } catch (e) {
    return esc(isoStr);
  }
}

/** Short HH:MM (Eastern) from an ISO timestamp (used for sunrise/sunset, chart ticks). */
function hhmm(isoStr) {
  if (!isoStr) return null;
  try { return tzHHMM(new Date(isoStr)); } catch (e) { return null; }
}

/** Human-readable age string from age_seconds or last_good_at. */
function humanAge(src) {
  let secs = src.age_seconds;
  if (secs == null && src.last_good_at) {
    secs = Math.floor((Date.now() - new Date(src.last_good_at).getTime()) / 1000);
  }
  if (secs == null) return 'unknown age';
  if (secs < 120)   return 'just now';
  if (secs < 3600)  return `about ${Math.round(secs / 60)} min ago`;
  const hrs = Math.round(secs / 3600);
  return `about ${hrs} hr${hrs !== 1 ? 's' : ''} ago`;
}

function lastGoodTime(src) {
  return src.last_good_at ? fmtTime(src.last_good_at) : '&mdash;';
}

/** "Source · Updated TIME" footer line for a source block */
function sourceFooter(src) {
  if (!src) return '';
  if (!src.ok || src.stale) {
    return `${esc(src.name || '')} &middot; last good ${lastGoodTime(src)}`;
  }
  return `${esc(src.name || '')} &middot; Updated ${fmtTime(src.fetched_at)}`;
}

/** Severity chip (color + icon + label text — never color alone) */
function sevChip(severity, extraText = '') {
  const m = SEV_META[severity] || SEV_META.info;
  const extra = extraText ? ` ${esc(extraText)}` : '';
  return `<span class="severity-chip ${m.cls}" aria-label="${m.label}${extraText ? ': ' + extraText : ''}">
    <i class="chip-icon" aria-hidden="true">${m.icon}</i>${m.label}${extra}
  </span>`;
}

/** Degraded-state banner for a section whose source is stale/down. */
function degradedBanner(src) {
  const timeStr = src.last_good_at ? `${fmtTime(src.last_good_at)}` : '&mdash;';
  const ageStr  = humanAge(src);
  return `<div class="degraded-banner" role="alert" aria-live="polite">
    <i class="dg-icon" aria-hidden="true">&#9888;</i>
    <div class="dg-text">
      Data as of ${timeStr} (${ageStr}) &mdash; source is down or stale.
      <span class="dg-note">Verify current conditions before you rely on this data.</span>
    </div>
  </div>`;
}

/** Determine if a source block is degraded (stale or not ok) */
function isDegraded(src) {
  if (!src) return false;
  return src.stale === true || src.ok === false;
}

/** Card title bar */
function cardTitle(text) {
  return `<div class="card-head"><h2 class="card-title">${esc(text)}</h2></div>`;
}

/** Card footer (source attribution) */
function cardFooter(src) {
  if (!src) return '';
  return `<div class="card-foot">${sourceFooter(src)}</div>`;
}

/** Weather icon key from a forecast/condition string */
function weatherIconKey(iconStr) {
  if (!iconStr) return 'unknown';
  const s = String(iconStr).toLowerCase();
  if (s.includes('storm') || s.includes('thunder')) return 'storm';
  if (s.includes('clear') || s.includes('sunny'))   return 'clear';
  if (s.includes('rain')  || s.includes('shower'))  return 'rain';
  if (s.includes('snow')  || s.includes('winter'))  return 'snow';
  if (s.includes('cloud') || s.includes('overcast')) return 'cloudy';
  if (s.includes('wind'))                            return 'wind';
  if (WEATHER_ICONS[s]) return s;
  return 'unknown';
}

/* ── Region renderers ─────────────────────────────────────────────────────── */

function renderHeader(state) {
  const loc  = (state.location || {}).name || 'Field Location';
  const mode = (state.display  || {}).mode || 'morning';
  $loc.textContent = loc;
  $modeBadge.className = `header-mode-badge ${mode}`;
  $modeBadge.textContent = mode === 'afternoon' ? 'Afternoon' : 'Morning';
  $app.classList.toggle('mode-morning', mode !== 'afternoon');
  $app.classList.toggle('mode-afternoon', mode === 'afternoon');
  applyModeLayout(mode);
}

/**
 * Place the Hazards and activity (Disruptions/PM Commute) cards into columns by
 * mode. Morning: Hazards leads the left column, Disruptions sits in the right.
 * Afternoon: they switch — PM Commute leads the left column (with more room for
 * traffic, 60/40 vs. Briefing via CSS), Hazards moves to the right.
 * Reparenting moves the existing nodes; the map and other cards are untouched.
 */
function applyModeLayout(mode) {
  const left = document.querySelector('.dash-col-left');
  const right = document.querySelector('.dash-col-right');
  if (!left || !right) return;
  if (mode === 'afternoon') {
    left.appendChild($activity);
    left.appendChild($summary);
    right.appendChild($chartTemp);
    right.appendChild($hazards);
    right.appendChild($forecast);
  } else {
    left.appendChild($hazards);
    left.appendChild($summary);
    right.appendChild($chartTemp);
    right.appendChild($activity);
    right.appendChild($forecast);
  }
}

function renderOverallRisk(state) {
  const ranked = ((state.hazards || {}).ranked) || [];
  const sev = ranked.length ? ranked[0].severity : 'info';
  const r = RISK_FROM_SEVERITY[sev] || RISK_FROM_SEVERITY.info;
  const m = SEV_META[sev] || SEV_META.info;
  $risk.className = `risk-badge ${r.cls}`;
  $risk.innerHTML = `<i aria-hidden="true">${m.icon}</i>${r.label}`;
}

function renderNextUpdate(state) {
  const refresh = ((state.display || {}).refresh_seconds) || DEFAULT_REFRESH_S;
  const next = new Date(Date.now() + refresh * 1000);
  $nextUpdate.textContent = `Next ~${tzHHMM(next)}`;
}

function renderSummary(state) {
  const b = state.briefing || {};
  const bottom = b.bottom_line
    ? `<p class="briefing-bottom-line">${esc(b.bottom_line)}</p>`
    : `<p class="briefing-bottom-line no-data-placeholder">Briefing not available.</p>`;
  const watch = Array.isArray(b.watch_for) && b.watch_for.length
    ? b.watch_for.map(i => `<li>${esc(i)}</li>`).join('')
    : '<li class="em-dash">No specific watch items.</li>';
  const srcName = Array.isArray(b.sources) && b.sources.length
    ? b.sources.join(', ') : (b.source === 'model' ? 'Model' : 'Template');
  const updated = b.generated_at ? fmtTime(b.generated_at) : '&mdash;';

  $summary.innerHTML = `
    ${cardTitle('Briefing')}
    <div class="card-body">
      ${bottom}
      <div class="briefing-label">Watch for</div>
      <ul class="watch-for-list" aria-label="Watch-for items">${watch}</ul>
    </div>
    <div class="card-foot">${esc(srcName)} &middot; ${esc(b.source || 'template')} &middot; Updated ${updated}</div>`;
}

function renderHazards(state) {
  const h = state.hazards || {};
  const ranked = Array.isArray(h.ranked) ? h.ranked : [];
  const aqi = h.aqi_callout || null;
  const src = (state.sources || {}).nws || (state.weather || {}).source || {};

  let flags;
  if (ranked.length === 0) {
    flags = `<div class="no-data-placeholder">No ranked hazards. Conditions nominal.</div>`;
  } else {
    flags = ranked.map(f => {
      const m = SEV_META[f.severity] || SEV_META.info;
      return `<div class="hazard-flag ${m.cls}" role="listitem"
                   aria-label="Hazard rank ${f.rank}: ${esc(f.label)}, severity ${f.severity}">
        <span class="flag-rank" aria-hidden="true">${f.rank}</span>
        <i aria-hidden="true">${m.icon}</i>
        <span class="flag-text">${esc(f.label)}</span>
        <span class="flag-sev">${m.label}</span>
      </div>`;
    }).join('');
    flags = `<div class="hazard-flags" role="list" aria-label="Ranked hazards">${flags}</div>`;
  }

  const aqiHtml = aqi
    ? `<div class="aqi-callout" role="note" aria-label="Air quality: ${esc(aqi.label)}, AQI ${aqi.aqi}">
        <i aria-hidden="true">&#9680;</i><strong>AQI ${val(aqi.aqi)}</strong> &mdash; ${esc(aqi.label)} &mdash; ${esc(aqi.category)}
      </div>` : '';
  const deg = isDegraded(src) ? degradedBanner(src) : '';

  $hazards.innerHTML = `
    ${cardTitle('Hazards')}
    <div class="card-body">${deg}${flags}${aqiHtml}</div>
    ${cardFooter(src)}`;
}

/** Render a traffic/alert event list item */
function eventItem(ev, sev) {
  if (sev) {
    const m = SEV_META[sev] || SEV_META.info;
    return `<li class="event-item alert-${sev}" role="listitem" aria-label="${m.label}: ${esc(ev.text)}">
      <span class="event-icon" aria-hidden="true">${m.icon}</span>
      <span class="event-text">${esc(ev.text)}</span>
      <span class="event-type-badge">${m.label}</span></li>`;
  }
  const type = (ev.type || 'default').toLowerCase();
  const icon = EVENT_ICONS[type] || EVENT_ICONS.default;
  const badge = type !== 'default' ? `<span class="event-type-badge">${esc(type.toUpperCase())}</span>` : '';
  return `<li class="event-item ${esc(type)}" role="listitem">
    <span class="event-icon" aria-hidden="true">${icon}</span>
    <span class="event-text">${esc(ev.text)}</span>${badge}</li>`;
}

/**
 * Adaptive activity card: Disruptions & Alerts in the morning, PM Commute in the
 * afternoon. Both blocks are always present in state; the mode picks one.
 */
function renderActivity(state) {
  const mode = (state.display || {}).mode || 'morning';

  if (mode === 'afternoon') {
    const c = state.commute || {};
    const cur = c.current || {};
    const traffic = Array.isArray(c.traffic) ? c.traffic : [];
    const src = c.source || {};
    const deg = isDegraded(src) ? degradedBanner(src) : '';
    const now = `<div class="commute-now">
      <span class="commute-temp">${val(cur.temp_f, '°')}</span>
      <span class="commute-feels">feels ${val(cur.feels_like_f, '°')}</span>
      ${cur.summary ? `<span class="commute-sum">${esc(cur.summary)}</span>` : ''}</div>`;
    const list = traffic.length
      ? `<ul class="event-list">${traffic.map(ev => eventItem(ev)).join('')}</ul>`
      : `<div class="no-data-placeholder">No reported traffic events.</div>`;
    $activity.innerHTML = `${cardTitle('PM Commute')}<div class="card-body">${deg}${now}${list}</div>${cardFooter(src)}`;
    return;
  }

  const d = state.disruptions || {};
  const traffic = Array.isArray(d.traffic) ? d.traffic : [];
  const alerts = Array.isArray(d.alerts) ? d.alerts : [];
  const src = d.source || {};
  const deg = isDegraded(src) ? degradedBanner(src) : '';
  const tList = traffic.length
    ? `<ul class="event-list">${traffic.map(ev => eventItem(ev)).join('')}</ul>`
    : `<div class="no-data-placeholder">No reported traffic events.</div>`;
  const aList = alerts.length
    ? `<ul class="event-list">${alerts.map(a => eventItem(a, alertSeverityFromProps(a))).join('')}</ul>`
    : `<div class="no-data-placeholder">No active NWS alerts.</div>`;
  $activity.innerHTML = `${cardTitle('Disruptions & Alerts')}
    <div class="card-body">${deg}
      <div class="sub-label">Traffic (511GA)</div>${tList}
      <div class="sub-label">Alerts (NWS)</div>${aList}
    </div>${cardFooter(src)}`;
}

/* ── Temperature / heat-index chart ───────────────────────────────────────── */

/** Map a numeric series to "x,y x,y …" polyline points within a viewBox. */
function chartPoints(values, w, h, pad, minV, maxV) {
  const n = values.length;
  if (n < 2) return '';
  const span = (maxV - minV) || 1;
  return values.map((v, i) => {
    const x = pad + (i / (n - 1)) * (w - 2 * pad);
    const y = (h - pad) - ((v - minV) / span) * (h - 2 * pad);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');
}

function renderTempChart(state) {
  const w = state.weather || {};
  const hours = (Array.isArray(w.hourly) ? w.hourly : []).slice(0, 12);
  const src = (state.sources || {}).openmeteo || {};
  const temps = hours.map(h => h.temp_f).filter(v => v != null);
  // Feels-like (apparent temp): heat index when hot, wind chill when cold. Unlike
  // the bare heat index — which equals air temp below 80°F and so overlaps the
  // temp line in mild weather — this stays distinct and informative year-round.
  const heat  = hours.map(h => h.feels_like_f).filter(v => v != null);

  if (temps.length < 2) {
    $chartTemp.innerHTML = `${cardTitle('Temperature & Feels-Like')}<div class="card-body"><div class="no-data-placeholder">&mdash;</div></div>`;
    return;
  }
  const W = 320, H = 120, PAD = 18;
  const all = temps.concat(heat);
  const minV = Math.min(...all) - 2, maxV = Math.max(...all) + 2;
  const span = (maxV - minV) || 1;
  const tPts = chartPoints(hours.map(h => h.temp_f != null ? h.temp_f : minV), W, H, PAD, minV, maxV);
  const hPts = chartPoints(hours.map(h => h.feels_like_f != null ? h.feels_like_f : (h.temp_f != null ? h.temp_f : minV)), W, H, PAD, minV, maxV);

  // Horizontal gridlines at every 10°F. SVG uses preserveAspectRatio="none" so
  // text inside the SVG would distort; labels go in the axis div instead.
  const GRID_STEP = 10;
  const gridStart = Math.ceil(minV / GRID_STEP) * GRID_STEP;
  const gridTemps = [];
  let gridSvg = '';
  for (let t = gridStart; t <= maxV; t += GRID_STEP) {
    const y = (H - PAD) - ((t - minV) / span) * (H - 2 * PAD);
    gridSvg += `<line x1="${PAD}" y1="${y.toFixed(1)}" x2="${W - PAD}" y2="${y.toFixed(1)}" class="chart-grid-line"/>`;
    gridTemps.push(Math.round(t));
  }
  // Y-axis labels: list gridline temps high→low so they read top-to-bottom.
  const axisLabels = gridTemps.slice().reverse().map(t => `<span>${t}°</span>`).join('');

  // X-axis ticks: first label is always "Now", middle and end show the hour.
  const tickIdxs = [0, Math.floor(hours.length / 2), hours.length - 1];
  const ticks = tickIdxs.map((i, pos) => {
    const label = pos === 0 ? 'Now' : esc(hhmm(hours[i].time) || '');
    return `<span>${label}</span>`;
  }).join('');

  $chartTemp.innerHTML = `
    ${cardTitle('Temperature & Feels-Like')}
    <div class="card-body chart-body">
      <div class="chart-with-axis">
        <div class="chart-y-axis">${axisLabels}</div>
        <div class="chart-svg-col">
          <svg class="spark" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" aria-hidden="true">
            ${gridSvg}
            <polyline points="${hPts}" class="spark-line spark-heat"/>
            <polyline points="${tPts}" class="spark-line spark-temp"/>
          </svg>
          <div class="chart-ticks">${ticks}</div>
        </div>
      </div>
      <div class="chart-legend"><span class="lg lg-temp">— Temp</span><span class="lg lg-heat">– – Feels Like</span></div>
    </div>
    ${cardFooter(src)}`;
}

function renderForecastMini(state) {
  const f = state.forecast_3day || {};
  const days = Array.isArray(f.days) ? f.days : [];
  const spc = f.spc_outlook || null;
  const src = f.source || {};
  const deg = isDegraded(src) ? degradedBanner(src) : '';

  let cards;
  if (days.length === 0) {
    cards = `<div class="no-data-placeholder">Forecast unavailable.</div>`;
  } else {
    cards = `<div class="forecast-days">` + days.map(d => {
      const icon = WEATHER_ICONS[weatherIconKey(d.icon)] || WEATHER_ICONS.unknown;
      return `<div class="forecast-day-card" aria-label="${esc(d.name)}: high ${val(d.high_f, '°')}, low ${val(d.low_f, '°')}">
        <div class="forecast-day-name">${esc(d.name)}</div>
        <div class="forecast-day-icon" aria-hidden="true">${icon}</div>
        <div class="forecast-temps">${val(d.high_f, '°')}/<span class="low">${val(d.low_f, '°')}</span></div>
        <div class="forecast-day-summary">${esc(d.summary || '')}</div>
      </div>`;
    }).join('') + `</div>`;
  }

  let spcHtml = '';
  if (spc && spc.text) {
    const cat = (spc.category || 'general').toLowerCase();
    spcHtml = `<div class="spc-banner spc-${esc(cat)}" role="note" aria-label="SPC outlook: ${esc(SPC_LABELS[cat] || cat)} — ${esc(spc.text)}">
      <strong>SPC:</strong> ${esc(SPC_LABELS[cat] || cat)} &mdash; ${esc(spc.text)}</div>`;
  }

  $forecast.innerHTML = `
    ${cardTitle('3-Day Look Ahead')}
    <div class="card-body">${deg}${cards}${spcHtml}</div>
    ${cardFooter(src)}`;
}

/* ── Bottom status strip ──────────────────────────────────────────────────── */

function renderStatusStrip(state) {
  const w   = state.weather || {};
  const cur = w.current || {};
  const tod = w.today || {};
  // Always-on AQI reading (not the threshold-gated hazard callout), so good-air
  // days show the actual value instead of "No data".
  const aqi = (state.air_quality && state.air_quality.aqi != null)
    ? state.air_quality
    : ((state.hazards || {}).aqi_callout || null);
  const sources = state.sources || {};

  // Forecast headline: high + heat index when hot, otherwise high/low (winter).
  const todayVal = tod.high_f != null ? `${Math.round(tod.high_f)}°` : '—';
  const todaySub = tod.heat_index_f != null
    ? `HI ${Math.round(tod.heat_index_f)}°`
    : (tod.low_f != null ? `Lo ${Math.round(tod.low_f)}°` : '');

  const items = [];
  items.push(stripItem('🌡', 'Temp',
    cur.temp_f != null ? `${Math.round(cur.temp_f)}°` : '—',
    cur.feels_like_f != null ? `feels ${Math.round(cur.feels_like_f)}°` : ''));
  items.push(stripItem('⤒', 'Forecast', todayVal, todaySub));
  items.push(stripItem('☂', 'Precip Chance', tod.pop_pct != null ? `${tod.pop_pct}%` : '—',
    tod.pop_window ? esc(tod.pop_window) : ''));
  items.push(stripItem('●', 'Air Quality', aqi ? aqi.label : 'No data',
    aqi ? `AQI ${aqi.aqi}` : ''));
  items.push(stripItem('✷', 'UV Index', tod.uv_index != null ? String(tod.uv_index) : '—'));
  items.push(stripItem('☀', 'Sunrise', hhmm(tod.sunrise) || '—'));
  items.push(stripItem('☾', 'Sunset', hhmm(tod.sunset) || '—'));

  // All-systems aggregate across every live source.
  const blocks = ['nws', 'spc', 'ga511', 'airnow', 'openmeteo', 'weather_map']
    .map(k => sources[k]).filter(Boolean);
  const down = blocks.filter(b => !b.ok || b.stale).map(b => b.name);
  const allGo = down.length === 0;
  const sysHtml = allGo
    ? `<div class="strip-item strip-status ok"><i aria-hidden="true">✓</i><div class="strip-text"><span class="strip-value">All Systems Go</span></div></div>`
    : `<div class="strip-item strip-status down" role="alert"><i aria-hidden="true">⚠</i><div class="strip-text"><span class="strip-label">Degraded</span><span class="strip-value">${esc(down.join(', '))}</span></div></div>`;

  $strip.innerHTML = items.join('') + sysHtml;
}

function stripItem(icon, label, value, sub = '') {
  const subHtml = sub ? `<span class="strip-sub">${esc(sub)}</span>` : '';
  return `<div class="strip-item">
    <i class="strip-icon" aria-hidden="true">${icon}</i>
    <div class="strip-text"><span class="strip-label">${esc(label)}</span><span class="strip-value">${esc(value)}</span>${subHtml}</div>
  </div>`;
}

/* ── Map ──────────────────────────────────────────────────────────────────── */

function alertSeverityFromProps(props) {
  const ev = String(props.event || '').toLowerCase();
  // Specific watch/warning types with NWS-convention colors
  if (/tornado warning/.test(ev))              return 'danger';   // red
  if (/severe thunderstorm warning/.test(ev))  return 'danger';   // red
  if (/tornado watch/.test(ev))                return 'caution';  // orange
  if (/severe thunderstorm watch/.test(ev))    return 'advisory'; // yellow
  // Flash flood — warning stays extreme, watch is orange
  if (/flash flood warning/.test(ev))          return 'extreme';  // purple
  if (/flash flood watch/.test(ev))            return 'caution';  // orange
  // Regular flood events
  if (/flood warning/.test(ev))               return 'danger';   // red
  if (/flood watch/.test(ev))                 return 'advisory'; // yellow
  if (/flood advisory/.test(ev))              return 'advisory'; // yellow
  // Other high-impact warnings stay extreme (purple)
  if (/(ice storm warning|extreme)/.test(ev)) return 'extreme';
  if (ev.includes('warning')) return 'danger';
  if (ev.includes('watch')) return 'watch';
  if (ev.includes('advisory')) return 'advisory';
  // Fall back to our own vocab if the demo geojson already carries it.
  if (SEV_META[props.severity]) return props.severity;
  return 'info';
}

const SEV_COLORS = {
  info:     '#4aa3ff',
  watch:    '#3fbf6b',
  advisory: '#e6b800',
  caution:  '#ed7a2f',
  danger:   '#ef5350',
  extreme:  '#b56cff',
};

/* MapLibre GL expression that maps the pre-processed '_sev' property to a color. */
const SEV_COLOR_EXPR = ['match', ['get', '_sev'],
  'watch',    '#3fbf6b',
  'advisory', '#e6b800',
  'caution',  '#ed7a2f',
  'danger',   '#ef5350',
  'extreme',  '#b56cff',
  /* default (info) */ '#4aa3ff',
];

function buildRadarFrames(cfg) {
  // Remove any existing radar sources + layers from a previous build.
  if (radarTimer) { clearInterval(radarTimer); radarTimer = null; }
  for (let i = 0; i < radarFrameCount; i++) {
    if (map.getLayer(`radar-layer-${i}`)) map.removeLayer(`radar-layer-${i}`);
    if (map.getSource(`radar-frame-${i}`)) map.removeSource(`radar-frame-${i}`);
  }
  radarFrameCount = 0;

  const anim       = cfg.animation || {};
  const opacity    = ((cfg.layers || {}).radar || {}).opacity != null ? cfg.layers.radar.opacity : 0.7;
  const nFrames    = anim.enabled ? (anim.frames || 8) : 1;
  const intervalMs = anim.interval_ms || 600;

  // Honor the active rotation view: radar frames stay hidden unless 'radar' is
  // showing, so the animation timer can't flash radar over temps/alerts.
  const applyOpacity = () => {
    const show = mapMode === null || mapMode === 'radar';
    for (let i = 0; i < radarFrameCount; i++) {
      if (map.getLayer(`radar-layer-${i}`)) {
        map.setPaintProperty(`radar-layer-${i}`, 'raster-opacity',
          show && i === radarIdx ? opacity : 0);
      }
    }
  };

  // Don't start the animation until every frame has finished loading its tiles.
  // Until then the most-recent frame (offset=0) is shown statically so the map
  // is never blank. Once all frames are in the browser tile cache, frame
  // transitions are instant and complete — no partial-tile flicker.
  const loadedSources = new Set();
  const sourcedataHandler = (e) => {
    if (e.isSourceLoaded && e.sourceId && e.sourceId.startsWith('radar-frame-') &&
        !loadedSources.has(e.sourceId)) {
      loadedSources.add(e.sourceId);
      if (loadedSources.size >= nFrames && anim.enabled && nFrames > 1 && !radarTimer) {
        map.off('sourcedata', sourcedataHandler);
        radarTimer = setInterval(() => {
          radarIdx = (radarIdx + 1) % radarFrameCount;
          applyOpacity();
        }, intervalMs);
      }
    }
  };
  map.on('sourcedata', sourcedataHandler);

  // Build sources + layers oldest → newest; offset 0 = most recent frame (last).
  for (let i = 0; i < nFrames; i++) {
    const offset = (nFrames - 1 - i) * 5;
    map.addSource(`radar-frame-${i}`, {
      type: 'raster',
      tiles: [radarTileUrl(offset)],
      tileSize: 256,
      attribution: 'Radar: NWS via Iowa Environmental Mesonet',
    });
    map.addLayer({
      id: `radar-layer-${i}`,
      type: 'raster',
      source: `radar-frame-${i}`,
      paint: { 'raster-opacity': 0 },
    });
  }

  // Show the most-recent frame immediately while older frames warm up.
  radarFrameCount = nFrames;
  radarIdx = radarFrameCount - 1;
  applyOpacity();
  radarBuiltAt = Date.now();
}

async function fetchAlerts() {
  if (!map || !mapStyleLoaded) return;
  try {
    const resp = await fetch(ALERTS_ENDPOINT, { cache: 'no-store' });
    if (!resp.ok) return;
    const gj = await resp.json();
    // Pre-process severity so MapLibre GL expressions can reference '_sev'.
    (gj.features || []).forEach(f => {
      f.properties._sev = alertSeverityFromProps(f.properties || {});
    });
    map.getSource('alerts').setData(gj);
  } catch (e) {
    /* alerts are best-effort; the radar + base map still render */
  }
}

/* Temperature color scale (°F) — cool blue → hot red, legible across the room. */
const TEMP_SCALE = [
  { t: 20,  c: '#5b8fff' },
  { t: 32,  c: '#56c6e8' },
  { t: 45,  c: '#4bd0a0' },
  { t: 60,  c: '#7ec64a' },
  { t: 72,  c: '#e3c93b' },
  { t: 85,  c: '#ef9a3d' },
  { t: 95,  c: '#ec6a3a' },
  { t: 105, c: '#d8392f' },
];

function tempColor(f) {
  if (f == null || isNaN(f)) return '#888';
  if (f <= TEMP_SCALE[0].t) return TEMP_SCALE[0].c;
  const last = TEMP_SCALE[TEMP_SCALE.length - 1];
  if (f >= last.t) return last.c;
  for (let i = 0; i < TEMP_SCALE.length - 1; i++) {
    const a = TEMP_SCALE[i], b = TEMP_SCALE[i + 1];
    if (f >= a.t && f < b.t) return a.c; // stepped scale reads cleaner at distance
  }
  return last.c;
}

async function fetchTemps() {
  if (!map || !mapStyleLoaded) return;
  try {
    const resp = await fetch(TEMPS_ENDPOINT, { cache: 'no-store' });
    if (!resp.ok) return;
    const gj = await resp.json();

    // Remove old HTML markers before rebuilding.
    tempMarkers.forEach(m => m.remove());
    tempMarkers = [];

    (gj.features || []).forEach(ft => {
      const props = ft.properties || {};
      const coords = (ft.geometry || {}).coordinates;
      const t = props.temp_f;
      if (!coords || t == null) return;
      const [lon, lat] = coords;

      const el = document.createElement('div');
      el.className = 'temp-dot';
      el.setAttribute('aria-hidden', 'true');
      const nameHtml = props.name ? `<small>${esc(props.name)}</small>` : '';
      el.innerHTML = `<span style="background:${tempColor(t)}"><b>${Math.round(t)}&deg;</b>${nameHtml}</span>`;

      const marker = new maplibregl.Marker({ element: el, anchor: 'center' })
        .setLngLat([lon, lat]);
      tempMarkers.push(marker);
    });

    // Feed the same data to the heatmap source.
    if (map.getSource('temps-heat')) map.getSource('temps-heat').setData(gj);

    // If the temps view is active, add them to the map immediately.
    if (mapMode === 'temps') tempMarkers.forEach(m => m.addTo(map));
  } catch (e) {
    /* temps are best-effort; the radar + base map still render */
  }
}

function initMap(state) {
  const cfg = state.weather_map || {};
  mapCfg = cfg;
  if (cfg.enabled === false) {
    document.getElementById('card-map').classList.add('hidden');
    return;
  }

  const center   = cfg.center || { lat: 33.749, lon: -84.388 };
  const styleUrl = VECTOR_STYLES[cfg.base_style] || VECTOR_STYLES.dark;

  map = new maplibregl.Map({
    container: 'map',
    style: styleUrl,
    center: [center.lon, center.lat],  // MapLibre: [lon, lat] order
    zoom: cfg.default_zoom || 8,
    minZoom: cfg.min_zoom || 5,
    maxZoom: cfg.max_zoom || 10,
    attributionControl: true,
    scrollZoom: false,
  });

  map.on('load', () => {
    mapStyleLoaded = true;

    // Alert GeoJSON source + fill/outline layers (hidden until alerts view).
    map.addSource('alerts', {
      type: 'geojson',
      data: { type: 'FeatureCollection', features: [] },
    });
    map.addLayer({
      id: 'alert-fill',
      type: 'fill',
      source: 'alerts',
      layout: { visibility: 'none' },
      paint: { 'fill-color': SEV_COLOR_EXPR, 'fill-opacity': 0.18 },
    });
    map.addLayer({
      id: 'alert-outline',
      type: 'line',
      source: 'alerts',
      layout: { visibility: 'none' },
      paint: { 'line-color': SEV_COLOR_EXPR, 'line-width': 2 },
    });

    // Temperature heatmap — inserted before the first symbol layer so city
    // names and road labels remain on top of the shading.
    const firstSymbolLayer = map.getStyle().layers.find(l => l.type === 'symbol')?.id;
    map.addSource('temps-heat', {
      type: 'geojson',
      data: { type: 'FeatureCollection', features: [] },
    });
    map.addLayer({
      id: 'temps-heatmap',
      type: 'heatmap',
      source: 'temps-heat',
      maxzoom: 12,
      layout: { visibility: 'none' },
      paint: {
        // Weight driven by temperature so hotter stations push the color up.
        'heatmap-weight': [
          'interpolate', ['linear'], ['get', 'temp_f'],
          20, 0,
          105, 1,
        ],
        // Radius must exceed the inter-city pixel distance so adjacent
        // Gaussians overlap and merge into a continuous field rather than
        // discrete blobs. Cities are ~100–200 px apart at the kiosk zoom,
        // so the radius needs to be at least 1.5× that to fill the gaps.
        'heatmap-radius': [
          'interpolate', ['linear'], ['zoom'],
          4,  120,
          7,  220,
          10, 360,
        ],
        // Density → temperature colour palette (cold blue → hot red).
        // A faint cool floor at density 0 fills any residual gaps between
        // stations so the whole region shows shading rather than dark voids.
        'heatmap-color': [
          'interpolate', ['linear'], ['heatmap-density'],
          0,    'rgba(91,143,255,0.08)',
          0.1,  'rgba(86,198,232,0.35)',
          0.25, 'rgba(75,208,160,0.48)',
          0.45, 'rgba(126,198,74,0.53)',
          0.6,  'rgba(227,201,59,0.56)',
          0.75, 'rgba(239,154,61,0.59)',
          0.9,  'rgba(236,106,58,0.62)',
          1,    'rgba(216,57,47,0.65)',
        ],
        'heatmap-intensity': 2.5,
        'heatmap-opacity': 0.55,
      },
    }, firstSymbolLayer);

    // Alert hover tooltip using a reusable Popup.
    alertPopup = new maplibregl.Popup({
      closeButton: false,
      closeOnClick: false,
      className: 'alert-popup',
    });
    map.on('mouseenter', 'alert-fill', (e) => {
      map.getCanvas().style.cursor = 'pointer';
      const props = (e.features[0] || {}).properties || {};
      const m = SEV_META[props._sev] || SEV_META.info;
      alertPopup.setLngLat(e.lngLat)
        .setHTML(`${m.icon} ${esc(props.event || 'Alert')}`)
        .addTo(map);
    });
    map.on('mouseleave', 'alert-fill', () => {
      map.getCanvas().style.cursor = '';
      alertPopup.remove();
    });

    // Traffic incident polylines — hidden until the traffic view is active.
    map.addSource('traffic-routes', {
      type: 'geojson',
      data: { type: 'FeatureCollection', features: [] },
    });
    map.addLayer({
      id: 'traffic-routes',
      type: 'line',
      source: 'traffic-routes',
      layout: { visibility: 'none', 'line-join': 'round', 'line-cap': 'round' },
      paint: {
        'line-color': ['match', ['get', 'type'],
          'crash',        '#ef5350',
          'construction', '#e6b800',
          'congestion',   '#f59e0b',
          'closure',      '#c0392b',
          'incident',     '#ed7a2f',
          '#6b7280',
        ],
        'line-width': 4,
        'line-opacity': 0.85,
      },
    }, firstSymbolLayer);

    // Radar frames stay on the map (opacity toggled by the active view).
    buildRadarFrames(cfg);
    fetchAlerts();
    fetchTemps();
    if (currentState) updateTrafficLayer(currentState);

    addMapControls(cfg);
    startMapRotation(cfg);
  });

  mapInited = true;
}

const MODE_META = {
  radar:   { label: 'Weather Radar' },
  alerts:  { label: 'Watches &amp; Warnings' },
  temps:   { label: 'Temperature' },
  traffic: { label: 'Traffic Incidents' },
};

/* Show exactly one rotation view; radar opacity is toggled rather than the
   layer removed so the warmed-up frame cache and animation timer survive. */
function showMapMode(mode) {
  if (!map || !mapStyleLoaded) return;
  const prevMode = mapMode;
  mapMode = mode;

  const radarOp = ((mapCfg.layers || {}).radar || {}).opacity != null
    ? mapCfg.layers.radar.opacity : 0.7;

  // Radar: toggle opacity per frame rather than removing the layers so the
  // tile cache stays warm through view switches.
  for (let i = 0; i < radarFrameCount; i++) {
    if (map.getLayer(`radar-layer-${i}`)) {
      map.setPaintProperty(`radar-layer-${i}`, 'raster-opacity',
        mode === 'radar' && i === radarIdx ? radarOp : 0);
    }
  }

  // Alerts: toggle visibility on both fill and outline layers.
  const alertVis = mode === 'alerts' ? 'visible' : 'none';
  if (map.getLayer('alert-fill'))   map.setLayoutProperty('alert-fill',    'visibility', alertVis);
  if (map.getLayer('alert-outline')) map.setLayoutProperty('alert-outline', 'visibility', alertVis);

  // Temps: show heatmap shading behind the pills, then add/remove pill markers.
  const heatVis = mode === 'temps' ? 'visible' : 'none';
  if (map.getLayer('temps-heatmap')) map.setLayoutProperty('temps-heatmap', 'visibility', heatVis);
  if (mode === 'temps') {
    tempMarkers.forEach(m => m.addTo(map));
  } else {
    tempMarkers.forEach(m => m.remove());
  }

  // Traffic: incident pins + polylines; fit to Atlanta metro then restore on exit.
  const routeVis = mode === 'traffic' ? 'visible' : 'none';
  if (map.getLayer('traffic-routes')) map.setLayoutProperty('traffic-routes', 'visibility', routeVis);
  if (mode === 'traffic') {
    trafficMarkers.forEach(m => m.addTo(map));
    map.fitBounds(ATLANTA_METRO_BOUNDS, { padding: 20, duration: 800 });
  } else {
    trafficMarkers.forEach(m => m.remove());
    if (prevMode === 'traffic') {
      const c = mapCfg.center || { lat: 33.749, lon: -84.388 };
      map.flyTo({ center: [c.lon, c.lat], zoom: mapCfg.default_zoom || 7, duration: 800 });
    }
  }

  updateMapChrome(mode);
}

function startMapRotation(cfg) {
  const rot = cfg.rotation || {};
  const modes = (rot.modes && rot.modes.length) ? rot.modes.slice() : ['radar', 'alerts', 'temps', 'traffic'];
  mapModes = modes;
  if (rotationTimer) { clearInterval(rotationTimer); rotationTimer = null; }

  let idx = 0;
  showMapMode(modes[idx]);
  if (rot.enabled === false || modes.length < 2) return;

  const intervalMs = (rot.interval_seconds || 20) * 1000;
  rotationTimer = setInterval(() => {
    idx = (idx + 1) % modes.length;
    showMapMode(modes[idx]);
  }, intervalMs);
}

/* Top-right view indicator + bottom-left legend, both updated per active view. */
function addMapControls(_cfg) {
  class SimpleControl {
    constructor(id, cls, position) {
      this._id = id; this._cls = cls; this._pos = position;
    }
    onAdd() {
      const div = document.createElement('div');
      div.id = this._id;
      div.className = `maplibregl-ctrl ${this._cls}`;
      div.addEventListener('click', e => e.stopPropagation());
      this._container = div;
      return div;
    }
    onRemove() { this._container?.parentNode?.removeChild(this._container); }
  }

  map.addControl(new SimpleControl('map-mode',   'map-mode',          'top-right'));
  map.addControl(new SimpleControl('map-legend', 'map-legend hidden', 'bottom-left'));
}

function updateMapChrome(mode) {
  const ind = document.getElementById('map-mode');
  if (ind) {
    ind.innerHTML = (mapModes.length ? mapModes : [mode]).map(m => {
      const meta = MODE_META[m] || { label: m };
      return `<span class="${m === mode ? 'active' : ''}">${meta.label}</span>`;
    }).join('');
  }
  const leg = document.getElementById('map-legend');
  if (!leg) return;
  if (mode === 'temps') {
    const stops = TEMP_SCALE.filter((_, i) => i % 2 === 0 || i === TEMP_SCALE.length - 1);
    leg.innerHTML = '<span class="legend-title">Temp &deg;F</span>' +
      stops.map(s => `<span class="legend-swatch"><i style="background:${s.c}"></i>${s.t}</span>`).join('');
    leg.classList.remove('hidden');
  } else if (mode === 'alerts') {
    const items = [
      ['watch', 'Watch'], ['advisory', 'Advisory'], ['danger', 'Warning'], ['extreme', 'Severe'],
    ];
    leg.innerHTML = items.map(([k, lbl]) =>
      `<span class="legend-swatch"><i style="background:${SEV_COLORS[k]}"></i>${lbl}</span>`).join('');
    leg.classList.remove('hidden');
  } else if (mode === 'traffic') {
    leg.innerHTML = Object.entries(TRAFFIC_PIN_META)
      .filter(([k]) => k !== 'other')
      .map(([, m]) =>
        `<span class="legend-swatch"><i style="background:${m.color}"></i>${m.icon} ${m.label}</span>`)
      .join('');
    leg.classList.remove('hidden');
  } else {
    leg.classList.add('hidden');
    leg.innerHTML = '';
  }
}

/* Build/refresh traffic incident markers and polylines from the current state.
   Called on first map load and on every state poll. */
function updateTrafficLayer(state) {
  if (!map || !mapStyleLoaded) return;

  // Merge disruptions + commute traffic, de-duped by text so the same event
  // that appears in both arrays only gets one pin.
  const seen = new Set();
  const events = [];
  for (const ev of [
    ...((state.disruptions || {}).traffic || []),
    ...((state.commute || {}).traffic || []),
  ]) {
    if (!seen.has(ev.text)) { seen.add(ev.text); events.push(ev); }
  }

  // Rebuild HTML markers.
  trafficMarkers.forEach(m => m.remove());
  trafficMarkers = [];

  const routeFeatures = [];

  for (const ev of events) {
    if (ev.lat != null && ev.lon != null) {
      const meta = TRAFFIC_PIN_META[ev.type] || TRAFFIC_PIN_META.other;
      const label = (ev.text || '').split(/\s/)[0]; // road token, e.g. "I-285"
      const el = document.createElement('div');
      el.className = 'traffic-pin';
      el.setAttribute('title', ev.text || '');
      el.setAttribute('aria-label', ev.text || '');
      el.innerHTML =
        `<div class="traffic-pin__inner">` +
          `<span class="traffic-pin__badge" style="background:${meta.color};--pin-color:${meta.color};">${meta.icon}</span>` +
          (label ? `<span class="traffic-pin__label">${esc(label)}</span>` : '') +
        `</div>`;
      trafficMarkers.push(
        new maplibregl.Marker({ element: el, anchor: 'center' }).setLngLat([ev.lon, ev.lat])
      );
    }

    if (ev.polyline) {
      const coords = decodePolyline(ev.polyline);
      if (coords.length >= 2) {
        routeFeatures.push({
          type: 'Feature',
          properties: { type: ev.type || 'other' },
          geometry: { type: 'LineString', coordinates: coords },
        });
      }
    }
  }

  if (map.getSource('traffic-routes')) {
    map.getSource('traffic-routes').setData({ type: 'FeatureCollection', features: routeFeatures });
  }

  // If already in traffic mode, add the freshly built markers immediately.
  if (mapMode === 'traffic') trafficMarkers.forEach(m => m.addTo(map));
}

function renderMap(state) {
  const cfg = state.weather_map || {};
  if (cfg.enabled === false) return;
  if (!mapInited) { initMap(state); }
  else {
    mapCfg = cfg;
    const anim = cfg.animation || {};
    const refreshMs = (anim.refresh_seconds || 300) * 1000;
    if (mapStyleLoaded && Date.now() - radarBuiltAt >= refreshMs) {
      buildRadarFrames(cfg);
      showMapMode(mapMode);  // re-assert the active view after a frame rebuild
    }
    fetchAlerts();
    fetchTemps();
    updateTrafficLayer(state);
  }

  // Degraded overlay driven by the map source freshness.
  const src = cfg.source || (state.sources || {}).weather_map || {};
  if (isDegraded(src)) {
    $mapDegraded.classList.remove('hidden');
    $mapDegraded.innerHTML = `<i aria-hidden="true">&#9888;</i> Radar as of ${lastGoodTime(src)} (${humanAge(src)}) &mdash; verify current conditions.`;
  } else {
    $mapDegraded.classList.add('hidden');
  }
  if (map) setTimeout(() => map.resize(), 0);
}

/* ── Master render ──────────────────────────────────────────────────────── */

function renderDashboard(state) {
  renderHeader(state);
  renderOverallRisk(state);
  renderNextUpdate(state);
  renderSummary(state);
  renderHazards(state);
  renderActivity(state);
  renderMap(state);
  renderTempChart(state);
  renderForecastMini(state);
  renderStatusStrip(state);
}

/* ── Clock ───────────────────────────────────────────────────────────────── */

function startClock() {
  function tick() {
    const now = new Date();
    const p = tzParts(now, {
      weekday: 'short', month: 'short', day: 'numeric',
      hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
    });
    $datetime.textContent = `${p.weekday} ${p.day} ${p.month}  ${p.hour}:${p.minute}`;
  }
  tick();
  clockTimer = setInterval(tick, 10000);
}

/* ── Data fetching ───────────────────────────────────────────────────────── */

function resolveDataUrl() {
  const params  = new URLSearchParams(window.location.search);
  const fixture = params.get('fixture');
  const valid   = ['morning', 'afternoon', 'degraded'];
  if (fixture && valid.includes(fixture)) {
    return `./fixtures/${fixture}.json`;
  }
  return API_ENDPOINT;
}

const DATA_URL = resolveDataUrl();

const FETCH_TIMEOUT_MS = 10000;

async function fetchState() {
  // Bound the request so a hung backend (e.g. mid-restart) can't leave the
  // board pending forever — abort and let the poll loop retry instead.
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), FETCH_TIMEOUT_MS);
  try {
    const resp = await fetch(DATA_URL, {
      cache: 'no-store',
      headers: { 'Accept': 'application/json' },
      signal: ctrl.signal,
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    return await resp.json();
  } finally {
    clearTimeout(t);
  }
}

function setReconnecting(isRecon) {
  reconnecting = isRecon;
  if (isRecon) {
    $statusBar.classList.add('visible');
    $statusTxt.textContent = 'Reconnecting…';
  } else {
    $statusBar.classList.remove('visible');
  }
}

async function poll() {
  try {
    const state = await fetchState();
    setReconnecting(false);
    const firstLoad = currentState === null;
    currentState = state;
    if (firstLoad) $loading.classList.add('hidden');
    // A successful poll clears any earlier first-load error screen.
    $errorScr.classList.remove('visible');
    renderDashboard(state);
  } catch (err) {
    console.warn('[SITREP] Fetch failed:', err.message);
    if (currentState === null) {
      // First-load failure: surface the error but keep polling so the board
      // recovers on its own once the backend is reachable (don't dead-end).
      $loading.classList.add('hidden');
      $errorDet.textContent = err.message || 'Network error';
      $errorScr.classList.add('visible');
    } else {
      setReconnecting(true);
    }
  }
}

function schedulePoll(state) {
  if (fetchTimer) clearTimeout(fetchTimer);
  const interval = ((state || {}).display || {}).refresh_seconds || DEFAULT_REFRESH_S;
  fetchTimer = setTimeout(async () => {
    await poll();
    schedulePoll(currentState);
  }, interval * 1000);
}

/* ── Bootstrap ───────────────────────────────────────────────────────────── */

(async function init() {
  startClock();
  await poll();
  // Always keep polling — even if the first load failed — so the board
  // recovers when the backend comes up. schedulePoll tolerates a null state.
  schedulePoll(currentState);
})();
