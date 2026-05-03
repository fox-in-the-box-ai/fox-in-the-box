# WIP — macOS release: DMG removed, install script documented

## Implemented

- **CI / releases:** Removed macOS from the Electron build matrix; tagged releases attach only the Windows `.exe` (no DMG). `release.yml` no longer downloads or ships a macOS artifact.
- **`electron-builder.yml`:** macOS target is unsigned **`.zip`** (local `pnpm build --mac`) — no DMG or signing/entitlements config.
- **`README.md`:** Option 1 is the **same `install.sh` curl|bash flow for Linux and macOS**; Option 3 is Windows-only; Docker one-liner aligned with localhost bind + `--device /dev/net/tun` + sysctl; macOS full-reset section updated for script/Docker users.
- **`install.sh`:** `_docker_running` now respects `DOCKER_CMD` (e.g. `sudo docker` immediately after `usermod -aG docker`).
- **`foxinthebox.service` / `io.foxinthebox.plist`:** Added `--device /dev/net/tun` so long-running installs match the container (Tailscale/`tailscaled`) and `install.sh` / Electron `docker-manager.js`.
- **Docs aligned:** `REQUIREMENTS.md`, `ROADMAP.md`, `docs/RELEASE_WORKFLOW.md`, `docs/LIGHTSAIL_TEST_CHECKLIST.md`, `docs/tasks/08-github-actions.md`, and archive notes — no DMG as a release artifact; macOS = `install.sh`.

## How to verify

- `bats tests/container/test_install.bats` (if `bats` is installed).
- Review workflow YAML in GitHub Actions tab after merge.

## Notes

- `bats` was not available in this environment; install tests were not executed here.
- AGENTS.md prefers task work on a `task/*` branch; this change was committed from the repo’s current branch.
