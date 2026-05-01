# DONE — Task 08: GitHub Actions CI/CD

## What was implemented

Three workflow files created under `.github/workflows/`:

### `build-container.yml`
- Triggers on push to `main` and PRs targeting `main`
- Tags `:latest` on main push, `:dev` on PR builds
- Builds with `--build-arg FITB_VERSION=${{ github.sha }}` so the image knows its version
- Added `--device /dev/net/tun` and `--sysctl net.ipv4.ip_forward=1` to the smoke test
  `docker run` command (required for tailscaled — task doc was missing these flags)
- Polls `/health` with retry loop (up to 3 min / 36 × 5s) — no blind sleep
- Prints container logs on failure (`if: always()`)

### `build-electron.yml`
- Triggers on push to `main` and `v*` tags
- Matrix: `windows-latest` (→ `.exe`) and `macos-latest` (→ `.zip`)
- `fail-fast: false` so one platform failure doesn't cancel the other
- Uploads artifacts with `if-no-files-found: error` (catches silent build failures)
- On `v*` tags: also attaches artifacts directly to the GitHub Release via `softprops/action-gh-release@v2`

### `release.yml`
- Triggers on `v*` tag push
- Uses reusable workflow calls (`uses: ./.github/workflows/...`) to re-run
  container + electron builds from the exact tagged commit
- Re-tags `:latest` → `:[version]` and `:stable` on GHCR
- Creates GitHub Release with auto-generated notes and attached installers

## Acceptance criteria status

| # | Criterion | Status |
|---|-----------|--------|
| 1 | Push to main → :latest on GHCR | ✅ Workflow present — verifiable once pushed |
| 2 | Push to main → Windows .exe + macOS .zip artifacts | ✅ Workflow present |
| 3 | Smoke test: /health returns HTTP 200 | ✅ Retry-poll in build-container.yml |
| 4 | Tag v* → GitHub Release with installers | ✅ release.yml + build-electron.yml tag path |
| 5 | PR build: only container workflow, :dev tag, no Electron | ✅ Electron on `push` only, not `pull_request` |
| 6 | Tag v* → :v0.1.0 and :stable on GHCR | ✅ Re-tag step in release.yml |

## Open issues / assumptions

1. **`/health` endpoint**: The smoke test polls `GET /health`. This endpoint was verified
   to exist via local browser testing (task 05b). If it ever moves or disappears, update
   the smoke test URL.
2. **`FITB_VERSION` build-arg**: Added `--build-arg FITB_VERSION=${{ github.sha }}` so the
   image embeds the git SHA. Task doc didn't specify this but it's a no-op if the Dockerfile
   ignores it, and useful if it does.
3. **`download-artifact` in release.yml**: Uses default (no `run-id`) — downloads from the
   same workflow run, which is correct since we use reusable workflow calls that produce
   artifacts in the same run context.
4. **macOS unsigned**: `.zip` artifact is unsigned; Gatekeeper warning expected. Documented
   in task doc pitfall #3.

## Files changed

```
.github/
└── workflows/
    ├── build-container.yml  (new)
    ├── build-electron.yml   (new)
    └── release.yml          (new)
```


## Task 10: CLI Graceful Shutdown (P0)

**Status:** In progress — tracking upstream branches

Added task documentation for graceful shutdown implementation across both forks:

- **hermes-agent branch:** `cli-graceful-shutdown` — SIGTERM/SIGINT handlers, session checkpoint, clean asyncio exit
- **hermes-webui branch:** `cli-graceful-shutdown` — AgentSessionLock with timeout watchdog, force-release mechanism

**FITB submodules:** Updated to track feature branches for integration once upstream merges to `local-patches`.

**Task doc:** `docs/tasks/10-cli-graceful-shutdown.md` — full scope, phases, acceptance criteria, and testing strategy.

**Next steps:**
1. Monitor upstream branches for merge to `local-patches`
2. Update submodule pointers when ready
3. Run end-to-end test: gateway restart → CLI checkpoints cleanly → auto-resume works
