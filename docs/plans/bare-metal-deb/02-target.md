# 02 — Target Architecture

## Overview

```
┌────────────────────────────────────────────────────────────────┐
│  packages/                                                      │
│  ├── install-core/                                             │
│  │   └── install-core.sh   ← SINGLE SOURCE OF TRUTH           │
│  │       • downloads qdrant + llama-server binaries            │
│  │       • clones hermes-agent + hermes-webui (or uses COPY'd) │
│  │       • applies fox-overlay patch series                    │
│  │       • pip installs hermes-agent + webui + fox-overlay     │
│  │       • writes supervisord.conf (path-parameterized)        │
│  │       • writes systemd units (path-parameterized)           │
│  │                                                              │
│  ├── integration/                                              │
│  │   └── Dockerfile        ← thin consumer of install-core.sh  │
│  │       COPY install-core.sh → RUN ./install-core.sh          │
│  │                                                              │
│  └── deb/                                                      │
│      ├── control            ← package metadata, depends        │
│      ├── postinst           ← calls install-core.sh after unpack│
│      ├── postrm             ← purge: rm /opt/foxinthebox        │
│      ├── conffiles          ← /etc/foxinthebox/ is user-owned   │
│      └── foxinthebox.service (path-substituted)                │
└────────────────────────────────────────────────────────────────┘

                         ▼ CI builds .deb ▼

┌────────────────────────────────────────────────────────────────┐
│  apt.foxinthebox.ai  (Cloudflare R2 + reprepro)                │
│                                                                  │
│  dists/stable/main/binary-amd64/  Packages.gz                  │
│  dists/stable/main/binary-arm64/  Packages.gz                  │
│  pool/main/f/foxinthebox/                                       │
│    foxinthebox_0.8.0_amd64.deb                                  │
│    foxinthebox_0.8.0_arm64.deb                                  │
└────────────────────────────────────────────────────────────────┘

User experience:
  curl -fsSL https://apt.foxinthebox.ai/gpg | sudo gpg --dearmor \
    -o /usr/share/keyrings/foxinthebox.gpg
  echo "deb [signed-by=...] https://apt.foxinthebox.ai stable main" \
    | sudo tee /etc/apt/sources.list.d/foxinthebox.list
  sudo apt update && sudo apt install foxinthebox
  # → Fox is running at http://localhost:8787
```

## Path mapping: container vs bare-metal

| Container | Bare-metal | Notes |
|-----------|-----------|-------|
| `/app/` | `/opt/foxinthebox/` | System-owned, root-written at install |
| `/data/` | `~/.foxinthebox/` | User-owned, persists across upgrades |
| `/etc/supervisor/supervisord.conf` | `/etc/foxinthebox/supervisord.conf` | conffiles — upgrades don't overwrite |
| `/run/fitb/` | `/run/foxinthebox/` | tmpfs — created by systemd RuntimeDirectory |
| `foxinthebox` user | `foxinthebox` system user (uid 999) | created by postinst |

## Systemd unit design (bare-metal)

### foxinthebox.service
```ini
[Unit]
Description=Fox in the Box
After=network-online.target tailscaled.service
Wants=network-online.target

[Service]
Type=forking
User=foxinthebox
RuntimeDirectory=foxinthebox
RuntimeDirectoryMode=0770

# Pre-start: first-run bootstrap + migrations + Tailscale Serve setup
ExecStartPre=/opt/foxinthebox/scripts/preflight.sh

# Start supervisord as the process manager
ExecStart=/usr/bin/supervisord -c /etc/foxinthebox/supervisord.conf \
    --pidfile /run/foxinthebox/supervisord.pid \
    --nodaemon

Restart=on-failure
RestartSec=10s

[Install]
WantedBy=multi-user.target
```

### foxinthebox-updater.service (one-shot)
```ini
[Service]
Type=oneshot
ExecStart=/bin/bash -c 'apt-get install --only-upgrade -y foxinthebox && \
  systemctl restart foxinthebox && \
  rm -f $HOME/.foxinthebox/update.trigger'
```

The `.path` unit watching `update.trigger` is identical to the existing one — the trigger file path stays the same, only the update command changes.

## install-core.sh parameters

All paths are passed as environment variables with sane defaults:

```bash
FITB_APP_DIR="${FITB_APP_DIR:-/opt/foxinthebox}"   # where binaries/code live
FITB_DATA_DIR="${FITB_DATA_DIR:-$HOME/.foxinthebox}" # user state
FITB_VERSION="${FITB_VERSION:-}"                    # read from VERSION if unset
FITB_SKIP_BINARIES="${FITB_SKIP_BINARIES:-0}"       # 1 = skip qdrant/llama download (CI cache)
QDRANT_VERSION="${QDRANT_VERSION:-v1.9.4}"
LLAMACPP_VERSION="${LLAMACPP_VERSION:-b9026}"
```

When called from the Dockerfile:
```dockerfile
ENV FITB_APP_DIR=/app
COPY packages/install-core/install-core.sh /tmp/install-core.sh
RUN FITB_APP_DIR=/app bash /tmp/install-core.sh
```

When called from `.deb` postinst:
```bash
FITB_APP_DIR=/opt/foxinthebox bash /opt/foxinthebox/install-core.sh
```

## Update story for users

```
Docker path:   docker pull → container restart (unchanged)
.deb path:     apt upgrade foxinthebox → postinst runs install-core.sh
                 → binaries re-downloaded if version changed
                 → patch series re-applied to fresh clone of pinned upstream tags
                 → supervisorctl reload (no full restart needed for config-only changes)
```

## What is NOT in scope

- Windows / macOS bare-metal (Docker/Electron path stays for those)
- RPM / Arch packages (can layer on later; same install-core.sh)
- GUI installer (Zorin users are comfortable with apt; fancy GUI is YAGNI)
