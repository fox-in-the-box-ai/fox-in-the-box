# DONE — Tailscale setup (cross-platform)

## Implemented

1. **`packages/integration/entrypoint.sh`**  
   Tailscale Serve runs in a background helper that waits for WebUI `/health`, then polls `tailscale status --json` until `BackendState` is `Running`, then runs `tailscale serve --bg`. This fixes first-time wizard / delayed login (no longer requires `tailscaled.state` before supervisord starts).

2. **`packages/scripts/install.sh`**  
   Login URL discovery reads `/data/logs/tailscaled.log` and `.err` inside the container via `docker exec`, with `docker logs` as fallback (tailscaled output is file-logged by supervisord, not on container stdout).

3. **`packages/integration/Dockerfile`**  
   Adds `foxinthebox` to the `tailscale` group when that group exists so the Hermes WebUI process can run `tailscale login` against the root-owned socket.

4. **Windows Electron (`packages/electron/src/docker-manager.js`)**  
   First-run dialog (Windows only) chooses access mode `1|2|3` matching `install.sh`; preference is stored in `userData/docker-access-mode.json`. `FOX_ACCESS_MODE` overrides. Host publish and `NET_ADMIN`/`/dev/net/tun`/sysctl follow the same rules as the shell installer.

5. **`startup-orchestrator.js` / `main.js`**  
   Call `ensureDockerAccessModeChosen()` before creating the container; tray flow does the same. Remediation text for `ACCESS_MODE_CANCELLED`.

## How to run tests

```bash
pytest tests/integration/test_task03_integration_files.py -v
cd packages/electron && pnpm test
```

(`bats tests/container/test_install.bats` if bats is installed.)

## Notes / Supervisor

- **`forks/hermes-webui`** was not changed; Dockerfile group membership addresses CLI access to tailscaled where applicable.
- Existing Windows installs without `docker-access-mode.json` will see the new dialog once on next launch before the container is created.
