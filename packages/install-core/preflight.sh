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
    - ${DATA_DIR}/apps/hermes-agent/skills
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

# ── 10. Tailscale Serve ──────────────────────────────────────────────────────
# Moved to foxinthebox-tailscale-serve.service (ExecStartPost= in the main
# unit). Running a background subshell in ExecStartPre= is unsafe — systemd
# may reap it when the pre-start phase completes.
# See: packages/deb/templates/foxinthebox-tailscale-serve.service.tmpl

_log "Preflight complete."
