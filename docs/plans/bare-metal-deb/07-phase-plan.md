# 07 — Phased Implementation Plan

## Phase 1 — install-core.sh (~3h agent)

**Goal:** Single script encapsulating all install logic. Dockerfile is refactored to call it. No behavior change for Docker users.

**Exit criteria:**
- `docker build` still succeeds and produces a working container (smoke test passes)
- `bash packages/install-core/install-core.sh` runs to completion in a clean Ubuntu 22.04 environment with `FITB_APP_DIR=/tmp/test-fitb`
- All logic from the Dockerfile's patch/pip/soul RUN steps removed from Dockerfile and present in install-core.sh
- Bats tests for install-core.sh pass with mock git/pip/curl

**Tasks:**

### Task 1.1: Create packages/install-core/ and scaffold install-core.sh
- Files: `packages/install-core/install-core.sh`
- Content: skeleton with all functions stubbed, env var defaults at top
- Test: shellcheck passes, script exits 0 with all stubs

### Task 1.2: Migrate binary download logic (qdrant + llama-server)
- Move from Dockerfile RUN blocks to `_install_qdrant` and `_install_llama_server`
- Use `uname -m` for arch detection (not TARGETARCH)
- Add sha256 check + skip-if-exists logic
- Test: mock curl, assert files created at expected paths

### Task 1.3: Migrate versions.toml parsing + repo sync
- Parse `AGENT_TAG` and `WEBUI_TAG` from `packages/fox-overlay/versions.toml`
- `_sync_hermes_repos`: git clone --depth=1 on fresh install, git fetch + checkout on upgrade
- Test: mock git, assert clone/fetch called with correct args

### Task 1.4: Migrate patch series application
- Extract logic from Dockerfile webui+agent RUN blocks verbatim
- Parameterize `/app/hermes-webui` → `$FITB_APP_DIR/hermes-webui`
- Test: mock git apply, assert series applied in order, assert --check run first

### Task 1.5: Migrate memory plugins, removals, SOUL.md
- Direct port from Dockerfile (path substitution only)
- Test: assert files copied to correct locations

### Task 1.6: Migrate pip install
- Create venv at `$FITB_APP_DIR/venv/` (bare-metal) or use system pip (Docker)
- Distinguish via `FITB_CONTEXT=docker|bare-metal`
- Test: mock pip, assert install called with correct extras

### Task 1.7: Write supervisord.conf generator
- Heredoc template embedded in script with `$FITB_APP_DIR` substitution
- Output to `/etc/foxinthebox/supervisord.conf` (bare-metal) or `/etc/supervisor/supervisord.conf` (Docker)
- Test: assert output file has no `/app/` references when FITB_APP_DIR=/opt/foxinthebox

### Task 1.8: Refactor Dockerfile to call install-core.sh
- Replace the 5 RUN blocks (webui patches, agent patches, mem plugins, removals, soul) with a single COPY + RUN
- Keep binary download layers separate (for Docker layer cache)
- Verify: `docker build` succeeds, smoke test passes

### Task 1.9: Bats test suite for install-core.sh
- File: `tests/container/test_install_core.bats`
- Test helpers: stubs for git, pip, curl in `tests/container/test_helpers/`
- Run: `bats tests/container/test_install_core.bats`

---

## Phase 2 — .deb package (~2h agent)

**Goal:** `dpkg -i foxinthebox_<version>_amd64.deb` installs Fox on Ubuntu 22.04 and starts the service.

**Exit criteria:**
- `.deb` builds without errors via `build.sh`
- Install in clean Ubuntu 22.04 Docker container → health check passes at `http://localhost:8787`
- `apt remove foxinthebox` cleanly stops service and removes `/opt/foxinthebox`
- `apt remove --purge foxinthebox` additionally removes system user
- Upgrade from v-1 to v: service restarts cleanly

**Tasks:**

### Task 2.1: Create packages/deb/ scaffold
- Files: `packages/deb/control/control`, `postinst`, `prerm`, `postrm`
- Content: as specified in 04-deb-package.md
- Test: `dpkg-deb --info` on resulting .deb validates control fields

### Task 2.2: Write build.sh
- As specified in 04-deb-package.md
- Test: runs to completion, produces `dist/foxinthebox_<version>_amd64.deb`

### Task 2.3: Write systemd unit templates
- `packages/deb/templates/foxinthebox.service.tmpl` (bare-metal variant)
- `packages/deb/templates/foxinthebox-updater.service.tmpl`
- `packages/deb/templates/foxinthebox-updater.path.tmpl`
- Identical to existing `packages/scripts/` units but with `__APP_DIR__` tokens

### Task 2.4: Write preflight.sh
- File: `packages/install-core/preflight.sh` (copied to `$APP_DIR/scripts/` by build.sh)
- Content: as specified in 03-install-core.md
- Test: runs idempotently in $TMPDIR

### Task 2.5: Smoke test in Docker
- `tests/container/test_deb_install.sh`
- Builds .deb, runs in `ubuntu:22.04` container, asserts health check
- Add to Makefile: `make test-deb`

---

## Phase 3 — Apt repo on R2 (~2h agent)

**Goal:** `apt install foxinthebox` works from `apt.foxinthebox.ai`.

**Exit criteria:**
- R2 bucket created, custom domain configured
- GPG key pair generated (private in GitHub secrets, public at `apt.foxinthebox.ai/gpg.asc`)
- `publish-apt.sh` runs locally and produces a valid apt repo structure
- Adding the source + `apt install` works on a clean Ubuntu 22.04 machine

**Tasks:**

### Task 3.1: Set up R2 bucket and custom domain
- Manual: create bucket `foxinthebox-apt` in Cloudflare R2
- Manual: add CNAME `apt.foxinthebox.ai`
- Document in `packages/deb/README.md`

### Task 3.2: Generate GPG signing key
- `gpg --batch --full-gen-key` with a non-expiring subkey
- Export and store per 05-apt-repo.md
- Upload `gpg.asc` to R2 bucket root

### Task 3.3: Write publish-apt.sh
- File: `packages/deb/publish-apt.sh`
- Content: as specified in 06-ci.md
- Test: dry-run with `--dry-run` rclone flag

### Task 3.4: Bootstrap the apt repo
- Run `publish-apt.sh` once manually with v0.1.0 `.deb`
- Verify: `apt-get update` from a test machine picks up the repo

---

## Phase 4 — CI integration (~1h agent)

**Goal:** Every GitHub Release automatically builds + publishes `.deb` for amd64 and arm64.

**Exit criteria:**
- Tag `v0.9.0` → CI builds two `.deb` files → published to apt repo → `apt upgrade` picks up v0.9.0

**Tasks:**

### Task 4.1: Add build-deb job to release.yml
- As specified in 06-ci.md
- Uses matrix strategy for amd64/arm64

### Task 4.2: Add publish-apt job (depends on build-deb)
- Calls `publish-apt.sh`
- Requires R2 + GPG secrets in repo settings

### Task 4.3: Add deb smoke test job
- Runs between build-deb and publish-apt
- Gates publish on passing health check

### Task 4.4: Update README with apt install instructions
- Add "Install on Ubuntu / Zorin OS" section
- One-liner: curl the install-deb.sh script (wraps the 3 apt setup steps)

---

## Total effort summary

| Phase | Agent hours | Complexity |
|-------|-------------|------------|
| 1: install-core.sh | ~3h | Medium-High (patch series, venv, Dockerfile refactor) |
| 2: .deb package | ~2h | Medium (dpkg mechanics, systemd, smoke test) |
| 3: apt repo | ~2h | Low-Medium (mostly infra + manual steps) |
| 4: CI | ~1h | Low (YAML, no new logic) |
| **Total** | **~8h** | |

## Linear issue to create

**Title:** feat: bare-metal install via .deb + apt.foxinthebox.ai (Ubuntu/Zorin)
**Labels:** enhancement, p1, feature, installer
**Links to:** closes #451
**Milestone:** v0.9.0 (suggested)
