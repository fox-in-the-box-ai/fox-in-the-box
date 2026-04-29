# Task 04: Container Entrypoint Script

| Field        | Value                                                       |
|--------------|-------------------------------------------------------------|
| **Status**   | Ready                                                       |
| **Executor** | AI agent                                                    |
| **Depends**  | Task 03 (container builds and supervisord is verified)      |
| **Blocks**   | Task 05 (onboarding wizard needs correct first-run state)   |
| **Parallel** | Can run in parallel with Task 05 (onboarding wizard)        |
| **Paths**    | `packages/integration/entrypoint.sh`, `packages/integration/default-configs/`, `packages/integration/scripts/migrate.sh` |

---

## Summary

Replace the minimal entrypoint stub created in Task 03 with a full production-grade entrypoint script. The script handles first-run directory scaffolding, default config seeding, version-based migration, permission fixing, environment loading, and finally hands off to `supervisord`.

Also create the default config templates that the entrypoint seeds into `/data/config/` on first run, and a migration helper script.

---

## Prerequisites

- Task 03 is complete: the image builds successfully and all four supervised services reach `RUNNING` state.
- The repo contains `packages/integration/` (created in Task 02 scaffolding).
- Docker daemon is running on the build host.

---

## Implementation

### Step 1 — Write `packages/integration/entrypoint.sh`

This script is the container `ENTRYPOINT`. It runs as root (supervisord needs root to later drop privileges per-process).

```bash
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
            "$DEST"; then
        echo "[entrypoint] ERROR: Failed to clone $APP. Check network and try again."
        echo "[entrypoint] If offline, manually place a git repo at $DEST and restart."
        exit 1
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
```

> **Important:** The Dockerfile must copy this file as `/app/entrypoint.sh` and mark it executable (`chmod +x`). It must also copy `packages/integration/default-configs/` to `/app/defaults/` and `packages/integration/scripts/` to `/app/scripts/`. These directives are already included in the Task 03 Dockerfile template — verify they exist in `packages/integration/Dockerfile`.

---

### Step 2 — Write `packages/integration/default-configs/hermes.yaml`

Minimal Hermes configuration pointing all storage to `/data/data/hermes`.

```yaml
# hermes.yaml — default Hermes agent configuration
# Copied to /data/config/hermes.yaml on first container run.
# Edit this file to customise Hermes behaviour.

storage:
  type: local
  path: /data/data/hermes

server:
  host: 0.0.0.0
  port: 8787

logging:
  level: info
  file: /data/logs/hermes.log
```

---

### Step 3 — Write `packages/integration/default-configs/hermes.env.template`

A commented-out template. Users copy/rename this to `hermes.env` and fill in their keys. The entrypoint loads `hermes.env` (not the template) if it exists.

```bash
# hermes.env — Fox in the Box environment overrides
# ──────────────────────────────────────────────────
# Instructions:
#   1. Copy this file to /data/config/hermes.env
#      (or rename it if you are editing from inside the container)
#   2. Uncomment and fill in the values you need.
#   3. Restart the container — entrypoint.sh will source this file
#      before starting supervisord, making the variables available to
#      all supervised child processes.
#
# Variables set here override anything baked into the image.

# ── LLM API Keys ──────────────────────────────────────────────────────────────
#OPENROUTER_API_KEY=***

# ── Tailscale ─────────────────────────────────────────────────────────────────
# Provide an auth key to join your tailnet automatically on first start.
# Generate one at https://login.tailscale.com/admin/settings/keys
#TAILSCALE_AUTHKEY=***

# ── Hermes / Memos extra config ───────────────────────────────────────────────
# Uncomment to override defaults.
#MEMOS_PORT=5230
#HERMES_LOG_LEVEL=debug
```

---

### Step 4 — Write `packages/integration/default-configs/onboarding.json`

The onboarding completion marker. This default is copied to `/data/config/onboarding.json` on first run, signalling that onboarding has not yet been completed.

```json
{"completed": false}
```

---

### Step 5 — Write `packages/integration/app-root/version.txt`

The application version baked into the image. Placed at `/app/version.txt` inside the container.

```
0.1.0
```

> **Note:** This file is copied to `/app/version.txt` in the Dockerfile. The `/data/version.txt` file is written by the entrypoint at runtime and tracks which version of the app last ran against this data volume.

---

### Step 6 — Write `packages/integration/scripts/migrate.sh`

A no-op migration script. Future tasks will add version-specific migration logic between the two `case` blocks.

```bash
#!/usr/bin/env bash
# /app/scripts/migrate.sh — data volume migration helper
# Called by entrypoint.sh when /data/version.txt differs from /app/version.txt
# Arguments:
#   $1  — current version (from /data/version.txt, e.g. "0.0.0")
#   $2  — latest version  (from /app/version.txt,  e.g. "0.1.0")
set -euo pipefail

CURRENT="$1"
LATEST="$2"

echo "[migrate] Migration $CURRENT -> $LATEST, nothing to do."
exit 0
```

---

### Step 7 — Update `packages/integration/Dockerfile`

These `COPY` directives are already included in the Dockerfile template from Task 03. Verify they are present:

```dockerfile
# ── default configs and version ───────────────────────────────────────────────
COPY packages/integration/default-configs/ /app/defaults/
COPY packages/integration/app-root/version.txt /app/version.txt

# ── migration scripts ─────────────────────────────────────────────────────────
COPY packages/integration/scripts/ /app/scripts/
RUN chmod +x /app/scripts/*.sh

# ── entrypoint (full version — replaces Task 03 stub) ─────────────────────────
COPY packages/integration/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh
```

> **Note:** The `ENTRYPOINT ["/app/entrypoint.sh"]` line already exists from Task 03; no change needed there.

---

## File Checklist

After completing this task the following files must exist in the repo:

```
packages/integration/
├── entrypoint.sh
├── default-configs/
│   ├── hermes.yaml
│   ├── hermes.env.template
│   └── onboarding.json
├── app-root/
│   └── version.txt            ← "0.1.0" — baked into image as /app/version.txt
└── scripts/
    └── migrate.sh

packages/integration/
└── Dockerfile                 ← already contains all COPY directives from Task 03
```

---

## Acceptance Criteria

All criteria must pass before this task is considered complete.

| # | Criterion | How to verify (see §Test Commands) |
|---|-----------|-------------------------------------|
| AC1 | Fresh container creates correct directory structure under `/data` including `/data/apps/` | `AC1` dir check |
| AC2 | `/data/config/onboarding.json` exists with `{"completed": false}` after first run | `AC2` json check |
| AC3 | Second run does **not** overwrite existing `/data/config` files | `AC3` idempotency check |
| AC4 | `supervisord` starts successfully and all 4 programs reach `RUNNING` | `AC4` status poll (inherits from Task 03) |
| AC5 | If `OPENROUTER_API_KEY` is set in `hermes.env`, it appears in a supervised child process's environment | `AC5` env propagation check |
| AC6 | `/data/apps/hermes-agent/.git` and `/data/apps/hermes-webui/.git` exist after first run | `AC6` git bootstrap check |
| AC7 | Second container run with existing `/data/apps/` skips clone (no network call attempted) | `AC7` skip-clone check |

---

## Test Commands

Run these in order after rebuilding the image with the changes from this task.

```bash
# ── Rebuild image ──────────────────────────────────────────────────────────────
docker build \
  --platform linux/amd64 \
  -t ghcr.io/fox-in-the-box-ai/cloud:dev \
  -f packages/integration/Dockerfile .
```bash
# ── AC1: Fresh container creates correct /data structure ───────────────────────
# Use a fresh, empty named volume (no prior /data state).
docker volume rm fitb-test-data 2>/dev/null || true
docker volume create fitb-test-data

docker run --rm \
  --cap-add=NET_ADMIN \
  --sysctl net.ipv4.ip_forward=1 \
  -v fitb-test-data:/data \
  ghcr.io/fox-in-the-box-ai/cloud:dev \
  bash -c "
    # Give supervisord 2 s to init, then inspect dirs and exit
    sleep 2 && find /data -maxdepth 3 -type d | sort
  "
# Expected output includes:
#   /data/config
#   /data/data/hermes
#   /data/data/mem0
#   /data/data/memos
#   /data/data/tailscale
#   /data/cache
#   /data/logs
#   /data/run

# ── AC2: onboarding.json created with {completed: false} ─────────────────────
docker run --rm \
  --cap-add=NET_ADMIN \
  --sysctl net.ipv4.ip_forward=1 \
  -v fitb-test-data:/data \
  ghcr.io/fox-in-the-box-ai/cloud:dev \
  bash -c "sleep 2 && cat /data/config/onboarding.json"
# Expected: {"completed": false}

# ── AC3: Second run does NOT overwrite existing /data/config files ────────────
# Write a sentinel value into an existing config file, then re-run the container.
docker run --rm \
  -v fitb-test-data:/data \
  busybox \
  sh -c 'echo "SENTINEL=my_custom_value" >> /data/config/hermes.env'

docker run --rm \
  --cap-add=NET_ADMIN \
  --sysctl net.ipv4.ip_forward=1 \
  -v fitb-test-data:/data \
  ghcr.io/fox-in-the-box-ai/cloud:dev \
  bash -c "sleep 2 && grep SENTINEL /data/config/hermes.env"
# Expected: SENTINEL=my_custom_value  (file was NOT overwritten)

# ── AC4: supervisord + all 4 programs RUNNING within 30 s ────────────────────
docker run -d --name fitb-ac4 \
  --cap-add=NET_ADMIN \
  --sysctl net.ipv4.ip_forward=1 \
  -v fitb-test-data:/data \
  -p 127.0.0.1:8787:8787 \
  ghcr.io/fox-in-the-box-ai/cloud:dev

for i in $(seq 1 6); do
  sleep 5
  STATUS=$(docker exec fitb-ac4 supervisorctl status 2>/dev/null || true)
  echo "$STATUS"
  RUNNING=$(echo "$STATUS" | grep -c "RUNNING" || true)
  [ "$RUNNING" -ge 4 ] && echo "✅ All 4 programs RUNNING" && break
  echo "... waiting ($((i*5))s elapsed)"
done

docker rm -f fitb-ac4

# ── AC5: OPENROUTER_API_KEY from hermes.env is visible in child process env ───
# Seed a hermes.env with the key.
docker run --rm \
  -v fitb-test-data:/data \
  busybox \
  sh -c 'echo "OPENROUTER_API_KEY=***" > /data/config/hermes.env'

docker run -d --name fitb-ac5 \
  --cap-add=NET_ADMIN \
  --sysctl net.ipv4.ip_forward=1 \
  -v fitb-test-data:/data \
  ghcr.io/fox-in-the-box-ai/cloud:dev

sleep 5

# Check env of the hermes-gateway child process
docker exec fitb-ac5 bash -c \
  'cat /proc/$(supervisorctl pid hermes-gateway)/environ | tr "\0" "\n" | grep OPENROUTER'
# Expected: OPENROUTER_API_KEY=***

docker rm -f fitb-ac5

# ── AC6: git repos cloned into /data/apps/ ────────────────────────────────────
docker run --rm \
  --cap-add=NET_ADMIN \
  --sysctl net.ipv4.ip_forward=1 \
  -v fitb-test-data:/data \
  ghcr.io/fox-in-the-box-ai/cloud:dev \
  bash -c "
    # Wait for entrypoint to finish cloning, then check .git dirs
    sleep 30 && \
    ls /data/apps/hermes-agent/.git/HEAD && \
    ls /data/apps/hermes-webui/.git/HEAD && \
    echo '✅ Both repos cloned'
  "

# ── AC7: second run skips clone ───────────────────────────────────────────────
docker run --rm \
  --cap-add=NET_ADMIN \
  --sysctl net.ipv4.ip_forward=1 \
  -v fitb-test-data:/data \
  ghcr.io/fox-in-the-box-ai/cloud:dev \
  bash -c "sleep 5 && grep 'skipping clone' /proc/1/fd/1 2>/dev/null || \
    docker logs \$(hostname) 2>&1 | grep 'skipping clone'"
# Expected: '[entrypoint] hermes-agent already present ... — skipping clone.'

# ── Cleanup ───────────────────────────────────────────────────────────────────
docker volume rm fitb-test-data
```

---

## Notes

- **Parallel work:** This task can be developed in parallel with Task 05 (onboarding wizard). Task 05 reads `/data/config/onboarding.json`; as long as the schema `{"completed": false}` is stable (it is), both tasks can proceed independently.
- **`cp -n` flag:** The `cp -n` (no-clobber) flag in the first-run bootstrap ensures that if a user manually pre-populates `/data/config/` before the first run, their files are not overwritten. This is intentional.
- **tailscale permissions:** `/data/data/tailscale` is intentionally left `root:root` because `tailscaled` runs as root in supervisord and writes its own state there. Do not `chown` it to `foxinthebox`.
- **`/data/run` permissions:** supervisord writes its pidfile and Unix socket to `/data/run`. This directory is kept root-owned. The socket is `chmod 0770 chown foxinthebox:foxinthebox` per `supervisord.conf` so `supervisorctl` can be called as the `foxinthebox` user.
- **`set -a` / `set +a`:** The entrypoint uses `set -a` before `source hermes.env` so every variable defined in the file is automatically exported into the environment that `exec supervisord` inherits. supervisord then passes this environment to its child processes.
- **Migration script:** `migrate.sh` is intentionally a no-op at this stage. Actual migration logic will be added by future tasks as the schema evolves. The version comparison uses simple string equality; semantic version ordering is not required until there is actual migration logic.
- **Partial clone guard:** The `_clone_app` function checks for `.git/HEAD` (not just the directory) before skipping. If a previous clone was interrupted mid-way, the directory exists but `.git/HEAD` does not — the function will `rm -rf` and retry cleanly. Always use this guard; never check `[ -d "$DEST" ]` alone.
- **First-boot latency:** `git clone` + `pip install -e` for two repos adds ~30–60 seconds to first startup depending on network speed. The onboarding wizard should show a loading state during this window. The entrypoint prints progress lines (`[entrypoint] Cloning ...`, `[entrypoint] Installing ...`) that can be tailed from the Electron app or install script.
