# Fox in the Box — Requirements & Architecture Document

**Version:** 0.2.0 (Draft)
**Date:** April 28, 2026
**Status:** Design Phase — No code written yet

---

## 1. Project Overview

### 1.1 What Is Fox in the Box?

Fox in the Box is an all-in-one, self-hosted AI assistant platform packaged as a single Docker container with native desktop apps (Electron) for Windows and macOS. It bundles a curated, tested, and stable set of open-source AI tools into a "works out of the box" experience for non-technical users.

### 1.2 Brand Guidelines

- **Product name (logos, UI):** lowercase "fox in the box"
- **Marketing copy:** sentence case "Fox in the box"
- **Parent brand:** fox in the box (fox in the box)
- **Domain:** `foxinthebox.io`
- **Tagline concept:** "AI Fox who simply works. For everyone."
- **Visual identity:** Fox character, container/box metaphor
- **GitHub Org:** `fox-in-the-box-ai`
- **Container image:** `ghcr.io/fox-in-the-box-ai/cloud:stable`

### 1.3 Core Philosophy

1. **Works out of the box** — One command to start, web-based onboarding for configuration
2. **Package stability over bleeding edge** — Bimonthly tested releases, not nightly
3. **Open source from day 1** — MIT licensed, forkable, community-friendly
4. **Non-technical user first** — No terminal required for end users
5. **AI fox works in the box, you live outside** — Clear separation of system and user space

---

## 2. Components

### 2.1 Included Components

| Component | Purpose | License | Data Storage |
|-----------|---------|---------|-------------|
| **Hermes Agent** | AI agent core (LLM orchestration, tools, gateway) | MIT | SQLite (sessions) |
| **Hermes WebUI** | Browser-based chat interface | MIT | None (stateless) |
| **mem0_oss** | Persistent memory (Qdrant vector DB) | Apache 2.0 | Qdrant files |
| **Memos** | Notes/knowledge management app | Apache 2.0 | SQLite | *(post-MVP, v0.2+)* |
| **Tailscale** | VPN, HTTPS, reverse proxy via Serve | Free tier | State files |

### 2.2 Excluded Components

| Component | Reason |
|-----------|--------|
| **PostgreSQL** | Too heavy for "out of the box" philosophy. All components use SQLite or embedded storage |
| **nginx** | Tailscale Serve provides HTTPS termination and path-based routing. No reverse proxy needed |
| **Blinko** | Requires PostgreSQL. Replaced by Memos (SQLite) |
| **Open WebUI** | Replaced by customized Hermes WebUI fork |

### 2.3 Component Communication

```
┌─────────────────────────────────────────────────┐
│ Single Docker Container                         │
│                                                 │
│  ┌───────────┐    ┌──────────────┐              │
│  │ Hermes    │◄──►│ Hermes Agent │              │
│  │ WebUI     │    │ (Gateway+API)│              │
│  │ :8787     │    │              │              │
│  └───────────┘    └──────┬───────┘              │
│                          │                      │
│  ┌───────────┐    ┌──────┴───────┐              │
│  │ Memos     │    │ mem0_oss     │              │
│  │ :5230     │    │ (Qdrant)     │              │
│  └───────────┘    │ :6333        │              │
│                   └──────────────┘              │
│                                                 │
│  ┌─────────────────────────────────┐            │
│  │ Tailscale (VPN + Serve proxy)   │            │
│  │ Exposes HTTPS to tailnet        │            │
│  └─────────────────────────────────┘            │
│                                                 │
│  ┌─────────────────────────────────┐            │
│  │ supervisord (process manager)   │            │
│  └─────────────────────────────────┘            │
└─────────────────────────────────────────────────┘
```

### 2.4 Tailscale Serve Routing

Tailscale Serve replaces nginx for all external access:

```bash
# HTTPS routing (auto-managed by entrypoint)
tailscale serve --bg /          http://localhost:8787    # WebUI
# tailscale serve --bg /memos   http://localhost:5230    # Notes — OUT-OF-MVP (v0.2+)
# Internal only (not exposed via Serve):
# mem0 Qdrant: localhost:6333
# Hermes API: localhost:8642
```

Result: `https://[machine-name].tailnet.ts.net` → WebUI with valid HTTPS certificate, zero configuration.

---

## 3. Architecture

### 3.1 Container Strategy

**Decision: Single container (v1) with migration path to Docker Compose (v2+)**

**Rationale:**
- Electron desktop apps need to manage one container, not N services
- "Works out of the box" = one `docker run` command
- Simpler error handling and debugging for end users

**Future Migration:**
- Design data structure identically for both single and compose

---

### 3.2 App Code Strategy — Git-in-volume model

**Decision: Python app code (Hermes Agent, Hermes WebUI) lives on the persistent volume as git repos, not baked into the image.**

```
~/.foxinthebox/
├── apps/                        ← cloned at install time, updated via git pull
│   ├── hermes-agent/            ← git clone fox-in-the-box-ai/hermes-agent@v0.1.0
│   └── hermes-webui/            ← git clone fox-in-the-box-ai/hermes-webui@v0.1.0
├── config/
├── data/
└── logs/
```

**How updates work:**
1. User clicks "Check for updates" in WebUI (or update sentinel file is touched)
2. Container runs `git fetch && git checkout vX.Y.Z` in each app directory
3. `pip install -e` is re-run if `requirements.txt` changed
4. supervisord restarts only the affected programs — no image pull, no container restart

**Why this is better than baking code into the image:**
- Image becomes thin and stable — only needs rebuilding when system deps change (Qdrant, Tailscale, OS packages)
- Updates are fast (seconds, not minutes), don't require Docker, and never interrupt Tailscale state
- Every install is auditable: `git log -1 HEAD` gives exact commit; `git status` shows any local modifications
- Rollback is `git checkout v0.1.2` + supervisorctl restart — no pulling a previous image
- Developers can edit code in `~/.foxinthebox/apps/` and restart services to test changes instantly
- Code integrity check: `git fsck && git status --porcelain` inside the container

**Security considerations:**
- Updates pull by **tag**, not branch (`git checkout v0.1.3`, not `git pull origin stable`) — a compromised push to `stable` doesn't affect users until a new verified tag is cut
- `pip install --no-deps` + pinned `requirements.txt` prevents transitive dependency surprises
- All app code runs as the `foxinthebox` non-root user — blast radius is contained within the container
- No new host-escape risk vs. current architecture; `--cap-add=NET_ADMIN` is the actual boundary

**Dockerfile implications:**
The image contains only:
- OS system packages (curl, git, ca-certificates, iproute2, iptables)
- Tailscale (apt package)
- Qdrant binary
- supervisord (pip)
- entrypoint.sh + supervisord.conf + default-configs

`hermes-agent` and `hermes-webui` are **NOT** installed in the image. The entrypoint clones them on first run if absent.

**entrypoint.sh app-bootstrap logic (first run):**
```bash
APPS_DIR="/data/apps"
for APP in hermes-agent hermes-webui; do
  if [ ! -d "$APPS_DIR/$APP/.git" ]; then
    # Remove any partial clone before retrying
    rm -rf "$APPS_DIR/$APP"
    git clone --depth 1 \
      --branch "$FITB_VERSION" \
      "https://github.com/fox-in-the-box-ai/$APP" \
      "$APPS_DIR/$APP"
    pip install -e "$APPS_DIR/$APP" --quiet
  fi
done
```

**supervisord command paths point into /data/apps:**
```ini
[program:hermes-gateway]
command=python -m hermes_cli.main gateway run --replace
environment=PYTHONPATH="/data/apps/hermes-agent",HOME="/app",...

[program:hermes-webui]
command=python /data/apps/hermes-webui/server.py
environment=PYTHONPATH="/data/apps/hermes-webui",HOME="/app",...
```
- Provide migration script when compose version ships
- Compose offered as "advanced mode" for power users

---

### 3.3 UI Build Strategy — Multi-stage Dockerfile

**Decision: React UI is built inside a Docker multi-stage build; no Node.js tooling required on the user's machine.**

This applies starting **v0.2** when the onboarding wizard (and any future React UI) moves from plain HTML to React. For v0.1, the wizard is plain HTML/JS — no build step needed.

**Pattern:**

```dockerfile
# ── Stage 1: build the React UI ───────────────────────────────────────────────
FROM node:20-slim AS ui-builder
WORKDIR /build
# Only copy the specific package being built to maximise layer cache hits
COPY packages/onboarding-wizard/package.json packages/onboarding-wizard/pnpm-lock.yaml ./
RUN npm install -g pnpm && pnpm install --frozen-lockfile
COPY packages/onboarding-wizard/ .
RUN pnpm build
# Output: /build/dist/

# ── Stage 2: runtime image ────────────────────────────────────────────────────
FROM python:3.11-slim AS final
# ... (existing Dockerfile contents) ...
COPY --from=ui-builder /build/dist/ /app/ui/
# Hermes WebUI serves /app/ui/ at /setup
```

**Key properties:**
- `node_modules` and build toolchain are in the builder stage and **never land in the final image**
- `dist/` is gitignored — it lives only in CI artifacts and the container image
- CI builds the full image (which runs both stages) → pushes to `ghcr.io/fox-in-the-box-ai/cloud:stable`
- The builder stage is cached independently; a Python-only change skips the Node build entirely

**Why not git-in-volume for the UI?**

| | Python apps (Hermes) | React UI |
|---|---|---|
| Update mechanism | `git pull` + `pip install -e` | Full image rebuild |
| Reason | Config files & API keys on volume; devs iterate rapidly | Static build artifact; no runtime state; version must match Python backend exactly |
| Volume? | ✅ `/data/apps/` | ❌ baked into image at `/app/ui/` |

The React UI is a build artifact tied tightly to the Python backend version — it should change only when the image is released. Keeping it in the image eliminates the risk of a stale UI calling an incompatible backend API.

**Serving:**
The existing Hermes WebUI server (Python) serves static files from `/app/ui/` at the `/setup` route — no nginx required. Add a `StaticFiles` mount or equivalent route in the WebUI server for v0.2.

**v0.1 note:** Task 03 Dockerfile currently has no `ui-builder` stage. When React migration happens in v0.2, add the stage before `FROM python:3.11-slim AS final` and add `COPY --from=ui-builder /build/dist/ /app/ui/` to the final stage.

---

### 3.4 Process Management

**supervisord** manages all processes inside the container:

> **Note:** Hermes app code lives on the volume (`/data/apps/`), not baked into the image — see §3.2. Command paths below reflect this.

```ini
[program:hermes-gateway]
command=python -m hermes_cli.main gateway run --replace
environment=PYTHONPATH="/data/apps/hermes-agent",HOME="/app"

[program:hermes-webui]
command=python /data/apps/hermes-webui/server.py
environment=PYTHONPATH="/data/apps/hermes-webui",HOME="/app"

[program:qdrant]
command=/app/qdrant/qdrant --storage-path /data/data/mem0

; [program:memos]  ← OUT-OF-MVP (v0.2+)
; command=/app/memos/memos --data /data/data/memos

[program:tailscaled]
command=tailscaled --state=/data/data/tailscale/tailscaled.state
```

### 3.5 Electron Desktop App

Native desktop app for **Windows** (`.exe` on GitHub Releases). **macOS** uses the same **`install.sh` + Docker** flow as Linux (documented in the README); there is no signed `.dmg` in releases. Developers may build an **unsigned** macOS `.zip` locally with Electron Builder.

**Responsibilities:**
- Detect Docker Desktop, silently install if missing
- Start/stop the single container
- Auto-update container image
- OS-native system tray icon
- Open WebUI in default browser or embedded webview
- Expose Electron Bridge API to WebUI for host-level actions
- Handle OAuth redirect flows (desktop context)

**Docker silent install (per platform):**
| Platform | Method |
|----------|--------|
| Windows | `winget install Docker.DockerDesktop` or MSI silent flags |
| macOS | `brew install --cask docker` or pkg silent install |

**Installer:** Electron Builder for MVP. Custom branded installer post-MVP.

**Auto-update flow:**
```
1. Check for new image tag on Docker Hub
2. Notify user via system tray: "Update available"
3. User confirms
4. Pull new image in background (progress shown)
5. Stop container → Remove old → Start new
6. Data volume unchanged
7. Browser reconnects automatically
```

**Container lifecycle:**
```javascript
// Electron manages one container
docker.pull('foxinthebox/cloud:stable')
// app.getPath('userData') resolves to the OS-appropriate path automatically:
// Windows: %APPDATA%\Fox in the Box
// macOS:   ~/Library/Application Support/Fox in the Box
// Linux:   ~/.config/Fox in the Box  (or FOX_DATA_DIR env override)
// See REQUIREMENTS.md §4.2 for the full platform defaults table.
const DATA_DIR = process.env.FOX_DATA_DIR || app.getPath('userData');

docker.run({
  image: 'ghcr.io/fox-in-the-box-ai/cloud:stable',
  name: 'fox-in-the-box',
  volumes: [`${DATA_DIR}:/data`],
  capAdd: ['NET_ADMIN'],        // Required for Tailscale
  sysctl: {'net.ipv4.ip_forward': 1},
  ports: ['127.0.0.1:8787:8787']  // localhost only on desktop
})
```

### 3.6 Electron Bridge API

The Electron Bridge is a **host-level IPC interface** exposed only to the WebUI renderer via Electron's `contextBridge`. It is **not a TCP port** — the container cannot reach it.

**Purpose:** Allows the onboarding wizard (running in browser) to trigger host-level actions (install software, download models, manage Docker) without exposing those capabilities to the AI agent.

**Security model:**
- Bridge is Electron IPC only — zero network exposure
- Container has no access to bridge whatsoever
- Every privileged action requires explicit user confirmation
- Actions are an enum allowlist — no arbitrary shell execution
- All actions logged to audit trail
- Action tokens are short-lived (30s expiry)
- Strict CSP on WebUI prevents XSS → bridge escalation

**Available actions (allowlist):**
```javascript
const ALLOWED_ACTIONS = [
  'system.info',          // Read-only: RAM, GPU, disk
  'docker.status',        // Read-only
  'ollama.status',        // Read-only
  'models.list',          // Read-only
  'models.download',      // Requires user confirmation
  'ollama.install',       // Requires confirmation + elevation
  'tailscale.login',      // Requires confirmation
]
// No shell exec, no arbitrary commands, no filesystem access
```

**Fallback (server/browser context):**
When WebUI runs outside Electron, bridge calls gracefully degrade — wizard shows manual instructions instead of install buttons.

```javascript
const context = {
  isElectron: !!window.electronBridge,
  hasBridge: !!window.electronBridge?.install,
}
// Desktop → "Installing Ollama..." (silent via bridge)
// Server  → "Run: curl -fsSL https://ollama.com/install.sh | sh"
```

### 3.7 Server Deployment

For Linux server users, Electron is not available. Deployment is via install script.

**Install script (`install.sh`):**
```bash
curl -fsSL https://foxinthebox.io/install.sh | bash
```

**Script flow:**
```
1. Check/install Docker (get.docker.com if missing)
2. Prompt: "How do you want to access Fox?"
   [1] Port only   (http://your-ip:8787)
   [2] Tailscale   (https://fox.tailnet.ts.net)
   [3] Both
3. Pull container image
4. If Tailscale selected:
   - Start container
   - Stream logs → extract Tailscale login URL
   - Display URL + QR code in terminal
   - Wait for authentication
   - Show Tailscale URL on success
5. Install systemd units (foxinthebox + foxinthebox-updater)
6. Enable autostart: systemctl enable foxinthebox
7. Print access URL
8. Warn about firewall if port mode selected
```

**Port binding:**
- **Desktop (Electron):** `127.0.0.1:8787` — localhost only, Electron manages access
- **Server (port mode):** `0.0.0.0:8787` — all interfaces, user responsible for firewall
- **Server (Tailscale only):** No port exposed after Tailscale confirmed working

**Security warning (server port mode):**
```
⚠️  Fox is accessible at http://0.0.0.0:8787
    Ensure your firewall restricts access to trusted IPs.
    Consider Tailscale for private encrypted access.
```

### 3.8 Server Auto-Boot & Updates

Two systemd units installed by `install.sh`:

```ini
# /etc/systemd/system/foxinthebox.service
# __DATA_DIR__ is substituted by install.sh with the OS-specific app data path
# (e.g. ~/.foxinthebox on Linux — see REQUIREMENTS.md §4.2)
[Unit]
Description=Fox in the Box
After=docker.service
Requires=docker.service

[Service]
Restart=always
ExecStart=docker run --rm --name fox-in-the-box \
  --cap-add=NET_ADMIN \
  --device /dev/net/tun \
  -v __DATA_DIR__:/data \
  -p 8787:8787 \
  foxinthebox/cloud:stable
ExecStop=docker stop fox-in-the-box

[Install]
WantedBy=multi-user.target
```

```ini
# /etc/systemd/system/foxinthebox-updater.service
# Triggered by sentinel file written by WebUI update button
[Service]
Type=oneshot
ExecStart=/usr/local/bin/foxinthebox-update.sh
# Script: docker pull → systemctl restart foxinthebox
```

**Update flow (server):**
```
User clicks "Update" in WebUI
    ↓
WebUI backend writes /data/update.trigger sentinel file
    ↓
foxinthebox-updater.path unit detects file
    ↓
Pulls new image → restarts container
    ↓
Browser reconnects automatically
```

**Rollback:** Post-MVP feature.

---

## 4. Data Storage & Persistence

### 4.1 Design Principles

1. **All user data AND app code lives outside the container** in a single volume mount
2. **Container is stateless and thin** — only system deps, binaries, supervisord; can be destroyed and recreated without losing anything
3. **Data structure identical** for single container and future compose migration
4. **Configs never overwritten** on container upgrade
5. **OS-specific workspace defaults** for user files
6. **App code is git repos on the volume** — updates via git, auditable, rollback-able, developer-friendly

### 4.2 Platform Default Paths

Two distinct directory types exist. They are **always separate** — never nested inside each other.

#### App data directory (bind-mounted as `/data` inside the container)

Holds app code repos, config, runtime data, logs, and cache.
The container never sees the host filesystem except through this mount.

| OS | Default path | Set via |
|----|-------------|---------|
| **Linux** | `~/.foxinthebox` | `$FOX_DATA_DIR` env var or install.sh prompt |
| **macOS** | `~/Library/Application Support/Fox in the Box` | same |
| **Windows** | `%APPDATA%\Fox in the Box` | Electron `app.getPath('userData')` |

> **Why different paths per OS?**
> macOS discourages hidden dot-dirs in `~` since Catalina. Windows has a
> dedicated `%APPDATA%` convention. Linux users expect dot-dirs. Electron's
> `app.getPath('userData')` already returns the correct OS-native path — the
> Electron app and install script must use the same value so data persists
> if a user switches from one to the other.

#### Workspace directory (user documents — never mounted into the container)

The fox character works *inside the box*; user files live *outside*.
This directory is for the user's own projects, documents, and outputs
that Fox in the Box helps with. It is **never bind-mounted into the container**
by default — only shared explicitly by the user if they choose to.

| OS | Default path |
|----|-------------|
| **Linux** | `~/Fox in the Box` |
| **macOS** | `~/Documents/Fox in the Box` |
| **Windows** | `Documents\Fox in the Box` (i.e. `%USERPROFILE%\Documents\Fox in the Box`) |

> **Separation rule:** `APP_DATA_DIR` ≠ `WORKSPACE_DIR`. Code, config, and
> runtime data go in the app data dir. User documents and project files go
> in the workspace dir. The install script creates both and prints both paths
> clearly at the end.

---

### 4.3 App Data Directory Structure

The app data directory is bind-mounted as `/data` inside the container.
All paths below are relative to the OS-specific default from §4.2.

```
<APP_DATA_DIR>/                     # e.g. ~/.foxinthebox on Linux
│                                   # Bind-mounted as /data in container
│
├── apps/                           # ── REPOS ─────────────────────────────
│   │                               # Git repos — cloned at first run,
│   │                               # updated via git checkout vX.Y.Z
│   ├── hermes-agent/              # fox-in-the-box-ai/hermes-agent
│   └── hermes-webui/              # fox-in-the-box-ai/hermes-webui
│
├── config/                         # ── CONFIG ────────────────────────────
│   │                               # User settings — NEVER overwritten
│   ├── hermes.yaml                #   Hermes Agent configuration
│   ├── hermes.env                 #   API keys and secrets
│   ├── mem0.toml                  #   Memory provider config
│   └── onboarding.json           #   Wizard completion state
│
├── data/                           # ── RUNTIME DATA ──────────────────────
│   │                               # Application state — survives upgrades
│   ├── hermes/
│   │   ├── sessions/             #   Chat session transcripts
│   │   └── skills/               #   Installed skills
│   ├── mem0/
│   │   └── qdrant/              #   Vector DB files (version-sensitive)
│   └── tailscale/
│       └── tailscaled.state    #   Tailscale node identity (root-owned)
│
├── cache/                          # ── CACHE ─────────────────────────────
│   │                               # Can be safely deleted
│   ├── models/                  #   Downloaded STT/TTS models
│   └── embeddings/             #   Cached embeddings
│
└── version.txt                     # Data format version (migration marker)
```

### 4.4 Workspace Directory Structure

The workspace directory lives on the **host only** — never mounted into the container.
It is the user's personal working area; Fox in the Box reads/writes it only
when the user explicitly shares a file or folder.

```
<WORKSPACE_DIR>/                    # e.g. ~/Fox in the Box on Linux
│                                   # NOT mounted into container
│
├── projects/                       # User's AI-assisted projects
├── exports/                        # Files exported from Fox (summaries, etc.)
└── uploads/                        # Files staged for sharing with Fox
```

> Created by install.sh on first run. Contents are the user's own files —
> no Fox in the Box code or config ever lives here.

**Configuration:**
```bash
# User can override via environment variable
docker run -e FOXINTHEBOX_WORKSPACE=/custom/path ...

# Or set in onboarding wizard
# Stored in /data/config/onboarding.json
```

**Mount in container:**
```bash
docker run \
  -v ~/.foxinthebox:/data \
  -v ~/Documents/Fox\ in\ the\ Box:/workspace \
  foxinthebox/cloud:stable
```

### 4.5 Configuration Hierarchy

```
Priority (highest → lowest):
1. Environment variables     # Power users, CI, secrets override
2. /data/config/             # User config — written by wizard, persists upgrades
3. /app/defaults/            # Container baked-in defaults — never written to user volume
```

| Config Type | Location | Env Var Override |
|-------------|----------|-----------------|
| API keys / secrets | `/data/config/hermes.env` | Yes (`-e OPENROUTER_KEY=...`) |
| App settings | `/data/config/hermes.yaml` | Yes (simple values) |
| Service ports / internals | `/app/defaults/` only | Yes |
| Onboarding state | `/data/config/onboarding.json` | No |

### 4.6 Ollama Integration

Ollama always runs on the **host machine**, never inside the container. Models are 4-30GB — too large for a container image.

```
Host machine
├── Ollama service (host-installed)
│   ├── API: localhost:11434
│   └── Models: ~/models/ (host storage)
│
└── Fox container
    └── Connects via host gateway
        ├── Linux:      host-gateway:11434
        └── Mac/Win:    host.docker.internal:11434
```

**Docker run flag:**
```bash
docker run \
  --add-host=host-gateway:host-gateway \
  -e OLLAMA_HOST=http://host-gateway:11434 \
  foxinthebox/cloud:stable
```

**install.sh behaviour:**
```
Check if Ollama already running on host
  → Yes: configure Fox to connect, skip install
  → No:  prompt "Install Ollama? [Y/n]"
           Y → curl install + start service
           N → skip, configurable later in wizard
```

**Onboarding wizard:**
- Polls `$OLLAMA_HOST/api/tags` to detect Ollama
- Shows model selector if connected
- Shows install instructions if not found

### 4.4 Container Entrypoint Logic *(summary — authoritative spec is Task 04)*

```bash
# 1. Check if first run
if [ ! -f /data/config/onboarding.json ]; then
    # Copy default configs (templates)
    cp /app/defaults/* /data/config/
    # Mark as needing onboarding
    echo '{"completed": false}' > /data/config/onboarding.json
fi

# 2. Check version for migrations
CURRENT=$(cat /data/version.txt 2>/dev/null || echo "0.0.0")
LATEST=$(cat /app/version.txt)
if [ "$CURRENT" != "$LATEST" ]; then
    /app/scripts/migrate.sh "$CURRENT" "$LATEST"
    echo "$LATEST" > /data/version.txt
fi

# 3. Fix permissions
chown -R foxinthebox:foxinthebox /data

# 4. Start services
exec supervisord -c /etc/supervisord.conf
```

---

## 5. Database Migrations

### 5.1 Strategy

Components handle their own migrations where possible:

| Component | Migration Approach |
|-----------|-------------------|
| **Hermes Agent** | Built-in session migration system |
| **Memos** | SQLite schema migrations (built-in) |
| **Qdrant** | Handles data format upgrades internally |
| **Fox-specific** | Version-gated scripts in `/app/scripts/migrate.sh` |

### 5.2 Migration Script Pattern

```bash
#!/bin/bash
# /app/scripts/migrate.sh <from_version> <to_version>

FROM=$1
TO=$2

# Backup before migration
cp -r /data/data /data/data.backup.$FROM

# Run component migrations
python -m hermes_cli.migrate --data-dir /data/data/hermes 2>/dev/null || true
# Memos migration — OUT-OF-MVP (v0.2+); guard with version check when enabling
# /app/memos/memos migrate --data /data/data/memos 2>/dev/null || true

# Run fox-specific migrations
for script in /app/scripts/migrations/${FROM}-to-*.sh; do
    [ -f "$script" ] && bash "$script"
done
```

### 5.3 Versioning

- Data format version stored in `/data/version.txt`
- Follows container release tags (e.g., `v0.1.0`, `v0.2.0`)
- Migration scripts named: `v0.1.0-to-v0.2.0.sh`
- Bimonthly releases reduce migration frequency

---

## 6. Onboarding Flow

> **⚠️ v0.1 MVP scope:** The v0.1 onboarding wizard is a **plain HTML/JS**
> 4-step implementation (see ROADMAP.md §v0.1). The React + Python architecture,
> 8-step flow, OAuth PKCE, and Memos step described below are **post-MVP** (v0.2+).
> Task 05a/05b implement the plain HTML/JS wizard. Do not use this section as
> implementation guidance for v0.1.

### 6.1 Design Principles

- **Single unified wizard** — same React component, adapts to context (Electron vs server vs browser) *(post-MVP)*
- **Context-aware** — detects Electron Bridge availability, server vs desktop, Tailscale state
- **Reusable components** — wizard pattern shared across future setup flows *(post-MVP)*
- **Tech stack:** React (frontend) + Python backend (follows WebUI conventions), separate pnpm package in monorepo *(post-MVP — v0.1 uses plain HTML/JS)*
- **Integrated into WebUI** — not a separate app, lives at `/setup`

### 6.2 Deployment Context Detection

```javascript
const context = {
  isElectron: !!window.electronBridge,
  hasBridge: !!window.electronBridge?.install,
  isTailscaleActive: await checkTailscale(),
  hasOllama: await checkOllama(),
  systemInfo: await bridge?.system.info() ?? null,  // RAM, GPU, disk
}
```

Wizard behaviour adapts per context:

| Step | Desktop (Electron) | Server (CLI/browser) |
|------|--------------------|---------------------|
| Docker check | Auto-detected, silent install via bridge | Pre-installed (install.sh handles it) |
| Ollama install | Silent via bridge + progress bar | Manual instructions shown |
| Model download | Bridge streams progress to wizard | Wizard calls container API → Ollama on host |
| OAuth flows | Standard browser redirect | Device auth code flow |
| Tailscale setup | Bridge opens system browser for login URL | URL + QR code shown in wizard |

### 6.3 Wizard Steps

```
Step 1: Welcome
  - Language selection
  - Desktop: detect Docker (install silently if missing)
  - Server: Docker confirmed by install.sh

Step 2: Access Mode (server only — desktop skips)
  - Port only / Tailscale / Both
  - If Tailscale: show login URL + QR code, poll until connected

Step 3: AI Provider
  ┌───────────────────────────────────────┐
  │ How do you want to use Fox?           │
  │                                       │
  │ ○ Local only (Ollama) — private/free  │
  │   [Auto-detect / Install Ollama]      │
  │                                       │
  │ ○ Cloud AI (recommended)              │
  │   Better quality, needs internet      │
  │   [Connect OpenRouter]  ← OAuth PKCE  │
  │   [Connect OpenAI]      ← OAuth       │
  │   [Connect Gemini]      ← Google OAuth│
  │   [Enter Anthropic key] ← manual only │
  │                                       │
  │ ○ Both (local + cloud fallback)       │
  │                                       │
  │ ○ Advanced (custom endpoint)          │
  └───────────────────────────────────────┘

Step 4: Local Model Selection (if Ollama chosen)
  - Bridge calls system.info → detect RAM
  - Auto-recommend based on hardware:
    < 8GB  → llama3.2:3b  (2GB,  fast)
    8-16GB → llama3.1:8b  (5GB,  balanced)
    16GB+  → llama3.3:70b (43GB, best quality)
  - Show download size warning clearly
  - Option to skip and configure later

Step 5: Memory Setup
  - Confirm mem0_oss (Qdrant) enabled
  - Optionally configure retention preferences

Step 6: Notes App (Memos)
  - Enable/disable Memos
  - Memos auth disabled (single-user mode)
  - Accessible via iframe in WebUI sidebar

Step 7: Workspace Folder
  - Show OS-appropriate default path
  - Allow override via folder picker

Step 8: Done
  - Config written to /data/config/
  - Services restart
  - Redirect to main WebUI
```

### 6.4 OAuth Flows Per Context

**Desktop (Electron):**
- Standard OAuth2 PKCE redirect
- Electron Bridge opens system browser
- Redirect back to `http://localhost:8787/oauth/callback`

**Server:**
- Device auth code flow (headless-compatible)
- Wizard shows code + URL: "Visit openai.com/device, enter: XXXX-XXXX"
- Backend polls for token until confirmed

**Provider support:**

| Provider | Desktop | Server | Notes |
|----------|---------|--------|-------|
| OpenRouter | OAuth PKCE ✅ | Device flow ✅ | Recommended default |
| OpenAI | OAuth (existing subscription) ✅ | Device flow ✅ | |
| Gemini | Google OAuth ✅ | Device flow ✅ | |
| Anthropic | API key only | API key only | No OAuth available |
| Ollama | No auth needed | No auth needed | Local only |

### 6.5 Post-Onboarding Settings

Users can modify settings via:
- WebUI settings panel (primary)
- Direct config file editing (advanced users)
- Environment variables (power users)

---

## 7. Monorepo & Tooling

### 7.1 Monorepo Structure

```
fox-in-the-box/                    # Main integration repo
├── .github/
│   ├── workflows/
│   │   ├── build-container.yml   # Build + push Docker image
│   │   ├── build-electron.yml   # Build Win/Mac Electron apps
│   │   ├── test-integration.yml # Full stack tests
│   │   └── release.yml         # Bimonthly release automation
│   └── ISSUE_TEMPLATE/
├── .gitmodules                   # Fork references
├── package.json                 # pnpm workspace root
├── pnpm-workspace.yaml         # Workspace definition
├── forks/                      # Git submodules (your forks)
│   ├── hermes-agent/          # Fork of NousResearch/hermes-agent
│   └── hermes-webui/          # Fork of hermes-webui upstream
├── packages/                   # pnpm workspaces
│   ├── integration/           # Docker build configs, patches
│   │   ├── Dockerfile
│   │   ├── supervisord.conf
│   │   ├── entrypoint.sh
│   │   ├── default-configs/
│   │   └── migration-scripts/
│   ├── electron/              # Electron desktop app
│   │   ├── main.js
│   │   ├── docker-manager.js
│   │   ├── auto-updater.js
│   │   └── installers/
│   ├── onboarding-wizard/    # Onboarding wizard UI
│   │   ├── src/              # v0.1: plain HTML/JS — no build step
│   │   │                     # v0.2+: React — built via multi-stage Dockerfile (see §3.3)
│   │   └── dist/             # .gitignored — output baked into Docker image at build time
│   └── tools/               # Dev scripts and utilities
│       ├── pull-upstream.sh
│       ├── rebase-patches.sh
│       ├── create-upstream-pr.sh
│       └── test-integration.sh
├── docs/
│   ├── ARCHITECTURE.md
│   ├── GETTING_STARTED.md
│   ├── DEVELOPMENT.md
│   ├── DATA_MIGRATION.md
│   ├── ELECTRON_DEPLOYMENT.md
│   ├── API_KEYS_GUIDE.md
│   └── CONTRIBUTING.md
├── tests/
│   ├── integration/          # Full stack tests
│   ├── electron/            # Desktop app tests
│   └── migration/           # Data migration tests
├── LICENSE                  # MIT
├── README.md
├── CONTRIBUTING.md
├── CODE_OF_CONDUCT.md
├── ROADMAP.md              # Public roadmap including compose migration
└── REQUIREMENTS.md         # This document
```

### 7.2 Tooling Choices

| Tool | Purpose | Rationale |
|------|---------|-----------|
| **pnpm** | Package management + workspaces | Smaller Docker images, strict deps, fast installs |
| **Git submodules** | Fork management | Clear repo boundaries, version pinning |
| **GitHub Actions** | CI/CD | Standard, free for open source |
| **Docker** | Container runtime | Universal, Electron-compatible |
| **supervisord** | Process management | Python-native, simple config |
| **Tailscale** | Networking + HTTPS + routing | Zero-config, replaces nginx |

### 7.3 pnpm Workspace Config

```yaml
# pnpm-workspace.yaml
packages:
  - 'packages/*'
```

```json
// package.json (root)
{
  "name": "fox-in-the-box",
  "private": true,
  "packageManager": "pnpm@9.0.0",
  "scripts": {
    "pull-upstream": "./packages/tools/pull-upstream.sh",
    "rebase": "./packages/tools/rebase-patches.sh",
    "test": "./packages/tools/test-integration.sh",
    "build": "docker build -f packages/integration/Dockerfile -t ghcr.io/fox-in-the-box-ai/cloud:dev .",
    "release": "./packages/tools/create-release.sh"
  }
}
```

---

## 8. Git & Fork Strategy

### 8.1 Fork Setup

Each upstream dependency has a corresponding fork under your GitHub org:

| Upstream | Your Fork | Purpose |
|----------|-----------|---------|
| `NousResearch/hermes-agent` | `fox-in-the-box-ai/hermes-agent` | Bedrock fixes, custom patches |
| `upstream/hermes-webui` | `fox-in-the-box-ai/hermes-webui` | Simplified UI, onboarding integration |
| `Mem0ai/mem0` | Use as-is or fork if needed | Memory provider |
| `usememos/memos` | Use upstream image directly | Notes app (no modifications planned) *(post-MVP, v0.2+)* |

### 8.2 Branch Strategy Per Fork

```
fox-in-the-box-ai/hermes-agent:
├── main              # Synced with upstream exactly
├── dev               # Integration testing branch
├── bedrock           # Bedrock-specific patches
├── custom            # Fox-specific modifications
└── pr/*              # Clean branches for upstream PRs

fox-in-the-box-ai/hermes-webui:
├── main              # Synced with upstream exactly
├── dev               # Integration testing branch
├── simplified-ui     # Clutter removal, custom interface
├── onboarding        # Onboarding wizard integration
└── pr/*              # Clean branches for upstream PRs
```

### 8.3 Upstream Contribution Workflow

When fixing a bug that affects everyone:

```
1. Fix bug in your feature branch (e.g., bedrock)
2. Create clean pr/* branch from main
3. Cherry-pick ONLY the generic fix (no Bedrock-specific code)
4. Submit PR to upstream
5. Keep fix in your branch until PR merged upstream
6. Once merged upstream, remove from your branch on next sync
```

**Categorization of fixes:**

| Fix Type | Action |
|----------|--------|
| **Generic bug** | PR upstream first, keep in fork until merged |
| **Critical bug** | Fix in fork immediately, release, then upstream PR |
| **Bedrock-specific** | Keep in fork only (not upstream-relevant) |
| **UI simplification** | Keep in fork only (opinionated changes) |

### 8.4 Bimonthly Update Workflow

```
Week 1: Pull upstream into fork main branches
         Run: pnpm pull-upstream
Week 2: Rebase feature branches, resolve conflicts
         Run: pnpm rebase
         Test individual components
Week 3: Integration testing
         Run: pnpm test
         Build test container
Week 4: Release
         Tag forks with version
         Build and push container image
         Build and publish Electron apps
         Run: pnpm release
Weeks 5-8: Stability period, bug fixes only
```

---

## 9. Release Strategy

### 9.1 Versioning

- **Container tags:** `ghcr.io/fox-in-the-box-ai/cloud:v0.1.0`, `:stable`, `:latest` (semver)
- **Electron app versions:** `0.1.0`, `0.2.0`, etc. (semver, always in sync with container version)
- **Fork tags:** `v0.1.0` on each fork repo (same tag as container release)

### 9.2 Release Artifacts

| Artifact | Registry/Platform |
|----------|------------------|
| Docker image | GHCR (`ghcr.io/fox-in-the-box-ai/cloud:stable`) |
| Windows installer (.exe) | GitHub Releases |
| macOS (`install.sh` + Docker, systemd/launchd) | README / raw script on `main` |
| Source code | GitHub (`fox-in-the-box-ai` org, tagged release) |

### 9.3 Auto-Update Channels

| Channel | Purpose | Update Frequency |
|---------|---------|-----------------|
| **stable** | Production users | Bimonthly |
| **beta** | Early adopters | Monthly |
| **dev** | Contributors | On every push to dev |

---

## 10. Security Considerations

### 10.1 Secrets Management

- API keys stored in `/data/config/hermes.env` (user's volume, not in image)
- No secrets baked into Docker image or git repo
- Onboarding wizard handles initial key setup via OAuth or manual entry
- `.env` files in `.gitignore` of all repos

### 10.2 Container Security

- Tailscale requires `NET_ADMIN` capability and `net.ipv4.ip_forward=1`
- Container runs as non-root user (except Tailscale daemon)
- Data volume permissions managed by entrypoint script
- Strict CSP headers on WebUI prevent XSS → bridge escalation
- All AI output rendered as sanitized markdown — never raw HTML

### 10.3 Electron Bridge Security

The bridge is the highest-risk surface area. Full threat model:

| Risk | Severity | Mitigation |
|------|----------|------------|
| Prompt injection → XSS → bridge call | 🔴 Critical | Strict CSP + sanitized AI output |
| Container calling bridge via host network | 🔴 Critical | Bridge is IPC only, not TCP — unreachable from container |
| Bridge token leaked via env vars | 🟠 High | Bridge not exposed via env vars |
| Privileged action without user confirmation | 🟠 High | Every action requires explicit user confirmation dialog |
| Arbitrary shell execution via bridge | 🟠 High | Strict action allowlist, no shell exec |

### 10.4 Network Security

- **Desktop:** Port bound to `127.0.0.1` only — not reachable from network
- **Server (Tailscale):** Zero open ports — encrypted VPN only
- **Server (port mode):** `0.0.0.0:8787` — user responsible for firewall, warning shown
- Tailscale Serve provides automatic HTTPS with valid certificates
- Services only listen on localhost inside container

### 10.5 No Telemetry

By design — privacy is a core value. No usage analytics, crash reporting, or telemetry of any kind. Not even opt-in.

---

## 11. Open Source Requirements

### 11.1 Licensing

| Component | License |
|-----------|---------|
| Fox in the Box (integration) | MIT |
| Documentation | CC-BY-4.0 |
| Hermes Agent fork | MIT (matches upstream) |
| Hermes WebUI fork | MIT (matches upstream) |

### 11.2 Repository Standards

- Clear README with quickstart instructions
- CONTRIBUTING.md with development setup
- CODE_OF_CONDUCT.md
- Issue templates for bugs, features, questions
- PR template with checklist
- ARCHITECTURE.md explaining system design
- All decisions documented (ADRs or this document)

### 11.3 Community Considerations

- No proprietary dependencies
- No required paid services (API keys are user-provided)
- Clear documentation for self-hosting without Electron
- Docker-only deployment path available
- Contributor-friendly development setup

---

## 12. Current VPS Reference (Development Environment)

### 12.1 Services Running

| Service | Type | Port | Status |
|---------|------|------|--------|
| Hermes WebUI | systemd user service | 8787 (Tailscale IP) | Active |
| Hermes Gateway | systemd user service | — | Active |
| Memos | Docker container | 5230 | Active |
| Blinko | Docker container | 8080 | Active (to be removed) |
| PostgreSQL | Docker container | 5432 | Active (to be removed) |
| Open WebUI | Docker container | 3000 | Active (to be replaced by WebUI fork) |
| Tailscale | system service | 443/HTTPS | Active |
| Samba | system service | 445 | Active (not included in container) |

### 12.2 Key Configuration Files

| File | Purpose |
|------|---------|
| `~/.hermes/config.yaml` | Hermes Agent configuration |
| `~/.hermes/.env` | API keys (Bedrock, Telegram, GitHub, etc.) |
| `~/.mem0/` | mem0 memory provider config + data |
| `~/.config/systemd/user/hermes-gateway.service` | Gateway service definition |
| `~/.config/systemd/user/hermes-webui.service` | WebUI service definition |
| `~/hermes-webui/.env` | WebUI environment (host binding) |

### 12.3 Current Hermes Configuration Highlights

- **Model:** `deepseek.v3.2` via Bedrock
- **Provider:** Bedrock (with 4-layer fix for non-Anthropic models)
- **Memory:** `mem0_oss` (self-hosted Qdrant + SQLite)
- **Auxiliary models:** Claude Haiku 4.5 via Bedrock (auto provider)
- **Gateway:** Telegram bot configured
- **Local patches:** Bedrock fixes maintained via local-patches branch

### 12.4 Tailscale Serve Configuration (Current)

```
https://hermes.tail873f17.ts.net (tailnet only)
|-- / proxy http://100.94.15.85:8787
```

---

## 13. Open Questions & Decisions Log

### 13.1 Resolved Decisions

| # | Decision | Resolution |
|---|----------|------------|
| 1 | Electron Docker runtime | Silent install via Electron (winget/brew). Detect first, install if missing |
| 2 | Tailscale auth | Interactive browser login. URL shown in CLI (server) or opened via bridge (desktop) |
| 3 | WebUI modifications | CSS overrides + component rearranging. Handled as part of MVP in webui fork |
| 4 | Onboarding wizard tech | **v0.1:** Plain HTML/JS, 4 steps, no build step. **v0.2+:** React + Python backend, multi-stage Dockerfile build, separate pnpm package at `/setup`. See decision #30. |
| 5 | mem0_oss Qdrant | Embed binary in container. Simpler for MVP |
| 6 | Memos integration | iframe in WebUI. Auth disabled (single-user mode) |
| 7 | Automatic backup | Manual docs only for MVP. Auto-backup is post-MVP |
| 8 | Multi-user support | Single user only. Not a priority. Simple architecture exploration post-MVP |
| 9 | Local model support | Ollama. Silent install via bridge (desktop) or manual (server). In MVP |
| 10 | Telemetry | None. Not even opt-in. Privacy is a core value |
| 11 | GitHub org name | `fox-in-the-box` |
| 12 | Monorepo tooling | pnpm workspaces + git submodules |
| 13 | Container strategy | Single monolithic container. Compose as optional advanced mode post-MVP |
| 14 | Reverse proxy | None — Tailscale Serve handles HTTPS routing |
| 15 | Server port binding | `0.0.0.0:8787` for MVP with clear firewall warning |
| 16 | Server updates | Sentinel file → systemd updater service. WebUI "Update" button |
| 17 | Desktop updates | Electron manages directly (pull + restart) |
| 18 | Auto-boot | Server: systemd. Desktop: Electron auto-launch |
| 19 | Rollback | Post-MVP |
| 20 | Installer | Electron Builder for MVP. Custom branded installer post-MVP |
| 21 | Electron bridge | IPC only (contextBridge) — not TCP. Container cannot reach it |
| 22 | OAuth on server | Device auth code flow for all server OAuth |
| 23 | Tailscale optional? | Yes — user chooses: port / Tailscale / both during install |

### 13.2 Still Open

| # | Question | Notes |
|---|----------|-------|
| 1 | **`/health` endpoint implementation** | CI smoke test (Task 08) requires `GET /health` → HTTP 200. Hermes WebUI upstream doesn't have this route. Decision: add to WebUI fork (cleanest) or add a supervisord-gated health responder in entrypoint.sh. See Task 03 pitfall #6. |
| 2 | **WebUI CSP headers — exact policy** | Needs security review. Post-MVP |

### 13.3 Additional Resolved Decisions

| # | Decision | Resolution |
|---|----------|------------|
| 24 | Config hierarchy | Three layers: env vars (highest) → `/data/config/` (user) → `/app/defaults/` (container). API keys in `hermes.env`, overridable via env vars. Onboarding state not overridable |
| 25 | Ollama on server | Always on host, never in container. Fox connects via `host-gateway:11434`. install.sh detects existing Ollama, offers install if missing. Models stay on host (too large for container) |
| 26 | Domain name | `foxinthebox.io` |
| 27 | GitHub org | `fox-in-the-box-ai` |
| 28 | Container image registry | GHCR (`ghcr.io/fox-in-the-box-ai/cloud:stable`). No Docker Hub pull rate limits, integrated with GitHub Actions, free for public repos. Docker Hub as optional mirror post-MVP |
| 29 | Memos iframe cross-origin | *(post-MVP)* Memos is out of v0.1 scope. Decision deferred to v0.2. |
| 30 | React UI build strategy | Multi-stage Dockerfile: `node:20-slim AS ui-builder` builds `dist/`, `COPY --from=ui-builder` bakes it into the final image. No Node.js on user machines. `dist/` gitignored. Applies from v0.2+; v0.1 uses plain HTML. See §3.3 |

---

## 14. Roadmap

> **Note:** This doc uses "MVP (v1)" for the full initial product vision.
> Active development targets **v0.1** first — a subset of the MVP. See ROADMAP.md
> for the phased breakdown. Items marked *(v0.1)* are in scope now; the rest are
> planned for subsequent releases before the full v1 launch.

### MVP (v1)
- Single container with Hermes Agent + WebUI + mem0 + Tailscale *(v0.1)*
- Linux server install script with systemd *(v0.1)*
- Plain HTML/JS onboarding wizard — 4 steps *(v0.1)*
- Electron apps for Windows + macOS (Electron Builder) *(v0.1, not promoted on website)*
- Memos notes app *(post-v0.1, v0.2+)*
- Onboarding wizard: React + Python, context-aware, 8-step *(post-v0.1, v0.2+)*
- Ollama local model support *(post-v0.1)*
- OAuth for OpenRouter, OpenAI, Gemini *(post-v0.1)*
- Tailscale integration (optional, user choice) *(post-v0.1)*
- WebUI fork: simplified UI, Memos iframe *(post-v0.1)*
- Hermes fork: Bedrock fixes, custom patches *(v0.1)*
- pnpm monorepo + git submodules *(v0.1)*
- Bimonthly release cadence

### Post-MVP (v2+)
- Docker Compose "advanced mode" with migration path
- Custom branded Electron installer
- Auto-backup before upgrades
- Rollback to previous version
- PWA support (mobile via browser)
- Multi-provider model switching UI
- Plugin/skill marketplace
- Shared workspaces / collaboration (requires multi-user in Hermes)
- White-label / rebrand support

---

## 15. Glossary

| Term | Definition |
|------|-----------|
| **Fox in the Box** | The product — packaged AI assistant platform |
| **fox in the box** | The brand (lowercase for logos/UI) |
| **Hermes Agent** | Open-source AI agent framework by Nous Research |
| **Hermes WebUI** | Browser-based chat interface for Hermes Agent |
| **mem0_oss** | Open-source memory provider using Qdrant vectors |
| **Memos** | Self-hosted notes/knowledge app (SQLite-based) |
| **Tailscale Serve** | Tailscale feature that proxies HTTPS traffic to local services |
| **Tailscale Funnel** | Tailscale feature that exposes services to the public internet |
| **supervisord** | Python process manager for running multiple services in one container |
| **pnpm** | Fast, disk-efficient Node.js package manager |
| **Bimonthly release** | New stable version every 2 months |
