# Changelog

All notable changes to Fox in the Box are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.6.3] - 2026-05-19

**First upstream bump driven by the auto-watch loop.** Fox now ships upstream `nesquena/hermes-webui` **v0.51.92** (was v0.51.84 — 8 patch versions of upstream improvements). The agent stays pinned at v2026.5.16. End-to-end proof that the v0.6.0 overlay architecture pays off: zero anchor refresh required, zero Fox code touched, ~5 minutes from auto-issue to merged PR.

### Upstream changes you may notice

- **Grok OAuth** is now a supported provider in the catalog
- **Auto-compression handoff** is surfaced more clearly in long conversations
- **Workspace file icons** in the file tree are visually aligned
- **Anonymous custom endpoints** stay in the model picker even when `/v1/models` probe fails (handy for OpenAI-compatible setups behind auth)
- Security-tightened: archive extraction is now scoped per-session attachment dir
- Plus assorted smaller fixes across `~108 files` upstream (full upstream changelog: see [v0.51.85 ... v0.51.92 on nesquena/hermes-webui](https://github.com/nesquena/hermes-webui/compare/v0.51.84...v0.51.92))

### Behind the scenes

- **`upstream-watch.yml` workflow bug fixed (#273 / #274).** The nightly watcher had a `set -e` + `[ ] && echo` gotcha that killed it whenever exactly one of the two upstreams drifted. Result: both 2026-05-18 + 19 nightly runs failed silently (only the generic self-health issue fired). Fix: replaced the short-circuit pattern with explicit `if/then` blocks. Surfaced because nesquena/hermes-webui shipped v0.51.92 yesterday but agent stayed pinned — asymmetric drift triggered the bug. First real-world signal-from-the-watcher: issue [#275](https://github.com/fox-in-the-box-ai/fox-in-the-box/issues/275).
- **`packages/fox-overlay/versions.toml`** gains a `[history]` block tracking prior pins for future debugging.
- `check-overlay-basis.sh` verified clean against v0.51.92 in both the auto-watch run AND the pre-build CI gate on this PR.

### What's next

v0.6.x stabilization continues; Playwright Phase 0 (#264) when you're ready. Upstream-watch is now self-healing for future asymmetric drift.

---

## [0.6.2] - 2026-05-19

Three small stabilization fixes surfaced during real-world smoke of v0.6.1. No new features; v0.6.x stays on track.

### Fixed

- **Mac launcher no longer stays open after the browser launches (#271).** Before: on a successful Mac launch, the browser would open and Fox worked, but the launcher window stayed visible stuck on "Step 5/6 — Wait for services." Race in `monitorContainerSetupLogs`: an in-flight `container.logs()` Docker API call could resolve AFTER `stopLogMonitor()` had been called, then call `showProgress(...)` which sees `_progressWin === null` (because `closeProgress()` already destroyed the window) and creates a fresh launcher window with the stale step-5 text. Fix: a `stopped` re-check after the async logs() returns, before any `showProgress` call.
- **Stream-error retry panel hides upstream's inline error immediately (#267).** Before: in v0.6.1, when an `apperror` event fired, the Fox "Something went wrong, please try again" panel appeared but upstream's `**Provider mismatch:** …` markdown ALSO stayed visible in the transcript above the panel until the user clicked Retry. After: the panel is now the sole error UI from the moment the error fires — upstream's inline message is wiped immediately on `apperror`, not deferred to the Retry click.

### Behind the scenes

- **Retired the `webui_patches/providers.py` overlay (#269 / #163).** The Fox overlay was substituting upstream's `set_provider_key` to add a `supervisorctl restart hermes-gateway` after every API-key change. Verified on a fresh v0.6.1 container that upstream's `_reload_runtime_env_preserving_config_authority()` at `gateway/run.py:15103` already picks up rotated keys per-turn without any gateway restart — the overlay was dead code AND actively worse (the supervisor restart disrupted in-flight SSE streams that upstream deliberately preserved). Removing the overlay simplifies the patch surface and aligns Fox with upstream's documented behavior. No user-visible change; the WebUI's Settings → Providers flow continues to work identically.
- **New jest regression tests** for the launcher race fix — `tests/electron/docker-manager.test.js` now covers the "stop() called during in-flight logs()" race + a no-op-when-callback-missing path.

### What's next

v0.6.x stabilization continues. Playwright Phase 0 (#264) is the next bigger workstream — replaces the manual smoke checklist for Sections A-C once landed.

---

## [0.6.1] - 2026-05-18

A universal retry surface for streaming errors. Closes the two v0.7.x carry-overs from the v0.6.0 migration in one shot, using a simpler approach than the original feature-specific implementations.

### Added

- **"Something went wrong, please try again" panel** with a Retry button that re-sends your last message. Appears at the bottom of the chat whenever the server emits a streaming error — auth mismatch, out of credits, rate-limited, mid-stream interruption, no-response, anything except a user-initiated cancellation. Retry wipes the partial assistant response, restores your prompt, and re-sends.

### Fixed

- **#254 — Mid-stream break detection.** Previously: v0.6.0 dropped Fox's old "Stream interrupted" label + partial-text-preservation behavior because upstream refactored the streaming/self-heal flow. Now: every error class — including mid-stream breaks — surfaces the same Retry panel, replacing both the lost behavior and upstream's wordy default error message.
- **#255 — Silent auto-failover on auth/quota errors.** Previously: when an OpenRouter key was rejected or credits ran out, v0.6.0 surfaced upstream's apperror with no auto-switch. Now: same Retry panel; the user clicks Retry once they've fixed the key in Settings → Providers (or already has fallback configured). Manual provider switch via Settings → Providers continues to work.

### Behind the scenes

- The fix is a single ~190-line static JS file (`packages/fox-overlay/webui_static/stream-error-retry.js`) injected via `HERMES_WEBUI_EXTENSION_DIR` + ~30 lines of CSS. No Python patches, no monkey-patches — it subscribes to upstream's stable `apperror` SSE event as a downstream consumer. Because it doesn't modify upstream source, it survives any future refactor of upstream's error-handling flow as long as the `apperror` event name + payload shape stay stable.

### Verified

Manual smoke against `:latest` candidate post-merge:
- Force `auth_mismatch`: set OpenRouter key to garbage in Settings → Providers → send message → upstream's inline error suppressed, Fox panel appears, Retry restores the prompt
- Force `interrupted`: kill the agent mid-stream via `docker exec ... pkill -KILL ...` → panel appears, partial assistant tokens wiped, Retry works
- Cancel button (`type: cancelled`): panel does NOT appear — user-initiated, no retry surface needed

### What's next

v0.6.x stabilization tail-end. Then Playwright E2E infrastructure (Phase 0 of a phased rollout the architects scoped today — see the upcoming Playwright epic).

---

## [0.6.0] - 2026-05-18

Upstream-separation migration. The `forks/hermes-webui` and `forks/hermes-agent` submodules now point at the virgin upstream repositories (`nesquena/hermes-webui` v0.51.84 and `NousResearch/hermes-agent` v2026.5.16). All Fox-specific behavior moved into the new `packages/fox-overlay/` package — applied at Docker build time as patch series + file-removals + a sibling Python package + pip-installed monkey-patches. Net: Fox can absorb upstream weekly instead of carrying 1,500+ commits of drift.

### Added

- **`packages/fox-overlay/` package** with four layering mechanisms: webui patch series (`patches/webui/`), agent patch series (`patches/agent/`), `.fox-removals` file-deletion manifest, and the `fox_overlay` Python package (`webui_modules/`, `webui_patches/`, `agent_plugins/`, `agent_memory_plugins/`). See `docs/architecture/upstream-overlay.md` for the full architecture.
- **`packages/fox-overlay/versions.toml`** pins the upstream tag pair. The pinned tags are the canonical source of truth for what virgin upstream Fox is currently riding on.
- **`packages/fox-overlay/scripts/check-overlay-basis.sh`** verifies every overlay artifact still applies cleanly against the current submodule pin. Runs as a CI gate before every Docker build via `.github/workflows/build-container.yml`.
- **Nightly `upstream-watch.yml` workflow** queries upstream for newer tags, runs `check-overlay-basis.sh` against the proposed bump, and opens an issue tagged `upstream-update-available` (clean) or `upstream-drift` (refresh required). 05:17 UTC daily; manual `workflow_dispatch` also supported.
- **`FITB_DISABLE_WEBUI_OVERLAY` and `FITB_DISABLE_AGENT_OVERLAY` build/runtime flags** for bisecting overlay-induced regressions during future bumps.

### Changed

- **`forks/hermes-webui` submodule URL** flipped from `fox-in-the-box-ai/hermes-webui` to `nesquena/hermes-webui` (virgin upstream). Same change for `forks/hermes-agent` → `NousResearch/hermes-agent`. The fork repos are archived but kept for history.
- **Webui patch series trimmed to two patches, 9 lines total**: a `server.py` bootstrap shim that loads `fox_overlay` at boot, and a `routes.py` dispatch hook that routes Fox-claimed paths through the overlay's dispatcher.
- **Phase 6 monkey-patch refresh against v0.51.84**: dropped redundant `get_config` patch (upstream native now does mtime checks); dropped the `models.py` patch wholesale (upstream v0.51.84 natively ships every Fox #1558 fix verbatim); refreshed the `reload_config` and `auxiliary_client` anchors against the new upstream code.
- **Agent monkey-patch bootstrap** extracted from the fork (where it was a free-floating commit) into a managed patch (`patches/agent/001-gateway-bootstrap-shim.patch`) so the upstream re-point doesn't drop it on the floor.

### Removed

- **`fox-in-the-box-ai/hermes-webui` and `fox-in-the-box-ai/hermes-agent` fork dependencies.** Both submodules now point at virgin upstream. The fork repos remain on GitHub under an archive tag.
- **`.github/workflows/sync-submodules.yml`** is gone — irrelevant in a virgin-upstream + overlay world; superseded by `upstream-watch.yml`.

### Known regressions (deferred to v0.7.x)

Two Fox features that depended on heavy in-place patches of upstream's streaming/self-heal flow could not be carried forward as textual substitutions against v0.51.84's refactored code. Both are tracked and will be re-implemented in v0.7.x using a downstream event-subscription pattern (subscribing to `put('apperror', ...)`) instead of in-place substitution:

- **#254 — Mid-stream break detection** (FITB#89): Fox's "Stream interrupted" label + partial-text preservation on mid-stream errors is unavailable. Upstream's native error classification still surfaces an error, just with upstream's wording and without partial-text preservation.
- **#255 — Silent auto-failover to local on auth/quota errors** (FITB#129b): on `auth_mismatch` / `quota_exhausted` the failover modal is unavailable. Manual provider switch via Settings → Providers still works (FITB#9 plumbing preserved).

### Verified

Full smoke checklist sections A–L re-run on a clean container built from main post-migration:
- All v0.5.0/v0.5.1/v0.5.2/v0.5.3/v0.5.4 baseline checks (carry-forward)
- New Section L v0.6.0 row: webui boots with `[fox-overlay] bootstrap installed: dispatcher frozen, N GET + M POST handlers registered`, agent boots without `fox-overlay-failed` warnings, mem0_oss installed in `/app/hermes-agent/plugins/memory/`, every Fox-claimed `/api/*` endpoint returns 200
- The two regressions above were verified intentional (not crashes) — UX degrades to upstream's defaults rather than failing

### What's next

v0.6.1 (or v0.7.0) re-implements #254 + #255 using the event-subscription pattern documented in `docs/architecture/upstream-overlay.md`. Then v0.7.x Phase 4 (Llama Guard 3 1B, original roadmap #6) resumes.

---

## [0.5.4] - 2026-05-07

Three stabilization fixes surfaced by real-world users in the days after v0.5.3 shipped. No new features — Phase 1 (#4 + #5) shifts to v0.5.5 per Rule 1.

### Fixed

- **Ollama models now appear in the chat picker immediately after "Use" (#138).** Before: clicking "Use this model" on an Ollama tile in Settings persisted the choice but the chat picker silently kept showing the previous provider's groups for up to five minutes. After: the in-memory available-models cache is evicted on every config change, so the picker reflects reality on the next open. Root cause was a half-fixed cache: the on-disk cache was being deleted on writes, but the parallel in-memory cache wasn't.
- **Tailscale auth link works in Safari and other popup-blocking browsers (#139).** Before: `window.open()` was silently swallowed by Safari's default popup blocker, leaving users staring at "Waiting for you to finish auth in the browser tab…" with no way forward. After: the auth URL renders as a persistent clickable link in the Tailscale tile alongside the auto-open attempt. The link clears on success or failure.
- **Tailscale Serve auto-configures even when authentication happens late (#140).** Before: if the user authenticated after the entrypoint's 15-minute boot window expired (or via `docker exec` outside the webui flow), `_attempt_configure_serve` was never called and the tailnet HTTPS URL stayed broken until the user clicked the manual "Configure HTTPS" retry button. After: `get_status()` triggers a one-shot configure when it sees `Running` + `serve_state == idle`. Idempotent on subsequent polls. Also adds a persistent inline hint pointing to the tailnet's admin console DNS page for the HTTPS Certificates toggle — the one prerequisite we cannot enable on the user's behalf.

### Verified

Full smoke checklist sections A–L re-run on a clean candidate container against `:latest`:
- All v0.5.0/v0.5.1/v0.5.2/v0.5.3 baseline + stabilization checks (carry-forward)
- New v0.5.4 #138 check: Ollama "Use" → chat picker immediately reflects the new model
- New v0.5.4 #139 check: Tailscale Connect in Safari → link visible + clickable, full auth completes
- New v0.5.4 #140 check: tailscaled authed mid-poll → `tailscale serve status` shows :8787 mapped without manual button click

### What's next

v0.5.5 picks up the original Phase 1 plan: `fox-guardrails` plugin scaffold (#4) + Microsoft Presidio PII detection (#5).

---

## [0.5.3] - 2026-05-07

Fox finds Ollama wherever it lives. Small focused release: one new feature, one issue closed-as-shipped.

### Added

- **Custom Ollama URL.** Point Fox at any Ollama daemon you can reach — a NAS at `192.168.1.50:11434`, a beefy desktop on your LAN, anything that speaks the Ollama API. Settings → Providers → Local Ollama → "Custom Ollama URL (advanced)". Empty (default) preserves the existing auto-detection. Validation rejects malformed URLs at save time so a typo never gets persisted; the cache invalidates immediately so the new probe result shows up the next time you open Settings (no 10-second wait).

### Fixed / Verified

- **Tailscale Serve retry button (#110)** — turns out this already shipped in v0.5.1 (the "Configure HTTPS" button in Settings → Tailscale tile). Closed as done after verifying in the v0.5.3 candidate.

### Verified

Full smoke checklist sections A–L re-run on a clean candidate container against `:latest`:
- All v0.5.0 baseline checks (#114-#117, README HTTPS toggle)
- All v0.5.1 #122 stabilization checks (wizard option-B flow, Tailscale Serve state, failover modal eligibility, recovery banner late-enable, `:stable` release-tag-only, FITB_VERSION populated)
- All v0.5.2 #127/#128/#129 stabilization checks (operator watchdog, timeout modal, auto-failover, download-on-demand)
- New v0.5.3 #109 checks (validator across 13 edge cases, atomic save, probe fallback, UI element + handler in served files)

### What's next

v0.5.4 starts Phase 1 of the original roadmap: `fox-guardrails` plugin scaffold (#4) + Microsoft Presidio PII detection (#5). Two-week effort. Per Rule 1, the original Phase 2 (Pydantic business rules #7) shifts to v0.5.5.

---

## [0.5.2] - 2026-05-06

Local fallback finally lives up to its name. v0.5.2 closes the gap between "local fallback enabled" (model is downloaded and ready) and what users actually expected: when your cloud provider fails, the assistant transparently switches to your local model and tells you about it. No more frozen tabs, no more cryptic errors.

This release also closes one Tailscale edge case from v0.5.1 verification.

### Fixed / Improved

- **Auto-failover to local model when cloud fails.** Before: "local fallback enabled" was just a label — the gateway didn't actually retry. After: bad API key, expired credits, network drop, slow provider — the assistant swaps to your downloaded local model in the background and shows a small "Switched to local — re-send to use it" notice. Eligibility is broad on purpose (auth, quota, no-response, model-not-found): chat must keep working.
- **"Provider isn't responding" modal after 10s.** When a remote provider stalls without an error (slow LLM, transient network), a modal appears offering "Switch to local now" instead of letting you stare at a frozen tab. Default 10s, override via `localStorage.fitb.timeout_modal_ms`. Auto-dismisses if the response eventually arrives.
- **Download-on-demand prompt when local isn't ready yet.** If your cloud fails and local fallback is enabled but the model isn't downloaded, you'll see a one-click "Download Phi-4-mini (~2.5 GB) and continue" prompt with progress UI inside the modal. When the download finishes the local model activates automatically.
- **Tailscale operator-grant survives key expiry.** Before: when a tailnet auth key expired, tailscaled cleared its `OperatorUser` preference and the next "Connect" click returned `Access denied: checkprefs access denied` with no in-app recovery. After: a tiny supervisord watchdog re-asserts the operator grant every 30 seconds. Idempotent — no observable cost on a healthy tailnet.

### Architecture

- New backend endpoint `POST /api/local-fallback/activate` swaps the gateway's active model to the bundled llama.cpp endpoint with one call. Used by both the timeout modal and the auto-failover engine.
- New `ready` field on `/api/local-fallback/status` (= installed AND server healthy) — the single boolean the failover loop checks.
- New SSE event types: `provider_switched`, `partial_response_truncated`, `local_fallback_unprepared`. Both `apperror` sites in `api/streaming.py` route through a shared `_attempt_failover()` helper with a 4-branch decision tree.

### Known limitations

- The in-flight prompt is **not** auto-retried after `provider_switched` — you re-send manually. Tighter coupling with the chat-send flow is deferred to a later release; the gain wasn't worth the risk surface for v0.5.2.
- Mid-stream failure mid-token-stream: any partial response is wiped (truncate policy). Trade-off: cleaner restart, at the cost of losing a few visible tokens.

### Verified

`/api/local-fallback/activate` endpoint behaves correctly (200 when ready, 400 with granular `reason` when not) · `_attempt_failover` decision tree all 4 branches · already-local guard prevents redundant `provider_switched` cascades · supervisord watchdog re-asserts `OperatorUser` within one 30s tick after force-clear · Tailscale `up` from foxinthebox user produces auth URL post-watchdog (was `Access denied: checkprefs`) · all v0.5.1 Section L regression checks pass.

### What's next

v0.5.3 (Phase 1 of the original roadmap, now slotted): `fox-guardrails` plugin scaffold (#4) + Microsoft Presidio PII detection (#5).

---

## [0.5.1] - 2026-05-06

Stabilization fix release. v0.5.0's clean-DMG smoke surfaced 7 issues across the wizard, Tailscale, and failover paths (issue #122). All seven addressed end-to-end against a real Docker container, a real tailnet, and a real Ollama daemon.

This release contains no new features — only fixes, plus two pieces of CI hygiene that prevent future drift.

### Fixed

- **Wizard's local-model fast-paths now actually render.** `setup.js` probes `/api/ollama/status` and `/api/local-fallback/status` during boot, but those endpoints were 302 redirecting to `/setup` (the onboarding gate didn't exempt them). `fetch` followed the redirect, JSON parse silently failed on the HTML, and the Ollama-detection box / bundled-local-model CTA never appeared even when Ollama was running. Both endpoints exempt now.
- **Wizard no longer auto-completes when you pick a local model.** "Use [model]" used to call `/api/setup/complete` and redirect to chat instantly — skipping the OpenRouter step and the explicit "Open Fox" handoff. Reported as confusing ("clicking the input field redirects me to chat" — actually a race against an 800ms delayed redirect). Now: picking a local model sets the model, advances to Step 2 ("Add OpenRouter — optional"), and Step 3 is the only place that completes onboarding. Same for the bundled llama.cpp path.
- **Race window in Step 1 closed.** The 800ms redirect that fired after "Use [model]" left the wizard fully interactive — clicks during that window could land on a stale Step 2 input. Wizard now replaces itself with a "Setting up [model]…" loading state synchronously on click.
- **Tailscale Serve config now surfaces in the UI.** When the auto-`tailscale serve --bg 8787` failed (most often: HTTPS not enabled in the tailnet admin console), the failure was logged at DEBUG level and silently dropped. Now: the Settings → Tailscale tile shows "HTTPS configured ✓" or a "Configure HTTPS" retry button + the actual error. Works for both Connect-button auth and desktop-app auth flows.
- **Reactive failover modal now fires on auth and quota errors** (`auth_mismatch`, `quota_exhausted`). Previously excluded with the rationale that "local fallback can't fix the user's wrong key" — but local fallback REPLACES broken cloud entirely. Auth/quota errors are exactly when the modal should offer to switch.
- **Recovery banner now starts polling when fallback is enabled mid-session.** Previously polling only kicked off if fallback was already on at page load, so the most common flow (provider fails → enable fallback → restore key → expect banner) silently never started. Settings panel now dispatches an event the banner subscribes to.
- **App version display no longer empty.** `:latest` and `:stable` images built off main pushes had `FITB_VERSION=""` (only tag pushes set it). Now non-tag builds get `dev-<short-sha>` so the in-app version is always populated.

### CI hygiene

- **`:stable` is now release-gated.** It used to auto-bump from `:latest` on every push to main, including post-release docs PRs. v0.5.0's `:stable` had drifted from `:v0.5.0` within hours of release. Now `:stable` only moves on tag pushes (`release.yml`'s digest-pinned re-tag).
- Pre-release verification now uses `docker pull ghcr.io/...:stable` invoked the way the DMG's LaunchAgent does, not a local `docker build`. Captured in `qa/SMOKE_CHECKLIST.md` and the QA methodology memory.

### Verified

Wizard option-B flow with real host Ollama (gemma4:latest detected → Step 2 optional OpenRouter → Step 3 summary → Open Fox → real reply) · Tailscale Connect → auth → Serve auto-config → HTTPS URL serves FITB chat from a phone on the same tailnet · settings persist across `docker stop` + KeepAlive restart · local fallback download (~2.5 GB Phi-4-mini) → ready → recovery banner appears when remote provider restored · macOS DMG signed + notarized stapled · `:stable` digest verified to match `:v0.5.1` on tag push.

### Known follow-ups (next release, v0.5.2)

- #127 — Tailscale operator-grant doesn't survive key expiry. Edge case (only triggers when a tailnet key expires after FITB install). Workaround: `docker exec fox-in-the-box tailscale set --operator=foxinthebox`.
- #128 — Timeout-based modal: offer local switch when a provider doesn't respond in N seconds. Better UX than the current "wait forever for an explicit error".
- #129 — Real auto-failover engine. Today "local fallback enabled" means the model is downloaded and ready — but the gateway doesn't actually retry against local on remote failure. The companion architectural fix to #128.

### What's next

Phase 1 of the roadmap (v0.5.2): the items above plus the `fox-guardrails` plugin scaffold (#4) + Presidio PII detection (#5).

---

## [0.5.0] - 2026-05-05

Stabilization release. Real-hardware verification of v0.3.0–v0.4.6 features surfaced 5 latent bugs that had been silently shipping for months. All fixed and verified end-to-end against a real Docker container and a real Tailscale tailnet.

This is Phase 0 of the new roadmap: nothing new, everything works.

### Fixed

- **Local AI fallback now actually works on Apple Silicon (#114).** The Docker build was downloading x86_64 binaries into arm64 images. `llama-server` would crash with a Rosetta error within seconds of toggling the fallback on. Apple Silicon users have been hitting this since v0.4.1.
- **Tailscale Serve now actually publishes HTTPS (#115).** The bundled tailscale binary moved past 1.60, which removed the legacy `serve` syntax we were calling. Auto-config silently failed on every container — the `https://<host>.<tailnet>.ts.net/` URL the README promised never came up. Modern syntax now used; verified end-to-end.
- **Settings actually persist across container restart (#116).** Theme, hostname-prompted flag, local-fallback toggle, all 6 Tailscale power-user fields — every persisted setting was being written to a path inside the image, wiped on every restart. This bug has been latent since the project's beginning. Fixed: settings live on the `/data` volume now.
- **Model switching actually reaches the gateway (#117).** When you switched providers via Settings (Ollama, OpenRouter, custom), the WebUI was writing config to a file the gateway never read. The "Save" call returned ok=true; the next chat ignored your change and routed through whatever was loaded at boot. Latent since v0.3.0. Fixed: WebUI and gateway now share the same config path.
- README updated to mention the one-time HTTPS toggle in the Tailscale admin console (DNS → Enable HTTPS) that Tailscale Serve requires.

### Verified

Tailscale full lifecycle (real auth, real device on tailnet) · bundled llama.cpp full flow on arm64 (2.5 GB download → real chat) · Ollama detect → use-model → chat · settings persistence across `docker restart` · reactive failover modal on real provider failure · macOS DMG signed + notarized stapled · Linux `install.sh` syntax on Ubuntu 22.04 + 24.04.

Full verification log on `qa/v0.4.7-verification` branch (kept as reference, not merged).

### What's next

Phase 1 (v0.5.1): guardrail plugin scaffold (#4) + Presidio PII detection (#5).

---

## [0.4.7] - 2026-05-05

Hotfix release. Comprehensive QA pass on the v0.4.4–v0.4.6 features after the project owner asked the question: "Have we fully completed Ollama and Tailscale integrations? Is there literally anything left, untested, not working fully or where we came short?" Answer: yes, plenty. Two parallel review agents and one adversarial reviewer found 30+ real bugs across the freshly-shipped code. End-to-end testing against a real Docker container surfaced two more showstoppers: **the v0.4.4 desktop Tailscale flow had been silently broken — clicking Connect showed "Starting…" forever**.

### Fixed (showstoppers found by real-container testing)

- **Tailscale desktop auth flow now actually works (Wave G).** Two root causes:
  - `tailscaled` runs as root for `NET_ADMIN`; the WebUI process runs as `foxinthebox` per `supervisord.conf`. Without `tailscale set --operator=foxinthebox`, every `tailscale` CLI call from the WebUI errored with `Access denied: login access denied`. Fix: `entrypoint.sh` runs `tailscale set --operator=foxinthebox` after the WebUI is healthy and the daemon is reachable, with a 60s budget. Every `tailscale up` invocation from `api/tailscale.py` now also includes `--operator=foxinthebox` because Tailscale requires non-default flags to be re-stated on every `up`.
  - The auth URL never reached the UI. `tailscale up` block-buffers stdout when not attached to a TTY → Python's `readline()` returned nothing → state stuck at "Starting…" forever. Fix: scrape the `AuthURL` field from `tailscale status --json` (the daemon exposes it directly the moment a fresh `up` issues), instead of trying to read the subprocess's stdout. End-to-end test in a v0.4.7 container: auth URL surfaces in <3 seconds.

### Fixed (P0 security)

- **XSS in the wizard's `useLocalOllama` inline `onclick`.** Model names from a remote Ollama daemon were interpolated into a JS string literal inside an HTML attribute via `escapeHtml()`, which is HTML-attribute-safe but not safe for JS string literals. A backslash-plus-apostrophe in a model name could break out of the string and execute arbitrary code in the wizard. Fix: replace inline-onclick interpolation with a `data-action` / `data-model` attribute pair plus a single delegated click listener.
- **Tailscale flag-injection via unvalidated power-user strings.** `--login-server`, advertise-routes, advertise-tags, exit-node values flowed straight into `tailscale up` argv without validation. shell=False prevented classic shell injection, but a malicious `/api/settings` POST could prefix a value with `-` to inject another flag, point `--login-server` at attacker-controlled headscale, or smuggle newlines/control characters. Fix: per-field regex validators (URL, CIDR list, `tag:` form, hostname RFC 1035, host charset) enforced at both `_build_up_argv` (argv-time gate) AND `save_settings` (POST-time gate, defense in depth). Validator error messages now reach the UI as proper 400 responses with the specific reason.

### Fixed (P1 — concurrency, lifecycle, secrets)

- **Six race conditions in the Tailscale state machine.** `_up_proc` and `_up_log` were mutated outside `_up_lock`, the daemon thread used the *global* `_up_proc` mid-loop (capture-by-reference bug — a second Connect could redirect the first thread's `wait()` to the new subprocess), `logout()` didn't kill the in-flight subprocess (orphan could resurrect "running" state minutes after the user disconnected), `start_up()` from terminal `failed`/`running` didn't reset the previous `_up_proc`, and `get_up_progress()` could write `state="running"` over a concurrent `logout()`'s reset because it didn't pass an `attempt_id`. Fix: introduce an `attempt_id` rotation pattern — each daemon thread captures its id on spawn; `_set_up_state(attempt_id, ...)` silently drops stale-thread updates; all `_up_proc`/`_up_log` access goes through `_up_lock`; `_up_subprocess` uses a local `proc` variable for all subprocess ops; `logout()` actively kills in-flight; `get_up_progress()` passes the snapshot's attempt_id.
- **Hostname dropped on Reconnect.** `_load_persisted_opts` returned the six power-user fields but not hostname — so a saved `FOX_HOSTNAME` was silently replaced with whatever Tailscale's default-naming chose (typically the container ID) on every Reconnect. Fix: include hostname (read from `/data/config/hermes.env` via the existing #44 helper).
- **`logout()` didn't clean Tailscale Serve config + Reconnect didn't auto-Serve.** Stale Serve binding pointed at the now-disconnected tunnel; after a fresh Connect under a new tailnet identity, Serve was missing until manual recovery. Fix: `logout()` runs `tailscale serve reset` (with `tailscale serve / off` fallback for older builds), and the daemon thread auto-calls `configure_serve()` after detecting `BackendState=Running`.
- **`use_model` leaked stale provider keys.** Only `api_key` was popped from the existing `model_cfg`, leaving `azure_endpoint`/`azure_api_version`/`aws_region`/`aws_access_key_id`/`aws_secret_access_key`/`vertex_project`/`openai_organization`/custom headers in place when switching to local Ollama. At minimum a stale-secrets exposure in a config the user thought they had switched away from; at worst those keys riding along on Ollama requests. Fix: replace the model block wholesale.
- **`bool("false") == True` settings footgun.** A `curl -X POST -d '{"hostname_prompted":"false"}' /api/settings` silently flipped the flag to True. Fix: explicit string-to-bool coercion accepting `true/1/yes/on` and `false/0/no/off/""`, rejecting other types.
- **`_start_when_ready` ignored download failures.** The 10-minute watcher polled `_is_final_present()` every 1s but never checked the download job's actual state. If the job moved to `failed`/`cancelled`, the watcher silently slept until deadline and the user sat on the wizard's 30-minute polling clock. Fix: also poll `list_models()`; on `failed`/`cancelled`, log + bail.
- **Recovery banner was OpenRouter-hardcoded.** Misleading for Anthropic-direct / OpenAI-direct / custom-provider users who could see "remote is back" when their actual provider was still down. Fix: probe OpenRouter, OpenAI, and Anthropic in turn; declare healthy if any responds (401/403 counts — network path works).

### Fixed (P2 — frontend polish, UX, edge cases)

- Reactive modal: `MODAL_DISMISSED` flag set on entry → moved to actual dismiss/success paths; added Escape-key close; tighter `_modalOpen` guard against rapid double-fire; `keydown` listener cleanup across all close paths.
- Recovery banner: kept polling forever after shown → exits when banner visible; resumes only on dismiss/switch.
- `apperror` SSE dispatch was inside the JSON.parse try block — malformed payloads (truncated stream, non-JSON frame) skipped the dispatch entirely. Fix: dispatch always fires; falls back to `{type:'unknown'}` if parse fails.
- Hostname prompt fired pre-Running. `Self.HostName` is populated long before `BackendState` reaches `Running`, so the prompt fired during `NeedsLogin` and users dismissed it ("why are you asking? I haven't connected yet"); since Skip persists `prompted=true`, they never got the prompt again. Fix: `hostname.py` exposes `backend_state` in the GET response; `hostname-prompt.js` gates on `backend_state === 'Running'`.
- Settings → Network tile didn't auto-refresh — 15s lightweight poll while visible.
- Saved Tailscale advanced settings didn't auto-apply — confirm prompt for inline reconnect.
- Wizard race: Next button enabled before probes returned — disabled "Detecting local options…" spinner until probes resolve.
- Indeterminate progress bar when `bytes_total` unknown — animated stripe instead of frozen 0%-fill.
- `install.sh` deadline-branch race in v0.4.5's bounded-poll fix — explicit `_ts_exit_reason` tracking; `set +e/-e` wrap on `_tailscale_backend_state` to survive transient docker-exec failures under `set -e`.
- `_TS_HOST_RE` allowed `/` in `exit_node` (copy-paste from URL regex); `tailscale serve --remove /` was invalid CLI syntax (replaced with `tailscale serve / off`); `_remote_health_cache` lockless across threads (added a `threading.Lock`).
- `completSetup` typo — renamed to `completeSetup`.

### Methodology

The owner asked for a diligent QA pass after noticing the prior PR test plans had been aspirational rather than executed. Per CLAUDE.md's Four Hats workflow:

1. **Architect** — scoped to "verify what's shipped + fix what's broken; no new features."
2. **Engineer** — 7 logical waves (A–G), one purpose per commit.
3. **Code Review** — 2 parallel QA reviewer agents on the original code (18 bugs found); 1 adversarial reviewer on the fixes themselves (12 more bugs found, including 2 P1 regressions of the fixes).
4. **QA** — built and ran a real Docker container on `port 8788` with a fresh data volume; ran end-to-end smoke matrix against actual `/api/*` endpoints with the real `tailscaled` and the validator/persistence layer. 17 of 17 corrected smoke-matrix items pass.

---

## [0.4.6] - 2026-05-05

Final v0.4.x release. Closes the loose ends on the local-AI fallback story (#9 polish) and the Tailscale Phase 2 power-user fields (#96 phase 2) — the last deliverables in the v0.4.x cadence before the strategic pause for v0.5 direction.

### Added

- **Tailscale power-user fields in Settings → Network → Advanced (#96 phase 2).** Surfaces the 6 flags that #96 Phase 1's argv builder already accepted but the UI didn't expose: login server (custom control plane / headscale), advertise routes (subnet-router CIDRs), advertise tags (ACL identity), exit node (route via tailnet peer), accept routes (consume peers' subnet routes), accept DNS (MagicDNS toggle, default on). Persistence via `settings.json`; `start_up()` merges body opts on top of persisted (body wins per-key, empty falls through). Closes Persona 3 of #96.

- **Reactive modal when remote provider fails and local fallback is OFF (#9 polish).** When a chat stream fails on a remote provider AND the user has not opted into local fallback, a one-time modal offers to enable it: *"Your provider is having trouble. Want to enable a local AI model as a fallback?"* Filters by error type — fires only for `stream_interrupted`, `rate_limit`, `no_response`, `unknown` (skips `auth_mismatch` / `model_not_found` / `quota_exhausted` since local can't fix those). One click → POST `/api/local-fallback/enable`, modal closes, the next remote failure silently uses local. The modal won't re-fire in the same session even if more errors arrive.

- **Recovery banner when local fallback is ON and remote is reachable again (#9 polish).** When local fallback is enabled, a top banner appears once `openrouter.ai/api/v1/models` becomes reachable from the container — *"Your remote provider looks reachable again. Switch off local fallback to use it?"* One click → POST `/api/local-fallback/disable`. Implementation: new `GET /api/local-fallback/remote-health` endpoint probes OpenRouter's public `/models` with a 5s timeout (30s in-process cache so multi-tab polling stays cheap); frontend polls every 90s only when `local_fallback_enabled === true`. Both modal and banner use `sessionStorage` flags so the UI doesn't pester — state resets on page reload.

### Architecture notes

- The reactive modal hooks into the `apperror` SSE event via a surgical one-line `window.dispatchEvent(new CustomEvent('fitb:stream-error', ...))` in `messages.js`. The polish module (`static/fallback-polish.js`) listens via the public `window` event — no monkey-patching of upstream code.
- The recovery banner intentionally probes a *generic remote-healthy* signal (OpenRouter's public `/models` endpoint) rather than per-provider probing. If that endpoint is up, the user has internet and the most common provider is reachable; their actual provider is *probably* up too. If not, the next chat will fail and the modal re-fires — self-healing UX.

### Why this is the last v0.4.x release

The v0.4.x cadence has shipped 7 releases in two days covering: local AI download manager (#10), local AI fallback runtime (#9), mid-stream error fix (#89), conversational onboarding without Ollama (#69), hostname post-wizard prompt (#68), Tailscale desktop auth (#96 phases 1–2), Linux install hang hotfix (#98), and #9 polish. Both pillars the README promised — local AI failover and Tailscale-from-anywhere — now actually deliver for desktop binary users.

Next release direction is intentionally paused per the user's "we will contemplate" framing. Three open buckets: v0.5 guardrails track (#4 spike → #5/#7/#8 → #6), #96 phase 3 (wizard step injection + reactive disconnected banner + Serve retry), revenue track (#91 LLM proxy → #90 hosted cloud).

---

## [0.4.5] - 2026-05-05

Hotfix release. P0 user report from a fresh Linux install: `install.sh` was hanging indefinitely after the Tailscale login URL displayed, even when the user successfully authenticated in the browser. Reported as #98.

### Fixed

- **`install.sh` no longer hangs forever after the Tailscale login URL is shown (#98).** Root cause: the script waited on the `tailscale up` background process via an unbounded `wait $FITB_TS_UP_PID`. `tailscale up --timeout=600` is supposed to exit after 10 minutes, but on Linux it doesn't always honor the flag when the daemon authenticates successfully but the WireGuard tunnel never reaches Running (firewall blocking outbound UDP, MTU mismatch, NAT-type incompatibility, SELinux/AppArmor restricting TUN access despite the `--device /dev/net/tun` grant). The fix replaces the unbounded `wait` with a bounded poll that:
  - Exits as soon as `BackendState == Running` is observed (typically within 5–30s of the user clicking through — actually faster than the original)
  - Exits if the bg process dies on its own (success or `--timeout` honored)
  - At a 15-minute hard deadline, sends SIGTERM, gives 2s grace, sends SIGKILL if still alive, surfaces actionable diagnostic hints (`tailscaled.err` location, common Linux causes, manual retry command), and proceeds to the existing `_tailscale_poll_until_running` which reports failure cleanly.
- The auth-key path is untouched — it's already bounded reliably by `tailscale up --timeout=600` because there's no browser-side wait involved.

### Why the issue is Linux-specific

macOS Docker Desktop runs everything inside its own VM with predictable networking; Linux Docker Engine inherits the host's network stack with all its weirdness. Some Linux distros also have SELinux/AppArmor profiles that subtly restrict TUN access even when `--device /dev/net/tun` is granted. The hang surfaces on Linux specifically.

---

## [0.4.4] - 2026-05-05

Closes the desktop-Tailscale gap. Until v0.4.3, the only way to authenticate Tailscale on a fresh install was either `install.sh` (Linux/macOS host-script users) or `docker exec` into the container manually. Windows .exe and macOS DMG users — the primary distribution path on the GitHub Release page — had no way to wire up Tailscale from inside the app despite the README explicitly promising *"Optional secure HTTPS access from your phone or another laptop via Tailscale"*. v0.4.4 closes both ends of this:

### Added

- **Tailscale connection panel in Settings (#96 phase 1).** New tile above the existing hostname tile, with status badge (Connected / Connecting / Needs login / Disconnected / Unknown), the tailnet HTTPS URL when connected, and Connect / Disconnect buttons. Clicking Connect spawns `tailscale up` in a daemon thread inside the container, scrapes the auth URL from stdout (handles both Tailscale-cloud and headscale-style URLs), and opens it in a new browser tab. The page polls `/api/tailscale/up/poll` every 2s; once `BackendState == Running`, the panel flips to Connected and Tailscale Serve auto-config (already wired in `entrypoint.sh:178`) publishes the HTTPS URL within ~10s.
  - Advanced accordion exposes an auth-key field — paste a reusable key from your tailnet admin console for unattended/non-interactive auth (no browser, succeeds in <30s).
  - The state machine is idempotent: clicking Connect twice doesn't double-spawn; it returns the in-flight `auth_url` instead.
  - Six new endpoints under `/api/tailscale/*` (status, up, up/poll, logout, serve get/post). The argv builder already accepts the full power-user flag set (`--login-server`, `--advertise-routes`, `--advertise-tags`, `--accept-routes`, `--accept-dns`, `--exit-node`, `--hostname`) — Phase 2 will surface these in the UI.
- **Hostname customization in onboarding (#68).** When the wizard finishes and the user lands in the chat UI for the first time, if Tailscale is running and `FOX_HOSTNAME` isn't set, a small modal pre-fills `fox-<adjective>` and lets the user pick a friendly name. Save uses #44's existing endpoint; Skip uses a new dismiss endpoint. Both persist `settings.json:hostname_prompted=true` so the modal never re-fires. Closes the AC-drift gap from #44 — the field shipped to Settings but most users never discovered it.
- **macOS access-mode chooser parity.** `ensureDockerAccessModeChosen()` now fires on macOS DMG first-runs (was Windows-only). DMG users can opt into Tailscale before container creation instead of being silently routed to the default mode.

### Why this matters for the README's headline promise

Top of README: *"Reachable from anywhere. Optional secure HTTPS access from your phone or another laptop via Tailscale."* Until today, that was true only for `install.sh` users. With v0.4.4, the promise extends to Release-page binary users on Windows and macOS — the primary distribution channel.

### Deferred to follow-up phases (#96)

- **Wizard step injection** during onboarding — Phase 2. Users currently auth from Settings → Network, which is one click away; less discoverable but functional.
- **Power-user fields in UI** (login-server, advertise-routes, advertise-tags, accept-routes, accept-dns, exit-node) — Phase 2. The backend already accepts them.
- **Reactive banner** in chat UI when access mode is Tailscale but state is Disconnected — Phase 3.
- **Serve retry button** for the case where entrypoint.sh's auto-config failed — Phase 3.

### Tracked separately

- **#9 polish** (reactive modal for non-opted-in users on first remote failure, recovery banner when remote is back) was the original v0.4.4 partner for #68; it was swapped for #96 phase 1 after the Tailscale gap surfaced. Will land in a later v0.4.x release.
- **#98** — install.sh hangs on Linux after the Tailscale login URL displays. Filed as P0; v0.4.5 hotfix in flight.

---

## [0.4.3] - 2026-05-05

Onboarding wizard now offers the bundled local model when no Ollama daemon is detected. Closes the gap from v0.3.0's "Option B" closure, where the welcome step had a fast-path for Ollama users only — leaving everyone else with no choice but OpenRouter. With v0.4.0's download manager and v0.4.1's local-fallback runtime in place, the wizard can finally run end-to-end on a user's hardware with no API key.

### Added

- **Bundled-llama.cpp fast-path on the welcome step (#69).** When the wizard detects no host-side Ollama, it probes `/api/local-fallback/status` and offers Phi-4-mini directly:
  - **Already on disk** → instant "Use bundled local model" CTA, no download.
  - **Not yet on disk** → "Download & use local model (~2.5 GB)" CTA. Click triggers `/api/local-fallback/enable` (toggles the flag, kicks the download via #10's manager, and queues llama-server start once the file lands). The welcome step swaps to a progress panel with a live MB / total counter and percentage bar; the user can close the window — the download keeps running on the server side.
  - **Outside the supervisord-managed container** (`ui_state: no-supervisor`) → CTA hidden; only OpenRouter and the skip footer show.
- Priority order on step 1 is now: Ollama detected → bundled llama.cpp ready → bundled llama.cpp installable → no local CTA. OpenRouter remains available on every branch via the existing **Next** button.

### Why this matters

Before v0.4.3, the only way to onboard without an API key was to (a) install Ollama on the host beforehand, or (b) skip the wizard and configure local fallback manually from Settings → Providers. (b) required knowledge most users don't have. v0.4.3 closes that loop: a user with no Ollama, no API key, and no prior knowledge of the local-fallback feature now has a one-click path to a working chat against an on-device model.

---

## [0.4.2] - 2026-05-05

Bug-fix release. When a remote provider closed the connection mid-stream — rate limit hit during streaming, gateway timeout, network reset after the first token — the user saw their partial response and then nothing. Spinner disappeared with no error, no recovery hint. The app appeared silently broken. v0.4.2 surfaces the failure clearly and preserves the partial response across page reload.

### Fixed

- **Mid-stream gateway errors no longer leave messages unanswered (#89).** The silent-failure detector in `streaming.py` was gated on `not _token_sent` to avoid false-firing on tool-call-only completions. Side effect: when tokens HAD started streaming and then the provider dropped the connection without re-raising (the agent's internal handler swallowed the failure), neither the silent-failure path nor the outer exception handler caught it. Result: the user's chat looked broken with no explanation. Fix:
  - Drop the `_token_sent=False` gate. The right condition is `not _assistant_added` — if no completed assistant message landed, the user needs feedback regardless of partial token streaming.
  - Branch on `_token_sent` for the error label: when tokens streamed → **"Stream interrupted"** (with the underlying error), when none did → existing **"No response received"**. The latter was misleading when half a response was already on screen.
  - Preserve `STREAM_PARTIAL_TEXT` in the persisted assistant message: `<partial>\n\n*[Stream interrupted: <label> — <error>]*`. Page reload no longer erases what the user already saw — the partial response stays visible with a clear marker that the stream broke.
  - Symmetric fix in the outer exception handler (`streaming.py:~2440`) — when a provider error IS raised mid-stream, the persisted message also includes the partial.
  - Frontend: new `stream_interrupted` type recognized by the apperror SSE handler so the live error bubble label reads cleanly.

### Why this isn't covered by v0.4.1's local fallback (#9)

#9 silently retries opted-in users' transient failures on the local model. That handles the **opted-in user with a downloaded local model** case. #89 is the broader case: a user without local fallback (or who hadn't opted in) still gets clear error feedback rather than silence. The two fixes are complementary.

### Closes

- **#89** — Gateway errors mid-chat leave messages unanswered with no error shown

[0.4.2]: https://github.com/fox-in-the-box-ai/fox-in-the-box/releases/tag/v0.4.2

## [0.4.1] - 2026-05-05

The local-AI fallback experience now actually works end-to-end. v0.4.0 shipped the download infrastructure; v0.4.1 ships the runtime that consumes it. Enable a single Settings toggle, wait for the one-time 2.5 GB download, and your chat keeps working when your remote provider is rate-limited or unreachable. Silent failover, no chat interruption.

### Added

- **Local AI fallback runtime (#9).** New tile in **Settings → Providers** ("Local fallback"). Toggle ON triggers v0.4.0's download manager (Phi-4-mini Q4_K_M, ~2.5 GB, sha256-pinned), and once the file lands, supervisord starts the bundled `llama-server`. The Settings tile shows live status: `Off` / `Will start downloading…` / `Downloading 1.2 GB / 2.5 GB (48%)` / `Starting llama-server…` / `Ready — your provider failures will silently retry on the local model.`
- **Silent failover.** When the user is opted in and a remote-provider call hits a transient failure (5xx, 429, connection drop), the existing agent-level retry path is plumbed at the local model. No modal, no chat interruption — the conversation continues. The retry classifier never fails over on auth/quota/billing/model-not-found errors (those are config errors that need to surface to the user, not be masked by a local model).
- **Bundled `llama.cpp` (b9026), per-arch.** Pre-built CPU binaries pulled into the image at build time via the same `TARGETARCH` switch the Qdrant build uses (#82's multi-arch pipeline keeps both x64 and arm64 builds covered). Supervised by supervisord with `--sleep-idle-seconds 60` — process stays up so failover is fast, weights unload after 60 s of no requests so RAM cost is ~50 MB at idle (vs ~3.5 GB while serving).

### Changed

- **`/api/local-fallback/{status,enable,disable}`** new endpoints exposing the orchestration above.
- **`settings.json` schema** gains `local_fallback_enabled` (bool, default `false`). Persisted via the existing `_SETTINGS_DEFAULTS` + `_SETTINGS_BOOL_KEYS` allowlist.
- **`packages/integration/Dockerfile`** installs `libgomp1` + `libcurl4` (~550 KB total) for the `llama-server` runtime.
- **`packages/integration/supervisord.conf`** gains `[program:llama-server]` with `autostart=false` — zero idle RAM cost when a user hasn't opted into local fallback.

### Caveats

- **First-run download is ~2.5 GB.** Honestly displayed in the toggle copy. Users on slow connections will wait. The download persists on `/data/models/` across container restarts; second-run is instant.
- **Reactive modal not yet shipped.** When a remote-provider call fails and the user *hasn't* opted in, today they see the existing remote error. v0.4.2 will add a one-time "Try local model? (downloads ~2.5 GB once)" prompt with a "Always do this" checkbox.
- **No recovery banner yet.** When the remote provider comes back, the user stays on the local model until they manually toggle off. v0.4.2 polish will add a passive "Remote is back — switch?" banner.

### Closes

- **#9** — local CPU fallback model (the original "provider outage handling" issue from the v0.1 backlog)

[0.4.1]: https://github.com/fox-in-the-box-ai/fox-in-the-box/releases/tag/v0.4.1

## [0.4.0] - 2026-05-05

The first of three v0.4.x releases on the path to fully-offline-capable Fox. This one ships the **local-model download engine** (#10) — server-side, resumable, sha256-verified GGUF downloads. Phi-4-mini Q4_K_M is the first registered model; v0.4.1 will add the llama.cpp runtime that consumes it (#9), and v0.4.2 wires conversational onboarding through the same path (#69).

Also includes the **multi-arch container image** (#82, P0) that landed earlier today — `:latest` and `:stable` are now manifest lists with `linux/amd64` and `linux/arm64` child images. arm64 hosts (Raspberry Pi, AWS Graviton, Apple Silicon Linux VMs) pull native binaries; no QEMU emulation, no platform-mismatch warning.

### Added

- **Local model download manager (#10).** Settings → System → "Local AI models" lists registered models with their on-disk status, expected size, and a single context-sensitive button (Download / Cancel / Delete). Downloads are server-side: closing the browser tab doesn't interrupt the download — re-opening Settings picks up the live progress. Resumes across container restarts because the partial file lives on the `/data` volume. New REST surface: `GET /api/local-models`, `POST /api/local-models/<id>/download`, `POST /api/local-models/<id>/cancel`, `POST /api/local-models/<id>/delete`, `GET /api/local-models/<id>/progress` (SSE). Distinct from the existing `/api/models` chat-input picker — no collision.

- **Phi-4-mini Q4_K_M registered as the first downloadable model.** 2.49 GB, sha256-pinned (`01999f17c39cc307…`), sourced from `bartowski/microsoft_Phi-4-mini-instruct-GGUF`. The URL, sha256, and size are all `MODEL_*_PHI4MINI` env-overridable so we can flip to a mirror without a code release if HuggingFace ever has an outage. The model isn't *used* anywhere yet — that's #9 in v0.4.1.

- **Multi-arch container image (#82, P0).** Cross-runner build pattern: native amd64 on `ubuntu-latest`, native arm64 on `ubuntu-24.04-arm` (GitHub-hosted, free for public repos). Per-platform digests are pushed to GHCR by digest, then assembled into a manifest list via `docker buildx imagetools create`. Verify-both-arches step fails the build hard if either platform's manifest is missing — won't let a single-platform image ship as `:latest`. Per-platform GHA cache scopes (`cloud-amd64`, `cloud-arm64`) prevent cross-arch layer contamination. Smoke test runs on each native runner: pulls by index digest, asserts the registry auto-selected the matching child manifest, validates `/health` returns 200 **and** body contains `"status": "ok"` (per #57's lesson).

### Changed

- **`release.yml` retag step now uses `docker buildx imagetools create`** instead of `docker pull && docker tag && docker push`. The old pattern collapsed a manifest list to a single-platform image because the pull only fetched the runner's child manifest — multi-arch users would have silently lost arm64 on every tagged release. The new pattern operates registry-side and preserves the full manifest list. Defense-in-depth verify step in `release.yml` fails the release loudly if either `:vX.Y.Z` or `:stable` ends up missing a platform.

### Integrity & verification

- All four diligence checks built into CI: manifest-list verify, index-digest pull arch verification, distinct cache scopes, body-shape validation on `/health`. Verified end-to-end on PR #83 (5/5 checks green) and on PR #84.

### Caveats

- Phi-4-mini downloads as soon as the user clicks Download in Settings, but **there's no way to use it yet**. v0.4.1 (#9) adds the llama.cpp runtime + Settings → Providers "Local fallback" toggle that makes the model serve chat traffic. Power users who want to pre-stage the model can do so today; everyone else can ignore the new section until v0.4.1 lands.

[0.4.0]: https://github.com/fox-in-the-box-ai/fox-in-the-box/releases/tag/v0.4.0

## [0.3.1] - 2026-05-05

Fully closes the local-Ollama integration that started in v0.3.0. Users with Ollama installed can now pull and delete models from inside the WebUI — no terminal step at any point in the flow. The 2-minute first-chat goal from #66 is now actually reachable: install Ollama, open Fox, click a recommended model, chat.

### Added

- **Pull Ollama models from inside Fox.** New **Settings → Providers → Local Ollama** controls:
  - **Recommended-models card** when zero models are installed: one-click pull buttons for `llama3.1:8b`, `mistral:7b`, `phi4-mini`, `deepseek-coder-v2:16b`
  - **Pull form** with a free-form input plus a curated `<datalist>` of suggestions (the four above plus `gemma3:4b` and `qwen3:4b`). Browse-all link to ollama.com/library
  - **Live progress block** during a pull: percentage bar, current/total bytes, instantaneous speed (rolling 4-sample window), ETA. After completion the model immediately appears in the list (cache invalidation)
  - Server-side allowlist regex on model names (`^[A-Za-z0-9._:/-]+$`, ≤200 chars) — defense-in-depth against shell-injection-via-config

- **Delete Ollama models from inside Fox.** Per-row Delete button next to the existing Use button. Confirmation dialog includes the freed-space estimate; success toast reports the actual freed bytes returned by Ollama. Model list refreshes after delete so the row disappears and the disk-usage indicator decreases.

- **Total-disk indicator.** Local Ollama tile header now shows total bytes across installed models.

### API

- New `POST /api/ollama/pull` — SSE-proxied stream of Ollama's NDJSON `/api/pull` progress. Three event types: `progress`, `done`, `error`. Errors include validation, daemon-not-running, mid-stream Ollama errors, network drop. Client-disconnect mid-pull doesn't kill the underlying Ollama pull (Ollama keeps fetching in the background by design).
- New `POST /api/ollama/delete` — wraps Ollama's `DELETE /api/delete`. Returns `{ok, freed_bytes}` on success or `{ok: false, error}` on failure (404 surfaced as "Model not installed: \<name\>").
- `GET /api/ollama/models` now returns `total_size_bytes` for the disk-usage indicator.

### Why `POST /api/ollama/delete` instead of `DELETE`

hermes-webui's request dispatcher routes only `GET` and `POST` at the framework level. Adding DELETE-method support would require server.py changes outside this fix's scope. POST symmetry with the rest of the Ollama endpoints is the cleaner local minimum.

### Closes

- #67 — Ollama Phase 3: pull / delete model management UI
- The remaining acceptance criteria from #66 that hadn't shipped in v0.3.0 (zero-terminal flow, 2-minute first-chat for non-technical users with Ollama)

[0.3.1]: https://github.com/fox-in-the-box-ai/fox-in-the-box/releases/tag/v0.3.1

## [0.3.0] - 2026-05-05

The "Smoother onboarding + first taste of local" release. Clears both of v0.2.0's "Coming soon" promises and adds first-class local Ollama support so users with Ollama already installed can chat without an API key, without a terminal, without a custom-endpoint config.

### Added

- **First-class local Ollama integration.** Settings → Providers gets a new **Local Ollama** tile that auto-detects a host-side Ollama daemon (probing `host.docker.internal:11434` then `localhost:11434`, 10s cache), lists installed models from `/api/tags` with parameter size, quantization, and disk size, and offers a one-click **"Use"** button per model. Picking a model writes `model.{provider:custom, base_url, name}` into `config.yaml` and triggers the gateway hot-reload pattern from v0.2.0 — no API key, no terminal, no manual configuration. Routes through Hermes Agent's existing custom OpenAI-compat endpoint path; no agent-side changes. Closes #66 (phases 1 and 2; phase 3 — pull/delete model UI — tracked as #67 for v0.3.1).

- **Local Ollama fast-path on the onboarding wizard.** When a host-side Ollama daemon is detected with at least one model installed, the wizard's Welcome step surfaces a green-bordered "Local model detected" panel with a **"Use <model name>"** CTA. Click → activates the model server-side → marks onboarding complete → drops the user straight into chat. No API key step. Falls back to the existing OpenRouter wizard when Ollama isn't detected. Part of #11.

- **Skip CTA on every onboarding step.** `POST /api/setup/skip` marks onboarding complete without collecting an API key — exit hatch for users who'll configure providers later from Settings, or who already have keys persisted from a prior install. Closes the "User can skip onboarding entirely" AC of #11.

- **Externalized onboarding welcome text.** The wizard's Welcome paragraph(s) are now read from `/data/config/onboarding.md` (default copy ships from the container's defaults sweep). Edit the file in place to customize the greeting per install. New `GET /api/setup/welcome` endpoint serves the content. Closes the "Script is externalized" AC of #11.

- **Tailscale device hostname customization in Settings.** A new **Device name (Tailscale)** field in Settings → System lets desktop-app users pick a friendly name for their Fox on their tailnet — no longer stuck with Tailscale's auto-generated `ip-x-x-x-x` hostnames in the HTTPS URL Tailscale Serve publishes. The field defaults to a `fox-<adjective>` from the same curated list `install.sh` uses (parity with the v0.1.3 shell-install fix from #3). Persists `FOX_HOSTNAME` to `/data/config/hermes.env` and applies live via `tailscale set --hostname=<sanitized>` against the running daemon — surgical `EditPrefs` mutation, not the full-preferences-reset risk of `tailscale up`. After applying, re-reads `tailscale status --json` and surfaces any collision suffix the control plane appended. If the daemon isn't running or authenticated yet (common at first run), the persist is a soft-success — the value applies on the next daemon start. Closes #44. Wizard-step refinement tracked separately as #68.

- **Linux Docker host networking.** `packages/electron/src/docker-manager.js` (Dockerode `HostConfig.ExtraHosts`) and `packages/scripts/install.sh` now add `--add-host=host.docker.internal:host-gateway` so the local-Ollama probe (and any future host-reaching code) works on Linux Docker Engine 20.10+. macOS / Windows Docker Desktop resolves this name natively; Linux Engine takes `host-gateway` as a placeholder for the host's gateway address.

### Fixed

- **Onboarding state drift.** `onboarding.json:completed` and `settings.json:onboarding_completed` were two unsynchronized flags — the redirect middleware read only the first, and any code path flipping the second was silently ignored. `/api/setup/{complete,skip}` now write both, and `onboarding_complete()` reads either. Future CLI / direct-config bootstrappers can flip either flag and the redirect agrees.

### Caveats

- **Local Ollama on existing v0.2.x containers.** The Linux `--add-host` flag was added to the container creation flow in this release. Containers created before v0.3.0 don't have it — the Local Ollama tile will show "Not detected" on Linux until the container is re-created. macOS / Windows Docker Desktop is unaffected. Surfaced inline in the Local Ollama tile's not-detected copy.

- **Live Tailscale hostname mutation requires an authenticated daemon.** If you set the device name before authenticating Tailscale (or with the daemon stopped), the value still persists to `hermes.env` and applies on the next daemon start. The Settings UI surfaces this distinction in its status line.

[0.3.0]: https://github.com/fox-in-the-box-ai/fox-in-the-box/releases/tag/v0.3.0

## [0.2.0] - 2026-05-04

The "App works out of the box" release. The first-launch flow now closes itself when services are healthy, post-onboarding key changes take effect without a container restart, and the release pipeline pins images by content digest so a tagged version is reproducible.

### Fixed

- **Setup window stuck at Step 5/6 — Wait for services.** The Electron `/health` probe in `packages/electron/src/health-check.js` accepted any HTTP 200 and discarded the body, while the in-container probe (`forks/hermes-webui/bootstrap.py:wait_for_health`) requires the body to contain `"status": "ok"`. Same endpoint, two different success criteria — and when those gates disagreed, the setup window hung at 5/6 even when curl returned a healthy response. Polling now reads the body (4KB cap) and requires both the 200 and the marker. Closes #57 (also closed #56 as a duplicate).

### Added

- **Provider keys can be added or changed after onboarding.** Users can now open Settings → Providers from the chat (gear icon → Settings → Providers tab) to add or remove API keys for Anthropic, OpenAI, OpenRouter, DeepSeek, and other supported providers. The change takes effect within seconds — no container restart needed. Two coordinated fixes:
  - `packages/integration/scripts/run-with-env.sh` now sources `$HOME/.hermes/.env` in addition to `/data/config/hermes.env`. The wizard writes to the first; Settings writes to the second; the wrapper sources both so either path's keys end up in the gateway's process env.
  - `forks/hermes-webui` (now at `98eb7d9`) — `api/providers.py:set_provider_key` best-effort calls `supervisorctl restart hermes-gateway` after writing the env file. No-op outside supervisor-managed deployments. Closes #13.

### Changed

- **Release pipeline pins the container image by content digest.** `release.yml` previously did `docker pull :latest && docker tag :vX.Y.Z`. A concurrent push to `main` between `wait-for-container`'s push and this pull could mutate `:latest`, leaving the released `:vX.Y.Z` / `:stable` tags pointing at a different commit's image than the tagged one. `build-container.yml` now exposes the pushed image's content digest as a `workflow_call` output, and `release.yml` pulls / retags `name@sha256:...` so the released image is verifiably the one this run produced. Fails fast if the digest is missing. Closes #41 (and #43, which described the same race from a different angle — the digest pin makes the prescribed `tags:` trigger redundant; adding that trigger would create the duplicate parallel build pattern that broke v0.1.1's Windows asset upload).

- **CI: documented why Windows installs Electron deps with `npm`, not `pnpm`.** `build-electron.yml` uses `npm install` on Windows runners while macOS/Linux use `pnpm install --frozen-lockfile` at the workspace root. The divergence is load-bearing: pnpm's content-addressed store nests deps under `node_modules/.pnpm/<name>@<ver>_<longhash>/...` which exceeds Windows MAX_PATH (260) for makensis.exe's NSIS include resolver. The earlier attempt with `--shamefully-hoist` (4510cc5) still produced unreachable include paths, and `cache: "pnpm"` for setup-node was likewise removed (4550e94) because the cache path doesn't exist when npm is used. Added an inline comment so the next person doesn't try to "fix" it back to pnpm and break Windows installer builds. Closes #42.

[0.2.0]: https://github.com/fox-in-the-box-ai/fox-in-the-box/releases/tag/v0.2.0

## [0.1.6] - 2026-05-04

This is the actual ship of the signed Windows installer that v0.1.4 and v0.1.5 attempted. Both prior tags are orphans — neither has a published GitHub Release. The chain of failures and what unblocked them:

- **v0.1.4** failed because `release.yml`'s caller didn't grant `id-token: write` to the `wait-for-electron` job; the called workflow's permissions inherit from the caller, not from its own declaration. Fixed in #52.
- **v0.1.5** failed because the Azure federated credential was set up with subject `repo:.../ref:refs/tags/v*` — the asterisk is treated as a literal string, not a wildcard. Microsoft's standard FICs don't support pattern matching on tag names by design.

### Added

- Windows installer (`fox-in-the-box-setup-x64.exe`) is now signed with Azure Trusted Signing under the Icemint LLC certificate profile (`fitb-exe-signing`). Microsoft Defender SmartScreen no longer blocks first launch with the "Windows protected your PC" dialog. (Originally targeted v0.1.4.)

### Changed

- Windows signing now uses GitHub Environment-bound federated credentials (subject `repo:.../environment:release`) instead of tag-pattern matching. Microsoft's recommended pattern for "many tags" releases — independent of the tag name, so every future release works without per-tag Azure setup. `build-electron.yml` accepts a `signing-environment` workflow_call input; `release.yml` passes `release`. Push-to-main and `workflow_dispatch` builds skip Azure login + signing entirely (no auth attempt, faster CI).

[0.1.6]: https://github.com/fox-in-the-box-ai/fox-in-the-box/releases/tag/v0.1.6

## [0.1.5] - 2026-05-04

This is the actual ship of the v0.1.4 work. The v0.1.4 tag exists in the repo but has no GitHub Release: when `release.yml` called `build-electron.yml` for that tag, GitHub's workflow validation rejected the call with `"requesting 'id-token: write', but is only allowed 'id-token: none'"`. The OIDC permission was declared at the called workflow's level but not granted at the calling job's `permissions:` block, so it defaulted to `none` and signing never ran.

### Added

- Windows installer (`fox-in-the-box-setup-x64.exe`) is now signed with Azure Trusted Signing under the Icemint LLC certificate profile. Microsoft Defender SmartScreen no longer blocks first launch with the "Windows protected your PC" dialog. (Originally targeted v0.1.4.)

### Fixed

- `release.yml`'s `wait-for-electron` job now grants `id-token: write`, allowing the called `build-electron.yml` to request the OIDC token needed by `azure/login@v2` and the Trusted Signing action when the workflow runs in `workflow_call` context.

[0.1.5]: https://github.com/fox-in-the-box-ai/fox-in-the-box/releases/tag/v0.1.5

## [0.1.4] - 2026-05-04

### Added

- Windows installer (`fox-in-the-box-setup-x64.exe`) is now signed with Azure Trusted Signing under the Icemint LLC certificate profile. Microsoft Defender SmartScreen no longer blocks first launch with the "Windows protected your PC" dialog.

[0.1.4]: https://github.com/fox-in-the-box-ai/fox-in-the-box/releases/tag/v0.1.4

## [0.1.3] - 2026-05-04

### Fixed

- Chat input's model dropdown now refreshes immediately after a provider key is saved or removed in Settings → Providers. Previously, adding an Anthropic (or other non-OpenRouter) key would update the server's model cache but leave the chat dropdown stale — users had to reload the page, and many didn't realize they needed to. Affected anyone routing through a provider added post-onboarding (#37).

### Added

- Tailscale device hostname is now configurable during install. `packages/scripts/install.sh` prompts for a name when Tailscale is part of the chosen access mode, defaulting to `fox-<adjective>` from a curated list (e.g. `fox-quick`, `fox-clever`). Honors `FOX_HOSTNAME` env var for non-interactive installs. Inputs are sanitized to lowercase letters/digits/hyphens, max 63 chars (#3).
- README rewritten for clarity: Windows and macOS desktop downloads are now the first install options (with the actual `.exe` and `.dmg` filenames), features described in plain language, and new FAQ / Support / Acknowledgments sections. Reset / clean-install procedures moved out to `docs/RESET.md` (#40).

### Changed

- README accuracy fixes: removed the incorrect "no signed macOS .dmg in releases" line — we ship signed and notarized DMGs (arm64 + x64) since v0.1.0.

[0.1.3]: https://github.com/fox-in-the-box-ai/fox-in-the-box/releases/tag/v0.1.3

## [0.1.2] - 2026-05-04

### Fixed

- Windows `.exe` now reliably ships with every release. The previous pipeline ran `build-electron.yml` twice on every tag push (once via the `tags:` trigger, once via `release.yml`'s `workflow_call`), causing concurrent uploaders to race on the same GitHub Release. The Windows asset lost the race and was dropped from v0.1.1.

### Changed

- Single-source-of-truth release uploads. `release.yml` is now the only workflow that writes assets to a GitHub Release. `build-electron.yml` only produces GitHub Actions artifacts; `release.yml` downloads them and publishes atomically.
- `release.yml` now refuses to publish a release with an empty body — fails fast if `CHANGELOG.md` has no matching version section.
- `release.yml` sets `fail_on_unmatched_files: true` so a missing artifact glob is a hard failure, not a silent success.
- `release.yml` runs in a `release-${{ github.ref }}` concurrency group so re-runs of the same tag never race themselves.

[0.1.2]: https://github.com/fox-in-the-box-ai/fox-in-the-box/releases/tag/v0.1.2

## [0.1.1] - 2026-05-04

### Fixed

- First-run chat unusable due to missing onboarding endpoint — wizard now writes the OpenRouter API key to `hermes.env` and marks onboarding complete (#28, #34)
- Wizard "Open Fox" button now actually applies the new key without a container restart — `hermes-gateway` and `hermes-webui` are wrapped in a script that re-sources `hermes.env` on every supervisord restart (#35)
- Product name now consistently rendered as "Fox in the Box" across the UI

### Added

- Manual `workflow_dispatch` trigger on `build-electron.yml` for on-demand smoke testing of Windows and macOS builds (#25)

[0.1.1]: https://github.com/fox-in-the-box-ai/fox-in-the-box/releases/tag/v0.1.1

## [0.1.0] - 2026-05-04

### Added

- Signed macOS DMG build in the Electron CI pipeline (#31)
- macOS DMG and ZIP artifacts included in GitHub Releases alongside Windows installer (#32)

### Fixed

- macOS notarization: `APPLE_TEAM_ID` is now passed explicitly to `@electron/notarize` instead of relying on env-var forwarding (#33)

[0.1.0]: https://github.com/fox-in-the-box-ai/fox-in-the-box/releases/tag/v0.1.0

## [0.0.2] - 2026-05-04

### Fixed

- Mobile: titlebar now visible for safe-area spacing; inner content hidden and border removed on narrow viewports
- Submodule sync: hermes-webui and hermes-agent now auto-synced to latest on every upstream commit

[0.0.2]: https://github.com/fox-in-the-box-ai/fox-in-the-box/releases/tag/v0.0.2

## [0.0.1] - 2026-05-04

Initial public release.

### Added

- Single Docker container bundling Hermes Agent, Hermes WebUI, mem0\_oss, Qdrant, Tailscale, and supervisord
- Browser-based onboarding wizard at `/setup` — enter your OpenRouter API key and Tailscale auth token with no terminal required
- Brave Search MCP integration available out of the box
- Persistent memory across sessions via local Qdrant vector store
- Automatic HTTPS and remote access via Tailscale Serve
- Electron desktop app for Windows (.exe installer) and macOS (.zip)
- Linux and macOS shell install scripts
- GitHub Actions CI/CD: container build to GHCR, Electron builds for Windows and macOS
- Data directory structure at `~/.foxinthebox` with `config/`, `data/`, and `cache/` separation
- MIT license

[0.0.1]: https://github.com/fox-in-the-box-ai/fox-in-the-box/releases/tag/v0.0.1
