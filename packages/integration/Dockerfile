# syntax=docker/dockerfile:1
FROM python:3.11-slim

# ── build args ────────────────────────────────────────────────────────────────
# QA fix (v0.4.7 verification, Phase 0): TARGETARCH is automatically set by
# BuildKit based on the target platform (--platform linux/arm64 → "arm64",
# linux/amd64 → "amd64"). Previously this line had a default value
# `=amd64` which OVERRODE BuildKit's auto-injection — so on every arm64
# build (including the multi-arch CI matrix), TARGETARCH stuck as "amd64"
# and we downloaded the x86_64 tarballs for both qdrant and llama-server
# into the arm64 image. qdrant happened to keep working via Rosetta
# emulation on Apple Silicon; llama-server failed with
#   "rosetta error: failed to open elf at /lib64/ld-linux-x86-64.so.2"
# meaning the entire local-fallback feature (issue #9, shipped in
# v0.4.1) was silently broken on Apple Silicon since launch. Removing
# the default lets BuildKit's value flow through. If the variable IS
# unset (some non-buildkit pathway), the case statements default to x64
# anyway, so this change cannot make non-buildkit builds worse.
ARG TARGETARCH
# Pin QDRANT_VERSION to match qdrant-client in hermes-agent (see task 03 docs).
# Do NOT use "latest" in production builds.
ARG QDRANT_VERSION=v1.9.4
# Pin LLAMACPP_VERSION — daily build tags on ggml-org/llama.cpp ship pre-built
# CPU binaries for both ubuntu-x64 and ubuntu-arm64. Avoid "latest"; pick a
# tested tag and bump deliberately. (#9)
ARG LLAMACPP_VERSION=b9026
# FITB_VERSION: written to /app/version.txt for migrations and display.
# hermes-agent / hermes-webui are copied from forks/ at build time (requires submodules).
ARG FITB_VERSION=v0.1.0
# FITB_DEV=1: runtime uses bind-mounted repos under /root/.hermes/ (see dev-init.sh).
ARG FITB_DEV=0

# ── system dependencies ───────────────────────────────────────────────────────
# libgomp1 + libcurl4 are runtime deps for the bundled llama.cpp llama-server
# binary (issue #9). Both are small (libgomp1 ~150 KB, libcurl4 ~400 KB).
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
        gnupg \
        git \
        lsb-release \
        iproute2 \
        iptables \
        libgomp1 \
        libcurl4 \
    && rm -rf /var/lib/apt/lists/*

# ── Node.js (LTS) — required for npx-based MCP servers (e.g. Brave Search) ───
RUN curl -fsSL https://deb.nodesource.com/setup_lts.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# ── Tailscale ─────────────────────────────────────────────────────────────────
RUN curl -fsSL "https://pkgs.tailscale.com/stable/debian/$(lsb_release -cs).noarmor.gpg" \
        | tee /usr/share/keyrings/tailscale-archive-keyring.gpg >/dev/null \
    && curl -fsSL "https://pkgs.tailscale.com/stable/debian/$(lsb_release -cs).tailscale-keyring.list" \
        | tee /etc/apt/sources.list.d/tailscale.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends tailscale \
    && rm -rf /var/lib/apt/lists/*

# ── Python packages (supervisor + Hermes apps from monorepo forks) ────────────
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

# ── llama.cpp llama-server binary ─────────────────────────────────────────────
# Bundled per-arch CPU build. Used by issue #9's local-fallback runtime —
# llama-server speaks /v1/chat/completions, /v1/models, /v1/embeddings
# (drop-in OpenAI-compat). Tarball ships its own .so files; llama-server's
# RUNPATH=$ORIGIN makes them resolve from /app/llama-cpp without any
# LD_LIBRARY_PATH gymnastics.
#
# The supervisord [program:llama-server] block is autostart=false and only
# spawns when api/local_fallback.py decides the user has opted in AND the
# model file (#10's download manager) is present. No idle RAM cost when
# the user hasn't enabled local fallback.
RUN set -eux; \
    mkdir -p /app/llama-cpp; \
    case "${TARGETARCH}" in \
        arm64) ARCH_SUFFIX="arm64" ;; \
        *)     ARCH_SUFFIX="x64"  ;; \
    esac; \
    curl -fsSL \
        "https://github.com/ggml-org/llama.cpp/releases/download/${LLAMACPP_VERSION}/llama-${LLAMACPP_VERSION}-bin-ubuntu-${ARCH_SUFFIX}.tar.gz" \
        | tar -xzf - -C /app/llama-cpp --strip-components=1; \
    chmod +x /app/llama-cpp/llama-server

# ── non-root user ─────────────────────────────────────────────────────────────
RUN useradd -r -s /bin/bash -d /app foxinthebox \
    && mkdir -p /data \
    && chown -R foxinthebox:foxinthebox /app /data \
    && (getent group tailscale >/dev/null && usermod -aG tailscale foxinthebox || true)

# Marker for Hermes WebUI: bind behavior / container hints (see hermes-webui server.py)
RUN printf '1\n' > /.within_container

# ── supervisord config ────────────────────────────────────────────────────────
COPY packages/integration/supervisord.conf /etc/supervisor/supervisord.conf

# ── default configs and version ───────────────────────────────────────────────
COPY packages/integration/default-configs/ /app/defaults/
COPY packages/integration/app-root/version.txt /app/version.txt
# Overwrite version.txt with the build-arg value (migrations / display).
RUN echo "${FITB_VERSION}" > /app/version.txt

# ── migration scripts ─────────────────────────────────────────────────────────
COPY packages/integration/scripts/ /app/scripts/
RUN chmod +x /app/scripts/*.sh

# ── Hermes app source (git submodules — init before build) ─────────────────────
COPY forks/hermes-agent /app/hermes-agent
COPY forks/hermes-webui /app/hermes-webui

# ── Fox webui patch series (Phase 4 of v0.6.0 migration) ──────────────────────
# Apply the patch series to /app/hermes-webui BEFORE pip install so the editable
# install registers the patched source. Submodule COPY brings in a `.git`
# gitlink file pointing at the superproject's .git/modules/... which doesn't
# exist in the container; `git apply` chokes on the broken pointer. The
# gitlink is useless inside the container anyway (nothing reads it), so we
# delete it before the apply loop — no rename/restore dance, no half-state
# risk if a patch fails mid-loop.
#
# `git apply --check` runs first on every patch — fuzz-tolerance failure
# surfaces here as a build-time error with a readable diagnostic rather than
# silently degrading runtime behavior. Phase 9 nightly upstream-watch CI uses
# the same `--check` against new upstream tags.
#
# FITB_DISABLE_WEBUI_OVERLAY=1 short-circuits the entire patch loop.
# Useful for bisecting overlay-induced regressions (compare patched vs
# vanilla container behavior) and for emergency rollback if a fresh
# upstream tag breaks anchor matching before the patches have been
# regenerated. The dispatcher hook in api/routes.py is the only runtime
# coupling; routes.py without it is just Fox's routes.py which works
# fine without the dispatcher (no Phase 5+ overlay handlers, but Fox's
# fork-side handlers still serve every existing route).
#
# Submodule pointer drift: any drift surfaces as a `git apply --check`
# anchor mismatch with the verbose error block below. Stronger pre-flight
# (assert submodule SHA matches a build-arg) is not feasible inside the
# container because the COPY'd submodule's `.git` is a broken gitlink.
# Monorepo CI is the right gate — it runs `git submodule status` before
# docker build; a stale submodule fails the workflow before we get here.
ARG FITB_DISABLE_WEBUI_OVERLAY=0
COPY packages/fox-overlay/patches/webui /tmp/fox-webui-patches
RUN set -eu; \
    if [ "${FITB_DISABLE_WEBUI_OVERLAY}" = "1" ]; then \
        echo "[fox-patch] FITB_DISABLE_WEBUI_OVERLAY=1 — skipping webui patch series"; \
        rm -rf /tmp/fox-webui-patches; \
        exit 0; \
    fi; \
    cd /app/hermes-webui; \
    rm -f .git; \
    series_file=/tmp/fox-webui-patches/series; \
    if [ ! -f "$series_file" ]; then \
        echo "::error::missing series file: $series_file"; exit 1; \
    fi; \
    patches=$(tr -d '\r' < "$series_file" | grep -vE '^\s*$|^\s*#' || true); \
    if [ -z "$patches" ]; then \
        echo "[fox-patch] series file empty; nothing to apply"; \
        rm -rf /tmp/fox-webui-patches; \
        exit 0; \
    fi; \
    echo "$patches" | while IFS= read -r p; do \
        [ -z "$p" ] && continue; \
        echo "[fox-patch] applying webui/$p"; \
        if ! err=$(git apply --check "/tmp/fox-webui-patches/$p" 2>&1); then \
            echo "::error::patch webui/$p failed --check"; \
            echo "----- git apply --check output -----"; \
            echo "$err"; \
            echo "------------------------------------"; \
            exit 1; \
        fi; \
        git apply "/tmp/fox-webui-patches/$p"; \
    done; \
    rm -rf /tmp/fox-webui-patches

# ── Fox agent patch series (Phase 8 of v0.6.0 migration) ─────────────────────
# Mirrors the webui patch series above. First non-empty consumer of the
# agent series at Phase 8: the gateway/run.py bootstrap shim that calls
# fox_overlay.agent_plugins.register() — without this, hermes-agent's
# PluginManager.discover_and_load() is only invoked from `hermes` CLI
# commands (not from the gateway startup path), so Phase 3 monkey-patches
# never fire when running as a daemon.
#
# FITB_DISABLE_AGENT_OVERLAY=1 short-circuits both the patch loop here
# AND the patched shim's runtime path (gated by env var inside the shim).
ARG FITB_DISABLE_AGENT_OVERLAY=0
COPY packages/fox-overlay/patches/agent /tmp/fox-agent-patches
RUN set -eu; \
    if [ "${FITB_DISABLE_AGENT_OVERLAY}" = "1" ]; then \
        echo "[fox-patch] FITB_DISABLE_AGENT_OVERLAY=1 — skipping agent patch series"; \
        rm -rf /tmp/fox-agent-patches; \
        exit 0; \
    fi; \
    cd /app/hermes-agent; \
    rm -f .git; \
    series_file=/tmp/fox-agent-patches/series; \
    if [ ! -f "$series_file" ]; then \
        echo "[fox-patch] no agent series — skipping"; \
        rm -rf /tmp/fox-agent-patches; \
        exit 0; \
    fi; \
    patches=$(tr -d '\r' < "$series_file" | grep -vE '^\s*$|^\s*#' || true); \
    if [ -z "$patches" ]; then \
        echo "[fox-patch] agent series file empty; nothing to apply"; \
        rm -rf /tmp/fox-agent-patches; \
        exit 0; \
    fi; \
    echo "$patches" | while IFS= read -r p; do \
        [ -z "$p" ] && continue; \
        echo "[fox-patch] applying agent/$p"; \
        if ! err=$(git apply --check "/tmp/fox-agent-patches/$p" 2>&1); then \
            echo "::error::patch agent/$p failed --check"; \
            echo "----- git apply --check output -----"; \
            echo "$err"; \
            echo "------------------------------------"; \
            exit 1; \
        fi; \
        git apply "/tmp/fox-agent-patches/$p"; \
    done; \
    rm -rf /tmp/fox-agent-patches

# ── Fox agent memory plugins (Phase 8 of v0.6.0 migration) ───────────────────
# COPY Fox-only memory provider plugins into upstream agent's
# `plugins/memory/` directory. Upstream hermes-agent discovers memory
# providers via directory-scan (separate path from the entry-point
# discovery used for general plugins) — see Phase 3 deferral note in
# fox_overlay/MANIFEST.toml. Each subdirectory under
# packages/fox-overlay/agent_memory_plugins/ becomes a sibling of
# upstream's plugins/memory/byterover, /hindsight, etc.
#
# FITB_DISABLE_AGENT_OVERLAY=1 short-circuits this step too (consistent
# with the agent patch series above).
COPY packages/fox-overlay/agent_memory_plugins /tmp/fox-agent-mem-plugins
RUN set -eu; \
    if [ "${FITB_DISABLE_AGENT_OVERLAY}" = "1" ]; then \
        echo "[fox-mem] FITB_DISABLE_AGENT_OVERLAY=1 — skipping agent memory plugins"; \
        rm -rf /tmp/fox-agent-mem-plugins; \
        exit 0; \
    fi; \
    target=/app/hermes-agent/plugins/memory; \
    if [ ! -d "$target" ]; then \
        echo "::error::upstream agent missing plugins/memory/ directory — refused to create"; \
        exit 1; \
    fi; \
    for src in /tmp/fox-agent-mem-plugins/*/; do \
        [ -d "$src" ] || continue; \
        name=$(basename "$src"); \
        echo "[fox-mem] installing $name → $target/"; \
        cp -R "$src" "$target/"; \
    done; \
    rm -rf /tmp/fox-agent-mem-plugins

# ── .fox-removals consumer (Phase 7 of v0.6.0 migration) ──────────────────────
# Apply the .fox-removals manifest to /app/hermes-webui. Each line names a
# fork-relative path Fox does NOT ship (e.g. upstream onboarding tests that
# Fox replaced with its own wizard). xargs invokes rm -f so missing files
# are silent (the file's load-bearing only at Phase 8 when the submodule
# re-points at virgin upstream; pre-Phase-8 the entries are no-ops because
# Fox already removed those files from the fork in past commits).
#
# Same parse convention as the webui patch series above: strip blanks +
# comments via `grep -vE '^\s*$|^\s*#'`, strip CRLF, pass through xargs.
COPY packages/fox-overlay/.fox-removals /tmp/fox-removals
RUN set -eu; \
    if [ "${FITB_DISABLE_WEBUI_OVERLAY}" = "1" ]; then \
        echo "[fox-removals] FITB_DISABLE_WEBUI_OVERLAY=1 — skipping removals"; \
        rm -f /tmp/fox-removals; \
        exit 0; \
    fi; \
    cd /app/hermes-webui; \
    removals=$(tr -d '\r' < /tmp/fox-removals | grep -vE '^\s*$|^\s*#' || true); \
    if [ -z "$removals" ]; then \
        echo "[fox-removals] manifest empty; nothing to remove"; \
        rm -f /tmp/fox-removals; \
        exit 0; \
    fi; \
    echo "$removals" | while IFS= read -r p; do \
        [ -z "$p" ] && continue; \
        if [ -e "$p" ]; then \
            echo "[fox-removals] rm $p"; \
            rm -f -- "$p"; \
        else \
            echo "[fox-removals] (absent — no-op) $p"; \
        fi; \
    done; \
    rm -f /tmp/fox-removals

RUN set -eux; \
    pip install -e /app/hermes-agent --quiet --no-cache-dir; \
    if [ -f /app/hermes-webui/pyproject.toml ] || [ -f /app/hermes-webui/setup.py ]; then \
        pip install -e /app/hermes-webui --quiet --no-cache-dir; \
    elif [ -f /app/hermes-webui/requirements.txt ]; then \
        pip install -r /app/hermes-webui/requirements.txt --quiet --no-cache-dir; \
    else \
        echo "ERROR: hermes-webui has no pyproject.toml, setup.py, or requirements.txt" >&2; \
        exit 1; \
    fi; \
    chown -R foxinthebox:foxinthebox /app/hermes-agent /app/hermes-webui

# ── Fox overlay: install package + serve static via api/extensions.py ─────────
# Phase 3 of v0.6.0 migration: COPY the whole overlay (Python modules + static
# webui assets) and pip install -e it. The pip install registers fox-overlay
# for import — the hermes_agent.plugins entry-points in fox-overlay's
# pyproject.toml wire into hermes-agent's PluginManager so register(ctx) fires
# at agent startup (applies the 3 monkey-patches: target_model fix, auxiliary
# default fallback, cron failure diagnostics). The same COPY makes
# webui_static/ available for the Phase-2 HERMES_WEBUI_EXTENSION_DIR-based
# static-asset serving.
#
# Placed AFTER the upstream pip install so static-asset OR overlay-code edits
# don't invalidate the (slow) upstream pip install layer cache.
COPY packages/fox-overlay /app/fox-overlay
RUN pip install --no-cache-dir -e /app/fox-overlay
ENV HERMES_WEBUI_EXTENSION_DIR=/app/fox-overlay/webui_static \
    HERMES_WEBUI_EXTENSION_SCRIPT_URLS=/extensions/onboarding-preview.js,/extensions/fox-overlay.js,/extensions/hostname-prompt.js,/extensions/fallback-polish.js,/extensions/stream-error-retry.js \
    HERMES_WEBUI_EXTENSION_STYLESHEET_URLS=/extensions/fox-in-the-box.css

# ── entrypoint (full version — replaces Task 03 stub) ─────────────────────────
COPY packages/integration/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# ── runtime ───────────────────────────────────────────────────────────────────
ENV FITB_DEV=${FITB_DEV}
VOLUME ["/data"]
EXPOSE 8787 6333

ENTRYPOINT ["/app/entrypoint.sh"]
