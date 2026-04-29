# DONE — Task 02: Monorepo Scaffold

**Branch / worktree:** `task/02-monorepo-scaffold` → `/home/ubuntu/workspace/fitb-task-02`  
**Executor:** AI implementer (Composer)

---

## What Was Implemented

Structural scaffolding per `docs/tasks/02-monorepo-scaffold.md`, with **task 01 correction**: `hermes-webui` submodule tracks **`master`**, not `main`.

### Added / updated

| Area | Contents |
|------|----------|
| **Root** | `pnpm-workspace.yaml` (`packages/*`), `package.json` with `"packageManager": "pnpm@9.0.0"` and aggregate scripts (`install:all`, `build`, `test`, `lint`, `dev`, `clean`). |
| **`packages/integration/`** | Stub `Dockerfile`, `supervisord.conf`, `entrypoint.sh`; `default-configs/hermes.yaml`, `hermes.env.template`, `onboarding.json`. |
| **`packages/electron/`** | Minimal `package.json` + stub `src/main.js` (task-specified TODO/console stub). |
| **`packages/scripts/`** | Stub `install.sh`; `dev/` with `.gitkeep`. |
| **`.github/workflows/`** | Empty workflows dir with `.gitkeep`. |
| **`tests/`** | `integration/`, `electron/`, `container/` each with `.gitkeep`. |

### Not completed in this session (needs Supervisor / local shell)

Automated **terminal commands were unavailable** in this environment (every shell invocation returned **Rejected** with no output). The following must be run **before** this branch meets all acceptance criteria:

1. **Executable bits**

   ```bash
   chmod +x packages/integration/entrypoint.sh packages/scripts/install.sh
   ```

2. **Git submodules** (token embedded URL per your instructions; **`master`** for webui):

   ```bash
   cd /home/ubuntu/workspace/fitb-task-02
   GITHUB_TOKEN=$(grep "^GITHUB_TOKEN=" ~/.hermes/.env | head -1 | cut -d= -f2- | tr -d '\n\r')

   git submodule add -b main \
     "https://fox-in-the-box-ai:${GITHUB_TOKEN}@github.com/fox-in-the-box-ai/hermes-agent.git" \
     forks/hermes-agent

   git submodule add -b master \
     "https://fox-in-the-box-ai:${GITHUB_TOKEN}@github.com/fox-in-the-box-ai/hermes-webui.git" \
     forks/hermes-webui
   ```

   Do **not** edit tracked files inside `forks/*` after add (submodules are read-only for implementer).

3. **pnpm**

   ```bash
   npm install -g pnpm@9   # if needed
   cd /home/ubuntu/workspace/fitb-task-02
   pnpm install
   ```

---

## Verification (task doc)

Use **`cd /home/ubuntu/workspace/fitb-task-02`** (this worktree), not `fox-in-the-box`, when copying the task doc’s verification block.

### Verbatim terminal output from this session

**None.** Shell execution was not available here; no `pnpm install`, `git submodule`, or verification loop output could be captured.

### Static checks performed without shell (workspace files)

These reflect repo contents **before** submodules, chmod, and `pnpm install`:

| Check | Result |
|-------|--------|
| `pnpm-workspace.yaml` | Present |
| Root `package.json` with `pnpm@9.0.0` `packageManager` | Present |
| `.gitmodules` | **Not present yet** — created when submodules are added |
| `packages/integration/Dockerfile`, `supervisord.conf`, `entrypoint.sh` | Present |
| `packages/integration/default-configs/*` (three files) | Present |
| `packages/electron/package.json`, `src/main.js` | Present |
| `packages/scripts/install.sh` | Present |
| `.github/workflows/` | Present (`.gitkeep`) |
| `packages/scripts/dev/` | Present (`.gitkeep`) |
| `tests/integration/`, `tests/electron/`, `tests/container/` | Present (`.gitkeep` each) |
| `forks/hermes-agent`, `forks/hermes-webui` populated submodules | **Pending** `git submodule add` |
| `entrypoint.sh` / `install.sh` executable (`-x`) | **Pending** `chmod +x` |

---

## How to Re-run Full Verification (after Supervisor steps)

From repo root of this worktree:

```bash
cd /home/ubuntu/workspace/fitb-task-02

# 1. Check key files exist
for f in \
  pnpm-workspace.yaml \
  package.json \
  .gitmodules \
  packages/integration/Dockerfile \
  packages/integration/supervisord.conf \
  packages/integration/entrypoint.sh \
  packages/integration/default-configs/hermes.yaml \
  packages/integration/default-configs/hermes.env.template \
  packages/integration/default-configs/onboarding.json \
  packages/electron/package.json \
  packages/electron/src/main.js \
  packages/scripts/install.sh; do
  [ -f "$f" ] && echo "OK: $f" || echo "MISSING: $f"
done

# 2. Check directories exist
for d in \
  .github/workflows \
  forks/hermes-agent \
  forks/hermes-webui \
  tests/integration \
  tests/electron \
  tests/container \
  packages/scripts/dev; do
  [ -d "$d" ] && echo "OK: $d/" || echo "MISSING: $d/"
done

# 3. Check executables
[ -x packages/integration/entrypoint.sh ] && echo "OK: entrypoint.sh is executable" || echo "FAIL: entrypoint.sh not executable"
[ -x packages/scripts/install.sh ]        && echo "OK: install.sh is executable"   || echo "FAIL: install.sh not executable"

# 4. pnpm workspace install
pnpm install && echo "OK: pnpm install succeeded" || echo "FAIL: pnpm install failed"

# 5. Git submodule status (both must appear)
git submodule status | grep "forks/hermes-agent"  && echo "OK: hermes-agent submodule" || echo "FAIL: hermes-agent submodule missing"
git submodule status | grep "forks/hermes-webui"  && echo "OK: hermes-webui submodule" || echo "FAIL: hermes-webui submodule missing"

# 6. Confirm packageManager field in root package.json
grep '"packageManager"' package.json | grep "pnpm@9" && echo "OK: pnpm@9 declared" || echo "FAIL: packageManager field wrong"
```

Expected after manual completion: all lines **`OK:`**, no **`MISSING:`** or **`FAIL:`**.

---

## Assumptions & Notes

- **`forks/`** is intentionally excluded from the pnpm workspace (only `packages/*`); submodule URLs must match GitHub org repos under `fox-in-the-box-ai`.
- **`pnpm-lock.yaml`** will appear after the first successful `pnpm install`; commit policy is up to Supervisor.
- Stub **`packages/electron/src/main.js`** includes `console.log` exactly as in the task doc — task 06 replaces real Electron wiring.

---

## Supervisor Attention

1. Run **`chmod`**, **`git submodule add`** (main vs **master** as above), and **`pnpm install`**; paste verification script output into PR/commit notes if you need recorded proof (this `DONE.md` cannot supply verbatim logs).
2. Submodule **directory order**: add `hermes-agent` first, then `hermes-webui`, if uncommitted tree demands sequential adds (typical `git submodule add` workflow).
