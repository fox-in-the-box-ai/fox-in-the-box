# Fox in the Box

[![GitHub Sponsors](https://img.shields.io/github/sponsors/bsgdigital?label=Sponsor&logo=githubsponsors&color=ea4aaa)](https://github.com/sponsors/bsgdigital)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)](https://github.com/fox-in-the-box-ai/fox-in-the-box/releases)
[![Release](https://img.shields.io/github/v/release/fox-in-the-box-ai/fox-in-the-box)](https://github.com/fox-in-the-box-ai/fox-in-the-box/releases/latest)

> A private AI assistant that runs on your computer. No subscriptions, no cloud lock-in, no data leaving your machine without your say-so.

Fox in the Box bundles a full AI assistant — agent, chat UI, persistent memory, and secure remote access — into one app. Bring an OpenRouter API key, run the installer, and start chatting in minutes.

<!-- TODO: add a screenshot or short GIF of the chat UI here -->

---

## What you get

- **Runs on your computer.** Conversations, memory, and files stay on your machine.
- **Remembers across sessions.** Your assistant picks up where you left off.
- **Reachable from anywhere.** Optional secure HTTPS access from your phone or another laptop via Tailscale.
- **Setup in the browser.** No terminal needed for the desktop app. Paste your API key, click Open Fox, start chatting.
- **Open source.** MIT licensed. You can read every line of what's running.

---

## How it works

Fox in the Box runs a small private server on your computer inside something called a **Docker container** — think of it as a sealed box that keeps everything organized and separate from the rest of your system. The desktop app manages this box for you automatically.

When you send a message, the app forwards it to your chosen AI provider (like OpenRouter or Anthropic) over the internet, gets a response, and displays it in the chat. The only thing that leaves your computer is the message itself — your conversation history, files, and memory stay on your machine.

**Memory** is what makes Fox different from a plain chatbot. It remembers what you've talked about across sessions — your preferences, your projects, the context of previous conversations. This memory is stored locally in a small database on your computer, not in the cloud.

**Remote access** is optional. If you want to chat with your assistant from your phone or another computer, Fox can set up a secure private link using Tailscale (a free personal VPN). Only your own devices can reach it — nobody else can see or access your assistant.

**Updates** are simple: the desktop app pulls the latest version automatically. If you installed via the terminal script, run it again — it replaces the old version and keeps your data.

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
```

See [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md) for the full build flow.

---

## Requirements

- **Windows 10** or later, **macOS 12** (Monterey) or later, or **any Linux** with Docker.
- An **[OpenRouter](https://openrouter.ai)** API key (required for setup). Additional providers — Anthropic, OpenAI, etc. — are configurable in Settings after install.

---

## After setup

The setup wizard runs once. After that the app handles itself — but a few things are worth knowing.

**Add or switch providers.** OpenRouter is configured during onboarding. To add Anthropic, OpenAI, Google Gemini, DeepSeek, Mistral, or any other supported provider: open Fox, click the **gear icon** in the top bar → **Settings → Providers** → paste the API key → **Save**. The new provider is live within seconds — no restart, no terminal. Overwrite a key to rotate it; click **Remove** to clear it.

**Pick a model.** The model picker in the chat lists every model your configured providers offer. Switch any time; the conversation thread is preserved.

**Update the app.** The desktop app pulls new versions automatically. For the install script, re-run the same `curl … | bash` line; it replaces the running container without touching your data.

**Memory.** Conversation memory persists automatically across sessions. To wipe it (start fresh, troubleshoot, or hand off the install) see [docs/RESET.md](docs/RESET.md).

---

## Architecture

| Component | Purpose |
|-----------|---------|
| [Hermes Agent](https://github.com/fox-in-the-box-ai/hermes-agent) | AI agent core — LLM orchestration, tools, skills |
| [Hermes WebUI](https://github.com/fox-in-the-box-ai/hermes-webui) | Browser-based chat interface |
| mem0 + Qdrant | Persistent memory with local vector search |
| Tailscale | Optional VPN tunneling and automatic HTTPS |
| supervisord | Process management inside the container |

**Container vs. data:** the published Docker image bundles Hermes agent and webui source (from `forks/` submodules) at **build** time. The container's `/data` volume holds your config, databases, logs, and Tailscale state. Updating Hermes for end users means pulling a newer image, not re-cloning at runtime.

---

## Need a fresh start?

See **[docs/RESET.md](docs/RESET.md)** for the full reset procedure (Windows and macOS).

---

## Documentation

- [CHANGELOG.md](CHANGELOG.md) — release history
- [CONTRIBUTING.md](CONTRIBUTING.md) — how to contribute
- [SECURITY.md](SECURITY.md) — vulnerability reporting
- [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) — community standards
- [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md) — development setup
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — system design
- [docs/RESET.md](docs/RESET.md) — full reset / clean install

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

What we're working on next. No promises on dates — this is a small team — but this is the direction.

**Coming soon**
- Hostname customization during desktop app setup
- First-run guided conversation to help new users explore what Fox can do

**On the horizon**
- Local AI model support — run smaller models directly on your computer for offline use or provider outages
- Safety guardrails — PII detection, content filtering, and input/output validation
- Scriptable workflows — teach Fox multi-step routines specific to your business

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
