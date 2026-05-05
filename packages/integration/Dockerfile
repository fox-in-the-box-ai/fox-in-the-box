# syntax=docker/dockerfile:1
FROM python:3.11-slim

# ── build args ────────────────────────────────────────────────────────────────
ARG TARGETARCH=amd64
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

# ── entrypoint (full version — replaces Task 03 stub) ─────────────────────────
COPY packages/integration/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# ── runtime ───────────────────────────────────────────────────────────────────
ENV FITB_DEV=${FITB_DEV}
VOLUME ["/data"]
EXPOSE 8787 6333

ENTRYPOINT ["/app/entrypoint.sh"]
