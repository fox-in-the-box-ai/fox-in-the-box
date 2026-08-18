# 01 — Current State Audit

Source audit of what the container does today, translated into what a bare-metal installer must replicate.

## System-level dependencies (from Dockerfile)

```
python 3.11 (base image)
curl, ca-certificates, gnupg, git, lsb-release
iproute2, iptables          ← networking stack (Tailscale)
libgomp1, libcurl4          ← llama-server runtime deps
nodejs (LTS via nodesource)  ← npx-based MCP servers
tailscale                   ← from pkgs.tailscale.com apt repo
supervisor (pip)            ← process manager
```

All available as apt packages on Ubuntu 22.04 / 24.04. No exotic deps.

## Binary downloads (arch-aware)

| Binary | Source | Version pinned |
|--------|--------|----------------|
| `qdrant` | github.com/qdrant/qdrant releases | `QDRANT_VERSION=v1.9.4` |
| `llama-server` | github.com/ggml-org/llama.cpp releases | `LLAMACPP_VERSION=b9026` |

Arch detection: `TARGETARCH` → `aarch64` (arm64) or `x86_64` (amd64).
On a host, use `uname -m` instead.

## Python packages installed

```bash
pip install -e '/app/hermes-agent[anthropic,bedrock,google]'
pip install -e /app/hermes-webui   # or requirements.txt fallback
pip install -e /app/fox-overlay
```

## Patch series application (the complex part)

Two series applied at build time via `git apply`:

1. **webui patches** — `packages/fox-overlay/patches/webui/` + `series` file
2. **agent patches** — `packages/fox-overlay/patches/agent/` + `series` file

Each patch validated with `git apply --check` first. Failures are hard errors.
Requires a `git` binary and the target directory to NOT have a `.git` gitlink
(deleted before applying — already handled).

## File-system layout (container → host mapping)

| Container path | Purpose | Host equivalent |
|----------------|---------|-----------------|
| `/app/` | Read-only app root (baked at build time) | `/opt/foxinthebox/` |
| `/data/` | Volume — user state, configs, logs, models | `~/.foxinthebox/` |
| `/app/hermes-agent` | Patched hermes-agent source | `/opt/foxinthebox/hermes-agent` |
| `/app/hermes-webui` | Patched hermes-webui source | `/opt/foxinthebox/hermes-webui` |
| `/app/fox-overlay` | Fox overlay package | `/opt/foxinthebox/fox-overlay` |
| `/app/qdrant/qdrant` | Qdrant binary | `/opt/foxinthebox/qdrant/qdrant` |
| `/app/llama-cpp/llama-server` | llama-server binary | `/opt/foxinthebox/llama-cpp/llama-server` |
| `/app/scripts/` | Runtime helper scripts | `/opt/foxinthebox/scripts/` |
| `/app/defaults/` | Default config files | `/opt/foxinthebox/defaults/` |
| `/app/version.txt` | Version string | `/opt/foxinthebox/version.txt` |

## Runtime: supervisord

`/etc/supervisor/supervisord.conf` manages 5 programs:

| Program | Command | Priority | autostart |
|---------|---------|----------|-----------|
| tailscaled | `tailscaled --state=/data/data/tailscale/tailscaled.state` | 10 | true |
| ts-operator-watchdog | `/app/scripts/tailscale-operator-watchdog.sh` | 15 | true |
| qdrant | `/app/qdrant/qdrant --config-path /data/config/qdrant.yaml` | 20 | true |
| hermes-gateway | `nice -n 10 ... python -m hermes_cli.main gateway run --replace` | 30 | true |
| hermes-webui | `python /data/apps/hermes-webui/server.py` | 40 | true |
| llama-server | (llama-server binary) | 50 | **false** (on-demand) |

Supervisord socket lives at `/run/fitb/supervisor.sock` (tmpfs — important: NOT under `/data`).

## Entrypoint logic (entrypoint.sh — 295 lines)

Key sections to replicate in bare-metal postinst + runtime:

1. **First-run detection** — if no `$DATA/config/onboarding.json`, bootstrap directory tree and seed default configs from `/app/defaults/`
2. **App symlink management** — links `/data/apps/hermes-{agent,webui}` → `/app/hermes-{agent,webui}`
3. **Version migration** — runs scripts from `/app/scripts/migrations/` for version bumps
4. **Tailscale Serve setup** — configures HTTPS proxy from Tailscale → port 8787
5. **supervisord handoff** — `exec supervisord -c /etc/supervisor/supervisord.conf`

Steps 1, 3, 4 need to run on every start (not just install). In bare-metal: these live in a `ExecStartPre=` script called by the systemd unit.

## Existing systemd units (packages/scripts/)

- `foxinthebox.service` — starts the Docker container (needs rewrite for bare-metal)
- `foxinthebox-updater.service` — one-shot: `docker pull` + restart
- `foxinthebox-updater.path` — watches `$DATA/update.trigger` sentinel file

The updater path/service pattern is **reusable** — for bare-metal, `foxinthebox-updater.service` runs `apt-get install --only-upgrade foxinthebox` instead of `docker pull`.

## Environment variables wired in supervisord

### hermes-gateway
```
HOME=/app
PYTHONPATH=/data/apps/hermes-agent
PATH=/usr/local/bin:/usr/bin:/bin
HERMES_HOME=/data/data/hermes
BRAVE_API_KEY=__BRAVE_API_KEY__  (sentinel replaced at first-run)
```

### hermes-webui
```
HOME=/app
PYTHONPATH=/data/apps/hermes-webui
HERMES_WEBUI_HOST=0.0.0.0
HERMES_WEBUI_AGENT_DIR=/data/apps/hermes-agent
HERMES_WEBUI_STATE_DIR=/data/state/webui
HERMES_HOME=/data/data/hermes
ONBOARDING_PATH=/data/config/onboarding.json
PATH=/usr/local/bin:/usr/bin:/bin
```

In bare-metal all `/app` references become `/opt/foxinthebox` and `/data` stays `~/.foxinthebox`.
The supervisord config is generated during install (path substitution), not hardcoded.

## What the .deb does NOT need to replicate

- Docker networking flags (`--cap-add=NET_ADMIN`, `--device /dev/net/tun`) — Tailscale on the host system handles this natively
- `/.within_container` marker file — not needed on bare-metal
- `FITB_DEV` bind-mount logic — dev mode handled separately
- The `foxinthebox` Linux user — `.deb` creates it via `adduser` in postinst
