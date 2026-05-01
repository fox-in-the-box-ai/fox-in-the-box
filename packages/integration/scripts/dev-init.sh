#!/usr/bin/env bash
# /app/scripts/dev-init.sh — Dev mode validation (bind mounts from host)
# Only runs when FITB_DEV=1 is set during docker build
set -euo pipefail

echo "[dev-init] Dev mode — validating bind-mounted repos"

# Check that bind mounts are present
HERMES_AGENT="/root/.hermes/hermes-agent"
HERMES_WEBUI="/root/.hermes/hermes-webui"

STATUS=0

if [ ! -d "$HERMES_AGENT/.git" ]; then
    echo "[dev-init] ✗ ERROR: $HERMES_AGENT/.git not found"
    echo "[dev-init]   Did you mount it? -v \$(pwd)/forks/hermes-agent:$HERMES_AGENT"
    STATUS=1
else
    echo "[dev-init] ✓ hermes-agent bound"
    AGENT_BRANCH=$(cd "$HERMES_AGENT" && git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
    AGENT_COMMIT=$(cd "$HERMES_AGENT" && git rev-parse --short HEAD 2>/dev/null || echo "unknown")
    echo "[dev-init]   Branch: $AGENT_BRANCH, Commit: $AGENT_COMMIT"
fi

if [ ! -d "$HERMES_WEBUI/.git" ]; then
    echo "[dev-init] ✗ ERROR: $HERMES_WEBUI/.git not found"
    echo "[dev-init]   Did you mount it? -v \$(pwd)/forks/hermes-webui:$HERMES_WEBUI"
    STATUS=1
else
    echo "[dev-init] ✓ hermes-webui bound"
    WEBUI_BRANCH=$(cd "$HERMES_WEBUI" && git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
    WEBUI_COMMIT=$(cd "$HERMES_WEBUI" && git rev-parse --short HEAD 2>/dev/null || echo "unknown")
    echo "[dev-init]   Branch: $WEBUI_BRANCH, Commit: $WEBUI_COMMIT"
fi

if [ $STATUS -ne 0 ]; then
    echo "[dev-init] ERROR: Dev mode requires both repos to be bind-mounted. Exiting."
    exit 1
fi

echo "[dev-init] Dev initialization OK"
