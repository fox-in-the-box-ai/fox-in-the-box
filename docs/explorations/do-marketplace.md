# DigitalOcean Marketplace — Path Assessment

*Exploration only. No code changes. 2026-06-01.*

---

## 1. Current Distribution Inventory

### 1.1 How Fox packages and provisions today

Fox ships as a **desktop app** (Electron for Windows/macOS) that manages a
**single Docker container** per user. The container runs the full stack:
Hermes Agent, Hermes WebUI, Qdrant, mem0, Tailscale, and llama-server.

**Container build pipeline:**

| File | Purpose |
|------|---------|
| `packages/integration/Dockerfile` | Multi-stage build: python:3.11-slim base, downloads qdrant + llama-server binaries, COPYs hermes-agent + hermes-webui + fox-overlay, applies patch series, pip installs |
| `packages/integration/entrypoint.sh` | Container startup: first-run bootstrap, /data directory tree, app symlinks, version migration, Tailscale Serve setup, hands off to supervisord |
| `packages/integration/supervisord.conf` | Process manager: tailscaled, ts-operator-watchdog, qdrant, hermes-gateway, hermes-webui, llama-server (autostart=false) |
| `packages/integration/default-configs/` | hermes.yaml (agent config), qdrant.yaml, onboarding.json |
| `packages/integration/scripts/` | migrate.sh, run-with-env.sh, tailscale-operator-watchdog.sh, dev-init.sh |
| `.github/workflows/build-container.yml` | Multi-arch build (linux/amd64 + linux/arm64), manifest-list publish to ghcr.io |
| `.github/workflows/release.yml` | Tag-driven release: SMOKE_LOG gate, builds container + Electron + .deb, creates GitHub Release |

**Desktop provisioning (Electron → Docker):**

| File | Purpose |
|------|---------|
| `packages/electron/src/docker-manager.js` (725 lines) | Dockerode wrapper: container create/start/stop/remove, image pull with progress, socket auto-detection, diagnostics |
| `packages/electron/src/startup-orchestrator.js` (326 lines) | 7-phase startup state machine: check_system → docker_install → docker_start → download_image → start_container → wait_services → connect_network |
| `packages/electron/src/health-check.js` (133 lines) | Poll GET /health until 200 + `{"status":"ok"}`, configurable timeout/interval, failFastCheck callback |
| `packages/electron/src/app-urls.js` | Hardcoded `APP_ORIGIN = http://127.0.0.1:8787` |

**Headless install paths (no desktop):**

| File | Purpose |
|------|---------|
| `packages/scripts/install.sh` | Non-interactive Linux/macOS installer: installs Docker, pulls image, creates systemd units, supports FOX_ACCESS_MODE=1\|2\|3 |
| `packages/install-core/install-core.sh` | Shared install logic (Docker + .deb): binary downloads, repo sync, patch application, pip install, supervisord.conf generation |
| `packages/install-core/preflight.sh` | Bare-metal pre-start: directory bootstrap, config seeding, version migration, Tailscale Serve |
| `packages/deb/` | .deb packaging: build.sh, control scripts, systemd templates |

### 1.2 What's single-instance-able today vs. desktop-tied

**Already headless-capable (works on a VPS without modification):**
- The container image (`ghcr.io/fox-in-the-box-ai/cloud:stable`) — runs standalone with `docker run -d -p 8787:8787 -v /data:/data`
- `install.sh` — non-interactive, supports `FOX_ACCESS_MODE=1` (bind 0.0.0.0)
- `install-core.sh` + `preflight.sh` — bare-metal path, systemd units
- All config injection via env vars in `hermes.env`
- `/data` volume mount for persistence

**Tied to desktop host (would not ship to Marketplace):**
- `packages/electron/` (entire directory) — Windows/macOS desktop wrapper
- `docker-manager.js`, `startup-orchestrator.js` — Electron-specific orchestration
- `app-urls.js` — hardcoded `127.0.0.1:8787`
- `electron-builder.yml`, signing configs, NSIS installer

**Needs adaptation for public-network VPS:**
- Auth: standalone mode trusts the LAN (§0.5 of ENTERPRISE_ARCHITECTURE.md). On a public DO Droplet, port 8787 is internet-exposed. Upstream Hermes password auth (`HERMES_WEBUI_PASSWORD`) is the only gate — it works but was designed for trusted networks.
- First-boot config: onboarding wizard runs in the browser at `:8787/setup`. On a Droplet, the user must reach this page over the internet to complete setup. This works if the port is open, but there's no HTTPS by default.
- Tailscale: optional, works as-is. Useful for private access without exposing 8787.

### 1.3 File count

| Category | Files | Headless-ready |
|----------|-------|---------------|
| Container build + runtime | 12 | 12 |
| Desktop app (Electron) | 18 | 0 |
| Install scripts (headless) | 10 | 10 |
| CI/CD workflows | 10 | N/A |
| Config/versioning | 4 | 4 |
| **Total** | **54** | **26** |

---

## 2. DO Marketplace Vendor Requirements

### 2.1 Listing types

| Type | Format | Monetizable | Fit for Fox |
|------|--------|-------------|-------------|
| **Droplet 1-Click** | Packer-built snapshot (Ubuntu LTS) | No (infra billing only) | High — all AI tools on DO use this |
| **Kubernetes 1-Click** | Helm chart + deploy/upgrade/uninstall scripts | No | Medium — Fox isn't K8s-native yet |
| **License Add-On** | Attached to Droplet 1-Click | Yes (75/25 rev share) | High — monetization path |
| **SaaS Add-On** | External SaaS, OIDC SSO | Yes (75/25 rev share) | Low — Fox is self-hosted, not SaaS |
| **Blueprint** | Terraform HCL | No | Low — single Droplet is simpler |
| **1-Click Model** | GPU Droplet snapshot | No | Low — Fox isn't a model server |

### 2.2 Droplet 1-Click build process

1. **Packer template** builds on DO builder plugin (v1.4.1+)
2. **Base image**: Ubuntu 24.04 LTS (recommended)
3. **Provisioning scripts**: install Docker, pull Fox image, configure systemd, write first-boot scripts
4. **First-boot scripts**: placed in `/var/lib/cloud/scripts/per-instance/` — run once via cloud-init on Droplet creation. Generate random admin password, configure UFW, write MOTD.
5. **`img_check.sh` validation** (mandatory): OS check, cloud-init installed, firewall active, no root password/SSH keys, bash history cleared, logs cleared, no DO agent present. Exit 0 = pass, 2 = fail (blocks submission).
6. **Cleanup**: security updates, delete history/keys, enable UFW

### 2.3 Security/hardening checklist

| Requirement | Fox status |
|-------------|-----------|
| UFW firewall enabled | Must add: open SSH (22) + Fox (8787) only |
| No root password | Must clear during image build |
| No SSH keys in image | Must clear during image build |
| cloud-init installed | Included in DO base images |
| Security updates applied | Must run during image build |
| Logs cleared | Must clear during image build |
| No DO agent in snapshot | Must remove during image build |

### 2.4 Monetization mechanics

- **License Add-On**: vendor attaches license tiers (Free, Pro, Enterprise) to their Droplet 1-Click app in the Vendor Portal. Customer selects tier at Droplet creation. License injected into Droplet.
- **Revenue share**: vendor receives **75%** of net collected add-on revenue. DO retains 25%.
- **Payment**: within 60 days after month-end. Wire or ACH.
- **Pricing changes**: 90 days advance notice required.
- **Tax**: vendor responsible. W-9 (US) or W8-BEN-E (non-US) required.

### 2.5 Existing comparable listings

| App | Type | Notes |
|-----|------|-------|
| **Open WebUI** | Droplet 1-Click | Listed at `marketplace.digitalocean.com/apps/open-webui` |
| **Ollama with Open WebUI** | Droplet 1-Click | Bundle listing |
| **OpenClaw** | Droplet 1-Click | Personal AI assistant, WhatsApp/Telegram |
| **n8n** | Droplet 1-Click | Workflow automation with AI |
| **Hermes Agent** | **Not listed** | Does not exist on DO Marketplace |

**Pattern**: all self-hosted AI tools use Droplet 1-Click. None use K8s 1-Click or SaaS Add-On.

### 2.6 Vendor onboarding

- Portal: `cloud.digitalocean.com/vendorportal`
- Apply: `marketplace.digitalocean.com/vendors`
- Contact: `one-clicks-team@digitalocean.com`
- Legal: accept Marketplace Vendor Terms, provide tax forms, grant trademark license for promotion
- Vendor API: `PATCH /api/v1/vendor-portal/apps/<id>` for CI/CD image updates

**Sources:**
- https://github.com/digitalocean/marketplace-partners
- https://github.com/digitalocean/droplet-1-clicks
- https://github.com/digitalocean/droplet-1-clicks/blob/master/DEVELOPER-GUIDE.md
- https://github.com/digitalocean/marketplace-kubernetes
- https://marketplace.digitalocean.com/vendors/getting-started-as-a-digitalocean-marketplace-vendor
- https://www.digitalocean.com/legal/marketplace-vendor-terms
- https://www.digitalocean.com/blog/introducing-software-license-subscriptions-on-digitalocean-marketplace

---

## 3. Gap Analysis

### 3.1 Droplet 1-Click App

**What Fox needs to add/change:**

| Gap | Effort | Description |
|-----|--------|-------------|
| Packer template | S (1 day) | `packer/do-marketplace.pkr.hcl` — Ubuntu 24.04, install Docker, pull `:stable`, install systemd units, configure UFW, write first-boot script |
| First-boot script | S (1 day) | `/var/lib/cloud/scripts/per-instance/001_fox_setup` — generate random `HERMES_WEBUI_PASSWORD`, write to `/data/config/hermes.env`, start Fox, print credentials in MOTD |
| UFW configuration | XS (hours) | Open ports 22 (SSH) + 8787 (Fox). Close everything else. |
| MOTD / getting-started | XS (hours) | `/etc/update-motd.d/99-fox` — print Fox URL + generated password on SSH login |
| img_check.sh compliance | XS (hours) | Cleanup script: clear history, keys, logs, remove DO agent |
| Vendor Portal listing | S (1 day) | App name, description, logo, getting-started doc, support URL, min Droplet size |
| **Trusted-LAN assumption** | **BLOCKER** | Port 8787 on a public Droplet is internet-exposed. Upstream `HERMES_WEBUI_PASSWORD` provides password-based auth, which works but was not hardened for public internet. Need: (a) generate strong random password at first boot, (b) force password setup before any other access, (c) consider Caddy/nginx reverse proxy with auto-TLS. |

**Total effort**: ~3-4 days for a basic listing (no TLS). ~1 week with a Caddy reverse proxy for HTTPS.

### 3.2 Kubernetes 1-Click App

**What Fox needs to add/change:**

| Gap | Effort | Description |
|-----|--------|-------------|
| Helm chart | M (3-5 days) | Deployment, PVC, Service, ConfigMap, Ingress. Fox is a single container so the chart is straightforward, but no Helm chart exists today. |
| deploy/upgrade/uninstall scripts | S (1 day) | Wrapper scripts per DO K8s 1-Click convention |
| Persistent storage | S (1 day) | PVC for `/data` volume |
| Health probes | XS | Already has `/health` endpoint |
| Ingress + TLS | M (2-3 days) | Need cert-manager + Ingress for public access |

**Total effort**: ~1-2 weeks. More work than Droplet 1-Click, and no K8s AI tools exist on DO Marketplace yet — unproven category.

### 3.3 License Add-On (monetization)

**What Fox needs to add/change (on top of Droplet 1-Click):**

| Gap | Effort | Description |
|-----|--------|-------------|
| License tier definition | S (1 day) | Free (single user, local models only) vs. Pro (cloud providers, Tailscale) vs. Enterprise (control plane) — ties to ADR-0001 |
| License validation | M (2-3 days) | First-boot script reads injected license, writes capability flags. Fox's existing `CapabilityFlags` system (INSTANCE_CONTRACT.md §4.4) is the enforcement mechanism. |
| License-gated features | M (2-3 days) | Map license tiers to capability toggles. The `.fox-removals` + `CapabilityFlags` machinery already supports this. |
| Vendor Portal config | S (1 day) | Define tiers, pricing, attach to 1-Click listing |

**Total effort**: ~1-2 weeks on top of the Droplet 1-Click work. Requires ADR-0001 (licensing model) to be resolved first.

---

## 4. Decision Matrix

| | Droplet 1-Click | K8s 1-Click | License Add-On |
|---|---|---|---|
| **Effort** | 3-4 days (no TLS) / 1 week (with TLS) | 1-2 weeks | 1-2 weeks (on top of Droplet) |
| **Fit with control-plane thesis** | High — single-instance managed Fox, same as demo tier | Medium — K8s plugin exists in BACKLOG (PLUG-03) but not built | High — license tiers map to capability flags, forward-compatible with enterprise |
| **Monetization** | None (DO bills infra only) | None | Yes (75/25 rev share) |
| **Market precedent** | All AI tools use this | No AI tools on DO K8s | Plesk is the only vendor so far |
| **Blocked on** | Trusted-LAN assumption (§0.5) | Helm chart + K8s plugin | ADR-0001 (licensing model) |
| **Competitive** | Open WebUI already listed; Fox differentiates on memory + overlay + Tailscale | No competition | Novel — no AI assistant has license-gated 1-Click |

### 4.1 Recommended path

**Phase 1: Droplet 1-Click (free listing)**
- Smallest viable milestone: Packer template + first-boot script + UFW + MOTD
- Ship as "Fox in the Box" alongside the existing Open WebUI listing
- Differentiation: persistent memory (mem0), local AI fallback (Ollama/llama-server), Tailscale remote access, Fox overlay (branding, silent failover, onboarding wizard) — all in one 1-Click
- **Must resolve**: generate strong random password at first boot, force setup before access. Caddy reverse proxy with auto-TLS (Let's Encrypt) strongly recommended for public Droplets.
- **Timeline**: 1 week to submission, ~1 week for DO review

**Phase 2: License Add-On (monetization)**
- Attach license tiers to the 1-Click listing after ADR-0001 resolves
- Free tier: single user, local models, community support
- Pro tier: cloud providers, Tailscale, priority support
- Enterprise tier: control plane features (Phase 3/5 architecture)
- **Blocked on**: ADR-0001 (licensing model)

**Phase 3: K8s 1-Click (if demand)**
- Only pursue if customers request K8s deployment
- Depends on PLUG-03 (K8s deployment plugin) from the Phase 3 backlog

### 4.2 Open questions / blockers

| # | Question | Severity | Owner |
|---|----------|----------|-------|
| 1 | **Trusted-LAN assumption on public internet** — Port 8787 exposed on a Droplet. `HERMES_WEBUI_PASSWORD` auth works but was designed for LAN. Is password auth sufficient for v1, or must we ship with a TLS reverse proxy? | **BLOCKER** | Founders |
| 2 | **ADR-0001 (licensing model)** — License Add-On tiers require knowing the open/commercial boundary. Droplet 1-Click (free) can ship without this. | Blocks Phase 2 | Founders |
| 3 | **Hermes Agent not on DO Marketplace** — despite the user's assumption, it's NOT listed. Open WebUI IS listed. Fox would be adjacent to Open WebUI, not Hermes. | Informational | — |
| 4 | **Vendor Portal access** — need to apply at `marketplace.digitalocean.com/vendors` and wait for credentials. Lead time unknown. | Process | Founders |
| 5 | **Image update CI/CD** — DO Vendor API supports programmatic snapshot updates. Should integrate with `build-container.yml` so `:stable` bumps auto-update the Marketplace listing. | Phase 2 | Engineering |
| 6 | **Droplet size recommendation** — Fox runs mem0 + Qdrant + llama-server. Minimum viable: 2 GB RAM / 1 vCPU for cloud-only providers. With local models (llama-server): 8 GB RAM / 4 vCPU. Need benchmarking. | TO RATIFY | Engineering |
