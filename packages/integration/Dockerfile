# syntax=docker/dockerfile:1
FROM python:3.11-slim

# ── build args ────────────────────────────────────────────────────────────────
ARG TARGETARCH=amd64
# Pin QDRANT_VERSION to match qdrant-client in hermes-agent (see task 03 docs).
# Do NOT use "latest" in production builds.
ARG QDRANT_VERSION=v1.9.4
# FITB_VERSION: the git tag to clone for hermes-agent and hermes-webui.
# Defaults to content of VERSION file; override at build time: docker build --build-arg FITB_VERSION=v0.2.0 ...
# For dev mode: pass FITB_DEV=1 to skip version tag cloning and use local mounts instead
ARG FITB_VERSION=v0.1.0
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

# Marker for Hermes WebUI: bind behavior / container hints (see hermes-webui server.py)
RUN printf '1\n' > /.within_container

# ── supervisord config ────────────────────────────────────────────────────────
COPY packages/integration/supervisord.conf /etc/supervisor/supervisord.conf

# ── default configs and version ───────────────────────────────────────────────
COPY packages/integration/default-configs/ /app/defaults/
COPY packages/integration/app-root/version.txt /app/version.txt
# Overwrite version.txt with the build-arg value so entrypoint uses the right tag
RUN echo "${FITB_VERSION}" > /app/version.txt

# ── migration scripts ─────────────────────────────────────────────────────────
COPY packages/integration/scripts/ /app/scripts/
RUN chmod +x /app/scripts/*.sh

# ── entrypoint (full version — replaces Task 03 stub) ─────────────────────────
COPY packages/integration/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# ── runtime ───────────────────────────────────────────────────────────────────
VOLUME ["/data"]
EXPOSE 8787 6333

ENTRYPOINT ["/app/entrypoint.sh"]
