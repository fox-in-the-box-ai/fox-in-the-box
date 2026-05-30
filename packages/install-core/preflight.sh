#!/usr/bin/env bash
# preflight.sh — Fox in the Box bare-metal pre-start script
#
# Called by ExecStartPre= in foxinthebox.service on every start.
# Replicates the first-run bootstrap, migration, and Tailscale Serve
# setup from packages/integration/entrypoint.sh — adapted for bare-metal
# (no /app or /data container paths; uses /opt/foxinthebox and ~/.foxinthebox).
#
# Idempotent — safe on every start.

set -euo pipefail

APP_DIR="/opt/foxinthebox"
DATA_DIR="${FITB_DATA_DIR:-$HOME/.foxinthebox}"
DATA_VERSION_FILE="$DATA_DIR/version.txt"
APP_VERSION_FILE="$APP_DIR/version.txt"
ONBOARDING_FLAG="$DATA_DIR/config/onboarding.json"
DEFAULTS_DIR="$APP_DIR/defaults"
APPS_DIR="$DATA_DIR/apps"

_log() { echo "[preflight] $*"; }
_warn() { echo "[preflight] WARNING: $*" >&2; }

# ── 1. First-run or upgrade: bootstrap directory tree ─────────────────────────
mkdir -p \
    "$APPS_DIR" \
    "$DATA_DIR/config" \
    "$DATA_DIR/data/hermes" \
    "$DATA_DIR/data/mem0" \
    "$DATA_DIR/data/memos" \
    "$DATA_DIR/data/tailscale" \
    "$DATA_DIR/cache" \
    "$DATA_DIR/logs" \
    "$DATA_DIR/run" \
    "$DATA_DIR/state/webui"

# ── 2. Seed default configs (cp -n = never overwrite user edits) ──────────────
if [ -d "$DEFAULTS_DIR" ]; then
    cp -n "$DEFAULTS_DIR"/* "$DATA_DIR/config/" 2>/dev/null || true
fi

# ── 3. Write onboarding marker if missing ────────────────────────────────────
if [ ! -f "$ONBOARDING_FLAG" ]; then
    echo '{"completed": false}' > "$ONBOARDING_FLAG"
    _log "First run — onboarding marker created."
fi

# ── 4. App symlinks ───────────────────────────────────────────────────────────
_link_app() {
    local name="$1" src="$2" dest="$APPS_DIR/$name"
    if [ -L "$dest" ] && [ "$(readlink -f "$dest" 2>/dev/null || true)" = "$(readlink -f "$src" 2>/dev/null || true)" ]; then
        return 0
    fi
    [ -e "$dest" ] && rm -rf "$dest"
    ln -sfn "$src" "$dest"
    _log "Linked $name -> $src"
}
_link_app hermes-agent "$APP_DIR/hermes-agent"
_link_app hermes-webui "$APP_DIR/hermes-webui"

# ── 5. Version migration ──────────────────────────────────────────────────────
CURRENT_VERSION="0.0.0"
[ -f "$DATA_VERSION_FILE" ] && CURRENT_VERSION=$(cat "$DATA_VERSION_FILE")
LATEST_VERSION=$(cat "$APP_VERSION_FILE" 2>/dev/null || echo "0.0.0")

if [ "$CURRENT_VERSION" != "$LATEST_VERSION" ]; then
    _log "Version change: $CURRENT_VERSION -> $LATEST_VERSION"
    if [ -x "$APP_DIR/scripts/migrate.sh" ]; then
        "$APP_DIR/scripts/migrate.sh" "$CURRENT_VERSION" "$LATEST_VERSION"
    else
        _warn "migrate.sh not found — skipping migration."
    fi
    echo "$LATEST_VERSION" > "$DATA_VERSION_FILE"
fi

# ── 6. Workspace directory ────────────────────────────────────────────────────
WORKSPACE_DIR="${FITB_WORKSPACE_DIR:-$HOME/Fox in the Box}"
mkdir -p "$WORKSPACE_DIR"

# ── 7. Load hermes.env + patch hermes.yaml ────────────────────────────────────
HERMES_ENV="$DATA_DIR/config/hermes.env"
if [ -f "$HERMES_ENV" ]; then
    set -a
    # shellcheck source=/dev/null
    source "$HERMES_ENV"
    set +a
fi

HERMES_YAML="$DATA_DIR/config/hermes.yaml"
if [ -f "$HERMES_YAML" ] && [ -n "${BRAVE_API_KEY:-}" ]; then
    sed -i "s|\${BRAVE_API_KEY}|${BRAVE_API_KEY}|g" "$HERMES_YAML"
fi

if [ -f "$HERMES_YAML" ] && ! grep -q "^skills:" "$HERMES_YAML"; then
    _log "Adding missing skills block to hermes.yaml..."
    cat >> "$HERMES_YAML" << 'EOF'

# ── Skills ────────────────────────────────────────────────────────────────────
skills:
  external_dirs:
    - /data/apps/hermes-agent/skills
EOF
fi

# ── 8. Patch supervisord.conf with runtime env vars ───────────────────────────
SUPERVISORD_CONF="/etc/foxinthebox/supervisord.conf"
sed -i "s|__BRAVE_API_KEY__|${BRAVE_API_KEY:-}|g" "$SUPERVISORD_CONF"

# ── 9. Ensure RPC socket directory exists ────────────────────────────────────
# systemd RuntimeDirectory=foxinthebox creates /run/foxinthebox, but
# supervisord needs it before it starts. Belt-and-suspenders.
mkdir -p /run/foxinthebox
chmod 750 /run/foxinthebox

# ── 10. Tailscale Serve (background — waits for WebUI and Tailscale login) ────
# Mirrors the background subshell in entrypoint.sh.
(
    sleep 10
    _health_dead=240
    _hi=0
    while [ "$_hi" -lt "$_health_dead" ]; do
        if curl -fsS --connect-timeout 2 --max-time 6 "http://127.0.0.1:8787/health" >/dev/null 2>&1; then
            _log "WebUI healthy — configuring Tailscale Serve..."
            break
        fi
        _hi=$((_hi + 2))
        sleep 2
    done
    if [ "$_hi" -ge "$_health_dead" ]; then
        _log "Tailscale Serve helper: WebUI not ready within ${_health_dead}s — skipping."
        exit 0
    fi

    # Grant operator access to foxinthebox user
    _opi=0
    while [ "$_opi" -lt 60 ]; do
        if tailscale set --operator=foxinthebox 2>/dev/null; then
            _log "Granted foxinthebox tailscale operator access."
            break
        fi
        _opi=$((_opi + 2))
        sleep 2
    done

    # Wait for Tailscale login (up to ~15 min)
    _ts_iters=450
    _ti=0
    while [ "$_ti" -lt "$_ts_iters" ]; do
        if tailscale status --json 2>/dev/null | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    sys.exit(0 if d.get('BackendState') == 'Running' else 1)
except Exception:
    sys.exit(1)
" 2>/dev/null; then
            if tailscale serve --bg 8787 2>/dev/null; then
                _log "Tailscale Serve configured (https -> localhost:8787)."
            else
                _warn "tailscale serve failed — may need HTTPS enabled at https://login.tailscale.com/admin/dns."
            fi
            exit 0
        fi
        _ti=$((_ti + 1))
        sleep 2
    done
    _log "Tailscale Serve not configured (no Running backend within timeout — OK for port-only)."
) &

_log "Preflight complete."
