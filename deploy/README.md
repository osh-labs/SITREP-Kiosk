# Field SITREP Board — Operator Runbook

**Milestone M3 — Kiosk Hardening**

This runbook covers everything you need to install, verify, operate, and
troubleshoot the Field SITREP Board on the kiosk mini PC.

---

## Table of Contents

1. [Hardware assumptions](#1-hardware-assumptions)
2. [First install — step by step](#2-first-install--step-by-step)
3. [Where secrets live (.env)](#3-where-secrets-live-env)
4. [Verifying the system is healthy](#4-verifying-the-system-is-healthy)
5. [How mode switching works](#5-how-mode-switching-works)
6. [Simulating a source outage (M3 exit criterion)](#6-simulating-a-source-outage-m3-exit-criterion)
7. [Updating and restarting](#7-updating-and-restarting)
8. [How reboot survival works](#8-how-reboot-survival-works)
9. [Autostart — desktop vs. systemd-user](#9-autostart--desktop-vs-systemd-user)
10. [Troubleshooting](#10-troubleshooting)

---

## 1. Hardware assumptions

| Item | Assumption |
|------|------------|
| Mini PC OS | Debian 12 or Ubuntu 22.04 / 24.04 LTS (64-bit) |
| Display server | X11 (Wayland works but xset DPMS disabling differs) |
| Display manager | LightDM, GDM, or SDDM (any that honours `~/.config/autostart`) |
| Python | 3.11 or 3.12 (install via `apt install python3.11 python3.11-venv`) |
| Chromium | `chromium` (apt) or `google-chrome-stable` |
| Network | Internet access for api.weather.gov, SPC, 511ga.org, airnowapi.org, api.anthropic.com |
| Ports | Nothing exposed externally; backend binds `127.0.0.1:8080` only |

> **Fedora/RHEL note:** package names differ (`chromium` is still correct;
> `python3.11` may need `dnf install python3.11`). The install script and
> service unit logic are identical.

---

## 2. First install — step by step

### 2.1 Get the repo onto the mini PC

```bash
# Option A — clone directly on the machine
git clone <repo-url> /opt/sitrep
cd /opt/sitrep

# Option B — copy a tarball / USB drive, extract to /opt/sitrep
```

The default install directory is `/opt/sitrep`. To use a different path, pass
`--install-dir /your/path` to install.sh.

### 2.2 Install OS prerequisites

```bash
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3-pip chromium curl \
                    x11-xserver-utils
```

### 2.3 Fill in API keys before installing

The installer will copy `.env.example` to `.env` if `.env` does not exist,
but it cannot fill in your keys for you.  **Do this before running the
installer** (or immediately after, then restart the service):

```bash
cp /opt/sitrep/.env.example /opt/sitrep/.env
nano /opt/sitrep/.env
```

Keys to fill in (see Section 3 for details):

```
GA511_API_KEY=your_key_here
AIRNOW_API_KEY=your_key_here
ANTHROPIC_API_KEY=sk-ant-...
```

The installer sets `.env` to mode 600 (owner-read only).

### 2.4 Run the installer

```bash
cd /opt/sitrep
sudo bash deploy/install.sh
```

To use a custom install directory or kiosk username:

```bash
sudo bash deploy/install.sh --install-dir /home/myuser/sitrep --kiosk-user myuser
```

The installer is **idempotent** — it is safe to run again after updating the
repo or changing configuration.  It will:

- Skip any step already complete (existing venv, existing config, existing .env).
- Re-substitute placeholders in the unit file and compare to the installed
  version; only writes if something changed.
- Reload systemd and restart the backend service.

### 2.5 Configure the display manager for auto-login

The kiosk should log in automatically as the kiosk user.  Example for
LightDM (edit `/etc/lightdm/lightdm.conf`):

```ini
[Seat:*]
autologin-user=kiosk
autologin-user-timeout=0
```

After saving: `sudo systemctl restart lightdm`

> **Security note:** Auto-login is acceptable here because the box has no
> inbound network services and the kiosk user has no sudo rights.

### 2.6 Reboot to verify end-to-end

```bash
sudo reboot
```

After reboot:
- The backend service starts automatically via systemd.
- When the kiosk user's desktop session starts, `~/.config/autostart/sitrep-kiosk.desktop` launches `kiosk.sh`.
- `kiosk.sh` waits up to 120 s for the backend `/healthz` to respond, then opens Chromium in full-screen kiosk mode.

---

## 3. Where secrets live (.env)

Secrets are stored in `/opt/sitrep/.env` (or `${INSTALL_DIR}/.env`).
This file is **never committed to git** (it is in `.gitignore`).

```bash
# /opt/sitrep/.env
NWS_USER_AGENT="UnitedConsulting-FieldSITREP/1.0 (contact: you@example.com)"
GA511_API_KEY=your_511ga_developer_key
AIRNOW_API_KEY=your_airnow_api_key
ANTHROPIC_API_KEY=sk-ant-...
SITREP_PORT=8080
```

**Where to get keys:**

| Key | Source |
|-----|--------|
| `GA511_API_KEY` | Register free at https://511ga.org (developer portal) |
| `AIRNOW_API_KEY` | Register free at https://docs.airnowapi.org |
| `ANTHROPIC_API_KEY` | https://console.anthropic.com — use a key scoped to claude-sonnet-4-6 |

After editing `.env`, restart the backend:

```bash
sudo systemctl restart sitrep-backend
```

The systemd unit loads `.env` via `EnvironmentFile=` before launching the
process, so the backend sees the new values on next start.

---

## 4. Verifying the system is healthy

### 4.1 Backend service status

```bash
sudo systemctl status sitrep-backend
```

Expected output: `Active: active (running)`.

### 4.2 Backend logs (live tail)

```bash
journalctl -u sitrep-backend -f
```

Look for lines like `[sitrep-backend] poller NWS: OK` and no repeated
connection errors.

### 4.3 Health endpoint

```bash
curl -s http://localhost:8080/healthz
```

Expected: HTTP 200 with a JSON body like `{"status": "ok"}`.

### 4.4 State endpoint

```bash
curl -s http://localhost:8080/api/state | python3 -m json.tool | head -60
```

This returns the consolidated state object including per-source timestamps.
Check that `last_updated` fields are recent (within the staleness window).

### 4.5 Kiosk process

```bash
# If the kiosk session is running, check for the Chromium process:
pgrep -a chromium
# Or: ps aux | grep chromium
```

---

## 5. How mode switching works

Mode switching (Morning / Afternoon) is **config-driven, not code-driven**.
The backend reads `config/config.yaml` and determines which slide set to
include in the state based on the current local time.

### Key config values

```yaml
# config/config.yaml
display:
  mode_windows:
    morning_until: "12:00"   # local time; switch to afternoon mode at noon
  work_hours:
    start: "06:00"
    end:   "18:00"
```

- Before `morning_until`: Morning Mode slides (BLUF, Weather, Disruptions, Look-ahead).
- At or after `morning_until`: Afternoon Mode slides (Weather, PM Commute, Look-ahead).

### Changing the switch time

1. Edit `config/config.yaml`:
   ```yaml
   display:
     mode_windows:
       morning_until: "13:00"   # now switches at 1 PM
   ```
2. Reload config without restarting: the backend supports config reload on
   `SIGHUP` (if implemented) — or simply restart the service:
   ```bash
   sudo systemctl restart sitrep-backend
   ```
3. No code change is required.

---

## 6. Simulating a source outage (M3 exit criterion)

The M3 exit criterion requires: *survives reboot and a simulated outage over 24 h.*

### 6.1 What "degraded state" looks like

When a source is unreachable or returns an error, the backend keeps serving
the last-good cached value.  The frontend marks it:

> *Data as of 04:55 (about 2 hrs ago) — source is down, so check current
> conditions before you rely on this.*

Other slides continue running normally.

### 6.2 Simulate a 511GA outage

Method 1 — block the domain at the hosts level:

```bash
sudo bash -c 'echo "0.0.0.0 511ga.org" >> /etc/hosts'
```

Wait one poll cycle (90 s per `config/config.yaml`), then verify:

```bash
# Check that 511GA data is marked stale
curl -s http://localhost:8080/api/state | python3 -c "
import json, sys, datetime
state = json.load(sys.stdin)
src = state.get('sources', {}).get('ga511', {})
print('GA511 stale:', src.get('stale'))
print('GA511 last_updated:', src.get('last_updated'))
"
```

The frontend should show the disruptions slide with the "as of" staleness
banner.  All other slides (NWS, SPC, AirNow) keep running normally.

Restore when done:

```bash
sudo sed -i '/511ga.org/d' /etc/hosts
```

### 6.3 Simulate an NWS outage

```bash
sudo bash -c 'echo "0.0.0.0 api.weather.gov" >> /etc/hosts'
# Wait 15 min (NWS poll interval), then check /api/state
# Restore:
sudo sed -i '/api.weather.gov/d' /etc/hosts
```

### 6.4 Simulate an Anthropic outage (BLUF fallback)

```bash
sudo bash -c 'echo "0.0.0.0 api.anthropic.com" >> /etc/hosts'
# Wait one briefing cycle (30 min), then check:
#   - The BLUF slide should show the templated fallback briefing, not an error page.
# Restore:
sudo sed -i '/api.anthropic.com/d' /etc/hosts
```

### 6.5 Simulate a backend crash (auto-restart test)

```bash
# Find the PID and kill it
sudo systemctl kill sitrep-backend
# Wait 5 s (RestartSec=5 in the unit)
sleep 6
sudo systemctl status sitrep-backend   # should show "active (running)" again
```

### 6.6 24-hour unattended run

After verifying individual failure modes, leave the system running for 24 h:

```bash
# On the morning of the test:
sudo reboot
# ... 24 h later:
journalctl -u sitrep-backend --since "24 hours ago" | grep -E "ERROR|WARN|restart"
curl -s http://localhost:8080/healthz
curl -s http://localhost:8080/api/state | python3 -m json.tool | grep last_updated
```

The M3 criterion is met when:
- The board is still running after 24 h with no manual intervention.
- At least one simulated outage was performed and the degraded state was visible.
- At least one reboot was survived.

---

## 7. Updating and restarting

### Pull latest code

```bash
cd /opt/sitrep
git pull
```

### Re-run the installer (always safe)

```bash
sudo bash deploy/install.sh
```

This reinstalls Python deps, refreshes the systemd unit if it changed, and
restarts the service.

### Restart the backend only

```bash
sudo systemctl restart sitrep-backend
```

### Reload config without a full restart

If the backend supports `SIGHUP`-based config reload:

```bash
sudo systemctl kill -s HUP sitrep-backend
```

Otherwise use `systemctl restart`.

### Update API keys

Edit `.env`, then:

```bash
sudo systemctl restart sitrep-backend
```

---

## 8. How reboot survival works

Reboot survival is achieved through two independent mechanisms:

### 8.1 Backend — systemd (system-level)

The file `/etc/systemd/system/sitrep-backend.service` is a **system-level**
unit with:

```ini
[Install]
WantedBy=multi-user.target
```

Because it was enabled with `systemctl enable`, systemd creates a symlink
in `/etc/systemd/system/multi-user.target.wants/` and starts the unit on
every boot — **before any user logs in**.

Auto-restart on failure:

```ini
Restart=always
RestartSec=5
RestartSteps=6
RestartMaxDelaySec=600
```

Meaning: restart after 5 s, backing off to a maximum of 10 min between
attempts.  A transient API error or network hiccup does not leave the board
down permanently.

### 8.2 Kiosk browser — desktop autostart (session-level)

The file `~/.config/autostart/sitrep-kiosk.desktop` is processed by the
desktop session manager (GNOME, XFCE, LXDE, etc.) each time the kiosk user's
session starts.  Since the display manager is configured for auto-login, this
runs on every boot.

`kiosk.sh` runs in an infinite loop — if Chromium exits for any reason it is
relaunched after 3 s.

Together:

```
Boot
 └─ systemd starts sitrep-backend.service (restarts on failure)
 └─ Display manager auto-logs-in kiosk user
     └─ ~/.config/autostart/sitrep-kiosk.desktop fires kiosk.sh
         └─ kiosk.sh polls /healthz until backend is ready
         └─ Chromium launches in kiosk mode
         └─ If Chromium exits → re-poll /healthz → relaunch
```

---

## 9. Autostart — desktop vs. systemd-user

**Primary (what install.sh sets up): `~/.config/autostart/sitrep-kiosk.desktop`**

This is the simpler and more portable approach:

- Works with any GNOME-compatible display manager (LightDM, GDM, SDDM with GNOME/XFCE session).
- The XDG autostart specification is honoured by virtually every Linux desktop environment.
- Fires after the X11/Wayland display session is up, so `DISPLAY` is set correctly when `kiosk.sh` runs.

**Alternative: systemd --user unit**

A `systemd --user` unit can also launch the kiosk:

```ini
# ~/.config/systemd/user/sitrep-kiosk.service
[Unit]
Description=SITREP Kiosk browser
After=graphical-session.target
Wants=graphical-session.target

[Service]
ExecStart=/opt/sitrep/deploy/kiosk.sh
Restart=always
RestartSec=3
Environment=DISPLAY=:0

[Install]
WantedBy=graphical-session.target
```

Enable with:

```bash
systemctl --user enable sitrep-kiosk.service
systemctl --user start  sitrep-kiosk.service
```

The downside: `graphical-session.target` reaching "active" depends on the
display manager correctly emitting the `DISPLAY` socket to the user session,
which varies between LightDM, GDM, and SDDM.  The `.desktop` approach avoids
this variance.

---

## 10. Troubleshooting

### Backend won't start

```bash
sudo systemctl status sitrep-backend
journalctl -u sitrep-backend -n 50 --no-pager
```

Common causes:

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `No module named backend.sitrep` | Venv not installed or wrong entrypoint | Re-run `install.sh`; verify `ExecStart` in the unit |
| `No config file found` | `config/config.yaml` missing | Run `install.sh` or copy manually |
| `FileNotFoundError: .env` | `.env` missing | Copy from `.env.example` and fill keys |
| `Port 8080 already in use` | Another process on 8080 | `sudo lsof -i :8080`; change `SITREP_PORT` in `.env` |
| `Permission denied` | Wrong file ownership | `sudo chown -R kiosk:kiosk /opt/sitrep` |

### Health check returns non-200

```bash
curl -v http://localhost:8080/healthz
```

If the connection is refused, the backend is not running.
If the backend is running but `/healthz` returns an error, check the logs —
likely a startup exception in the app code.

### Chromium doesn't launch / desktop is blank

```bash
# Check if kiosk.sh is running under the kiosk user's session:
ps aux | grep kiosk
# Check if the autostart entry was installed:
ls -la /home/kiosk/.config/autostart/
# Run manually as the kiosk user (from a terminal in the kiosk session):
bash /opt/sitrep/deploy/kiosk.sh
```

If Chromium shows "This site can't be reached", the backend is not ready yet.
Wait for `kiosk.sh` to finish polling, or check `journalctl -u sitrep-backend`.

### Screen blanks / sleeps

`kiosk.sh` calls `xset s off`, `xset -dpms`, `xset s noblank` on startup.
If blanking still occurs:

```bash
# Verify xset is installed:
which xset
# Apply manually (from kiosk X session):
DISPLAY=:0 xset s off && DISPLAY=:0 xset -dpms && DISPLAY=:0 xset s noblank
```

Some mini PC BIOSes have independent display-off timers — check the BIOS
power settings if software xset commands are insufficient.

### Data source is always stale

```bash
# Test network connectivity to each source:
curl -s -A "UnitedConsulting-FieldSITREP/1.0" \
     "https://api.weather.gov/points/33.749,-84.388"
curl -s "https://airnowapi.org/aq/observation/latLong/current/?format=application/json&latitude=33.749&longitude=-84.388&distance=25&API_KEY=YOUR_KEY"
```

If `api.weather.gov` is reachable but NWS data stays stale, verify the
`NWS_USER_AGENT` in `.env` — NWS will block requests with a missing or
generic User-Agent.

### BLUF shows templated fallback instead of AI briefing

The backend falls back to the deterministic template when the Anthropic API
call fails.  Check:

```bash
journalctl -u sitrep-backend | grep -i "anthropic\|briefing\|LLM"
```

Common causes: empty or invalid `ANTHROPIC_API_KEY`, Anthropic API outage, or
rate limiting.  The fallback is intentional — the board should never go
wordless (PRD §7.3).

### Re-running install.sh after a code update

```bash
cd /opt/sitrep
git pull
sudo bash deploy/install.sh   # safe to re-run; skips already-done steps
```

---

*End of runbook — Field SITREP Board M3*
