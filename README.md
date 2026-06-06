# Fox in the Box

[![GitHub Sponsors](https://img.shields.io/github/sponsors/bsgdigital?label=Sponsor&logo=githubsponsors&color=ea4aaa)](https://github.com/sponsors/bsgdigital)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)](https://github.com/fox-in-the-box-ai/fox-in-the-box/releases)
[![Release](https://img.shields.io/github/v/release/fox-in-the-box-ai/fox-in-the-box)](https://github.com/fox-in-the-box-ai/fox-in-the-box/releases/latest)
[![Playwright](https://github.com/fox-in-the-box-ai/fox-in-the-box/actions/workflows/playwright.yml/badge.svg)](https://github.com/fox-in-the-box-ai/fox-in-the-box/actions/workflows/playwright.yml)
[![CodeQL](https://github.com/fox-in-the-box-ai/fox-in-the-box/actions/workflows/codeql.yml/badge.svg)](https://github.com/fox-in-the-box-ai/fox-in-the-box/actions/workflows/codeql.yml)

> A private AI assistant that runs on your computer. No subscriptions, no cloud lock-in, no data leaving your machine without your say-so.

Fox in the Box bundles a full AI assistant — agent, chat UI, persistent memory, and secure remote access — into one app. Bring an OpenRouter API key, run the installer, and start chatting in minutes.

<!-- TODO: add a screenshot or short GIF of the chat UI here -->

---

## What you get

- **Runs on your computer.** Conversations, memory, and files stay on your machine.
- **Remembers across sessions.** Your assistant picks up where you left off.
- **Reachable from anywhere.** Optional secure HTTPS access from your phone or another laptop via Tailscale.
- **Setup in the browser.** No terminal needed for the desktop app. Paste your API key — or skip the wizard entirely if you already have a local model running.
- **Local AI in one click.** Got Ollama installed? Fox auto-detects it on first launch and lets you chat with a local model — no API key, no terminal.
- **Open source.** MIT licensed. You can read every line of what's running.

---

## How it works

Fox in the Box runs a small private server on your computer inside something called a **Docker container** — think of it as a sealed box that keeps everything organized and separate from the rest of your system. The desktop app manages this box for you automatically.

When you send a message, the app forwards it to your chosen AI provider (like OpenRouter or Anthropic) over the internet, gets a response, and displays it in the chat. The only thing that leaves your computer is the message itself — your conversation history, files, and memory stay on your machine.

**Memory** is what makes Fox different from a plain chatbot. It remembers what you've talked about across sessions — your preferences, your projects, the context of previous conversations. This memory is stored locally in a small database on your computer, not in the cloud.

**Remote access** is optional. If you want to chat with your assistant from your phone or another computer, Fox can set up a secure private link using Tailscale (a free personal VPN). Only your own devices can reach it — nobody else can see or access your assistant.

**Updates** are simple: the desktop app pulls the latest version automatically. If you installed via the terminal script, run it again — it replaces the old version and keeps your data.

---

## Features

A practical tour of what's in the box. Most of this is wired up by the bundled [Hermes Agent](https://github.com/NousResearch/hermes-agent) and [Hermes WebUI](https://github.com/NousResearch/hermes-webui); Fox in the Box adds the desktop wrapper, the Docker packaging, the onboarding wizard, Tailscale integration, and the auto-update channel.

### Chat

- Streaming responses with live tool-call progress, markdown rendering, and syntax-highlighted code blocks
- 26 slash commands — including `/new`, `/clear`, `/compress`, `/branch`, `/queue`, `/interrupt`, `/steer`, `/btw`, `/background`, `/reasoning`, `/yolo`, `/voice`, `/skills`, `/personality`, `/usage`, `/retry`, `/undo`, `/status`
- **Live steering** — inject mid-stream guidance without canceling the current turn
- **Branching** — fork a conversation into a new session at any point and explore an alternate direction
- **Background tasks** — kick off long-running prompts and keep chatting; a badge tracks completion
- **Session search** — browse and search every prior conversation from the sidebar

### Memory and personalization

- Persistent memory across sessions, stored locally in **Qdrant** (vector DB) + **mem0**
- Read, edit, and prune entries from the Memory panel
- Per-profile personality (`SOUL.md`) — give your assistant a different voice in different profiles

### Multi-profile

- Separate Hermes environments with isolated config, sessions, and memory
- Switch profiles without restarting; create one for work, one for personal, one for experiments

### Skills, tools, and scheduling

- **Skills** — bundled and user-authored. Browse, search, and edit from the Skills panel. Each skill can register its own slash command.
- **MCP integrations** — Brave Search included out of the box. Add more in `hermes.yaml`.
- **Built-in tools** — file I/O, terminal execution, web browsing (Chrome DevTools Protocol), vision, TTS, transcription, image generation
- **Scheduled tasks** — cron-style job builder; trigger a skill at a fixed cadence (every weekday at 9am, hourly, custom cron)

### Setup and management

- Browser-based onboarding — paste your OpenRouter key, click Open Fox, you're in. No terminal.
- **Switch providers from the chat** — Settings → Providers → key → Save. Live in seconds (no restart).
- **Auto-update** — desktop app pulls new releases via electron-updater; install-script users re-run the same one-liner to upgrade in place
- **Backup-friendly data layout** — everything in `~/.foxinthebox`; reset by deleting the folder
- **Built-in log viewer + diagnostics** — Settings → System

### Privacy and access

- **Local-first** — the only outbound traffic is the LLM API call when you send a message. Memory, sessions, and files never leave your machine.
- **Tailscale integration** — optional secure remote access from your phone or another laptop on your tailnet, with automatic HTTPS via Tailscale Serve
- **MIT licensed** — every line of Fox is readable on GitHub

> **Advanced — messaging gateways.** Hermes Agent ships with Slack, Discord, Telegram, and WhatsApp gateway adapters. They're available inside the container but currently driven via the `hermes` CLI rather than the WebUI. Setup is more involved than provider key entry; see the [Hermes Agent docs](https://github.com/NousResearch/hermes-agent) if you need them today, and watch the [Roadmap](#roadmap) for in-app gateway management.

---

## Install

### Windows desktop app — **easiest**

Download **[`fox-in-the-box-setup-x64.exe`](https://github.com/fox-in-the-box-ai/fox-in-the-box/releases/latest)** from the latest release. Run the installer and follow the prompts. Docker Desktop is installed automatically if missing.

### macOS desktop app — **easiest**

Download the matching DMG from the [latest release](https://github.com/fox-in-the-box-ai/fox-in-the-box/releases/latest):

- Apple Silicon (M1/M2/M3/M4): **`fox-in-the-box-arm64-mac.dmg`**
- Intel Mac: **`fox-in-the-box-x64-mac.dmg`**

Open the DMG and drag Fox in the Box to your Applications folder. The DMG is signed and notarized by Apple.

### Linux / macOS install script

```bash
curl -fsSL https://raw.githubusercontent.com/fox-in-the-box-ai/fox-in-the-box/main/packages/scripts/install.sh | bash
```

Installs Docker if needed, pulls the container image, asks how you want to access it (port, Tailscale, or both), prompts for a friendly Tailscale hostname, and sets up `systemd` (Linux) or `launchd` (macOS) so the assistant comes back after reboot.

### Docker one-liner — advanced users

```bash
docker run -d \
  --name fox-in-the-box \
  --restart unless-stopped \
  --add-host=host.docker.internal:host-gateway \
  --cap-add=NET_ADMIN \
  --device /dev/net/tun \
  --sysctl net.ipv4.ip_forward=1 \
  -p 127.0.0.1:8787:8787 \
  -v ~/.foxinthebox:/data \
  ghcr.io/fox-in-the-box-ai/cloud:stable
```

Then open **http://localhost:8787** and follow the setup wizard.

### Build from source

```bash
git submodule update --init --recursive
pnpm install
pnpm build:docker          # build the container with the version in /VERSION
docker run -d --name fitb \
  --cap-add=NET_ADMIN --device /dev/net/tun --sysctl net.ipv4.ip_forward=1 \
  -p 127.0.0.1:8787:8787 -v ~/.foxinthebox:/data \
  fox-in-the-box:$(cat VERSION)
```

For local iteration on the bundled `hermes-agent` / `hermes-webui` submodules, see [`docs/DEV_MODE.md`](docs/DEV_MODE.md). For releases, see [`docs/RELEASE_WORKFLOW.md`](docs/RELEASE_WORKFLOW.md).

---

## Requirements

**Operating system**

- **Windows 10 or later** (Windows 11 recommended).
- **macOS 12** (Monterey) or later — Apple Silicon or Intel.
- **Linux** with Docker Engine 20.10 or later.

**Docker — required**

- **[Docker Desktop](https://www.docker.com/products/docker-desktop/)** on Windows and macOS; **[Docker Engine](https://docs.docker.com/engine/install/)** on Linux. Fox auto-installs Docker Desktop on Windows if it isn't present and walks you through the install + reboot.
- **Windows: Linux-containers mode is required** (Docker Desktop's default). If you've previously switched to Windows-containers mode, Fox detects it and exits with an actionable error — right-click the Docker Desktop tray icon → **Switch to Linux containers...** and relaunch Fox.
- **Windows: the WSL 2 backend is required.** Docker Desktop's installer enables it for you. In Docker Desktop settings make sure **General → "Use the WSL 2 based engine"** is checked. If WSL2 isn't installed when Fox launches, it'll attempt the repair automatically (may require a reboot).

**CPU virtualization** *(Windows only)*

- **Hardware virtualization must be enabled in BIOS/UEFI** — `VT-x` on Intel CPUs, `AMD-V` / `SVM Mode` on AMD CPUs. Required by both Docker Desktop and WSL2.
- Most consumer PCs ship with it enabled. If Docker reports "WSL2 backend not running" or "virtualization disabled," reboot into BIOS, look for **Intel Virtualization Technology** / **SVM Mode** / **VT-x**, enable it, save, reboot.
- Apple Silicon and Intel Macs have virtualization on by default — nothing to configure.

**Provider API key** *(at least one)*

- An **[OpenRouter](https://openrouter.ai)** API key (recommended — one key gives you hundreds of models, no per-provider setup).
- Or any other supported provider — Anthropic, OpenAI, Google Gemini, DeepSeek, Mistral, etc. Configurable in Settings after install. See [Supported providers](#supported-providers) below.

**Ollama** *(optional — only if you want local models)*

- To run local AI models, install **[Ollama](https://ollama.com/download)** separately on your host machine — Ollama runs on your computer, not inside the Fox container.
- Fox auto-detects a running Ollama daemon via `host.docker.internal:11434` and surfaces every installed model in **Settings → Providers → Local Ollama** with one-click switching.
- Pull at least one model first (`ollama pull phi4-mini`, `ollama pull llama3.2:3b`, etc.) — or use Fox's one-click pull from the recommended set inside the app.
- Ollama is not required if you only use cloud providers.

---

## After setup

The setup wizard runs once. After that the app handles itself — but a few things are worth knowing.

**Add or switch providers.** OpenRouter is configured during onboarding. To add Anthropic, OpenAI, Google Gemini, DeepSeek, Mistral, or any other supported provider: open Fox, click the **gear icon** in the top bar → **Settings → Providers** → paste the API key → **Save**. The new provider is live within seconds — no restart, no terminal. Overwrite a key to rotate it; click **Remove** to clear it.

**Use a local model.** If you have [Ollama](https://ollama.com/download) running on your computer, Fox finds it automatically. **Settings → Providers → Local Ollama** lists every model on your machine and lets you switch to one with a single click. Keyless, on-device, private. If you don't have any models yet, Fox shows a recommended set with one-click install — no terminal needed. You can pull more, switch active model, and delete unused ones, all from inside the chat. Total disk usage is shown so you know what you're carrying.

**Pick a model.** The model picker in the chat lists every model your configured providers offer. Switch any time; the conversation thread is preserved.

**Name your Fox on Tailscale.** If you're using Tailscale for remote access, **Settings → System → Device name (Tailscale)** lets you pick a friendly hostname (e.g. `fox-clever`) — it shows up on your tailnet and in the HTTPS URL Tailscale Serve publishes. Defaults to a `fox-<adjective>` if you leave it blank.

**Enable HTTPS for the tailnet URL.** Tailscale Serve needs HTTPS to be enabled on your tailnet — a one-time toggle in the [Tailscale admin console](https://login.tailscale.com/admin/dns) → **DNS** → **Enable HTTPS**. Once enabled, Fox publishes its chat UI at `https://fox-<your-name>.<your-tailnet>.ts.net/`. The first time you visit, Chrome / Safari may show a brief HTTPS warning while Tailscale provisions the cert — refresh after a minute. Without HTTPS enabled on the tailnet, the chat UI is still reachable via the device's tailnet IP (e.g. `http://100.x.x.x:8787`); only the friendly HTTPS URL requires the toggle.

**Update the app.** The desktop app pulls new versions automatically. For the install script, re-run the same `curl … | bash` line; it replaces the running container without touching your data.

**Memory.** Conversation memory persists automatically across sessions. To wipe it (start fresh, troubleshoot, or hand off the install) see [docs/RESET.md](docs/RESET.md).

---

## Supported providers

Most users start with **OpenRouter** — one key, hundreds of models. Add more from Settings → Providers when you need direct access or specific pricing.

| Provider | How to add | Notes |
|---|---|---|
| **OpenRouter** | Onboarding wizard, then Settings | Recommended starting point. Hundreds of models via a single API. |
| **Anthropic** | Settings → Providers | Direct Claude API |
| **OpenAI** | Settings → Providers | Direct GPT API |
| **Google Gemini** | Settings → Providers | Google AI Studio |
| **xAI (Grok)** | Settings → Providers | Direct xAI API |
| **DeepSeek** | Settings → Providers | Direct |
| **Mistral AI** | Settings → Providers | Direct |
| **Z.ai (GLM)** | Settings → Providers | Direct |
| **Kimi** | Settings → Providers | Coding-tuned models |
| **MiniMax** | Settings → Providers | Global + China endpoints |
| **NVIDIA NIM** | Settings → Providers | Hosted NIM endpoints |
| **OpenCode-Zen / Go** | Settings → Providers | Code-specialized providers |
| **Ollama Cloud** | Settings → Providers | Hosted Ollama (`ollama.com`) |
| **Local Ollama** | Auto-detected — no key needed | Fox probes `host.docker.internal:11434` then `localhost:11434` on Settings open. If a daemon is running, it appears as its own tile with installed models, one-click switching, **one-click pull from a recommended set** when no models are installed, and delete from inside the chat (since v0.3.1). Linux requires Fox v0.3.0+ (containers built before then need to be re-created — they're missing the `--add-host=host.docker.internal:host-gateway` flag). |
| **LM Studio** | Settings → Providers | Local OpenAI-compatible endpoint |
| **GitHub Copilot, Nous Portal, Codex, Qwen** | `hermes` CLI inside the container | OAuth-only — managed via the bundled Hermes CLI, not the Settings UI |

---

## Architecture

| Component | Purpose |
|-----------|---------|
| [Hermes Agent](https://github.com/NousResearch/hermes-agent) | AI agent core — LLM orchestration, tools, skills (Fox tracks virgin upstream via overlay; see `docs/architecture/upstream-overlay.md`) |
| [Hermes WebUI](https://github.com/nesquena/hermes-webui) | Browser-based chat interface (Fox tracks virgin upstream via overlay; see `docs/architecture/upstream-overlay.md`) |
| mem0 + Qdrant | Persistent memory with local vector search |
| Tailscale | Optional VPN tunneling and automatic HTTPS |
| supervisord | Process management inside the container |

**Container vs. data:** the published Docker image bundles Hermes agent and webui source (from `forks/` submodules) at **build** time. The container's `/data` volume holds your config, databases, logs, and Tailscale state. Updating Hermes for end users means pulling a newer image, not re-cloning at runtime.

**Tech stack:** Electron 28 (desktop wrapper) · Python 3.11 (Hermes Agent + WebUI) · Qdrant (vector DB) · mem0 (memory layer) · supervisord (process management) · Tailscale (remote access) · Docker (packaging). Hermes WebUI is intentionally vanilla — Python `http.server` + plain JavaScript, no SPA framework — so the chat UI loads instantly on any device.

---

## Need a fresh start?

See **[docs/RESET.md](docs/RESET.md)** for the full reset procedure (Windows and macOS).

---

## Documentation

- [CHANGELOG.md](CHANGELOG.md) — release history
- [CONTRIBUTING.md](CONTRIBUTING.md) — how to contribute
- [SECURITY.md](SECURITY.md) — vulnerability reporting
- [docs/DEV_MODE.md](docs/DEV_MODE.md) — local development with bind-mounted submodules
- [docs/RELEASE_WORKFLOW.md](docs/RELEASE_WORKFLOW.md) — how releases are cut
- [docs/RESET.md](docs/RESET.md) — full reset / clean install
- [qa/SMOKE_CHECKLIST.md](qa/SMOKE_CHECKLIST.md) — pre-release verification gate

---

## FAQ

**Is it really private?**
Yes. The app runs on your computer. The only outbound traffic is the API call to your AI provider when you send a message. Conversations, memory, and files never leave your machine.

**Do I need to know how to code?**
No. Download the desktop app, run it, and follow the setup wizard in your browser. No terminal, no commands, no config files.

**What's an API key and where do I get one?**
An API key is a token that lets the app talk to an AI service. Create a free account at **[openrouter.ai](https://openrouter.ai)** and generate a key — the setup wizard asks you to paste it in. Top up a few dollars of credit there to send messages.

**Can I use it on my phone?**
Yes. Choose the Tailscale option during setup; you'll get an HTTPS URL you can open from any device on your tailnet — phone, tablet, another laptop.

**How much does it cost?**
The app itself is free and open source. You only pay for AI usage at your provider (typically a few cents per conversation, depending on the model).

---

## Roadmap

What we're working on next. No promises on dates — this is a small team — but this is the direction. v0.7.x is the stabilization cycle: v0.8.0 only ships once the verification rebuild is complete and the project is genuinely solid.

**Just shipped (v0.7.33–v0.7.44)**
- **7-step progress window** — real-time install progress with diagnostics pane, post-reboot Docker resume, smooth animations (v0.7.33–v0.7.40)
- **Fox branding in WebUI** — custom bot name, avatar, and empty-state branding via build-time patches (v0.7.23)
- **Ollama local model routing** — correct provider routing, colon-split fixes across frontend and backend, picker dedup (v0.7.42–v0.7.44)
- **Windows installer overhaul** — install-mode selection, HyperV/WSL2 detection, uninstaller data cleanup, Docker Desktop uninstall integration (v0.7.22–v0.7.27)

**v0.7.x stabilization in flight**
- **#336 — Wizard local-fallback error on Windows** — needs Win11 Docker logs for diagnosis
- **On-device smoke backlog** — 14 POST-RELEASE items unchecked since v0.7.17
- **Upstream anchor drift (#439)** — blocks the next upstream bump

**Eventually (v0.8.0 and beyond)**
- UI overhaul — a clean, professional design system replacing the current developer-tool look
- Network isolation mode for enterprise — air-gapped Docker deployment
- Routines — teach Fox multi-step workflows via conversation, runs on a schedule
- Content-safety classifier (Llama Guard 3 1B), guardrail plugins, business-rule validators — opt-in safety layer for users who want it

**Have an idea?** [Open a discussion](https://github.com/fox-in-the-box-ai/fox-in-the-box/discussions) or [file a feature request](https://github.com/fox-in-the-box-ai/fox-in-the-box/issues/new).

---

## Support

Open an [issue](https://github.com/fox-in-the-box-ai/fox-in-the-box/issues/new/choose) or start a [discussion](https://github.com/fox-in-the-box-ai/fox-in-the-box/discussions).

---

## Acknowledgments

Fox in the Box stands on the shoulders of:

- **[Hermes Agent](https://github.com/NousResearch/hermes-agent)** by NousResearch — the agent core.
- **[Hermes WebUI](https://github.com/NousResearch/hermes-webui)** — the browser chat interface.
- **[Qdrant](https://qdrant.tech)** — vector database powering memory.
- **[mem0](https://github.com/mem0ai/mem0)** — memory layer.
- **[Tailscale](https://tailscale.com)** — secure remote access and HTTPS.
- **[Electron](https://www.electronjs.org)** — desktop app framework.
- **[Brave Search](https://brave.com/search/)** — web search via MCP.

---

## License

MIT — see [LICENSE](LICENSE).
