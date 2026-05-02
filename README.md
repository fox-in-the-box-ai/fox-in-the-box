# Fox in the Box

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

See [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md) for full build instructions.

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
