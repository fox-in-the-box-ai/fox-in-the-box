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
FITB_DEV=${FITB_DEV:-0}  # 1 = bind mounts at /root/.hermes/* (see dev-init.sh)

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

    # Self-heal: if a previous install was partial, backfill any missing default configs.
    if [ -d "$DEFAULTS_DIR" ]; then
        cp -n "$DEFAULTS_DIR"/* /data/config/ 2>/dev/null || true
    fi
fi

# ── 2. Hermes app trees under /data/apps (supervisord paths) ───────────────────
# Production: repos are baked into the image at /app/hermes-* ; entrypoint places
# symlinks at /data/apps/hermes-* so the /data volume stays user state only.
# Dev (FITB_DEV=1): symlinks point at bind mounts under /root/.hermes/
_link_hermes_app() {
    local name="$1"
    local src="$2"
    local dest="$APPS_DIR/$name"

    mkdir -p "$APPS_DIR"
    if [ -L "$dest" ] && [ "$(readlink -f "$dest" 2>/dev/null || true)" = "$(readlink -f "$src" 2>/dev/null || true)" ]; then
        echo "[entrypoint] $name already linked -> $src"
        return 0
    fi
    if [ -e "$dest" ]; then
        echo "[entrypoint] Replacing $dest with symlink -> $src"
        rm -rf "$dest"
    fi
    ln -sfn "$src" "$dest"
    echo "[entrypoint] Linked $name -> $src"
}

if [ "$FITB_DEV" = "1" ]; then
    echo "[entrypoint] Dev mode — Hermes repos from bind mounts (/root/.hermes/)"
    if [ -x "/app/scripts/dev-init.sh" ]; then
        /app/scripts/dev-init.sh
    else
        echo "[entrypoint] WARNING: /app/scripts/dev-init.sh not found"
    fi
    _link_hermes_app hermes-agent "/root/.hermes/hermes-agent"
    _link_hermes_app hermes-webui "/root/.hermes/hermes-webui"
    echo "[entrypoint] Installing Hermes packages from bind mounts (editable) ..."
    pip install -e "$APPS_DIR/hermes-agent" --quiet --no-cache-dir
    if [ -f "$APPS_DIR/hermes-webui/pyproject.toml" ] || [ -f "$APPS_DIR/hermes-webui/setup.py" ]; then
        pip install -e "$APPS_DIR/hermes-webui" --quiet --no-cache-dir
    elif [ -f "$APPS_DIR/hermes-webui/requirements.txt" ]; then
        pip install -r "$APPS_DIR/hermes-webui/requirements.txt" --quiet --no-cache-dir
    else
        echo "[entrypoint] WARNING: hermes-webui has no pyproject.toml, setup.py, or requirements.txt — skipping pip."
    fi
else
    echo "[entrypoint] Hermes apps from container image (symlinks under $APPS_DIR)"
    if [ ! -d "/app/hermes-agent" ] || [ ! -d "/app/hermes-webui" ]; then
        echo "[entrypoint] ERROR: Baked Hermes trees missing under /app/ — image build is broken."
        exit 1
    fi
    _link_hermes_app hermes-agent "/app/hermes-agent"
    _link_hermes_app hermes-webui "/app/hermes-webui"
fi

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
# /data/run is kept root-owned (reserved for future use; supervisord pid/socket are
# under /run/fitb so bind-mounted /data from Docker Desktop does not break AF_UNIX).
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

# ── 5b. Patch hermes.yaml with runtime env vars ────────────────────────────────
# Replace ${BRAVE_API_KEY} placeholder so Hermes MCP server gets the real key.
HERMES_YAML="/data/config/hermes.yaml"
if [ -f "$HERMES_YAML" ] && [ -n "${BRAVE_API_KEY:-}" ]; then
    sed -i "s|\${BRAVE_API_KEY}|${BRAVE_API_KEY}|g" "$HERMES_YAML"
    echo "[entrypoint] Patched BRAVE_API_KEY into $HERMES_YAML"
fi

# ── 6. Tailscale Serve (deferred until WebUI answers /health) ─────────────────
# Do not run `tailscale serve` before supervisord — nothing listens on :8787 yet.
# A background loop waits for Hermes WebUI then runs `tailscale serve --bg` once.
if [ -f "/data/data/tailscale/tailscaled.state" ]; then
    echo "[entrypoint] Tailscale state present — Serve will configure after WebUI is up (background)."
    (
        _ts_deadline=240
        _ts_i=0
        while [ "$_ts_i" -lt "$_ts_deadline" ]; do
            if curl -fsS --connect-timeout 2 --max-time 6 "http://127.0.0.1:8787/health" >/dev/null 2>&1; then
                if tailscale serve --bg / http://localhost:8787 2>/dev/null; then
                    echo "[entrypoint] Tailscale Serve configured (https → localhost:8787)."
                else
                    echo "[entrypoint] WARNING: tailscale serve failed — will retry on next container restart."
                fi
                exit 0
            fi
            _ts_i=$((_ts_i + 2))
            sleep 2
        done
        echo "[entrypoint] WARNING: Tailscale Serve skipped (WebUI /health not ready within ${_ts_deadline}s)."
    ) &
fi

# ── 6b. Patch supervisord.conf with runtime env vars ──────────────────────────
# supervisord %(ENV_VAR)s expansion fails when the var is absent from the process
# environment. Use a placeholder + sed to inject the value (or empty string) at
# runtime so supervisord always starts cleanly.
SUPERVISORD_CONF="/etc/supervisor/supervisord.conf"
sed -i "s|__BRAVE_API_KEY__|${BRAVE_API_KEY:-}|g" "$SUPERVISORD_CONF"

# ── 6c. Supervisord RPC socket directory (must not be on a host bind-mounted /data)
mkdir -p /run/fitb
chmod 755 /run/fitb

# ── 7. Hand off to supervisord ─────────────────────────────────────────────────
echo "[entrypoint] Starting supervisord ..."
exec /usr/local/bin/supervisord -c /etc/supervisor/supervisord.conf
