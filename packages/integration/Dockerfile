# syntax=docker/dockerfile:1
FROM python:3.11-slim

# ── build args ────────────────────────────────────────────────────────────────
ARG TARGETARCH=amd64
# Pin QDRANT_VERSION to match qdrant-client in hermes-agent (see task 03 docs).
# Do NOT use "latest" in production builds.
ARG QDRANT_VERSION=v1.9.4
# FITB_VERSION: written to /app/version.txt for migrations and display.
# hermes-agent / hermes-webui are copied from forks/ at build time (requires submodules).
ARG FITB_VERSION=v0.1.0
# FITB_DEV=1: runtime uses bind-mounted repos under /root/.hermes/ (see dev-init.sh).
ARG FITB_DEV=0

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

# ── non-root user ─────────────────────────────────────────────────────────────
RUN useradd -r -s /bin/bash -d /app foxinthebox \
    && mkdir -p /data \
    && chown -R foxinthebox:foxinthebox /app /data

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
