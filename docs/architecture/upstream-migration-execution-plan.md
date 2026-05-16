# Upstream Migration Execution Plan
**Status:** READY FOR DECISION (BLOCKING: see Open Questions)
**Date:** 2026-05-16
**Author:** Architect 1 (commissioned by Dennis Vorobyov)
**Builds on:** `docs/architecture/upstream-separation-plan.md` (the 827-line research synthesis)
**Repo:** `/Users/macpro/Documents/Fox-In-the-Box/project` (v0.5.4 in tree)
**Drift at time of writing:** 1,526 commits behind on `hermes-agent`, 1,238 behind on `hermes-webui`, growing ~70/day

---

## 1. Executive summary

The 2026-05-08 research synthesis recommended a **hybrid** end state: re-point the `forks/hermes-{agent,webui}` submodules at virgin upstream pinned to a tag, hold all Fox-specific code in a sibling `packages/fox-overlay/` package, ship a curated patch series of ~9 lines / 2 files in webui (0 in agent), and adopt upstream's plugin manager (now 17 hooks) plus the `HERMES_WEBUI_EXTENSION_DIR` mechanism for everything additive. The Dockerfile gains three short stages: COPY upstream → apply patches → overlay. The Electron app, install scripts, supervisord, qdrant/llama.cpp tarballs, and the release/signing pipeline are all out of scope and untouched.

This plan operationalizes that recommendation as a **10-phase migration** (one phase split out of the original 9 to honor anti-regression Rule 1: "one big change per release"). Total effort is **~14 engineering days** over a **~5-week calendar window** including the mandatory 48-hour soak after every tag bump that exposes user-facing change. Each phase produces a green Docker container and an individually revertible PR.

The single highest-value early action is **Phase 0 (Upstream-PR campaign)**: send the 5 bug-fix-class FITB commits to NousResearch and nesquena. Each accepted PR shrinks the patch series forever, and three of the five (`runtime_provider.py`, `auxiliary_client.py`, `models.py` #1558) are textbook upstream candidates.

The work is reversible at every phase. The only point-of-no-return is Phase 7 (submodule re-point), and even that is one `git revert` away from rollback because the submodule pointer is just a SHA in the parent repo.

**Recommendation:** GO once the three Open Questions are resolved. The drift gap closes by ~70 commits per day; every week of delay adds ~2 days of patch resolution at first sync.

---

## 2. Dependency graph

```
                Phase 0 (PR campaign, async)
                    │
                    ▼
Phase 1 ── Phase 2 ── Phase 3 ── Phase 4 ── Phase 5 ── Phase 6 ── Phase 7 ── Phase 8 ── Phase 9
(scaffold) (statics)  (agent)   (patches) (additive) (modified) (onboard)  (re-point) (CI watch)
                                                                                         │
                                                                                         ▼
                                                                              Phase 10 (cleanup)

PARALLEL SAFE:
  • Phase 0 runs throughout — async, depends on upstream review velocity, never blocks.
  • Phase 2 and Phase 3 can run in parallel (different repos, different concerns).
  • Phase 5's per-module migrations are independent; can be parallelized across one engineer
    (commit-by-commit) or two (if a second pair of hands is available).

STRICT SERIAL:
  • Phase 4 must precede Phase 5/6 — the 9-line dispatcher patches are the ONLY way
    additive Python modules can register routes.
  • Phase 7 must follow Phases 1–6 — re-pointing the submodule before the overlay
    can host everything Fox needs would break the build.
  • Phase 8 (CI nightly upstream-watch) must follow Phase 7 — it has nothing to bump
    until the submodule points at virgin upstream.
  • Phase 9 cleanup must be last — deletes scaffolding the prior phases relied on.

48-HOUR SOAK GATES (anti-regression Rule 2):
  • Required after Phase 7 (submodule re-point — first user-visible structural change).
  • Required after Phase 9 if any user-facing wording / asset / route changes during cleanup.
  • Not required after intermediate phases that produce byte-identical runtime.
```

---

## 3. Go / No-Go preconditions

Do NOT start Phase 1 until **all** of the following are true.

### Code preconditions

- [ ] `main` is at v0.5.4 stable; no in-flight feature branches blocking on shared files (`api/routes.py`, `static/index.html`, `static/panels.js`, `api/streaming.py`, `api/onboarding.py`, `api/config.py`).
- [ ] All v0.5.4 follow-on stabilization issues (#138/#139/#140) closed; smoke checklist Section L row for v0.5.4 passes against `:stable`.
- [ ] No open PR on the fox-in-the-box-ai/hermes-{webui,agent} forks awaiting merge — they will be invalidated by the submodule re-point.
- [ ] `.github/workflows/sync-submodules.yml` is **paused** (workflow_dispatch only, no `repository_dispatch`) for the duration of the migration. Auto-bumping mid-migration would whipsaw the pin.

### Roadmap preconditions

- [ ] Phase 1 (v0.5.5: `fox-guardrails` + Presidio PII per `project_roadmap_v0_5_to_v0_9.md`) is explicitly **paused** by Dennis, or the migration is sequenced to ship as v0.5.5 in place of guardrails. Per anti-regression Rule 1 ("one large change per release") the two cannot share a version.
- [ ] Decision recorded on Open Question #1 (where this slots in roadmap).
- [ ] Decision recorded on Open Question #2 (cadence: dedicated sprint vs. interleaved).
- [ ] Decision recorded on Open Question #3 (Phase 0 PR campaign first or skip).

### Team capacity preconditions

- [ ] One engineer with 14 days of focused capacity over a 5-week window, OR two engineers with explicit ownership split (engineer A: Phases 1–4, 7; engineer B: Phases 5, 6, 8). Phase 5/6 splits naturally on per-module boundaries.
- [ ] Dennis available for two scheduled review checkpoints: end of Phase 4 (patch series locked), end of Phase 7 (submodule re-point passed smoke).
- [ ] Real-hardware tester available for the Phase 7 smoke (full SMOKE_CHECKLIST.md A–L, est. 30 min if green).

### Infrastructure preconditions

- [ ] Verification container pattern from `reference_test_container.md` works cleanly on Apple Silicon and an x86_64 host. Both required to catch architecture regressions like #114.
- [ ] Standalone clones at `~/Documents/Fox-In-the-Box/hermes-{agent,webui}` have `upstream` remote configured with `push = DISABLED` (verified — they do).
- [ ] Branch protection rules on `fox-in-the-box-ai/hermes-{webui,agent}` are confirmed not to block the planned `fitb-overlay-archive` tag push (Phase 7 step 7.3).

If any box is unchecked, do not proceed. Document the blocker in the issue tracker.

---

## 4. Phases

Each phase below includes: Goal, Prerequisites, Concrete file operations, Code skeletons (where load-bearing), Validation gates, Rollback procedure, Effort estimate, Suggested PR/issue split, and Risks specific to this phase.

---

### Phase 0 — Upstream-PR campaign (async, runs parallel to all other phases)

**Goal.** Each accepted upstream PR removes one commit from Fox's permanent patch surface. Even partial acceptance reduces ongoing maintenance.

**Prerequisites.** None. Runs entirely on the standalone clones; does not touch the monorepo.

**Concrete file operations.** None in monorepo. In standalone clones, branch and PR per below.

Targets (in priority order — bug fixes first, new behavior last):

| # | Source path | Upstream | Branch | One-line scope |
|---|---|---|---|---|
| 1 | `hermes_cli/runtime_provider.py` | NousResearch/hermes-agent | `fitb/fix-target-model-bedrock` | One-line `target_model` fix for Bedrock api_mode routing |
| 2 | `api/models.py` (#1558) | nesquena/hermes-webui | `fitb/fix-1558-metadata-save` | P0 metadata-only Session.save guard (data-loss class) |
| 3 | `agent/auxiliary_client.py` | NousResearch/hermes-agent | `fitb/fix-provider-auto-fallback` | `provider=auto` resolution + `auxiliary.default` fallback |
| 4 | `cron/{jobs,scheduler}.py` + `tools/cronjob_tools.py` | NousResearch/hermes-agent | `fitb/feat-cron-failure-diagnostics` | Rolling-5 failure history + diagnostics fields |
| 5 | `api/providers.py` | nesquena/hermes-webui | `fitb/fix-providers-hot-reload` | Gateway hot-reload after key change |

**Validation gates.** Each upstream PR must (a) include unit tests if the file has tests, (b) declare `Upstream-Status: Submitted <PR-URL>` in the corresponding Fox commit message in the standalone clone, (c) reference the FITB issue if any.

**Rollback.** N/A — these are upstream PRs. If rejected, the patch stays in Fox's series; no monorepo state changes.

**Effort estimate.** 1.5 engineering days spread across 1–4 weeks of upstream review latency. Assume ~30% acceptance rate → 1–2 commits removed.

**Suggested PR/issue split.**
- Issue: "Phase 0: Upstream PR campaign — track 5 candidate fixes" (parent tracking issue)
- 5 PRs against upstreams as listed above; one Fox-side issue per PR to track upstream review.

**Risks.**
- Maintainers reject or sit on PRs for weeks. **Mitigation:** time-boxed; do not block the migration on Phase 0 outcomes.
- A PR is accepted but lands with significant rework that conflicts with our patch. **Mitigation:** carry both versions until the corresponding Fox patch can be retired cleanly, then drop in Phase 9.

---

### Phase 1 — Scaffold `packages/fox-overlay/` skeleton

**Goal.** Empty overlay package exists at `packages/fox-overlay/`, installable via `pip install -e`. Container builds and runs identically to today (overlay imports nothing, registers nothing). PR is mergeable to `main` with zero behavior change.

**Prerequisites.** Go/No-Go checklist passed. No prior phase required.

**Concrete file operations.**

```
packages/fox-overlay/
├── pyproject.toml                          # NEW
├── MANIFEST.toml                           # NEW (empty inventory placeholder)
├── README.md                               # NEW (one-paragraph description + link to this doc)
├── .fox-removals                           # NEW (empty file; one-path-per-line manifest)
├── fox_overlay/                            # NEW package
│   ├── __init__.py                         # NEW (empty)
│   ├── bootstrap.py                        # NEW (no-op skeleton — see code below)
│   ├── webui_modules/                      # NEW (empty package, ready for Phase 5)
│   │   └── __init__.py
│   ├── webui_patches/                      # NEW (empty package, ready for Phase 6)
│   │   └── __init__.py
│   └── agent_plugins/                      # NEW (empty package, ready for Phase 3)
│       └── __init__.py
├── webui_static/                           # NEW (empty dir, .gitkeep)
│   └── .gitkeep
├── patches/                                # NEW
│   ├── webui/
│   │   └── series                          # NEW (empty)
│   └── agent/
│       └── series                          # NEW (empty)
└── scripts/
    └── check-overlay-basis.sh              # NEW (no-op stub returning 0)
```

`pyproject.toml` skeleton:

```toml
[project]
name = "fox-overlay"
version = "0.0.1"
description = "Fox in the Box overlay for hermes-agent and hermes-webui"
requires-python = ">=3.11"
dependencies = []

[project.entry-points."hermes_agent.plugins"]
# fox_overlay = "fox_overlay:register"   # commented until Phase 3

[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["fox_overlay*"]
```

`fox_overlay/bootstrap.py` (load-bearing skeleton, will grow in Phases 4/6):

```python
"""Fox overlay bootstrap. Imported by hermes-webui's server.py before any api.* imports.

Phase 1: no-op. Phases 4–6 will populate install() with monkey-patches and dispatcher
registration. Until then this module exists so the import line in server.py is harmless.
"""
import logging

_log = logging.getLogger("fox_overlay.bootstrap")
_INSTALLED = False


def install() -> None:
    """Apply Fox overlay to a running hermes-webui process. Idempotent."""
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True
    _log.info("[fox-overlay] bootstrap installed (no-op skeleton)")


# Auto-install on import. Anything that imports fox_overlay.bootstrap gets the patch.
install()
```

**Dockerfile changes (this phase): none.** The overlay package exists in the tree but isn't `pip install`'d yet. Behavior is unchanged.

**Validation gates.**
- `pip install -e packages/fox-overlay` from a fresh venv succeeds without errors.
- `python -c "import fox_overlay.bootstrap"` prints the install log line and exits 0.
- Build the verification container (port 8788) per `reference_test_container.md`. Run smoke A1–A4 only. All green.
- `git diff main...HEAD` — only adds files under `packages/fox-overlay/`. No edits to existing files.

**Rollback.** `git revert <merge-commit>`. The overlay dir disappears; no other code touched.

**Effort estimate.** 4 hours.

**Suggested PR/issue split.**
- PR: "phase 1: scaffold packages/fox-overlay/ (no behavior change)"

**Risks.**
- `pip install -e` interaction with existing `packages/electron/` workspace if pnpm-workspace.yaml accidentally globs it. **Mitigation:** verify `pnpm-workspace.yaml` only enumerates JS packages.
- Future `setuptools.packages.find` ambiguity if other dirs are added under `packages/`. **Mitigation:** `include = ["fox_overlay*"]` is explicit.

---

### Phase 2 — Move static files into overlay; wire `HERMES_WEBUI_EXTENSION_DIR`

**Goal.** Every Fox-only static asset (CSS, JS, fonts, images, setup wizard HTML) lives in `packages/fox-overlay/webui_static/`. The container serves them through upstream's existing `extensions.py` mechanism. The fork's `static/` directory shrinks by exactly the count of Fox-only files. Runtime is byte-identical to today (verified by checksum diff).

**Prerequisites.** Phase 1 merged.

**Concrete file operations.**

Move (preserving git history with `git mv`):

```
forks/hermes-webui/static/fox-in-the-box.css   → packages/fox-overlay/webui_static/fox-in-the-box.css
forks/hermes-webui/static/fox-in-the-box.js    → packages/fox-overlay/webui_static/fox-overlay.js
forks/hermes-webui/static/fox_avatar_cropped.jpg → packages/fox-overlay/webui_static/images/fox_avatar_cropped.jpg
forks/hermes-webui/static/fonts/*              → packages/fox-overlay/webui_static/fonts/
forks/hermes-webui/static/setup.html           → packages/fox-overlay/webui_static/setup.html
forks/hermes-webui/static/setup.css            → packages/fox-overlay/webui_static/setup.css
forks/hermes-webui/static/setup.js             → packages/fox-overlay/webui_static/setup.js
forks/hermes-webui/static/onboarding-preview.js → packages/fox-overlay/webui_static/onboarding-preview.js
forks/hermes-webui/static/fallback-polish.js   → packages/fox-overlay/webui_static/fallback-polish.js
forks/hermes-webui/static/hostname-prompt.js   → packages/fox-overlay/webui_static/hostname-prompt.js
forks/hermes-webui/static/apple-touch-icon.png → packages/fox-overlay/webui_static/apple-touch-icon.png
```

(NOTE: `git mv` across submodule boundary requires per-submodule branches: branch in standalone hermes-webui clone for the deletion, branch in monorepo for the addition; merge fork-side first, then bump the submodule pointer atomically with the monorepo PR per `feedback_cross_repo_cohesion.md`.)

Append to `packages/fox-overlay/MANIFEST.toml`:

```toml
[static]
fox-in-the-box.css   = "fox-only"
fox-overlay.js       = "fox-only"
setup.html           = "fox-only"
setup.css            = "fox-only"
setup.js             = "fox-only"
# ... etc
```

Add to `packages/fox-overlay/.fox-removals` — these are upstream onboarding files Fox deletes:

```
static/onboarding.js
tests/test_issue1499_keyless_onboarding.py
tests/test_issue1499_onboarding_probe.py
tests/test_onboarding_existing_config.py
tests/test_onboarding_mvp.py
tests/test_onboarding_network.py
tests/test_onboarding_static.py
```

Edit `packages/integration/Dockerfile` — insert immediately after the existing line 128 (`COPY forks/hermes-webui /app/hermes-webui`):

```dockerfile
# ── Fox overlay: static files ─────────────────────────────────────────────────
COPY packages/fox-overlay/webui_static /app/fox-overlay/webui_static
ENV HERMES_WEBUI_EXTENSION_DIR=/app/fox-overlay/webui_static \
    HERMES_WEBUI_EXTENSION_SCRIPT_URLS=/extensions/fox-overlay.js \
    HERMES_WEBUI_EXTENSION_STYLESHEET_URLS=/extensions/fox-in-the-box.css
```

Edit `forks/hermes-webui/static/index.html` (in the standalone fork): remove the explicit `<link>` to `fox-in-the-box.css` and the explicit `<script>` for `fox-in-the-box.js` — the `extensions.py` injector will now provide them.

**Validation gates.**
- Smoke checklist Section A (container health) all green.
- Section B (onboarding wizard B1–B9) all green — the wizard is the highest-risk asset because it's served from `setup.html`.
- Section C (settings persistence) green — fonts/CSS unaffected.
- View-source comparison: `curl http://127.0.0.1:8788/` before vs after must contain (a) the `<link rel="stylesheet" href="/extensions/fox-in-the-box.css">` injection, (b) the `<script defer src="/extensions/fox-overlay.js">` injection, (c) all other markup byte-identical except those two diffs.
- HTTP status 200 on `/extensions/fox-in-the-box.css`, `/extensions/fox-overlay.js`, `/extensions/setup.html`, `/extensions/setup.js`, `/extensions/setup.css`, all font files.
- File checksums (sha256) of every moved asset match before vs. after.

**Rollback.** Two-step revert: (a) revert monorepo PR (drops the COPY + ENV vars and the .fox-removals append); (b) revert hermes-webui fork PR (restores `static/*` files). Both are clean reverts. Submodule pointer rolls back automatically when the monorepo PR is reverted.

**Effort estimate.** 1 engineering day (1 day fork-side, 0.5 day monorepo-side; overlap with the cohesion sequencing).

**Suggested PR/issue split.**
- Fork PR: "phase 2a (webui): move Fox-only static assets out of static/ — to be served via HERMES_WEBUI_EXTENSION_DIR"
- Monorepo PR: "phase 2b: serve Fox static via overlay extension dir; bump hermes-webui submodule"

**Risks.**
- Some upstream code (e.g. `static/index.html` or `boot.js`) hard-references one of the moved file paths (e.g. `/static/fox-in-the-box.css` literal). **Mitigation:** `grep -r "fox-in-the-box\|fox_avatar\|setup.html\|setup.js" forks/hermes-webui/` before moving; rewrite or proxy.
- Service worker (`sw.js`) caches the old paths. **Mitigation:** the smoke checklist mandates `sw.js` cache disable verification (Section A2). Bump the SW version string in the overlay JS to invalidate.
- Font MIME types not in `extensions.py`'s `_EXTENSION_MIME` map. **Mitigation:** verify `_EXTENSION_MIME` covers `woff`, `woff2`, `ttf`, `otf`; if not, this becomes a 1-line upstream PR (Phase 0 candidate #6) OR a one-line monkey-patch in the bootstrap shim.
- Cap of 32 URLs per env var (per `extensions.py`). Fox's overlay JS/CSS is comma-separated; comma-joining stays under cap.

---

### Phase 3 — Migrate hermes-agent plugin + bootstrap monkey-patches

**Goal.** All hermes-agent customizations live in `packages/fox-overlay/fox_overlay/agent_plugins/` and are loaded via the upstream plugin manager's `hermes_agent.plugins` entry-point. The `mem0_oss` plugin gets the missing `kind: backend` field added to its manifest. The 5 modified-file customizations in hermes-agent become monkey-patches applied at agent startup. **Zero patches** in hermes-agent fork.

**Prerequisites.** Phase 1 merged. Can run concurrently with Phase 2.

**Concrete file operations.**

In monorepo:

```
packages/fox-overlay/fox_overlay/agent_plugins/
├── __init__.py                              # NEW (entry-point target — see below)
├── fox_overlay_plugin/                      # NEW
│   ├── __init__.py                          # NEW (register() function — see below)
│   ├── plugin.yaml                          # NEW (manifest with kind: backend)
│   └── monkey_patches/
│       ├── __init__.py
│       ├── runtime_provider.py              # NEW (target_model fix as patch)
│       ├── auxiliary_client.py              # NEW (provider=auto fallback as patch)
│       └── cron_diagnostics.py              # NEW (3 cron file changes as patches)
└── mem0_oss/                                # MOVED from forks/hermes-agent/plugins/memory/mem0_oss/
    ├── __init__.py                          # (unchanged source)
    ├── README.md                            # (unchanged source)
    └── plugin.yaml                          # MODIFIED: add `kind: backend`
```

Update `pyproject.toml` entry-points:

```toml
[project.entry-points."hermes_agent.plugins"]
fox_overlay = "fox_overlay.agent_plugins:register"
mem0_oss = "fox_overlay.agent_plugins.mem0_oss:register"
```

`fox_overlay/agent_plugins/__init__.py` skeleton:

```python
"""Fox overlay registration for hermes-agent's plugin manager.

Called by hermes_cli.plugins.PluginManager.discover_and_load via the
'hermes_agent.plugins' entry-point group. Applies bootstrap monkey-patches
at register() time so they're in place before any code path runs.
"""
from .fox_overlay_plugin.monkey_patches import (
    runtime_provider, auxiliary_client, cron_diagnostics,
)


def register(ctx):
    """Entry point. ctx is a PluginContext from hermes_cli.plugins."""
    runtime_provider.apply()
    auxiliary_client.apply()
    cron_diagnostics.apply()
    # Future: ctx.register_hook("transform_llm_output", fox_guardrails.transform)
```

Each monkey-patch module follows this pattern (example — `runtime_provider.py`):

```python
"""Fox patch: use target_model for Bedrock api_mode routing.

Replaces the 1-line bug in upstream resolve_runtime_provider. If accepted
upstream (Phase 0 PR #1), this module becomes dead code and is removed in Phase 9.
"""
import inspect
from hermes_cli import runtime_provider

_PATCHED_SENTINEL = "_fox_patched_target_model"


def apply():
    if getattr(runtime_provider.resolve_runtime_provider, _PATCHED_SENTINEL, False):
        return
    original = runtime_provider.resolve_runtime_provider
    sig = inspect.signature(original)
    assert "target_model" in sig.parameters or "model" in sig.parameters, (
        "[fox-overlay] upstream signature changed; refresh patch")

    def patched(*args, **kwargs):
        # ... fixed body here ...
        return original(*args, **kwargs)

    patched._fox_patched_target_model = True
    runtime_provider.resolve_runtime_provider = patched
    import logging
    logging.getLogger("fox-overlay").info(
        "[fox-overlay] patched hermes_cli.runtime_provider.resolve_runtime_provider")
```

In hermes-agent fork (standalone clone), branch `fitb/phase3-restore-upstream`:
- Delete the 5 modified-file Fox edits (`hermes_cli/runtime_provider.py`, `agent/auxiliary_client.py`, `cron/jobs.py`, `cron/scheduler.py`, `tools/cronjob_tools.py`) — restore upstream content.
- Delete `plugins/memory/mem0_oss/` — relocated.
- Keep `.github/workflows/notify-monorepo.yml` as-is (Fox-side CI).

Edit `packages/integration/Dockerfile` (after the existing line 130 `pip install -e /app/hermes-agent`):

```dockerfile
# ── Fox overlay: install package; entry-points wire into hermes_agent.plugins ─
COPY packages/fox-overlay /app/fox-overlay
RUN pip install --no-cache-dir -e /app/fox-overlay
```

**Validation gates.**
- `hermes plugins list` (executed inside the container) shows `fox_overlay` and `mem0_oss` registered.
- `hermes` startup logs include four `[fox-overlay] patched ...` lines.
- mem0 memory operations succeed end-to-end (Section D scenarios in smoke).
- Cron failure diagnostics still surface in `cron list-failures` (carry forward from v0.4.x cron tests).
- Agent boots cleanly with `--check` (no missing-attribute traceback from the monkey-patch self-tests).

**Rollback.** Two-step revert: (a) monorepo PR revert removes the overlay install line and entry-points; (b) hermes-agent fork PR revert restores the 5 modified files + mem0_oss directory. Submodule pointer rolls back via the monorepo revert.

**Effort estimate.** 1.5 engineering days (heavier than Phase 2 because of the inspect-based safety checks).

**Suggested PR/issue split.**
- Fork PR: "phase 3a (agent): restore upstream content for 5 files; remove mem0_oss (relocated to fox-overlay)"
- Monorepo PR: "phase 3b: implement fox-overlay agent plugin + monkey-patches; bump hermes-agent submodule"

**Risks.**
- One of the 5 files has been refactored upstream beyond what the monkey-patch can wrap. **Mitigation:** the `inspect.signature` self-test fires at startup; CI catches it.
- mem0_oss `plugin.yaml` schema requires more than `kind` (per upstream v0.13.0 plugin manifest validation). **Mitigation:** follow `forks/hermes-agent/plugins/memory/mem0/plugin.yaml` (sibling reference plugin) as the schema oracle.
- Entry-point name collision with another plugin in `~/.hermes/plugins/`. **Mitigation:** namespace as `fox_overlay` (already done).

---

### Phase 4 — Land 9-line webui patches (the only mid-file edits)

**Goal.** Two minimal patches exist in `packages/fox-overlay/patches/webui/`. The fork's `server.py` has a 3-line bootstrap import; the fork's `api/routes.py` has 6 lines (3 in `handle_get`, 3 in `handle_post`) calling `fox_overlay.dispatch()` before falling through. With overlay absent, the patches are no-ops (the `import` fails silently in a `try/except`; the dispatch returns False). Patch series file is populated and ordered.

**Prerequisites.** Phases 1, 3 merged. Phase 2 strongly recommended (so the static side already proves the overlay is loadable).

**Concrete file operations.**

Create `packages/fox-overlay/patches/webui/series`:

```
001-server-py-bootstrap.patch
002-routes-py-dispatch-hook.patch
```

Create `packages/fox-overlay/patches/webui/001-server-py-bootstrap.patch`:

```diff
--- a/server.py
+++ b/server.py
@@ -1,5 +1,8 @@
 import os
 import sys
+try:
+    import fox_overlay.bootstrap  # noqa: F401  -- installs Fox patches at import
+except ImportError:
+    pass
 import threading
```

Create `packages/fox-overlay/patches/webui/002-routes-py-dispatch-hook.patch`:

```diff
--- a/api/routes.py
+++ b/api/routes.py
@@ -42,6 +42,9 @@
 def handle_get(handler, parsed):
+    from fox_overlay import dispatch  # lazy import — no-op if unavailable
+    if dispatch.handle_get(handler, parsed):
+        return True
     # existing upstream body unchanged below
@@ -612,6 +615,9 @@
 def handle_post(handler, parsed):
+    from fox_overlay import dispatch  # lazy import — no-op if unavailable
+    if dispatch.handle_post(handler, parsed):
+        return True
     # existing upstream body unchanged below
```

Create `packages/fox-overlay/fox_overlay/dispatch.py`:

```python
"""Fox dispatcher. Called by the 6-line patch in api/routes.py before upstream body.

Phase 4: skeleton — handle_get/handle_post return False (no-op) until Phase 5
populates the dispatch table.
"""
from typing import Any

_GET_TABLE: dict = {}
_POST_TABLE: dict = {}


def register_get(path_prefix: str, handler):
    _GET_TABLE[path_prefix] = handler


def register_post(path_prefix: str, handler):
    _POST_TABLE[path_prefix] = handler


def handle_get(handler, parsed) -> bool:
    for prefix, fn in _GET_TABLE.items():
        if parsed.path.startswith(prefix):
            return bool(fn(handler, parsed))
    return False


def handle_post(handler, parsed) -> bool:
    for prefix, fn in _POST_TABLE.items():
        if parsed.path.startswith(prefix):
            return bool(fn(handler, parsed))
    return False
```

Edit Dockerfile to apply patches between the upstream COPY and the overlay COPY (insert between lines 128 and 130):

```dockerfile
# ── Fox patch series (mid-file edits we cannot express as overlay) ────────────
COPY packages/fox-overlay/patches/webui /tmp/p
RUN cd /app/hermes-webui \
 && for p in $(grep -v '^\s*$\|^\s*#' /tmp/p/series); do \
        echo "Applying $p"; \
        git apply --check "/tmp/p/$p" || { echo "::error::patch $p failed --check"; exit 1; }; \
        git apply "/tmp/p/$p"; \
    done \
 && rm -rf /tmp/p
```

(NOTE: `git apply` requires `git` in the image — already installed.)

In hermes-webui standalone fork, on a `fitb/phase4-restore-upstream-server-routes` branch: revert the existing Fox edits to `server.py` and `api/routes.py`. The patches in monorepo are now the source of truth for those edits.

**Validation gates.**
- `git apply --check` succeeds against the pinned upstream during build (it currently still points at fox fork — that's fine; the patch file is small enough to apply cleanly to either base).
- Container starts; `[fox-overlay] bootstrap installed` log line appears.
- All Section A–B–C smoke checks green.
- `curl /api/setup/skip` (POST) returns 200 — confirms Phase 5/6 dispatch path is wired but empty.
- Behavior is byte-identical to before this phase for any path Fox has not yet migrated (because the dispatch table is empty).

**Rollback.** (a) revert monorepo PR (drops the patches + Dockerfile changes); (b) revert hermes-webui fork PR (restores `server.py` and `api/routes.py` Fox edits inline).

**Effort estimate.** 0.5 engineering days.

**Suggested PR/issue split.**
- Fork PR: "phase 4a (webui): restore upstream server.py + api/routes.py (Fox edits move to overlay patch series)"
- Monorepo PR: "phase 4b: introduce fox-overlay patch series + Dockerfile apply step + dispatcher skeleton"

**Risks.**
- The 3-line `import fox_overlay.bootstrap` block runs before logging is configured. **Mitigation:** swallow the ImportError silently; log line emits later from inside `install()`.
- A future upstream refactor of `handle_get` shifts line numbers beyond `git apply`'s default fuzz tolerance (3 lines). **Mitigation:** the patches use anchor lines (`def handle_get(handler, parsed):`) that are extremely stable; if drift exceeds tolerance, refresh the patch in CI before bump.
- The `_ensure_active_branch()` startup hook (still present in current `server.py`) is now misaligned with the new model. **Mitigation:** delete `_ensure_active_branch()` in the same fork PR (it becomes dead code once the submodule re-points in Phase 7; deleting it now is harmless).

---

### Phase 5 — Migrate additive webui Python modules into overlay

**Goal.** Six fully-additive Python modules (`api/ollama.py`, `api/tailscale.py`, `api/local_fallback.py`, `api/models_download.py`, `api/hostname.py`, `api/session_recovery.py`) live in `packages/fox-overlay/fox_overlay/webui_modules/`. Each registers its routes via the dispatcher introduced in Phase 4. Fork's `api/` directory shrinks by 6 files. No mid-file upstream edits in this phase.

**Prerequisites.** Phase 4 merged.

**Concrete file operations.**

For each of the 6 modules, repeat:

1. In standalone hermes-webui fork: `git rm api/<module>.py`.
2. In monorepo: place the same file at `packages/fox-overlay/fox_overlay/webui_modules/<module>.py`.
3. Adapt imports: `from api.helpers import ...` becomes `from api.helpers import ...` (still works — these still ship as upstream; the overlay imports them at module-load time).
4. At the bottom of each migrated module, register routes:

```python
# At bottom of fox_overlay/webui_modules/ollama.py:
from fox_overlay import dispatch

def _register():
    dispatch.register_get("/api/ollama/", handle_ollama_get)
    dispatch.register_post("/api/ollama/", handle_ollama_post)

_register()
```

5. Update `packages/fox-overlay/MANIFEST.toml`:

```toml
[python]
"fox_overlay.webui_modules.ollama"           = "fox-only-additive"
"fox_overlay.webui_modules.tailscale"        = "fox-only-additive"
"fox_overlay.webui_modules.local_fallback"   = "fox-only-additive"
"fox_overlay.webui_modules.models_download"  = "fox-only-additive"
"fox_overlay.webui_modules.hostname"         = "fox-only-additive"
"fox_overlay.webui_modules.session_recovery" = "fox-only-additive"
```

6. Add eager imports to `fox_overlay/__init__.py` so registration fires on import:

```python
from .webui_modules import (
    ollama, tailscale, local_fallback, models_download, hostname, session_recovery,
)
```

**Validation gates.** Per migrated module, run the corresponding smoke checklist section:
- `ollama.py` → Section D5–D7
- `tailscale.py` → Section E full
- `local_fallback.py` + `models_download.py` → Section F full + G + H
- `hostname.py` → Section I
- `session_recovery.py` → Section L (#127–#129 carry-forward)

**Rollback.** Per-module revert. Each migration is a standalone PR with its own fork-PR pair and monorepo-PR pair.

**Effort estimate.** 2 engineering days (one ~1.5h slot per module; the `local_fallback`/`tailscale`/`session_recovery` triad takes longer because their smoke sections take longer).

**Suggested PR/issue split.** One PR per module pair (fork side + monorepo side):
- "phase 5a (webui-fork): remove api/ollama.py — migrated to overlay"
- "phase 5b (monorepo): host api/ollama via fox-overlay; bump hermes-webui submodule"
- ... repeat for each of the 6 modules

**Risks.**
- A migrated module references a private upstream symbol that gets renamed. **Mitigation:** import-time check for symbol existence with `getattr(module, "_private_thing", None)`; log + degrade gracefully.
- Two migrated modules accidentally register overlapping path prefixes in the dispatcher. **Mitigation:** dispatcher logs every registration at INFO; unit-test in `packages/fox-overlay/tests/test_dispatch_no_overlap.py` (add in this phase).
- The dispatcher's `startswith()` matching is too permissive (e.g. `/api/ollamax` would match `/api/ollama/`). **Mitigation:** require trailing slash in registered prefixes, OR switch to exact-prefix-with-segment-boundary; document the contract in `dispatch.py` docstring.

---

### Phase 6 — Migrate modified-upstream webui patches as monkey-patches

**Goal.** Five files Fox edits mid-stream (`api/streaming.py`, `api/models.py`, `api/config.py`, `api/providers.py`, `api/updates.py`) become monkey-patches in `packages/fox-overlay/fox_overlay/webui_patches/`. Fork restores those files to upstream content. Each monkey-patch logs at startup. No corresponding patch in the patch series — these are runtime mutations, not static patches.

**Prerequisites.** Phase 4 merged. Phase 5 strongly recommended (proves the overlay-import lifecycle works end-to-end before adding monkey-patches that depend on it).

**Concrete file operations.**

For each modified file, create a `webui_patches/<name>.py`. Skeleton example for `streaming.py` (silent-failover-to-local-on-remote-error):

```python
"""Fox patch: silent failover to local model on remote provider error (#129b)."""
import inspect
from api import streaming as _u

_PATCHED = "_fox_patched_streaming"


def apply():
    if getattr(_u._handle_provider_error, _PATCHED, False):
        return
    original = _u._handle_provider_error
    # signature self-check
    sig = inspect.signature(original)
    assert {"context", "error"}.issubset(sig.parameters), (
        "[fox-overlay] api.streaming._handle_provider_error signature changed; "
        "refresh patch fox_overlay/webui_patches/streaming.py")

    def patched(context, error, *a, **kw):
        # ... Fox failover body here ...
        return original(context, error, *a, **kw)

    patched._fox_patched_streaming = True
    _u._handle_provider_error = patched
    import logging
    logging.getLogger("fox-overlay").info(
        "[fox-overlay] patched api.streaming._handle_provider_error")
```

Repeat for: `models.py` (Session.save metadata-only fix #1558), `config.py` (Tailscale + fallback + Ollama URL config keys), `providers.py` (gateway hot-reload), `updates.py` (rewritten or deleted — Phase 9 may delete entirely).

Append all patch invocations to `fox_overlay/bootstrap.py`:

```python
def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True
    from .webui_patches import streaming, models, config, providers
    streaming.apply(); models.apply(); config.apply(); providers.apply()
    _log.info("[fox-overlay] bootstrap installed (5 webui patches)")
```

In standalone hermes-webui fork: revert the 5 files to upstream content.

**Validation gates.**
- All 4 `[fox-overlay] patched api.<file>.<symbol>` log lines appear in container startup logs.
- Smoke Section D (provider switching) green — covers `models.py`, `providers.py`, `config.py`.
- Smoke Section G (reactive failover) and Section H (recovery banner) green — covers `streaming.py`.
- Settings persistence (Section C) green — covers `config.py`.
- Specifically test #1558 regression: existing `test_metadata_save_wipe_1558.py` (which stays in fork's `tests/` since it's a Fox-authored test) must pass.

**Rollback.** Per-patch revert — each patch is a separate file. The monorepo PR can be staged as 5 sequential commits (one per patch) so individual reverts don't disturb other patches.

**Effort estimate.** 3 engineering days. This is the highest-effort phase because each monkey-patch needs a signature check, a smoke section, and a rollback test.

**Suggested PR/issue split.** Five PRs in monorepo (one per patch), one fork PR per release of monorepo PRs. Per anti-regression Rule 1 ("one large change per release"), Phase 6 itself is one logical change so the 5 sub-PRs can land in one merge window.
- "phase 6 (webui-fork): restore upstream content for streaming.py, models.py, config.py, providers.py, updates.py"
- "phase 6a (monorepo): monkey-patch streaming silent failover"
- "phase 6b (monorepo): monkey-patch models Session.save #1558"
- "phase 6c (monorepo): monkey-patch config Fox env vars"
- "phase 6d (monorepo): monkey-patch providers gateway hot-reload"
- "phase 6e (monorepo): patch or delete updates.py (covered by submodule re-point in Phase 7)"

**Risks.**
- Order of monkey-patches matters: `config.py` must apply before any module reads its settings. **Mitigation:** `bootstrap.install()` orders `config` first; document the order constraint.
- Upstream renamed `_handle_provider_error`. **Mitigation:** the inspect.signature self-test fires at import; CI fails fast.
- A monkey-patch double-applies because two import paths hit `bootstrap.install()`. **Mitigation:** `_INSTALLED` global gate (already in skeleton).

---

### Phase 7 — Wholesale-replace `api/onboarding.py` and handle deleted `static/onboarding.js`

**Goal.** Fox's onboarding flow lives entirely in `packages/fox-overlay/fox_overlay/webui_modules/onboarding.py`, registered via the dispatcher. Upstream's `api/onboarding.py` is unchanged (no patch); when both are loaded, Fox's dispatcher fires first and upstream's becomes dead code. The `static/onboarding.js` file is removed via the `.fox-removals` manifest.

**Prerequisites.** Phases 4 and 5 merged.

**Concrete file operations.**

Move `forks/hermes-webui/api/onboarding.py` → `packages/fox-overlay/fox_overlay/webui_modules/onboarding.py` (same `git mv` cross-submodule pattern as Phase 5).

Wrap the module so it claims the relevant route prefixes:

```python
# At bottom of fox_overlay/webui_modules/onboarding.py:
from fox_overlay import dispatch
dispatch.register_get("/api/onboarding/", _fox_onboarding_get)
dispatch.register_post("/api/onboarding/", _fox_onboarding_post)
dispatch.register_get("/setup", _fox_setup_html)        # Fox's setup wizard HTML
dispatch.register_post("/api/setup/", _fox_setup_post)  # Fox's setup wizard endpoints
```

Append to `.fox-removals`:

```
static/onboarding.js
```

(Already added in Phase 2; verify no duplication.)

In standalone hermes-webui fork: `git rm api/onboarding.py`. Restore upstream onboarding tests that we deleted (`test_issue1499_*`, `test_onboarding_*`) — they will now run against the upstream module; if they pass, great; if they fail because Fox's dispatcher intercepts, document and skip-mark them with `pytest.mark.skipif(os.environ.get("FOX_OVERLAY"))` upstream-rebased.

Add to Dockerfile (after the `pip install -e fox-overlay` line):

```dockerfile
# ── Apply Fox removals: upstream files Fox does not ship ──────────────────────
RUN cd /app/hermes-webui \
 && grep -v '^\s*$\|^\s*#' /app/fox-overlay/.fox-removals \
    | xargs -r -I{} rm -f -- {}
```

**Validation gates.**
- Smoke Section B (B1–B9) all green — full wizard walk-through.
- Smoke Section L row for #122 (always-3-step flow) green.
- `curl /api/onboarding/status` returns Fox's response shape, not upstream's.
- `curl /static/onboarding.js` returns 404.
- Upstream onboarding tests skip cleanly (no errors).

**Rollback.** Per the Phase 2/Phase 5 pattern: revert monorepo PR + revert fork PR. The `.fox-removals` manifest reverts atomically with the monorepo PR.

**Effort estimate.** 1 engineering day.

**Suggested PR/issue split.**
- Fork PR: "phase 7a (webui): remove api/onboarding.py — Fox dispatcher takes over"
- Monorepo PR: "phase 7b: host Fox onboarding via overlay; remove upstream onboarding.js via .fox-removals"

**Risks.**
- Upstream's onboarding has shipped Codex OAuth + new flows since Fox forked. Hidden routes (e.g. `/api/onboarding/codex-callback`) Fox doesn't claim get served by upstream and confuse users. **Mitigation:** Fox's dispatcher claims `/api/onboarding/` (full prefix) — upstream's body never runs for those URLs. If Codex OAuth is desired, ship as a separate Fox feature later.
- `_ensure_active_branch()` in fork's `server.py` was already deleted in Phase 4. Re-confirm it's gone.

---

### Phase 8 — Re-point submodules at upstream tags; switch Dockerfile to multi-stage

**Goal.** `forks/hermes-webui` submodule URL = `https://github.com/nesquena/hermes-webui.git`, pinned to tag `v0.51.22` (or current latest). `forks/hermes-agent` submodule URL = `https://github.com/NousResearch/hermes-agent.git`, pinned to `v2026.5.7` (= v0.13.0). `versions.toml` records both. The Dockerfile gains a multi-stage layout. **This is the point of structural change** — first phase requiring the 48-hour soak per anti-regression Rule 2.

**Prerequisites.** Phases 1–7 merged. All smoke checks green against the existing Fox-fork-pinned submodules. Patch series in `packages/fox-overlay/patches/webui/` confirmed to apply against the chosen upstream tag (dry-run before merging this phase's PR).

**Concrete file operations.**

Create `versions.toml` at repo root:

```toml
[upstream]
hermes_agent_tag = "v2026.5.7"          # = hermes-agent v0.13.0, 2026-05-07
hermes_webui_tag = "v0.51.22"           # 2026-05-07
```

Edit `.gitmodules`:

```ini
[submodule "forks/hermes-agent"]
        path = forks/hermes-agent
        url = https://github.com/NousResearch/hermes-agent.git
        branch = v2026.5.7
[submodule "forks/hermes-webui"]
        path = forks/hermes-webui
        url = https://github.com/nesquena/hermes-webui.git
        branch = v0.51.22
[submodule "forks/figma-mcp"]
        # unchanged
```

Re-pin the submodule SHAs:

```bash
cd /Users/macpro/Documents/Fox-In-the-Box/project
git submodule sync forks/hermes-webui
git submodule sync forks/hermes-agent
git -C forks/hermes-webui fetch --tags origin
git -C forks/hermes-webui checkout v0.51.22
git -C forks/hermes-agent fetch --tags origin
git -C forks/hermes-agent checkout v2026.5.7
git add forks/hermes-{webui,agent}
```

Restructure Dockerfile (replace lines 127–139 of current Dockerfile with):

```dockerfile
# ── Hermes app source (virgin upstream submodules) ────────────────────────────
COPY forks/hermes-agent /app/hermes-agent
COPY forks/hermes-webui /app/hermes-webui

# ── Apply Fox patch series ────────────────────────────────────────────────────
COPY packages/fox-overlay/patches /tmp/fox-patches
RUN set -eux; \
    for sub in webui agent; do \
        if [ -f "/tmp/fox-patches/$sub/series" ]; then \
            cd "/app/hermes-$sub"; \
            for p in $(grep -v '^\s*$\|^\s*#' "/tmp/fox-patches/$sub/series"); do \
                echo "[fox-patch] applying $sub/$p"; \
                git apply --check "/tmp/fox-patches/$sub/$p" \
                  || { echo "::error::patch $sub/$p failed --check against pinned upstream"; exit 1; }; \
                git apply "/tmp/fox-patches/$sub/$p"; \
            done; \
        fi; \
    done; \
    rm -rf /tmp/fox-patches

# ── Install upstream packages ─────────────────────────────────────────────────
RUN set -eux; \
    pip install --no-cache-dir -e /app/hermes-agent --quiet; \
    if [ -f /app/hermes-webui/pyproject.toml ] || [ -f /app/hermes-webui/setup.py ]; then \
        pip install --no-cache-dir -e /app/hermes-webui --quiet; \
    elif [ -f /app/hermes-webui/requirements.txt ]; then \
        pip install --no-cache-dir -r /app/hermes-webui/requirements.txt --quiet; \
    fi

# ── Install Fox overlay ───────────────────────────────────────────────────────
COPY packages/fox-overlay /app/fox-overlay
RUN pip install --no-cache-dir -e /app/fox-overlay

# ── Apply .fox-removals (deleted-upstream-files manifest) ─────────────────────
RUN cd /app/hermes-webui \
 && grep -v '^\s*$\|^\s*#' /app/fox-overlay/.fox-removals \
    | xargs -r -I{} rm -f -- {}

# ── Static overlay env vars ───────────────────────────────────────────────────
ENV HERMES_WEBUI_EXTENSION_DIR=/app/fox-overlay/webui_static \
    HERMES_WEBUI_EXTENSION_SCRIPT_URLS=/extensions/fox-overlay.js \
    HERMES_WEBUI_EXTENSION_STYLESHEET_URLS=/extensions/fox-in-the-box.css

RUN chown -R foxinthebox:foxinthebox /app/hermes-agent /app/hermes-webui /app/fox-overlay
```

Implement `packages/fox-overlay/scripts/check-overlay-basis.sh` (was a stub since Phase 1 — make it real):

```bash
#!/bin/sh
# Detect upstream rename/delete of any file referenced in .fox-removals.
# Runs as a CI gate before Docker build; failure means Phase 7's submodule
# pin needs to be rolled back to the previous tag and the migration plan
# updated for the upstream restructure.
set -eu
REPO_ROOT=$(cd "$(dirname "$0")/../.." && pwd)
FORK="$REPO_ROOT/forks/hermes-webui"
REMOVALS="$REPO_ROOT/packages/fox-overlay/.fox-removals"
fail=0
while IFS= read -r line; do
  case "$line" in ''|\#*) continue ;; esac
  if [ ! -e "$FORK/$line" ]; then
    echo "::error::.fox-removals expects $line in upstream — not found in pinned tag"
    fail=1
  fi
done < "$REMOVALS"
exit "$fail"
```

Update `.github/workflows/build-container.yml` to run `check-overlay-basis.sh` before the Docker build step.

Delete from fork (already gone since Phase 4) — confirm:
- `forks/hermes-webui/scripts/apply-local-patches.sh`
- The `_ensure_active_branch()` function in `forks/hermes-webui/server.py`
- Fox's `local-patches` branch in `fox-in-the-box-ai/hermes-webui` (or repurpose as `fitb-overlay-archive` tag for historical reference).

**Validation gates.**
- `check-overlay-basis.sh` exits 0.
- All 11 patches in `series` apply with `git apply --check` cleanly.
- Container builds. **Full smoke checklist sections A–L run end-to-end against the verification container, on both Apple Silicon and an x86_64 host.** Section A4 (architecture verification per #114 lesson) is non-skippable.
- `docker exec fitb-test cat /app/version.txt` returns the FITB_VERSION (proves no `version.txt` regression).
- `docker exec fitb-test ls /app/hermes-webui/api/` shows neither `ollama.py` nor `tailscale.py` etc. — they're in `/app/fox-overlay/...`.
- `docker exec fitb-test pip show hermes-webui` shows the pinned upstream version (e.g. `Version: 0.51.22`).
- 48-hour soak (anti-regression Rule 2) starts at tag time.

**Rollback.** This is the most consequential phase. Rollback procedure:

1. `git revert <merge-commit>` on monorepo `main` — restores .gitmodules to the fox fork URLs and the submodule pins to the previous SHAs.
2. `git submodule sync && git submodule update --init --recursive` to re-fetch the fork-side content.
3. Rebuild and redeploy `:stable` from the prior `:vX.Y.<n-1>` digest.
4. File a post-mortem issue documenting which patch failed against which upstream tag.

Critically: the prior Fox-fork branches (`master`/`main`) on `fox-in-the-box-ai/hermes-{webui,agent}` are **not deleted** until Phase 9. Until then, rollback is fully reversible.

**Effort estimate.** 1.5 engineering days (1 day implementation, 0.5 day full smoke run on real hardware).

**Suggested PR/issue split.**
- "phase 7a: re-pin forks/hermes-webui to upstream nesquena v0.51.22"
- "phase 7b: re-pin forks/hermes-agent to upstream NousResearch v0.13.0 (v2026.5.7)"
- "phase 7c: multi-stage Dockerfile + check-overlay-basis CI gate"

(These can be one merged PR if Dennis prefers atomic — the rollback story is identical either way since they all change the submodule pin.)

**Risks.**
- A patch fails `git apply --check` against the new upstream. **Mitigation:** dry-run before merging. If it fails, refresh the patch (or, if it's a 5-line edit, just inline it as a monkey-patch).
- One of the 6 webui modules in `webui_modules/` imports a now-renamed upstream symbol. **Mitigation:** the Phase 5 import-time check (`getattr(module, "_thing", None)`) fires; CI catches it. Update the overlay module to handle the new symbol.
- Upstream's pinned `pyproject.toml` requires Python >3.11 (it does — confirmed). **Mitigation:** Dockerfile already uses `python:3.11-slim`. But verify any sub-deps that bumped past 3.11.
- A user mid-upgrade hits a state-format mismatch (e.g. `settings.json` schema). **Mitigation:** the `packages/integration/scripts/` migration scripts already run on entrypoint; add a one-time migration if needed (none expected, but flag in Phase 9 cleanup).

---

### Phase 9 — Wire `nightly upstream-watch.yml`

**Goal.** A scheduled GitHub Actions workflow runs nightly. It checks for a newer upstream tag than `versions.toml` records. If found, it runs the full container build with the new tag and opens an issue if the build or smoke fails. Catches drift early, surfaces incompatibilities as CI signals, and enforces the security cadence implied by upstream's 8 P0 closures in v0.13.0 alone.

**Prerequisites.** Phase 7 merged and deployed; 48-hour soak complete.

**Concrete file operations.**

Create `.github/workflows/upstream-watch.yml`:

```yaml
name: Upstream watch (nightly)

on:
  schedule:
    - cron: "17 5 * * *"   # 05:17 UTC daily
  workflow_dispatch:

permissions:
  contents: read
  issues: write

jobs:
  check-and-build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { submodules: recursive, fetch-depth: 0 }

      - name: Read pinned versions
        id: pinned
        run: |
          echo "agent=$(grep '^hermes_agent_tag' versions.toml | cut -d'\"' -f2)" >> "$GITHUB_OUTPUT"
          echo "webui=$(grep '^hermes_webui_tag' versions.toml | cut -d'\"' -f2)" >> "$GITHUB_OUTPUT"

      - name: Resolve latest upstream tags
        id: latest
        run: |
          agent_latest=$(curl -fsSL https://api.github.com/repos/NousResearch/hermes-agent/releases/latest | jq -r .tag_name)
          webui_latest=$(curl -fsSL https://api.github.com/repos/nesquena/hermes-webui/releases/latest | jq -r .tag_name)
          echo "agent=$agent_latest" >> "$GITHUB_OUTPUT"
          echo "webui=$webui_latest" >> "$GITHUB_OUTPUT"

      - name: Test build against latest upstream
        if: ${{ steps.pinned.outputs.agent != steps.latest.outputs.agent || steps.pinned.outputs.webui != steps.latest.outputs.webui }}
        env:
          AGENT_TAG: ${{ steps.latest.outputs.agent }}
          WEBUI_TAG: ${{ steps.latest.outputs.webui }}
        run: |
          git -C forks/hermes-agent fetch --tags origin
          git -C forks/hermes-agent checkout "$AGENT_TAG"
          git -C forks/hermes-webui fetch --tags origin
          git -C forks/hermes-webui checkout "$WEBUI_TAG"
          packages/fox-overlay/scripts/check-overlay-basis.sh
          docker build -f packages/integration/Dockerfile \
            -t fitb:upstream-watch \
            --build-arg FITB_VERSION=upstream-watch .

      - name: Open issue on failure
        if: failure()
        uses: actions/github-script@v7
        with:
          script: |
            github.rest.issues.create({
              owner: context.repo.owner,
              repo: context.repo.repo,
              title: `upstream-watch: build failed for hermes-agent=${{ steps.latest.outputs.agent }}, hermes-webui=${{ steps.latest.outputs.webui }}`,
              body: `Nightly upstream-watch run ${context.runId} failed. See workflow logs for details.\n\nMost likely cause: a patch in packages/fox-overlay/patches/ no longer applies, or a monkey-patch's signature self-test fired. Refresh the affected patch before bumping versions.toml.`,
              labels: ["upstream-drift", "P2"],
            });
```

**Validation gates.**
- Manual `workflow_dispatch` trigger succeeds when current pin matches latest (no-op).
- Manual run with a fake mismatch (temporarily edit versions.toml to an older tag) builds the container and either passes or opens an issue.
- An issue actually opens when forced to fail (e.g. break a patch deliberately and rerun).

**Rollback.** Disable the workflow (`workflow_dispatch` only) or delete the file.

**Effort estimate.** 1 engineering day.

**Suggested PR/issue split.**
- "phase 9: nightly upstream-watch CI workflow"

**Risks.**
- GitHub API rate limits on `api.github.com/repos/.../releases/latest`. **Mitigation:** these endpoints don't need auth and are within the unauthenticated rate budget when run nightly.
- An accepted upstream PR retroactively conflicts with a Fox monkey-patch and the issue piles up unnoticed. **Mitigation:** the issue is labeled `upstream-drift P2`; team triage cadence catches it.

---

### Phase 10 — Cleanup and decommission

**Goal.** Remove all dead code and infrastructure that the migration obviated. The Fox forks of `hermes-webui` and `hermes-agent` are tagged for archival but no longer the source of truth. The `sync-submodules.yml` workflow is repurposed (or deleted) since it pointed at the Fox forks.

**Prerequisites.** Phase 9 merged. At least 1 successful upstream-watch cycle observed (one nightly run with a real bump signal).

**Concrete file operations.**

In monorepo:
- Delete `.github/workflows/sync-submodules.yml` (it pointed at the Fox forks; obsolete).
- Delete any leftover dead code or comments in monorepo referring to the old fork-pinning model.
- Update `CLAUDE.md` "Repository Structure" section to describe the new layout: forks point at upstream; Fox code lives in `packages/fox-overlay/`.
- Update `AGENTS.md`, `CONTRIBUTING.md`, `README.md` accordingly (one PR each or one combined doc PR).

In fork repos (`fox-in-the-box-ai/hermes-{webui,agent}`):
- Tag current `master`/`main` as `fitb-overlay-archive-2026-MM-DD` so the historical Fox-fork content remains discoverable.
- Update fork README to point to the monorepo (`packages/fox-overlay/`) for active development.
- Optionally archive the fork repos via GitHub UI (read-only). **Do not delete** — they're referenced by historical commits/tags.

In monorepo `docs/architecture/`:
- Move `upstream-separation-plan.md` → `upstream-separation-plan.archive.md` (it's now historical).
- Move `upstream-migration-execution-plan.md` → `upstream-migration-execution-plan.archive.md`.
- Add a `docs/architecture/upstream-overlay.md` describing the steady-state architecture for newcomers (1-pager, no migration prose).

**Validation gates.**
- All linked docs render and reference correct paths.
- `git submodule status` in monorepo shows clean upstream URLs.
- A fresh clone + `git submodule update --init --recursive` produces a buildable tree.

**Rollback.** Per-step. Everything in this phase is documentation + workflow config; no code change rollback needed.

**Effort estimate.** 0.5 engineering day.

**Suggested PR/issue split.**
- "phase 10a: archive sync-submodules workflow; update docs to overlay model"
- "phase 10b: tag fox forks as overlay-archive; archive fork repos read-only"

**Risks.**
- A future engineer reads `upstream-separation-plan.md` (now archive) without realizing it's historical. **Mitigation:** prominent banner at top + filename suffix.

---

## 5. Open questions Dennis must decide before Phase 1

The original 827-line plan listed 3 open questions. Refreshed for current state (v0.5.4 in tree, drift now 1,526 + 1,238 commits, 2026-05-16):

1. **Where in the roadmap does this slot? (Phase / version assignment.)**
   The roadmap has Phase 1 = v0.5.5 (`fox-guardrails` + Presidio PII). Per anti-regression Rule 1, Phase 1 of the roadmap and the migration cannot share a release. Options:
   - **(a) Migration is v0.5.5, push guardrails to v0.5.6.** Cleanest separation; 5-week migration window; guardrails resume after 48h soak post-Phase-7.
   - **(b) Migration is v0.6.0 (after guardrails ship in v0.5.5).** Defers ~6 weeks; drift adds ~3,000 commits in that window; security-cadence risk grows materially.
   - **(c) Interleave: Phase 0 (PR campaign) runs now; Phases 1–4 run in parallel with guardrail dev (different files); Phase 5+ blocks on guardrails ship.** Highest scheduling complexity; needs 2 engineers.
   **Recommendation:** (a). The drift is a security cost; guardrails are a feature cost. Rule 2 ("48-hour soak") makes interleaving risky.

2. **Phase 0 (Upstream-PR campaign) — go or skip?**
   Sending the 5 bug-fix PRs upstream takes ~1.5 days; review latency adds 1–4 weeks of nothing-to-do calendar. Each accepted PR shrinks the patch series forever. The two top candidates (`runtime_provider.py` Bedrock fix, `models.py` #1558 metadata-save) are pure bug fixes any maintainer would accept.
   **Recommendation:** GO. Run Phase 0 immediately, in parallel with Phase 1; do not block migration on it. If 0 PRs accept, Fox's patch series is unchanged. If 5 accept, Fox's permanent patch surface drops by another ~5 commits.

3. **Choice of upstream tag pin for the initial cut.**
   Two options:
   - **(a) Latest stable tags as of migration start** (`hermes-agent v2026.5.7` / `hermes-webui v0.51.22` per the 2026-05-08 audit; check at Phase 7 time for newer). Maximizes immediate value capture (Kanban, `transform_llm_output` hook, security wave).
   - **(b) Older tag known to compile against Fox's existing patches** (e.g. one tag prior to a known refactor). Lower risk; less value.
   **Recommendation:** (a). The whole point of the migration is to enable upstream tracking; pinning to a stale tag immediately defeats it. If a patch fails against latest, the patch needs refresh anyway — that's a known cost, surface it in Phase 7 not Phase 8.

---

## 6. Glossary

- **Overlay** — A separate package (`packages/fox-overlay/`) whose contents are layered on top of upstream files at build time, without modifying the upstream tree in place. Comparable to Nix overlays or rpm-ostree layered images.
- **Monkey-patch** — Replacing a function or method on a Python module at runtime, after import. Used here when a Fox change must alter mid-file upstream behavior but cannot be expressed as a clean overlay (e.g. swapping `api.streaming._handle_provider_error`).
- **Patch series** — A Debian-quilt-style ordered list of `.patch` files, with a `series` text file listing the order. Applied with `git apply` at Docker build time. Used here only for the unavoidable mid-file edits that cannot be monkey-patched (the 9 lines in webui's `server.py` and `api/routes.py`).
- **Basis** — The upstream commit/tag the overlay was authored against. `check-overlay-basis.sh` verifies that every file Fox claims to modify or remove still exists in the pinned upstream — guards against silent feature loss when upstream renames or deletes a file.
- **Dispatcher** — The `fox_overlay.dispatch` module's `handle_get`/`handle_post` callable. The 6-line patch in `api/routes.py` calls it before falling through to the upstream `if/elif` chain. Lets Fox claim route prefixes without modifying upstream's giant route table.
- **Bootstrap** — The `fox_overlay.bootstrap.install()` entry point. Installs all monkey-patches at import time. The 3-line patch in `server.py` is just `import fox_overlay.bootstrap` — everything else fans out from there.
- **`.fox-removals`** — A one-path-per-line manifest in the overlay listing upstream files Fox does NOT want in the shipped image. Applied via `xargs rm -f` after the upstream COPY in the Dockerfile. Cleaner than a patch that deletes 7 files.
- **Anti-regression rules** — The 5 non-negotiable rules in `project_roadmap_v0_5_to_v0_9.md`: (1) one large change per release, (2) 48-hour soak after every tag, (3) growing regression suite, (4) feature flags everywhere, (5) stabilization pass before every minor bump.
- **Smoke checklist** — `qa/SMOKE_CHECKLIST.md`. Sections A–L. Must pass against the released `:stable` (or candidate `:latest` for pre-tag), not against a local rebuild. Verification container always on port 8788, never disturbing the user's port-8787 production install.
- **Verification container** — The convention from `reference_test_container.md`: `fitb-test` on port 8788 with `--cap-add=NET_ADMIN --device /dev/net/tun --sysctl net.ipv4.ip_forward=1` and a named volume. Required for Tailscale section of smoke to actually work.
