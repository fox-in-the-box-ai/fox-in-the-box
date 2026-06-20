# Fox in the Box — Security Posture

Last updated: v0.7.57 (2026-06-20)

## Threat model

Fox in the Box is a **single-tenant, self-hosted** AI assistant. The user IS the operator. There is no multi-tenant isolation boundary, no untrusted input processing from external users, and no data leaving the user's machine unless they explicitly configure a remote model provider.

The container runs on the user's infrastructure (local Docker, cloud VM, or fleet-managed host). The network attack surface is the HTTP port (8787) which should be behind TLS termination (Caddy, nginx, or fleet proxy) in any non-local deployment.

## Supply-chain monitoring

### Automated scanning

- **Dependabot** — monitors npm (Electron workspace), pip (fox-overlay), and GitHub Actions for vulnerable dependencies. Weekly schedule, grouped PRs.
- **Trivy** — scans the container image on every PR and release via GitHub code scanning (SARIF upload). Covers OS packages, language packages, and binary dependencies.
- **CodeQL** — static analysis for JavaScript/TypeScript and Python on every PR.

### Accepted risks

The following alert categories have been triaged and accepted based on Fox's threat model. Each is documented with reasoning in the internal triage record.

**Ancient/disputed CVEs in system libraries (21 alerts, CVEs from 2005–2019):**
These are long-standing CVEs in Debian system packages (glibc, tar, perl, iptables, coreutils, ldap, kerberos, systemd, git, libgcrypt) that have been open across the entire Debian ecosystem for years. None have practical exploit paths in Fox's single-tenant threat model:
- Fox doesn't use LDAP, Kerberos, or Perl
- Fox doesn't process untrusted tar archives or user-supplied regex patterns
- Container isolation + TLS termination mitigate the remaining vectors

**Debian system packages with no fix available (~336 alerts):**
The container base image (`python:3.11-slim`, Debian trixie) includes system packages at their latest Debian patch level. When CVEs are reported against these packages before Debian releases a fix, the alerts appear and remain open until Debian ships the patch. These auto-close on the next container rebuild after the Debian fix lands.

**System npm bundled dependencies (~7 alerts):**
Node.js LTS bundles npm, which bundles its own transitive dependencies (undici, tar, etc.). These can't be independently overridden — they close when the next Node.js LTS release includes a newer npm.

**Tailscale binary Go stdlib (~7 alerts):**
Tailscale is installed from the official Debian stable repository. Go stdlib CVEs in the compiled binary close when Tailscale releases a version compiled with a patched Go runtime.

## Dependency override policy

When Dependabot identifies vulnerable transitive npm dependencies that can't be resolved by bumping direct dependencies, the project uses **pnpm overrides** in the root `package.json` to force resolution to patched versions. Overrides use caret ranges (`^X.Y.Z`) to allow patch updates within the same major version while preventing unexpected major-version jumps.

## Reporting

To report a security issue, email roadhero@gmail.com. For non-sensitive issues, use the GitHub issue tracker.
