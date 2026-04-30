#!/usr/bin/env bash
# install.sh — Fox in the Box installer (Linux & macOS)
# Usage: curl -fsSL https://raw.githubusercontent.com/.../install.sh | bash
#   or:  bash install.sh
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
_docker_running() {
  docker info >/dev/null 2>&1
}

if ! command -v docker &>/dev/null || ! _docker_running; then
  warn "Docker not found or not running — installing…"

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
      info "Docker Desktop installed. Please launch it from /Applications, then re-run this installer."
      exit 1
    else
      die "Docker is not installed and Homebrew is not available.\n\
Please install Docker Desktop manually from https://docs.docker.com/desktop/mac/install/\n\
then re-run this installer."
    fi
  fi

  # Final check
  _docker_running || die "Docker installed but daemon is still not responding. Start Docker and re-run."
fi

DOCKER_CMD="${DOCKER_CMD:-docker}"
success "Docker is ready."

##############################################################################
# 3. Pull image
##############################################################################
info "Pulling image: $IMAGE"
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
    read -rp "Enter 1, 2, 3 or ? [default: 1]: " ACCESS_MODE
    ACCESS_MODE="${ACCESS_MODE:-1}"

    case "$ACCESS_MODE" in
      1) PORT_BIND="-p 0.0.0.0:8787:8787"; USE_TAILSCALE=false; break ;;
      2) PORT_BIND="-p 127.0.0.1:8787:8787"; USE_TAILSCALE=true;  break ;;
      3) PORT_BIND="-p 0.0.0.0:8787:8787";  USE_TAILSCALE=true;  break ;;
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
  --cap-add=NET_ADMIN \
  --device /dev/net/tun \
  --sysctl net.ipv4.ip_forward=1 \
  -v "$DATA_DIR":/data \
  $PORT_BIND \
  "$IMAGE" \
  || die "Failed to start container."

success "Container '$CONTAINER' is running."

##############################################################################
# 7. Tailscale authentication
##############################################################################
if [[ "$USE_TAILSCALE" == "true" ]]; then
  info "Waiting for Tailscale login URL (up to 60 s)…"
  LOGIN_URL=""
  DEADLINE=$(( $(date +%s) + 60 ))
  while [[ $(date +%s) -lt $DEADLINE ]]; do
    LOG_LINE="$($DOCKER_CMD logs --tail 50 "$CONTAINER" 2>&1 || true)"
    LOGIN_URL="$(echo "$LOG_LINE" | grep -oE 'https://login\.tailscale\.com/a/[A-Za-z0-9]+' | head -1 || true)"
    [[ -n "$LOGIN_URL" ]] && break
    sleep 2
  done

  if [[ -z "$LOGIN_URL" ]]; then
    warn "Tailscale login URL not seen in logs within 60 s."
    warn "Run:  docker logs $CONTAINER | grep tailscale"
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

    # Poll until authenticated
    info "Waiting for Tailscale to connect…"
    CONNECTED=false
    DEADLINE=$(( $(date +%s) + 180 ))
    while [[ $(date +%s) -lt $DEADLINE ]]; do
      BACKEND_STATE="$($DOCKER_CMD exec "$CONTAINER" tailscale status --json 2>/dev/null \
                       | grep -oE '"BackendState":"[^"]+"' \
                       | grep -oE '[^"]+$' || true)"
      if [[ "$BACKEND_STATE" == "Running" ]]; then
        CONNECTED=true
        break
      fi
      sleep 3
    done

    if [[ "$CONNECTED" == "true" ]]; then
      TAILNET_URL="$($DOCKER_CMD exec "$CONTAINER" tailscale status --json 2>/dev/null \
                     | grep -oE '"DNSName":"[^"]+"' | head -1 \
                     | grep -oE '"[^"]+$' | tr -d '"' || true)"
      if [[ -n "$TAILNET_URL" ]]; then
        success "Tailscale connected! Access Fox at:  https://${TAILNET_URL%\.}"
      else
        success "Tailscale connected!"
      fi
    else
      warn "Tailscale not yet confirmed running. Check with: docker exec $CONTAINER tailscale status"
    fi
  fi
fi

##############################################################################
# 8 / 9. Install service manager integration
##############################################################################
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

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
if [[ "$ACCESS_MODE" == "1" || "$ACCESS_MODE" == "3" ]]; then
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
