# Task 08: GitHub Actions CI/CD

| Field          | Value                                                                             |
|----------------|-----------------------------------------------------------------------------------|
| **Status**     | Ready                                                                             |
| **Executor**   | AI agent                                                                          |
| **Depends on** | Task 03 (Dockerfile exists at `packages/integration/Dockerfile`), Task 06 (Electron app in `packages/electron/`) |
| **Parallel**   | Can be started alongside Tasks 04–07 — workflow YAML can be committed before container or Electron builds pass |
| **Blocks**     | Nothing (this is the final delivery pipeline)                                     |
| **Path**       | `.github/workflows/`                                                              |

---

## Summary

Create three GitHub Actions workflow files under `.github/workflows/` that form the complete CI/CD pipeline for Fox in the Box:

| Workflow | File | Trigger |
|---|---|---|
| Build & push Docker container to GHCR | `build-container.yml` | Push to `main`, PRs targeting `main` |
| Build Electron installers (Windows + macOS) | `build-electron.yml` | Push to `main` only |
| Tag release — re-tag image, create GitHub Release | `release.yml` | Tag push matching `v*` |

> **Early commit OK.** These workflow files can be committed to the repository immediately. They will fail until Tasks 03 and 06 are complete, but committing early is encouraged so CI structure is visible in PRs.

---

## Prerequisites

1. **Task 03 complete** — `packages/integration/Dockerfile` exists and `docker build` succeeds.
2. **Task 06 complete** — `packages/electron/` exists with `pnpm build` producing a `dist/` directory containing `.exe` (Windows) and `.zip` (macOS) artifacts.
3. `GITHUB_TOKEN` is automatically provided by GitHub Actions — no manual secret setup is required for v0.1.
4. GHCR (GitHub Container Registry) is enabled for the `fox-in-the-box-ai` org (it is on by default for all GitHub orgs).

---

## Implementation

### Step 1 — Ensure `.github/workflows/` directory exists

```bash
mkdir -p .github/workflows
```

---

### Step 2 — Create `.github/workflows/build-container.yml`

This workflow:
- Runs on every push to `main` and every PR targeting `main`.
- Builds the Docker image from `packages/integration/Dockerfile`.
- Tags `:latest` on pushes to `main`, `:dev` on pull request builds.
- Pushes to `ghcr.io/fox-in-the-box-ai/cloud`.
- Runs a container smoke test to verify the image is functional.

```yaml
# .github/workflows/build-container.yml
name: Build Container

on:
  push:
    branches:
      - main
  pull_request:
    branches:
      - main

jobs:
  build-and-push:
    name: Build & Push Docker Image
    runs-on: ubuntu-latest

    permissions:
      contents: read
      packages: write   # required to push to GHCR

    steps:
      - name: Checkout (with submodules)
        uses: actions/checkout@v4
        with:
          submodules: recursive

      - name: Log in to GHCR
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Determine image tag
        id: meta
        run: |
          if [[ "${{ github.event_name }}" == "pull_request" ]]; then
            echo "tag=dev" >> "$GITHUB_OUTPUT"
          else
            echo "tag=latest" >> "$GITHUB_OUTPUT"
          fi

      - name: Build Docker image
        run: |
          docker build \
            --platform linux/amd64 \
            -t ghcr.io/fox-in-the-box-ai/cloud:${{ steps.meta.outputs.tag }} \
            -f packages/integration/Dockerfile \
            .

      - name: Push Docker image to GHCR
        run: |
          docker push ghcr.io/fox-in-the-box-ai/cloud:${{ steps.meta.outputs.tag }}

      - name: Smoke test — start container
        run: |
          docker run -d \
            --name test-fox \
            --cap-add=NET_ADMIN \
            -p 127.0.0.1:8787:8787 \
            ghcr.io/fox-in-the-box-ai/cloud:${{ steps.meta.outputs.tag }}

      - name: Smoke test — wait for container to be healthy
        # Poll instead of blind sleep: first boot clones git repos + pip install,
        # which takes 30–90 seconds on a cold CI runner. sleep 10 is not enough.
        # Retry for up to 3 minutes (36 × 5s). Fail fast if container exits.
        run: |
          for i in $(seq 1 36); do
            if curl -sf http://localhost:8787/health -o /dev/null 2>/dev/null; then
              echo "✅ /health returned HTTP 200 (attempt $i)"
              exit 0
            fi
            # Abort early if the container died
            if ! docker inspect test-fox --format '{{.State.Running}}' | grep -q true; then
              echo "❌ Container exited unexpectedly"
              exit 1
            fi
            echo "  Waiting... ($i/36)"
            sleep 5
          done
          echo "❌ Container did not become healthy within 3 minutes"
          exit 1

      - name: Smoke test — print container logs (for debugging)
        if: always()
        run: docker logs test-fox

      - name: Smoke test — stop container
        if: always()
        run: docker stop test-fox || true
```

---

### Step 3 — Create `.github/workflows/build-electron.yml`

This workflow:
- Runs **only on pushes to `main`** (not on PRs — Electron builds are slow and expensive).
- Uses a matrix to build on both `windows-latest` and `macos-latest` in parallel.
- Installs Node 20 + pnpm 9, runs `pnpm build` inside `packages/electron/`.
- Uploads `dist/` as a named artifact per platform.
- On tagged releases (`v*`), also uploads the artifacts to the GitHub Release.

```yaml
# .github/workflows/build-electron.yml
name: Build Electron

on:
  push:
    branches:
      - main
    tags:
      - "v*"

jobs:
  build:
    name: Build Electron — ${{ matrix.os }}
    runs-on: ${{ matrix.os }}

    strategy:
      fail-fast: false
      matrix:
        include:
          - os: windows-latest
            artifact-name: fox-windows
            artifact-path: packages/electron/dist/*.exe
          - os: macos-latest
            artifact-name: fox-macos
            artifact-path: packages/electron/dist/*.zip

    steps:
      - name: Checkout (with submodules)
        uses: actions/checkout@v4
        with:
          submodules: recursive

      - name: Setup pnpm 9
        uses: pnpm/action-setup@v3
        with:
          version: 9

      - name: Setup Node.js 20
        uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: "pnpm"

      - name: Install dependencies
        run: pnpm install --frozen-lockfile

      - name: Build Electron app
        working-directory: packages/electron
        run: pnpm build

      - name: Upload build artifact
        uses: actions/upload-artifact@v4
        with:
          name: ${{ matrix.artifact-name }}
          path: ${{ matrix.artifact-path }}
          if-no-files-found: error
          retention-days: 30

      - name: Upload to GitHub Release (tagged releases only)
        if: startsWith(github.ref, 'refs/tags/v')
        uses: softprops/action-gh-release@v2
        with:
          files: ${{ matrix.artifact-path }}
          generate_release_notes: false   # release.yml owns release notes
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

---

### Step 4 — Create `.github/workflows/release.yml`

This workflow:
- Triggers when a tag matching `v*` is pushed (e.g. `v0.1.0`).
- Waits for both `build-container.yml` and `build-electron.yml` to succeed on the same SHA.
- Re-tags the Docker image `:latest` → `:[tag-name]` and `:stable`.
- Creates a GitHub Release with auto-generated release notes from commits.
- Attaches the Windows `.exe` and macOS `.zip` artifacts.

```yaml
# .github/workflows/release.yml
name: Release

on:
  push:
    tags:
      - "v*"

jobs:
  # ── Wait for upstream workflows to pass on this tag commit ─────────────────
  wait-for-container:
    name: Wait — build-container.yml
    uses: ./.github/workflows/build-container.yml
    permissions:
      contents: read
      packages: write

  wait-for-electron:
    name: Wait — build-electron.yml
    uses: ./.github/workflows/build-electron.yml
    permissions:
      contents: read
      packages: write

  # ── Retag Docker image and create GitHub Release ───────────────────────────
  release:
    name: Create GitHub Release
    needs: [wait-for-container, wait-for-electron]
    runs-on: ubuntu-latest

    permissions:
      contents: write   # required to create releases
      packages: write   # required to push re-tagged image

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Log in to GHCR
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Extract version tag
        id: tag
        run: echo "version=${GITHUB_REF_NAME}" >> "$GITHUB_OUTPUT"

      - name: Re-tag Docker image as versioned and :stable
        run: |
          docker pull ghcr.io/fox-in-the-box-ai/cloud:latest
          docker tag  ghcr.io/fox-in-the-box-ai/cloud:latest \
                      ghcr.io/fox-in-the-box-ai/cloud:${{ steps.tag.outputs.version }}
          docker tag  ghcr.io/fox-in-the-box-ai/cloud:latest \
                      ghcr.io/fox-in-the-box-ai/cloud:stable
          docker push ghcr.io/fox-in-the-box-ai/cloud:${{ steps.tag.outputs.version }}
          docker push ghcr.io/fox-in-the-box-ai/cloud:stable

      - name: Download Windows artifact
        uses: actions/download-artifact@v4
        with:
          name: fox-windows
          path: release-artifacts/windows
          run-id: ${{ github.run_id }}

      - name: Download macOS artifact
        uses: actions/download-artifact@v4
        with:
          name: fox-macos
          path: release-artifacts/macos
          run-id: ${{ github.run_id }}

      - name: Create GitHub Release
        uses: softprops/action-gh-release@v2
        with:
          tag_name: ${{ steps.tag.outputs.version }}
          generate_release_notes: true
          files: |
            release-artifacts/windows/*.exe
            release-artifacts/macos/*.zip
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

> **Note on `workflow_run` vs `needs` with reusable workflows:**  
> The approach above uses [reusable workflow calls](https://docs.github.com/en/actions/using-workflows/reusing-workflows) (`uses: ./.github/workflows/...`) so that `release.yml` directly runs and depends on the upstream jobs. This is simpler and more reliable than `workflow_run` events, which are asynchronous and harder to gate on. The tradeoff is that the container build and Electron build are re-run at tag time — this ensures the artifacts used in the release are freshly built from the exact tagged commit.

---

## Secrets Reference

| Secret | Source | Purpose |
|---|---|---|
| `GITHUB_TOKEN` | Auto-injected by GitHub Actions | Authenticate with GHCR; create releases; upload artifacts |

No additional secrets are required for v0.1. Future versions may add:
- `APPLE_DEVELOPER_ID_*` secrets for macOS code signing.
- `WINDOWS_CODESIGN_*` secrets for Windows code signing.

---

## Acceptance Criteria

All criteria must pass before this task is considered complete.

| # | Criterion | How to verify |
|---|---|---|
| 1 | Push to `main` → Docker image `ghcr.io/fox-in-the-box-ai/cloud:latest` appears on GHCR within 10 minutes | Check `ghcr.io/fox-in-the-box-ai/cloud` package page on GitHub |
| 2 | Push to `main` → Windows `.exe` and macOS `.zip` available as downloadable artifacts in the `build-electron` Actions run | Actions → Build Electron → latest run → Artifacts section |
| 3 | Smoke test in CI: container starts and responds HTTP 200 | `build-container` run log: "✅ /health returned HTTP 200" or "✅ / returned HTTP 200" |
| 4 | Tag push `v0.1.0` → GitHub Release created with Windows `.exe` and macOS `.zip` attached | Releases page on GitHub shows `v0.1.0` with both installer files |
| 5 | PR build: only `build-container.yml` runs, `:dev` tag is pushed, Electron build does **not** run | Open a test PR; confirm only the container workflow appears under Checks |
| 6 | Tag push `v0.1.0` → `ghcr.io/fox-in-the-box-ai/cloud:v0.1.0` and `:stable` tags visible on GHCR | GHCR package tags page shows `v0.1.0`, `latest`, and `stable` |

---

## File Checklist

After completing this task the following files must exist in the repository:

```
.github/
└── workflows/
    ├── build-container.yml
    ├── build-electron.yml
    └── release.yml
```

---

## Known Pitfalls

### 1 — Dockerfile path

The build context is the repo root (`.`), and the Dockerfile is at
`packages/integration/Dockerfile`. The `-f` flag in the `docker build` command
must use the correct path. If Task 03 places the Dockerfile elsewhere (e.g.
`docker/Dockerfile`), update the `-f` argument in `build-container.yml`
accordingly.

### 2 — pnpm cache key on Windows

`actions/setup-node` with `cache: "pnpm"` works on Windows but requires that
`pnpm-lock.yaml` is committed. If the lockfile is absent, remove `cache: "pnpm"`
and add a manual cache step, or simply accept the slower uncached install.

### 3 — macOS unsigned build gatekeeper warning

The macOS `.zip` is built without an Apple Developer certificate (`identity:
null` in `electron-builder.yml`). End users on macOS will see a Gatekeeper
warning on first launch. This is expected for v0.1. Code signing can be added
in a future task once an Apple Developer account is available.

### 4 — Electron build time

`windows-latest` and `macos-latest` runners are significantly slower than
`ubuntu-latest`. Budget 15–25 minutes for a full Electron build matrix. This
is why Electron builds are restricted to `main` pushes and not PRs.

### 5 — `softprops/action-gh-release` version

Use `softprops/action-gh-release@v2` (not `@v1`). The v2 release supports the
latest GitHub API and `generate_release_notes: true`. Pin to a specific SHA in
production for supply-chain safety.

### 7 — `/health` endpoint must exist before CI can pass

The smoke test polls `GET /health`. This endpoint must be implemented in the
Hermes WebUI server (or entrypoint.sh could expose a minimal health responder).
If `/health` returns a non-2xx status or does not exist, the smoke test will
time out after 3 minutes and fail.

**Minimum viable health endpoint:** Return `HTTP 200 {"status": "ok"}` once
supervisord has started all required programs. Task 03/04 must ensure this
exists before CI can go green.

### 8 — arm64 / multi-platform builds (deferred to v0.2+)

The current `build-container.yml` only builds `linux/amd64`. Apple Silicon Mac
server users and Raspberry Pi 4/5 users will run under QEMU emulation, which
is significantly slower.

Add multi-platform support in v0.2 by switching to `docker/build-push-action`
with `platforms: linux/amd64,linux/arm64`. This requires enabling QEMU in CI
(`docker/setup-qemu-action`) and GHCR supports multi-arch manifests natively.
Note the build time will approximately double.

The macOS Electron build already targets both `x64` and `arm64` — this gap
only affects Linux server users on ARM hardware.

If you prefer `workflow_run` over reusable workflow calls in `release.yml`, be
aware that `workflow_run` fires when a workflow *run* completes — not
necessarily the run associated with the tag commit. The reusable-workflow
approach (`uses:`) avoids this ambiguity by running the workflows inline.

---

## Dependencies / Next Steps

| Task | Relationship |
|---|---|
| Task 03 | `build-container.yml` will fail until the Dockerfile exists and builds successfully |
| Task 06 | `build-electron.yml` will fail until `packages/electron/pnpm build` produces artifacts |
| Future: code signing | Add Apple/Windows signing secrets and update `electron-builder.yml` |
| Future: auto-update | Configure `electron-updater` + add a `publish:` target in `electron-builder.yml` |
