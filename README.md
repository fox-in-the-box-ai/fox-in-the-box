# Fox in the Box

[![GitHub Sponsors](https://img.shields.io/github/sponsors/bsgdigital?label=Sponsor&logo=githubsponsors&color=ea4aaa)](https://github.com/sponsors/bsgdigital)

> A self-hosted AI assistant that runs entirely on your machine — no subscriptions, no cloud dependencies, no data leaving your control.

Fox in the Box packages a full AI assistant stack into a single Docker container with native desktop apps for Windows and macOS. Bring your own API key and you're up in minutes.

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
| Desktop apps | Native Electron wrapper for Windows and macOS |
| Open source | MIT licensed, full source available |

---

## Installation

### Option 1 — Docker (all platforms)

```bash
docker run -d \
  --name fox-in-the-box \
  --cap-add=NET_ADMIN \
  --device /dev/net/tun \
  -p 8787:8787 \
  -v ~/.foxinthebox:/data \
  ghcr.io/fox-in-the-box-ai/cloud:stable
```

Open [http://localhost:8787](http://localhost:8787) and follow the setup wizard.

### Option 2 — Desktop app

Download the installer for your platform from the [latest release](https://github.com/fox-in-the-box-ai/fox-in-the-box/releases/latest):

- **Windows** — `fox-in-the-box-x.x.x-setup.exe`
- **macOS** — `fox-in-the-box-x.x.x-mac.zip`

### Option 3 — Build from source

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

### macOS

1. Quit the app (menu bar).
2. `docker rm -f fox-in-the-box`
3. Delete the app’s user data directory (Electron **userData** for this app — typically under `~/Library/Application Support/` for the product name), and remove `~/Library/Caches/` entries for the app if you want caches cleared too.
4. Optionally `docker rmi ghcr.io/fox-in-the-box-ai/cloud:stable`, then reinstall from the release zip.

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

**WebUI POST timeouts (fixed at image build):** A bug in upstream Hermes WebUI caused `do_POST` to read the entire request body before routing, while `handle_post` then tried to read the same body again — the second read blocked until the 30s socket timeout, surfacing as **HTTP 500** on routes such as `POST /api/providers` and `POST /api/session/new`. The integration [Dockerfile](packages/integration/Dockerfile) applies [this patch](packages/integration/patches/hermes-webui-do-post-double-read.patch) during `docker build`. Rebuild or pull an image that includes that step if you still see those symptoms on an older tag.

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
