#!/usr/bin/env bash
# /app/entrypoint.sh — Fox in the Box container entrypoint
set -euo pipefail

# ── Constants ─────────────────────────────────────────────────────────────────
ONBOARDING_FLAG="/data/config/onboarding.json"
DEFAULTS_DIR="/app/defaults"
DATA_VERSION_FILE="/data/version.txt"
APP_VERSION_FILE="/app/version.txt"
APPS_DIR="/data/apps"
REPO_SYNC_VERSION_FILE="$APPS_DIR/.repo-sync-version"
FITB_VERSION=$(cat "$APP_VERSION_FILE" 2>/dev/null || echo "v0.1.0")
FITB_DEV=${FITB_DEV:-0}  # Set by docker build --build-arg FITB_DEV=1

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

# ── 2. App code bootstrap (git-in-volume model) ────────────────────────────────
# hermes-agent and hermes-webui live as git repos on the /data volume.
# Clone on first run, skip if already present. Updates happen separately.
# If FITB_DEV=1, skip cloning and use bind-mounted repos instead.
if [ "$FITB_DEV" = "1" ]; then
    echo "[entrypoint] Dev mode — skipping git clone, will use bind-mounted repos"
else
    _sync_app() {
        local APP="$1"
        local DEST="$APPS_DIR/$APP"
        local STAGING="${DEST}.new"
        local BACKUP="${DEST}.previous"
        local CLONE_OK=0

        echo "[entrypoint] Syncing $APP @ $FITB_VERSION ..."
        rm -rf "$STAGING"
        if git clone --depth 1 \
                --branch "$FITB_VERSION" \
                "https://github.com/fox-in-the-box-ai/$APP" \
                "$STAGING" 2>/dev/null; then
            CLONE_OK=1
        else
            echo "[entrypoint] Tag $FITB_VERSION not found — falling back to default branch ..."
            if git clone --depth 1 \
                    "https://github.com/fox-in-the-box-ai/$APP" \
                    "$STAGING"; then
                CLONE_OK=1
            fi
        fi

        if [ "$CLONE_OK" != "1" ]; then
            echo "[entrypoint] ERROR: Failed to sync $APP. Check network and try again."
            if [ -d "$DEST/.git" ]; then
                echo "[entrypoint] Using existing local copy at $DEST."
            else
                echo "[entrypoint] No existing copy found for $APP — cannot continue."
                exit 1
            fi
        else
            # Atomic-ish swap: always move existing repo away, then promote staged clone.
            rm -rf "$BACKUP"
            if [ -d "$DEST" ]; then
                mv "$DEST" "$BACKUP"
            fi
            mv "$STAGING" "$DEST"
        fi

        echo "[entrypoint] Installing $APP ..."
        local INSTALL_OK=1
        if [ -f "$DEST/setup.py" ] || [ -f "$DEST/pyproject.toml" ]; then
            if ! pip install -e "$DEST" --quiet --no-cache-dir; then
                INSTALL_OK=0
            fi
        elif [ -f "$DEST/requirements.txt" ]; then
            if ! pip install -r "$DEST/requirements.txt" --quiet --no-cache-dir; then
                INSTALL_OK=0
            fi
        else
            echo "[entrypoint] WARNING: No installable package or requirements.txt in $APP — skipping pip install."
        fi

        if [ "$INSTALL_OK" != "1" ]; then
            echo "[entrypoint] ERROR: Dependency install for $APP failed."
            if [ -d "$BACKUP" ]; then
                echo "[entrypoint] Restoring previous $APP from backup."
                rm -rf "$DEST"
                mv "$BACKUP" "$DEST"
            fi
            exit 1
        fi

        # Cleanup backup only after successful install.
        rm -rf "$BACKUP"
        echo "[entrypoint] $APP ready."
    }

    SHOULD_SYNC_REPOS=0
    SYNC_REASON=""
    SYNC_VERSION=$(cat "$REPO_SYNC_VERSION_FILE" 2>/dev/null || true)
    if [ -z "$SYNC_VERSION" ]; then
        SHOULD_SYNC_REPOS=1
        SYNC_REASON="first repo sync"
    elif [ "$SYNC_VERSION" != "$FITB_VERSION" ]; then
        SHOULD_SYNC_REPOS=1
        SYNC_REASON="version changed ($SYNC_VERSION -> $FITB_VERSION)"
    elif [ ! -d "$APPS_DIR/hermes-agent/.git" ] || [ ! -d "$APPS_DIR/hermes-webui/.git" ]; then
        SHOULD_SYNC_REPOS=1
        SYNC_REASON="repo missing or incomplete"
    fi

    if [ "$SHOULD_SYNC_REPOS" = "1" ]; then
        echo "[entrypoint] Repo sync required: $SYNC_REASON"
        _sync_app hermes-agent
        _sync_app hermes-webui
        echo "$FITB_VERSION" > "$REPO_SYNC_VERSION_FILE"
        echo "[entrypoint] Repo sync marker updated to $FITB_VERSION."
    else
        echo "[entrypoint] Repo sync not required (marker=$SYNC_VERSION)."
    fi
fi

# ── 2b. Dev mode initialization (if FITB_DEV=1) ─────────────────────────────────
if [ "$FITB_DEV" = "1" ]; then
    echo "[entrypoint] Dev mode detected (FITB_DEV=1) — using bind-mounted repos"
    if [ -x "/app/scripts/dev-init.sh" ]; then
        /app/scripts/dev-init.sh
    else
        echo "[entrypoint] WARNING: /app/scripts/dev-init.sh not found"
    fi
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

# ── 5b. Patch hermes.yaml with runtime env vars ────────────────────────────────
# Replace ${BRAVE_API_KEY} placeholder so Hermes MCP server gets the real key.
HERMES_YAML="/data/config/hermes.yaml"
if [ -f "$HERMES_YAML" ] && [ -n "${BRAVE_API_KEY:-}" ]; then
    sed -i "s|\${BRAVE_API_KEY}|${BRAVE_API_KEY}|g" "$HERMES_YAML"
    echo "[entrypoint] Patched BRAVE_API_KEY into $HERMES_YAML"
fi

# ── 6. Configure Tailscale Serve (if Tailscale state exists) ──────────────────
# tailscale serve routes https://<machine>.tailnet.ts.net → http://localhost:8787
# This is a no-op if Tailscale is not yet authenticated.
if [ -f "/data/data/tailscale/tailscaled.state" ]; then
    echo "[entrypoint] Configuring Tailscale Serve..."
    tailscale serve --bg / http://localhost:8787 2>/dev/null || \
        echo "[entrypoint] WARNING: tailscale serve failed (daemon may not be ready yet — will retry at next restart)."
fi

# ── 6b. Patch supervisord.conf with runtime env vars ──────────────────────────
# supervisord %(ENV_VAR)s expansion fails when the var is absent from the process
# environment. Use a placeholder + sed to inject the value (or empty string) at
# runtime so supervisord always starts cleanly.
SUPERVISORD_CONF="/etc/supervisor/supervisord.conf"
sed -i "s|__BRAVE_API_KEY__|${BRAVE_API_KEY:-}|g" "$SUPERVISORD_CONF"

# ── 7. Hand off to supervisord ─────────────────────────────────────────────────
echo "[entrypoint] Starting supervisord ..."
exec /usr/local/bin/supervisord -c /etc/supervisor/supervisord.conf
