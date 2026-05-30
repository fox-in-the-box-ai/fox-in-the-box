# Task: Bare-Metal .deb Package + Apt Repository (Phases 2–4)

## Context

Fox in the Box is a self-hosted AI assistant (Electron desktop app + Docker container). 
Phase 1 is already done: `packages/install-core/install-core.sh` now contains all shared 
install logic. The Dockerfile calls it. Your job is Phases 2–4: wrap that into a `.deb`, 
host it on an apt repo, wire up CI.

Read these docs before writing any code:
- `docs/plans/bare-metal-deb/README.md` — overview and decisions
- `docs/plans/bare-metal-deb/04-deb-package.md` — exact .deb structure and file contents
- `docs/plans/bare-metal-deb/05-apt-repo.md` — apt repo design
- `docs/plans/bare-metal-deb/06-ci.md` — CI changes

Also skim:
- `packages/install-core/install-core.sh` — what postinst will call
- `packages/install-core/preflight.sh` — what the systemd unit will call
- `packages/scripts/foxinthebox.service` — existing Docker-based unit to understand shape

---

## Phase 2 — .deb package

Create `packages/deb/` with the following structure:

```
packages/deb/
├── build.sh
├── control/
│   ├── control
│   ├── postinst
│   ├── prerm
│   └── postrm
└── templates/
    ├── foxinthebox.service.tmpl
    ├── foxinthebox-updater.service.tmpl
    └── foxinthebox-updater.path.tmpl
```

**Exact content specs are in `docs/plans/bare-metal-deb/04-deb-package.md`.** Implement them 
as written — do not invent alternatives.

Key points:
- `postinst` calls `FITB_APP_DIR=/opt/foxinthebox FITB_CONTEXT=bare-metal bash /opt/foxinthebox/install-core.sh`
- `build.sh` does NOT bundle hermes-agent or hermes-webui in the .deb (install-core.sh clones them at install time)
- `build.sh` DOES bundle: `install-core.sh`, `preflight.sh`, `default-configs/`, `scripts/`, `fox-overlay/`, `version.txt`
- The supervisord unit templates use `__APP_DIR__` token substituted to `/opt/foxinthebox` by build.sh
- `/opt/foxinthebox` must be owned by `foxinthebox` system user (created in postinst)

**Smoke test** — add `tests/container/test_deb_install.sh`:
```bash
#!/usr/bin/env bash
# Build the .deb, install in a clean ubuntu:22.04 container, assert /health responds
set -euo pipefail
bash packages/deb/build.sh amd64
docker run --rm \
  -v "$(pwd)/dist:/debs" \
  ubuntu:22.04 bash -c "
    apt-get update -q &&
    apt-get install -y -q /debs/foxinthebox_*.deb &&
    sleep 15 &&
    curl -sf http://localhost:8787/health &&
    echo PASS
  "
```

---

## Phase 3 — Apt repo infrastructure

Create `packages/deb/publish-apt.sh` — exact content in `docs/plans/bare-metal-deb/05-apt-repo.md`.

Also create `packages/deb/README.md` documenting:
1. How to generate the GPG signing key pair (one-time, manual)
2. How to bootstrap the R2 bucket (one-time, manual — just document the steps, don't automate)
3. The user install one-liner
4. Required GitHub secrets: `APT_GPG_PRIVATE_KEY`, `APT_GPG_KEY_ID`, `R2_ACCOUNT_ID`, `R2_ACCESS_KEY`, `R2_SECRET_KEY`

---

## Phase 4 — CI

Add two new jobs to `.github/workflows/release.yml`:
- `build-deb` — matrix over `[amd64, arm64]`, calls `build.sh`, uploads artifacts
- `publish-apt` — depends on `build-deb`, calls `publish-apt.sh`

Exact YAML in `docs/plans/bare-metal-deb/06-ci.md`.

Also update `.github/workflows/release.yml` to add a `deb-smoke-test` job between `build-deb` 
and `publish-apt` that runs `tests/container/test_deb_install.sh`.

---

## Acceptance criteria

- [ ] `bash packages/deb/build.sh amd64` produces `dist/foxinthebox_<version>_amd64.deb`
- [ ] `dpkg-deb --info dist/foxinthebox_*.deb` shows correct metadata
- [ ] `bash tests/container/test_deb_install.sh` passes (health check ok)
- [ ] `bash packages/deb/publish-apt.sh` exits 0 when R2 creds are set (can test with dry-run flag)
- [ ] `.github/workflows/release.yml` has `build-deb` and `publish-apt` jobs
- [ ] No hardcoded paths other than `/opt/foxinthebox` and `/etc/foxinthebox`
- [ ] `packages/deb/README.md` covers the 4 documented items

## What NOT to do

- Do not modify `packages/install-core/install-core.sh` or `preflight.sh` — they are done
- Do not modify the Dockerfile
- Do not bundle hermes-agent or hermes-webui source in the .deb
- Do not add a GUI installer
- Do not create a Snap or AppImage
