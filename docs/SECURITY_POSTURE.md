# Fox in the Box — Security Posture

Last updated: v0.7.60 + post-release pins (2026-08-18)

## Threat model

Fox in the Box is a **single-tenant, self-hosted** AI assistant. The user IS the operator. There is no multi-tenant isolation boundary, no untrusted input processing from external users, and no data leaving the user's machine unless they explicitly configure a remote model provider.

The container runs on the user's infrastructure (local Docker, cloud VM, or fleet-managed host). The network attack surface is the HTTP port (8787) which should be behind TLS termination (Caddy, nginx, or fleet proxy) in any non-local deployment.

### Long-term memory subsystem (default-on since v0.7.60)

Conversation-derived facts are stored **locally** under the instance data volume: self-hosted mem0 (mem0ai 2.0.10) with an embedded Qdrant store. Embeddings are computed **on-device** by a llama.cpp embed-server (nomic-embed-text-v1.5 GGUF) bound to `127.0.0.1:8644` — never exposed outside the container. The only egress the feature adds is fact-extraction calls to the chat provider the user already configured. mem0's PostHog telemetry is force-disabled (`MEM0_TELEMETRY=False` at every process boundary — the posthog package is present but inert; verified zero egress in the v0.7.60 release smoke). Memory state is fail-loud (`READY`/`OFF`/`ERROR` in Settings and `/readyz`) — no silent degradation. The image also bakes `openssh-client` and `rsync` (v0.7.60) for agent remote-host workflows; both are standard Debian packages covered by Trivy scanning.

### Cloud provider credentials

On AWS VMs, the instance metadata service (IMDS) makes the machine's default instance role reachable by any local process. Fox does **not** treat an IMDS-derived instance role as valid Bedrock authentication: the provider card will not show as authenticated, and Bedrock calls are rejected until explicit credentials are configured (bearer token or IAM key pair in Settings → Providers, `AWS_PROFILE`, a shared credentials file, an ECS task role, or IRSA). Operators who deliberately want instance-role auth can opt in with `HERMES_BEDROCK_ALLOW_INSTANCE_ROLE=1`.

## Supply-chain monitoring

### Automated scanning

- **Dependabot** — monitors npm (Electron workspace), pip (fox-overlay), and GitHub Actions for vulnerable dependencies. Weekly schedule, grouped PRs.
- **Trivy** — scans the container image on every PR and release via GitHub code scanning (SARIF upload). Covers OS packages, language packages, and binary dependencies.
- **CodeQL** — static analysis for JavaScript/TypeScript and Python on every PR.

### Current state

**Open Dependabot alerts: 0** (as of 2026-08-18 — js-yaml 4.3.1 and protobufjs 7.6.5 cleared the last npm alerts). The long-tracked **GHSA-537c-gmf6-5ccf accepted risk is CLOSED**: upstream hermes-agent previously hard-pinned `cryptography` below the 48.0.1 fix; since the v0.52.113 / v2026.8.16.2 pin bump, `requirements.lock` carries `cryptography==50.0.0`.

`packages/integration/requirements.lock` is itself a supply-chain control: 94 exact pins for every Python package in the container, consumed as a pip **constraints** file (`-c`) at build time so transitive resolution cannot drift silently between builds; CI fails on freeze drift.

### Triage policy for container-scan (Trivy) alert categories

The following categories recur in container scans and are triaged against Fox's threat model; the reasoning applies to future alerts of the same class, not to a fixed count of open ones.

**Ancient/disputed CVEs in system libraries (CVEs from 2005–2019):**
These are long-standing CVEs in Debian system packages (glibc, tar, perl, iptables, coreutils, ldap, kerberos, systemd, git, libgcrypt) that have been open across the entire Debian ecosystem for years. None have practical exploit paths in Fox's single-tenant threat model:

- Fox doesn't use LDAP, Kerberos, or Perl
- Fox doesn't process untrusted tar archives or user-supplied regex patterns
- Container isolation + TLS termination mitigate the remaining vectors

**Debian system packages with no fix available:**
The container base image (`python:3.11-slim`, Debian trixie) includes system packages at their latest Debian patch level. When CVEs are reported against these packages before Debian releases a fix, the alerts appear and remain open until Debian ships the patch. These auto-close on the next container rebuild after the Debian fix lands.

**System npm bundled dependencies:**
Node.js LTS bundles npm, which bundles its own transitive dependencies (undici, tar, etc.). These can't be independently overridden — they close when the next Node.js LTS release includes a newer npm.

**Tailscale binary Go stdlib:**
Tailscale is installed from the official Debian stable repository. Go stdlib CVEs in the compiled binary close when Tailscale releases a version compiled with a patched Go runtime.

## Dependency override policy

When Dependabot identifies vulnerable transitive npm dependencies that can't be resolved by bumping direct dependencies, the project uses **pnpm overrides** in the root `package.json` to force resolution to patched versions. Overrides use caret ranges (`^X.Y.Z`) to allow patch updates within the same major version while preventing unexpected major-version jumps.

## Reporting

To report a security issue, email roadhero@gmail.com. For non-sensitive issues, use the GitHub issue tracker.
