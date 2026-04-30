# Task 07 — Install Scripts (DONE)

## Implemented

- **`packages/scripts/install.sh`** — Installer per `docs/tasks/07-install-scripts.md` (Linux/macOS detection, Docker bootstrap, GHCR pull, access-mode prompt with Tailscale help, container run, optional Tailscale log/exec flow, systemd or launchd installation, summary).
- **`packages/scripts/foxinthebox.service`** — systemd unit for `docker run` with `__DATA_DIR__` placeholder.
- **`packages/scripts/foxinthebox-updater.service`** — oneshot unit: pull, restart, remove trigger path as specified.
- **`packages/scripts/foxinthebox-updater.path`** — path unit watching `__DATA_DIR__/update.trigger`.
- **`packages/scripts/io.foxinthebox.plist`** — launchd plist with `__DATA_DIR__` placeholders.
- **`tests/container/test_install.bats`** — Bats suite copied verbatim from the task doc.
- **`install.sh`** is executable (`chmod +x`).

No changes under `forks/`.

## Bats

`bats` was not on the default PATH; it was installed with `sudo apt-get install -y bats` so the suite could be run.

### Test output

```
1..7
ok 1 detects Linux platform from uname -s
ok 2 detects macOS platform from uname -s Darwin
ok 3 skips Docker install when docker info succeeds
ok 4 port-only mode uses 0.0.0.0:8787 binding
ok 5 tailscale-only mode binds to 127.0.0.1
ok 6 entering ? shows Tailscale explanation and re-prompts
not ok 7 exits 1 with error when Docker install script fails
# (in test file tests/container/test_install.bats, line 223)
#   `[ "$status" -eq 1 ]' failed
```

(Full `apt-get` run also printed debconf / needrestart messages; omitted here for clarity.)

## Issues / assumptions

1. **Failing test 7 (Docker install failure):** The task-spec `curl` stub prints a single line `#!/usr/bin/env bash; exit 1`. When that line is fed to `sh` (as in `curl ... | sh`), POSIX shells treat `#` as starting a comment for the **entire line**, so the simulated install script is effectively empty and `sh` exits **0**. The pipeline therefore does not fail, `die` is never run, and the test expects status 1 incorrectly. Fixing this would require adjusting the stub or the test (for example `echo exit 1` without a leading `#`), which was out of scope because the task asked for an exact copy of the bats file.

2. **`foxinthebox-updater.service`:** The task text uses `rm -f /data/update.trigger` on the host unit; on the host filesystem the sentinel is under the bind-mounted data dir (e.g. `__DATA_DIR__/update.trigger`). Supervisor may want to align that with the path unit’s host path if updates should clear the trigger reliably.

3. **macOS `sed`:** `install.sh` uses `sed -i ''` only in the macOS branch, which matches the task spec.

## How to re-run tests

```bash
cd /home/ubuntu/workspace/fitb-task-07
bats tests/container/test_install.bats
```

Per user instruction: no `git commit` / `git push` from this session (Supervisor handles that).
