## What changed

Supervisord’s Unix RPC socket and pidfile were moved from `/data/run/` to `/run/fitb/` so the container starts when `/data` is **bind-mounted from the host** (Docker Desktop on macOS or Windows). On those setups, creating an AF_UNIX socket on the shared mount fails with `errno.EINVAL (22)`, which supervisord reports as **“Cannot open an HTTP server”**, then the container exits and restart policies loop.

## How to verify

```bash
python -m pytest tests/integration/test_task03_integration_files.py -v
```

Rebuild the image and run with your usual `-v ~/…:/data` mount; supervisord should stay up.

## Notes for Supervisor

- Task docs under `docs/tasks/` still mention `/data/run` for the supervisord socket in a few places; update if you want docs aligned with `/run/fitb/`.
- No submodule or fork changes.
