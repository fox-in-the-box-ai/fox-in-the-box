     1|# Task 04: Container Entrypoint Script
     2|
     3|| Field        | Value                                                       |
     4||--------------|-------------------------------------------------------------|
     5|| **Status**   | Ready                                                       |
     6|| **Executor** | AI agent                                                    |
     7|| **Depends**  | Task 03 (container builds and supervisord is verified)      |
     8|| **Blocks**   | Task 05 (onboarding wizard needs correct first-run state)   |
     9|| **Parallel** | Can run in parallel with Task 05 (onboarding wizard)        |
    10|| **Paths**    | `packages/integration/entrypoint.sh`, `packages/integration/default-configs/`, `packages/integration/scripts/migrate.sh` |
    11|
    12|---
    13|
    14|## Summary
    15|
    16|Replace the minimal entrypoint stub created in Task 03 with a full production-grade entrypoint script. The script handles first-run directory scaffolding, default config seeding, version-based migration, permission fixing, environment loading, and finally hands off to `supervisord`.
    17|
    18|Also create the default config templates that the entrypoint seeds into `/data/config/` on first run, and a migration helper script.
    19|
    20|---
    21|
    22|## Prerequisites
    23|
    24|- Task 03 is complete: the image builds successfully and all four supervised services reach `RUNNING` state.
    25|- The repo contains `packages/integration/` (created in Task 02 scaffolding).
    26|- Docker daemon is running on the build host.
    27|
    28|---
    29|
    30|## Implementation
    31|
    32|### Step 1 — Write `packages/integration/entrypoint.sh`
    33|
    34|This script is the container `ENTRYPOINT`. It runs as root (supervisord needs root to later drop privileges per-process).
    35|
    36|```bash
    37|#!/usr/bin/env bash
    38|# /app/entrypoint.sh — Fox in the Box container entrypoint
    39|set -euo pipefail
    40|
    41|# ── Constants ─────────────────────────────────────────────────────────────────
    42|ONBOARDING_FLAG="/data/config/onboarding.json"
    43|DEFAULTS_DIR="/app/defaults"
    44|DATA_VERSION_FILE="/data/version.txt"
    45|APP_VERSION_FILE="/app/version.txt"
    46|APPS_DIR="/data/apps"
    47|FITB_VERSION=$(cat "$APP_VERSION_FILE" 2>/dev/null || echo "v0.1.0")
    48|
    49|# ── 1. First-run detection ─────────────────────────────────────────────────────
    50|if [ ! -f "$ONBOARDING_FLAG" ]; then
    51|    echo "[entrypoint] First run detected — bootstrapping /data ..."
    52|
    53|    # Create full directory structure
    54|    mkdir -p \
    55|        /data/apps \
    56|        /data/config \
    57|        /data/data/hermes \
    58|        /data/data/mem0 \
    59|        /data/data/tailscale \
    60|        /data/cache \
    61|        /data/logs \
    62|        /data/run
    63|
    64|    # Seed default configs (only if the source directory exists)
    65|    if [ -d "$DEFAULTS_DIR" ]; then
    66|        cp -n "$DEFAULTS_DIR"/* /data/config/ 2>/dev/null || true
    67|    fi
    68|
    69|    # Write initial onboarding marker
    70|    echo '{"completed": false}' > "$ONBOARDING_FLAG"
    71|
    72|    echo "[entrypoint] Bootstrap complete."
    73|else
    74|    echo "[entrypoint] Existing /data detected — skipping first-run bootstrap."
    75|
    76|    # Ensure any directories added in later versions are present
    77|    mkdir -p \
    78|        /data/apps \
    79|        /data/config \
    80|        /data/data/hermes \
    81|        /data/data/mem0 \
    82|        /data/data/tailscale \
    83|        /data/cache \
    84|        /data/logs \
    85|        /data/run
    86|fi
    87|
    88|# ── 2. App code bootstrap (git-in-volume model) ────────────────────────────────
    89|# hermes-agent and hermes-webui live as git repos on the /data volume.
    90|# Clone on first run, skip if already present. Updates happen separately.
    91|_clone_app() {
    92|    local APP="$1"
    93|    local DEST="$APPS_DIR/$APP"
    94|
    95|    if [ -d "$DEST/.git" ]; then
    96|        echo "[entrypoint] $APP already present at $DEST — skipping clone."
    97|        return 0
    98|    fi
    99|
   100|    echo "[entrypoint] Cloning $APP @ $FITB_VERSION ..."
   101|    # Remove any partial clone before retrying
   102|    rm -rf "$DEST"
   103|    if ! git clone --depth 1 \
   104|            --branch "$FITB_VERSION" \
   105|            "https://github.com/fox-in-the-box-ai/$APP" \
   106|            "$DEST"; then
   107|        echo "[entrypoint] ERROR: Failed to clone $APP. Check network and try again."
   108|        echo "[entrypoint] If offline, manually place a git repo at $DEST and restart."
   109|        exit 1
   110|    fi
   111|
   112|    echo "[entrypoint] Installing $APP ..."
   113|    pip install -e "$DEST" --quiet --no-cache-dir
   114|    echo "[entrypoint] $APP ready."
   115|}
   116|
   117|_clone_app hermes-agent
   118|_clone_app hermes-webui
   119|
   120|# ── 3. Version migration ───────────────────────────────────────────────────────
   121|CURRENT_VERSION="0.0.0"
   122|if [ -f "$DATA_VERSION_FILE" ]; then
   123|    CURRENT_VERSION=$(cat "$DATA_VERSION_FILE")
   124|fi
   125|
   126|LATEST_VERSION=$(cat "$APP_VERSION_FILE" 2>/dev/null || echo "0.0.0")
   127|
   128|if [ "$CURRENT_VERSION" != "$LATEST_VERSION" ]; then
   129|    echo "[entrypoint] Version change detected: $CURRENT_VERSION -> $LATEST_VERSION"
   130|    if [ -x "/app/scripts/migrate.sh" ]; then
   131|        /app/scripts/migrate.sh "$CURRENT_VERSION" "$LATEST_VERSION"
   132|    else
   133|        echo "[entrypoint] WARNING: /app/scripts/migrate.sh not found — skipping migration."
   134|    fi
   135|    echo "$LATEST_VERSION" > "$DATA_VERSION_FILE"
   136|    echo "[entrypoint] Version file updated to $LATEST_VERSION."
   137|else
   138|    echo "[entrypoint] Version unchanged ($CURRENT_VERSION) — no migration needed."
   139|fi
   140|
   141|# ── 4. Fix permissions ─────────────────────────────────────────────────────────
   142|# Exclude /data/data/tailscale — tailscaled runs as root and manages its own state.
   143|echo "[entrypoint] Setting ownership on /data ..."
   144|chown -R foxinthebox:foxinthebox \
   145|    /data/apps \
   146|    /data/config \
   147|    /data/data/hermes \
   148|    /data/data/mem0 \
   149|    /data/cache \
   150|    /data/logs
   151|# /data/run is kept root-owned so supervisord can write its pidfile.
   152|# /data/data/tailscale is kept root-owned so tailscaled can write state.
   153|chown root:root /data/run /data/data/tailscale
   154|
   155|# ── 5. Load environment ────────────────────────────────────────────────────────
   156|HERMES_ENV="/data/config/hermes.env"
   157|if [ -f "$HERMES_ENV" ]; then
   158|    echo "[entrypoint] Loading environment from $HERMES_ENV ..."
   159|    set -a
   160|    # shellcheck source=/dev/null
   161|    source "$HERMES_ENV"
   162|    set +a
   163|fi
   164|
   165|# ── 6. Hand off to supervisord ─────────────────────────────────────────────────
   166|echo "[entrypoint] Starting supervisord ..."
   167|exec /usr/local/bin/supervisord -c /etc/supervisor/supervisord.conf
   168|```
   169|
   170|> **Important:** The Dockerfile must copy this file as `/app/entrypoint.sh` and mark it executable (`chmod +x`). It must also copy `packages/integration/default-configs/` to `/app/defaults/` and `packages/integration/scripts/` to `/app/scripts/`. These directives are already included in the Task 03 Dockerfile template — verify they exist in `packages/integration/Dockerfile`.
   171|
   172|---
   173|
   174|### Step 2 — Write `packages/integration/default-configs/hermes.yaml`
   175|
   176|Minimal Hermes configuration pointing all storage to `/data/data/hermes`.
   177|
   178|```yaml
   179|# hermes.yaml — default Hermes agent configuration
   180|# Copied to /data/config/hermes.yaml on first container run.
   181|# Edit this file to customise Hermes behaviour.
   182|
   183|storage:
   184|  type: local
   185|  path: /data/data/hermes
   186|
   187|server:
   188|  host: 0.0.0.0
   189|  port: 8787
   190|
   191|logging:
   192|  level: info
   193|  file: /data/logs/hermes.log
   194|```
   195|
   196|---
   197|
   198|### Step 3 — Write `packages/integration/default-configs/hermes.env.template`
   199|
   200|A commented-out template. Users copy/rename this to `hermes.env` and fill in their keys. The entrypoint loads `hermes.env` (not the template) if it exists.
   201|
   202|```bash
   203|# hermes.env — Fox in the Box environment overrides
   204|# ──────────────────────────────────────────────────
   205|# Instructions:
   206|#   1. Copy this file to /data/config/hermes.env
   207|#      (or rename it if you are editing from inside the container)
   208|#   2. Uncomment and fill in the values you need.
   209|#   3. Restart the container — entrypoint.sh will source this file
   210|#      before starting supervisord, making the variables available to
   211|#      all supervised child processes.
   212|#
   213|# Variables set here override anything baked into the image.
   214|
   215|# ── LLM API Keys ──────────────────────────────────────────────────────────────
   216|#OPENROUTER_API_KEY=***
   217|
   218|# ── Tailscale ─────────────────────────────────────────────────────────────────
   219|# Provide an auth key to join your tailnet automatically on first start.
   220|# Generate one at https://login.tailscale.com/admin/settings/keys
   221|#TAILSCALE_AUTHKEY=***
   222|
   223|# ── Hermes / Memos extra config ───────────────────────────────────────────────
   224|# Uncomment to override defaults.
   225|#MEMOS_PORT=5230
   226|#HERMES_LOG_LEVEL=debug
   227|```
   228|
   229|---
   230|
   231|### Step 4 — Write `packages/integration/default-configs/onboarding.json`
   232|
   233|The onboarding completion marker. This default is copied to `/data/config/onboarding.json` on first run, signalling that onboarding has not yet been completed.
   234|
   235|```json
   236|{"completed": false}
   237|```
   238|
   239|---
   240|
   241|### Step 5 — Write `packages/integration/app-root/version.txt`
   242|
   243|The application version baked into the image. Placed at `/app/version.txt` inside the container.
   244|
   245|```
   246|0.1.0
   247|```
   248|
   249|> **Note:** This file is copied to `/app/version.txt` in the Dockerfile. The `/data/version.txt` file is written by the entrypoint at runtime and tracks which version of the app last ran against this data volume.
   250|
   251|---
   252|
   253|### Step 6 — Write `packages/integration/scripts/migrate.sh`
   254|
   255|A no-op migration script. Future tasks will add version-specific migration logic between the two `case` blocks.
   256|
   257|```bash
   258|#!/usr/bin/env bash
   259|# /app/scripts/migrate.sh — data volume migration helper
   260|# Called by entrypoint.sh when /data/version.txt differs from /app/version.txt
   261|# Arguments:
   262|#   $1  — current version (from /data/version.txt, e.g. "0.0.0")
   263|#   $2  — latest version  (from /app/version.txt,  e.g. "0.1.0")
   264|set -euo pipefail
   265|
   266|CURRENT="$1"
   267|LATEST="$2"
   268|
   269|echo "[migrate] Migration $CURRENT -> $LATEST, nothing to do."
   270|exit 0
   271|```
   272|
   273|---
   274|
   275|### Step 7 — Update `packages/integration/Dockerfile`
   276|
   277|These `COPY` directives are already included in the Dockerfile template from Task 03. Verify they are present:
   278|
   279|```dockerfile
   280|# ── default configs and version ───────────────────────────────────────────────
   281|COPY packages/integration/default-configs/ /app/defaults/
   282|COPY packages/integration/app-root/version.txt /app/version.txt
   283|
   284|# ── migration scripts ─────────────────────────────────────────────────────────
   285|COPY packages/integration/scripts/ /app/scripts/
   286|RUN chmod +x /app/scripts/*.sh
   287|
   288|# ── entrypoint (full version — replaces Task 03 stub) ─────────────────────────
   289|COPY packages/integration/entrypoint.sh /app/entrypoint.sh
   290|RUN chmod +x /app/entrypoint.sh
   291|```
   292|
   293|> **Note:** The `ENTRYPOINT ["/app/entrypoint.sh"]` line already exists from Task 03; no change needed there.
   294|
   295|---
   296|
   297|## File Checklist
   298|
   299|After completing this task the following files must exist in the repo:
   300|
   301|```
   302|packages/integration/
   303|├── entrypoint.sh
   304|├── default-configs/
   305|│   ├── hermes.yaml
   306|│   ├── hermes.env.template
   307|│   └── onboarding.json
   308|├── app-root/
   309|│   └── version.txt            ← "0.1.0" — baked into image as /app/version.txt
   310|└── scripts/
   311|    └── migrate.sh
   312|
   313|packages/integration/
   314|└── Dockerfile                 ← already contains all COPY directives from Task 03
   315|```
   316|
   317|---
   318|
   319|## Acceptance Criteria
   320|
   321|All criteria must pass before this task is considered complete.
   322|
   323|| # | Criterion | How to verify (see §Test Commands) |
   324||---|-----------|-------------------------------------|
   325|| AC1 | Fresh container creates correct directory structure under `/data` including `/data/apps/` | `AC1` dir check |
   326|| AC2 | `/data/config/onboarding.json` exists with `{"completed": false}` after first run | `AC2` json check |
   327|| AC3 | Second run does **not** overwrite existing `/data/config` files | `AC3` idempotency check |
   328|| AC4 | `supervisord` starts successfully and all 4 programs reach `RUNNING` | `AC4` status poll (inherits from Task 03) |
   329|| AC5 | If `OPENROUTER_API_KEY` is set in `hermes.env`, it appears in a supervised child process's environment | `AC5` env propagation check |
   330|| AC6 | `/data/apps/hermes-agent/.git` and `/data/apps/hermes-webui/.git` exist after first run | `AC6` git bootstrap check |
   331|| AC7 | Second container run with existing `/data/apps/` skips clone (no network call attempted) | `AC7` skip-clone check |
   332|
   333|---
   334|
   335|## Test Commands
   336|
   337|Run these in order after rebuilding the image with the changes from this task.
   338|
   339|```bash
   340|# ── Rebuild image ──────────────────────────────────────────────────────────────
   341|docker build \
   342|  --platform linux/amd64 \
   343|  -t ghcr.io/fox-in-the-box-ai/cloud:dev \
   344|  -f packages/integration/Dockerfile .
   345|```bash
   346|# ── AC1: Fresh container creates correct /data structure ───────────────────────
   347|# Use a fresh, empty named volume (no prior /data state).
   348|docker volume rm fitb-test-data 2>/dev/null || true
   349|docker volume create fitb-test-data
   350|
   351|docker run --rm \
   352|  --cap-add=NET_ADMIN \
     --device /dev/net/tun \
   353|  --sysctl net.ipv4.ip_forward=1 \
   354|  -v fitb-test-data:/data \
   355|  ghcr.io/fox-in-the-box-ai/cloud:dev \
   356|  bash -c "
   357|    # Give supervisord 2 s to init, then inspect dirs and exit
   358|    sleep 2 && find /data -maxdepth 3 -type d | sort
   359|  "
   360|# Expected output includes:
   361|#   /data/config
   362|#   /data/data/hermes
   363|#   /data/data/mem0
   364|#   /data/data/memos
   365|#   /data/data/tailscale
   366|#   /data/cache
   367|#   /data/logs
   368|#   /data/run
   369|
   370|# ── AC2: onboarding.json created with {completed: false} ─────────────────────
   371|docker run --rm \
   372|  --cap-add=NET_ADMIN \
     --device /dev/net/tun \
   373|  --sysctl net.ipv4.ip_forward=1 \
   374|  -v fitb-test-data:/data \
   375|  ghcr.io/fox-in-the-box-ai/cloud:dev \
   376|  bash -c "sleep 2 && cat /data/config/onboarding.json"
   377|# Expected: {"completed": false}
   378|
   379|# ── AC3: Second run does NOT overwrite existing /data/config files ────────────
   380|# Write a sentinel value into an existing config file, then re-run the container.
   381|docker run --rm \
   382|  -v fitb-test-data:/data \
   383|  busybox \
   384|  sh -c 'echo "SENTINEL=my_custom_value" >> /data/config/hermes.env'
   385|
   386|docker run --rm \
   387|  --cap-add=NET_ADMIN \
     --device /dev/net/tun \
   388|  --sysctl net.ipv4.ip_forward=1 \
   389|  -v fitb-test-data:/data \
   390|  ghcr.io/fox-in-the-box-ai/cloud:dev \
   391|  bash -c "sleep 2 && grep SENTINEL /data/config/hermes.env"
   392|# Expected: SENTINEL=my_custom_value  (file was NOT overwritten)
   393|
   394|# ── AC4: supervisord + all 4 programs RUNNING within 30 s ────────────────────
   395|docker run -d --name fitb-ac4 \
   396|  --cap-add=NET_ADMIN \
     --device /dev/net/tun \
   397|  --sysctl net.ipv4.ip_forward=1 \
   398|  -v fitb-test-data:/data \
   399|  -p 127.0.0.1:8787:8787 \
   400|  ghcr.io/fox-in-the-box-ai/cloud:dev
   401|
   402|for i in $(seq 1 6); do
   403|  sleep 5
   404|  STATUS=$(docker exec fitb-ac4 supervisorctl status 2>/dev/null || true)
   405|  echo "$STATUS"
   406|  RUNNING=$(echo "$STATUS" | grep -c "RUNNING" || true)
   407|  [ "$RUNNING" -ge 4 ] && echo "✅ All 4 programs RUNNING" && break
   408|  echo "... waiting ($((i*5))s elapsed)"
   409|done
   410|
   411|docker rm -f fitb-ac4
   412|
   413|# ── AC5: OPENROUTER_API_KEY from hermes.env is visible in child process env ───
   414|# Seed a hermes.env with the key.
   415|docker run --rm \
   416|  -v fitb-test-data:/data \
   417|  busybox \
   418|  sh -c 'echo "OPENROUTER_API_KEY=***" > /data/config/hermes.env'
   419|
   420|docker run -d --name fitb-ac5 \
   421|  --cap-add=NET_ADMIN \
     --device /dev/net/tun \
   422|  --sysctl net.ipv4.ip_forward=1 \
   423|  -v fitb-test-data:/data \
   424|  ghcr.io/fox-in-the-box-ai/cloud:dev
   425|
   426|sleep 5
   427|
   428|# Check env of the hermes-gateway child process
   429|docker exec fitb-ac5 bash -c \
   430|  'cat /proc/$(supervisorctl pid hermes-gateway)/environ | tr "\0" "\n" | grep OPENROUTER'
   431|# Expected: OPENROUTER_API_KEY=***
   432|
   433|docker rm -f fitb-ac5
   434|
   435|# ── AC6: git repos cloned into /data/apps/ ────────────────────────────────────
   436|docker run --rm \
   437|  --cap-add=NET_ADMIN \
     --device /dev/net/tun \
   438|  --sysctl net.ipv4.ip_forward=1 \
   439|  -v fitb-test-data:/data \
   440|  ghcr.io/fox-in-the-box-ai/cloud:dev \
   441|  bash -c "
   442|    # Wait for entrypoint to finish cloning, then check .git dirs
   443|    sleep 30 && \
   444|    ls /data/apps/hermes-agent/.git/HEAD && \
   445|    ls /data/apps/hermes-webui/.git/HEAD && \
   446|    echo '✅ Both repos cloned'
   447|  "
   448|
   449|# ── AC7: second run skips clone ───────────────────────────────────────────────
   450|docker run --rm \
   451|  --cap-add=NET_ADMIN \
     --device /dev/net/tun \
   452|  --sysctl net.ipv4.ip_forward=1 \
   453|  -v fitb-test-data:/data \
   454|  ghcr.io/fox-in-the-box-ai/cloud:dev \
   455|  bash -c "sleep 5 && grep 'skipping clone' /proc/1/fd/1 2>/dev/null || \
   456|    docker logs \$(hostname) 2>&1 | grep 'skipping clone'"
   457|# Expected: '[entrypoint] hermes-agent already present ... — skipping clone.'
   458|
   459|# ── Cleanup ───────────────────────────────────────────────────────────────────
   460|docker volume rm fitb-test-data
   461|```
   462|
   463|---
   464|
   465|## Notes
   466|
   467|- **Parallel work:** This task can be developed in parallel with Task 05 (onboarding wizard). Task 05 reads `/data/config/onboarding.json`; as long as the schema `{"completed": false}` is stable (it is), both tasks can proceed independently.
   468|- **`cp -n` flag:** The `cp -n` (no-clobber) flag in the first-run bootstrap ensures that if a user manually pre-populates `/data/config/` before the first run, their files are not overwritten. This is intentional.
   469|- **tailscale permissions:** `/data/data/tailscale` is intentionally left `root:root` because `tailscaled` runs as root in supervisord and writes its own state there. Do not `chown` it to `foxinthebox`.
   470|- **`/data/run` permissions:** supervisord writes its pidfile and Unix socket to `/data/run`. This directory is kept root-owned. The socket is `chmod 0770 chown foxinthebox:foxinthebox` per `supervisord.conf` so `supervisorctl` can be called as the `foxinthebox` user.
   471|- **`set -a` / `set +a`:** The entrypoint uses `set -a` before `source hermes.env` so every variable defined in the file is automatically exported into the environment that `exec supervisord` inherits. supervisord then passes this environment to its child processes.
   472|- **Migration script:** `migrate.sh` is intentionally a no-op at this stage. Actual migration logic will be added by future tasks as the schema evolves. The version comparison uses simple string equality; semantic version ordering is not required until there is actual migration logic.
   473|- **Partial clone guard:** The `_clone_app` function checks for `.git/HEAD` (not just the directory) before skipping. If a previous clone was interrupted mid-way, the directory exists but `.git/HEAD` does not — the function will `rm -rf` and retry cleanly. Always use this guard; never check `[ -d "$DEST" ]` alone.
   474|- **First-boot latency:** `git clone` + `pip install -e` for two repos adds ~30–60 seconds to first startup depending on network speed. The onboarding wizard should show a loading state during this window. The entrypoint prints progress lines (`[entrypoint] Cloning ...`, `[entrypoint] Installing ...`) that can be tailed from the Electron app or install script.
   475|