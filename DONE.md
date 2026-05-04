# Done — Linux Docker detection in `install.sh`

## What changed

- **Cause:** With Docker already installed, the script skipped the branch that sets `DOCKER_CMD="sudo docker"` after `usermod -aG docker`. If the daemon was healthy but the current user could not use `/var/run/docker.sock` (not in `docker` group yet), `docker info` failed and the installer waited until timeout, then showed a macOS-only error.
- **Fix:** On Linux, before (and during) the wait loop, call `_docker_linux_use_sudo_if_needed`: if `docker info` fails but `sudo -n docker info` succeeds, set `DOCKER_CMD="sudo docker"` and continue. Linux failure message now mentions `systemctl`, `docker` group, and `sudo docker info`.
- **Tests:** New bats case with stubs for `sudo -n docker info` (must handle `-n` like real sudo).

## How to verify

```bash
cd tests/container && bats test_install.bats
```

## Notes

- Requires **passwordless** `sudo` for the `sudo -n` probe (typical on Ubuntu cloud images). If `sudo` needs a password, the script still cannot proceed non-interactively; the new Linux error text points to group membership and `sudo docker info`.
