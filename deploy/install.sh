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
#   0b. Install OS packages (Xorg, xinit, Openbox, Chromium, curl, venv).
#   1.  Check prerequisites (Python 3.11+, Chromium).
#   2.  Create the kiosk OS user (+ X groups, Xwrapper) if needed.
#   3.  Create a Python venv at ${INSTALL_DIR}/.venv and pip-install requirements.
#   4.  Copy config/config.example.yaml -> config/config.yaml (if absent).
#   5.  Copy .env.example -> .env (if absent), then warn to fill in keys.
#   6.  Install/enable/start the backend systemd service.
#   7.  Configure tty1 console auto-login for the kiosk user.
#   7b. Install the X session (~/.xinitrc -> Openbox -> kiosk.sh) + ~/.bash_profile.
#
# DESIGN: minimal X + Openbox kiosk (no desktop environment, no display manager).
#   Boot -> getty auto-login on tty1 -> ~/.bash_profile runs `startx`
#        -> ~/.xinitrc starts Openbox + kiosk.sh -> Chromium --kiosk.
#   This is X11 (not Wayland), so xset screen-blank disabling works directly.
#
# ASSUMPTIONS — read before deploying:
#
#   BACKEND ENTRYPOINT:
#     ExecStart uses:  ${INSTALL_DIR}/.venv/bin/python -m backend.sitrep
#     run from WorkingDirectory=${INSTALL_DIR} (the repo root).
#     If the entrypoint changes, update the .service and re-run install.sh.
#
#   VENV LOCATION:  ${INSTALL_DIR}/.venv  (override VENV_DIR before running).
#
#   DISTRO:
#     Targets Ubuntu Server 24.04 (apt). Package names may differ on
#     Fedora/RHEL/Arch; the script logic is otherwise distro-neutral.
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
    # Minimal X stack + window manager for the kiosk session
    for p in xserver-xorg xinit openbox x11-xserver-utils; do
        dpkg -s "$p" &>/dev/null || PKGS+=("$p")
    done
    command -v curl &>/dev/null            || PKGS+=(curl)
    python3 -m venv --help &>/dev/null     || PKGS+=(python3-venv)
    if ! command -v chromium &>/dev/null && ! command -v chromium-browser &>/dev/null \
         && ! command -v google-chrome &>/dev/null; then
        PKGS+=(chromium-browser)   # Ubuntu: this pulls the Chromium snap
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
    # useradd creates a locked-password account by default (no --disabled-password
    # needed; that flag belongs to adduser, not useradd). --comment sets GECOS.
    useradd \
        --create-home \
        --shell /bin/bash \
        --comment "SITREP kiosk user" \
        --groups video,audio,tty,input \
        "${KIOSK_USER}"
    success "Created user '${KIOSK_USER}'"
    info "Set a password if needed: passwd ${KIOSK_USER}"
fi

# Ensure the kiosk user is in the groups X needs (idempotent for existing users)
usermod -aG video,audio,tty,input "${KIOSK_USER}" || true

# Allow startx to run from the auto-login console (some minimal installs default
# to allowed_users=console only; 'anybody' is safe for a single-purpose kiosk).
mkdir -p /etc/X11
if [[ ! -f /etc/X11/Xwrapper.config ]] || ! grep -q '^allowed_users=anybody' /etc/X11/Xwrapper.config 2>/dev/null; then
    printf 'allowed_users=anybody\nneeds_root_rights=yes\n' > /etc/X11/Xwrapper.config
    success "Wrote /etc/X11/Xwrapper.config (allowed_users=anybody)"
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

# ── 7. Console auto-login on tty1 ─────────────────────────────────────────────
# The board must return unattended after a power loss (NFR-2). With no display
# manager, we auto-login the kiosk user on tty1; ~/.bash_profile then runs startx.
step "Configuring console auto-login on tty1 for '${KIOSK_USER}'"

KIOSK_HOME="$(getent passwd "${KIOSK_USER}" | cut -d: -f6)"
GETTY_TEMPLATE="${SCRIPT_DIR}/getty-autologin.conf"
GETTY_DIR="/etc/systemd/system/getty@tty1.service.d"

if [[ ! -f "${GETTY_TEMPLATE}" ]]; then
    fail "Getty autologin template not found: ${GETTY_TEMPLATE}"
fi
mkdir -p "${GETTY_DIR}"
sed -e "s|__KIOSK_USER__|${KIOSK_USER}|g" "${GETTY_TEMPLATE}" > "${GETTY_DIR}/override.conf"
chmod 644 "${GETTY_DIR}/override.conf"
systemctl daemon-reload
systemctl enable getty@tty1.service &>/dev/null || true
success "tty1 auto-login configured for '${KIOSK_USER}'"

# ── 7b. Kiosk X session (startx -> Openbox -> kiosk.sh) ───────────────────────
step "Installing kiosk X session files"

# ~/.xinitrc — started by startx; brings up Openbox + the kiosk browser
XINITRC_TEMPLATE="${SCRIPT_DIR}/xinitrc"
if [[ ! -f "${XINITRC_TEMPLATE}" ]]; then
    fail "xinitrc template not found: ${XINITRC_TEMPLATE}"
fi
sed -e "s|__INSTALL_DIR__|${INSTALL_DIR}|g" "${XINITRC_TEMPLATE}" > "${KIOSK_HOME}/.xinitrc"
chmod 644 "${KIOSK_HOME}/.xinitrc"
chown "${KIOSK_USER}:${KIOSK_USER}" "${KIOSK_HOME}/.xinitrc"
success "Installed ${KIOSK_HOME}/.xinitrc"

# ~/.bash_profile — auto-run startx once, only on the tty1 console login
cat > "${KIOSK_HOME}/.bash_profile" <<'EOF'
# Field SITREP Board — start the X kiosk session on tty1 auto-login.
# Guarded so SSH / other TTYs still get a normal shell.
if [ -z "${DISPLAY:-}" ] && [ "${XDG_VTNR:-}" = "1" ]; then
    exec startx
fi
EOF
chmod 644 "${KIOSK_HOME}/.bash_profile"
chown "${KIOSK_USER}:${KIOSK_USER}" "${KIOSK_HOME}/.bash_profile"
success "Installed ${KIOSK_HOME}/.bash_profile (startx on tty1)"

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
echo " Kiosk session (automatic on reboot):"
echo "   tty1 auto-login as '${KIOSK_USER}' -> startx -> Openbox -> Chromium --kiosk"
echo "   Reboot to verify unattended bring-up:  sudo reboot"
echo "   Manual test (from the kiosk user on tty1):  startx"
echo ""

# Final warnings about unfilled secrets
if grep -qE '^(GA511_API_KEY|AIRNOW_API_KEY|ANTHROPIC_API_KEY)=$' "${ENV_DEST}" 2>/dev/null; then
    echo " *** API keys are empty in ${ENV_DEST} ***"
    echo "     Fill them in, then run:  systemctl restart sitrep-backend"
    echo ""
fi

echo " See deploy/README.md for the full operator runbook."
echo "============================================================"
