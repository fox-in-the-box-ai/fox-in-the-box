# Upstream Separation Architecture — Research & Plan

**Status:** RESEARCH COMPLETE / AWAITING DECISION
**Date:** 2026-05-08
**Author:** Architecture research dispatched by Dennis Vorobyov (@roadhero)
**Scope:** Separate Fox in the Box customizations from upstream `NousResearch/hermes-agent` and `nesquena/hermes-webui`

---

## Why this document exists

We forked `NousResearch/hermes-agent` and `nesquena/hermes-webui` and have been editing fork files directly for months. We're now ~612 commits behind on `hermes-agent` and ~294 commits behind on `hermes-webui`. Every upstream pull would conflict on dozens of files. Each upstream release adds real value (Kanban, security fixes, new plugin hooks) we can't easily absorb. This blocks Fox from benefiting from upstream improvements, and the gap widens by ~70 commits per day.

This document captures four parallel deep-research lanes plus a synthesis that recommends a path forward. **No code has been changed. Implementation requires explicit approval.**

---

## TABLE OF CONTENTS

1. [Synthesis & Recommended Approach](#1-synthesis--recommended-approach)
2. [Agent 1: Git-Level Separation Research](#2-agent-1--git-level-fork-separation-architecture)
3. [Agent 2: Plugin / Runtime Overlay Research](#3-agent-2--plugin--runtime-overlay-architecture)
4. [Agent 3: Build-Time Assembly Research](#4-agent-3--build-time-assembly-architecture)
5. [Agent 4: Upstream State as of 2026-05-08](#5-agent-4--upstream-state-report-2026-05-08)
6. [Decision Points Still Open](#6-decision-points-still-open)

---

# 1. Synthesis & Recommended Approach

## TL;DR

**Hybrid: submodule-pinned-to-upstream-tag + sibling overlay tree + curated patch series + runtime plugin adoption.** Each lane handles a different class of Fox change; together they reduce Fox's upstream patch surface from "every modified upstream file conflicts forever" to **2 files / ~9 lines in `hermes-webui`** and **0 files in `hermes-agent`**.

This is **not optional**. Upstream is shipping ~73 commits/day across both repos, with weekly minor tags and 8 P0 security closures in v0.13.0 alone (one was CVSS 8.1). Fox's current "edit forks directly" model means we're already 612 + 294 commits behind, and the gap widens by ~70 commits/day.

## Why hybrid (not any single lane alone)

| Change class | Right lane | Why |
|---|---|---|
| Pure-additive Python files (`api/ollama.py`, `api/tailscale.py`, `api/local_fallback.py`, etc. — 2,931 lines, 6 files) | **Build-time overlay** (Agent 3) | Drop into `packages/fox-overlay/webui-modules/`; zero conflict ever. |
| Pure-additive static files (CSS, JS, fonts, fox avatar, setup wizard — 4,900 net lines) | **Build-time overlay** + existing `HERMES_WEBUI_EXTENSION_DIR` (Agent 2) | Already supported by upstream's `api/extensions.py`. Set 3 env vars; done. |
| Mid-file Python edits Fox owns (`server.py`, `api/routes.py`, `api/streaming.py`, `api/models.py`, `api/config.py`, `api/onboarding.py`) | **Curated patch series** (Agent 1) + **runtime monkey-patches** (Agent 2) | Patches apply at Docker build; monkey-patches install at runtime via 9-line bootstrap shim. |
| All hermes-agent changes (5 modified files + mem0 plugin) | **Runtime plugin** (Agent 2) | Upstream's plugin manager already exposes 17 hooks incl. brand-new `transform_llm_output`. Zero patches. |
| Removed upstream files (7 deleted onboarding tests, `static/onboarding.js`) | **Build-time `.fox-removals` manifest** (Agent 3) | `xargs rm -f` step in Dockerfile after overlay copy. |
| Branch-management workflow (`scripts/apply-local-patches.sh`, `_ensure_active_branch()`) | **Retire** | Becomes obsolete once submodule pins virgin upstream. |

This isn't three competing proposals — it's one architecture with three implementation layers.

## Final patch surface (target state)

| Repo | Patches | Total lines |
|---|---|---|
| `hermes-agent` | **0 files** — everything via `pip install fox-overlay` + `hermes_agent.plugins` entry-point + 4 monkey-patches in bootstrap | 0 |
| `hermes-webui` | **2 files: `server.py` (3 lines bootstrap import) + `api/routes.py` (3 lines per dispatcher × 2)** | ~9 |

Compare to status quo: 5 modified files (agent) + 36 modified+deleted files (webui).

## Concrete proposed layout

```
packages/fox-overlay/
├── pyproject.toml                          # entry-point: hermes_agent.plugins → fox_overlay
├── fox_overlay/
│   ├── bootstrap.py                        # the 9-line import target; applies monkey-patches
│   ├── agent_plugins/{mem0_oss,fox_guardrails}/  # uses upstream plugin manifest schema (kind: ...)
│   ├── webui_modules/{ollama,tailscale,local_fallback,models_download,hostname,onboarding,session_recovery}.py
│   ├── webui_routes.py                     # dispatch table called by routes.py patch
│   └── webui_patches/{streaming,session_safety,config,providers}.py  # monkey-patches
├── webui_static/                            # mounted via HERMES_WEBUI_EXTENSION_DIR
│   ├── fox-in-the-box.css, fox-overlay.js
│   ├── setup.{html,js,css}
│   ├── fonts/, icons/, images/
│   └── ...
├── patches/
│   ├── webui/series                        # Debian-style quilt
│   │   ├── 001-server-py-bootstrap.patch    (3 lines)
│   │   └── 002-routes-py-dispatch-hook.patch (6 lines)
│   └── agent/series                        # empty — entry-points cover everything
├── MANIFEST.toml                           # classifies every overlay file
├── .fox-removals                           # files to rm from upstream tree at build
└── scripts/check-overlay-basis.sh          # CI gate: detect upstream rename/delete
```

`forks/hermes-{webui,agent}` submodules **re-pointed at upstream** (`nesquena/hermes-webui` v0.51.22, `NousResearch/hermes-agent` v0.13.0), pinned to a tag in `versions.toml`.

Dockerfile sketch:
```dockerfile
COPY forks/hermes-webui /app/hermes-webui          # virgin upstream
COPY packages/fox-overlay/patches/webui /tmp/p
RUN cd /app/hermes-webui && for p in $(ls /tmp/p/*.patch | sort); do git apply --check "$p" && git apply "$p"; done
COPY packages/fox-overlay /app/fox-overlay         # the overlay package
RUN cd /app/hermes-webui && xargs -r -a /app/fox-overlay/.fox-removals rm -f --
RUN pip install -e /app/hermes-webui /app/fox-overlay
ENV HERMES_WEBUI_EXTENSION_DIR=/app/fox-overlay/webui_static \
    HERMES_WEBUI_EXTENSION_SCRIPT_URLS=/extensions/fox-overlay.js \
    HERMES_WEBUI_EXTENSION_STYLESHEET_URLS=/extensions/fox-in-the-box.css
```

## Things to retire / drop during migration

The upstream-state report flagged Fox features that already shipped upstream — these are **patches we delete entirely** during the rebase:

- **#109 Custom Ollama URL** — partially obsolete. Upstream landed:
  - `e38ea3807` `fix(credential_pool): resolve key mix-up when custom providers share base_url`
  - `7338e5d9b` Ollama credential switch fix (#21703)
  - `3ac89c2` Stage-306 named custom-provider routing (webui PR #1818)
  - `:free`/`:beta`/`:thinking` suffix mis-resolution fix (PR #1783)

  Drop the redundant parts of Fox's #109 implementation; keep only the UI tile (which is a clean overlay anyway).

- **`mem0_oss` plugin manifest** — upstream now enforces `kind: standalone|backend|exclusive|platform|model-provider` in `plugin.yaml`. Fox's plugin omits this field. Update before next rebase.

- **`scripts/apply-local-patches.sh` + `_ensure_active_branch()`** in webui's `server.py` — both become dead code in the new model. Delete in the migration.

- **Fox's `local-patches` branch** in `fox-in-the-box-ai/hermes-webui` — stale (34 commits behind master). Not revivable; delete or repurpose as patch archive.

## New upstream hooks Fox should adopt

The upstream-state report identified concrete hook adoption opportunities — these collapse Fox monkey-patches into clean plugin registrations:

- **`transform_llm_output`** (NEW in v0.13.0, PR #21235) — exactly the hook Fox guardrails Phase 1 (#4 + #5 Presidio PII) needs. Use this instead of any monkey-patch on streaming output.
- **`pre_gateway_dispatch`** — for Fox admission control / message rewriting.
- **`on_session_start` / `on_session_finalize`** — the right hooks for `mem0_oss` to register against.
- **`pre_approval_request` / `post_approval_response`** — for the planned Llama Guard 3 work (Phase 4 / #6).
- **`plugins/model-providers/` directory + `ProviderProfile` ABC** — the architecturally-clean way to ship Fox's local-fallback once Phase 0 stabilization absorbs it.

## Migration plan (incremental, reversible at every step)

| Phase | What | Days | Rollback |
|---|---|---|---|
| **1.** Scaffold `packages/fox-overlay/` skeleton + `MANIFEST.toml` | Empty package, current Dockerfile untouched | 1 | revert PR |
| **2.** Move static files to overlay; set `HERMES_WEBUI_EXTENSION_DIR` | byte-identical runtime; smoke confirms | 1 | revert PR |
| **3.** Migrate hermes-agent plugin + 4 monkey-patches; restore upstream `.py` files | `hermes plugins list` shows fox; smoke | 1 | revert PR |
| **4.** Land 9-line webui patches (`server.py`, `api/routes.py`); harmless when overlay absent | bootstrap shim becomes loadable | 0.5 | revert PR |
| **5.** Migrate additive webui Python modules (ollama, tailscale, local-fallback, etc.) into overlay | smoke each affected endpoint | 2 | per-module revert |
| **6.** Migrate modified-upstream patches (streaming, models, config, providers) as monkey-patches; restore upstream files | feature-by-feature smoke | 3 | per-patch revert |
| **7.** Migrate `api/onboarding.py` wholesale-replacement; deal with deleted `static/onboarding.js` fallout | setup flow smoke | 1 | revert PR |
| **8.** Re-point submodules at upstream tags; switch Dockerfile to multi-stage; delete `_ensure_active_branch` + `apply-local-patches.sh` | Full smoke A–L | 1.5 | tag rollback + submodule revert |
| **9.** Wire `nightly upstream-watch.yml` (auto-bump to latest tag, build, open issue on failure) | Catches drift early | 1 | disable workflow |

**Total: ~12 days focused work, ~3 weeks calendar.** Each phase produces a working build.

## Risk register

| Risk | Mitigation |
|---|---|
| **Upstream renames a function we monkey-patch** | `bootstrap.install()` self-test asserts every patched symbol exists (`inspect.signature` check); fail fast in CI. |
| **Upstream adds a route at the same path as a Fox route** | Startup audit walks upstream `handle_get` for path literals; warn on overlap. |
| **Order-of-import: bootstrap runs after `Session.save` is already cached** | Bootstrap patch is the **first** import in `server.py` before any `from api.* import`. |
| **`api/routes.py` upstream growth (+3,153 lines, 80 commits/30 days) makes patches drift** | Patch is only 6 lines (dispatcher hook). Does not touch any upstream route handler. |
| **`api/onboarding.py` upstream restructured (Codex OAuth onboarding shipped)** | Treat as full-replace, not patch. Fox dispatcher fires first; upstream becomes dead code. |
| **Force-pushes to patch branches break in-flight contributor work** | Tag pre-rebase tip (`pre-pull-YYYY-MM-DD`); 24h announcement window for rebases. |
| **Debug-ability — "where did this come from?"** | Every monkey-patch logs `[fox-overlay] patched api.streaming._handle_provider_error` at startup; `MANIFEST.toml` is canonical inventory. |
| **Silent feature loss on upstream rename of overlaid file** | `check-overlay-basis.sh` runs as first build step; CI fails if a `full-replace` overlay file no longer exists upstream. |
| **Security tag drops weekly, we're not tracking** | Nightly `upstream-watch.yml` opens an issue when a new tag fails to build; security cadence becomes a CI signal. |

## Cost / ongoing maintenance

| Scenario | Status quo | After migration |
|---|---|---|
| Typical weekly upstream pull | 6–10 hours (unworkable; we don't do it) | **15–60 min** |
| Big-feature pull (e.g. Kanban v1) | Days | **1–2 hours** |
| Worst case (upstream restructures patched dir) | Days | **Half a day**, detected by `git apply` failure not silent regression |
| Cost of delaying further | Linear-in-commits, unbounded | Bounded by patch series size (~10 files, self-amortizing) |

Migration cost: **~12 engineering days, recoupable in ~3 upstream pulls.**

## Strategic call-out: Fox features to upstream first

Several Fox commits are bug fixes upstream would likely accept. Sending them as PRs to NousResearch / nesquena before the migration **shrinks our patch series for free**:

- `hermes_cli/runtime_provider.py` — one-line `target_model` fix (pure bug, no Fox semantics).
- `agent/auxiliary_client.py` — `provider=auto` resolution + `auxiliary.default` fallback (general utility).
- `cron/{jobs,scheduler}.py` + `tools/cronjob_tools.py` — failure diagnostics (operability improvement).
- `api/models.py` (#1558) — `Session.save` metadata-only guard (P0 data-loss fix; **definitely** wanted upstream).
- `api/providers.py` — gateway hot-reload after key change.

Each one upstream accepts = one less commit in our patch series forever.

---

# 2. Agent 1 — Git-Level Fork Separation Architecture

## Executive summary

Recommended approach: **patch-series-on-top-of-upstream**, implemented as a long-lived `fitb` branch on each fork that we keep cleanly rebased onto `upstream/main` (agent) and `upstream/master` (webui). Submodule pointers in the monorepo move from `master`/`main` to `fitb`. The Dockerfile and CI keep working unchanged because they `COPY forks/hermes-*` — the branch name is opaque to the build.

Why this and not subtree/submodule-of-upstream: the audit shows the actual patch surface is small enough to manage as a series. **hermes-agent has only 5 MODIFIED files / 0 DELETED**, and **hermes-webui has 29 MODIFIED / 7 DELETED**. Most of our work (22 of webui's 58 changed files, 4 of agent's 9) is already in NEW Fox-only files that conflict with nothing. A patch series turns "every pull is a merge nightmare" into "every pull is a 36-commit rebase, of which only ~12 commits touch upstream lines and might need touch-ups." Subtree adds a layer of indirection without solving the conflict on `static/index.html` or `api/routes.py`. A submodule-of-upstream + overlay copy-on-build would solve conflicts but bans us from ever touching upstream files at all, which the audit shows is unrealistic — onboarding, streaming, routes, server.py and config.py are co-modified by Fox features and upstream evolution.

The codebase already has the bones of this approach: `scripts/apply-local-patches.sh` does `git rebase --onto origin/$DEFAULT_BRANCH origin/$DEFAULT_BRANCH local-patches`, and `server.py` has a `_ensure_active_branch()` startup hook that switches to `local-patches` before booting. The infrastructure exists; it's been bypassed by direct commits to `master`. Migration is largely "stop doing that, formalize what was already designed."

## File-level diff audit

Audit method: `git merge-base <fork-pin> upstream/<branch>`, then `git diff --name-status` and `git diff --numstat` from base to the submodule-pinned SHA. Pinned SHAs from `git submodule status` in `/Users/macpro/Desktop/Fox-In-the-Box/project`:

- `forks/hermes-agent` → `44a6808f` (on `main`, merge-base `e5dad4ac` — only 6 commits ahead of upstream)
- `forks/hermes-webui` → `62c0854` (on `master`, merge-base `9e31a2ac` — 56 linear commits ahead of upstream, **no merge commits**)

**Note on actual Fox patch surface for webui:** the heavy "Fox-only" branches (e.g. `feat/wizard-option-b-flow`, `local-patches`, the fix/* and feat/* branches listed earlier) are not what's deployed. The deployed pin is `master`, and `master`'s 56 linear commits include all the Fox features. So the audit numbers below ARE the live patch surface.

### hermes-agent (pin `44a6808f` vs `upstream/main`)

| File | Class | LOC delta (+/−) | Intent |
|---|---|---|---|
| `.github/workflows/notify-monorepo.yml` | NEW | +18 / 0 | repository_dispatch to monorepo on push |
| `plugins/memory/mem0_oss/__init__.py` | NEW | +1011 / 0 | mem0_oss memory provider plugin (drop-in dir, zero conflict) |
| `plugins/memory/mem0_oss/README.md` | NEW | +201 / 0 | docs for plugin |
| `plugins/memory/mem0_oss/plugin.yaml` | NEW | +6 / 0 | plugin manifest |
| `agent/auxiliary_client.py` | MODIFIED | +20 / −2 | `_resolve_task_provider_model` provider=auto fallback + auxiliary.default config fallback |
| `cron/jobs.py` | MODIFIED | +11 / 0 | cron failure diagnostics fields |
| `cron/scheduler.py` | MODIFIED | +58 / −6 | rolling failure history on scheduler |
| `tools/cronjob_tools.py` | MODIFIED | +8 / 0 | expose new diagnostics fields to tool API |
| `hermes_cli/runtime_provider.py` | MODIFIED | +1 / −1 | use `target_model` for Bedrock api_mode routing |

**Roll-up:** NEW=4, MODIFIED=5, DELETED=0. Minimum patch surface = **5 files**. Three of the MODIFIED files (`cron/*`) form one logical change set ("cron failure diagnostics") that touches related upstream code and lands as one commit.

### hermes-webui (pin `62c0854` vs `upstream/master`)

| File | Class | LOC delta (+/−) | Intent |
|---|---|---|---|
| `api/hostname.py` | NEW | +279 / 0 | post-wizard device-naming endpoint (#68) |
| `api/local_fallback.py` | NEW | +616 / 0 | Local AI fallback orchestration (issue #9) |
| `api/models_download.py` | NEW | +620 / 0 | Server-side GGUF download manager (#10) |
| `api/ollama.py` | NEW | +508 / 0 | Pull/delete models from WebUI (#67) + custom URL (#109) |
| `api/session_recovery.py` | NEW | +131 / 0 | Recover sessions on startup |
| `api/tailscale.py` | NEW | +877 / 0 | Tailscale phase-1+2 endpoints (#96) |
| `scripts/apply-local-patches.sh` | NEW | +63 / 0 | local-patches rebase tool (already a patch-series scaffold) |
| `static/setup.css` `setup.html` `setup.js` | NEW | +939 / 0 | Onboarding wizard UI (Fox-specific) |
| `static/fox-in-the-box.{css,js}` | NEW | +1011 / 0 | Fox visual shell + variable fonts |
| `static/onboarding-preview.js` | NEW | +616 / 0 | Replacement preview for upstream onboarding |
| `static/fallback-polish.js` | NEW | +527 / 0 | Failover modal UI (FITB#128/129c+d) |
| `static/hostname-prompt.js` | NEW | +145 / 0 | Hostname prompt UI |
| `static/fonts/*`, `static/fox_avatar_cropped.jpg`, `apple-touch-icon.png`, favicons (5) | NEW/MODIFIED (binary) | n/a | Fox branding assets |
| `tests/test_local_patches_update_flow.py` | NEW | +77 / 0 | Test for #1 |
| `tests/test_metadata_save_wipe_1558.py` | NEW | +217 / 0 | P0 #1558 regression test |
| `tests/test_stale_stream_cleanup.py` | NEW | +149 / 0 | Stale-stream cleanup test |
| `.github/workflows/notify-monorepo.yml` | NEW | +18 / 0 | repository_dispatch trigger |
| `api/routes.py` | **MODIFIED** | **+1510 / −98** | **Hottest file.** Registers new endpoints + messaging session helpers. Conflicts every pull. |
| `api/onboarding.py` | **MODIFIED** | +227 / −916 | Replaced upstream wizard with Fox 3-step flow; net DELETION of 689 lines |
| `api/streaming.py` | MODIFIED | +207 / −28 | Silent failover to local model on remote error (#129b) |
| `api/config.py` | MODIFIED | +118 / −6 | Tailscale + fallback + Ollama URL config keys |
| `api/models.py` | MODIFIED | +58 / −1 | P0 #1558 metadata-save fix + project_id propagation |
| `api/providers.py` | MODIFIED | +29 / 0 | Hot-reload gateway after key change |
| `api/updates.py` | MODIFIED | +163 / −42 | Track fitb-ai fork remote; auto-reapply local patches |
| `server.py` | MODIFIED | +95 / 0 | `_ensure_active_branch()` startup git checkout + onboarding redirect import |
| `.env.example`, `.env.docker.example` | MODIFIED | +7 / 0 | Document Fox env vars |
| `ARCHITECTURE.md` | MODIFIED | +1 / −2 | Note Fox fork |
| `static/index.html` | MODIFIED | +174 / −31 | New side panels for Tailscale/fallback/models, Fox shell |
| `static/panels.js` | **MODIFIED** | **+1181 / −7** | All side-panel JS for new features |
| `static/messages.js` | MODIFIED | +142 / −1 | provider_switched badge + download-on-demand modal |
| `static/style.css` | MODIFIED | +86 / −27 | Fox theme overrides |
| `static/i18n.js` | MODIFIED | +40 / −36 | Fox translation keys |
| `static/boot.js` | MODIFIED | +13 / −1 | Hardcoded agent name + WIP onboarding hooks |
| `static/sw.js` | MODIFIED | +22 / −1 | Disable shell cache by default; avatar rename |
| `static/sessions.js`, `static/ui.js` | MODIFIED (trivial) | +4 / −2 | Wiring |
| `static/favicon-512.svg`, `favicon.svg` | MODIFIED | +19 / −37 | Fox branding |
| `tests/test_pwa_manifest_sw.py`, `tests/test_service_worker_api_cache.py` | MODIFIED | +10 / −1 | Updated assertions |
| `static/onboarding.js` | **DELETED** | 0 / −635 | Upstream onboarding script removed |
| `tests/test_issue1499_keyless_onboarding.py` | DELETED | 0 / −381 | Upstream onboarding test |
| `tests/test_issue1499_onboarding_probe.py` | DELETED | 0 / −409 | Upstream onboarding test |
| `tests/test_onboarding_existing_config.py` | DELETED | 0 / −426 | Upstream onboarding test |
| `tests/test_onboarding_mvp.py` | DELETED | 0 / −244 | Upstream onboarding test |
| `tests/test_onboarding_network.py` | DELETED | 0 / −184 | Upstream onboarding test |
| `tests/test_onboarding_static.py` | DELETED | 0 / −58 | Upstream onboarding test |

**Roll-up:** NEW=22, MODIFIED=29, DELETED=7. Minimum patch surface = **36 files**. Of those 36, 6 are the "always conflict" set: `api/routes.py`, `api/onboarding.py`, `api/streaming.py`, `api/config.py`, `static/index.html`, `static/panels.js`. The 7 DELETED files are guaranteed conflicts every pull because upstream keeps touching them.

## Industry precedents

**LineageOS / AOSP** — monthly upstream merge cadence using their `aosp-merger` script. Tracks current vs. previous AOSP tag in `vendor/lineage/vars/common`; runs a coordinated merge across hundreds of repo-manifest projects. Crucially, *they merge, they don't rebase* — because the patch volume is too large to keep linear. Cost: a maintenance team, monthly merge windows. Outcome: tracks AOSP within ~30 days, indefinitely. ([source](https://github.com/LineageOS/android))

**Chromium / ChromeOS** — uses `UPSTREAM`/`FROMGIT`/`FROMLIST` commit-message tags so every downstream patch advertises its provenance. Strict "upstream first" policy. ([source](https://www.chromium.org/chromium-os/chromiumos-design-docs/upstream-first/), [LWN coverage](https://lwn.net/Articles/798147/))

**Bazzite / Bluefin / Universal Blue** — image-overlay model. They don't fork Fedora source. They take Fedora's OCI base image and layer rpm-ostree changes via `Containerfile`s. **Zero source-level merge cost** — they only ship overlay artifacts. ([source](https://docs.bazzite.gg/Installing_and_Managing_Software/rpm-ostree/))

**Debian / Ubuntu (quilt patch series)** — every Debian source package using the "3.0 (quilt)" format keeps downstream changes as numbered patches in `debian/patches/` with a `series` file. `gbp pq` switches to a patch-queue git branch, `git rebase` against the new upstream, regenerates the series. ([Debian wiki: UsingQuilt](https://wiki.debian.org/UsingQuilt)) **This is the closest analogue to Fox's situation.**

**Grafana (originally Kibana)** — Torkel Ödegaard forked Kibana 3 in 2013 to add Graphite/time-series support after upstream rejected the patches. They diverged immediately and **never tried to keep tracking** upstream Kibana — full hard fork. Cost: zero merge cost forever, but also zero free upstream features after the cut point. **This is the path Fox is implicitly drifting toward and should explicitly avoid.**

## The three git-level approaches compared

### Patch-series-on-top-of-upstream (RECOMMENDED)

**Pros:** small operational surface (36 files for webui, 5 for agent); each Fox change keeps an authored commit you can `git log`; works with existing GitHub PR review; conflict resolution is per-commit not per-file; rejected commits drop out of the series naturally; the existing `scripts/apply-local-patches.sh` and `server.py` startup hook are already designed for this.

**Cons:** linear history requires discipline (no merging into the patch branch, no force-pushes without notice); `git rebase` rewrites SHAs every pull. Mitigation: tag the pre-rebase tip as `pre-pull-2026-05-08` before each rebase.

**Bootstrap (do once per fork):**
```
# In /Users/macpro/Desktop/Fox-In-the-Box/hermes-webui (standalone clone)
git fetch origin upstream
git checkout -b fitb origin/master            # 56 commits ahead of upstream
git log --merges $(git merge-base fitb upstream/master)..fitb   # should print nothing
git push -u origin fitb
# In monorepo: re-pin submodule
cd /Users/macpro/Desktop/Fox-In-the-Box/project
git -C forks/hermes-webui fetch origin
git -C forks/hermes-webui checkout fitb
git add forks/hermes-webui && git commit -m "chore: pin webui submodule to fitb branch"
# Update .gitmodules: branch = fitb
```

**Ongoing pull (per upstream release, ~weekly):**
```
git fetch upstream
git tag pre-pull-$(date +%Y%m%d) fitb        # rollback anchor
git rebase upstream/master                   # replay 56 commits onto new base
# resolve conflicts (typically 0–4 files)
git push --force-with-lease origin fitb
```

**Conflict surface per pull:** the 6 always-conflict files in webui plus the 7 DELETED files. Empirically: 5–15 minutes of conflict resolution per upstream release.

### `git subtree` (skip)

Does not solve any conflicts on shared files (`api/routes.py` still has to be modified). Splitting our changes into "overlay" vs "patch" duplicates classification work. **Verdict:** subtree is great when the patch surface is 0 modified files. We have 36. Skip.

### Submodule pointing at upstream + Fox overlay directory (analyzed in Agent 3's lane)

Shifts the conflict from `git pull` time to `git apply` time — same 36-file conflict surface, same expertise required, just in a different file format (.patch vs git rebase).

## Recommended migration plan (git-level only)

The existing `local-patches` branch on webui is stale. We should not revive it; we should formalize `master` itself as the patch series, rename it `fitb`, and fix the workflow so it stays clean.

**Step 1: Audit & tag.** In `hermes-webui` standalone clone: `git tag fitb-snapshot-2026-05-08 origin/master` and push the tag. Same for `hermes-agent`.

**Step 2: Create the `fitb` branch.** `git checkout -b fitb origin/master` in each fork; `git push -u origin fitb`.

**Step 3: Repoint submodules.** Edit `.gitmodules` so `branch = fitb` for both fork submodules.

**Step 4: Branch protect both forks' `fitb` and `master`/`main`.**

**Step 5: First pull-from-upstream dry run** (1–2 hours, webui only).

**Step 6: Document the workflow.**

**Hard cases — files we MUST patch (cannot move to overlay):**
- `api/routes.py` — keep all Fox endpoint registration in a single contiguous block at the bottom of the file, marked with `# === FITB ===` fences.
- `api/onboarding.py` — explicitly mark this commit "REPLACE upstream onboarding" and use `-Xtheirs` for that one commit during rebase.
- `static/index.html`, `static/panels.js` — frontend equivalent of `routes.py`. Same fence-comment mitigation.

## Risks (Agent 1's view)

**R1: Submodule pointer mismatch breaks the Docker build.** Mitigation: Step 3 includes a CI build verification before merging the PR.

**R2: First rebase produces a silently-wrong merge.** Mitigation: Step 5 includes manual smoke tests; pin a "canary" deploy slot before promoting `fitb` rebases to the main monorepo.

**R3: Force-push to `fitb` clobbers in-flight feature branches.** Mitigation: announce rebase windows.

**R4: 7 DELETED files come back every pull.** Mitigation: a tiny `.git/hooks/post-rewrite` (or a CI check) that runs `git rm` on a hardcoded list.

**R5: A Fox commit is duplicated when nesquena merges our PR upstream.** Mitigation: when we send a PR to nesquena, mark our local commit with `Upstream-Status: Submitted <PR-URL>`.

**R6: The existing `_ensure_active_branch()` startup hook hardcodes `local-patches`.** Mitigation: change the env var default in the same commit that renames the branch.

## Effort and ongoing maintenance estimates

**Migration:** ~6–8 hours, single-engineer.

**Per-upstream-pull cost, before vs after:**
- *Before* (status quo): ~6–10 hours, unworkable.
- *After*: ~30–60 minutes for a typical weekly upstream release.

**Ongoing maintenance:** the patch series should *shrink* over time as we upstream changes.

---

# 3. Agent 2 — Plugin / Runtime Overlay Architecture

## Executive Summary

The plugin/overlay story is **highly asymmetric** between the two forks.

**hermes-agent** is in great shape. Upstream ships a real, mature plugin framework at `forks/hermes-agent/hermes_cli/plugins.py` with 14 lifecycle hooks, four discovery sources (bundled / user / project / pip entry-points), tool registration, slash- and CLI-command registration, platform adapters, image-gen providers, context engines, and skill registration. Our actual fork delta against `NousResearch/hermes-agent` upstream is tiny: **4 modified `.py` files** plus **one fully-additive `plugins/memory/mem0_oss/` directory**. **Realistic patch surface for hermes-agent: 0 files** — the four modifications can either be upstreamed as PRs (they fix real bugs) or expressed as targeted monkey-patches in a Fox bootstrap.

**hermes-webui** is the hard problem. Upstream's only built-in overlay surface is `api/extensions.py`: a directory of static files (CSS/JS/HTML/fonts) injected via two env vars (`HERMES_WEBUI_EXTENSION_DIR`, `HERMES_WEBUI_EXTENSION_SCRIPT_URLS`, `HERMES_WEBUI_EXTENSION_STYLESHEET_URLS`) into `static/index.html`. There is **no Python route registry**, no Flask-style blueprints, no entry_points hook — `api/routes.py` is a 5,400-line `if/elif` chain dispatched from `server.py`.

**Minimum unavoidable patch surface (target state):**
- hermes-agent: **0 patches** (entry-points + monkey-patches in a bootstrap module).
- hermes-webui: **2 minimal patches** — one in `server.py` to call `fox_overlay.bootstrap()` at startup, one in `api/routes.py` to call `fox_overlay.dispatch(handler, parsed)` before returning False from `handle_get`/`handle_post`.

## Plugin System Inventory

### hermes-agent plugin framework

**Loader entry point:** `forks/hermes-agent/hermes_cli/plugins.py` lines 614–747 (`PluginManager.discover_and_load`).

**Discovery sources (priority low→high; later wins on key collision):**
1. **Bundled** — `<repo>/plugins/<name>/`
2. **User** — `~/.hermes/plugins/<name>/`
3. **Project** — `./.hermes/plugins/<name>/`
4. **pip entry_points** — `hermes_agent.plugins` group via `importlib.metadata`.

**Plugin contract:** Each plugin is a directory with `plugin.yaml` (manifest) + `__init__.py` exposing `def register(ctx: PluginContext) -> None`.

**Lifecycle hooks (full set):** `pre_tool_call`, `post_tool_call`, `transform_terminal_output`, `transform_tool_result`, `pre_llm_call`, `post_llm_call`, `pre_api_request`, `post_api_request`, `on_session_start`, `on_session_end`, `on_session_finalize`, `on_session_reset`, `subagent_stop`, `pre_gateway_dispatch`, `pre_approval_request`, `post_approval_response`. **(Note: Agent 4 confirmed `transform_llm_output` was added in v0.13.0 — bringing the total to 17.)**

**`PluginContext` capabilities:**
- `register_tool(name, toolset, schema, handler, …)` — adds new model-callable tools.
- `register_hook(name, callback)` — register lifecycle hook.
- `register_cli_command(name, help, setup_fn, handler_fn)` — adds `hermes <subcommand>` shell commands.
- `register_command(name, handler, …)` — adds `/slash` commands.
- `register_platform(name, label, adapter_factory, check_fn, …)` — registers a new gateway messaging adapter.
- `register_image_gen_provider(provider)`, `register_context_engine(engine)`, `register_skill(name, path, description)`.
- `inject_message(content, role)` — push messages into an active CLI conversation.

### hermes-webui overlay system

**Static-file overlay:** `forks/hermes-webui/api/extensions.py` (246 lines, fully implemented in upstream).
- Env vars: `HERMES_WEBUI_EXTENSION_DIR`, `HERMES_WEBUI_EXTENSION_SCRIPT_URLS`, `HERMES_WEBUI_EXTENSION_STYLESHEET_URLS`.
- `serve_extension_static()` at `extensions.py:209–246` serves files from the configured dir under `/extensions/` URL prefix.
- `inject_extension_tags(html)` at `extensions.py:158–197` injects `<link>` tags before `</head>` and `<script defer>` before `</body>`.
- Wire-in points in upstream `api/routes.py`: line 1125 (HTML injection) and lines 1269–1272 (`/extensions/*` static dispatch).
- Cap: 32 URLs per env var.
- Security: same-origin only.

**Python backend overlay:** **Does not exist upstream.** `server.py`'s `do_GET`/`do_POST` calls `handle_get`/`handle_post` from `api/routes.py`, which is a single giant `if parsed.path == "/foo"` chain. There is no decorator, no Blueprint, no registration list.

## Per-Modified-File Audit (Agent 2's view)

### hermes-agent

| File | What we changed | Strategy | Feasibility |
|---|---|---|---|
| `agent/auxiliary_client.py` | provider=auto fallback + auxiliary.default | Upstreamable bug fix; fallback = monkey-patch | Easy |
| `cron/jobs.py` | failure_history rolling-5 list | Upstreamable; fallback = `post_tool_call` hook | Easy |
| `cron/scheduler.py` | diagnostics + traceback | Upstreamable; fallback = monkey-patch run_job | Easy |
| `hermes_cli/runtime_provider.py` | one-line target_model fix | Pure bug fix; fallback = monkey-patch | Easy |
| `tools/cronjob_tools.py` | surface failure fields | Upstreamable; fallback = `transform_tool_result` hook | Easy |
| `plugins/memory/mem0_oss/*` | new exclusive memory provider plugin | Already a plugin | Easy |

**hermes-agent unavoidable patches: none.**

### hermes-webui

#### Additive Python files — drop-in candidates

`api/ollama.py`, `api/tailscale.py`, `api/local_fallback.py`, `api/models_download.py`, `api/hostname.py`, `api/session_recovery.py` — all move into `packages/fox-overlay/webui_modules/`; loaded by Fox bootstrap; routes registered via Fox dispatcher. **Easy.**

#### New static files — pure overlay candidates

All move to `packages/fox-overlay/static/` and serve via `HERMES_WEBUI_EXTENSION_DIR`. Already supported by upstream. **Easy.**

#### Modified upstream Python files

| File | Strategy | Feasibility |
|---|---|---|
| `server.py` (+95) | **Minimum patch:** 1 line, `import packages.fox_overlay.bootstrap` at the top of `server.py`. | Hard (without 1-line patch); Easy with it |
| `api/routes.py` (+1608) | Wrap the dispatcher: monkey-patch `handle_get` and `handle_post` to first call `fox_overlay.dispatch_get(handler, parsed)`. **OR** ask Agent 1 to land a 2-line patch upstream. | Hard (without patch); Medium with monkey-patch; Easy with 2-line patch |
| `api/onboarding.py` (-689 net) | Move our version to `packages/fox-overlay/webui-modules/onboarding.py`. Upstream becomes dead code. | Medium |
| `api/streaming.py` | Monkey-patch the exception handler, OR expose as `pre_llm_call` / `post_api_request` hook | Medium |
| `api/models.py` | Monkey-patch `Session.save` and `Session.load_metadata_only`. | Medium |
| `api/config.py` | Monkey-patch settings defaults at import time. | Medium |
| `api/updates.py` | Tightly coupled to patch-series branch workflow (Agent 1's lane). | Hard |
| `api/providers.py` | Likely small wrap; monkey-patch | Easy |

#### Modified static files (HTML/JS/CSS)

| File | Strategy | Feasibility |
|---|---|---|
| `static/index.html` | Most rebrandable from overlay JS at DOMContentLoaded. SW disable needs care. | Medium |
| `static/panels.js` (+1188) | Overlay JS as DOM-mutation code. | Medium |
| `static/messages.js` | Add to overlay JS; subscribe to existing SSE event stream. | Easy |
| Other JS/CSS | Overlay-able as appended scripts/styles | Easy |
| `static/onboarding.js` (DELETED) | Can't delete via overlay. Solution: our setup.js loads first; upstream becomes dead code. | Medium |

**Webui unavoidable patches summary:** With the recommended **2-line patch in `server.py`** and the recommended **1-line patch at the top of `handle_get`/`handle_post`**, every other change moves out of `forks/hermes-webui/`. Total patch surface: **2 files, 9 lines**.

## Industry Precedents (Agent 2's view)

### Open WebUI — Functions + Pipelines

Closest peer product. Two extension layers:
- **Functions** (in-process, admin-only): **Pipe** (virtual model), **Filter** (inlet/outlet middleware — same hook pair Fox needs), **Action** (button on each message).
- **Pipelines** (separate process, OpenAI-compatible API).

Sources: [docs.openwebui.com/features/extensibility/plugin/](https://docs.openwebui.com/features/extensibility/plugin/), [docs.openwebui.com/features/extensibility/pipelines/](https://docs.openwebui.com/features/extensibility/pipelines/).

### Other patterns

- **Jupyter server extensions** — `jupyter_server_extensions` entry-point group.
- **MkDocs plugins** — `mkdocs.plugins` entry-points; `on_config`, `on_pre_build` hooks.
- **Flask Blueprints / Starlette routers** — the dominant Python pattern for route extension.
- **VS Code extensions** — activation events + contribution points.

## Recommended Overlay Architecture (Agent 2's proposal)

[See section 1 synthesis for the consolidated layout — Agent 2's proposal is incorporated there.]

## Migration Plan (Agent 2's view)

[See section 1 synthesis for the consolidated migration plan.]

## Risks (Agent 2's view)

**Upstream rename / signature change of a hook or function we monkey-patch.** Mitigation: a self-test in `bootstrap.install()` that asserts every hook we register is in `VALID_HOOKS`; fail fast in CI on hermes-agent updates.

**Order-of-import sensitivity.** Mitigation: install bootstrap **before any `from api.* import …`** in `server.py`.

**Performance overhead.** Negligible.

**Debug-ability — "where did this behavior come from?"** Mitigations: every monkey-patch sets a sentinel attribute and prints a startup line; ship a `hermes-webui doctor` command that lists every patched function.

**Static-file collision with hard-coded asset paths.** Accept either Docker-stage COPY (Agent 3) or `_serve_static` monkey-patch.

**Upstream adds a new route at the same path as a Fox route.** Startup audit walks upstream `handle_get` for path literals and warns on overlap.

## Effort Estimate (Agent 2's view)

| Phase | Days |
|---|---|
| 1. Skeleton package + entry-points | 1 |
| 2. Static-file overlay | 1 |
| 3. hermes-agent plugin migration | 1 |
| 4. Two-line webui patches + bootstrap shim | 0.5 |
| 5. Additive webui Python modules | 2 |
| 6. Modified-upstream patches | 3 |
| 7. Onboarding migration + dead-code cleanup | 1 |
| 8. api/updates.py + final coordination | 1.5 |
| 9. CI / monkey-patch sentinels / docs | 1 |
| **Total** | **~12 days** |

---

# 4. Agent 3 — Build-Time Assembly Architecture

## Executive Summary

The current container build (`packages/integration/Dockerfile`) bakes the Fox fork directly into the image via `COPY forks/hermes-agent /app/hermes-agent` and `COPY forks/hermes-webui /app/hermes-webui`. Because both submodules point at the Fox fork's default branch (with edits applied directly to upstream files), each upstream pull triggers the conflict storm.

**Recommended architecture: Submodule-pinned-to-upstream-tag + sibling `packages/fox-overlay/{webui,agent}` + multi-stage Docker COPY.** The Dockerfile clones the virgin upstream into `/app/hermes-webui`, then a second `COPY` lays the Fox overlay on top. Files we own outright live in the overlay and shadow upstream cleanly. The remaining ~6 mid-file patches in `hermes-webui` and ~5 in `hermes-agent` become a **patch series** maintained by Agent 1 and applied via `git apply` in a build stage between the upstream copy and the overlay copy.

The single load-bearing tradeoff: this approach pushes complexity to upstream **bumps** (re-resolve patches against new upstream tag) instead of paying it on every developer rebase. The bet is that bumps are intentional, scheduled events while rebases happen continuously. A **pre-build "overlay basis check"** detects upstream renames/deletions before they silently swallow Fox features.

## Current Dockerfile Read-Out

`packages/integration/Dockerfile` today (lines 127–139) does:

```
COPY forks/hermes-agent /app/hermes-agent
COPY forks/hermes-webui /app/hermes-webui
RUN pip install -e /app/hermes-agent && \
    (pip install -e /app/hermes-webui || pip install -r /app/hermes-webui/requirements.txt)
```

The `forks/` paths are submodules pointing at the Fox fork. CI uses `actions/checkout@v4` with `submodules: recursive`. Everything below line 139 — entrypoint, supervisord, qdrant/llama-cpp tarballs, ENV/VOLUME/EXPOSE — is independent of this change and stays as-is. The `release.yml` / signing / notarization flow is **completely insulated** from this restructure.

## The Three Build-Time Approaches

### Multi-stage Docker COPY overlay (no patches)

```dockerfile
FROM alpine/git:latest AS upstream-webui
ARG UPSTREAM_WEBUI_TAG=v0.51.22
RUN git clone --depth 1 --branch ${UPSTREAM_WEBUI_TAG} \
    https://github.com/nesquena/hermes-webui /upstream-webui \
 && rm -rf /upstream-webui/.git

FROM python:3.11-slim
COPY --from=upstream-webui /upstream-webui /app/hermes-webui
COPY packages/fox-overlay/webui/ /app/hermes-webui/
RUN pip install -r /app/hermes-webui/requirements.txt
```

**Pros.** Pure file-system semantics; auditable. Cache-friendly.

**Cons.**
1. **Mid-file edits are unsolvable.** `api/routes.py` upstream is 1,180 lines; Fox added 1,608 lines into the middle. Replacing the whole file means re-doing the merge every upstream bump.
2. **Silent feature loss on upstream rename.** No build error.
3. **No precedent for "remove upstream file."** `COPY` cannot delete.

### Runtime patching alternative

```dockerfile
COPY --from=upstream-webui /upstream-webui /app/hermes-webui
COPY packages/fox-overlay/webui/ /app/fox-overlay/
COPY packages/fox-overlay/patches/webui/*.patch /app/fox-patches/
COPY packages/integration/apply-overlay.sh /app/
ENTRYPOINT ["/app/apply-overlay.sh", "/app/entrypoint.sh"]
```

**Pros.** Same image works as upstream (with `FITB_OVERLAY=0` skip). A/B testing trivial.

**Cons.** Cold-start latency. Patch failures surface at boot not build. Disqualifying issue: Fox overlay introduces new top-level Python files that need `setup.py`/`pyproject.toml` to know about them.

### Submodule-pinned-to-upstream + sibling overlay + curated patch series (RECOMMENDED)

```dockerfile
# forks/hermes-webui submodule now points at github.com/nesquena/hermes-webui
# pinned to a tag (e.g. v0.51.22). NOT the Fox fork.
COPY forks/hermes-webui /app/hermes-webui

# Apply curated mid-file patches.
COPY packages/fox-overlay/patches/webui /tmp/patches
RUN cd /app/hermes-webui \
 && for p in $(ls /tmp/patches/*.patch 2>/dev/null | sort); do \
        echo "Applying $(basename $p)"; \
        git apply --check "$p" && git apply "$p" || \
            { echo "::error::patch $(basename $p) failed against pinned upstream"; exit 1; }; \
    done \
 && rm -rf /tmp/patches

# Drop in fully-Fox-owned files.
COPY packages/fox-overlay/webui /app/hermes-webui

# Remove upstream files Fox does NOT want shipped.
RUN xargs -r -a /app/hermes-webui/.fox-removals rm -f --

RUN pip install -e /app/hermes-webui
```

**Pros.** Submodule pointer always names a precise upstream tag. Patches are short, named, reviewable. Overlay tree is pure adds + replaces. `.fox-removals` makes deletions explicit. CI's existing submodule-checkout flow keeps working unchanged.

**Cons.** Patch maintenance is real work (~10 files). Forces discipline. No GitHub Dependabot on the pinned tag. Mitigation: a separate workflow polls upstream tags weekly and opens an issue.

## Per-Modified-File Overlay-Feasibility Audit (Agent 3)

[Tables consolidated into Agent 1's audit; Agent 3's classification per file: full-replace / layered-add / patch-required / `.fox-removals`. Aggregate count: ~10 patch files for hermes-webui + 5 for hermes-agent = **~15 small, named patches**, of which 3–4 carry the bulk of the line count.]

## Industry Precedents (Agent 3's view)

1. **Nix overlays** — pure functions taking `(self, super)` and returning a record of overrides. https://nixos.wiki/wiki/Overlays
2. **Bazzite / Bluefin / Silverblue (rpm-ostree)** — base immutable image + layered customizations. https://docs.projectbluefin.io/, https://universal-blue.org/
3. **Bitnami container images** — never patch upstream PHP files; mounted config files and entrypoint helpers compose around the unmodified payload. https://github.com/bitnami/containers
4. **Apache Tomcat WAR drop-in** — stock Tomcat container with `webapps/` volume mount. **Strategic recommendation:** every patch we land upstream for a clean extension point pays dividends forever.
5. **Kustomize** — `bases/` + `overlays/` directories, strategic-merge-patch model. https://kustomize.io/
6. **Debian source packages with quilt** — closest precedent. `debian/patches/series` file applied by `quilt`. **Borrow Debian's directory layout** — `packages/fox-overlay/patches/{webui,agent}/series` listing the patch order, individual `.patch` files alongside.

## Edge-Case Handling

**Upstream renames a file we patched.** A `git apply` patch contains the source filename in its header. `git apply` fails loudly. **Good.**

**Upstream deletes a file Fox depends on.** Two failure shapes:
- (a) We had a patch against the deleted file: `git apply` fails loudly. **Good.**
- (b) Our overlay overwrote the now-deleted file: `COPY` succeeds. **Silent.** Detection: `packages/fox-overlay/scripts/check-overlay-basis.sh` walks the overlay tree and asserts each *non-overlay-only* file exists in upstream.

**Upstream restructures the directory.** Both detections fire. Workflow: pin submodule back to last-known-good upstream tag, file an issue, ship from the working pin, schedule the bump for after triage.

**Upstream changes function signatures inside a hunk we patched.** `git apply` with default fuzz tolerates 3 lines of context drift; beyond that it fails. Run `git apply --check` first AND a sanity test (`pip install -e .` succeeds, `pytest` smoke runs) inside the build stage.

## CI Changes Required

**`.github/workflows/build-container.yml`** changes:
1. `actions/checkout@v4` `submodules: recursive` keeps working — submodules will fetch upstream content directly. **Zero edits to checkout step.**
2. Add a new step before the build: "Validate overlay basis" runs `packages/fox-overlay/scripts/check-overlay-basis.sh`.
3. Add a build-arg passthrough for `UPSTREAM_WEBUI_TAG` and `UPSTREAM_AGENT_TAG` (read from `versions.toml`).
4. The `Determine FITB_VERSION` step is unchanged.

**`.github/workflows/sync-submodules.yml`** changes: repurpose to poll upstream for new tags, open a PR bumping `versions.toml` + the submodule pointer.

**Caching.** Multi-stage `COPY --from=upstream-webui` caches at the layer boundary. **Net cache hit rate improves**.

**Image size delta.** Negligible. The `git clone --depth 1` of upstream is the same content the submodule already provides. `rm -rf .git` actually **shrinks** the image.

## Migration Plan (Agent 3's view)

[Phases consolidated into the synthesis section above.]

## Risks (Agent 3's view)

**During migration.** Phase 4 patch extraction misses a hunk. Mitigation: byte-equivalence CI gate. Submodule re-pointing breaks dev environments. Patch fails to apply against upstream HEAD that previously applied against fork master.

**Ongoing.** Patch rot on upstream bumps. Drift between overlay tree and upstream API. Overlay tree drifts from MANIFEST.

## Effort Estimate (Agent 3's view)

**Migration: 8–12 engineering days.**

**Ongoing per-upstream-bump cost:**
- Best case: **15 minutes**.
- Typical case: **1–2 hours**.
- Worst case: **half a day**.

---

# 5. Agent 4 — Upstream State Report (2026-05-08)

## Executive summary

Both upstreams are in an extreme growth-and-iteration phase that bears almost no resemblance to what Fox forked. **`NousResearch/hermes-agent`** has shipped **1,236 commits in the last 30 days alone** (737 since Fox's fork-base on 2026-04-30) and tags a minor release every Thursday — `v0.7.0` through `v0.13.0` all landed in the 35 days between 2026-04-03 and 2026-05-07. **`nesquena/hermes-webui`** has shipped **953 commits in the last 30 days** (479 since Fox's fork-base on 2026-05-03) and tags a patch release essentially daily — `v0.50.278` to `v0.51.22` in five days, including a major version bump for the Kanban v1 feature on 2026-05-05.

Headline features Fox doesn't have include durable multi-agent Kanban, the `/goal` Ralph loop, Checkpoints v2, Google Chat as the 20th platform, a `ProviderProfile` plugin ABC, seven new i18n locales, the `transform_llm_output` plugin hook, and SSE-driven Kanban dashboards.

Stability signals are strongly positive on both repos: 295 contributors on the agent's last release, daily merges from a top-5 contributor pool, no rewrite/abandonment language in commit history, 138K stars on hermes-agent and growing.

Breakage risk on rebase is severe — `api/routes.py` alone grew by 3,153 lines upstream while Fox modified ~1,412 lines of it; five new API modules (`kanban_bridge.py`, `agent_health.py`, `dashboard_probe.py`, `system_health.py`, `session_recovery.py`) appeared upstream that Fox would have to reconcile.

Both upstreams are unambiguously **worth tracking** — the velocity is too high to ignore — but Fox's current fork-and-patch model is no longer viable; a true plugin/overlay architecture is required or Fox will be a year out of date within months.

## NousResearch/hermes-agent — current state

- **Latest tag**: `v2026.5.7` = Hermes Agent **v0.13.0** "Tenacity Release", **2026-05-07** (one day ago).
- **Cadence (last 6 mo)**: ~weekly minor versions. 12 minor releases in 56 days, accelerating.
- **Top ~10 themes/features shipped since Fox's fork-base** (737 commits behind):
  1. **Durable multi-agent Kanban** — heartbeat, reclaim, zombie detection, hallucination gate, per-task `max_retries`, cross-profile shared boards (PRs #17805, #19653, #20232, #20332, #21330, #21183, #21214). Single biggest feature in v0.13.0.
  2. **`/goal` Ralph loop** — agent stays locked on a target across turns (#18262, #18275, #21287).
  3. **Pluggable platforms via `ProviderProfile` ABC** — `plugins/model-providers/` directory; third-party providers drop in without core changes (#20324). IRC and Teams already migrated.
  4. **Google Chat as the 20th messaging platform** plus generic platform-plugin hooks (#21306, #21331).
  5. **Sessions auto-resume after gateway restart** (#21192) and Checkpoints v2 with real pruning (#20709).
  6. **Curator subcommands**: `archive`, `prune`, `list-archived`, synchronous `run` (#20200, #21236, #21216).
  7. **MCP improvements** — SSE transport with OAuth forwarding, stale-pipe retries, image results as MEDIA tags, keepalive (#21227, #21323, #21289, #21328, #20209).
  8. **`no_agent` cron mode** — script-only watchdog; empty stdout silent (#19709).
  9. **Post-write delta lint** — agent lints its own `write_file` / `patch` outputs for Python/JSON/YAML/TOML syntax errors before they propagate (#20191).
  10. **Security wave — 8 P0 closures** in v0.13.0 alone: redaction ON by default, Discord role-allowlists guild-scoped (CVSS 8.1 cross-guild DM bypass), WhatsApp rejects strangers, TOCTOU windows on `auth.json` and MCP OAuth, browser SSRF cloud-metadata floor, cron prompt-injection scans skill content, `hermes debug share` redacts at upload (#21193, #21241, #21291, #21176, #21194, #21228, #21350, #19318).
  11. **`transform_llm_output` plugin hook** — new lifecycle hook for context-window reducers and content filters (#21235, commit `c3be6ec18`). **This is the key opportunity for Fox.**
  12. **i18n** — 7 locales (zh, ja, de, es, fr, uk, tr) for static gateway+CLI strings.
  13. **Six new optional skills** — Shopify, here.now, shop-app, Anthropic financial-services, kanban-video-orchestrator, searxng-search.
  14. **`X-Hermes-Session-Key` API server header** for long-term memory scoping (#20199).
- **Open issues / open PRs**: **3,211 open issues**, **5,737 open PRs**.
- **Top 5 contributors last 6 mo**: Teknium (368), Brooklyn Nicholson (59), teknium1 (53), Austin Pickett (42), brooklyn! (36).
- **Breaking changes / dependency bumps**:
  - **Python**: `requires-python = ">=3.11"` at HEAD.
  - **Pinned upper bounds added** to `openai>=2.21.0,<3`, `anthropic>=0.39.0,<1`, `pydantic>=2.12.5,<3`, `requests>=2.33.0,<3` (CVE-2026-25645), `PyJWT[crypto]>=2.12.0,<3` (CVE-2026-32597).
  - **Plugin manifest schema** added `kind: standalone|backend|exclusive|platform|model-provider`. Fox's `mem0_oss/plugin.yaml` does not declare `kind` — needs review.
  - **`gateway/hooks.py`** — new event-driven hook system at `~/.hermes/hooks/` with YAML+Python pairs (separate from `hermes_cli/plugins.py`). **Two parallel hook systems now exist.**
  - Optional-skill ports touched `cron/scheduler.py`, `cron/jobs.py`, `tools/cronjob_tools.py`, `agent/auxiliary_client.py`, `hermes_cli/runtime_provider.py` — every file Fox modified.
- **Plugin-system evolution**:
  - **At HEAD, the Python plugin manager registers ~17 hook events** (added `transform_llm_output`).
  - **Plugin kinds gained `model-provider`** — third parties can register a `ProviderProfile` via `plugins/model-providers/<name>/`. **Fox's #109 Custom Ollama URL is exactly the shape of a `model-provider` plugin.**
- **Last 30 days, files in Fox's modified-file set**:
  - `cron/scheduler.py`: 5 commits.
  - `cron/jobs.py`: 1 commit.
  - `tools/cronjob_tools.py`: 2 commits.
  - `hermes_cli/runtime_provider.py`: 2 commits including `fix(credential_pool): resolve key mix-up when custom providers share base_url` (`e38ea3807`) — directly relevant to Fox's custom-Ollama work, **already implements much of #109**.
  - `agent/auxiliary_client.py`: 5 commits.

## nesquena/hermes-webui — current state

- **Latest tag**: `v0.51.22` on **2026-05-07**.
- **Cadence (last 6 mo)**: extremely high — typical day ships **3–10 patch tags**. 953 commits in 16 days (~60/day average).
- **Top ~10 themes/features shipped since Fox's fork-base** (479 commits behind):
  1. **Kanban v1 launch** (v0.51.0, PRs #1645, #1646, #1647, #1649, #1654, #1655, #1660, #1675) — first-party-compatible board, multi-board CRUD, real-time SSE event stream, dispatcher contract enforcement, +68 tests.
  2. **Kanban hardening** (#1828, #1843).
  3. **VPS resource health panel** + **agent heartbeat alert** + active provider quota status (PR #1676).
  4. **Workspace polish** (#1816, #1818, #1689, #1702).
  5. **Custom provider routing** — named custom providers (PR #1818), `:free`/`:beta`/`:thinking` suffix mis-resolution fix (#1783), `custom:*` provider model list (#1619), provider duplicate-group collapse (#1568) — **directly overlaps Fox's #109 custom-Ollama-URL work**.
  6. **Codex spark models** (#1685), **Codex OAuth onboarding flow** (commit `259c5c4`), **Anthropic OAuth env fallback serialization** (commit `91f99d8`).
  7. **Streaming markdown** via `smd.min.js` (P0 hotfix in v0.51.22 PR #1851) and **LaTeX `\(...\)` / `\[...\]` delimiter rendering** (PR #1848).
  8. **No-agent cron edits** support, **shell-route HTML 503 fallback** (PR #1844 v0.51.21).
  9. **CSP source-map allowance for jsDelivr** (PR #1852).
  10. **Subpath frontend route hardening**.
  11. **Auto-compression running indicator**, **adaptive title refresh deadlock fix** (#1693).
- **Open issues / open PRs**: **65 open issues**, **30 open PRs**.
- **Top 5 contributors last 6 mo**: nesquena-hermes (343), Hermes Bot (95), Michael Lam (83), test (78), bergeouss (55).
- **Breaking changes**:
  - **`api/routes.py` shape**: 5,425 lines at fork-base → 8,578 lines at upstream HEAD (+3,153 lines, +58%). Fox's version has 6,837 lines.
  - **Five new `api/` modules**: `agent_health.py`, `dashboard_probe.py`, `kanban_bridge.py`, `system_health.py`, `session_recovery.py`. **None overlap Fox's added modules — clean coexistence is possible.**
  - **Service worker (`static/sw.js`)** version-pin scheme tightened.
  - **CSP headers** in `api/helpers.py` updated for jsDelivr.
  - **`localStorage.setItem('hermes-webui-model')` now guarded against `QuotaExceededError`** (commit `9a0a621`).
- **Plugin / extensibility surface**: webui has **no plugin system** in the agent's sense.
- **Last 30 days touch on Fox-modified files**: `api/routes.py` 80 commits, `api/streaming.py` 18, `api/models.py` 21, `api/providers.py` 8, `static/index.html` 35, `static/style.css` 66, `static/boot.js` 12, `static/onboarding.js` 5, `static/sw.js` 5, `server.py` 8. **Nearly every Fox-modified file is upstream-active**.
- **Kanban impact on Fox files**: Kanban v1's 12-commit stack landed on 2026-05-05 and touched `api/routes.py`, `static/index.html`, and `static/style.css`. Specifically: `397d851 feat(kanban): multi-board management + SSE live event stream`, `dc3418c feat: add Kanban dashboard parity core`, `5093e01 feat: add Kanban write semantics MVP`. Fox's `routes.py` and `index.html` patches will require manual three-way reconciliation here.

## Other NousResearch projects worth knowing

- **`hermes-agent-self-evolution`** (2,915 stars) — DSPy + GEPA evolutionary skill optimizer.
- **`hermes-paperclip-adapter`** (1,126 stars) — Hermes as a managed employee in Paperclip.
- **`atropos`** (1,178 stars) — RL environments framework.
- **`autonovel`** (882 stars), **`pokemon-agent`** (85 stars) — applications built on Hermes Agent.
- **`NemoClaw`**, **`OpenShell-Community`** — sandbox runtime for autonomous agents.
- **No repos suggest hermes-agent is being rewritten or absorbed**. The org's posture is to invest in `hermes-agent` as the flagship and add adapters/applications around it.

## Implications for the Fox separation architecture

- **Cadence reality check**: 1,236 agent commits + 953 webui commits in the **last 30 days** = ~73 upstream commits per day across both. Even a weekly Fox rebase would face ~500 commits worth of conflict surface. A patch-series-on-tag-only strategy (only re-baselining when upstream tags a release) is the only sustainable model.
- **Drop-in opportunities (Fox commits to retire)**:
  - **#109 Custom Ollama URL** is partially obsolete. Drop redundant parts.
  - **Fox's `mem0_oss` plugin** uses an outdated `plugin.yaml` schema.
- **Plugin hooks Fox should adopt to retire monkey-patches**:
  - **`transform_llm_output`** for Fox guardrails Phase 1.
  - **`pre_gateway_dispatch`** for Fox admission control.
  - **`on_session_start` / `on_session_finalize`** for `mem0_oss`.
  - **`pre_approval_request` / `post_approval_response`** for Llama Guard 3 (Phase 4 / #6).
  - **`plugins/model-providers/` directory + `ProviderProfile` ABC**.
- **Patches at structural risk**:
  - **`api/routes.py`** — single largest conflict surface. Recommendation: shard Fox's routes into `api/fox_*.py` modules.
  - **`static/style.css`** — 66 upstream commits in 30 days.
  - **`static/index.html`** — 35 upstream commits/30 days.
  - **`cron/scheduler.py`** — `af9336d57 feat(gateway): generic plugin hooks for env enablement + cron delivery` directly contests this file.
- **Kanban as forcing function**: webui's Kanban v1 added a parallel UI layer that Fox doesn't need but users will expect. Either Fox enables it pass-through (zero work) or hides it (CSS/route gating).
- **Security cadence**: 8 P0 security closures in v0.13.0 alone, including a CVSS 8.1 cross-guild Discord DM bypass. Fox tracking upstream tags weekly, not monthly, is now a **security requirement**, not just a freshness preference.

## Sources

**Repos & releases**
- https://github.com/NousResearch/hermes-agent (138,586 stars)
- https://github.com/NousResearch/hermes-agent/releases (latest `v2026.5.7` = v0.13.0)
- https://github.com/nesquena/hermes-webui
- https://github.com/nesquena/hermes-webui/releases (latest `v0.51.22`)
- https://github.com/orgs/NousResearch/repositories?type=public

**Local clones with `upstream` remote**
- `/Users/macpro/Desktop/Fox-In-the-Box/hermes-agent` — upstream HEAD `a3131862b` (2026-05-08), merge-base `e5dad4ac` (2026-04-30), 737 commits behind.
- `/Users/macpro/Desktop/Fox-In-the-Box/hermes-webui` — upstream HEAD `5005f1c8` (2026-05-07), merge-base `9e31a2ac` (2026-05-03), 479 commits behind.

**Issue counts (via `gh api search/issues`)**
- NousResearch/hermes-agent: 3,211 open issues + 5,737 open PRs
- nesquena/hermes-webui: 65 open issues + 30 open PRs

**Top contributors (via `git shortlog -sn upstream/{main,master} --since='2025-11-08'`)**
- Agent: Teknium 368, Brooklyn Nicholson 59, teknium1 53, Austin Pickett 42, brooklyn! 36
- Webui: nesquena-hermes 343, Hermes Bot 95, Michael Lam 83, test 78, bergeouss 55

---

# 6. Decision Points Still Open

Three things need explicit sign-off before any implementation starts:

1. **Approach: hybrid as described in section 1?** (Submodule-pinned-upstream + sibling overlay + 9-line patch + runtime plugin adoption.) Or a single lane?

2. **Migration cadence: ship as v0.5.5 (3 weeks of dedicated work), or interleave with Phase 1 guardrails (#4 + #5)?** The roadmap currently has Phase 1 in v0.5.5; this work would either delay it or share the slot.

3. **Upstream-PR campaign first?** Send the 5 bug-fix-class commits (~7 files) upstream before migration, so the patch series starts smaller. Adds ~3–5 days but materially reduces ongoing maintenance.

---

**Document control**

- Generated: 2026-05-08
- Research dispatch: 4 parallel agents (Plan + general-purpose subagents)
- Synthesis author: Claude Code (Opus 4.7)
- Status: NOT COMMITTED — local document only, awaiting decision per @roadhero instruction
- Location: `docs/architecture/upstream-separation-plan.md` in working tree
