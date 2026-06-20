# Contributing to Fox in the Box

Thank you for your interest in contributing. This document explains how to get involved.

---

## How to contribute

### Reporting bugs

Search [existing issues](https://github.com/fox-in-the-box-ai/fox-in-the-box/issues) before opening a new one. If you find a match, add any additional information as a comment rather than opening a duplicate.

Use the **Bug report** template and include:
- steps to reproduce the problem
- your OS, installation method, and Fox in the Box version
- relevant log output (`docker logs fox-in-the-box`)

### Requesting features

Use the **Feature request** template. Describe the problem you are trying to solve, not just the solution. This helps us evaluate whether the feature fits the project's direction.

### Questions and ideas

For questions, troubleshooting, or early-stage ideas, start a [Discussion](https://github.com/fox-in-the-box-ai/fox-in-the-box/discussions) instead of an issue. Issues are for defined, actionable work.

### Submitting pull requests

Pull requests are welcome. Please open an issue first to discuss the change before investing time in an implementation — this avoids wasted effort if the direction does not align.

When your PR is ready:
- reference the related issue (`Closes #NNN`)
- keep the scope focused; one fix or feature per PR
- make sure existing tests still pass
- add tests for new behavior where applicable

---

## Development setup

### Prerequisites

- Docker 20.10 or later
- Node.js 22.12.0 or later and pnpm
- Git

### Clone and build

```bash
git clone --recurse-submodules https://github.com/fox-in-the-box-ai/fox-in-the-box.git
cd fox-in-the-box

# Build the Docker image
docker build -f packages/integration/Dockerfile -t fitb:local .

# Run locally
docker run -d \
  --name fox-in-the-box \
  --cap-add=NET_ADMIN \
  --device /dev/net/tun \
  -p 8787:8787 \
  -v ~/.foxinthebox:/data \
  fitb:local
```

Open [http://localhost:8787](http://localhost:8787) and complete the setup wizard.

### Running tests

```bash
# Fox overlay tests (with coverage — CI enforces 45% minimum)
cd packages/fox-overlay && pytest tests/ -v --cov=. --cov-report=term-missing

# Electron unit tests
cd packages/electron && pnpm test

# Container smoke test
cd tests/container && bats test_install.bats
```

### Quality gates

CI enforces these automatically on every PR:

- **Test coverage**: fox-overlay tests must maintain at least 45% line coverage (pytest-cov)
- **Startup time**: container must start and pass health check within 45s (warning) / 90s (hard fail)
- **Static analysis**: CodeQL and Trivy scans must pass
- **Container build**: multi-arch (amd64 + arm64) build and smoke test must succeed

---

## Developer Certificate of Origin (DCO)

All contributions must be signed off to certify you have the right to submit
them under the project's open-source license. Add a `Signed-off-by` line to
every commit:

```bash
git commit -s -m "feat: add widget support"
```

This adds a trailer like:

```
Signed-off-by: Jane Doe <jane@example.com>
```

By signing off, you agree to the [DCO](https://developercertificate.org/).
CI checks for this trailer on every PR. If you forget, amend and force-push:

```bash
git commit --amend -s
git push --force-with-lease
```

---

## Coding standards

- Python: match the style of the existing codebase in `forks/hermes-webui/`
- JavaScript: plain ES2020 modules, no TypeScript, no bundler
- Shell scripts: `set -euo pipefail` at the top of every script
- Commit messages: use [Conventional Commits](https://www.conventionalcommits.org/) format (`feat:`, `fix:`, `docs:`, `chore:`, etc.)
- Do not leave debug logging (`console.log`, `print`) in committed code
- Do not hardcode paths — use environment variables or the `/data` mount point

