# Security Policy

## Supported versions

Only the latest release receives security fixes.

| Version | Supported |
|---------|-----------|
| Latest  | Yes       |
| Older   | No        |

## Reporting a vulnerability

Please do not report security vulnerabilities through public GitHub issues.

Send a description of the issue to **security@foxinthebox.io**. Include:

- a description of the vulnerability and its potential impact
- steps to reproduce or proof-of-concept if available
- any relevant environment details (OS, version, configuration)

**What to expect:**

- Acknowledgement within 48 hours
- A status update within 7 days
- A patch or mitigation within 14 days for confirmed issues
- Credit in the release notes if you wish (opt-in)

We ask that you do not publicly disclose the vulnerability until a fix has been released. We will coordinate the disclosure timeline with you.

## Scope

In scope:
- The Docker container and its bundled components
- The Electron desktop apps
- The web-based onboarding wizard and setup flow

Out of scope:
- Vulnerabilities in upstream dependencies (Hermes Agent, Hermes WebUI, Qdrant, Tailscale) — please report those to their respective maintainers
- Issues requiring physical access to the host machine
- Social engineering attacks
