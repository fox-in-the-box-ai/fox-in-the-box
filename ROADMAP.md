# Fox in the Box — Roadmap

**Last updated:** April 28, 2026

---

## v0.1 — Hackathon Release (deadline: May 3, 2026 PST)

Goal: working product across all three platforms, clean onboarding, polished UX.

### Scope

**In:**
- Single Docker container (Hermes Agent + Hermes WebUI from our forks, mem0+Qdrant, Tailscale, supervisord)
- Simple HTML/JS onboarding wizard at `/setup` — OpenRouter key entry + Tailscale login
- Windows: Electron app (.exe via Electron Builder, unsigned)
- macOS: shell script (brew-based Docker install)
- Linux: shell script (apt-based Docker install)
- GitHub Actions: build + push container to GHCR, build Electron Windows app
- Data directory structure (`~/.foxinthebox` with config / data / cache separation)
- HTTPS via Tailscale Serve (PWA-ready)

**Out:**
- macOS .dmg (no Apple dev cert yet → script only)
- Memos notes app
- OAuth flows (OpenRouter API key entry is enough)
- Electron auto-updater (tray menu item links to GitHub Releases page instead)
- React wizard
- Git submodules / upstream sync workflow
- Rollback
- Multi-language UI

---

### Sprint Plan

#### Day 1 — Monorepo + Container skeleton
- [ ] Create GitHub forks: `fox-in-the-box-ai/hermes-agent`, `fox-in-the-box-ai/hermes-webui`
- [ ] Set up monorepo `fox-in-the-box` with pnpm workspaces:
  - `packages/integration/` — Dockerfile, supervisord.conf, entrypoint.sh, default-configs
  - `packages/electron/` — Electron desktop app
  - `packages/scripts/` — install.sh (Linux + macOS), dev utilities
- [ ] Dockerfile: Python 3.11 slim, install hermes + webui from forks via `pip install git+https://...@main`, Qdrant binary, Tailscale, supervisord
- [ ] supervisord.conf: hermes-gateway, hermes-webui, qdrant, tailscaled
- [ ] entrypoint.sh: first-run detection, config copy from defaults, permissions, launch supervisord
- [ ] Container runs locally, WebUI reachable at localhost:8787

#### Day 2 — Onboarding + data layer
- [ ] `/setup` route in Hermes WebUI fork (plain HTML/JS, served by existing Python backend)
- [ ] Step 1: OpenRouter API key → saves to `/data/config/hermes.env`
- [ ] Step 2: Tailscale login — backend triggers `tailscale login`, polls status, shows login URL + QR code
- [ ] Step 3: Done → redirect to main chat UI
- [ ] onboarding.json state (completed: true/false) — entrypoint redirects to `/setup` if incomplete
- [ ] Default config templates in `packages/integration/default-configs/`
- [ ] End-to-end test: fresh container → onboarding → chat with OpenRouter model → memory persists after restart

#### Day 3 — Platform packaging
- [ ] **Electron app (Windows + macOS unsigned .app):**
  - Docker Desktop detection → winget install (Windows) / brew install (macOS) if missing
  - `docker pull` + `docker run` with correct volume + port + cap-add flags
  - System tray: Start / Stop / Open Fox / Quit
  - Open `http://localhost:8787` in default browser on start
  - Electron Builder config: Windows .exe NSIS installer, macOS unsigned .app zip
- [ ] **install.sh (macOS + Linux):**
  - Detect OS → brew (macOS) or apt (Linux) for Docker
  - Pull container image from GHCR
  - Prompt: port-only / Tailscale / both
  - If Tailscale: stream logs, extract login URL, show + QR
  - Install systemd units on Linux (foxinthebox.service + foxinthebox-updater.service)
  - macOS: launchd plist for auto-start
  - Print access URL

#### Day 4 — CI/CD + polish
- [ ] GitHub Actions: `build-container.yml` — build + push to `ghcr.io/fox-in-the-box-ai/cloud:latest` on push to main
- [ ] GitHub Actions: `build-electron.yml` — build Windows .exe + macOS unsigned .zip, attach to GitHub Release
- [ ] UX pass on onboarding wizard (look + feel, error states, loading indicators)
- [ ] README quickstart (30-second install instructions for all three platforms)

#### Day 5 — Buffer / hackathon submission
- [ ] Integration smoke test on clean Windows VM + fresh Linux VPS
- [ ] Marketing website (Stan leads — one day, visuals already done)
- [ ] Hackathon submission

---

## v0.2 — Post-hackathon stabilisation (May / June 2026)

Focus: reliability, macOS proper packaging, dev workflow formalised.

- [ ] macOS signed .dmg (once Apple dev profile sorted)
- [ ] Electron auto-updater (`electron-updater` against GitHub Releases)
- [ ] Fork sync workflow documented and scripted (`pull-upstream.sh`, `rebase-patches.sh`)
- [ ] Proper upstream contribution workflow for generic bug fixes
- [ ] Container smoke test suite (pytest, runs in CI against built image)
- [ ] Rollback: keep previous image tag, "Roll back" option in tray menu
- [ ] Structured error handling + user-friendly error messages in onboarding
- [ ] WebUI update notification banner (container polls GHCR for new tag, shows banner, one-click restart)
- [ ] Signed Windows installer (code signing cert)

---

## v1.0 — Stable release (Q3 2026)

- [ ] Full React onboarding wizard (replaces plain HTML)
- [ ] Additional AI providers: OpenAI, Gemini, Anthropic (API key), Ollama (local)
- [ ] Memos notes app (iframe in WebUI sidebar) — drop if cross-origin issues unresolvable
- [ ] PWA manifest + service worker (installable on mobile)
- [ ] Bimonthly release cadence starts
- [ ] CONTRIBUTING.md + community setup (issue templates, PR template)
- [ ] Docker Compose "advanced mode" (optional, power users)

---

## Post-v1 (backlog)

- Multi-language UI
- Auto-backup before upgrades
- Plugin/skill marketplace
- Shared workspaces / collaboration (requires multi-user in Hermes upstream)
- White-label / rebrand support
- Self-hosted STT/TTS models
- Mobile native apps (iOS / Android)
