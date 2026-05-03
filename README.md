# Fox in the Box

[![GitHub Sponsors](https://img.shields.io/github/sponsors/bsgdigital?label=Sponsor&logo=githubsponsors&color=ea4aaa)](https://github.com/sponsors/bsgdigital)

> A self-hosted AI assistant that runs entirely on your machine — no subscriptions, no cloud dependencies, no data leaving your control.

Fox in the Box packages a full AI assistant stack into a single Docker container, with a native Windows desktop app and a one-command install script for **Linux and macOS** (Docker-based, same flow on both). Bring your own API key and you're up in minutes.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)](https://github.com/fox-in-the-box-ai/fox-in-the-box/releases)
[![Release](https://img.shields.io/github/v/release/fox-in-the-box-ai/fox-in-the-box)](https://github.com/fox-in-the-box-ai/fox-in-the-box/releases/latest)

---

## Features

| Feature | Description |
|---------|-------------|
| Single container | AI agent, web UI, memory, and VPN in one Docker image |
| Web-based setup | Browser onboarding wizard — no terminal required |
| Persistent memory | Remembers context across sessions via local vector store |
| Remote access | Built-in Tailscale VPN with automatic HTTPS |
| Desktop app | Native Electron wrapper for Windows; macOS uses the install script or Docker |
| Open source | MIT licensed, full source available |

---

## Installation

### Option 1 — Install script (Linux and macOS)

Same flow on both platforms: installs Docker if needed, pulls `ghcr.io/fox-in-the-box-ai/cloud:stable`, runs the container, and sets up **systemd** (Linux) or **launchd** (macOS) so the stack comes back after reboot.

```bash
curl -fsSL https://raw.githubusercontent.com/fox-in-the-box-ai/fox-in-the-box/main/packages/scripts/install.sh | bash
```

Or clone the repo and run `bash packages/scripts/install.sh`.

- **Data directory (default):** Linux `~/.foxinthebox`; macOS `~/Library/Application Support/Fox in the Box`. Override with `FOX_DATA_DIR` / `FOX_WORKSPACE_DIR` if you need to.
- **macOS:** If Docker is missing, the script installs **Docker Desktop** via Homebrew when `brew` is available, then exits so you can start Docker once and re-run the script.
- **Browser:** The script waits until **`http://127.0.0.1:8787/health`** responds (up to **240s** on first boot), then opens **http://localhost:8787**. Set **`FOX_OPEN_BROWSER=0`** to skip opening; **`FOX_HEALTH_WAIT_SEC`** overrides the wait cap. If the tab still loads slowly, refresh once Hermes has finished starting (`docker logs -f fox-in-the-box`).

### Option 2 — Docker one-liner (all platforms)

Matches the integration smoke test (localhost binding, Tailscale-capable container):

```bash
docker run -d \
  --name fox-in-the-box \
  --restart unless-stopped \
  --cap-add=NET_ADMIN \
  --device /dev/net/tun \
  --sysctl net.ipv4.ip_forward=1 \
  -p 127.0.0.1:8787:8787 \
  -v ~/.foxinthebox:/data \
  ghcr.io/fox-in-the-box-ai/cloud:stable
```

On macOS you can keep `-v ~/.foxinthebox:/data` or use a path under `~/Library/Application Support/Fox in the Box` for consistency with the install script.

### Option 3 — Windows desktop app

Download the installer from the [latest release](https://github.com/fox-in-the-box-ai/fox-in-the-box/releases/latest): **`fox-in-the-box-setup.exe`** (stable name on tagged releases).

There is **no** signed macOS `.dmg` in releases; use **Option 1** on Mac.

### Option 4 — Build from source

Initialize submodules (Hermes agent and webui are **copied into the image at build time** from `forks/`):

```bash
git submodule update --init --recursive
```

Then see [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md) for full build instructions (e.g. `pnpm build:docker` from the repo root).

---

## Full reset (desktop app, “clean install”)

Use this when you want a **new container**, fresh **on-disk data**, and optionally a **fresh image** (for example after changing Docker options such as `/dev/net/tun`).

### Windows

1. **Quit** Fox in the box completely (including the system tray icon).
2. **Uninstall** the application from **Settings → Apps → Installed apps** if you also want the program files removed. The installer does **not** delete your data folder by default.
3. Remove the container and app data — either:
   - **Script (recommended):** in PowerShell, from the repo (or copy the file elsewhere):

     ```powershell
     cd packages\scripts
     .\clean-windows-desktop.ps1
     ```

     To also delete the published Linux image (next app start will `docker pull` again):

     ```powershell
     .\clean-windows-desktop.ps1 -RemoveImage
     ```

     If you ever used the **CLI** flow with `-v ~/.foxinthebox:/data` from this README, add `-RemoveFoxintheboxDir` to remove `%USERPROFILE%\.foxinthebox` as well.

   - **Manual:** `docker rm -f fox-in-the-box`, delete `%APPDATA%\Fox in the box`, and optionally `docker rmi ghcr.io/fox-in-the-box-ai/cloud:stable`.
4. **Reinstall** from the [latest release](https://github.com/fox-in-the-box-ai/fox-in-the-box/releases/latest) (or run your new installer / dev build), then start the app once so it recreates the container.

### macOS (install script or Docker)

1. Stop the stack: `docker stop fox-in-the-box` (or `docker rm -f fox-in-the-box`).
2. If you used **launchd** from the install script: `launchctl unload ~/Library/LaunchAgents/io.foxinthebox.plist` and remove that plist if you no longer want auto-start.
3. Remove data under your chosen `FOX_DATA_DIR` (default: `~/Library/Application Support/Fox in the Box`).
4. Optionally `docker rmi ghcr.io/fox-in-the-box-ai/cloud:stable`, then re-run the [install script](#option-1--install-script-linux-and-macos) or the Docker one-liner.

---

## Requirements

| Platform | Requirement |
|----------|-------------|
| Docker | 20.10 or later |
| Windows | Windows 10 or later (x64) |
| macOS | macOS 12 (Monterey) or later |
| Linux | Any distro with Docker support |

An [OpenRouter](https://openrouter.ai) API key is required for AI functionality.

---

## Architecture

Fox in the Box bundles the following components:

| Component | Purpose |
|-----------|---------|
| [Hermes Agent](https://github.com/fox-in-the-box-ai/hermes-agent) | AI agent core — LLM orchestration, tools, skills |
| [Hermes WebUI](https://github.com/fox-in-the-box-ai/hermes-webui) | Browser-based chat interface |
| mem0\_oss + Qdrant | Persistent memory with local vector search |
| Tailscale | VPN tunneling and automatic HTTPS |
| supervisord | Process management inside the container |

**Container vs. data:** The published Docker image includes Hermes agent and webui source (from the monorepo `forks/` submodules) installed at **build** time. On startup, the entrypoint links them under `/data/apps` so supervisord paths stay stable; the **`/data` volume** holds your config, databases, logs, and Tailscale state — not a fresh `git clone` of Hermes on every first run. Updating Hermes for end users means pulling a **newer image**, not waiting for the container to clone GitHub.

---

## Documentation

- [CHANGELOG.md](CHANGELOG.md) — release history
- [CONTRIBUTING.md](CONTRIBUTING.md) — how to contribute
- [SECURITY.md](SECURITY.md) — vulnerability reporting
- [CODE\_OF\_CONDUCT.md](CODE_OF_CONDUCT.md) — community standards
- [docs/GETTING\_STARTED.md](docs/GETTING_STARTED.md) — development setup
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — system design

---

## License

MIT — see [LICENSE](LICENSE).
