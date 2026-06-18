#!/usr/bin/env bash
# =============================================================================
# update.sh — Pull the latest code and refresh the running kiosk.
#
# Run as the KIOSK USER (the user that owns the repo), NOT as root. Running as
# root would re-trigger git's "dubious ownership" guard and leave root-owned
# files the service user can't manage. The one step that needs privilege — the
# systemd restart — is done with sudo.
#
# USAGE:
#   bash deploy/update.sh [--branch NAME] [--force] [--no-restart] [--no-deps]
#
#   # From anywhere, run as the owner (e.g. user "kiosk"):
#   sudo -u kiosk bash /opt/sitrep/deploy/update.sh
#
# OPTIONS:
#   --branch NAME   Branch to pull. Default: the repo's current branch.
#   --force         Hard-reset the working tree to origin/<branch>, discarding
#                   local edits to tracked files (e.g. a hand-edited install.sh).
#                   Untracked, gitignored files (config.yaml, .env) are kept.
#                   Use this to force a box back into alignment with the remote.
#   --no-restart    Pull (and update deps) but don't restart the backend.
#   --no-deps       Don't pip-install even if requirements.txt changed.
#
# WHAT IT DOES (in order):
#   1. Verify it's running as the repo owner (clean git ownership).
#   2. Fast-forward pull the branch from origin.
#   3. If requirements.txt changed, pip-install into the existing venv.
#   4. Restart the backend service (via sudo).
#
# NOTE: the static frontend (index.html/app.js/styles.css) is cached by the
#   Chromium kiosk. After a frontend change, reboot or restart the kiosk session
#   to pick it up — restarting the backend alone is not enough.
# =============================================================================

set -euo pipefail

# ── Derived paths (resolve from this script's location, cwd-independent) ──────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
VENV_DIR="${REPO_ROOT}/.venv"
REQ_FILE="${REPO_ROOT}/requirements.txt"
SERVICE="sitrep-backend.service"

# ── Defaults / flags ─────────────────────────────────────────────────────────
BRANCH=""
RESTART=1
DEPS=1
FORCE=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --branch)     BRANCH="$2"; shift 2 ;;
        --force)      FORCE=1; shift ;;
        --no-restart) RESTART=0; shift ;;
        --no-deps)    DEPS=0; shift ;;
        -h|--help)    grep '^#' "$0" | head -40; exit 0 ;;
        *)            echo "Unknown flag: $1" >&2; exit 1 ;;
    esac
done

# ── Helpers ──────────────────────────────────────────────────────────────────
step()    { echo; echo "==> $*"; }
info()    { echo "    $*"; }
warn()    { echo "    WARNING: $*" >&2; }
success() { echo "    OK: $*"; }
fail()    { echo "    FATAL: $*" >&2; exit 1; }

# ── 1. Must run as the repo owner (not root) ─────────────────────────────────
OWNER="$(stat -c '%U' "${REPO_ROOT}")"
CURRENT="$(id -un)"
if [[ "${CURRENT}" != "${OWNER}" ]]; then
    fail "Run as the repo owner '${OWNER}', not '${CURRENT}'. Try: sudo -u ${OWNER} bash ${BASH_SOURCE[0]}"
fi

cd "${REPO_ROOT}"

if ! git rev-parse --is-inside-work-tree &>/dev/null; then
    fail "${REPO_ROOT} is not a git working tree."
fi

BRANCH="${BRANCH:-$(git rev-parse --abbrev-ref HEAD)}"

step "Field SITREP Board — update"
info "Repo root : ${REPO_ROOT}"
info "Owner     : ${OWNER}"
info "Branch    : ${BRANCH}"

# Refuse to clobber local edits unless --force was given. config.yaml / .env are
# gitignored (untracked), so they are safe either way.
if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
    if [[ "${FORCE}" -eq 1 ]]; then
        warn "Tracked files have local changes — --force will discard them:"
        git status --short --untracked-files=no >&2
    else
        warn "Tracked files have uncommitted changes:"
        git status --short --untracked-files=no >&2
        fail "Commit/stash/revert them, or re-run with --force to discard and align to origin."
    fi
fi

# ── 2. Pull (fast-forward) or hard-reset to origin (--force) ──────────────────
OLD_REV="$(git rev-parse HEAD)"
req_hash() { [[ -f "${REQ_FILE}" ]] && sha1sum "${REQ_FILE}" | awk '{print $1}' || echo "none"; }
REQ_BEFORE="$(req_hash)"

git fetch --prune origin "${BRANCH}"
if [[ "${FORCE}" -eq 1 ]]; then
    step "Hard-resetting to origin/${BRANCH} (discarding local tracked changes)"
    git reset --hard "origin/${BRANCH}"
else
    step "Fast-forward pulling origin/${BRANCH}"
    git pull --ff-only origin "${BRANCH}"
fi

NEW_REV="$(git rev-parse HEAD)"
if [[ "${OLD_REV}" == "${NEW_REV}" ]]; then
    info "Already up to date (${NEW_REV:0:8})."
else
    success "Updated ${OLD_REV:0:8} -> ${NEW_REV:0:8}"
fi

# ── 3. Update Python deps only if requirements.txt changed ────────────────────
if [[ "${DEPS}" -eq 1 && "$(req_hash)" != "${REQ_BEFORE}" ]]; then
    step "requirements.txt changed — updating venv"
    if [[ -x "${VENV_DIR}/bin/pip" ]]; then
        "${VENV_DIR}/bin/pip" install --quiet --upgrade -r "${REQ_FILE}"
        success "Dependencies updated."
    else
        warn "venv not found at ${VENV_DIR}; skipping pip. Run deploy/install.sh to (re)create it."
    fi
else
    info "requirements.txt unchanged — skipping pip."
fi

# ── 4. Restart the backend service (needs privilege) ──────────────────────────
if [[ "${RESTART}" -eq 1 ]]; then
    step "Restarting ${SERVICE}"
    SUDO=""
    [[ "${EUID}" -ne 0 ]] && SUDO="sudo"
    if ${SUDO} systemctl restart "${SERVICE}"; then
        ${SUDO} systemctl --no-pager --lines=0 status "${SERVICE}" || true
        success "Backend restarted."
    else
        fail "Failed to restart ${SERVICE}. Check: ${SUDO} journalctl -u ${SERVICE} -n 50"
    fi
else
    info "Skipping restart (--no-restart). Apply manually: sudo systemctl restart ${SERVICE}"
fi

step "Done"
info "Frontend assets are cached by the Chromium kiosk. To load frontend changes,"
info "reboot the mini PC or restart the kiosk session."
