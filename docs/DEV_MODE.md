# Dev Mode

Local development with bind-mounted submodules. Lets you iterate on `forks/hermes-agent` and `forks/hermes-webui` without rebuilding the container or pushing tags between every change.

## When to use

- Working on a feature branch in either submodule and want to run it inside the FITB container immediately
- Testing a bug-fix candidate before opening a PR
- Reproducing a production issue against a known-good snapshot

If you're just running the released image as a user, you don't need any of this — see the README quickstart.

## Build the dev image (one-time per Dockerfile change)

```bash
pnpm build:docker:dev
```

What this does:
- Reads `VERSION` (repo root) — currently `0.7.19`
- Builds with `--build-arg FITB_DEV=1`
- Tags the image as `fox-in-the-box:dev`
- Skips the `_clone_app hermes-agent` / `_clone_app hermes-webui` calls in `entrypoint.sh` — the container will use bind-mounted submodules instead

## Run with bind mounts

```bash
pnpm dev:container
```

Wraps:
```bash
docker run -it --rm \
  --cap-add=NET_ADMIN --device /dev/net/tun \
  -p 127.0.0.1:8787:8787 \
  -v $(pwd)/forks/hermes-agent:/root/.hermes/hermes-agent \
  -v $(pwd)/forks/hermes-webui:/root/.hermes/hermes-webui \
  fox-in-the-box:dev
```

Edit code in `forks/*` on your host. The container sees the changes immediately. After a Python change, restart the affected service from inside the container:

```bash
docker exec -it <container> supervisorctl -c /etc/supervisor/supervisord.conf restart hermes-webui
# or hermes-gateway, qdrant, llama-server, tailscaled
```

For static-asset changes (HTML / JS / CSS in `forks/hermes-webui/static/`), just hard-refresh the browser — webui serves static files directly from the bind mount.

## Expected startup output

```
[entrypoint] Dev mode detected (FITB_DEV=1)
[dev-init] Using bind-mounted hermes-agent and hermes-webui
[dev-init] ✓ hermes-agent — branch: feat/your-work, commit: abc1234
[dev-init] ✓ hermes-webui — branch: feat/your-work, commit: def5678
```

If a mount is missing:
```
[dev-init] WARNING: /root/.hermes/hermes-webui/.git not found
[dev-init] Make sure both `-v` flags are present (forks/hermes-agent and forks/hermes-webui)
```

## Prod vs Dev image differences

| Aspect | `fox-in-the-box:dev` | `fox-in-the-box:<version>` (production) |
|---|---|---|
| Build flag | `FITB_DEV=1` | `FITB_DEV=0` (default) |
| Submodule source | Bind-mounted from your host | Cloned from a git tag at build time |
| Tag | `dev` | semver e.g. `0.7.19` |
| Use case | Iterating on submodule code | Released artifact, CI, what users run |

## Common workflows

### Test a feature branch in both submodules together

```bash
cd forks/hermes-agent  && git checkout feat/agent-side-thing
cd ../hermes-webui     && git checkout feat/webui-side-thing
cd ../..

pnpm build:docker:dev
pnpm dev:container
```

### Switch back to mainline mid-session

```bash
# Inside container terminal
exit
# or in another shell:
docker stop <container>
```
Switch the submodule branches with `git checkout master` (note: hermes-webui uses `master`, not `main`), re-run `pnpm dev:container`.

### Reproduce a production-only issue

When dev mode hides the bug, you need the actual built image. Build the production image with the same VERSION as production:

```bash
docker build -f packages/integration/Dockerfile \
  -t fitb:repro --build-arg FITB_VERSION=v0.7.19 .
docker run --rm --cap-add=NET_ADMIN --device /dev/net/tun \
  --sysctl net.ipv4.ip_forward=1 \
  -p 127.0.0.1:8788:8787 \
  -v fitb-repro-data:/data fitb:repro
```

(Port 8788 not 8787 so it doesn't collide with your real install.)

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| "Cannot find `/root/.hermes/hermes-agent/.git`" | Missing or wrong `-v` | Verify both `-v` flags include `:/root/.hermes/...` |
| "Container still cloning from git" | Used `:latest` instead of `:dev` | `pnpm build:docker:dev` then `pnpm dev:container` |
| "My code changes don't show up" | Service has cached bytecode / open file | `supervisorctl restart hermes-webui` (or whichever) |
| "Container won't start, exits in seconds" | Submodule branch references a Python module not yet checked out | Fix the branch state first; `pnpm dev:container` again |

## Related files

- `packages/integration/Dockerfile` — `ARG FITB_DEV` + `ARG FITB_VERSION` plumbing
- `packages/integration/entrypoint.sh` — branches on `FITB_DEV` to skip clone
- `packages/integration/scripts/dev-init.sh` — bind-mount validator that runs in dev mode only
- `package.json` — `dev:container` script (the actual `docker run` invocation)

## Related docs

- [`RELEASE_WORKFLOW.md`](RELEASE_WORKFLOW.md) — how production releases are cut (separate flow)
- [`../qa/SMOKE_CHECKLIST.md`](../qa/SMOKE_CHECKLIST.md) — the verification gate every release must pass
