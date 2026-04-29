# Fox in the Box 🦊📦

All-in-one self-hosted AI assistant platform packaged as a single Docker container with native desktop apps for Windows and macOS.

## 🚀 Quick Start

```bash
# Pull and run (will be available after first release)
docker run -d \
  --name fox-in-the-box \
  --cap-add=NET_ADMIN \
  -p 8787:8787 \
  ghcr.io/fox-in-the-box-ai/cloud:stable
```

Open browser: http://localhost:8787

## ✨ Features

- **Single container** - Everything included: AI agent, web UI, memory, VPN
- **Web-based onboarding** - No terminal commands needed for setup
- **Cross-platform** - Docker container + Electron desktop apps
- **Self-hosted** - Your data stays on your machine
- **MIT licensed** - Open source and free

## 🏗️ Architecture

Fox in the Box bundles:

| Component | Purpose |
|-----------|---------|
| **Hermes Agent** | AI agent core (LLM orchestration, tools) |
| **Hermes WebUI** | Browser-based chat interface |
| **mem0_oss** | Persistent memory with vector search |
| **Tailscale** | VPN, HTTPS, remote access |

## 📦 Installation Options

1. **Docker Container** (All platforms)
2. **Electron Desktop App** (Windows/macOS)
3. **Manual Installation** (Advanced)

## 🔧 Development

```bash
# Clone repository with submodules
git clone --recurse-submodules https://github.com/fox-in-the-box-ai/fox-in-the-box.git
cd fox-in-the-box

# Build Docker image
docker build -f packages/integration/Dockerfile -t fitb:local .
```

## 📄 License

MIT License - see [LICENSE](LICENSE) file.

## 🤝 Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidelines.
