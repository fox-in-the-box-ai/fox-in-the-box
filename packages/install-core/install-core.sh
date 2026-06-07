#!/usr/bin/env bash
# install-core.sh — Fox in the Box shared install logic
#
# Single source of truth for all install steps. Called by:
#   • packages/integration/Dockerfile  (FITB_CONTEXT=docker)
#   • packages/deb/control/postinst    (FITB_CONTEXT=bare-metal, default)
#
# Idempotent — safe to re-run on upgrade.
#
# Environment variables (all optional — sane defaults):
#   FITB_APP_DIR         App root. Default: /opt/foxinthebox  (bare-metal)
#                        Docker sets this to /app.
#   FITB_CONTEXT         docker | bare-metal (default: bare-metal)
#   FITB_VERSION         Written to version.txt. Default: read from $FITB_APP_DIR/version.txt.
#   FITB_SKIP_BINARIES   1 = skip qdrant + llama-server download. Default: 0.
#                        Docker sets 1 when binaries are already in a cached layer.
#   FITB_DISABLE_WEBUI_OVERLAY   1 = skip webui patch series. Default: 0.
#   FITB_DISABLE_AGENT_OVERLAY   1 = skip agent patch series + mem plugins + SOUL. Default: 0.
#   QDRANT_VERSION       Default: v1.9.4
#   LLAMACPP_VERSION     Default: b9026
#   FITB_OVERLAY_DIR     Path to fox-overlay package. Default: $FITB_APP_DIR/fox-overlay
#                        Docker passes /tmp/fox-overlay (COPYd before install-core runs).

set -euo pipefail

# ── 0. Config ─────────────────────────────────────────────────────────────────
FITB_APP_DIR="${FITB_APP_DIR:-/opt/foxinthebox}"
FITB_CONTEXT="${FITB_CONTEXT:-bare-metal}"
if [ "$FITB_CONTEXT" = "docker" ]; then
    FITB_DATA_DIR="${FITB_DATA_DIR:-/data}"
else
    FITB_DATA_DIR="${FITB_DATA_DIR:-/opt/foxinthebox/.foxinthebox}"
fi
QDRANT_VERSION="${QDRANT_VERSION:-v1.9.4}"
LLAMACPP_VERSION="${LLAMACPP_VERSION:-b9026}"
FITB_SKIP_BINARIES="${FITB_SKIP_BINARIES:-0}"
FITB_DISABLE_WEBUI_OVERLAY="${FITB_DISABLE_WEBUI_OVERLAY:-0}"
FITB_DISABLE_AGENT_OVERLAY="${FITB_DISABLE_AGENT_OVERLAY:-0}"
FITB_OVERLAY_DIR="${FITB_OVERLAY_DIR:-$FITB_APP_DIR/fox-overlay}"

FITB_VERSION="${FITB_VERSION:-$(cat "$FITB_APP_DIR/version.txt" 2>/dev/null || echo "unknown")}"

# Arch detection — works on host (uname -m) and inside Docker (TARGETARCH set externally)
case "${TARGETARCH:-$(uname -m)}" in
    aarch64|arm64) ARCH_QDRANT="aarch64"; ARCH_LLAMA="arm64" ;;
    *)             ARCH_QDRANT="x86_64";  ARCH_LLAMA="x64"   ;;
esac

_log()  { echo "[install-core] $*"; }
_warn() { echo "[install-core] WARNING: $*" >&2; }
_die()  { echo "[install-core] ERROR: $*" >&2; exit 1; }

_log "Starting Fox in the Box install (version=$FITB_VERSION, context=$FITB_CONTEXT, app=$FITB_APP_DIR)"

# ── 1. Qdrant binary ──────────────────────────────────────────────────────────
_install_qdrant() {
    local dest="$FITB_APP_DIR/qdrant/qdrant"
    if [ -x "$dest" ]; then
        _log "qdrant already present — skipping download"
        return 0
    fi
    _log "Downloading qdrant $QDRANT_VERSION ($ARCH_QDRANT)..."
    mkdir -p "$FITB_APP_DIR/qdrant"
    local ver="$QDRANT_VERSION"
    if [ "$ver" = "latest" ]; then
        ver=$(curl -fsSL -o /dev/null -w '%{url_effective}' \
            https://github.com/qdrant/qdrant/releases/latest \
            | sed 's|.*/tag/||')
    fi
    curl -fsSL \
        "https://github.com/qdrant/qdrant/releases/download/${ver}/qdrant-${ARCH_QDRANT}-unknown-linux-musl.tar.gz" \
        | tar -xzf - -C "$FITB_APP_DIR/qdrant"
    chmod +x "$dest"
    _log "qdrant installed at $dest"
}

# ── 2. llama-server binary ────────────────────────────────────────────────────
_install_llama_server() {
    local dest="$FITB_APP_DIR/llama-cpp/llama-server"
    if [ -x "$dest" ]; then
        _log "llama-server already present — skipping download"
        return 0
    fi
    _log "Downloading llama-server $LLAMACPP_VERSION ($ARCH_LLAMA)..."
    mkdir -p "$FITB_APP_DIR/llama-cpp"
    curl -fsSL \
        "https://github.com/ggml-org/llama.cpp/releases/download/${LLAMACPP_VERSION}/llama-${LLAMACPP_VERSION}-bin-ubuntu-${ARCH_LLAMA}.tar.gz" \
        | tar -xzf - -C "$FITB_APP_DIR/llama-cpp" --strip-components=1
    chmod +x "$dest"
    _log "llama-server installed at $dest"
}

# ── 3. Hermes repos — clone or sync to pinned upstream tags ───────────────────
# Reads tags from packages/fox-overlay/versions.toml (relative to FITB_OVERLAY_DIR).
_read_versions_toml() {
    local toml="$FITB_OVERLAY_DIR/versions.toml"
    [ -f "$toml" ] || _die "versions.toml not found at $toml"
    WEBUI_TAG=$(grep 'hermes_webui_tag' "$toml" | sed 's/.*= *"\(.*\)"/\1/')
    WEBUI_URL=$(grep 'hermes_webui_url' "$toml" | sed 's/.*= *"\(.*\)"/\1/')
    AGENT_TAG=$(grep 'hermes_agent_tag' "$toml" | sed 's/.*= *"\(.*\)"/\1/')
    AGENT_URL=$(grep 'hermes_agent_url' "$toml" | sed 's/.*= *"\(.*\)"/\1/')
    [ -n "$WEBUI_TAG" ] && [ -n "$AGENT_TAG" ] || _die "Failed to parse tags from $toml"
    _log "Pinned: hermes-webui=$WEBUI_TAG  hermes-agent=$AGENT_TAG"
}

_sync_repo() {
    local name="$1" url="$2" tag="$3"
    local dest="$FITB_APP_DIR/$name"
    if [ -d "$dest/.git" ]; then
        _log "$name exists — fetching tag $tag..."
        git -C "$dest" fetch --depth=1 origin "refs/tags/$tag:refs/tags/$tag" 2>/dev/null || \
            git -C "$dest" fetch --depth=1 origin "$tag"
        git -C "$dest" checkout "$tag" --quiet
    else
        _log "Cloning $name @ $tag..."
        rm -rf "$dest"
        git clone --depth=1 --branch "$tag" "$url" "$dest" --quiet
    fi
    # Remove .git gitlink file left by a COPY'd submodule (Docker path).
    # .git in a submodule COPY is a plain file (the gitlink), not a directory.
    # Deleting it is safe — nothing inside the container reads it, and
    # git apply requires it to be absent to avoid choke on broken pointer.
    [ -f "$dest/.git" ] && rm -f "$dest/.git" || true
}

_sync_hermes_repos() {
    # In Docker context, the repos are already COPYd by the Dockerfile at the
    # correct pinned tag. We only need to remove the gitlink and we're done.
    if [ "$FITB_CONTEXT" = "docker" ]; then
        _log "Docker context — repos already COPYd; cleaning gitlinks only"
        [ -f "$FITB_APP_DIR/hermes-agent/.git" ] && rm -f "$FITB_APP_DIR/hermes-agent/.git" || true
        [ -f "$FITB_APP_DIR/hermes-webui/.git" ] && rm -f "$FITB_APP_DIR/hermes-webui/.git" || true
        return 0
    fi
    _read_versions_toml
    _sync_repo hermes-agent "$AGENT_URL" "$AGENT_TAG"
    _sync_repo hermes-webui "$WEBUI_URL" "$WEBUI_TAG"
}

# ── 4. Apply fox-overlay patch series ────────────────────────────────────────
_apply_patch_series() {
    local target="$1"        # e.g. $FITB_APP_DIR/hermes-webui
    local patch_dir="$2"     # e.g. $FITB_OVERLAY_DIR/patches/webui
    local label="$3"         # e.g. "webui"

    local series_file="$patch_dir/series"
    [ -f "$series_file" ] || { _log "$label: no series file — skipping"; return 0; }

    local patches
    patches=$(tr -d '\r' < "$series_file" | grep -vE '^\s*$|^\s*#' || true)
    if [ -z "$patches" ]; then
        _log "$label: series file empty — skipping"
        return 0
    fi

    _log "Applying $label patch series in $target..."
    # Ensure we're in a git-apply-able state (no broken gitlink)
    [ -f "$target/.git" ] && rm -f "$target/.git" || true

    echo "$patches" | while IFS= read -r p; do
        [ -z "$p" ] && continue
        local patch_file="$patch_dir/$p"
        [ -f "$patch_file" ] || _die "Patch file missing: $patch_file"
        _log "  checking $label/$p"
        if ! err=$(git -C "$target" apply --check "$patch_file" 2>&1); then
            echo "::error::patch $label/$p failed --check"
            echo "----- git apply --check output -----"
            echo "$err"
            echo "------------------------------------"
            _die "Patch check failed — aborting"
        fi
        git -C "$target" apply "$patch_file"
        _log "  applied $label/$p"
    done
    _log "$label patch series applied."
}

_apply_patches() {
    if [ "$FITB_DISABLE_WEBUI_OVERLAY" = "1" ]; then
        _log "FITB_DISABLE_WEBUI_OVERLAY=1 — skipping webui patches"
    else
        _apply_patch_series \
            "$FITB_APP_DIR/hermes-webui" \
            "$FITB_OVERLAY_DIR/patches/webui" \
            "webui"
    fi

    if [ "$FITB_DISABLE_AGENT_OVERLAY" = "1" ]; then
        _log "FITB_DISABLE_AGENT_OVERLAY=1 — skipping agent patches"
    else
        _apply_patch_series \
            "$FITB_APP_DIR/hermes-agent" \
            "$FITB_OVERLAY_DIR/patches/agent" \
            "agent"
    fi
}

# ── 5. Agent memory plugins ───────────────────────────────────────────────────
_install_memory_plugins() {
    [ "$FITB_DISABLE_AGENT_OVERLAY" = "1" ] && { _log "Skipping memory plugins (overlay disabled)"; return 0; }
    local src="$FITB_OVERLAY_DIR/agent_memory_plugins"
    local target="$FITB_APP_DIR/hermes-agent/plugins/memory"

    [ -d "$src" ] || { _log "No agent_memory_plugins directory — skipping"; return 0; }
    [ -d "$target" ] || _die "hermes-agent missing plugins/memory/ — upstream layout changed?"

    for plugin_src in "$src"/*/; do
        [ -d "$plugin_src" ] || continue
        local name; name=$(basename "$plugin_src")
        _log "Installing memory plugin: $name"
        cp -R "$plugin_src" "$target/"
    done
}

# ── 6. .fox-removals ─────────────────────────────────────────────────────────
_apply_removals() {
    [ "$FITB_DISABLE_WEBUI_OVERLAY" = "1" ] && { _log "Skipping removals (overlay disabled)"; return 0; }
    local manifest="$FITB_OVERLAY_DIR/.fox-removals"
    [ -f "$manifest" ] || { _log "No .fox-removals manifest — skipping"; return 0; }

    local removals
    removals=$(tr -d '\r' < "$manifest" | grep -vE '^\s*$|^\s*#' || true)
    [ -z "$removals" ] && { _log ".fox-removals empty — skipping"; return 0; }

    _log "Applying .fox-removals..."
    local target="$FITB_APP_DIR/hermes-webui"
    echo "$removals" | while IFS= read -r p; do
        [ -z "$p" ] && continue
        if [ -e "$target/$p" ]; then
            _log "  rm $p"
            rm -f -- "$target/$p"
        else
            _log "  (absent — no-op) $p"
        fi
    done
}

# ── 7. SOUL.md ────────────────────────────────────────────────────────────────
_install_soul() {
    [ "$FITB_DISABLE_AGENT_OVERLAY" = "1" ] && { _log "Skipping SOUL.md (overlay disabled)"; return 0; }
    local src="$FITB_OVERLAY_DIR/agent_overlay/SOUL.md"
    local dest="$FITB_APP_DIR/hermes-agent/docker/SOUL.md"

    [ -f "$src" ]  || _die "SOUL.md missing at $src"
    [ -d "$(dirname "$dest")" ] || _die "hermes-agent/docker/ missing — upstream layout changed?"
    cp "$src" "$dest"
    _log "Installed Fox SOUL.md → $dest"
}

# ── 8. pip install ────────────────────────────────────────────────────────────
_pip_install() {
    local pip_cmd

    if [ "$FITB_CONTEXT" = "bare-metal" ]; then
        # Create an isolated venv so Fox doesn't pollute system Python
        local venv="$FITB_APP_DIR/venv"
        if [ ! -f "$venv/bin/pip" ]; then
            local py_bin
            py_bin="$(command -v python3.11 || command -v python3)"
            _log "Creating Python venv at $venv (using $py_bin)..."
            "$py_bin" -m venv "$venv"
        fi
        pip_cmd="$venv/bin/pip"
    else
        # Docker: use system pip (already in the base image, no venv overhead)
        pip_cmd="pip"
    fi

    _log "Installing hermes-agent[anthropic,bedrock,google]..."
    "$pip_cmd" install -e "$FITB_APP_DIR/hermes-agent[anthropic,bedrock,google]" \
        --quiet --no-cache-dir

    _log "Installing hermes-webui..."
    if [ -f "$FITB_APP_DIR/hermes-webui/requirements.txt" ]; then
        "$pip_cmd" install -r "$FITB_APP_DIR/hermes-webui/requirements.txt" \
            --quiet --no-cache-dir
    elif [ -f "$FITB_APP_DIR/hermes-webui/setup.py" ] || \
         grep -q '^\[build-system\]' "$FITB_APP_DIR/hermes-webui/pyproject.toml" 2>/dev/null; then
        "$pip_cmd" install -e "$FITB_APP_DIR/hermes-webui" --quiet --no-cache-dir
    else
        _die "hermes-webui has no requirements.txt, setup.py, or installable pyproject.toml"
    fi

    _log "Installing fox-overlay..."
    "$pip_cmd" install -e "$FITB_OVERLAY_DIR" --quiet --no-cache-dir

    # supervisor: needed in bare-metal (Docker installs it separately)
    if [ "$FITB_CONTEXT" = "bare-metal" ]; then
        _log "Installing supervisor..."
        "$pip_cmd" install supervisor --quiet --no-cache-dir
    fi
}

# ── 9. supervisord.conf (generated — paths substituted) ───────────────────────
_write_supervisord_conf() {
    local app="$FITB_APP_DIR"
    local data="$FITB_DATA_DIR"

    local conf_path
    if [ "$FITB_CONTEXT" = "docker" ]; then
        conf_path="/etc/supervisor/supervisord.conf"
        local sock_path="/run/fitb/supervisor.sock"
        local pid_path="/run/fitb/supervisord.pid"
    else
        conf_path="/etc/foxinthebox/supervisord.conf"
        local sock_path="/run/foxinthebox/supervisor.sock"
        local pid_path="/run/foxinthebox/supervisord.pid"
    fi

    mkdir -p "$(dirname "$conf_path")"
    _log "Writing $conf_path (app=$app, data=$data)..."

    cat > "$conf_path" << SUPERVISORD_EOF
[supervisord]
nodaemon=true
user=root
logfile=${data}/logs/supervisord.log
logfile_maxbytes=10MB
logfile_backups=3
pidfile=${pid_path}
childlogdir=${data}/logs

; Unix socket must NOT live under the data volume: bind-mounting from macOS or
; Windows (Docker Desktop) breaks AF_UNIX bind() with EINVAL.
[unix_http_server]
file=${sock_path}
chmod=0770
chown=foxinthebox:foxinthebox

[supervisorctl]
serverurl=unix://${sock_path}

[rpcinterface:supervisor]
supervisor.rpcinterface_factory = supervisor.rpcinterface:make_main_rpcinterface

; ── tailscaled ────────────────────────────────────────────────────────────────
[program:tailscaled]
command=tailscaled --state=${data}/data/tailscale/tailscaled.state
user=root
autostart=true
autorestart=true
stdout_logfile=${data}/logs/tailscaled.log
stderr_logfile=${data}/logs/tailscaled.err
stdout_logfile_maxbytes=10MB
stdout_logfile_backups=3
stderr_logfile_maxbytes=10MB
stderr_logfile_backups=3
priority=10

; ── tailscale operator watchdog ───────────────────────────────────────────────
[program:ts-operator-watchdog]
command=${app}/scripts/tailscale-operator-watchdog.sh
user=root
autostart=true
autorestart=true
stdout_logfile=${data}/logs/ts-operator-watchdog.log
stderr_logfile=${data}/logs/ts-operator-watchdog.err
stdout_logfile_maxbytes=10MB
stdout_logfile_backups=3
stderr_logfile_maxbytes=10MB
stderr_logfile_backups=3
priority=15

; ── qdrant ────────────────────────────────────────────────────────────────────
[program:qdrant]
command=${app}/qdrant/qdrant --config-path ${data}/config/qdrant.yaml
user=foxinthebox
autostart=true
autorestart=true
stdout_logfile=${data}/logs/qdrant.log
stderr_logfile=${data}/logs/qdrant.err
stdout_logfile_maxbytes=10MB
stdout_logfile_backups=3
stderr_logfile_maxbytes=10MB
stderr_logfile_backups=3
priority=20

; ── hermes gateway ────────────────────────────────────────────────────────────
[program:hermes-gateway]
command=/usr/bin/nice -n 10 ${app}/scripts/run-with-env.sh python -m hermes_cli.main gateway run --replace
user=foxinthebox
autostart=true
autorestart=true
stdout_logfile=${data}/logs/hermes-gateway.log
stderr_logfile=${data}/logs/hermes-gateway.err
stdout_logfile_maxbytes=10MB
stdout_logfile_backups=3
stderr_logfile_maxbytes=10MB
stderr_logfile_backups=3
environment=HOME="${app}",PYTHONPATH="${data}/apps/hermes-agent",PATH="/usr/local/bin:/usr/bin:/bin",HERMES_HOME="${data}/data/hermes",BRAVE_API_KEY="__BRAVE_API_KEY__"
priority=30

; ── hermes webui ──────────────────────────────────────────────────────────────
[program:hermes-webui]
command=${app}/scripts/run-with-env.sh python ${data}/apps/hermes-webui/server.py
user=foxinthebox
autostart=true
autorestart=true
stdout_logfile=${data}/logs/hermes-webui.log
stderr_logfile=${data}/logs/hermes-webui.err
stdout_logfile_maxbytes=10MB
stdout_logfile_backups=3
stderr_logfile_maxbytes=10MB
stderr_logfile_backups=3
environment=HOME="${app}",PYTHONPATH="${data}/apps/hermes-webui",HERMES_WEBUI_HOST="0.0.0.0",HERMES_WEBUI_AGENT_DIR="${data}/apps/hermes-agent",HERMES_WEBUI_STATE_DIR="${data}/state/webui",HERMES_HOME="${data}/data/hermes",ONBOARDING_PATH="${data}/config/onboarding.json",PATH="/usr/local/bin:/usr/bin:/bin"
priority=40

; ── llama-server (local AI fallback — autostart=false) ───────────────────────
[program:llama-server]
command=${app}/llama-cpp/llama-server -m ${data}/models/microsoft_Phi-4-mini-instruct-Q4_K_M.gguf --host 127.0.0.1 --port 8643 -c 4096 -t 4 --sleep-idle-seconds 60
user=foxinthebox
autostart=false
autorestart=true
startretries=2
stdout_logfile=${data}/logs/llama-server.log
stderr_logfile=${data}/logs/llama-server.err
stdout_logfile_maxbytes=10MB
stdout_logfile_backups=3
stderr_logfile_maxbytes=10MB
stderr_logfile_backups=3
priority=50
SUPERVISORD_EOF

    _log "supervisord.conf written."
}

# ── Main ──────────────────────────────────────────────────────────────────────
if [ "$FITB_SKIP_BINARIES" != "1" ]; then
    _install_qdrant
    _install_llama_server
fi

_sync_hermes_repos
_apply_patches
_install_memory_plugins
_apply_removals
_install_soul
_pip_install
_write_supervisord_conf

_log "Fox in the Box install complete (v${FITB_VERSION})."
