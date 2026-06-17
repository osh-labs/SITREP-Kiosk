#!/usr/bin/env bash
# =============================================================================
# install.sh — Idempotent installer for the Field SITREP Board (M3)
#
# Run as root (or with sudo) on the kiosk mini PC.
# Safe to re-run: it skips steps that are already done.
#
# USAGE:
#   sudo bash deploy/install.sh [--install-dir PATH] [--kiosk-user USER]
#
# OPTIONS:
#   --install-dir PATH   Absolute path where the repo lives / will live.
#                        Default: /opt/sitrep
#   --kiosk-user USER    Non-root OS user that will run the kiosk session.
#                        Default: kiosk
#
# WHAT IT DOES (in order):
#   1. Check prerequisites (Python 3.11+, Chromium or Google Chrome).
#   2. Create the kiosk OS user if it does not exist.
#   3. Create a Python virtual environment at ${INSTALL_DIR}/.venv and
#      pip-install -r requirements.txt.
#   4. Copy config/config.example.yaml -> config/config.yaml (if absent).
#   5. Copy .env.example -> .env (if absent), then warn to fill in keys.
#   6. Substitute placeholders in the systemd unit file, copy it to
#      /etc/systemd/system/, enable and start the service.
#   7. Install the desktop autostart entry for the kiosk user.
#
# ASSUMPTIONS — read before deploying:
#
#   BACKEND ENTRYPOINT:
#     ExecStart uses:  ${INSTALL_DIR}/.venv/bin/python -m backend.sitrep
#     run from WorkingDirectory=${INSTALL_DIR} (the repo root).
#     This works when the package layout is backend/sitrep/__init__.py,
#     which is what the backend agent has built.  If the entrypoint changes
#     (e.g. to "python -m sitrep" launched from backend/, or a uvicorn call),
#     update EXEC_START in this script and re-run install.sh.
#
#   VENV LOCATION:
#     ${INSTALL_DIR}/.venv
#     If you want the venv elsewhere, override VENV_DIR before running.
#
#   DISTRO:
#     Assumes Debian/Ubuntu.  Package names (chromium, python3.11, etc.) may
#     differ on Fedora/RHEL/Arch; comments note where differences appear.
#
#   DISPLAY MANAGER:
#     Assumes a GNOME-compatible display manager (LightDM, GDM) that honours
#     ~/.config/autostart/*.desktop.  On non-GNOME setups you may need to wire
#     kiosk.sh into the session a different way (see README.md §Autostart).
# =============================================================================

set -euo pipefail

# ── Defaults — override via CLI flags ────────────────────────────────────────
INSTALL_DIR="/opt/sitrep"
KIOSK_USER="kiosk"

# ── Parse CLI flags ──────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --install-dir)
            INSTALL_DIR="$2"; shift 2 ;;
        --kiosk-user)
            KIOSK_USER="$2"; shift 2 ;;
        -h|--help)
            grep '^#' "$0" | head -40; exit 0 ;;
        *)
            echo "Unknown flag: $1" >&2; exit 1 ;;
    esac
done

# Derived paths
VENV_DIR="${INSTALL_DIR}/.venv"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# ── Helpers ──────────────────────────────────────────────────────────────────
step()    { echo; echo "==> $*"; }
info()    { echo "    $*"; }
warn()    { echo "    WARNING: $*" >&2; }
success() { echo "    OK: $*"; }
fail()    { echo "    FATAL: $*" >&2; exit 1; }

require_root() {
    if [[ "${EUID}" -ne 0 ]]; then
        fail "This script must be run as root (use sudo)."
    fi
}

# ── 0. Root check ─────────────────────────────────────────────────────────────
require_root

step "Field SITREP Board — install/update"
info "INSTALL_DIR : ${INSTALL_DIR}"
info "KIOSK_USER  : ${KIOSK_USER}"
info "VENV_DIR    : ${VENV_DIR}"
info "Repo root   : ${REPO_ROOT}"

# ── 0b. Install required OS packages (Debian/Ubuntu) ─────────────────────────
step "Installing required OS packages"
if command -v apt-get &>/dev/null; then
    PKGS=()
    command -v curl &>/dev/null            || PKGS+=(curl)
    python3 -m venv --help &>/dev/null     || PKGS+=(python3-venv)
    command -v xset &>/dev/null            || PKGS+=(x11-xserver-utils)
    if ! command -v chromium &>/dev/null && ! command -v chromium-browser &>/dev/null \
         && ! command -v google-chrome &>/dev/null; then
        PKGS+=(chromium-browser)   # Ubuntu 24.04: this pulls the Chromium snap
    fi
    if (( ${#PKGS[@]} > 0 )); then
        info "Installing: ${PKGS[*]}"
        apt-get update -qq || warn "apt-get update failed (continuing)"
        if apt-get install -y "${PKGS[@]}"; then
            success "Installed: ${PKGS[*]}"
        else
            warn "apt-get install failed; install manually: ${PKGS[*]}"
        fi
    else
        success "All required OS packages already present"
    fi
else
    warn "apt-get not found — ensure python3-venv, chromium, curl, x11-xserver-utils are installed."
fi

# ── 1. Prerequisite checks ────────────────────────────────────────────────────
step "Checking prerequisites"

# Python 3.11+
PYTHON_BIN=""
for candidate in python3.12 python3.11 python3; do
    if command -v "$candidate" &>/dev/null; then
        PY_VER="$("$candidate" -c 'import sys; print(sys.version_info[:2])')"
        # Accept (3, 11) or higher
        if "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)' 2>/dev/null; then
            PYTHON_BIN="$candidate"
            break
        fi
    fi
done

if [[ -z "${PYTHON_BIN}" ]]; then
    fail "Python 3.11+ is required but not found. Install with: apt install python3.11"
fi
success "Python: $("${PYTHON_BIN}" --version)"

# pip / venv module
if ! "${PYTHON_BIN}" -m venv --help &>/dev/null; then
    # Debian/Ubuntu ships venv separately
    fail "Python venv module missing. Install with: apt install python3-venv"
fi
success "Python venv module: available"

# Chromium
CHROMIUM_FOUND=false
for cb in chromium chromium-browser google-chrome google-chrome-stable; do
    if command -v "$cb" &>/dev/null; then
        success "Chromium binary: $cb ($(command -v "$cb"))"
        CHROMIUM_FOUND=true
        break
    fi
done
if ! "${CHROMIUM_FOUND}"; then
    warn "No Chromium binary found. Install with: apt install chromium"
    warn "The backend service will still be installed; the kiosk won't launch until Chromium is present."
fi

# curl (needed by kiosk.sh health polling)
if ! command -v curl &>/dev/null; then
    fail "curl is required (used by kiosk.sh). Install with: apt install curl"
fi
success "curl: $(command -v curl)"

# xset (optional — absence is non-fatal; kiosk.sh handles gracefully)
if command -v xset &>/dev/null; then
    success "xset: $(command -v xset)"
else
    warn "xset not found; screen blanking won't be disabled automatically."
    warn "Install with: apt install x11-xserver-utils"
fi

# ── 2. Kiosk OS user ─────────────────────────────────────────────────────────
step "Ensuring kiosk OS user '${KIOSK_USER}'"

if id "${KIOSK_USER}" &>/dev/null; then
    success "User '${KIOSK_USER}' already exists"
else
    # --disabled-password: can still log in via PAM/display manager
    # --gecos: skip interactive prompt on Debian/Ubuntu
    useradd \
        --create-home \
        --shell /bin/bash \
        --comment "SITREP kiosk user" \
        --groups video,audio \
        --disabled-password \
        --gecos "" \
        "${KIOSK_USER}"
    success "Created user '${KIOSK_USER}'"
    info "Set a password if needed: passwd ${KIOSK_USER}"
fi

# Ensure the install dir is accessible to the kiosk user
if [[ "${INSTALL_DIR}" == "${REPO_ROOT}" ]]; then
    # Running from an in-place repo; fix ownership
    chown -R "${KIOSK_USER}:${KIOSK_USER}" "${INSTALL_DIR}"
    info "Ownership of ${INSTALL_DIR} set to ${KIOSK_USER}"
fi

# ── 3. Python virtual environment + dependencies ─────────────────────────────
step "Setting up Python venv at ${VENV_DIR}"

if [[ ! -f "${VENV_DIR}/bin/python" ]]; then
    "${PYTHON_BIN}" -m venv "${VENV_DIR}"
    success "Created venv"
else
    success "Venv already exists — skipping creation"
fi

info "Installing / updating requirements.txt..."
"${VENV_DIR}/bin/pip" install --quiet --upgrade pip
"${VENV_DIR}/bin/pip" install --quiet -r "${REPO_ROOT}/requirements.txt"
success "Python dependencies installed"

# Fix ownership so the kiosk user can use the venv
chown -R "${KIOSK_USER}:${KIOSK_USER}" "${VENV_DIR}"

# ── 4. Config file ────────────────────────────────────────────────────────────
step "Ensuring config/config.yaml"

CONFIG_DEST="${INSTALL_DIR}/config/config.yaml"
CONFIG_SRC="${INSTALL_DIR}/config/config.example.yaml"

if [[ -f "${CONFIG_DEST}" ]]; then
    success "config/config.yaml already exists — not overwriting"
else
    if [[ -f "${CONFIG_SRC}" ]]; then
        cp "${CONFIG_SRC}" "${CONFIG_DEST}"
        chown "${KIOSK_USER}:${KIOSK_USER}" "${CONFIG_DEST}"
        success "Copied config.example.yaml -> config.yaml"
        warn "Review ${CONFIG_DEST} and adjust location, thresholds, and dwell times."
    else
        fail "config/config.example.yaml not found at ${CONFIG_SRC}"
    fi
fi

# ── 5. .env file ──────────────────────────────────────────────────────────────
step "Ensuring .env secrets file"

ENV_DEST="${INSTALL_DIR}/.env"
ENV_SRC="${INSTALL_DIR}/.env.example"

if [[ -f "${ENV_DEST}" ]]; then
    success ".env already exists — not overwriting"
else
    if [[ -f "${ENV_SRC}" ]]; then
        cp "${ENV_SRC}" "${ENV_DEST}"
        chmod 600 "${ENV_DEST}"          # secrets: readable only by owner
        chown "${KIOSK_USER}:${KIOSK_USER}" "${ENV_DEST}"
        success "Copied .env.example -> .env (mode 600)"
    else
        fail ".env.example not found at ${ENV_SRC}"
    fi
    warn "*** ACTION REQUIRED: fill in API keys in ${ENV_DEST} ***"
    warn "    GA511_API_KEY, AIRNOW_API_KEY, ANTHROPIC_API_KEY"
fi

# ── 6. Systemd service unit ───────────────────────────────────────────────────
step "Installing systemd service unit"

UNIT_TEMPLATE="${SCRIPT_DIR}/sitrep-backend.service"
UNIT_DEST="/etc/systemd/system/sitrep-backend.service"

if [[ ! -f "${UNIT_TEMPLATE}" ]]; then
    fail "Service template not found: ${UNIT_TEMPLATE}"
fi

# Perform placeholder substitution into a temp file, then copy
TMP_UNIT="$(mktemp)"
sed \
    -e "s|__INSTALL_DIR__|${INSTALL_DIR}|g" \
    -e "s|__KIOSK_USER__|${KIOSK_USER}|g" \
    -e "s|__VENV_DIR__|${VENV_DIR}|g" \
    "${UNIT_TEMPLATE}" > "${TMP_UNIT}"

# Only update if the file changed (idempotent)
if [[ -f "${UNIT_DEST}" ]] && diff -q "${TMP_UNIT}" "${UNIT_DEST}" &>/dev/null; then
    success "Service unit is already up to date"
    rm "${TMP_UNIT}"
else
    mv "${TMP_UNIT}" "${UNIT_DEST}"
    chmod 644 "${UNIT_DEST}"
    success "Installed ${UNIT_DEST}"
fi

# Reload systemd and enable the service
systemctl daemon-reload
systemctl enable sitrep-backend.service
success "Service enabled (starts on next boot)"

# Start / restart the service now
if systemctl is-active --quiet sitrep-backend.service; then
    systemctl restart sitrep-backend.service
    success "Service restarted"
else
    systemctl start sitrep-backend.service
    success "Service started"
fi

# ── 7. Desktop autostart entry ────────────────────────────────────────────────
step "Installing kiosk autostart entry"

DESKTOP_SRC="${SCRIPT_DIR}/sitrep-kiosk.desktop"
KIOSK_HOME="$(getent passwd "${KIOSK_USER}" | cut -d: -f6)"
AUTOSTART_DIR="${KIOSK_HOME}/.config/autostart"

if [[ ! -f "${DESKTOP_SRC}" ]]; then
    fail "Desktop entry template not found: ${DESKTOP_SRC}"
fi

mkdir -p "${AUTOSTART_DIR}"

# Skip the GNOME first-login setup wizard for the kiosk user so the desktop
# (and therefore the kiosk autostart) comes up clean on the very first login.
echo "yes" > "${KIOSK_HOME}/.config/gnome-initial-setup-done"
chown "${KIOSK_USER}:${KIOSK_USER}" "${KIOSK_HOME}/.config/gnome-initial-setup-done"

DESKTOP_DEST="${AUTOSTART_DIR}/sitrep-kiosk.desktop"

# Substitute __INSTALL_DIR__ placeholder
TMP_DESKTOP="$(mktemp)"
sed \
    -e "s|__INSTALL_DIR__|${INSTALL_DIR}|g" \
    "${DESKTOP_SRC}" > "${TMP_DESKTOP}"

if [[ -f "${DESKTOP_DEST}" ]] && diff -q "${TMP_DESKTOP}" "${DESKTOP_DEST}" &>/dev/null; then
    success "Autostart entry is already up to date"
    rm "${TMP_DESKTOP}"
else
    mv "${TMP_DESKTOP}" "${DESKTOP_DEST}"
    chown -R "${KIOSK_USER}:${KIOSK_USER}" "${KIOSK_HOME}/.config"
    chmod 644 "${DESKTOP_DEST}"
    success "Installed ${DESKTOP_DEST}"
fi

# ── 7b. GDM auto-login ────────────────────────────────────────────────────────
# The board must come back unattended after a power loss (NFR-2). On Ubuntu
# Desktop (GDM3) that means enabling auto-login for the kiosk user.
step "Configuring GDM auto-login for '${KIOSK_USER}'"
GDM_CONF="/etc/gdm3/custom.conf"
if [[ -d /etc/gdm3 ]]; then
    [[ -f "${GDM_CONF}" && ! -f "${GDM_CONF}.sitrep.bak" ]] && cp "${GDM_CONF}" "${GDM_CONF}.sitrep.bak"
    # Edit the [daemon] section idempotently with Python's configparser.
    python3 - "${GDM_CONF}" "${KIOSK_USER}" <<'PYEOF'
import sys, os, configparser
conf, user = sys.argv[1], sys.argv[2]
cp = configparser.ConfigParser()
cp.optionxform = str
if os.path.exists(conf):
    cp.read(conf)
if not cp.has_section("daemon"):
    cp.add_section("daemon")
cp.set("daemon", "AutomaticLoginEnable", "true")
cp.set("daemon", "AutomaticLogin", user)
with open(conf, "w") as fh:
    cp.write(fh)
PYEOF
    success "Auto-login enabled for '${KIOSK_USER}' in ${GDM_CONF} (backup: ${GDM_CONF}.sitrep.bak)"
    info "A Wayland GNOME session will auto-start and fire the kiosk autostart entry."
else
    warn "GDM3 not found (/etc/gdm3 missing). Enable auto-login for '${KIOSK_USER}'"
    warn "in your display manager manually — see deploy/README.md."
fi

# ── 8. Make kiosk.sh executable ───────────────────────────────────────────────
step "Ensuring kiosk.sh is executable"
chmod +x "${SCRIPT_DIR}/kiosk.sh"
success "kiosk.sh is executable"

# ── 9. Summary ────────────────────────────────────────────────────────────────
echo
echo "============================================================"
echo " Field SITREP Board — installation complete"
echo "============================================================"
echo ""
echo " Backend service:"
echo "   systemctl status sitrep-backend"
echo "   journalctl -u sitrep-backend -f"
echo ""
echo " Health check:"
echo "   curl http://localhost:8080/healthz"
echo "   curl http://localhost:8080/api/state"
echo ""
echo " Kiosk (autostart on next login as '${KIOSK_USER}'):"
echo "   ${INSTALL_DIR}/deploy/kiosk.sh"
echo ""

# Final warnings about unfilled secrets
if grep -qE '^(GA511_API_KEY|AIRNOW_API_KEY|ANTHROPIC_API_KEY)=$' "${ENV_DEST}" 2>/dev/null; then
    echo " *** API keys are empty in ${ENV_DEST} ***"
    echo "     Fill them in, then run:  systemctl restart sitrep-backend"
    echo ""
fi

echo " See deploy/README.md for the full operator runbook."
echo "============================================================"
