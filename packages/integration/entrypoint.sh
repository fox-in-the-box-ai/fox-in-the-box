#!/usr/bin/env bash
# /app/entrypoint.sh — Fox in the Box container entrypoint
set -euo pipefail

# ── Constants ─────────────────────────────────────────────────────────────────
ONBOARDING_FLAG="/data/config/onboarding.json"
DEFAULTS_DIR="/app/defaults"
DATA_VERSION_FILE="/data/version.txt"
APP_VERSION_FILE="/app/version.txt"
APPS_DIR="/data/apps"
FITB_VERSION=$(cat "$APP_VERSION_FILE" 2>/dev/null || echo "v0.1.0")

# ── 1. First-run detection ─────────────────────────────────────────────────────
if [ ! -f "$ONBOARDING_FLAG" ]; then
    echo "[entrypoint] First run detected — bootstrapping /data ..."

    # Create full directory structure
    mkdir -p \
        /data/apps \
        /data/config \
        /data/data/hermes \
        /data/data/mem0 \
        /data/data/memos \
        /data/data/tailscale \
        /data/cache \
        /data/logs \
        /data/run

    # Seed default configs (only if the source directory exists)
    if [ -d "$DEFAULTS_DIR" ]; then
        cp -n "$DEFAULTS_DIR"/* /data/config/ 2>/dev/null || true
    fi

    # Write initial onboarding marker
    echo '{"completed": false}' > "$ONBOARDING_FLAG"

    echo "[entrypoint] Bootstrap complete."
else
    echo "[entrypoint] Existing /data detected — skipping first-run bootstrap."

    # Ensure any directories added in later versions are present
    mkdir -p \
        /data/apps \
        /data/config \
        /data/data/hermes \
        /data/data/mem0 \
        /data/data/memos \
        /data/data/tailscale \
        /data/cache \
        /data/logs \
        /data/run
fi

# ── 2. App code bootstrap (git-in-volume model) ────────────────────────────────
# hermes-agent and hermes-webui live as git repos on the /data volume.
# Clone on first run, skip if already present. Updates happen separately.
_clone_app() {
    local APP="$1"
    local DEST="$APPS_DIR/$APP"

    if [ -d "$DEST/.git" ]; then
        echo "[entrypoint] $APP already present at $DEST — skipping clone."
        return 0
    fi

    echo "[entrypoint] Cloning $APP @ $FITB_VERSION ..."
    # Remove any partial clone before retrying
    rm -rf "$DEST"
    if ! git clone --depth 1 \
            --branch "$FITB_VERSION" \
            "https://github.com/fox-in-the-box-ai/$APP" \
            "$DEST" 2>/dev/null; then
        echo "[entrypoint] Tag $FITB_VERSION not found — falling back to main branch ..."
        if ! git clone --depth 1 \
                --branch main \
                "https://github.com/fox-in-the-box-ai/$APP" \
                "$DEST"; then
            echo "[entrypoint] ERROR: Failed to clone $APP. Check network and try again."
            echo "[entrypoint] If offline, manually place a git repo at $DEST and restart."
            exit 1
        fi
    fi

    echo "[entrypoint] Installing $APP ..."
    pip install -e "$DEST" --quiet --no-cache-dir
    echo "[entrypoint] $APP ready."
}

_clone_app hermes-agent
_clone_app hermes-webui

# ── 3. Version migration ───────────────────────────────────────────────────────
CURRENT_VERSION="0.0.0"
if [ -f "$DATA_VERSION_FILE" ]; then
    CURRENT_VERSION=$(cat "$DATA_VERSION_FILE")
fi

LATEST_VERSION=$(cat "$APP_VERSION_FILE" 2>/dev/null || echo "0.0.0")

if [ "$CURRENT_VERSION" != "$LATEST_VERSION" ]; then
    echo "[entrypoint] Version change detected: $CURRENT_VERSION -> $LATEST_VERSION"
    if [ -x "/app/scripts/migrate.sh" ]; then
        /app/scripts/migrate.sh "$CURRENT_VERSION" "$LATEST_VERSION"
    else
        echo "[entrypoint] WARNING: /app/scripts/migrate.sh not found — skipping migration."
    fi
    echo "$LATEST_VERSION" > "$DATA_VERSION_FILE"
    echo "[entrypoint] Version file updated to $LATEST_VERSION."
else
    echo "[entrypoint] Version unchanged ($CURRENT_VERSION) — no migration needed."
fi

# ── 4. Fix permissions ─────────────────────────────────────────────────────────
# Exclude /data/data/tailscale — tailscaled runs as root and manages its own state.
echo "[entrypoint] Setting ownership on /data ..."
chown -R foxinthebox:foxinthebox \
    /data/apps \
    /data/config \
    /data/data/hermes \
    /data/data/mem0 \
    /data/data/memos \
    /data/cache \
    /data/logs
# /data/run is kept root-owned so supervisord can write its pidfile.
# /data/data/tailscale is kept root-owned so tailscaled can write state.
chown root:root /data/run /data/data/tailscale

# ── 5. Load environment ────────────────────────────────────────────────────────
HERMES_ENV="/data/config/hermes.env"
if [ -f "$HERMES_ENV" ]; then
    echo "[entrypoint] Loading environment from $HERMES_ENV ..."
    set -a
    # shellcheck source=/dev/null
    source "$HERMES_ENV"
    set +a
fi

# ── 6. Hand off to supervisord ─────────────────────────────────────────────────
echo "[entrypoint] Starting supervisord ..."
exec /usr/local/bin/supervisord -c /etc/supervisor/supervisord.conf
