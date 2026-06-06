# DO Droplet 1-Click — Spec (Free Listing)

*Decision-ready. No monetization — decoupled from ADR-0001. 2026-06-01.*

*Builds on: `docs/explorations/do-marketplace.md`*

---

## 0. Scope

Ship Fox in the Box as a free DigitalOcean Droplet 1-Click App. A user clicks
"Create Droplet," picks Fox, and gets a running instance with TLS and
password auth — no terminal required beyond the initial SSH to retrieve
the generated password.

**Not in scope:** License Add-On (requires ADR-0001), K8s 1-Click (requires
Helm chart + PLUG-03), Tailscale integration in the Marketplace image (users
who want Tailscale can configure it after deploy — it works as-is).

---

## 1. Verified Repo Inventory

### 1.1 Container build + launch (12 files, all headless-capable)

| # | File | Purpose | Headless? |
|---|------|---------|-----------|
| 1 | `packages/integration/Dockerfile` | Multi-stage build: python:3.11-slim, qdrant, llama-server, hermes-agent+webui, fox-overlay, supervisord. `EXPOSE 8787 6333` (line 164). | Yes |
| 2 | `packages/integration/entrypoint.sh` (296 lines) | First-run bootstrap: /data tree, app symlinks, version migration, loads `hermes.env` (line 161–167), Tailscale Serve (line 220–280), exec supervisord. Does NOT set or generate `HERMES_WEBUI_PASSWORD`. | Yes |
| 3 | `packages/integration/supervisord.conf` | 6 services: tailscaled (:10), ts-operator-watchdog (:15), qdrant (:20), hermes-gateway (:30), hermes-webui (:40), llama-server (:50, autostart=false). WebUI env: `HERMES_WEBUI_HOST="0.0.0.0"` (line 142). | Yes |
| 4 | `packages/integration/default-configs/hermes.yaml` | Agent config: `server.host: 0.0.0.0`, `server.port: 8787` (lines 9–11). | Yes |
| 5 | `packages/integration/default-configs/qdrant.yaml` | `host: 0.0.0.0`, `http_port: 6333`, `grpc_port: 6334` (lines 5–8). Internal only — not host-mapped. | Yes |
| 6 | `packages/integration/default-configs/onboarding.json` | First-run marker `{"completed": false}`. | Yes |
| 7 | `packages/integration/scripts/migrate.sh` | Version migration helper. | Yes |
| 8 | `packages/integration/scripts/run-with-env.sh` | Env loader for supervised processes. | Yes |
| 9 | `packages/integration/scripts/tailscale-operator-watchdog.sh` | Grants foxinthebox Tailscale operator access. | Yes |
| 10 | `packages/integration/scripts/dev-init.sh` | Dev-mode helper. | Yes |
| 11 | `.github/workflows/build-container.yml` | Multi-arch build (amd64 + arm64), manifest-list push to `ghcr.io/fox-in-the-box-ai/cloud`. | CI |
| 12 | `.github/workflows/release.yml` | Tag-driven: SMOKE_LOG gate, builds container + Electron + .deb, creates GitHub Release. | CI |

### 1.2 HERMES_WEBUI_PASSWORD path (verified, 6 files)

| # | File | Line(s) | Behavior |
|---|------|---------|----------|
| 1 | `forks/hermes-webui/api/auth.py` | 292 | `os.getenv("HERMES_WEBUI_PASSWORD")` — env var checked first, overrides settings.json |
| 2 | `forks/hermes-webui/api/auth.py` | 303–305 | `is_password_auth_enabled()` — returns True if `get_password_hash() is not None` |
| 3 | `forks/hermes-webui/api/auth.py` | 353–355 | `is_auth_enabled()` — returns `is_password_auth_enabled() or are_passkeys_enabled()` |
| 4 | `forks/hermes-webui/server.py` | 529–539 | Warning on startup if binding to non-loopback without password |
| 5 | `forks/hermes-webui/api/routes.py` | 6439–6451 | Settings UI locked (409) when env var is set |
| 6 | `forks/hermes-webui/.env.docker.example` | 48 | `# HERMES_WEBUI_PASSWORD=change-me-to-something-strong` — commented example only |

**Confirmed: no default value shipped anywhere.** Password is unset unless explicitly
provided. When unset, `is_auth_enabled()` returns False and auth is bypassed entirely.
On a public Droplet this means open access — the blocker the exploration identified.

### 1.3 Port binding (verified)

**Only port 8787 reaches the host.** All other services are container-internal.

| Service | Container bind | Host exposure | Cite |
|---------|---------------|---------------|------|
| Hermes WebUI | `0.0.0.0:8787` | Mode-dependent: `127.0.0.1:8787` (mode 2) or `0.0.0.0:8787` (modes 1/3) | `docker-manager.js:407–414` |
| Qdrant HTTP | `0.0.0.0:6333` | NOT mapped to host | `qdrant.yaml:5–8`, Dockerfile EXPOSE only |
| Qdrant gRPC | `0.0.0.0:6334` | NOT mapped to host | `qdrant.yaml:5–8` |
| llama-server | `127.0.0.1:8643` | NOT mapped to host, autostart=false | `supervisord.conf:162–174` |
| supervisord | `/run/fitb/supervisor.sock` (AF_UNIX) | NOT accessible from host | `supervisord.conf:10–16` |
| Tailscale | WireGuard tunnel | External (tailnet) if configured | `entrypoint.sh:269` |

### 1.4 X-Fox-Auth gate + managed-mode invariant

**Not applicable for this listing.** The `X-Fox-Auth` substitution
(`ENTERPRISE_ARCHITECTURE.md` §5.3) and the managed-mode boot invariant
(`FOX_PLANE_AUTH_SECRET` requires upstream auth, §5.4) are control-plane
features for managed deployments. A standalone DO Droplet runs without
`FOX_PLANE_AUTH_SECRET` — the substitution is a no-op, the invariant is
not triggered. The auth layer for the Marketplace listing is upstream's
`HERMES_WEBUI_PASSWORD` enforced via `check_auth()` at `auth.py:489–540`.

### 1.5 Desktop-host assumptions that leak into provisioning

| Assumption | Where | Headless replacement |
|------------|-------|---------------------|
| Access mode selection dialog | `docker-manager.js:370–394` | Hardcode mode 1 (`0.0.0.0`) — Caddy sits in front |
| `APP_ORIGIN = http://127.0.0.1:8787` | `app-urls.js` | Not used — Electron-only file, not in container |
| Docker socket auto-detection | `docker-manager.js:125–130` | Not used — container runs via `docker run`, not Dockerode |
| Docker Desktop install prompts | `startup-orchestrator.js:steps 1–3` | Not used — Docker pre-installed in Packer image |
| Workspace at `$HOME/Fox in the Box` | `preflight.sh:77` | Keep — foxinthebox user's home works for this |
| Tailscale browser auth | `entrypoint.sh:252–278` | Not applicable — Tailscale is opt-in post-deploy |

**Count: 6 assumptions.** 4 are Electron-only (irrelevant to container path).
2 are in the container/install path and either work as-is or are bypassed.
**No code changes needed in the container image itself.**

---

## 2. Image Build

### 2.1 Build tooling

DO requires Packer with the `digitalocean` builder plugin (v1.4.1+).

**Source:** https://github.com/digitalocean/marketplace-partners (official
image-build repo), https://github.com/digitalocean/droplet-1-clicks/blob/master/DEVELOPER-GUIDE.md

```
packer/
├── do-marketplace.pkr.hcl          # Packer template
├── scripts/
│   ├── 010-docker.sh               # Install Docker CE
│   ├── 020-fox.sh                   # Pull Fox image, write systemd unit + first-boot script
│   ├── 030-caddy.sh                 # Install Caddy reverse proxy
│   ├── 040-ufw.sh                   # Configure firewall: allow 22, 80, 443 only
│   └── 900-cleanup.sh              # DO img_check.sh compliance: clear history/keys/logs
├── files/
│   ├── etc/update-motd.d/99-fox    # Getting-started MOTD
│   └── var/lib/cloud/scripts/per-instance/001-fox-firstboot  # First-boot hardening
└── img_check.sh                    # DO's validation script (copied from marketplace-partners)
```

### 2.2 What goes in the snapshot vs. configured at first boot

**In the snapshot (immutable, baked at Packer build time):**
- Ubuntu 24.04 LTS base
- Docker CE installed and enabled
- Fox `:stable` image pre-pulled (`ghcr.io/fox-in-the-box-ai/cloud:stable`)
- Caddy installed (apt repo)
- UFW configured: allow 22/tcp, 80/tcp, 443/tcp — deny everything else
- Systemd unit: `foxinthebox.service` (manages the Docker container)
- Systemd unit: `caddy.service` (reverse proxy)
- First-boot script at `/var/lib/cloud/scripts/per-instance/001-fox-firstboot`
- MOTD at `/etc/update-motd.d/99-fox`
- DO compliance: no root password, no SSH keys, history cleared, logs cleared

**At first boot (per-instance, dynamic):**
- Generate 32-char random password → write to `/data/config/hermes.env` as `HERMES_WEBUI_PASSWORD`
- Write Caddy config: reverse proxy `https://<droplet-ip>:443` → `http://127.0.0.1:8787`
- Start Fox container (bound to `127.0.0.1:8787` — NOT 0.0.0.0)
- Verify `/health` returns 200
- Write password to `/root/.fox-credentials` (readable only by root)
- Update MOTD with the generated password

### 2.3 Reproducible build

- No secrets baked into the snapshot. Password generated per-instance at first boot.
- No credentials in the Packer template. `DIGITALOCEAN_API_TOKEN` is a build-time env var, never in the image.
- Fox image referenced by digest pin (`:stable` resolves to a content-addressed digest via `versions.toml`).
- Packer build is deterministic: same template → same image (minus timestamps).

---

## 3. First-Boot Hardening

### 3.1 Password generation

```bash
#!/bin/bash
# /var/lib/cloud/scripts/per-instance/001-fox-firstboot
# Runs once per Droplet via cloud-init. Generates admin password,
# configures Caddy TLS, starts Fox.
set -euo pipefail

DATA_DIR="/mnt/foxdata"
HERMES_ENV="$DATA_DIR/config/hermes.env"

# ── 1. Generate strong random password ──────────────────────────────────────
FOX_PASSWORD=$(openssl rand -base64 24 | tr -d '/+=' | head -c 32)
if [ -z "$FOX_PASSWORD" ] || [ ${#FOX_PASSWORD} -lt 24 ]; then
    echo "FATAL: password generation failed — refusing to start" >&2
    exit 1  # fail closed
fi

# ── 2. Write to hermes.env ──────────────────────────────────────────────────
mkdir -p "$DATA_DIR/config"
echo "HERMES_WEBUI_PASSWORD=$FOX_PASSWORD" > "$HERMES_ENV"
chmod 600 "$HERMES_ENV"

# ── 3. Configure Caddy (auto-TLS via Let's Encrypt) ────────────────────────
DROPLET_IP=$(curl -sf http://169.254.169.254/metadata/v1/interfaces/public/0/ipv4/address)
cat > /etc/caddy/Caddyfile << EOF
$DROPLET_IP {
    reverse_proxy 127.0.0.1:8787
}
EOF
systemctl restart caddy

# ── 4. Start Fox container (localhost-only — Caddy in front) ────────────────
docker run -d --name fox-in-the-box \
    --restart unless-stopped \
    --cap-add=NET_ADMIN --device /dev/net/tun \
    --sysctl net.ipv4.ip_forward=1 \
    -p 127.0.0.1:8787:8787 \
    -v "$DATA_DIR":/data \
    --env-file "$HERMES_ENV" \
    ghcr.io/fox-in-the-box-ai/cloud:stable

# ── 5. Wait for health ─────────────────────────────────────────────────────
for i in $(seq 1 60); do
    if curl -sf http://127.0.0.1:8787/health > /dev/null; then
        break
    fi
    sleep 2
done

# ── 6. Surface credentials ─────────────────────────────────────────────────
cat > /root/.fox-credentials << EOF
Fox in the Box — Admin Credentials
URL:      https://$DROPLET_IP
Password: $FOX_PASSWORD
EOF
chmod 600 /root/.fox-credentials
```

**Convention source:** DO recommends first-boot scripts in
`/var/lib/cloud/scripts/per-instance/` (cloud-init) and credentials surfaced
via MOTD on first SSH login.
Source: https://github.com/digitalocean/droplet-1-clicks/blob/master/DEVELOPER-GUIDE.md

### 3.2 Caddy reverse proxy + automatic TLS

Caddy provides automatic HTTPS via Let's Encrypt. No manual cert management.

**Config:**
```
$DROPLET_IP {
    reverse_proxy 127.0.0.1:8787
}
```

**Note on IP-based TLS:** Let's Encrypt issues certs for domain names, not
bare IPs. For IP-only access, Caddy will use a self-signed cert (browser
warning). For proper TLS, the user must point a domain at the Droplet IP and
update the Caddyfile. The MOTD should document this.

**Alternative:** ZeroSSL supports IP certificates. Caddy can use ZeroSSL as
an ACME provider. This is a configuration option, not a code change.
TO RATIFY: ship with self-signed (IP) or require domain setup.

### 3.3 Boot-time invariant

**In the Marketplace context, the invariant is simpler than the control-plane
invariant (§5.4):** Fox MUST NOT start with auth disabled on a public Droplet.

The first-boot script enforces this by:
1. Generating the password BEFORE starting the container.
2. Passing it via `--env-file` so `HERMES_WEBUI_PASSWORD` is set in the
   container's environment from the first process start.
3. `is_auth_enabled()` (`auth.py:353–355`) returns True because
   `is_password_auth_enabled()` returns True (env var is set).
4. `server.py:529–539` does NOT print the "no password" warning.

**Fail-closed:** If password generation fails (`openssl rand` returns empty),
the script exits 1 and the container never starts. The user SSHs in, sees the
MOTD explaining the failure, and can re-run or debug.

### 3.4 Attack surface of a public Droplet

| Surface | Exposure | Mitigation | Status |
|---------|----------|------------|--------|
| **Port 22 (SSH)** | Open (UFW allow) | DO SSH keys injected at Droplet creation. No root password in image. | Covered by img_check.sh |
| **Port 80 (HTTP)** | Open (UFW allow) | Caddy: redirects HTTP → HTTPS | To build |
| **Port 443 (HTTPS)** | Open (UFW allow) | Caddy: TLS termination → reverse proxy to 127.0.0.1:8787 | To build |
| **Port 8787 (Fox WebUI)** | CLOSED (UFW deny) | Not directly accessible. Caddy proxies to it via localhost. | To build |
| **Port 6333 (Qdrant)** | Container-internal only | Not host-mapped. Not in UFW. | Already covered |
| **Port 6334 (Qdrant gRPC)** | Container-internal only | Not host-mapped. Not in UFW. | Already covered |
| **Port 8643 (llama-server)** | Container-internal, localhost-only, autostart=false | Triple isolation: not host-mapped, binds 127.0.0.1, disabled by default. | Already covered |
| **Tailscale WireGuard** | Disabled by default | User opts in post-deploy. Not configured in Marketplace image. | Already covered |
| **`/data` volume** | Filesystem (Droplet disk) | Owned by foxinthebox user. `hermes.env` is chmod 600. | To build |
| **`/health` endpoint** | Unauthenticated (by design) | Returns `{"status":"ok"}` only. No secrets, no recon value. | Already covered |
| **`/readyz` endpoint** | Unauthenticated | Subsystem status. No secrets. | Already covered |
| **`/version`, `/capabilities`** | Behind `check_auth` in managed mode, open in standalone | Standalone (Marketplace) mode: open. Leaks version/overlay info. Acceptable — same as upstream Hermes. | Already covered |
| **Onboarding wizard (`/setup`)** | Behind `check_auth` (password required) | User must authenticate before configuring API keys. | Already covered |
| **CSRF bypass (non-browser callers)** | `_check_csrf` passes non-browser callers (`routes.py:1317–1324`) | With `HERMES_WEBUI_PASSWORD` set, `check_auth` requires a valid session cookie regardless of CSRF. Non-browser callers without a session are rejected at `auth.py:489–540` (PATH 4: 401/302). | Already covered |

**Ports open to the internet: 3** (22, 80, 443). Port 8787 is localhost-only
behind Caddy. All other services are container-internal.

---

## 4. Headless Config

### 4.1 Desktop assumptions replaced

| # | Desktop assumption | File | Headless replacement |
|---|-------------------|------|---------------------|
| 1 | User picks access mode via dialog | `docker-manager.js:370–394` | Hardcoded: `127.0.0.1:8787` (Caddy in front). No dialog. |
| 2 | Electron manages container lifecycle | `docker-manager.js`, `startup-orchestrator.js` | Systemd `foxinthebox.service` manages the container via `docker run`. |
| 3 | Health check polls from Electron | `health-check.js` | First-boot script polls `/health` before writing credentials. Caddy provides ongoing upstream health via reverse proxy. |
| 4 | `APP_ORIGIN = http://127.0.0.1:8787` | `app-urls.js` | Not used — this is an Electron-only file. |
| 5 | Docker Desktop install/start | `startup-orchestrator.js:steps 1–3` | Docker CE pre-installed in Packer image. |
| 6 | Tailscale auth via browser popup | `entrypoint.sh:252–278` | Disabled by default. User configures post-deploy if desired. |

**Container image: unchanged.** The same `ghcr.io/fox-in-the-box-ai/cloud:stable`
image runs on a Droplet as on a desktop. The Packer image wraps it with systemd,
Caddy, UFW, and the first-boot script. No Fox code changes.

### 4.2 Data persistence

- `/mnt/foxdata` on the Droplet maps to `/data` in the container.
- Survives container restart and image upgrade (`docker pull` + recreate).
- DO Block Storage can be attached for additional space (user's responsibility).
- `hermes.env`, `config.yaml`, `settings.json`, conversation history, mem0 data,
  Qdrant vectors all persist in `/mnt/foxdata`.

---

## 5. DO Submission Checklist

### 5.1 img_check.sh requirements (12 checks)

Source: https://github.com/digitalocean/marketplace-partners/blob/master/scripts/99-img-check.sh

| # | Requirement | Status | How |
|---|-------------|--------|-----|
| 1 | Supported OS | To build | Ubuntu 24.04 LTS |
| 2 | cloud-init installed | Done | Pre-installed in DO base image |
| 3 | Firewall active (UFW) | To build | `040-ufw.sh`: allow 22, 80, 443; deny all |
| 4 | Security updates applied | To build | `900-cleanup.sh`: `apt-get upgrade` |
| 5 | No root password | To build | `900-cleanup.sh`: `passwd -d root` |
| 6 | No root SSH authorized_keys | To build | `900-cleanup.sh`: `truncate -s 0 /root/.ssh/authorized_keys` |
| 7 | No root SSH private keys | To build | `900-cleanup.sh`: `rm -f /root/.ssh/id_*` |
| 8 | Root bash history cleared | To build | `900-cleanup.sh`: `truncate -s 0 /root/.bash_history` |
| 9 | Non-system users clean | To build | foxinthebox user: no password, no SSH keys, history cleared |
| 10 | Log files cleared | To build | `900-cleanup.sh`: `find /var/log -type f -exec truncate -s 0 {} \;` |
| 11 | DO agent removed | To build | `900-cleanup.sh`: `rm -rf /opt/digitalocean` |
| 12 | GPU support (optional) | N/A | Fox doesn't require GPU for cloud-provider mode |

**Status: 0 of 11 applicable checks done. All addressed by Packer scripts.**

### 5.2 Vendor Portal metadata

| Field | Value | Status |
|-------|-------|--------|
| App name | Fox in the Box | Ready |
| Version | 0.7.44 (or current at submission) | Ready |
| OS | Ubuntu 24.04 LTS | Ready |
| Software included | Docker CE, Caddy, Fox in the Box (list with versions) | To build |
| Short description | Private AI assistant with memory, local AI, and secure remote access | Ready |
| Getting-started doc | SSH → read MOTD → open URL → enter password → paste API key | To write |
| Logo | Fox logo (512x512 PNG) | Ready (exists in `packages/electron/assets/`) |
| Support URL | `https://github.com/fox-in-the-box-ai/fox-in-the-box/issues` | Ready |
| Documentation URL | `https://github.com/fox-in-the-box-ai/fox-in-the-box` | Ready |
| Min Droplet size | 2 GB RAM / 1 vCPU / 50 GB disk (TO RATIFY — needs benchmarking) | TO RATIFY |
| Category | AI Agents | Ready |

### 5.3 Listing assets

| Asset | Status |
|-------|--------|
| Logo (512x512 PNG) | Extract from `packages/electron/assets/icon.png` |
| Getting-started markdown | To write |
| Support/docs URLs | Ready |

---

## 6. Build Sequence (ordered)

**8 deliverables, ~5 days estimated.**

```
1. Packer template (do-marketplace.pkr.hcl)           → can build test images
2. 010-docker.sh (Docker CE install)                   → Docker on the Droplet
3. 020-fox.sh (pull :stable, systemd unit)             → Fox runs headless
4. 030-caddy.sh (install Caddy)                        → reverse proxy ready
5. 001-fox-firstboot (password + Caddy config + start) → secure first boot
6. 040-ufw.sh (firewall)                               → attack surface closed
7. 900-cleanup.sh (img_check compliance)               → image submittable
8. 99-fox MOTD + getting-started doc                   → user sees credentials
```

**Dependencies:** 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 (linear — each builds on prior).

**Smallest viable first deliverable:** Steps 1–7 produce a submittable image.
Step 8 (MOTD/docs) can be written in parallel.

---

## 7. Validation Plan

### 7.1 Hardening tests (pass/fail criteria)

| # | Test | Pass | Fail |
|---|------|------|------|
| 1 | **Password unguessable** | `wc -c /root/.fox-credentials` shows password >= 24 chars, no dictionary words. Run against image 10 times — all passwords unique. | Any duplicate, any password < 24 chars, any dictionary word |
| 2 | **Password generation failure = no start** | Set `openssl` to fail (e.g., `chmod 000 /usr/bin/openssl`), create Droplet. Fox container must NOT be running. | Container running without password |
| 3 | **TLS cert issued** | `curl -v https://<droplet-ip>` returns a valid cert (self-signed for IP, or Let's Encrypt for domain). No cleartext on port 80 (redirect to HTTPS). | Cleartext HTTP serves Fox content |
| 4 | **Port 8787 not reachable from internet** | `nmap -p 8787 <droplet-ip>` returns filtered/closed. | Port 8787 open |
| 5 | **Only ports 22, 80, 443 open** | `nmap -p- <droplet-ip>` returns exactly 3 open ports. | Any other port open |
| 6 | **Auth required on /setup** | `curl -s https://<droplet-ip>/setup` returns 302 → /login (not the setup page content). | Setup page accessible without auth |
| 7 | **Auth required on /api/models** | `curl -s https://<droplet-ip>/api/models` returns 401. | 200 with model data |
| 8 | **Auth NOT required on /health** | `curl -s https://<droplet-ip>/health` returns 200 `{"status":"ok"}`. | 401 or connection refused |
| 9 | **CSRF bypass closed** | `curl -X POST https://<droplet-ip>/api/chat -H "Content-Type: application/json" -d '{}'` returns 401 (no session). | 200 or any non-401 response |
| 10 | **img_check.sh passes** | Run `bash img_check.sh` on the snapshot. Exit code 0. | Exit code 2 (FAIL) |
| 11 | **Droplet survives reboot** | `reboot`, wait 2 min, Fox accessible at HTTPS with same password. | Fox not running after reboot |
| 12 | **Data persists across container recreate** | Chat, send message, `docker stop fox-in-the-box && docker rm fox-in-the-box`, re-run container with same `/mnt/foxdata` volume. Previous conversation visible. | Data lost |

### 7.2 Functional tests

| # | Test | Pass |
|---|------|------|
| 13 | Onboarding wizard completes | Paste OpenRouter API key → chat works |
| 14 | Memory persists | Ask "remember my name is Alice", new session, ask "what's my name" → "Alice" |
| 15 | Local fallback toggle | Enable local fallback in Settings → llama-server starts (check supervisorctl) |

---

## 8. Open Questions / Residual Blockers

| # | Question | Severity | Notes |
|---|----------|----------|-------|
| 1 | **IP-based TLS** — Let's Encrypt doesn't issue certs for bare IPs. Self-signed cert (browser warning) or require domain setup? ZeroSSL supports IP certs but adds a dependency. | TO RATIFY | Recommend: ship with Caddy's auto self-signed for IPs; document domain setup for proper TLS |
| 2 | **Droplet size** — 2 GB RAM / 1 vCPU is the minimum for cloud-provider mode. Local models (llama-server) need 8 GB+. Which size do we list as minimum? | TO RATIFY | Recommend: list 2 GB as minimum, note 8 GB for local models in getting-started doc |
| 3 | **Image update automation** — DO Vendor API supports programmatic snapshot updates. Should `build-container.yml` trigger a Packer rebuild + API push on `:stable` bump? | Phase 2 | Not needed for initial listing |
| 4 | **Vendor Portal access** — need to apply at `marketplace.digitalocean.com/vendors`. Lead time unknown. Start now, build in parallel. | Process | Founder action |
| 5 | **Onboarding wizard on HTTPS** — the wizard at `/setup` works but was designed for `http://localhost:8787`. Verify it renders correctly when accessed via `https://<ip>`. | Verify | Likely works — it's standard HTML/JS, no localhost assumptions in the UI |
