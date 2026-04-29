#!/usr/bin/env bash
# /app/entrypoint.sh — Fox in the Box container entrypoint (task 03 bootstrap).
# Task 04 will extend with full onboarding, migrations, and env loading.
set -euo pipefail

DEFAULTS_DIR="/app/defaults"
APPS_DIR="/data/apps"
APP_VERSION_FILE="/app/version.txt"
FITB_VERSION="$(tr -d '[:space:]' <"$APP_VERSION_FILE" 2>/dev/null || echo 'v0.1.0')"

bootstrap_data_dirs() {
    mkdir -p \
        "$APPS_DIR" \
        /data/config \
        /data/data/hermes \
        /data/data/mem0 \
        /data/data/tailscale \
        /data/cache \
        /data/logs \
        /data/run

    if [ -d "$DEFAULTS_DIR" ]; then
        # Do not overwrite user-edited configs on restart
        cp -n "$DEFAULTS_DIR"/* /data/config/ 2>/dev/null || true
    fi
}

install_app_dependencies() {
    local dest="$1"
    if [ -f "$dest/pyproject.toml" ] || [ -f "$dest/setup.py" ]; then
        pip install -e "$dest" --quiet --no-cache-dir
    elif [ -f "$dest/requirements.txt" ]; then
        pip install -r "$dest/requirements.txt" --quiet --no-cache-dir
    fi
}

clone_fitb_app() {
    local app="$1"
    local dest="$APPS_DIR/$app"

    if [ -d "$dest/.git" ]; then
        echo "[entrypoint] $app already present — skipping clone."
        return 0
    fi

    rm -rf "$dest"
    echo "[entrypoint] Cloning $app (tag $FITB_VERSION) ..."
    if git clone --depth 1 --branch "$FITB_VERSION" \
        "https://github.com/fox-in-the-box-ai/$app" "$dest" 2>/dev/null; then
        :
    else
        echo "[entrypoint] Tag $FITB_VERSION unavailable for $app; falling back to main."
        git clone --depth 1 --branch main \
            "https://github.com/fox-in-the-box-ai/$app" "$dest"
    fi

    echo "[entrypoint] Installing Python dependencies for $app ..."
    install_app_dependencies "$dest"
    echo "[entrypoint] $app ready."
}

bootstrap_data_dirs

clone_fitb_app hermes-agent
clone_fitb_app hermes-webui

chown -R foxinthebox:foxinthebox /data/data /data/logs /data/apps /data/config /data/cache

exec /usr/local/bin/supervisord -c /etc/supervisor/supervisord.conf
