# Fox in the Box — upstream-overlay architecture (post-v0.6.0)

**Status:** authoritative live doc, kept in sync with shipped reality. Supersedes
`upstream-separation-plan.archive.md` and `upstream-migration-execution-plan.archive.md`
(both archived 2026-05-18 — kept for history).

## TL;DR

Fox in the Box wraps two upstream projects without forking them:

- [`nesquena/hermes-webui`](https://github.com/nesquena/hermes-webui)
- [`NousResearch/hermes-agent`](https://github.com/NousResearch/hermes-agent)

Pinned upstream tags live in [`packages/fox-overlay/versions.toml`](../../packages/fox-overlay/versions.toml).
Container build COPYs the pinned upstream content, then layers Fox behavior on top
via four mechanisms (in the order they apply at build/run time):

1. **Webui patch series** (`packages/fox-overlay/patches/webui/`) — `git apply`'d
   at Docker build time. Today: 8 patches (001 server.py bootstrap, 002 routes.py
   dispatcher hook, 003 server.py onboarding-redirect, 004 fox-bot-name-override,
   005 fox-avatar-override, 006 fox-empty-state-branding, 007 ui.js colon-split
   fix, 008 routes.py colon-split fix).
2. **Agent patch series** (`packages/fox-overlay/patches/agent/`) — same, for the
   agent submodule. Today: 1 patch (bootstrap shim).
3. **`.fox-removals` manifest** (`packages/fox-overlay/.fox-removals`) — file paths
   the container shouldn't ship from upstream (e.g. upstream onboarding tests Fox
   replaced).
4. **`fox_overlay` Python package** (`packages/fox-overlay/fox_overlay/`) —
   sibling package, pip-installed in the same venv. Provides:
   - `webui_modules/` — additive HTTP handlers registered with the dispatcher
     (Phase 5 modules: ollama, tailscale, local_fallback, models_download,
     hostname, onboarding, test_hooks). `test_hooks` only registers its
     `/test/*` routes when `FITB_TEST_MODE=1`; in production the module
     loads but is inert.
   - `webui_patches/` — runtime monkey-patches on upstream webui modules
     (Phase 6 patches: config, streaming)
   - `agent_plugins/` — entry-point-loaded agent monkey-patches (Phase 3:
     runtime_provider, auxiliary_client, cron_diagnostics)
   - `agent_memory_plugins/` — fox-only memory providers COPYd into upstream's
     `plugins/memory/` dir at build time (e.g. mem0_oss)

A `check-overlay-basis.sh` script ([`packages/fox-overlay/scripts/`](../../packages/fox-overlay/scripts/check-overlay-basis.sh))
verifies that every overlay artifact still applies cleanly against the current
submodule pin. It runs as a CI gate before every Docker build.

A nightly `upstream-watch.yml` workflow ([`.github/workflows/`](../../.github/workflows/upstream-watch.yml))
opens an issue whenever a newer upstream tag exists, surfacing whether the
overlay basis is still clean for the proposed bump.

## When to use which mechanism

| You want to… | Use |
|---|---|
| Add a new HTTP route Fox provides on top of upstream | `webui_modules/` — register with `fox_overlay.dispatch.register_get/post` |
| Add a content file alongside upstream (e.g. a Fox-specific `SOUL.md` persona) | `agent_overlay/<file>` + a Dockerfile `RUN cp` block at build time. New in v0.7.3 (PR #297). Mirrors the existing `agent_memory_plugins/` install pattern. |
| Modify upstream Python behavior **in-function** at a small, well-defined point | `webui_patches/` with `substitute_function` / `substitute_method` (runtime, `inspect.getsource` + textual anchor substitution) — preferred over a static patch when the change is small and may need to survive frequent upstream churn |
| **Mutate the return value of an upstream function (post-call)** | `webui_patches/` with the **wrap-and-splice pattern** (new in v0.7.4, see `_wrap_get_available_models` in `webui_patches/config.py`). Replace the module attribute with a closure that calls the original then mutates the result. Invariant to upstream internal refactors as long as signature + return-shape hold. Use when the change is "add behavior after the call," NOT "modify code inside a 1200-line function body" — anchored substitution deep inside large functions is fragile. |
| Add a few lines of code to a load-bearing upstream module where module-load ordering matters (e.g. bootstrap, dispatcher hook) | Patch series (`patches/webui/` or `patches/agent/`) — applied at Docker build time, so the imports are statically there |
| Delete an upstream file Fox doesn't ship | Add to `.fox-removals` |
| Add an agent monkey-patch (target_model fix, etc.) | `agent_plugins/.../monkey_patches/` (entry-point loaded via `fox_overlay.agent_plugins.register()`) |
| Add a memory provider | `agent_memory_plugins/<name>/{__init__.py,plugin.yaml,README.md}` — Dockerfile installer COPYs into `/app/hermes-agent/plugins/memory/` and upstream's directory-scan discovery picks it up |

## Engineer-discovered patterns (codified mid-migration)

### Option E — "fork-side keep-when-coupled"

When migration would revert a fork file to upstream content, but that fork
file has a tight import coupling to another file Fox edits (discovered in
Phase 4: `api/routes.py` imports from `api/onboarding.py` at module-load),
**do not wholesale-revert.** Instead, keep Fox's version and patch the
specific change on top. Phases 5/6/7 each delete their own fork-side
modifications progressively as overlay code takes ownership.

Recurred in Phase 8 follow-up #244: tried to add `api/onboarding.py` to
`.fox-removals`; upstream `routes.py` top-level-imports four symbols from
it; can't remove without also removing `routes.py`. Kept as dead-code-but-
shipped per Option E.

### Dispatcher `allow_bare=True` opt-in

Phase 5 module 4 (models_download) needed to claim both a bare path
(`/api/local-models` for list) AND parameterized sub-paths
(`/api/local-models/<id>/...`). The dispatcher's default prefix contract
requires a trailing `/` to prevent `/api/foo` matching `/api/foobar`.
`register_get/post(..., allow_bare=True)` lets the prefix omit the
trailing slash; the handler is contractually responsible for boundary
checks (reject `/api/local-modelsX` etc.). First users: `models_download`,
`hostname`, `onboarding` (for `/setup`).

### `substitute_method` helper (Phase 6 module 2)

Phase 3's `substitute_function` only handles top-level functions —
`inspect.getsource(SomeClass.method)` returns the method body with the
surrounding class indentation, and `compile()` rejects it at module scope.
`substitute_method` (`packages/fox-overlay/fox_overlay/webui_patches/_helpers.py`)
handles class methods: applies substitutions against the indented source,
then runs `textwrap.dedent` AFTER anchor matching is complete so `compile()`
accepts the source at module scope. Also handles classmethod-descriptor
sentinel resolution via `__func__`. Models patch was the first user (now
removed because upstream caught up); pattern remains for future class-method
patches.

### Wrapping rather than substituting (shipped in v0.7.4)

Phase 8 follow-up #241 discovered: when upstream extensively refactors the
target function's surrounding code (not just renames a kwarg), textual
substitution becomes infeasible. **Resolved in v0.7.4 with the
wrap-and-splice pattern** — the first such use is
`_wrap_get_available_models` in `fox_overlay/webui_patches/config.py`,
which adds a Fox OLLAMA group to the picker output by wrapping upstream's
`get_available_models()` rather than splicing inside its ~1200-line body.
Wrap depends only on the function's signature + return-shape, both
self-checked at apply-time. **Use this pattern whenever the change is a
post-call mutation of the return value; reserve `substitute_function` for
genuine in-function modifications where the anchor is short and stable.**

### Multi-substitution on a single function (shipped in v0.7.6)

`substitute_function` accepts a list of `(old, new)` tuples and applies
them sequentially — each anchor must still appear exactly once in the
upstream source. v0.7.6 ships 3 substitutions on
`_run_agent_streaming` (FITB#9 plumbing + #303 silent-failover success
path + #303 silent-failover exception path). Each substitution has its
own anchor; the three are independent splice points within the same
upstream function. This is the right shape when one function needs
multiple, structurally-distinct mid-body insertions.

### Fail-loud anchor drift (shipped in v0.7.5)

`fox_overlay.bootstrap.install()` used to demote `AssertionError` from
`webui_patches.apply_all()` to a WARNING and continue — meaning anchor
drift would ship silently-broken Fox to users. v0.7.5 changed this:
`AssertionError` re-raises (aborts container boot, CI catches), other
exceptions log via `_log.exception` with full traceback (still degrade
one patch but keep webui usable). The fail-loud path is the entire
reason `substitute_function`'s anchor self-check exists in the first
place; pre-v0.7.5 that signal was being swallowed.

### Option B diff guard (shipped in v0.7.5)

`.github/workflows/option-b-diff-guard.yml` fails any PR titled
`bump(upstream): …` whose diff touches anything outside the upstream-pin
allow-list (`forks/hermes-*` submodule pointers +
`packages/fox-overlay/versions.toml`). Closes the last hole in the
Option B auto-bump trust model — a typo'd or copy-pasted
`bump(upstream):` subject on a Fox-code PR can no longer silently ship
arbitrary code to `:stable`. See `docs/RELEASE_WORKFLOW.md` Flow B for
the user-facing process.

## Phase summary (shipped)

| Phase | What it shipped |
|-------|-----------------|
| 0 | Upstream PR campaign (some merged upstream — e.g. #1558 fixes) |
| 1 | `packages/fox-overlay/` scaffold + MANIFEST + scripts stubs |
| 2 | Static assets via overlay extensions dir (`HERMES_WEBUI_EXTENSION_*`) |
| 3 | Agent monkey-patches (entry-point loaded): runtime_provider, auxiliary_client, cron_diagnostics. Bootstrap shim added to fork's gateway/run.py. mem0_oss kept as fork plugin pending Phase 8 relocation. |
| 4 | Dispatcher mechanism + 2-patch webui series (server.py + routes.py hooks). Option E discovered. |
| 5 | 5 additive webui modules: ollama, tailscale, local_fallback, models_download, hostname. session_recovery deferred (route-less). |
| 6 | 4 webui mid-file monkey-patches initially: providers, models, config, streaming. **Updates over time:** providers retired v0.6.2 (#269) — upstream's per-turn env reload covers Fox's original concern. models retired Phase 8 #239 — upstream v0.51.84 ships Fox's #1558 P0 guard natively. Today (v0.7.6): config + streaming only. updates.py removed (Fox edits superseded by upstream / dropped). |
| 7 | Onboarding wholesale-replace via overlay (incl. setup files moved). `.fox-removals` Dockerfile consumer wired. |
| 8 | Re-point submodules at virgin upstream (webui v0.51.84 + agent v2026.5.16). Refresh all anchors. mem0_oss relocated. versions.toml + check-overlay-basis.sh shipped. Bootstrap shim extracted from fork to managed patch. |
| 9 | Nightly upstream-watch CI workflow opens issues on drift. |
| 10 | (in flight) Cleanup + archive + this doc |

### Mid-flight deviations from the original plan

- Phase 3 deferred mem0_oss relocation → done in Phase 8 #243.
- Phase 4 swapped Option A (wholesale-revert routes.py) for Option E
  (keep + patch).
- Phase 5 added dispatcher `allow_bare=True` opt-in for modules with
  bare-path + sub-path claims.
- Phase 5 module 6 (session_recovery) deferred (route-less + dead code at
  runtime); closed not-planned.
- Phase 6 added `substitute_method` helper for class-method patches.
- Phase 6 updates.py chose DELETE path over PATCH path (Fox custom
  updates dropped; upstream's native version takes over).
- Phase 8 ATOMIC discovered the Phase 3 bootstrap shim (a fork commit)
  was lost in the re-point — extracted to a managed patch in #242.
- Phase 8 ATOMIC dropped Fox's #89 (mid-stream break) + #129b (silent
  failover) features from streaming patch — upstream refactor made them
  infeasible to substitute. Deferred to v0.7.x (issues #254 + #255).

## Operational

### Versioning policy (Option B, since v0.7.0)

Fox's version number reflects **Fox-code changes only**. Upstream-pin
advances (submodule pointer + `versions.toml` updates with no Fox-code
diff) **do not bump VERSION/package.json and do not rebuild DMG/exe**.
Instead, they ship as **container-only updates**: the `:stable` Docker
tag advances to the new build; existing DMG/exe installations pick up
the new container on their next launch (Electron pulls `:stable` at
startup); no re-download required by users.

Why: nesquena/hermes-webui ships several patch versions per day. Treating
each as a full Fox release would inflate version numbers, churn signed
binaries, and waste ~25 min of CI per release with no Fox-side change to
report. Treating upstream as a base image (the way alpine bumps don't
bump app versions) is the natural fit.

How: a commit-message convention. The merge step in
`build-container.yml` auto-bumps `:stable` if-and-only-if the merged
commit subject starts with `bump(upstream):`. Fox-code commits never use
this prefix, so the original FITB#122 protection (`:stable` doesn't
follow main on Fox-code commits) is preserved.

### Bumping the upstream pin

1. Open the auto-issue from `upstream-watch.yml` (or run it manually).
2. If `check-overlay-basis.sh` reported clean, open a single PR that:
   - Updates `forks/hermes-webui` + `forks/hermes-agent` submodule
     pointers to the new tags.
   - Updates `packages/fox-overlay/versions.toml` with the new tags +
     `pinned_at` date + the bump PR's number.
   - **Title + squash-merge commit subject MUST start with
     `bump(upstream):`** — this is the Option B marker that authorizes the
     `:stable` auto-bump. Example: `bump(upstream): webui v0.51.92 →
     v0.51.95 (closes #277)`.
   - **Does NOT change** `VERSION` or `packages/electron/package.json`
     version.
   - **Does NOT add** a CHANGELOG `## [X.Y.Z]` entry. (Optional: add a
     line under an existing `### Container-only updates` section that
     accumulates between Fox releases.)
3. CI runs `check-overlay-basis.sh` as a pre-build gate.
4. On merge to `main`: container builds + smokes as usual, then the
   merge step's "Auto-bump :stable on upstream-only commits" step
   detects the `bump(upstream):` prefix and tags `:stable` to the new
   manifest-list digest.
5. No GitHub Release is created. No DMG/exe rebuild. Users pick up the
   new container on their next Electron launch.

If `check-overlay-basis.sh` reported drift, an open issue (label
`upstream-drift`) lists the failing anchor(s) — refresh in a preceding
Fox-code PR (which DOES bump VERSION + DMG/exe), then do the
`bump(upstream):` PR.

### When to do a real Fox release instead

- Fox-overlay code change (Python, JS, CSS, patches)
- Electron code change (any file under `packages/electron/`)
- Packaging / signing / install-script change
- Documentation that ships with the binary (CLAUDE.md, etc.)
- Stabilization fix that resolves a user-reported bug

In those cases: bump `VERSION` + `packages/electron/package.json`, add
a CHANGELOG `## [X.Y.Z]` entry, merge, then tag `vX.Y.Z` and push the
tag. `release.yml` fires, builds container + DMG + exe, publishes a
GitHub Release, and moves `:stable` to the released digest. Just like
before Option B — the difference is that pure upstream-pin advances
no longer follow this path.

### Tripwires (upstream-dependency monitoring)

`.github/workflows/upstream-tripwires.yml` runs daily at 06:00 UTC (43 min after `upstream-watch.yml`) and exposes 10 independent monitoring jobs. Each opens (or re-fires on) an issue labeled `tripwire-fire + tripwire/<name>` when its condition triggers. Workflow-self-failure (network, API rate limit, script bug) opens a separate `tripwire-self-health` issue.

| Job | Label | What it watches | Where to resolve |
|-----|-------|----------------|------------------|
| `upstream_commit_digest` (#207) | `tripwire/digest` | 24h commits on either upstream; flags keyword/conflict-file hits | Inspect listed commits; pre-emptive anchor refresh if any will conflict |
| `license_watch` (#208) | `tripwire/license` | LICENSE blob SHA drift | Review diff; update `.github/state/upstream-licenses.json` baseline once intentional change is accepted |
| `branch_creation_watch` (#209) | `tripwire/branch` | New upstream branch matching rewrite-regex (`react|vue|...|major`) | Inspect branch; strategic review if it's a rewrite-in-progress |
| `nousresearch_ui_watch` (#210) | `tripwire/nous-ui` | `webui/`, `frontend/`, `static/` dir appearing at root of agent repo | Pivot review per Architect 3 §8 Scenario B |
| `maintainer_absence` (#211) | `tripwire/absence` | `nesquena` silent for 5+ days on webui | Check public activity; close if explained by known context |
| `cve_feed` (#212) | `tripwire/cve`, `security` | New GitHub Security Advisory on either upstream | Determine if pinned tag affected; emergency bump if so |
| `stage_batch_gap` (#213) | `tripwire/stage-batch` | nesquena's `Stamp CHANGELOG` cadence breaks >48h with unreleased work | Check upstream CI; surface to upstream if real stall |
| `e2e_pair_test` (#214) | `tripwire/e2e-pair` | Sanity check that `build-container.yml` still does the pair-test (already shipped) | Restore missing invariant or update tripwire expectations |
| `patch_rebase_clock` (#215) | `tripwire/rebase-clock` | Overlay patch file untouched for >90 days | Refresh against current pin OR document why anchor is intentionally stable |
| `open_issue_age` (#216) | `tripwire/issue-age` | Oldest open upstream issue >90d while upstream <12mo old | Inspect; re-evaluate dependence if upstream triage degrading |

The full implementation lives in `.github/workflows/upstream-tripwires.yml` + `.github/scripts/tripwire-*.sh` (one script per tripwire — bash-based, no runtime deps beyond `gh` + `jq`). Per-tripwire dedupe is by exact issue title, so re-fires comment on the existing issue rather than stack new ones. Bootstrap baseline state for stateful tripwires (license + future ones): `.github/state/`.

### Build-time flags

- `FITB_DISABLE_WEBUI_OVERLAY=1` (build arg) — skip the webui patch
  series + `.fox-removals` removals. For bisecting overlay-induced
  regressions.
- `FITB_DISABLE_AGENT_OVERLAY=1` (build arg + runtime env) — skip the
  agent patch series + agent memory plugin install + agent bootstrap
  shim's runtime path.

## Key paths

| Path | Purpose |
|------|---------|
| `packages/fox-overlay/.fox-removals` | Files to delete from the upstream COPY |
| `packages/fox-overlay/versions.toml` | Pinned upstream tag pair |
| `packages/fox-overlay/scripts/check-overlay-basis.sh` | Pre-build basis sanity check |
| `packages/fox-overlay/patches/webui/{series,*.patch}` | webui static patches |
| `packages/fox-overlay/patches/agent/{series,*.patch}` | agent static patches |
| `packages/fox-overlay/fox_overlay/dispatch.py` | webui HTTP route dispatcher |
| `packages/fox-overlay/fox_overlay/bootstrap.py` | webui-side overlay loader |
| `packages/fox-overlay/fox_overlay/webui_modules/` | additive webui Python modules |
| `packages/fox-overlay/fox_overlay/webui_patches/` | runtime monkey-patches on upstream webui |
| `packages/fox-overlay/fox_overlay/agent_plugins/` | agent entry-point + monkey-patches |
| `packages/fox-overlay/agent_memory_plugins/` | mem0_oss + future memory providers |
| `packages/fox-overlay/webui_static/` | Fox static assets served via `HERMES_WEBUI_EXTENSION_DIR` |
| `.github/workflows/upstream-watch.yml` | Nightly drift detection |
| `.github/workflows/build-container.yml` | Container build (runs check-overlay-basis.sh as gate) |
