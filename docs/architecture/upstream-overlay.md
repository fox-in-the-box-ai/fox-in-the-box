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
   at Docker build time. Today: 2 patches, 9 lines total.
2. **Agent patch series** (`packages/fox-overlay/patches/agent/`) — same, for the
   agent submodule. Today: 1 patch (bootstrap shim).
3. **`.fox-removals` manifest** (`packages/fox-overlay/.fox-removals`) — file paths
   the container shouldn't ship from upstream (e.g. upstream onboarding tests Fox
   replaced).
4. **`fox_overlay` Python package** (`packages/fox-overlay/fox_overlay/`) —
   sibling package, pip-installed in the same venv. Provides:
   - `webui_modules/` — additive HTTP handlers registered with the dispatcher
     (Phase 5 modules: ollama, tailscale, local_fallback, models_download,
     hostname, onboarding)
   - `webui_patches/` — runtime monkey-patches on upstream webui modules
     (Phase 6 patches: config, providers, streaming)
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
| Modify upstream Python behavior at a small, well-defined point | `webui_patches/` (runtime, `inspect.getsource` + textual substitution via `substitute_function` / `substitute_method`) — preferred over a static patch when the change is small and may need to survive frequent upstream churn |
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

### Wrapping rather than substituting (suggested for v0.7.x)

Phase 8 follow-up #241 discovered: when upstream extensively refactors the
target function's surrounding code (not just renames a kwarg), textual
substitution becomes infeasible. The proposed approach for future
re-implementation of #89 + #129b features (v0.7.x): subscribe to
`put('apperror', ...)` events as a downstream consumer rather than
substituting in-place. Avoids anchor fragility entirely.

## Phase summary (shipped)

| Phase | What it shipped |
|-------|-----------------|
| 0 | Upstream PR campaign (some merged upstream — e.g. #1558 fixes) |
| 1 | `packages/fox-overlay/` scaffold + MANIFEST + scripts stubs |
| 2 | Static assets via overlay extensions dir (`HERMES_WEBUI_EXTENSION_*`) |
| 3 | Agent monkey-patches (entry-point loaded): runtime_provider, auxiliary_client, cron_diagnostics. Bootstrap shim added to fork's gateway/run.py. mem0_oss kept as fork plugin pending Phase 8 relocation. |
| 4 | Dispatcher mechanism + 2-patch webui series (server.py + routes.py hooks). Option E discovered. |
| 5 | 5 additive webui modules: ollama, tailscale, local_fallback, models_download, hostname. session_recovery deferred (route-less). |
| 6 | 4 webui mid-file monkey-patches: providers, models, config, streaming. updates.py removed (Fox edits superseded by upstream / dropped). |
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

### Bumping the upstream pin

1. Open the auto-issue from `upstream-watch.yml` (or run it manually).
2. If `check-overlay-basis.sh` reported clean, open a single PR that:
   - Updates `forks/hermes-webui` + `forks/hermes-agent` submodule
     pointers to the new tags.
   - Updates `packages/fox-overlay/versions.toml` with the new tags +
     `pinned_at` date + the bump PR's number.
3. CI runs `check-overlay-basis.sh` as a pre-build gate.
4. Container build + smoke as usual.

If `check-overlay-basis.sh` reported drift, an open issue (label
`upstream-drift`) lists the failing anchor(s) — refresh in a preceding
PR, then bump.

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
