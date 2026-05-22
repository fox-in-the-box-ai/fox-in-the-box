     1|# Task 03: Dockerfile and Container Build
     2|
     3|| Field        | Value                                      |
     4||--------------|--------------------------------------------|
     5|| **Status**   | Ready                                      |
     6|| **Executor** | AI agent                                   |
     7|| **Depends**  | Task 02 (repository scaffolding complete)  |
     8|| **Blocks**   | Task 04 (entrypoint.sh), Task 05 (onboarding UI) |
     9|| **Path**     | `packages/integration/Dockerfile`, `packages/integration/supervisord.conf` |
    10|
    11|---
    12|
    13|## Summary
    14|
    15|Write the `Dockerfile` and `supervisord.conf` for the single-container Fox in the Box image, then verify the image builds cleanly and all four supervised services reach `RUNNING` state within 30 seconds of container start.
    16|
    17|This is **critical path** — tasks 04 and 05 depend on a working container.
    18|
    19|---
    20|
    21|## Prerequisites
    22|
    23|- Task 02 is complete (repo scaffolded with `packages/integration/` directory in place).
    24|- Docker is installed and the daemon is running on the build host.
    25|- Outbound internet access is available (pip, apt, GitHub releases).
    26|
    27|---
    28|
    29|## Container Overview
    30|
    31|| Concern          | Choice                                                  |
    32||------------------|---------------------------------------------------------|
    33|| Base image       | `python:3.11-slim` (Debian-based)                       |
    34|| Process manager  | `supervisord` (via `pip install supervisor`)            |
    35|| Runtime user     | `foxinthebox` (non-root) — except `tailscaled` (needs root)  |
    36|| Exposed ports    | `8787` (webui), `6333` (Qdrant — internal only)         |
    37|| Persistent data  | `/data` volume                                          |
    38|| Entrypoint       | `/app/entrypoint.sh`                                    |
    39|| App code         | **NOT in image** — cloned to `/data/apps/` at first run |
    40|
    41|> **Architecture note:** `hermes-agent` and `hermes-webui` are git repos that
    42|> live on the persistent `/data` volume (see REQUIREMENTS.md §3.2). The image
    43|> contains only system deps, binaries (Qdrant, Tailscale), supervisord, and the
    44|> entrypoint. This keeps the image stable and rarely needing a rebuild — app
    45|> updates happen via `git checkout vX.Y.Z` inside the container, not `docker pull`.
    46|
    47|---
    48|
    49|## Implementation
    50|
    51|### Step 1 — Investigate `hermes-webui` repo structure
    52|
    53|Before writing the Dockerfile, the agent **must** determine whether
    54|`hermes-webui` is a pip-installable package or a collection of files to be
    55|copied directly.
    56|
    57|```bash
    58|# Check if there is a setup.py / pyproject.toml at the repo root
    59|curl -s https://api.github.com/repos/fox-in-the-box-ai/hermes-webui/contents/ \
    60|  | python3 -c "import sys,json; [print(f['name']) for f in json.load(sys.stdin)]"
    61|```
    62|
    63|> **⚠️ Note:** The git-in-volume model (§3.2 of REQUIREMENTS.md) means `hermes-webui` is
    64|> **NOT** installed in the image. It is cloned to `/data/apps/hermes-webui/` at first run
    65|> by `entrypoint.sh` and launched from there. The pip-installability check above is only
    66|> relevant if you are considering an alternative "baked" install strategy — skip it for
    67|> the current architecture.
    68|>
    69|> The pre-packaged investigation below is retained for reference in case the git-in-volume
    70|> model is ever revisited for a specific component.
    71|
    72|---
    73|
    74|### Step 2 — Determine Qdrant binary architecture
    75|
    76|The base image is `python:3.11-slim` which is typically `linux/amd64`. On ARM
    77|hosts (Apple Silicon, Graviton) a multi-arch build or explicit `--platform`
    78|flag is needed. The agent must select the correct Qdrant release asset:
    79|
    80|```bash
    81|# amd64
    82|QDRANT_URL=https://github.com/qdrant/qdrant/releases/latest/download/qdrant-x86_64-unknown-linux-musl.tar.gz
    83|
    84|# arm64
    85|QDRANT_URL=https://github.com/qdrant/qdrant/releases/latest/download/qdrant-aarch64-unknown-linux-musl.tar.gz
    86|```
    87|
    88|In the Dockerfile use `ARG TARGETARCH` (set automatically by `docker buildx`)
    89|and select the URL accordingly. See the Dockerfile below.
    90|
    91|---
    92|
    93|### Step 3 — Write `packages/integration/Dockerfile`
    94|
    95|```dockerfile
    96|# syntax=docker/dockerfile:1
    97|FROM python:3.11-slim
    98|
    99|# ── build args ────────────────────────────────────────────────────────────────
   100|ARG TARGETARCH
   101|# Pin QDRANT_VERSION to match the qdrant-client version in hermes-agent/requirements.txt.
   102|# Check the client version first: grep qdrant-client packages/integration/../hermes-agent/requirements.txt
   103|# Then find the matching server release: https://github.com/qdrant/qdrant/releases
   104|# Do NOT use "latest" in production builds — a server/client mismatch can silently corrupt data.
   105|ARG QDRANT_VERSION=v1.9.4
   106|# FITB_VERSION is baked into the image so entrypoint.sh knows which git tag to
   107|# clone on first run. Override at build time: --build-arg FITB_VERSION=v0.1.0
   108|ARG FITB_VERSION=v0.1.0
   109|
   110|# ── system dependencies ───────────────────────────────────────────────────────
   111|RUN apt-get update && apt-get install -y --no-install-recommends \
   112|        curl \
   113|        ca-certificates \
   114|        gnupg \
   115|        git \
   116|        lsb-release \
   117|        iproute2 \
   118|        iptables \
   119|    && rm -rf /var/lib/apt/lists/*
   120|
   121|# ── Tailscale ─────────────────────────────────────────────────────────────────
   122|RUN curl -fsSL https://pkgs.tailscale.com/stable/debian/$(lsb_release -cs).noarmor.gpg \
   123|        | tee /usr/share/keyrings/tailscale-archive-keyring.gpg >/dev/null \
   124|    && curl -fsSL https://pkgs.tailscale.com/stable/debian/$(lsb_release -cs).tailscale-keyring.list \
   125|        | tee /etc/apt/sources.list.d/tailscale.list \
   126|    && apt-get update \
   127|    && apt-get install -y --no-install-recommends tailscale \
   128|    && rm -rf /var/lib/apt/lists/*
   129|
   130|# ── Python packages (runtime infrastructure only — NO app code) ───────────────
   131|RUN pip install --no-cache-dir supervisor
   132|
   133|# ── Qdrant binary ─────────────────────────────────────────────────────────────
   134|RUN set -eux; \
   135|    mkdir -p /app/qdrant; \
   136|    case "${TARGETARCH}" in \
   137|        arm64) ARCH="aarch64" ;; \
   138|        *)     ARCH="x86_64"  ;; \
   139|    esac; \
   140|    if [ "${QDRANT_VERSION}" = "latest" ]; then \
   141|        QDRANT_VERSION=$(curl -fsSL -o /dev/null -w '%{url_effective}' \
   142|            https://github.com/qdrant/qdrant/releases/latest \
   143|            | sed 's|.*/tag/||'); \
   144|    fi; \
   145|    curl -fsSL \
   146|        "https://github.com/qdrant/qdrant/releases/download/${QDRANT_VERSION}/qdrant-${ARCH}-unknown-linux-musl.tar.gz" \
   147|        | tar -xzf - -C /app/qdrant; \
   148|    chmod +x /app/qdrant/qdrant
   149|
   150|# ── non-root user ─────────────────────────────────────────────────────────────
   151|RUN useradd -r -s /bin/bash -d /app foxinthebox \
   152|    && mkdir -p /data \
   153|    && chown -R foxinthebox:foxinthebox /app /data
   154|
   155|# ── bake version into image so entrypoint knows which git tag to clone ────────
   156|RUN echo "${FITB_VERSION}" > /app/version.txt
   157|
   158|# ── supervisord config ────────────────────────────────────────────────────────
   159|COPY packages/integration/supervisord.conf /etc/supervisor/supervisord.conf
   160|
   161|# ── default configs and migration scripts ────────────────────────────────────
   162|COPY packages/integration/default-configs/ /app/defaults/
   163|COPY packages/integration/scripts/ /app/scripts/
   164|RUN chmod +x /app/scripts/*.sh
   165|
   166|# ── entrypoint ────────────────────────────────────────────────────────────────
   167|COPY packages/integration/entrypoint.sh /app/entrypoint.sh
   168|RUN chmod +x /app/entrypoint.sh
   169|
   170|# ── runtime ───────────────────────────────────────────────────────────────────
   171|VOLUME ["/data"]
   172|EXPOSE 8787 6333
   173|
   174|ENTRYPOINT ["/app/entrypoint.sh"]
   175|```
   176|
   177|> **Why no `pip install hermes-agent` or `git clone hermes-webui` here?**
   178|> App code is managed as git repos on the `/data` volume (see REQUIREMENTS.md
   179|> §3.2). The entrypoint clones them on first run and updates them via
   180|> `git checkout` — no image rebuild required for app updates. The image only
   181|> needs rebuilding when system deps (Qdrant version, Tailscale, OS packages) change.
   182|
   183|---
   184|
   185|### Step 4 — Write `packages/integration/supervisord.conf`
   186|
   187|```ini
   188|[supervisord]
   189|nodaemon=true
   190|user=root
   191|logfile=/data/logs/supervisord.log
   192|logfile_maxbytes=10MB
   193|logfile_backups=3
   194|pidfile=/data/run/supervisord.pid
   195|childlogdir=/data/logs
   196|
   197|[unix_http_server]
   198|file=/data/run/supervisor.sock
   199|chmod=0770
   200|chown=foxinthebox:foxinthebox
   201|
   202|[supervisorctl]
   203|serverurl=unix:///data/run/supervisor.sock
   204|
   205|[rpcinterface:supervisor]
   206|supervisor.rpcinterface_factory = supervisor.rpcinterface:make_main_rpcinterface
   207|
   208|; ── tailscaled (must run as root for NET_ADMIN) ───────────────────────────────
   209|[program:tailscaled]
   210|command=tailscaled --state=/data/data/tailscale/tailscaled.state
   211|user=root
   212|autostart=true
   213|autorestart=true
   214|stdout_logfile=/data/logs/tailscaled.log
   215|stderr_logfile=/data/logs/tailscaled.err
   216|priority=10
   217|
   218|; ── qdrant ────────────────────────────────────────────────────────────────────
   219|[program:qdrant]
   220|command=/app/qdrant/qdrant --storage-path /data/data/mem0
   221|user=foxinthebox
   222|autostart=true
   223|autorestart=true
   224|stdout_logfile=/data/logs/qdrant.log
   225|stderr_logfile=/data/logs/qdrant.err
   226|priority=20
   227|
   228|; ── hermes gateway ────────────────────────────────────────────────────────────
   229|[program:hermes-gateway]
   230|command=python -m hermes_cli.main gateway run --replace
   231|user=foxinthebox
   232|autostart=true
   233|autorestart=true
   234|stdout_logfile=/data/logs/hermes-gateway.log
   235|stderr_logfile=/data/logs/hermes-gateway.err
   236|environment=HOME="/app",PYTHONPATH="/data/apps/hermes-agent",PATH="/usr/local/bin:/usr/bin:/bin"
   237|priority=30
   238|
   239|; ── hermes webui ──────────────────────────────────────────────────────────────
   240|; server.py path confirmed against hermes-webui repo at clone time by entrypoint
   241|[program:hermes-webui]
   242|command=python /data/apps/hermes-webui/server.py
   243|user=foxinthebox
   244|autostart=true
   245|autorestart=true
   246|stdout_logfile=/data/logs/hermes-webui.log
   247|stderr_logfile=/data/logs/hermes-webui.err
   248|environment=HOME="/app",PYTHONPATH="/data/apps/hermes-webui",PATH="/usr/local/bin:/usr/bin:/bin"
   249|priority=40
   250|```
   251|
   252|---
   253|
   254|### Step 5 — Write `packages/integration/entrypoint.sh` (stub — full version in Task 04)
   255|
   256|A minimal entrypoint is needed to create required directories before
   257|`supervisord` starts. Task 04 will replace this with the full onboarding-aware
   258|version.
   259|
   260|```bash
   261|#!/usr/bin/env bash
   262|set -euo pipefail
   263|
   264|# Create required data-volume directories
   265|mkdir -p \
   266|    /data/data/mem0 \
   267|    /data/data/tailscale \
   268|    /data/logs \
   269|    /data/run
   270|
   271|chown -R foxinthebox:foxinthebox /data/data /data/logs
   272|# /data/run kept as root so supervisord can write its pidfile
   273|
   274|exec /usr/local/bin/supervisord -c /etc/supervisor/supervisord.conf
   275|```
   276|
   277|---
   278|
   279|## Acceptance Criteria
   280|
   281|All criteria must pass before this task is considered complete.
   282|
   283|| # | Criterion                                        | How to verify (see §Test Commands)           |
   284||---|--------------------------------------------------|----------------------------------------------|
   285|| 1 | `docker build` exits 0                           | `AC1` build command                          |
   286|| 2 | All 4 supervisor programs show `RUNNING` ≤ 30 s  | `AC2` status poll                            |
   287|| 3 | `curl http://localhost:8787` → HTTP 200          | `AC3` curl webui                             |
   288|| 4 | `curl http://localhost:6333/healthz` → `{"title":"qdrant - 200"}` | `AC4` curl qdrant         |
   289|| 5 | No `ERROR` lines in startup logs                 | `AC5` log grep                               |
   290|| 6 | `/data` subdirectory structure created           | `AC6` directory check                        |
   291|
   292|---
   293|
   294|## Test Commands
   295|
   296|Run these in order. Each command is labelled with its acceptance criterion.
   297|
   298|```bash
   299|# ── AC1: build ─────────────────────────────────────────────────────────────────
   300|docker build \
   301|  --platform linux/amd64 \
   302|  -t ghcr.io/fox-in-the-box-ai/cloud:dev \
   303|  -f packages/integration/Dockerfile .
   304|
   305|# ── start container for remaining checks ──────────────────────────────────────
   306|docker run -d --name fitb-test \
   307|  --cap-add=NET_ADMIN \
     --device /dev/net/tun \
   308|  --sysctl net.ipv4.ip_forward=1 \
   309|  -v ~/.foxinthebox:/data \        # Linux default; adjust path for macOS/Windows (see REQUIREMENTS §4.2)
   310|  -p 127.0.0.1:8787:8787 \
   311|  -p 127.0.0.1:6333:6333 \
   312|  ghcr.io/fox-in-the-box-ai/cloud:dev
   313|
   314|# ── AC2: all 4 programs RUNNING within 30 s ───────────────────────────────────
   315|for i in $(seq 1 6); do
   316|  sleep 5
   317|  STATUS=$(docker exec fitb-test supervisorctl -c /etc/supervisor/supervisord.conf status 2>/dev/null)
   318|  echo "$STATUS"
   319|  RUNNING=$(echo "$STATUS" | grep -c "RUNNING" || true)
   320|  [ "$RUNNING" -ge 4 ] && echo "✅ All 4 programs RUNNING" && break
   321|  echo "... waiting ($((i*5))s elapsed)"
   322|done
   323|
   324|# ── AC3: webui returns HTTP 200 ───────────────────────────────────────────────
   325|curl -sf -o /dev/null -w "%{http_code}\n" http://localhost:8787
   326|# expected: 200
   327|
   328|# ── AC4: qdrant healthz ───────────────────────────────────────────────────────
   329|curl -sf http://localhost:6333/healthz
   330|# expected: {"title":"qdrant - 200"}  (or similar OK response)
   331|
   332|# ── AC5: no ERROR lines in startup logs ───────────────────────────────────────
   333|docker logs fitb-test 2>&1 | grep -i "^ERROR\|^\[ERROR\]" && echo "❌ Errors found" || echo "✅ No startup errors"
   334|
   335|# ── AC6: /data directory structure ───────────────────────────────────────────
   336|docker exec fitb-test find /data -maxdepth 3 -type d | sort
   337|# expected to contain: /data/data/mem0  /data/data/tailscale  /data/logs  /data/run
   338|
   339|# ── cleanup ───────────────────────────────────────────────────────────────────
   340|docker rm -f fitb-test
   341|```
   342|
   343|---
   344|
   345|## Known Pitfalls
   346|
   347|### 1 — `hermes-webui` may not be a pip package
   348|
   349|Check the repo contents **before** finalising the Dockerfile. If
   350|`pyproject.toml` / `setup.py` is absent, the `pip install git+...` line will
   351|silently install nothing useful.
   352|> **However:** under the git-in-volume model the Dockerfile does NOT install hermes-webui
   353|> at all — `entrypoint.sh` clones it to `/data/apps/hermes-webui/` on first run. If you
   354|> ever switch to a baked approach, use `git clone` and confirm the entry point filename
   355|> (`server.py`, `app.py`, `main.py`, etc.). Update both Dockerfile and `supervisord.conf`.
   356|
   357|### 2 — Qdrant binary architecture mismatch
   358|
   359|`python:3.11-slim` defaults to `linux/amd64`. If you are building on an ARM
   360|host without `--platform linux/amd64`, the downloaded `x86_64` Qdrant binary
   361|will segfault at runtime. Always pass `--platform linux/amd64` to `docker
   362|build` (or use `docker buildx`) and verify with:
   363|
   364|```bash
   365|docker exec fitb-test /app/qdrant/qdrant --version
   366|```
   367|
   368|### 3 — `tailscaled` requires `NET_ADMIN`
   369|
   370|The `docker run` command must include `--cap-add=NET_ADMIN` and
   371|`--sysctl net.ipv4.ip_forward=1`. Without these, `tailscaled` will crash on
   372|startup, causing supervisord to restart it in a tight loop. This will appear in
   373|logs as repeated `INFO exited: tailscaled` lines.
   374|
   375|### 6 — `/health` endpoint required for CI smoke test
   376|
   377|Task 08 (`build-container.yml`) polls `GET /health` to determine when the
   378|container is ready. This endpoint does not exist yet in the upstream Hermes
   379|WebUI.
   380|
   381|**Options (pick one when implementing):**
   382|
   383|1. **Add a `/health` route to the Hermes WebUI fork** — returns `{"status":"ok"}`
   384|   once the server is listening. This is the cleanest solution.
   385|
   386|2. **Add a minimal Python health server in entrypoint.sh** — a one-liner
   387|   `python3 -m http.server 8787` is not viable (port conflict), but a tiny
   388|   Flask or http.server on a separate port with an nginx-style passthrough
   389|   would work. Not recommended — extra complexity.
   390|
   391|3. **Patch supervisord.conf** to write a sentinel file when all programs are
   392|   `RUNNING`, and have entrypoint.sh start a one-shot HTTP responder that
   393|   serves 200 until the sentinel is detected — then hand off to WebUI.
   394|
   395|**Recommendation: Option 1.** Add to the WebUI fork task (Task 01 / WebUI
   396|fork scope). Document the expected route in the Hermes WebUI fork README.
   397|
   398|> This is a **Task 03/04 blocker for CI** — CI will never go green without it.
   399|
   400|Qdrant's on-disk storage format can change between major versions. If the image
   401|is rebuilt with a newer `QDRANT_VERSION` but `/data/data/mem0/qdrant` already
   402|contains data from an older version, Qdrant may refuse to start or corrupt data.
   403|
   404|**Rule:** Always pin `QDRANT_VERSION` in the Dockerfile to the version that
   405|matches `qdrant-client` in `hermes-agent/requirements.txt`. Check the
   406|[qdrant-client compatibility matrix](https://github.com/qdrant/qdrant-client#compatibility)
   407|before bumping either side.
   408|
   409|When bumping Qdrant across a data-format boundary, add a migration step to
   410|`packages/integration/scripts/migrate.sh` that runs `qdrant` with the
   411|`--snapshot` flag to export/reimport data, or documents the manual steps
   412|clearly.
   413|
   414|For v0.1: `QDRANT_VERSION=v1.9.4`. Do not change without checking hermes-agent
   415|`requirements.txt` first.
   416|
   417|### 4 — `/data` volume ownership
   418|
   419|Supervisord runs as root but launches child processes as `foxinthebox`. The
   420|exec-ing supervisord, otherwise Qdrant and the webui will fail to write their
   421|files.
   422|
   423|---
   424|
   425|## File Checklist
   426|
   427|After completing this task the following files must exist in the repo:
   428|
   429|```
   430|packages/integration/
   431|├── Dockerfile
   432|├── supervisord.conf
   433|└── entrypoint.sh          ← minimal stub (full version written in Task 04)
   434|```
   435|
   436|---
   437|
   438|## Dependencies / Next Steps
   439|
   440|| Task | Depends on this task because…                                   |
   441||------|-----------------------------------------------------------------|
   442|| 04   | Entrypoint script replaces the stub created here                |
   443|| 05   | Onboarding UI is served from the running container's port 8787  |
   444|