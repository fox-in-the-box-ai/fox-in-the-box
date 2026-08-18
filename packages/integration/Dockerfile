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
# Pin QDRANT_VERSION deliberately. The standalone server and the pip-installed
# qdrant-client are intentionally independent: mem0 uses the client in embedded
# *path* mode (no server connection on any default path), and nothing on a
# default install path dials this server with a version-coupled client.
# Do NOT use "latest" in production builds.
ARG QDRANT_VERSION=v1.9.4
# Pin LLAMACPP_VERSION — daily build tags on ggml-org/llama.cpp ship pre-built
# CPU binaries for both ubuntu-x64 and ubuntu-arm64. Avoid "latest"; pick a
# tested tag and bump deliberately. (#9)
ARG LLAMACPP_VERSION=b9026
# FITB_VERSION: written to /app/version.txt for migrations and display.
# hermes-agent / hermes-webui are copied from forks/ at build time (requires submodules).
ARG FITB_VERSION=v0.1.0
ARG FITB_RUNTIME_VERSION=unknown
# FITB_DEV=1: runtime uses bind-mounted repos under /root/.hermes/ (see dev-init.sh).
ARG FITB_DEV=0

# ── system dependencies ───────────────────────────────────────────────────────
# libgomp1 + libcurl4 are runtime deps for the bundled llama.cpp llama-server
# binary (issue #9). Both are small (libgomp1 ~150 KB, libcurl4 ~400 KB).
# openssh-client gives agents ssh/scp/sftp for remote host management and
# git-over-ssh (subagent VPS ops, demo box rollouts); rsync pairs with it
# for the vps-patch-sync flow. Baking BOTH keeps the entrypoint tool-heal
# a true no-op on fresh images (~15-20 MB installed with the krb5/gnutls
# dependency train — shared in part with git).
# `upgrade -y` first: the python:3.11-slim base is a point-in-time
# snapshot, and without it Debian security fixes published after that
# snapshot never reach the image — this was most of the fixable Trivy
# backlog (#755). Tailscale and Node track their own apt repos below, so
# each rebuild already pulls their current versions.
RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
        gnupg \
        git \
        lsb-release \
        iproute2 \
        iptables \
        libgomp1 \
        libcurl4 \
        openssh-client \
        rsync \
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
RUN pip install --no-cache-dir --upgrade pip wheel setuptools \
    && pip install --no-cache-dir supervisor

# ── Qdrant binary ─────────────────────────────────────────────────────────────
RUN set -eux; \
    mkdir -p /app/qdrant; \
    case "${TARGETARCH:-amd64}" in \
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
    case "${TARGETARCH:-amd64}" in \
        arm64) ARCH_SUFFIX="arm64" ;; \
        *)     ARCH_SUFFIX="x64"  ;; \
    esac; \
    curl -fsSL \
        "https://github.com/ggml-org/llama.cpp/releases/download/${LLAMACPP_VERSION}/llama-${LLAMACPP_VERSION}-bin-ubuntu-${ARCH_SUFFIX}.tar.gz" \
        | tar -xzf - -C /app/llama-cpp --strip-components=1; \
    chmod +x /app/llama-cpp/llama-server

# ── embedding model (mem0 local embedder — served by [program:embed-server]) ──
# The URL / sha256 / filename live ONLY in embed-model.lock (single source of
# truth for the model pin). The lock is COPYd to /tmp/ deliberately: it must
# sit beside install-core.sh — which also runs from /tmp during this build —
# because install-core sources it via "$(dirname "$0")/embed-model.lock".
# The GGUF is arch-independent; the llama-server binary above serves it.
# Placed with the stable binary layers (qdrant / llama-server) so overlay and
# app-source edits don't bust this ~95 MB download layer.
COPY packages/integration/embed-model.lock /tmp/embed-model.lock
RUN set -eux; \
    . /tmp/embed-model.lock; \
    mkdir -p /app/models; \
    curl -fsSL "$EMBED_MODEL_URL" -o "/app/models/$EMBED_MODEL_FILENAME"; \
    echo "$EMBED_MODEL_SHA256  /app/models/$EMBED_MODEL_FILENAME" | sha256sum -c

# ── non-root user ─────────────────────────────────────────────────────────────
RUN useradd -r -s /bin/bash -d /app foxinthebox \
    && mkdir -p /data \
    && chown -R foxinthebox:foxinthebox /app /data \
    && (getent group tailscale >/dev/null && usermod -aG tailscale foxinthebox || true)

# Marker for Hermes WebUI: bind behavior / container hints (see hermes-webui server.py)
RUN printf '1\n' > /.within_container

# ── default configs and version ───────────────────────────────────────────────
# Note: supervisord.conf is generated by install-core.sh (see below), not COPYd.
COPY packages/integration/default-configs/ /app/defaults/
COPY packages/integration/app-root/version.txt /app/version.txt
# Overwrite version.txt with the build-arg value (migrations / display).
RUN echo "${FITB_VERSION}" > /app/version.txt
RUN echo "${FITB_RUNTIME_VERSION}" > /app/runtime_version.txt

# ── migration scripts ─────────────────────────────────────────────────────────
COPY packages/integration/scripts/ /app/scripts/
RUN chmod +x /app/scripts/*.sh

# ── Hermes app source (git submodules — init before build) ─────────────────────
COPY forks/hermes-agent /app/hermes-agent
COPY forks/hermes-webui /app/hermes-webui

# ── Fox overlay COPY (static assets + patches + Python package) ───────────────
# COPYd before install-core.sh so the overlay is available as FITB_OVERLAY_DIR.
# Placed after the upstream forks COPY so overlay-only edits don't bust the
# (slow) forks+pip layer cache.
COPY packages/fox-overlay /app/fox-overlay

# ── pip constraints (supply-chain pin) ───────────────────────────────────────
# Pins every transitive Python dependency to the version resolved in the last
# verified build. Prevents silent dep drift across builds. Regenerate after
# upstream bumps: see packages/integration/requirements.lock header.
COPY packages/integration/requirements.lock /app/requirements.lock

# ── install-core.sh — patches, pip, supervisord.conf ─────────────────────────
# Single source of truth for all install logic (shared with .deb postinst).
# Runs in Docker context: repos already COPYd, binaries handled in separate
# layers above (FITB_SKIP_BINARIES=1), venv skipped (uses system pip).
ARG FITB_DISABLE_WEBUI_OVERLAY=0
ARG FITB_DISABLE_AGENT_OVERLAY=0
COPY packages/install-core/install-core.sh /tmp/install-core.sh
RUN set -eux; \
    chmod +x /tmp/install-core.sh; \
    FITB_APP_DIR=/app \
    FITB_CONTEXT=docker \
    FITB_SKIP_BINARIES=1 \
    FITB_OVERLAY_DIR=/app/fox-overlay \
    FITB_DISABLE_WEBUI_OVERLAY=${FITB_DISABLE_WEBUI_OVERLAY} \
    FITB_DISABLE_AGENT_OVERLAY=${FITB_DISABLE_AGENT_OVERLAY} \
    FITB_PIP_CONSTRAINTS=/app/requirements.lock \
    bash /tmp/install-core.sh; \
    rm /tmp/install-core.sh /tmp/embed-model.lock; \
    chown -R foxinthebox:foxinthebox /app/hermes-agent /app/hermes-webui /app/fox-overlay

ENV HERMES_WEBUI_EXTENSION_DIR=/app/fox-overlay/webui_static \
    HERMES_WEBUI_EXTENSION_SCRIPT_URLS=/extensions/onboarding-preview.js,/extensions/fox-overlay.js,/extensions/hostname-prompt.js,/extensions/fallback-polish.js,/extensions/stream-error-retry.js,/extensions/chat-model-preselect.js,/extensions/model-picker-filter.js,/extensions/approval-explain.js,/extensions/custom-providers.js \
    HERMES_WEBUI_EXTENSION_STYLESHEET_URLS=/extensions/fox-in-the-box.css

# ── entrypoint (full version — replaces Task 03 stub) ─────────────────────────
COPY packages/integration/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# ── runtime ───────────────────────────────────────────────────────────────────
ENV FITB_DEV=${FITB_DEV}
# mem0's bundled PostHog telemetry stays off at every process boundary. The
# image-level ENV covers processes outside supervisord's environment= lines
# and the entrypoint's export (e.g. docker exec sessions).
ENV MEM0_TELEMETRY=False
VOLUME ["/data"]
EXPOSE 8787 6333

ENTRYPOINT ["/app/entrypoint.sh"]
