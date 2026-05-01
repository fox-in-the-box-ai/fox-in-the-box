# Dev Mode — Version Sync & Local Testing

## Overview

**Dev mode** lets you test FITB changes with local code mounts instead of cloning from git tags. Perfect for rapid iteration on `hermes-agent` and `hermes-webui` features.

---

## Version Sync System

### Single Source of Truth

All version references now read from `/VERSION` at the repo root:

```
VERSION (repo root)
  ↓
  ├─ package.json (build:docker scripts)
  ├─ Dockerfile (ARG FITB_VERSION)
  └─ Electron app display
```

### Build commands

```bash
# Production: read VERSION file, tag image as 0.1.0
pnpm build:docker
# → docker build ... -t fox-in-the-box:$(cat VERSION)

# Dev: read VERSION, tag as 'dev', enable FITB_DEV=1
pnpm build:docker:dev
# → docker build ... --build-arg FITB_DEV=1 -t fox-in-the-box:dev
```

### Updating version

```bash
echo "0.2.0" > VERSION
pnpm build:docker  # ← builds as :0.2.0

# Also updates package.json version manually if needed
```

---

## Dev Mode Workflow

### 1. Build dev image (once)

```bash
pnpm build:docker:dev
# Builds with FITB_DEV=1 flag
# Skips git clone logic in entrypoint
```

### 2. Run container with bind mounts

```bash
pnpm dev:container
# Mounts:
#   forks/hermes-agent    → /root/.hermes/hermes-agent
#   forks/hermes-webui    → /root/.hermes/hermes-webui
# Container uses LOCAL code, not git tags
```

Or manually:

```bash
docker run -it --rm \
  --cap-add=NET_ADMIN \
  --device /dev/net/tun \
  -p 127.0.0.1:8787:8787 \
  -v $(pwd)/forks/hermes-agent:/root/.hermes/hermes-agent \
  -v $(pwd)/forks/hermes-webui:/root/.hermes/hermes-webui \
  fox-in-the-box:dev
```

### 3. Iterate (outside container)

```bash
# Terminal 1: container running
pnpm dev:container

# Terminal 2: make changes locally
cd forks/hermes-agent
git checkout -b feature/my-change
# ... edit code ...

# Terminal 3: container sees changes immediately (bind mount)
# Restart services inside container if needed:
#   supervisorctl restart hermes
```

---

## Dev Mode Behavior

When `FITB_DEV=1` during build:

### Entrypoint changes
- ✅ Still creates `/data/config`, `/data/cache`, etc. (first-run setup)
- ❌ Skips `_clone_app hermes-agent` and `_clone_app hermes-webui`
- ✅ Runs `scripts/dev-init.sh` to verify bind mounts are present
- ✅ Logs branch + commit of mounted repos for debugging

### Expected output on startup

```
[entrypoint] Dev mode detected (FITB_DEV=1)
[dev-init] Dev mode initialization — using bind-mounted hermes-agent and hermes-webui
[dev-init] ✓ hermes-agent bind mount detected
[dev-init]   Branch: feature/my-change
[dev-init]   Commit: abc1234
[dev-init] ✓ hermes-webui bind mount detected
[dev-init]   Branch: fix/sidebar
[dev-init]   Commit: def5678
```

If a mount is missing:

```
[dev-init] WARNING: /root/.hermes/hermes-webui/.git not found
[dev-init] Make sure you mounted it: -v $(pwd)/forks/hermes-webui:/root/.hermes/hermes-webui
```

---

## Prod vs Dev Build Matrix

| Aspect | Production | Dev |
|--------|-----------|-----|
| **Build cmd** | `pnpm build:docker` | `pnpm build:docker:dev` |
| **FITB_VERSION** | From VERSION file | From VERSION file |
| **FITB_DEV** | 0 (clone from git) | 1 (skip clone, use mounts) |
| **Image tag** | `0.1.0`, `latest`, etc. | `dev` |
| **Entrypoint** | Clones hermes-agent/webui | Skips clone, runs dev-init |
| **Mount mounts** | Not needed | Required for hermes-agent/.git, hermes-webui/.git |
| **Use case** | Production container, CI/CD, releases | Local dev, testing, feature branches |

---

## Testing Scenarios

### Test P0 bug fix before merge

```bash
# Check out feature branch in both forks
cd forks/hermes-agent && git checkout feature/cli-graceful-shutdown
cd forks/hermes-webui && git checkout feature/session-lock-watchdog

# Build dev image
pnpm build:docker:dev

# Run with mounts
pnpm dev:container

# Test inside container
hermes chat  # or whatever you're testing
```

### Test version upgrade path

```bash
# Update VERSION
echo "0.2.0" > VERSION

# Build prod image
pnpm build:docker

# In entrypoint, version migration logic runs
# (scripts/migrations/v0.1.0_to_v0.2.0.sh, if exists)
```

### Test container image after release

```bash
# Simulate release build
pnpm build:docker
# Image is tagged as :0.1.0 (or whatever VERSION contains)

# Push to GHCR manually (CI does this automatically)
docker tag fox-in-the-box:0.1.0 ghcr.io/fox-in-the-box-ai/cloud:0.1.0
docker push ghcr.io/fox-in-the-box-ai/cloud:0.1.0
```

---

## Implementation Details

### Dockerfile changes

```dockerfile
ARG FITB_VERSION=v0.1.0
ARG FITB_DEV=0

# ... later ...

RUN echo "${FITB_VERSION}" > /app/version.txt
# Entrypoint reads this to decide what to clone

COPY packages/integration/scripts/ /app/scripts/
# Includes dev-init.sh
```

### Entrypoint logic

```bash
if [ "$FITB_DEV" = "1" ]; then
    echo "[entrypoint] Dev mode detected — skipping git clone"
    /app/scripts/dev-init.sh
else
    echo "[entrypoint] Production mode — cloning from git tags"
    _clone_app hermes-agent
    _clone_app hermes-webui
fi
```

---

## Troubleshooting

### "Cannot find /root/.hermes/hermes-agent/.git"

**Cause:** Bind mount not provided or path is wrong.

**Fix:**
```bash
# Make sure you're running with both mounts:
docker run ... \
  -v $(pwd)/forks/hermes-agent:/root/.hermes/hermes-agent \
  -v $(pwd)/forks/hermes-webui:/root/.hermes/hermes-webui \
  fox-in-the-box:dev
```

### "Container still cloning from git"

**Cause:** Using `fox-in-the-box:latest` instead of `fox-in-the-box:dev`.

**Fix:**
```bash
# Rebuild dev image
pnpm build:docker:dev

# Run dev image explicitly
docker run ... fox-in-the-box:dev  # not :latest
```

### "Changes I make locally don't appear in container"

**Cause:** Container cached old Python bytecode or Node modules.

**Fix:**
```bash
# Inside container, restart affected service
supervisorctl restart hermes

# Or restart entire container
docker restart <container_id>
```

---

## Next Steps

1. ✅ VERSION file created at repo root
2. ✅ Dockerfile updated to read FITB_VERSION + FITB_DEV args
3. ✅ package.json build:docker + build:docker:dev + dev:container commands
4. ✅ dev-init.sh script validates bind mounts
5. ⏳ Update entrypoint.sh to use FITB_DEV flag (next commit)
6. ⏳ Test dev mode workflow end-to-end

---

## See also

- `packages/integration/Dockerfile` — build args, entrypoint setup
- `packages/integration/entrypoint.sh` — runtime logic
- `packages/integration/scripts/dev-init.sh` — bind mount validation
