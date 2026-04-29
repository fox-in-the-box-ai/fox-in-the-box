# Task 03: Dockerfile and Container Build

| Field        | Value                                      |
|--------------|--------------------------------------------|
| **Status**   | Ready                                      |
| **Executor** | AI agent                                   |
| **Depends**  | Task 02 (repository scaffolding complete)  |
| **Blocks**   | Task 04 (entrypoint.sh), Task 05 (onboarding UI) |
| **Path**     | `packages/integration/Dockerfile`, `packages/integration/supervisord.conf` |

---

## Summary

Write the `Dockerfile` and `supervisord.conf` for the single-container Fox in the Box image, then verify the image builds cleanly and all four supervised services reach `RUNNING` state within 30 seconds of container start.

This is **critical path** — tasks 04 and 05 depend on a working container.

---

## Prerequisites

- Task 02 is complete (repo scaffolded with `packages/integration/` directory in place).
- Docker is installed and the daemon is running on the build host.
- Outbound internet access is available (pip, apt, GitHub releases).

---

## Container Overview

| Concern          | Choice                                                  |
|------------------|---------------------------------------------------------|
| Base image       | `python:3.11-slim` (Debian-based)                       |
| Process manager  | `supervisord` (via `pip install supervisor`)            |
| Runtime user     | `foxinthebox` (non-root) — except `tailscaled` (needs root)  |
| Exposed ports    | `8787` (webui), `6333` (Qdrant — internal only)         |
| Persistent data  | `/data` volume                                          |
| Entrypoint       | `/app/entrypoint.sh`                                    |
| App code         | **NOT in image** — cloned to `/data/apps/` at first run |

> **Architecture note:** `hermes-agent` and `hermes-webui` are git repos that
> live on the persistent `/data` volume (see REQUIREMENTS.md §3.2). The image
> contains only system deps, binaries (Qdrant, Tailscale), supervisord, and the
> entrypoint. This keeps the image stable and rarely needing a rebuild — app
> updates happen via `git checkout vX.Y.Z` inside the container, not `docker pull`.

---

## Implementation

### Step 1 — Investigate `hermes-webui` repo structure

Before writing the Dockerfile, the agent **must** determine whether
`hermes-webui` is a pip-installable package or a collection of files to be
copied directly.

```bash
# Check if there is a setup.py / pyproject.toml at the repo root
curl -s https://api.github.com/repos/fox-in-the-box-ai/hermes-webui/contents/ \
  | python3 -c "import sys,json; [print(f['name']) for f in json.load(sys.stdin)]"
```

> **⚠️ Note:** The git-in-volume model (§3.2 of REQUIREMENTS.md) means `hermes-webui` is
> **NOT** installed in the image. It is cloned to `/data/apps/hermes-webui/` at first run
> by `entrypoint.sh` and launched from there. The pip-installability check above is only
> relevant if you are considering an alternative "baked" install strategy — skip it for
> the current architecture.
>
> The pre-packaged investigation below is retained for reference in case the git-in-volume
> model is ever revisited for a specific component.

---

### Step 2 — Determine Qdrant binary architecture

The base image is `python:3.11-slim` which is typically `linux/amd64`. On ARM
hosts (Apple Silicon, Graviton) a multi-arch build or explicit `--platform`
flag is needed. The agent must select the correct Qdrant release asset:

```bash
# amd64
QDRANT_URL=https://github.com/qdrant/qdrant/releases/latest/download/qdrant-x86_64-unknown-linux-musl.tar.gz

# arm64
QDRANT_URL=https://github.com/qdrant/qdrant/releases/latest/download/qdrant-aarch64-unknown-linux-musl.tar.gz
```

In the Dockerfile use `ARG TARGETARCH` (set automatically by `docker buildx`)
and select the URL accordingly. See the Dockerfile below.

---

### Step 3 — Write `packages/integration/Dockerfile`

```dockerfile
# syntax=docker/dockerfile:1
FROM python:3.11-slim

# ── build args ────────────────────────────────────────────────────────────────
ARG TARGETARCH
# Pin QDRANT_VERSION to match the qdrant-client version in hermes-agent/requirements.txt.
# Check the client version first: grep qdrant-client packages/integration/../hermes-agent/requirements.txt
# Then find the matching server release: https://github.com/qdrant/qdrant/releases
# Do NOT use "latest" in production builds — a server/client mismatch can silently corrupt data.
ARG QDRANT_VERSION=v1.9.4
# FITB_VERSION is baked into the image so entrypoint.sh knows which git tag to
# clone on first run. Override at build time: --build-arg FITB_VERSION=v0.1.0
ARG FITB_VERSION=v0.1.0

# ── system dependencies ───────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
        gnupg \
        git \
        lsb-release \
        iproute2 \
        iptables \
    && rm -rf /var/lib/apt/lists/*

# ── Tailscale ─────────────────────────────────────────────────────────────────
RUN curl -fsSL https://pkgs.tailscale.com/stable/debian/$(lsb_release -cs).noarmor.gpg \
        | tee /usr/share/keyrings/tailscale-archive-keyring.gpg >/dev/null \
    && curl -fsSL https://pkgs.tailscale.com/stable/debian/$(lsb_release -cs).tailscale-keyring.list \
        | tee /etc/apt/sources.list.d/tailscale.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends tailscale \
    && rm -rf /var/lib/apt/lists/*

# ── Python packages (runtime infrastructure only — NO app code) ───────────────
RUN pip install --no-cache-dir supervisor

# ── Qdrant binary ─────────────────────────────────────────────────────────────
RUN set -eux; \
    mkdir -p /app/qdrant; \
    case "${TARGETARCH}" in \
        arm64) ARCH="aarch64" ;; \
        *)     ARCH="x86_64"  ;; \
    esac; \
    if [ "${QDRANT_VERSION}" = "latest" ]; then \
        QDRANT_VERSION=$(curl -fsSL -o /dev/null -w '%{url_effective}' \
            https://github.com/qdrant/qdrant/releases/latest \
            | sed 's|.*/tag/||'); \
    fi; \
    curl -fsSL \
        "https://github.com/qdrant/qdrant/releases/download/${QDRANT_VERSION}/qdrant-${ARCH}-unknown-linux-musl.tar.gz" \
        | tar -xzf - -C /app/qdrant; \
    chmod +x /app/qdrant/qdrant

# ── non-root user ─────────────────────────────────────────────────────────────
RUN useradd -r -s /bin/bash -d /app foxinthebox \
    && mkdir -p /data \
    && chown -R foxinthebox:foxinthebox /app /data

# ── bake version into image so entrypoint knows which git tag to clone ────────
RUN echo "${FITB_VERSION}" > /app/version.txt

# ── supervisord config ────────────────────────────────────────────────────────
COPY packages/integration/supervisord.conf /etc/supervisor/supervisord.conf

# ── default configs and migration scripts ────────────────────────────────────
COPY packages/integration/default-configs/ /app/defaults/
COPY packages/integration/scripts/ /app/scripts/
RUN chmod +x /app/scripts/*.sh

# ── entrypoint ────────────────────────────────────────────────────────────────
COPY packages/integration/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# ── runtime ───────────────────────────────────────────────────────────────────
VOLUME ["/data"]
EXPOSE 8787 6333

ENTRYPOINT ["/app/entrypoint.sh"]
```

> **Why no `pip install hermes-agent` or `git clone hermes-webui` here?**
> App code is managed as git repos on the `/data` volume (see REQUIREMENTS.md
> §3.2). The entrypoint clones them on first run and updates them via
> `git checkout` — no image rebuild required for app updates. The image only
> needs rebuilding when system deps (Qdrant version, Tailscale, OS packages) change.

---

### Step 4 — Write `packages/integration/supervisord.conf`

```ini
[supervisord]
nodaemon=true
user=root
logfile=/data/logs/supervisord.log
logfile_maxbytes=10MB
logfile_backups=3
pidfile=/data/run/supervisord.pid
childlogdir=/data/logs

[unix_http_server]
file=/data/run/supervisor.sock
chmod=0770
chown=foxinthebox:foxinthebox

[supervisorctl]
serverurl=unix:///data/run/supervisor.sock

[rpcinterface:supervisor]
supervisor.rpcinterface_factory = supervisor.rpcinterface:make_main_rpcinterface

; ── tailscaled (must run as root for NET_ADMIN) ───────────────────────────────
[program:tailscaled]
command=tailscaled --state=/data/data/tailscale/tailscaled.state
user=root
autostart=true
autorestart=true
stdout_logfile=/data/logs/tailscaled.log
stderr_logfile=/data/logs/tailscaled.err
priority=10

; ── qdrant ────────────────────────────────────────────────────────────────────
[program:qdrant]
command=/app/qdrant/qdrant --storage-path /data/data/mem0
user=foxinthebox
autostart=true
autorestart=true
stdout_logfile=/data/logs/qdrant.log
stderr_logfile=/data/logs/qdrant.err
priority=20

; ── hermes gateway ────────────────────────────────────────────────────────────
[program:hermes-gateway]
command=python -m hermes_cli.main gateway run --replace
user=foxinthebox
autostart=true
autorestart=true
stdout_logfile=/data/logs/hermes-gateway.log
stderr_logfile=/data/logs/hermes-gateway.err
environment=HOME="/app",PYTHONPATH="/data/apps/hermes-agent",PATH="/usr/local/bin:/usr/bin:/bin"
priority=30

; ── hermes webui ──────────────────────────────────────────────────────────────
; server.py path confirmed against hermes-webui repo at clone time by entrypoint
[program:hermes-webui]
command=python /data/apps/hermes-webui/server.py
user=foxinthebox
autostart=true
autorestart=true
stdout_logfile=/data/logs/hermes-webui.log
stderr_logfile=/data/logs/hermes-webui.err
environment=HOME="/app",PYTHONPATH="/data/apps/hermes-webui",PATH="/usr/local/bin:/usr/bin:/bin"
priority=40
```

---

### Step 5 — Write `packages/integration/entrypoint.sh` (stub — full version in Task 04)

A minimal entrypoint is needed to create required directories before
`supervisord` starts. Task 04 will replace this with the full onboarding-aware
version.

```bash
#!/usr/bin/env bash
set -euo pipefail

# Create required data-volume directories
mkdir -p \
    /data/data/mem0 \
    /data/data/tailscale \
    /data/logs \
    /data/run

chown -R foxinthebox:foxinthebox /data/data /data/logs
# /data/run kept as root so supervisord can write its pidfile

exec /usr/local/bin/supervisord -c /etc/supervisor/supervisord.conf
```

---

## Acceptance Criteria

All criteria must pass before this task is considered complete.

| # | Criterion                                        | How to verify (see §Test Commands)           |
|---|--------------------------------------------------|----------------------------------------------|
| 1 | `docker build` exits 0                           | `AC1` build command                          |
| 2 | All 4 supervisor programs show `RUNNING` ≤ 30 s  | `AC2` status poll                            |
| 3 | `curl http://localhost:8787` → HTTP 200          | `AC3` curl webui                             |
| 4 | `curl http://localhost:6333/healthz` → `{"title":"qdrant - 200"}` | `AC4` curl qdrant         |
| 5 | No `ERROR` lines in startup logs                 | `AC5` log grep                               |
| 6 | `/data` subdirectory structure created           | `AC6` directory check                        |

---

## Test Commands

Run these in order. Each command is labelled with its acceptance criterion.

```bash
# ── AC1: build ─────────────────────────────────────────────────────────────────
docker build \
  --platform linux/amd64 \
  -t ghcr.io/fox-in-the-box-ai/cloud:dev \
  -f packages/integration/Dockerfile .

# ── start container for remaining checks ──────────────────────────────────────
docker run -d --name fitb-test \
  --cap-add=NET_ADMIN \
  --sysctl net.ipv4.ip_forward=1 \
  -v ~/.foxinthebox:/data \        # Linux default; adjust path for macOS/Windows (see REQUIREMENTS §4.2)
  -p 127.0.0.1:8787:8787 \
  -p 127.0.0.1:6333:6333 \
  ghcr.io/fox-in-the-box-ai/cloud:dev

# ── AC2: all 4 programs RUNNING within 30 s ───────────────────────────────────
for i in $(seq 1 6); do
  sleep 5
  STATUS=$(docker exec fitb-test supervisorctl -c /etc/supervisor/supervisord.conf status 2>/dev/null)
  echo "$STATUS"
  RUNNING=$(echo "$STATUS" | grep -c "RUNNING" || true)
  [ "$RUNNING" -ge 4 ] && echo "✅ All 4 programs RUNNING" && break
  echo "... waiting ($((i*5))s elapsed)"
done

# ── AC3: webui returns HTTP 200 ───────────────────────────────────────────────
curl -sf -o /dev/null -w "%{http_code}\n" http://localhost:8787
# expected: 200

# ── AC4: qdrant healthz ───────────────────────────────────────────────────────
curl -sf http://localhost:6333/healthz
# expected: {"title":"qdrant - 200"}  (or similar OK response)

# ── AC5: no ERROR lines in startup logs ───────────────────────────────────────
docker logs fitb-test 2>&1 | grep -i "^ERROR\|^\[ERROR\]" && echo "❌ Errors found" || echo "✅ No startup errors"

# ── AC6: /data directory structure ───────────────────────────────────────────
docker exec fitb-test find /data -maxdepth 3 -type d | sort
# expected to contain: /data/data/mem0  /data/data/tailscale  /data/logs  /data/run

# ── cleanup ───────────────────────────────────────────────────────────────────
docker rm -f fitb-test
```

---

## Known Pitfalls

### 1 — `hermes-webui` may not be a pip package

Check the repo contents **before** finalising the Dockerfile. If
`pyproject.toml` / `setup.py` is absent, the `pip install git+...` line will
silently install nothing useful.
> **However:** under the git-in-volume model the Dockerfile does NOT install hermes-webui
> at all — `entrypoint.sh` clones it to `/data/apps/hermes-webui/` on first run. If you
> ever switch to a baked approach, use `git clone` and confirm the entry point filename
> (`server.py`, `app.py`, `main.py`, etc.). Update both Dockerfile and `supervisord.conf`.

### 2 — Qdrant binary architecture mismatch

`python:3.11-slim` defaults to `linux/amd64`. If you are building on an ARM
host without `--platform linux/amd64`, the downloaded `x86_64` Qdrant binary
will segfault at runtime. Always pass `--platform linux/amd64` to `docker
build` (or use `docker buildx`) and verify with:

```bash
docker exec fitb-test /app/qdrant/qdrant --version
```

### 3 — `tailscaled` requires `NET_ADMIN`

The `docker run` command must include `--cap-add=NET_ADMIN` and
`--sysctl net.ipv4.ip_forward=1`. Without these, `tailscaled` will crash on
startup, causing supervisord to restart it in a tight loop. This will appear in
logs as repeated `INFO exited: tailscaled` lines.

### 6 — `/health` endpoint required for CI smoke test

Task 08 (`build-container.yml`) polls `GET /health` to determine when the
container is ready. This endpoint does not exist yet in the upstream Hermes
WebUI.

**Options (pick one when implementing):**

1. **Add a `/health` route to the Hermes WebUI fork** — returns `{"status":"ok"}`
   once the server is listening. This is the cleanest solution.

2. **Add a minimal Python health server in entrypoint.sh** — a one-liner
   `python3 -m http.server 8787` is not viable (port conflict), but a tiny
   Flask or http.server on a separate port with an nginx-style passthrough
   would work. Not recommended — extra complexity.

3. **Patch supervisord.conf** to write a sentinel file when all programs are
   `RUNNING`, and have entrypoint.sh start a one-shot HTTP responder that
   serves 200 until the sentinel is detected — then hand off to WebUI.

**Recommendation: Option 1.** Add to the WebUI fork task (Task 01 / WebUI
fork scope). Document the expected route in the Hermes WebUI fork README.

> This is a **Task 03/04 blocker for CI** — CI will never go green without it.

Qdrant's on-disk storage format can change between major versions. If the image
is rebuilt with a newer `QDRANT_VERSION` but `/data/data/mem0/qdrant` already
contains data from an older version, Qdrant may refuse to start or corrupt data.

**Rule:** Always pin `QDRANT_VERSION` in the Dockerfile to the version that
matches `qdrant-client` in `hermes-agent/requirements.txt`. Check the
[qdrant-client compatibility matrix](https://github.com/qdrant/qdrant-client#compatibility)
before bumping either side.

When bumping Qdrant across a data-format boundary, add a migration step to
`packages/integration/scripts/migrate.sh` that runs `qdrant` with the
`--snapshot` flag to export/reimport data, or documents the manual steps
clearly.

For v0.1: `QDRANT_VERSION=v1.9.4`. Do not change without checking hermes-agent
`requirements.txt` first.

### 4 — `/data` volume ownership

Supervisord runs as root but launches child processes as `foxinthebox`. The
exec-ing supervisord, otherwise Qdrant and the webui will fail to write their
files.

---

## File Checklist

After completing this task the following files must exist in the repo:

```
packages/integration/
├── Dockerfile
├── supervisord.conf
└── entrypoint.sh          ← minimal stub (full version written in Task 04)
```

---

## Dependencies / Next Steps

| Task | Depends on this task because…                                   |
|------|-----------------------------------------------------------------|
| 04   | Entrypoint script replaces the stub created here                |
| 05   | Onboarding UI is served from the running container's port 8787  |
