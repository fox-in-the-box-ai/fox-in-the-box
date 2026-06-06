# Security Policy

## Supported versions

Only the latest release receives security fixes.

| Version | Supported |
|---------|-----------|
| Latest  | Yes       |
| Older   | No        |

## Reporting a vulnerability

**Preferred:** Use [GitHub's private vulnerability reporting](https://github.com/fox-in-the-box-ai/fox-in-the-box/security/advisories/new) to create a private security advisory. This keeps the report, discussion, and fix private until disclosure.

**Alternative:** Send a description to **security@foxinthebox.io**.

Include:

- A description of the vulnerability and its potential impact
- Steps to reproduce or proof-of-concept if available
- Any relevant environment details (OS, version, configuration)

**What to expect:**

- Acknowledgement within 48 hours
- A status update within 7 days
- A patch or mitigation within 14 days for confirmed issues
- Credit in the release notes if you wish (opt-in)
- A CVE identifier for confirmed vulnerabilities (via GitHub Security Advisory)

We ask that you do not publicly disclose the vulnerability until a fix has been released. We will coordinate the disclosure timeline with you.

## Threat model

Fox in the Box is a self-hosted AI assistant. The primary deployment modes and their trust boundaries:

### Standalone (desktop / single user)

The instance runs on `127.0.0.1:8787`. The trust boundary is the local machine. The LAN is treated as trusted (inherited from upstream Hermes). Network-adjacent attackers on the same LAN can reach the port if the user selects access mode 1 or 3 (`0.0.0.0`).

**Assumed trusted:** The local user, processes on the same machine.
**Not trusted:** Remote network callers (mitigated by binding to localhost in access mode 2).

### Managed (control plane)

The instance is provisioned by a control plane with authentication enforced via `check_auth` substitution (`FOX_PLANE_AUTH_SECRET`). Upstream session auth is required (managed-mode invariant). The trust boundary shifts to the control plane's auth layer.

**Assumed trusted:** Authenticated control-plane callers (`X-Fox-Auth`), session-bearing browser users.
**Not trusted:** Unauthenticated callers (rejected by `check_auth` PATH 4).

### Key security properties

| Property | Mechanism |
|----------|-----------|
| No credential storage in agent context | API keys in `hermes.env`, sourced by `entrypoint.sh`, never in chat history |
| Session auth | Upstream Hermes `check_auth` with HMAC-signed session cookies |
| Control-plane auth | `X-Fox-Auth` shared secret via `hmac.compare_digest` (constant-time) |
| CSRF protection | Upstream `_check_csrf` for browser callers; managed mode closes the non-browser bypass via the auth invariant |
| Container isolation | All services run inside a single container; host access only via bind-mounted `/data` volume |
| Overlay integrity | `validate-overlay.yml` CI gate verifies patch anchors; `check-overlay-basis.sh` detects upstream drift |
| Image provenance | Digest-pinned images via `versions.toml`; container builds gated by CI |

### Known limitations

- Standalone mode trusts the LAN (upstream Hermes design choice). See `ENTERPRISE_ARCHITECTURE.md` section 0.5 for the ratification question.
- The shared secret (`FOX_PLANE_AUTH_SECRET`) is symmetric. All components that know it are equally trusted. mTLS upgrade path is documented but not yet implemented.
- LLM provider API keys are stored as plaintext environment variables in `hermes.env` on the `/data` volume. Access to the volume means access to the keys.

## Scope

**In scope:**
- The Docker container and its bundled components (Hermes Agent, Hermes WebUI, Fox overlay, Qdrant, Tailscale)
- The Electron desktop apps (Windows, macOS)
- The `.deb` bare-metal installer
- The web-based onboarding wizard and setup flow
- The fox-overlay Python package (patches, dispatcher, substitutions)
- CI/CD pipeline security (workflow permissions, signing, artifact integrity)

**Out of scope:**
- Vulnerabilities in upstream dependencies (Hermes Agent, Hermes WebUI, Qdrant, Tailscale) — please report those to their respective maintainers
- Issues requiring physical access to the host machine
- Social engineering attacks
- Denial-of-service against the LLM provider (rate limiting is the provider's responsibility)

## Security CI

| Check | Workflow | Frequency |
|-------|----------|-----------|
| CodeQL static analysis | `codeql.yml` | Every PR + weekly |
| Overlay anchor integrity | `validate-overlay.yml` | Every PR |
| Upstream drift detection | `upstream-watch.yml` + `upstream-tripwires.yml` | Nightly |
| Dependency updates | Dependabot | Weekly |
