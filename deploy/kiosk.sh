#!/usr/bin/env bash
# =============================================================================
# kiosk.sh — Launch Chromium in kiosk mode for the Field SITREP Board
#
# ASSUMPTIONS:
#   - SITREP_PORT defaults to 8080 (matches .env.example).
#   - The backend exposes GET /healthz (HTTP 200) when ready.
#     If the backend uses a different health endpoint (e.g. /api/health),
#     change HEALTH_URL below.  Flag this to the backend agent.
#   - X11 session is already running (called from autostart; see kiosk.desktop).
#   - Runs as the kiosk user (not root).
#
# WHAT THIS SCRIPT DOES:
#   1. Disables display sleep / screen blanking (xset, if X is available).
#   2. Polls the backend /healthz until it responds 200 (with a timeout).
#   3. Launches Chromium in kiosk mode.
#   4. Loops: if Chromium exits for any reason, re-checks health and relaunches.
#
# DISTRO NOTE:
#   Tested against Debian/Ubuntu naming conventions.  On Fedora/RHEL the
#   binary is often "chromium" rather than "chromium-browser".  The script
#   tries chromium, chromium-browser, google-chrome in that order.
# =============================================================================

set -euo pipefail

# ── Configuration ─────────────────────────────────────────────────────────────
SITREP_PORT="${SITREP_PORT:-8080}"
KIOSK_URL="http://localhost:${SITREP_PORT}"
HEALTH_URL="${KIOSK_URL}/healthz"

# How long (seconds) to wait for the backend before giving up on health poll.
HEALTH_TIMEOUT=120
# Seconds between health-check attempts.
HEALTH_POLL_INTERVAL=2
# Seconds to wait before relaunching Chromium after an exit.
RELAUNCH_DELAY=3

# ── Logging helpers ───────────────────────────────────────────────────────────
log()  { echo "[kiosk] $(date '+%Y-%m-%d %H:%M:%S') $*"; }
warn() { echo "[kiosk] $(date '+%Y-%m-%d %H:%M:%S') WARNING: $*" >&2; }
die()  { echo "[kiosk] $(date '+%Y-%m-%d %H:%M:%S') FATAL: $*" >&2; exit 1; }

# ── 1. Display power management ───────────────────────────────────────────────
# Disable screen blanking / sleep. Ubuntu 24.04 GNOME defaults to a *Wayland*
# session where xset is a no-op, so we also drive GNOME via gsettings. Both
# paths are guarded and best-effort (|| true) so neither aborts the kiosk.
disable_screen_blanking() {
    # X11 path (works on Xorg sessions / XWayland)
    if [[ -n "${DISPLAY:-}" ]] && command -v xset &>/dev/null; then
        log "Disabling X11 screen blanking (xset)"
        xset s off     || true   # disable screen saver
        xset -dpms     || true   # disable DPMS power management
        xset s noblank || true   # disable screen blanking
    fi
    # GNOME / Wayland path (Ubuntu 24.04 default)
    if command -v gsettings &>/dev/null; then
        log "Disabling GNOME idle/blank/lock (gsettings)"
        gsettings set org.gnome.desktop.session idle-delay 0 || true
        gsettings set org.gnome.desktop.screensaver idle-activation-enabled false || true
        gsettings set org.gnome.desktop.screensaver lock-enabled false || true
        gsettings set org.gnome.settings-daemon.plugins.power sleep-inactive-ac-type 'nothing' || true
        gsettings set org.gnome.settings-daemon.plugins.power sleep-inactive-battery-type 'nothing' || true
    fi
    if [[ -z "${DISPLAY:-}" && -z "${WAYLAND_DISPLAY:-}" ]]; then
        warn "Neither DISPLAY nor WAYLAND_DISPLAY is set — not in a graphical session yet"
    fi
}

disable_screen_blanking

# ── 2. Locate a Chromium binary ───────────────────────────────────────────────
find_chromium() {
    local candidates=(chromium chromium-browser google-chrome google-chrome-stable)
    for bin in "${candidates[@]}"; do
        if command -v "$bin" &>/dev/null; then
            echo "$bin"
            return 0
        fi
    done
    return 1
}

CHROMIUM_BIN=""
if ! CHROMIUM_BIN="$(find_chromium)"; then
    die "No Chromium binary found. Install chromium or google-chrome and retry."
fi
log "Using Chromium binary: $CHROMIUM_BIN"

# ── 3. Wait for backend health ────────────────────────────────────────────────
wait_for_backend() {
    log "Waiting for backend at ${HEALTH_URL} (timeout: ${HEALTH_TIMEOUT}s)"
    local elapsed=0
    while (( elapsed < HEALTH_TIMEOUT )); do
        if curl --silent --fail --max-time 2 "${HEALTH_URL}" &>/dev/null; then
            log "Backend is healthy — launching kiosk"
            return 0
        fi
        sleep "${HEALTH_POLL_INTERVAL}"
        (( elapsed += HEALTH_POLL_INTERVAL ))
    done
    warn "Backend did not respond within ${HEALTH_TIMEOUT}s — launching kiosk anyway (will show error page until backend comes up)"
    return 0  # Don't block; Chromium will show its own error page until backend is up.
}

# ── 4. Chromium flags ─────────────────────────────────────────────────────────
# From CLAUDE.md: --kiosk --noerrdialogs --disable-session-crashed-bubble --incognito
# Additional hardening flags added below.
CHROMIUM_FLAGS=(
    # Core kiosk flags (CLAUDE.md mandated)
    "--kiosk"
    "--noerrdialogs"
    "--disable-session-crashed-bubble"
    "--incognito"

    # Wayland-native when available (Ubuntu 24.04 GNOME), else falls back to XWayland
    "--ozone-platform-hint=auto"

    # UI noise suppression
    "--disable-infobars"
    "--disable-translate"
    "--no-first-run"
    "--no-default-browser-check"

    # Gesture / touch
    "--disable-pinch"

    # Auto-update: set a very long check interval (seconds) to avoid
    # update dialogs during kiosk operation.
    "--check-for-update-interval=604800"

    # Crash recovery suppression (belt-and-suspenders with the above)
    "--disable-hang-monitor"
    "--disable-client-side-phishing-detection"

    # Target URL
    "${KIOSK_URL}"
)

# ── 5. Kiosk loop — relaunch on exit ─────────────────────────────────────────
log "Entering kiosk loop for ${KIOSK_URL}"
while true; do
    wait_for_backend

    log "Starting: ${CHROMIUM_BIN} ${CHROMIUM_FLAGS[*]}"
    # Run Chromium; capture exit code but don't let set -e kill the loop.
    "${CHROMIUM_BIN}" "${CHROMIUM_FLAGS[@]}" || EXIT_CODE=$?
    EXIT_CODE="${EXIT_CODE:-0}"

    log "Chromium exited with code ${EXIT_CODE}; relaunching in ${RELAUNCH_DELAY}s"
    sleep "${RELAUNCH_DELAY}"
done
