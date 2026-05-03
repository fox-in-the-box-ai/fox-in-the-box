# Done — Baked Hermes in container image

## Implemented

- **`packages/integration/Dockerfile`**: `COPY` `forks/hermes-agent` and `forks/hermes-webui` into `/app/hermes-*`, run `pip install -e` (agent) and webui install (requirements or editable) at **build** time. `ENV FITB_DEV` passes the build-arg through for dev images.
- **`packages/integration/entrypoint.sh`**: Removed runtime git clone / volume pip sync. Production creates **symlinks** `/data/apps/hermes-*` → `/app/hermes-*` so `supervisord.conf` paths stay unchanged and `/data` remains user state. Dev mode (`FITB_DEV=1`): symlinks to `/root/.hermes/*`, then `pip install -e` from mounts so editable installs match bind-mounted code.
- **`.gitattributes`**: Force LF for `packages/integration/**/*.sh` so Windows checkouts do not break Linux shebangs in Docker (fixes `env: bash\r` in container).
- **Tests / UX**: `tests/integration/test_task03_integration_files.py` (Dockerfile COPY forks, qdrant `config-path`, symlink entrypoint assertions), `tests/electron/docker-manager.test.js`, `packages/electron/src/docker-manager.js` (image link + `Syncing` log lines), `.github/workflows/build-container.yml` comments.

## How to run tests

- Electron: `cd packages/electron && pnpm test`
- Integration file checks: `python -m pytest tests/integration/test_task03_integration_files.py -v` (requires `pytest` in the environment)
- Docker: `git submodule update --init --recursive` then `docker build -f packages/integration/Dockerfile -t fitb:local .`

Smoke (this agent): `docker run -d -p 127.0.0.1:9876:8787 fitb:local`, wait ~20s, `curl -sf http://127.0.0.1:9876/health`.

## Assumptions / notes

- **Submodules required** for `docker build`; CI already uses `submodules: recursive`. Local builds must run `git submodule update --init` first.
- **`REQUIREMENTS.md`** still describes the old git-in-volume model in places; Supervisor may want to align docs when convenient (AGENTS: implementer does not maintain REQUIREMENTS).
- Existing volumes with **full git clones** under `/data/apps/hermes-*` are replaced by symlinks on next start (entrypoint logs `Replacing ... with symlink`).

## Supervisor

- Submodule pins in `forks/` flow into the image at build time; no fork edits in this change.

---

## Addendum — Electron: `/dev/net/tun` for tailscaled (Windows Docker)

### Implemented

- **`packages/electron/src/docker-manager.js`**: `HostConfig.Devices` maps `/dev/net/tun` (with existing `NET_ADMIN` + `net.ipv4.ip_forward` sysctl) so supervisord `tailscaled` matches AGENTS.md / `install.sh` expectations.
- **`tests/electron/docker-manager.test.js`**: Asserts the Tailscale-friendly `HostConfig` shape.

### Notes

- If HTTP 500 persists after `tailscaled` stays up, inspect `/data/logs/hermes-gateway.err` in the container for gateway tracebacks.

### Full clean reinstall (Windows desktop)

- Documented in [README.md](README.md) section **Full reset (desktop app)**; helper script [packages/scripts/clean-windows-desktop.ps1](packages/scripts/clean-windows-desktop.ps1).
