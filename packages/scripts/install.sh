#!/usr/bin/env bash
# install.sh — Fox in the Box installer (Linux & macOS)
# Usage: curl -fsSL https://raw.githubusercontent.com/.../install.sh | bash
#   or:  bash install.sh
#
# Non-interactive (no /dev/tty): set FOX_ACCESS_MODE to 1, 2, or 3 instead of prompting.
# Tailscale: optional — FOX_TAILSCALE_WAIT_READY_SEC (default 120), FOX_TAILSCALE_URL_POLL_SEC (default 180)
# Headless Tailscale (no browser): set FOX_TAILSCALE_AUTHKEY to a reusable install auth key from
# https://login.tailscale.com/admin/settings/keys — install.sh runs `tailscale up` with TS_AUTHKEY.
set -euo pipefail

##############################################################################
# Helpers
##############################################################################
BLUE='\033[0;34m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
RED='\033[0;31m'; NC='\033[0m'

info()    { echo -e "${BLUE}[fox]${NC} $*"; }
success() { echo -e "${GREEN}[fox]${NC} $*"; }
warn()    { echo -e "${YELLOW}[fox]${NC} $*"; }
die()     { echo -e "${RED}[fox] ERROR:${NC} $*" >&2; exit 1; }

IMAGE="ghcr.io/fox-in-the-box-ai/cloud:stable"
CONTAINER="fox-in-the-box"

##############################################################################
# 1. Detect OS
##############################################################################
OS="$(uname -s)"
case "$OS" in
  Linux)  PLATFORM="linux"  ;;
  Darwin) PLATFORM="macos"  ;;
  *)      die "Unsupported operating system: $OS" ;;
esac
info "Detected platform: $PLATFORM"

# ── Platform-specific default paths ──────────────────────────────────────────
# APP_DATA_DIR  : bind-mounted as /data inside the container.
#                 Holds repos, config, runtime data, cache.
# WORKSPACE_DIR : lives on the host only — NEVER mounted into the container.
#                 The user's own documents and project files.
#
# These two directories must NEVER be the same path or nested inside each other.

if [[ "$PLATFORM" == "linux" ]]; then
  DEFAULT_DATA_DIR="$HOME/.foxinthebox"
  DEFAULT_WORKSPACE_DIR="$HOME/Fox in the Box"
elif [[ "$PLATFORM" == "macos" ]]; then
  DEFAULT_DATA_DIR="$HOME/Library/Application Support/Fox in the Box"
  DEFAULT_WORKSPACE_DIR="$HOME/Documents/Fox in the Box"
fi

DATA_DIR="${FOX_DATA_DIR:-$DEFAULT_DATA_DIR}"
WORKSPACE_DIR="${FOX_WORKSPACE_DIR:-$DEFAULT_WORKSPACE_DIR}"

##############################################################################
# 2. Check / install Docker
##############################################################################
# Docker Desktop on macOS often installs the CLI outside a minimal PATH (e.g. curl|bash).
_docker_prepath_macos() {
  if [[ "$PLATFORM" != "macos" ]]; then
    return 0
  fi
  local _d
  for _d in \
    "/Applications/Docker.app/Contents/Resources/bin" \
    "/usr/local/bin" \
    "/opt/homebrew/bin"; do
    if [[ -d "$_d" ]]; then
      PATH="$_d:${PATH:-}"
    fi
  done
  export PATH
}

_docker_prepath_macos

_docker_running() {
  # Honour DOCKER_CMD (e.g. "sudo docker" right after usermod -aG docker)
  if [[ -n "${DOCKER_CMD:-}" ]]; then
    $DOCKER_CMD info >/dev/null 2>&1
  else
    docker info >/dev/null 2>&1
  fi
}

# Linux: pre-installed Docker often works as root but not for this user until they
# join the docker group and start a new session. The "install Docker" branch sets
# DOCKER_CMD=sudo in that case; mirror it here when the CLI exists but the socket
# is not accessible without sudo (typical on cloud images with passwordless sudo).
_docker_linux_use_sudo_if_needed() {
  [[ "$PLATFORM" == "linux" ]] || return 0
  [[ -z "${DOCKER_CMD:-}" ]] || return 0
  command -v sudo &>/dev/null || return 0
  if _docker_running; then
    return 0
  fi
  if sudo -n docker info >/dev/null 2>&1; then
    DOCKER_CMD="sudo docker"
    warn "Docker daemon is reachable via sudo only. To use Docker without sudo, run: sudo usermod -aG docker \"$(id -un)\" then log out and back in (or newgrp docker)."
  fi
}

# ── A) No docker CLI: install (Linux) or offer install / instructions (macOS)
if ! command -v docker &>/dev/null; then
  warn "Docker CLI not found — installing…"

  if [[ "$PLATFORM" == "linux" ]]; then
    curl -fsSL https://get.docker.com | sh \
      || die "Docker install script failed. Fix the error above and re-run."
    sudo systemctl start docker \
      || die "Failed to start Docker daemon."
    # Allow current user to use Docker without sudo (takes effect next login)
    if ! groups "$USER" | grep -q docker; then
      sudo usermod -aG docker "$USER"
      warn "Added $USER to the 'docker' group. You may need to log out and back in."
      warn "Re-running this installer under 'sudo' for now…"
      DOCKER_CMD="sudo docker"
    fi
  elif [[ "$PLATFORM" == "macos" ]]; then
    if command -v brew &>/dev/null; then
      brew install --cask docker \
        || die "Homebrew failed to install Docker Desktop."
      info "Docker Desktop installed. Open Docker from Applications, wait until it says running, then re-run this installer."
      exit 1
    else
      die "Docker CLI not on PATH and Homebrew is not installed.\n\
Install Docker Desktop from https://docs.docker.com/desktop/mac/install/\n\
then open it once from Applications, wait until it is running, and re-run this installer."
    fi
  fi

  _DOCKER_READY=false
  for _i in 1 2 3 4 5; do
    if _docker_running; then
      _DOCKER_READY=true
      break
    fi
    sleep 1
  done
  $_DOCKER_READY || die "Docker installed but daemon is still not responding after ~5s. Start Docker and re-run."
fi

# ── B) CLI present but engine not ready (Linux: socket permission vs sudo; macOS: Docker Desktop starting)
_docker_linux_use_sudo_if_needed

if ! _docker_running; then
  warn "Docker is installed but the engine is not responding yet — waiting…"
  _DOCKER_READY=false
  _max=15
  [[ "$PLATFORM" == "macos" ]] && _max=60
  for ((_i = 1; _i <= _max; _i++)); do
    _docker_linux_use_sudo_if_needed
    if _docker_running; then
      _DOCKER_READY=true
      break
    fi
    sleep 2
  done
  if ! $_DOCKER_READY; then
    if [[ "$PLATFORM" == "linux" ]]; then
      die "Docker engine still not reachable. On Linux: start the daemon (sudo systemctl start docker), fix socket access (sudo usermod -aG docker \"$(id -un)\" then log out and back in, or use newgrp docker), or confirm with 'docker info' / 'sudo docker info' in this shell."
    else
      die "Docker engine still not reachable. On macOS: open Docker from Applications, wait until the engine is running, then run this script again. Tip: use Terminal.app; if 'docker version' works there, re-run this script from the same window."
    fi
  fi
fi

DOCKER_CMD="${DOCKER_CMD:-docker}"
success "Docker is ready."

##############################################################################
# 3. Pull image (always fetch latest, don't use stale local cache)
##############################################################################
info "Pulling image: $IMAGE"
# Remove any existing cached image to force a fresh pull from registry.
# This ensures hotfixes and updates to :stable tag are picked up immediately.
$DOCKER_CMD rmi "$IMAGE" 2>/dev/null || true
$DOCKER_CMD pull "$IMAGE" \
  || die "Failed to pull $IMAGE. Check your network connection or GHCR credentials."
success "Image pulled."

##############################################################################
# 4. Prompt: network access mode
##############################################################################
_explain_tailscale() {
  echo
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "  What is Tailscale?"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo
  echo "  Tailscale is a free VPN tool that lets you securely"
  echo "  access Fox in the Box from anywhere — your phone,"
  echo "  laptop, or any other device — without opening ports"
  echo "  in your firewall or dealing with IP addresses."
  echo
  echo "  With Tailscale:"
  echo "    • You get a stable private URL like https://fox.your-name.ts.net"
  echo "    • HTTPS is set up automatically (no certificates to manage)"
  echo "    • Only your approved devices can connect — nothing is public"
  echo "    • Free for personal use (up to 100 devices)"
  echo
  echo "  Without Tailscale (port only):"
  echo "    • Fox in the Box is available at http://localhost:8787"
  echo "    • Accessible on your local network if your firewall allows it"
  echo "    • No remote access unless you set up your own reverse proxy"
  echo
  echo "  Not sure? Choose [1] Port only for now — you can add"
  echo "  Tailscale later by re-running this script."
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo
}

_prompt_access_mode() {
  while true; do
    echo
    echo "How do you want to access Fox in the Box?"
    echo "  [1] Port only (http://localhost:8787 + LAN if firewall permits)"
    echo "  [2] Tailscale only (private HTTPS from anywhere, free)"
    echo "  [3] Both (port binding + Tailscale)"
    echo "  [?] What is Tailscale? Explain more"
    echo
    # curl … | bash: stdin is the script pipe, not the keyboard — read would eat
    # the next line of this file. Use stdin only when it is a real TTY.
    if [[ -t 0 ]]; then
      read -rp "Enter 1, 2, 3 or ? [default: 1]: " ACCESS_MODE
    elif ! { read -rp "Enter 1, 2, 3 or ? [default: 1]: " ACCESS_MODE < /dev/tty; } 2>/dev/null; then
      if [[ -n "${FOX_ACCESS_MODE:-}" ]]; then
        ACCESS_MODE="$FOX_ACCESS_MODE"
        info "Non-interactive install: FOX_ACCESS_MODE=$ACCESS_MODE"
      else
        ACCESS_MODE="1"
        warn "No usable terminal for prompts — using [1] Port only."
        warn "For automated installs set FOX_ACCESS_MODE=1|2|3 before running."
      fi
    fi
    ACCESS_MODE="${ACCESS_MODE:-1}"

    case "$ACCESS_MODE" in
      1) PORT_BIND="-p 0.0.0.0:8787:8787";   USE_TAILSCALE=false; TAILSCALE_FLAGS="";                                                          break ;;
      2) PORT_BIND="-p 127.0.0.1:8787:8787"; USE_TAILSCALE=true;  TAILSCALE_FLAGS="--cap-add=NET_ADMIN --device /dev/net/tun --sysctl net.ipv4.ip_forward=1"; break ;;
      3) PORT_BIND="-p 0.0.0.0:8787:8787";   USE_TAILSCALE=true;  TAILSCALE_FLAGS="--cap-add=NET_ADMIN --device /dev/net/tun --sysctl net.ipv4.ip_forward=1"; break ;;
      "?"|"help"|"explain"|"more"|"what") _explain_tailscale ;;
      *) warn "Invalid selection: '$ACCESS_MODE'. Please enter 1, 2, 3 or ?." ;;
    esac
  done
}

_prompt_access_mode

##############################################################################
# 5. Create host directories
##############################################################################
# App data dir — bind-mounted as /data inside the container
mkdir -p "$DATA_DIR"

# Workspace dir — host only, NEVER mounted into container
# This is where the user's own project files and exports live
mkdir -p "$WORKSPACE_DIR"

if $DOCKER_CMD ps -a --format '{{.Names}}' | grep -qx "$CONTAINER"; then
  warn "Container '$CONTAINER' already exists — stopping and removing it for a clean install."
  $DOCKER_CMD stop "$CONTAINER" >/dev/null 2>&1 || true
  $DOCKER_CMD rm   "$CONTAINER" >/dev/null 2>&1 || true
fi

info "Starting container…"
# shellcheck disable=SC2086
$DOCKER_CMD run -d \
  --name "$CONTAINER" \
  --restart unless-stopped \
  $TAILSCALE_FLAGS \
  -v "$DATA_DIR":/data \
  $PORT_BIND \
  "$IMAGE" \
  || die "Failed to start container."

success "Container '$CONTAINER' is running."

##############################################################################
# 7. Tailscale authentication
##############################################################################
# tailscaled logs go to /data/logs/*.log (supervisord), not container stdout —
# scrape those via docker exec, with docker logs as fallback.
_extract_tailscale_login_url() {
  local url=""
  url="$($DOCKER_CMD exec "$CONTAINER" sh -c \
    'grep -hEo "https://login\.tailscale\.com[^[:space:]]+" /data/logs/tailscaled.log /data/logs/tailscaled.err 2>/dev/null | head -1' \
    2>/dev/null || true)"
  [[ -n "$url" ]] && { echo "$url"; return 0; }
  local LOG_LINE="$($DOCKER_CMD logs --tail 80 "$CONTAINER" 2>&1 || true)"
  echo "$LOG_LINE" | grep -oE 'https://login\.tailscale\.com/a/[A-Za-z0-9]+' | head -1 || true
}

# Wait until /dev/net/tun exists and the tailscale CLI runs. Do NOT require `tailscale status` here:
# on first boot `docker exec … tailscale status` can block or hang until tailscaled is ready, which
# leaves the installer silent after "Container is running" for a long time or indefinitely.
_wait_tailscale_cli_ready() {
  local waited=0 max_wait="${FOX_TAILSCALE_WAIT_READY_SEC:-120}"
  info "Waiting for TUN device and tailscale CLI inside the container (up to ${max_wait}s)…"
  while [[ "$waited" -lt "$max_wait" ]]; do
    if $DOCKER_CMD exec "$CONTAINER" sh -c 'test -c /dev/net/tun' >/dev/null 2>&1 \
      && $DOCKER_CMD exec "$CONTAINER" tailscale version >/dev/null 2>&1; then
      info "Tailscale CLI is reachable; starting join…"
      return 0
    fi
    if (( waited % 20 == 0 && waited > 0 )); then
      info "…still waiting (${waited}s / ${max_wait}s) — first boot may be slow"
    fi
    sleep 2
    waited=$((waited + 2))
  done
  warn "Tailscale CLI not ready within ${max_wait}s — check: $DOCKER_CMD exec $CONTAINER ls -l /dev/net/tun"
  warn "Daemon logs: $DOCKER_CMD exec $CONTAINER tail -80 /data/logs/tailscaled.err"
  return 1
}

# Run `tailscale up` automatically (no manual docker exec) and poll logs + stdout capture for the URL.
# Use `tailscale up`, not `tailscale login`: login-only can finish OAuth while leaving the node
# stopped (WantRunning=false); `up` authenticates if needed and brings the tunnel online.
#
# IMPORTANT: Do not call this from command substitution `$(...)`: subshell exit kills background
# `tailscale up` jobs. Use globals FITB_TAILSCALE_URL + FITB_TS_UP_PID and call directly.
FITB_TAILSCALE_URL=""
FITB_TS_UP_PID=""
_obtain_tailscale_login_url() {
  local url="" waited=0 poll_max="${FOX_TAILSCALE_URL_POLL_SEC:-180}"
  local cap="${TMPDIR:-/tmp}/fitb-tailscale-login.$$.$RANDOM.log"
  rm -f "$cap"
  FITB_TAILSCALE_URL=""
  FITB_TS_UP_PID=""

  info "Waiting for Tailscale daemon inside the container…"
  _wait_tailscale_cli_ready || true

  info "Starting Tailscale (opens auth URL if needed — then connects automatically)…"
  # `tailscale up` stdout/stderr go to this file on the *host* running install.sh — not to
  # /data/logs/tailscaled.log (that file is only what supervisord's tailscaled writes).
  info "Host-side tailscale up log (use: tail -f \"$cap\")"
  ($DOCKER_CMD exec "$CONTAINER" tailscale up --timeout=600 >>"$cap" 2>&1) &
  FITB_TS_UP_PID=$!

  while [[ "$waited" -lt "$poll_max" ]]; do
    url="$(_extract_tailscale_login_url)"
    if [[ -z "$url" ]] && [[ -f "$cap" ]]; then
      url="$(grep -hoE 'https://login\.tailscale\.com[^[:space:]]+' "$cap" 2>/dev/null | head -1)"
    fi
    if [[ -n "$url" ]]; then
      FITB_TAILSCALE_URL="$url"
      return 0
    fi
    sleep 2
    waited=$((waited + 2))
  done

  kill "$FITB_TS_UP_PID" 2>/dev/null || true
  wait "$FITB_TS_UP_PID" 2>/dev/null || true
  FITB_TS_UP_PID=""

  url="$(_extract_tailscale_login_url)"
  if [[ -z "$url" ]] && [[ -f "$cap" ]]; then
    url="$(grep -hoE 'https://login\.tailscale\.com[^[:space:]]+' "$cap" 2>/dev/null | head -1)"
  fi
  rm -f "$cap"
  if [[ -n "$url" ]]; then
    FITB_TAILSCALE_URL="$url"
    return 0
  fi
  return 1
}

# Parse BackendState from `tailscale status --json` inside the container (grep breaks on nested JSON).
_tailscale_backend_state() {
  $DOCKER_CMD exec "$CONTAINER" sh -c \
    'tailscale status --json 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get(\"BackendState\",\"\"))"' \
    2>/dev/null | tr -d '\r\n'
}

# Poll until BackendState is Running (shared by browser auth and auth-key paths).
_tailscale_poll_until_running() {
  local CONNECTED=false
  local DEADLINE=$(( $(date +%s) + 300 ))
  local _poll_n=0
  info "Waiting for Tailscale backend (Running)…"
  while [[ $(date +%s) -lt $DEADLINE ]]; do
    local BACKEND_STATE="$(_tailscale_backend_state)"
    if [[ "$BACKEND_STATE" == "Running" ]]; then
      CONNECTED=true
      break
    fi
    _poll_n=$((_poll_n + 1))
    if [[ "$_poll_n" -eq 15 ]]; then
      info "Nudging tailscale up (tunnel may have stayed down after auth)…"
      $DOCKER_CMD exec "$CONTAINER" tailscale up --timeout=120 >/dev/null 2>&1 || true
    fi
    sleep 3
  done

  if [[ "$CONNECTED" == "true" ]]; then
    local TAILNET_URL="$($DOCKER_CMD exec "$CONTAINER" tailscale status --json 2>/dev/null \
                   | grep -oE '"DNSName":"[^"]+"' | head -1 \
                   | grep -oE '"[^"]+$' | tr -d '"' || true)"
    if [[ -n "$TAILNET_URL" ]]; then
      success "Tailscale connected! Access Fox at:  https://${TAILNET_URL%\.}"
    else
      success "Tailscale connected!"
    fi
  else
    warn "Tailscale not yet confirmed Running. Check: $DOCKER_CMD exec $CONTAINER tailscale status"
    warn "Daemon stderr log: $DOCKER_CMD exec $CONTAINER tail -80 /data/logs/tailscaled.err"
    warn "On AWS, allow outbound UDP (WireGuard). Container needs NET_ADMIN + /dev/net/tun."
  fi
}

if [[ "$USE_TAILSCALE" == "true" ]]; then
  info "Tailscale mode — preparing authentication (do not interrupt this step)…"
  _wait_tailscale_cli_ready || true

  # ── Headless: reusable install auth key (no browser, stable for automation) ──
  if [[ -n "${FOX_TAILSCALE_AUTHKEY:-}" ]]; then
    _ak_log="${TMPDIR:-/tmp}/fitb-tailscale-authkey.$$.$RANDOM.log"
    info "Tailscale: joining with FOX_TAILSCALE_AUTHKEY (no browser URL)…"
    set +e
    # TS_AUTHKEY is read by tailscale up; never echo the key.
    $DOCKER_CMD exec -e "TS_AUTHKEY=${FOX_TAILSCALE_AUTHKEY}" "$CONTAINER" \
      tailscale up --timeout=600 >>"$_ak_log" 2>&1
    _ts_ak_rc=$?
    set -e
    if [[ "$_ts_ak_rc" -ne 0 ]]; then
      warn "tailscale up (auth key) exited $_ts_ak_rc — see: $_ak_log"
    fi
    _tailscale_poll_until_running
  else
    # ── Interactive: background tailscale up + URL + wait on PID (no $(...) subshell) ──
    LOGIN_URL=""
    set +e
    _obtain_tailscale_login_url
    _ts_url_rc=$?
    LOGIN_URL="$FITB_TAILSCALE_URL"
    set -e

    if [[ "$_ts_url_rc" -ne 0 || -z "$LOGIN_URL" ]]; then
      warn "Tailscale login URL not discovered automatically after polling."
      warn "Daemon stderr: $DOCKER_CMD exec $CONTAINER tail -80 /data/logs/tailscaled.err"
      warn "Host capture: ls -t ${TMPDIR:-/tmp}/fitb-tailscale-login.* 2>/dev/null | head -1"
    else
      echo
      echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
      echo "  Tailscale login URL:"
      echo "  $LOGIN_URL"
      echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
      if command -v qrencode &>/dev/null; then
        info "QR code (scan with Tailscale mobile app):"
        qrencode -t ANSIUTF8 "$LOGIN_URL"
      else
        info "(Install 'qrencode' to display a QR code here.)"
      fi

      if [[ -n "${FITB_TS_UP_PID:-}" ]] && kill -0 "$FITB_TS_UP_PID" 2>/dev/null; then
        info "Waiting for Tailscale to finish (complete browser login — this step exits when the tunnel is up)…"
        wait "$FITB_TS_UP_PID" 2>/dev/null || true
      fi
      FITB_TS_UP_PID=""

      # If the first `tailscale up` exited before Running (race / user slow), retry once in foreground.
      if [[ "$(_tailscale_backend_state)" != "Running" ]]; then
        info "Retrying tailscale up once to stabilize the tunnel…"
        set +e
        $DOCKER_CMD exec "$CONTAINER" tailscale up --timeout=300 >/dev/null 2>&1
        set -e
      fi
    fi

    _tailscale_poll_until_running
  fi
fi

##############################################################################
# 8 / 9. Install service manager integration
##############################################################################
# When run via `curl ... | bash`, BASH_SOURCE[0] is empty or /dev/stdin, so
# __dirname-style detection doesn't work.  We download the service files from
# GitHub instead and write them to a temp directory.
_download_service_files() {
  local DEST="$1"
  local RAW_BASE="https://raw.githubusercontent.com/fox-in-the-box-ai/fox-in-the-box/main/packages/scripts"
  mkdir -p "$DEST"
  for FILE in foxinthebox.service foxinthebox-updater.service foxinthebox-updater.path io.foxinthebox.plist; do
    curl -fsSL "$RAW_BASE/$FILE" -o "$DEST/$FILE" 2>/dev/null || true
  done
}

# Detect whether we were piped via curl (BASH_SOURCE empty or /dev/stdin)
_SCRIPT_SRC="${BASH_SOURCE[0]:-}"
if [[ -z "$_SCRIPT_SRC" || "$_SCRIPT_SRC" == "/dev/stdin" || ! -f "${_SCRIPT_SRC}" ]]; then
  # curl-pipe path — download service files from GitHub
  _SVC_TMPDIR="$(mktemp -d)"
  trap 'rm -rf "$_SVC_TMPDIR"' EXIT
  info "Downloading service files…"
  _download_service_files "$_SVC_TMPDIR"
  SCRIPT_DIR="$_SVC_TMPDIR"
else
  # Local bash install.sh path — sibling files are right next to the script
  SCRIPT_DIR="$(cd "$(dirname "$_SCRIPT_SRC")" && pwd)"
fi

if [[ "$PLATFORM" == "linux" ]]; then
  info "Installing systemd units…"
  SYSTEMD_DIR="/etc/systemd/system"

  sudo cp "$SCRIPT_DIR/foxinthebox.service"           "$SYSTEMD_DIR/"
  sudo cp "$SCRIPT_DIR/foxinthebox-updater.service"   "$SYSTEMD_DIR/"
  sudo cp "$SCRIPT_DIR/foxinthebox-updater.path"      "$SYSTEMD_DIR/"

  # Substitute __DATA_DIR__ placeholder with the actual data directory
  sudo sed -i "s|__DATA_DIR__|${DATA_DIR}|g" "$SYSTEMD_DIR/foxinthebox.service"
  sudo sed -i "s|__DATA_DIR__|${DATA_DIR}|g" "$SYSTEMD_DIR/foxinthebox-updater.path"

  sudo systemctl daemon-reload
  sudo systemctl enable foxinthebox
  sudo systemctl enable foxinthebox-updater.path
  success "systemd units installed and enabled."

elif [[ "$PLATFORM" == "macos" ]]; then
  info "Installing launchd agent…"
  LAUNCH_AGENTS="$HOME/Library/LaunchAgents"
  mkdir -p "$LAUNCH_AGENTS"
  PLIST="$LAUNCH_AGENTS/io.foxinthebox.plist"

  cp "$SCRIPT_DIR/io.foxinthebox.plist" "$PLIST"

  # Patch data dir into plist
  sed -i '' "s|__DATA_DIR__|$DATA_DIR|g" "$PLIST"

  # Unload first (idempotent)
  launchctl unload "$PLIST" 2>/dev/null || true
  launchctl load -w "$PLIST" \
    || die "launchctl failed to load $PLIST"
  success "launchd agent installed and loaded."
fi

##############################################################################
# 10. Success summary
##############################################################################
echo
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
success "Fox in the Box is installed!"
echo
echo "  Container  : $CONTAINER"
echo
echo "  App data   : $DATA_DIR"
echo "               (config, repos, runtime data — bind-mounted into container)"
echo
echo "  Workspace  : $WORKSPACE_DIR"
echo "               (your files and projects — NOT inside the container)"
echo
if [[ "$ACCESS_MODE" == "1" || "$ACCESS_MODE" == "2" || "$ACCESS_MODE" == "3" ]]; then
  echo "  Web UI     : http://localhost:8787"
fi
if [[ "$USE_TAILSCALE" == "true" ]]; then
  echo "  Tailscale  : see Tailscale admin console for HTTPS URL"
fi
echo
echo "  Logs       : docker logs -f $CONTAINER"
echo "  Stop       : docker stop $CONTAINER"
if [[ "$PLATFORM" == "linux" ]]; then
  echo "  Service   : systemctl status foxinthebox"
else
  echo "  Service   : launchctl list io.foxinthebox"
fi
echo
if [[ "$ACCESS_MODE" == "1" || "$ACCESS_MODE" == "3" ]]; then
  warn "FIREWALL NOTE: Port 8787 is bound to 0.0.0.0. Ensure your firewall"
  warn "rules only allow trusted hosts (e.g., 'ufw allow from 192.168.0.0/16 to any port 8787')."
fi
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Wait for Web UI before opening browser (Hermes/Qdrant first boot can take 1–3+ minutes)
_wait_web_health_host() {
  local _hp="${FOX_HEALTH_PORT:-8787}"
  local _url="http://127.0.0.1:${_hp}/health"
  local _max="${FOX_HEALTH_WAIT_SEC:-240}"
  local _i
  if ! command -v curl &>/dev/null; then
    warn "curl not found — waiting 25s then opening browser (first start may still be loading)…"
    sleep 25
    return 0
  fi
  info "Waiting for Web UI (${_url}, up to ${_max}s — first start can be slow)…"
  for ((_i = 1; _i <= _max; _i++)); do
    if curl -fsS --connect-timeout 2 --max-time 6 "$_url" >/dev/null 2>&1; then
      success "Web UI is ready."
      return 0
    fi
    if ((_i % 15 == 0)); then
      info "Still starting… (${_i}s) — check: docker logs -f $CONTAINER"
    fi
    sleep 1
  done
  warn "Web UI did not respond on /health within ${_max}s — open http://localhost:${_hp} manually when ready."
  return 1
}

# Open setup Web UI (localhost works for modes 1–3; set FOX_OPEN_BROWSER=0 to skip)
if [[ "${FOX_OPEN_BROWSER:-1}" != "0" ]] && [[ "$ACCESS_MODE" == "1" || "$ACCESS_MODE" == "2" || "$ACCESS_MODE" == "3" ]]; then
  _url="http://localhost:8787"
  _wait_web_health_host || true
  info "Opening $_url in your default browser…"
  if [[ "$PLATFORM" == "macos" ]]; then
    open "$_url" 2>/dev/null || warn "Could not open browser — visit $_url manually."
  elif [[ "$PLATFORM" == "linux" ]]; then
    if command -v xdg-open &>/dev/null; then
      xdg-open "$_url" 2>/dev/null || warn "Could not open browser — visit $_url manually."
    else
      warn "Install xdg-utils for auto-open, or visit $_url manually."
    fi
  fi
fi
