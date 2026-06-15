/* =========================================================================
   Field SITREP Board — app.js
   Plain vanilla JS, no build step, no framework, no external deps.
   Fetches /api/state (or a local fixture for dev) and renders a rotating
   slide carousel.

   Dev fixture usage:  ?fixture=morning | afternoon | degraded
   ========================================================================= */

'use strict';

/* ── Constants ──────────────────────────────────────────────────────────── */
const DEFAULT_DWELL_S   = 12;
const DEFAULT_REFRESH_S = 30;
const API_ENDPOINT      = '/api/state';

/* ── Severity metadata — icon shape + label so color is never the only cue */
const SEV_META = {
  info:     { icon: 'ℹ',  label: 'INFO',     cls: 'sev-info'     },
  watch:    { icon: '◉',  label: 'WATCH',    cls: 'sev-watch'    },
  advisory: { icon: '⚑',  label: 'ADVISORY', cls: 'sev-advisory' },
  caution:  { icon: '⚠',  label: 'CAUTION',  cls: 'sev-caution'  },
  danger:   { icon: '▲',  label: 'DANGER',   cls: 'sev-danger'   },
  extreme:  { icon: '◆',  label: 'EXTREME',  cls: 'sev-extreme'  },
};

/* Traffic/alert event icons — shape reinforces meaning beyond color */
const EVENT_ICONS = {
  crash:        '✖',
  incident:     '⚠',
  construction: '⚒',
  congestion:   '≡',
  default:      '●',
};

/* Weather icon SVGs — inline, no network dependency */
const WEATHER_ICONS = {
  storm: `<svg viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" focusable="false">
    <ellipse cx="24" cy="20" rx="12" ry="9" fill="#4a5568"/>
    <ellipse cx="18" cy="23" rx="8" ry="6" fill="#6b7280"/>
    <polygon points="22,28 18,36 23,33 19,42 28,31 23,34" fill="#fbbf24"/>
  </svg>`,
  clear: `<svg viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" focusable="false">
    <circle cx="24" cy="24" r="9" fill="#f0920e"/>
    <g stroke="#f0920e" stroke-width="2.5" stroke-linecap="round">
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
    <ellipse cx="24" cy="18" rx="13" ry="9" fill="#4a5568"/>
    <ellipse cx="17" cy="21" rx="8" ry="6" fill="#6b7280"/>
    <g stroke="#2c7be5" stroke-width="2" stroke-linecap="round">
      <line x1="17" y1="30" x2="15" y2="38"/>
      <line x1="24" y1="30" x2="22" y2="38"/>
      <line x1="31" y1="30" x2="29" y2="38"/>
    </g>
  </svg>`,
  cloudy: `<svg viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" focusable="false">
    <ellipse cx="24" cy="22" rx="13" ry="9" fill="#4a5568"/>
    <ellipse cx="16" cy="25" rx="8" ry="6" fill="#6b7280"/>
    <ellipse cx="32" cy="26" rx="7" ry="5" fill="#6b7280"/>
  </svg>`,
  snow: `<svg viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" focusable="false">
    <ellipse cx="24" cy="18" rx="13" ry="9" fill="#6b7280"/>
    <g stroke="#2c7be5" stroke-width="2" stroke-linecap="round">
      <line x1="16" y1="30" x2="16" y2="38"/>
      <line x1="12" y1="34" x2="20" y2="34"/>
      <line x1="24" y1="30" x2="24" y2="38"/>
      <line x1="20" y1="34" x2="28" y2="34"/>
      <line x1="32" y1="30" x2="32" y2="38"/>
      <line x1="28" y1="34" x2="36" y2="34"/>
    </g>
  </svg>`,
  wind: `<svg viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" focusable="false">
    <g stroke="#51606e" stroke-width="2.5" stroke-linecap="round">
      <path d="M8 18 Q28 14 36 18 Q42 21 38 24 Q34 27 30 22" fill="none"/>
      <path d="M8 24 Q24 21 32 24" fill="none"/>
      <path d="M8 30 Q20 27 28 30 Q34 33 30 36 Q27 38 24 34" fill="none"/>
    </g>
  </svg>`,
  unknown: `<svg viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" focusable="false">
    <circle cx="24" cy="24" r="16" stroke="#4a5568" stroke-width="2"/>
    <text x="24" y="30" text-anchor="middle" font-size="18" fill="#6b7280">?</text>
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

/* ── State ──────────────────────────────────────────────────────────────── */
let currentState    = null;   // last successfully parsed state
let slides          = [];     // current slide descriptors
let activeSlideIdx  = 0;
let carouselTimer   = null;
let fetchTimer      = null;
let clockTimer      = null;
let reconnecting    = false;

/* ── DOM refs ────────────────────────────────────────────────────────────── */
const $loading   = document.getElementById('loading-screen');
const $errorScr  = document.getElementById('error-screen');
const $errorDet  = document.getElementById('error-detail');
const $app       = document.getElementById('app');
const $loc       = document.getElementById('header-location');
const $modeBadge = document.getElementById('header-mode-badge');
const $datetime  = document.getElementById('header-datetime');
const $statusBar = document.getElementById('status-bar');
const $statusTxt = document.getElementById('status-text');
const $carousel  = document.getElementById('carousel');
const $dots      = document.getElementById('slide-dots');

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

/**
 * Format an ISO-8601 timestamp for glanceable display.
 * Returns e.g. "06:35" for same-day, "Jun 13 06:35" cross-day.
 */
function fmtTime(isoStr) {
  if (!isoStr) return '&mdash;';
  try {
    const d = new Date(isoStr);
    const now = new Date();
    const sameDay = d.getFullYear() === now.getFullYear()
      && d.getMonth() === now.getMonth()
      && d.getDate() === now.getDate();
    const hh = String(d.getHours()).padStart(2, '0');
    const mm = String(d.getMinutes()).padStart(2, '0');
    if (sameDay) return `${hh}:${mm}`;
    const mon = d.toLocaleString('en-US', { month: 'short' });
    return `${mon} ${d.getDate()} ${hh}:${mm}`;
  } catch (e) {
    return esc(isoStr);
  }
}

/**
 * Derive a human-readable age string from age_seconds or last_good_at.
 * e.g. "about 2 hrs ago", "about 45 min ago", "about 1 hr ago"
 */
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

/** Format last_good_at for the footer (short time) */
function lastGoodTime(src) {
  return src.last_good_at ? fmtTime(src.last_good_at) : '&mdash;';
}

/** Get the formatted "last updated" text for a source block */
function sourceFooter(src) {
  if (!src) return '';
  if (!src.ok || src.stale) {
    return `${esc(src.name || '')} &middot; last good ${lastGoodTime(src)}`;
  }
  return `${esc(src.name || '')} &middot; Updated ${fmtTime(src.fetched_at)}`;
}

/** Build a severity chip element (color + icon + label text — never color alone) */
function sevChip(severity, extraText = '') {
  const m = SEV_META[severity] || SEV_META.info;
  const extra = extraText ? ` ${esc(extraText)}` : '';
  return `<span class="severity-chip ${m.cls}" aria-label="${m.label}${extraText ? ': ' + extraText : ''}">
    <i class="chip-icon" aria-hidden="true">${m.icon}</i>${m.label}${extra}
  </span>`;
}

/**
 * Build a degraded-state banner for a section whose source is stale/down.
 * Shows last-good time, age, and a check-conditions note.
 */
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

/** Build footer HTML for a slide */
function slideFooter(src) {
  return `<footer class="slide-footer">
    <span class="footer-source">${sourceFooter(src)}</span>
  </footer>`;
}

/** Get the appropriate weather icon key from a forecast day icon string */
function weatherIconKey(iconStr) {
  if (!iconStr) return 'unknown';
  const s = String(iconStr).toLowerCase();
  if (s.includes('storm') || s.includes('thunder')) return 'storm';
  if (s.includes('clear') || s.includes('sunny'))   return 'clear';
  if (s.includes('rain')  || s.includes('shower'))  return 'rain';
  if (s.includes('snow')  || s.includes('winter'))  return 'snow';
  if (s.includes('cloud') || s.includes('overcast')) return 'cloudy';
  if (s.includes('wind'))                            return 'wind';
  // direct key match
  if (WEATHER_ICONS[s]) return s;
  return 'unknown';
}

/* ── Slide builders ─────────────────────────────────────────────────────── */

/**
 * Slide 1 (morning only): Morning Briefing (BLUF)
 * Renders briefing.bottom_line + briefing.watch_for
 * + hazard flags from hazards.ranked + AQI callout.
 * Source text comes from briefing.sources (model-attributed).
 */
function buildBriefingSlide(state) {
  const b = state.briefing || {};
  const h = state.hazards  || {};
  const ranked = Array.isArray(h.ranked) ? h.ranked : [];
  const aqi    = h.aqi_callout || null;

  /* Hazard flag row */
  let flagsHtml = '';
  if (ranked.length > 0) {
    const chips = ranked.map(flag => {
      const m = SEV_META[flag.severity] || SEV_META.info;
      return `<div class="hazard-flag ${m.cls}" role="listitem"
                   aria-label="Hazard rank ${flag.rank}: ${flag.label}, severity ${flag.severity}">
        <span class="flag-rank" aria-hidden="true">${flag.rank}</span>
        <i aria-hidden="true">${m.icon}</i>
        ${esc(flag.label)}
      </div>`;
    }).join('');
    flagsHtml = `<div class="hazard-flags" role="list" aria-label="Active hazards">${chips}</div>`;
  }

  /* AQI callout */
  let aqiHtml = '';
  if (aqi) {
    aqiHtml = `<div class="aqi-callout" role="note" aria-label="Air quality: ${aqi.label}, AQI ${aqi.aqi}">
      <i aria-hidden="true">&#9680;</i>
      <strong>AQI ${val(aqi.aqi)}</strong>
      &mdash; ${esc(aqi.label)} &mdash; ${esc(aqi.category)}
    </div>`;
  }

  /* Bottom-line prose */
  const bottomLine = b.bottom_line
    ? `<p class="briefing-bottom-line">${esc(b.bottom_line)}</p>`
    : `<p class="briefing-bottom-line no-data-placeholder">Briefing not available.</p>`;

  /* Watch-for list */
  const watchItems = Array.isArray(b.watch_for) && b.watch_for.length > 0
    ? b.watch_for.map(item => `<li>${esc(item)}</li>`).join('')
    : '<li class="em-dash">No specific watch items.</li>';

  /* Source footer: briefing uses briefing.sources + briefing.generated_at */
  const srcName    = Array.isArray(b.sources) ? b.sources.join(', ') : (b.source || 'Model');
  const updatedAt  = b.generated_at ? fmtTime(b.generated_at) : '&mdash;';
  const footerHtml = `<footer class="slide-footer">
    <span class="footer-source">${esc(srcName)} &middot; Updated ${updatedAt}</span>
  </footer>`;

  return `<div class="slide-inner">
    <div class="slide-title-bar">
      <h2 class="slide-title">Morning Briefing</h2>
    </div>
    <div class="slide-body">
      ${flagsHtml}
      ${aqiHtml}
      ${bottomLine}
      <div>
        <div class="briefing-label">Watch for</div>
        <ul class="watch-for-list" aria-label="Watch-for items">${watchItems}</ul>
      </div>
    </div>
    ${footerHtml}
  </div>`;
}

/**
 * Slide 2 (morning) / Slide 1 (afternoon): Weather
 * Renders current conditions + today's outlook.
 * Degraded banner when weather source is stale/down.
 */
function buildWeatherSlide(state) {
  const w   = state.weather || {};
  const cur = w.current || {};
  const tod = w.today   || {};
  const src = w.source  || {};
  const loc = (state.location || {}).name || '';
  const deg = isDegraded(src);

  let bodyHtml = '';

  if (deg) {
    bodyHtml += degradedBanner(src);
    bodyHtml += `<p class="no-data-placeholder">Last known values shown below.</p>`;
  }

  /* Current conditions column */
  const wind = cur.wind || {};
  const windStr = wind.speed_mph != null
    ? `${esc(wind.dir || '')} ${val(wind.speed_mph, ' mph')}${wind.gust_mph != null ? ', gusts ' + val(wind.gust_mph, ' mph') : ''}`
    : '&mdash;';

  const curCol = `<div>
    <div class="weather-section-label">Now</div>
    <div class="weather-temp-primary">${val(cur.temp_f, '°F')}</div>
    <div class="weather-temp-secondary">feels ${val(cur.feels_like_f, '°F')}</div>
    <div class="weather-detail-rows">
      <div class="weather-row">
        <span class="weather-row-label">Wind</span>
        <span class="weather-row-value">${windStr}</span>
      </div>
      ${cur.summary ? `<div class="weather-summary-pill" aria-label="Conditions: ${esc(cur.summary)}">
        ${esc(cur.summary)}
      </div>` : ''}
    </div>
  </div>`;

  /* Today's outlook column */
  const hiloHtml = `H ${val(tod.high_f, '°F')} / L ${val(tod.low_f, '°F')}`;
  const heatIdxHtml = tod.heat_index_f != null
    ? `<div class="weather-row">
        <span class="weather-row-label">Heat index</span>
        <span class="weather-row-value highlight">${val(tod.heat_index_f, '°F')}</span>
       </div>`
    : '';
  const popHtml = tod.pop_pct != null
    ? `<div class="weather-row">
        <span class="weather-row-label">Rain chance</span>
        <span class="weather-row-value">${val(tod.pop_pct, '%')}${tod.pop_window ? ' ' + esc(tod.pop_window) : ''}</span>
       </div>`
    : '';
  const daylightHtml = tod.daylight_until
    ? `<div class="weather-row">
        <span class="weather-row-label">Daylight until</span>
        <span class="weather-row-value">${esc(tod.daylight_until)}</span>
       </div>`
    : '';

  const todayCol = `<div>
    <div class="weather-section-label">Today</div>
    <div class="weather-temp-secondary">${hiloHtml}</div>
    <div class="weather-detail-rows">
      ${heatIdxHtml}
      ${popHtml}
      ${daylightHtml}
      ${tod.summary ? `<div class="weather-summary-pill">${esc(tod.summary)}</div>` : ''}
    </div>
  </div>`;

  bodyHtml += `<div class="weather-grid">${curCol}${todayCol}</div>`;

  /* AQI callout if present */
  const aqi = (state.hazards || {}).aqi_callout;
  if (aqi) {
    bodyHtml += `<div class="aqi-callout" role="note" aria-label="Air quality: ${esc(aqi.label)}, AQI ${aqi.aqi}">
      <i aria-hidden="true">&#9680;</i>
      <strong>AQI ${val(aqi.aqi)}</strong>
      &mdash; ${esc(aqi.label)} &mdash; ${esc(aqi.category)}
    </div>`;
  }

  return `<div class="slide-inner">
    <div class="slide-title-bar">
      <h2 class="slide-title">Weather</h2>
      ${loc ? `<span class="slide-subtitle">${esc(loc)}</span>` : ''}
    </div>
    <div class="slide-body">${bodyHtml}</div>
    ${slideFooter(src)}
  </div>`;
}

/**
 * Slide 3 (morning only): Disruptions & Alerts
 * Renders disruptions.traffic + disruptions.alerts.
 * Degraded banner when disruptions source is stale/down.
 */
function buildDisruptionsSlide(state) {
  const d       = state.disruptions || {};
  const traffic = Array.isArray(d.traffic) ? d.traffic : [];
  const alerts  = Array.isArray(d.alerts)  ? d.alerts  : [];
  const src     = d.source || {};
  const deg     = isDegraded(src);

  let bodyHtml = '';
  if (deg) bodyHtml += degradedBanner(src);

  /* Traffic events */
  let trafficHtml;
  if (traffic.length === 0) {
    trafficHtml = `<li class="no-data-placeholder" role="listitem">No reported traffic events.</li>`;
  } else {
    trafficHtml = traffic.map(ev => {
      const type    = (ev.type || 'default').toLowerCase();
      const icon    = EVENT_ICONS[type] || EVENT_ICONS.default;
      const typeLbl = type !== 'default' ? type.toUpperCase() : '';
      return `<li class="event-item ${esc(type)}" role="listitem">
        <span class="event-icon" aria-hidden="true">${icon}</span>
        <span class="event-text">${esc(ev.text)}</span>
        ${typeLbl ? `<span class="event-type-badge" aria-label="Event type: ${typeLbl}">${typeLbl}</span>` : ''}
      </li>`;
    }).join('');
  }

  /* NWS alerts */
  let alertsHtml;
  if (alerts.length === 0) {
    alertsHtml = `<li class="no-data-placeholder" role="listitem">No active NWS alerts.</li>`;
  } else {
    alertsHtml = alerts.map(al => {
      const sev    = al.severity || 'info';
      const m      = SEV_META[sev] || SEV_META.info;
      const typeCls = `alert-${sev}`;
      return `<li class="event-item ${typeCls}" role="listitem"
               aria-label="${m.label}: ${esc(al.text)}">
        <span class="event-icon" aria-hidden="true">${m.icon}</span>
        <span class="event-text">${esc(al.text)}</span>
        <span class="event-type-badge" aria-label="Severity: ${m.label}">${m.label}</span>
      </li>`;
    }).join('');
  }

  bodyHtml += `
    <div>
      <div class="disruptions-section-title">Traffic (511GA)</div>
      <ul class="event-list" aria-label="Traffic events">${trafficHtml}</ul>
    </div>
    <div>
      <div class="disruptions-section-title">Alerts (NWS)</div>
      <ul class="event-list" aria-label="NWS alerts">${alertsHtml}</ul>
    </div>`;

  return `<div class="slide-inner">
    <div class="slide-title-bar">
      <h2 class="slide-title">Disruptions &amp; Alerts</h2>
    </div>
    <div class="slide-body">${bodyHtml}</div>
    ${slideFooter(src)}
  </div>`;
}

/**
 * Slide 4 (both modes): 3-Day Look Ahead
 * Renders forecast_3day.days + spc_outlook.
 */
function buildForecastSlide(state) {
  const f    = state.forecast_3day || {};
  const days = Array.isArray(f.days) ? f.days : [];
  const spc  = f.spc_outlook || null;
  const src  = f.source || {};
  const deg  = isDegraded(src);

  let bodyHtml = '';
  if (deg) bodyHtml += degradedBanner(src);

  /* Day cards */
  let cardsHtml = '';
  if (days.length === 0) {
    cardsHtml = `<p class="no-data-placeholder">Forecast unavailable.</p>`;
  } else {
    const cards = days.map(day => {
      const iconKey = weatherIconKey(day.icon);
      const iconSvg = WEATHER_ICONS[iconKey] || WEATHER_ICONS.unknown;
      return `<div class="forecast-day-card" aria-label="${esc(day.name)}: high ${val(day.high_f, '°F')}, low ${val(day.low_f, '°F')}, ${esc(day.summary || '')}">
        <div class="forecast-day-name">${esc(day.name)}</div>
        <div class="forecast-day-icon" aria-hidden="true">${iconSvg}</div>
        <div class="forecast-temps">
          ${val(day.high_f, '°F')} / <span class="low">${val(day.low_f, '°F')}</span>
        </div>
        <div class="forecast-day-summary">${esc(day.summary || '')}</div>
      </div>`;
    }).join('');
    cardsHtml = `<div class="forecast-days" aria-label="3-day forecast">${cards}</div>`;
  }

  /* SPC outlook banner */
  let spcHtml = '';
  if (spc && spc.text) {
    const cat    = (spc.category || 'general').toLowerCase();
    const catLbl = SPC_LABELS[cat] || esc(cat);
    spcHtml = `<div class="spc-banner spc-${esc(cat)}"
                    role="note"
                    aria-label="SPC outlook: ${catLbl} — ${esc(spc.text)}">
      <strong>SPC Outlook:</strong>
      <span>${esc(catLbl)}</span>
      &mdash;
      <span>${esc(spc.text)}</span>
    </div>`;
  } else if (spc === null) {
    spcHtml = `<div class="spc-banner spc-general" role="note" aria-label="SPC outlook unavailable">
      <strong>SPC Outlook:</strong> <span>&mdash;</span>
    </div>`;
  }

  bodyHtml += cardsHtml + spcHtml;

  return `<div class="slide-inner">
    <div class="slide-title-bar">
      <h2 class="slide-title">3-Day Look Ahead</h2>
    </div>
    <div class="slide-body">${bodyHtml}</div>
    ${slideFooter(src)}
  </div>`;
}

/**
 * Slide 5 (afternoon only): PM Commute
 * Renders commute.current + commute.traffic.
 */
function buildCommuteSlide(state) {
  const c       = state.commute || {};
  const cur     = c.current || {};
  const traffic = Array.isArray(c.traffic) ? c.traffic : [];
  const src     = c.source || {};
  const deg     = isDegraded(src);

  let bodyHtml = '';
  if (deg) bodyHtml += degradedBanner(src);

  /* Current conditions row */
  bodyHtml += `<div class="commute-now-row">
    <div class="commute-temp-block">
      <div class="weather-temp-primary">${val(cur.temp_f, '°F')}</div>
      <div class="weather-temp-secondary">feels ${val(cur.feels_like_f, '°F')}</div>
    </div>
    ${cur.summary ? `<div class="commute-summary-block">${esc(cur.summary)}</div>` : ''}
  </div>`;

  /* Traffic */
  let trafficHtml;
  if (traffic.length === 0) {
    trafficHtml = `<li class="no-data-placeholder" role="listitem">No reported traffic events.</li>`;
  } else {
    trafficHtml = traffic.map(ev => {
      const type = (ev.type || 'default').toLowerCase();
      const icon = EVENT_ICONS[type] || EVENT_ICONS.default;
      return `<li class="event-item ${esc(type)}" role="listitem">
        <span class="event-icon" aria-hidden="true">${icon}</span>
        <span class="event-text">${esc(ev.text)}</span>
        ${type !== 'default' ? `<span class="event-type-badge" aria-label="Event type: ${type.toUpperCase()}">${type.toUpperCase()}</span>` : ''}
      </li>`;
    }).join('');
  }

  bodyHtml += `<div>
    <div class="disruptions-section-title">Traffic (511GA)</div>
    <ul class="event-list" aria-label="PM commute traffic">${trafficHtml}</ul>
  </div>`;

  return `<div class="slide-inner">
    <div class="slide-title-bar">
      <h2 class="slide-title">PM Commute</h2>
    </div>
    <div class="slide-body">${bodyHtml}</div>
    ${slideFooter(src)}
  </div>`;
}

/* ── Slide set builder ──────────────────────────────────────────────────── */

/**
 * Returns an array of { id, html } slide descriptors for the given state.
 * Morning:   Briefing, Weather, Disruptions, 3-Day
 * Afternoon: Weather, PM Commute, 3-Day
 */
function buildSlides(state) {
  const mode = (state.display || {}).mode || 'morning';
  if (mode === 'afternoon') {
    return [
      { id: 'weather',    html: buildWeatherSlide(state)    },
      { id: 'commute',    html: buildCommuteSlide(state)    },
      { id: 'forecast',   html: buildForecastSlide(state)   },
    ];
  }
  // morning (default)
  return [
    { id: 'briefing',   html: buildBriefingSlide(state)  },
    { id: 'weather',    html: buildWeatherSlide(state)    },
    { id: 'disruptions',html: buildDisruptionsSlide(state)},
    { id: 'forecast',   html: buildForecastSlide(state)   },
  ];
}

/* ── Carousel rendering ──────────────────────────────────────────────────── */

function renderCarousel(state) {
  slides = buildSlides(state);

  /* Inject slide DOM */
  $carousel.innerHTML = slides.map((s, i) =>
    `<section class="slide${i === activeSlideIdx ? ' active' : ''}"
              id="slide-${s.id}"
              role="region"
              aria-label="Slide ${i + 1} of ${slides.length}"
              aria-hidden="${i !== activeSlideIdx}">
      ${s.html}
    </section>`
  ).join('');

  /* Inject dots */
  $dots.innerHTML = slides.map((s, i) =>
    `<button class="dot${i === activeSlideIdx ? ' active' : ''}"
             aria-label="Slide ${i + 1}${i === activeSlideIdx ? ' (current)' : ''}"
             aria-current="${i === activeSlideIdx}"
             data-idx="${i}">
    </button>`
  ).join('');

  /* Dot click: jump to that slide */
  $dots.querySelectorAll('.dot').forEach(btn => {
    btn.addEventListener('click', () => {
      goToSlide(Number(btn.dataset.idx));
      resetCarouselTimer(state);
    });
  });
}

function updateCarousel(state) {
  const newSlides = buildSlides(state);

  /* If slide count or mode changed, re-render from scratch */
  if (newSlides.length !== slides.length) {
    activeSlideIdx = 0;
    renderCarousel(state);
    return;
  }

  /* Otherwise update in-place to avoid visible flash */
  slides = newSlides;
  const slideEls = $carousel.querySelectorAll('.slide');
  slides.forEach((s, i) => {
    if (slideEls[i]) slideEls[i].innerHTML = s.html;
  });
}

function goToSlide(idx) {
  const slideEls = $carousel.querySelectorAll('.slide');
  const dotEls   = $dots.querySelectorAll('.dot');

  if (slideEls[activeSlideIdx]) {
    slideEls[activeSlideIdx].classList.remove('active');
    slideEls[activeSlideIdx].setAttribute('aria-hidden', 'true');
  }
  if (dotEls[activeSlideIdx]) {
    dotEls[activeSlideIdx].classList.remove('active');
    dotEls[activeSlideIdx].setAttribute('aria-current', 'false');
    dotEls[activeSlideIdx].removeAttribute('aria-label');
    dotEls[activeSlideIdx].setAttribute('aria-label', `Slide ${activeSlideIdx + 1}`);
  }

  activeSlideIdx = idx;

  if (slideEls[activeSlideIdx]) {
    slideEls[activeSlideIdx].classList.add('active');
    slideEls[activeSlideIdx].setAttribute('aria-hidden', 'false');
  }
  if (dotEls[activeSlideIdx]) {
    dotEls[activeSlideIdx].classList.add('active');
    dotEls[activeSlideIdx].setAttribute('aria-current', 'true');
    dotEls[activeSlideIdx].setAttribute('aria-label', `Slide ${activeSlideIdx + 1} (current)`);
  }
}

function advanceSlide() {
  if (slides.length === 0) return;
  goToSlide((activeSlideIdx + 1) % slides.length);
}

function resetCarouselTimer(state) {
  if (carouselTimer) clearInterval(carouselTimer);
  const dwell = ((state.display || {}).dwell_seconds || DEFAULT_DWELL_S) * 1000;
  carouselTimer = setInterval(advanceSlide, dwell);
}

/* ── Header rendering ────────────────────────────────────────────────────── */

function renderHeader(state) {
  const loc  = (state.location || {}).name || 'Field Location';
  const mode = (state.display  || {}).mode || 'morning';

  $loc.textContent = loc;

  $modeBadge.className = `header-mode-badge ${mode}`;
  $modeBadge.textContent = mode === 'afternoon' ? 'Afternoon' : 'Morning';
}

function startClock() {
  function tick() {
    const now = new Date();
    const days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
    const mons = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    const dow  = days[now.getDay()];
    const mon  = mons[now.getMonth()];
    const d    = now.getDate();
    const hh   = String(now.getHours()).padStart(2, '0');
    const mm   = String(now.getMinutes()).padStart(2, '0');
    $datetime.textContent = `${dow} ${d} ${mon}  ${hh}:${mm}`;
  }
  tick();
  clockTimer = setInterval(tick, 10000); // update every 10 s
}

/* ── Data fetching ───────────────────────────────────────────────────────── */

/**
 * Resolve which URL to fetch.
 * ?fixture=morning | afternoon | degraded  -> fetch ./fixtures/<name>.json
 * (no param)                               -> fetch /api/state
 */
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

async function fetchState() {
  const resp = await fetch(DATA_URL, {
    cache: 'no-store',
    headers: { 'Accept': 'application/json' },
  });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  const data = await resp.json();
  return data;
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

    renderHeader(state);

    if (firstLoad) {
      /* First load: full render */
      $loading.classList.add('hidden');
      renderCarousel(state);
      resetCarouselTimer(state);
    } else {
      /* Subsequent polls: update slides in-place */
      updateCarousel(state);
      /* Re-arm the carousel timer in case dwell_seconds changed */
      resetCarouselTimer(state);
    }

  } catch (err) {
    console.warn('[SITREP] Fetch failed:', err.message);
    if (currentState === null) {
      /* Never had good data — show error screen */
      $loading.classList.add('hidden');
      $errorDet.textContent = err.message || 'Network error';
      $errorScr.classList.add('visible');
    } else {
      /* Keep showing last good state; show reconnecting indicator */
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
  if (currentState) schedulePoll(currentState);
})();
