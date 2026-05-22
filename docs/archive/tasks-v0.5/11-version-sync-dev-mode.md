# Task 11: Version Sync & Dev Mode

**Priority:** Medium (quality-of-life for developers)  
**Status:** Complete  
**Epic:** Development experience  
**Components:** 
- VERSION file (source of truth)
- Dockerfile (FITB_VERSION + FITB_DEV args)
- package.json (build:docker, build:docker:dev, dev:container commands)
- entrypoint.sh (conditional clone vs bind-mount)
- dev-init.sh (validation script)

---

## Problem Solved

**Before:**
- Version was hardcoded in multiple places (package.json, Dockerfile, manual sync)
- Testing required full docker build → clone → wait (5-10 min per iteration)
- No easy way to test feature branches without modifying Dockerfile

**After:**
- Single VERSION file at repo root
- Dev mode: build once, mount local code, iterate instantly
- Clear separation: production clones from git tags, dev uses bind mounts

---

## Solution Overview

### 1. Single Source of Truth: VERSION file

**File:** `/VERSION` (repo root)  
**Content:** Single line with semver (e.g., `0.1.0`)  
**Usage:**
```bash
# Read by build scripts
$(cat VERSION)

# Sourced by:
# - Dockerfile ARG FITB_VERSION
# - package.json build:docker script
# - Electron app version display
```

### 2. Build Variants

**Production build:**
```bash
pnpm build:docker
# → docker build ... -t fox-in-the-box:$(cat VERSION)
# → Clones hermes-agent/webui from git tags at build time
```

**Dev build:**
```bash
pnpm build:docker:dev
# → docker build ... --build-arg FITB_DEV=1 -t fox-in-the-box:dev
# → Skips git clone, expects bind mounts at runtime
```

### 3. Dev Mode Workflow

**Setup (one-time):**
```bash
pnpm build:docker:dev
```

**Run with bind mounts:**
```bash
pnpm dev:container
# Or manually:
docker run -it --rm \
  --cap-add=NET_ADMIN \
  --device /dev/net/tun \
  -p 127.0.0.1:8787:8787 \
  -v $(pwd)/forks/hermes-agent:/root/.hermes/hermes-agent \
  -v $(pwd)/forks/hermes-webui:/root/.hermes/hermes-webui \
  fox-in-the-box:dev
```

**Iterate:**
```bash
# Terminal 1: container running
pnpm dev:container

# Terminal 2: make changes (bind mount auto-syncs)
cd forks/hermes-agent
git checkout feature/my-fix
# ... edit ...

# Terminal 3: container sees changes immediately
# (May need: supervisorctl restart hermes)
```

---

## Implementation Details

### Dockerfile

```dockerfile
ARG FITB_VERSION=v0.1.0
ARG FITB_DEV=0

RUN echo "${FITB_VERSION}" > /app/version.txt
COPY packages/integration/scripts/ /app/scripts/
```

### entrypoint.sh

```bash
FITB_DEV=${FITB_DEV:-0}

if [ "$FITB_DEV" = "1" ]; then
    echo "Dev mode — skipping git clone"
    /app/scripts/dev-init.sh
else
    _clone_app hermes-agent
    _clone_app hermes-webui
fi
```

### dev-init.sh

Validates bind mounts are present:
```
✓ hermes-agent bound (Branch: feature/foo, Commit: abc1234)
✓ hermes-webui bound (Branch: fix/bar, Commit: def5678)
```

Exits with error if mounts missing (clear UX).

### package.json

```json
{
  "scripts": {
    "build:docker": "docker build -f packages/integration/Dockerfile -t fox-in-the-box:$(cat VERSION) .",
    "build:docker:dev": "docker build ... --build-arg FITB_DEV=1 -t fox-in-the-box:dev .",
    "dev:container": "docker run -it ... -v $(pwd)/forks/hermes-agent:... -v $(pwd)/forks/hermes-webui:... fox-in-the-box:dev"
  }
}
```

---

## Acceptance Criteria

- [x] VERSION file created at repo root
- [x] Dockerfile updated with FITB_VERSION and FITB_DEV args
- [x] entrypoint.sh reads FITB_DEV and skips clone when set
- [x] dev-init.sh validates bind mounts and reports branch/commit
- [x] package.json has build:docker, build:docker:dev, dev:container commands
- [x] DEV_MODE.md documents workflow with examples
- [x] Production build still works (backward compatible)

---

## Testing

### Prod mode (unchanged behavior)
```bash
pnpm build:docker
docker run -p 127.0.0.1:8787:8787 fox-in-the-box:0.1.0
# Should clone hermes-agent and hermes-webui on first run
```

### Dev mode (new)
```bash
pnpm build:docker:dev
pnpm dev:container
# Container should validate bind mounts and start cleanly
```

### Version update
```bash
echo "0.2.0" > VERSION
pnpm build:docker
# Image should be tagged :0.2.0
# entrypoint writes 0.2.0 to /app/version.txt
```

---

## Files Changed

| File | Change |
|------|--------|
| `VERSION` | Created (0.1.0) |
| `Dockerfile` | +FITB_DEV arg, updated comments |
| `entrypoint.sh` | +FITB_DEV logic, conditional clone |
| `package.json` | +build:docker, build:docker:dev, dev:container |
| `scripts/dev-init.sh` | New validation script |
| `DEV_MODE.md` | New documentation |
| `docs/tasks/11-version-sync-dev-mode.md` | This file |

---

## Next Steps

1. Test dev mode end-to-end
2. Update CI to use VERSION file for image tagging
3. Publish DEV_MODE.md in project README
4. Consider auto-increment VERSION on release

---

## Related

- Task 08: CI/CD (uses `--build-arg FITB_VERSION=${{ github.sha }}`)
- Task 07: Docker setup (container build/run)
- Task 03: Dockerfile (initial setup)
