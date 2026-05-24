# Changelog

All notable changes to Fox in the Box are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.7.26] - 2026-05-24

**Windows installer: mode selection + branding + uninstall cleanup (#353, #323, #346).**

### Added

- **#353 / #346 Install mode selection.** When Fox is already installed, the installer now shows a dialog with two options: "Express upgrade — keep my data, conversations, and AI models" (default) or "Clean install — remove everything and start fresh." Clean install stops and removes the container + image + `%APPDATA%\fox-in-the-box` before copying new files. No more manual PowerShell cleanup before a fresh reinstall.
- **#353 / #346 Uninstall data cleanup.** The uninstaller now asks "Also remove Fox data, conversations, and AI models?" with a default of **No** — so a normal uninstall preserves data for reinstall, but users who want a complete clean-sheet can opt in.
- **#323 Installer branding.** NSIS wizard chrome now shows a navy + gold header (150×57) and sidebar (164×314) matching the Fox dark palette instead of the generic Windows installer chrome. `oneClick: false` enables the wizard UI.

### What's next

- **v0.7.27:** #336 local fallback root cause (unblocked once Stan provides docker logs) + next issue batch.

---

## [0.7.25] - 2026-05-24

**Network access dialog rewritten for non-technical users (#357).**

### Changed

- **#357 Network access dialog copy.** Replaced jargon-heavy installer copy ("bind 8787 on all interfaces", "Tailscale inside the container") with plain language. "Tailscale only" is now "This PC + other devices (Tailscale)" with a one-liner: "Tailscale connects your devices together so you can open Fox from anywhere on your personal network. Free, no subscription." The three button labels are now "This PC only", "This PC + other devices (Tailscale)", "Both".

### What's next

- **v0.7.26:** #353 NVidia-style installer modes (Express / Clean Install / Uninstall-with-cleanup) + #323 Windows installer design system styling.

---

## [0.7.24] - 2026-05-24

**Tailscale URL surfaced after startup (#358) + Fox WebUI branding.**

### Fixed

- **#358 Tailscale URL not shown after container start.** When access mode is "Tailscale only" (mode 2) or "Both" (mode 3), the app now polls `/api/tailscale/status` for up to 30s after the container is healthy, then shows a dialog with the local URL and the Tailscale HTTPS URL before opening the browser. A "Copy Tailscale URL" button is included. If Tailscale isn't connected within 30s, the app opens normally without blocking. Reported by @bsgdigital.

### What's next

- **v0.7.25:** Next issue batch — #336 (local fallback root cause), #323 (Windows installer styling), and others.

---

## [0.7.23] - 2026-05-24

**Fox branding lands in the WebUI + provider card styling consistency.** The bot name, assistant avatar, and empty-state copy now read "Fox in the Box" instead of upstream's "Hermes" defaults. Provider card buttons in Settings also inherit the Fox design tokens.

### Added

- **Fox bot name (#360).** Chat messages from the assistant now show "Fox in the box" instead of "Hermes". Patch 004 in the webui series overrides `window._botName` at runtime, keyed on the `.fox-in-the-box` class now injected by `fox-overlay.js`.
- **Fox avatar in chat (#360).** Assistant messages show the Fox avatar image instead of the "H" initial-letter circle. Patch 005 fixes the asset path (`/extensions/fox_avatar_cropped.jpg`) that was wrong in the original PR #327.
- **Fox empty-state branding (#360).** The empty chat screen now reads "Think less. Start here." with Fox-tone suggestion copy. Patch 006.
- **`.fox-in-the-box` class trigger.** `fox-overlay.js` now sets `document.documentElement.classList.add('fox-in-the-box')` on load — the missing wire that activates all class-conditional CSS and JS.

### Fixed

- **#279 Provider card button/input font consistency.** `provider-card-btn` and `provider-card-input` elements in Settings now inherit Manrope font and Fox border-radius tokens instead of defaulting to browser defaults.

### What's next

- **v0.7.24:** #358 Tailscale URL surfaced after container start + next issue batch.

---

## [0.7.22] - 2026-05-24

**Wizard styling parity with Hermes WebUI.** The setup wizard now uses the same navy + gold dark palette and Sora/Manrope typography as the main chat UI, addressing Stan's feedback that onboarding felt disconnected from the app it leads into.

### Changed

- **Setup wizard reskinned to Hermes upstream dark palette (#364).** Replaced standalone zinc/orange color scheme (`#0e0e10` bg, `#f97316` accent) with Hermes dark-mode tokens (navy `#0D0D1A`, gold `#FFD700`, surface `#1A1A2E`). Added Sora variable font for headings and Manrope for body text. Ollama detection box now uses `#4DD0E1` (Hermes `--info`) instead of the non-standard teal. Pure CSS change — no layout, HTML, or JS modifications.

### What's next

- **v0.7.23:** #362 interactive install UX overhaul (Apple-polish step states + retry buttons) + #353 NVidia-style installer modes.
- **v0.7.23+ also:** #365 test-infrastructure hooks (`/test/seed-provider` + `/test/skip-onboarding` + `/test/inject-failure`) unblocks 5 currently-skipped Playwright specs.

---

## [0.7.21] - 2026-05-24

**Tooling cleanup + Playwright net + one onboarding-redirect whitelist tweak.** The patch-system hygiene work the v0.7.15 audit recommended finally lands. `check-overlay-basis.sh` stops silently destroying submodule work-in-progress; it now also catches the v0.7.13 #331 failure mode at commit-time (orphan patches sitting in directory but missing from series). `regen-patch.sh` (broken-on-arrival since v0.7.14 — had a `# Wait that's not right. Let me redo:` comment shipped to main) is rewritten to actually work. Plus folds in the Playwright model-picker coverage agent 1 wrote during the v0.7.20 session, and adds `/api/models` to the patch-003 whitelist so the new specs can reach it on fresh containers (same shape as v0.7.17's `/test/` whitelist).

### Fixed

- **`check-overlay-basis.sh` stash leak.** The script's `git stash --include-untracked` was never popped; subsequent `git reset --hard` + `git clean -fdx` destroyed the working tree, orphaning the stash forever. On CI runners (always fresh checkout) this was a no-op. For local dev runs, it silently destroyed submodule work-in-progress. Now: refuse-if-dirty preflight checks `git status --porcelain` on each submodule, bails with exit code 2 + a clear "fix your state explicitly" message if anything's modified.
- **`regen-patch.sh` rewrite.** The v0.7.14 ship had two competing diff blocks fighting each other (the second one `cp -r snapshot/* .`'d the dev's edits with the snapshot BEFORE computing the diff → output always empty). New version uses git itself as the diff engine: commit baseline → drop into dev shell → `git diff HEAD` after shell exits → reset to pristine. Trap-based cleanup so even an error mid-write leaves the submodule clean.

### Added

- **Orphan-patch detection in `check-overlay-basis.sh`.** Every `.patch` file in `patches/{webui,agent}/` MUST appear in its `series` file. v0.7.13 #331 root cause: `003-server-py-onboarding-redirect.patch` existed in the directory from v0.7.13 onwards but wasn't added to series until v0.7.15 — for 2 releases the onboarding-redirect fix shipped broken because the Dockerfile only iterates the series file, not the directory. New check uses `comm -23` between sorted directory contents and series entries; any orphan fails with a clear "add to series or delete" message.
- **`qa/playwright/tests/smoke/model-picker.spec.ts`** (5 specs from agent 1's `qa/playwright-model-picker-coverage` branch — folded in). 2 live (`#337` Ollama tile always present + install-hint copy) + 3 `describe.skip` for now (`#344` no-providers, `#344` with-provider, `#278` Ollama dedup — fixes shipped v0.7.20 but tests need `/test/seed-provider` + `/test/skip-onboarding` hooks documented in **#365**).

### Changed

- **`wizard-local-fallback.spec.ts` skip comments updated** to reflect v0.7.20 tactical-fix-shipped + failure-injection-hook-needed status. Same unskip target as the model-picker specs: when #365 lands the test harness.
- **`/api/models` added to `_SETUP_PREFIXES` whitelist** in `packages/fox-overlay/fox_overlay/webui_modules/onboarding.py`. Same shape as v0.7.17's `/test/` whitelist fix — the public read endpoint should work regardless of onboarding state, so the model-picker spec can hit it on fresh containers. (The 2 currently-live model-picker tests are still `describe.skip` for this PR because `:stable` doesn't yet have the whitelist; they unskip in v0.7.22.)

### Behind the scenes

- 24 Playwright smoke specs total (was 18 before v0.7.21; +6 from the model-picker spec — 2 live + 3 skipped, plus 1 already-skipped section updated). Live count went up by 2.
- No code change to runtime paths; no jest delta expected. CI green carries the same shape as v0.7.20.

### What's next

- **v0.7.22:** #364 wizard styling parity with Hermes WebUI + restore old-version onboarding feel (Stan's "wizard looks odd" + "old onboarding was prettier").
- **v0.7.23:** #362 interactive install UX overhaul (Apple-polish step states + retry buttons) + #353 NVidia-style installer modes (Express / Clean Install / Uninstall-with-cleanup).
- **v0.7.22+ also:** #365 test-infrastructure hooks (`/test/seed-provider` + `/test/skip-onboarding` + `/test/inject-failure`) unblocks 5 currently-skipped Playwright specs.

---

## [0.7.20] - 2026-05-23

**Windows install reliability + picker sanity + #336 diagnostics.** Stan @bsgdigital's Win11 smoke caught the load-bearing P0 race that made fresh-install Fox fail to detect Docker after reboot. v0.7.20 fixes that, fixes the Ollama-under-Custom mis-categorization in the picker, auto-preselects a usable chat model on first open, and surfaces real backend errors in the wizard's local-fallback failure path so future bug reports carry diagnostics instead of "unknown error."

### Fixed

- **#361 P0: Docker detection race on Windows.** `ensureDockerWindows` polling loop in `packages/electron/src/startup.js:482+` previously `break`'d on the first `WSL_BACKEND_MISSING` diagnostic — a TRANSIENT state during fresh Docker Desktop boot. Fix: tolerate the WSL-missing signal as long as the Docker Desktop PROCESS is still alive (5 consecutive reports = ~60s patience before escalating to recovery). Timeout extended 180s → 240s for fresh-install-on-slower-hardware. Progress UI shows "Waiting for Docker WSL backend to register… (Ns)" so users see what's happening. Closes Stan's "не детектить коли завантажується докер" diagnosis. **Unblocks @bsgdigital's blog-post promotion.**
- **#278 Ollama models classified under OLLAMA group, not CUSTOM.** `packages/fox-overlay/fox_overlay/webui_modules/ollama.py:459,492` set_active_model now writes `provider: "ollama"` instead of `provider: "custom"`. Backend routing unchanged (upstream's `hermes_cli/auth.py:1412` aliases `ollama → custom` in PROVIDER_REGISTRY, so same HTTP path); only picker categorization changes. Also closes #343 (v0.7.18-era duplicate).
- **#344 Chat auto-preselects first usable model on open.** New JS extension `packages/fox-overlay/webui_static/chat-model-preselect.js` runs after DOM ready, checks if a usable model is selected, picks the first one if not (skipping `__ollama_hint:` synthetic entries from v0.7.18 #337). Empty state when zero models available: composer chip shows "Model not selected" with `title` pointing to Settings → Providers. Wired into the Dockerfile's `HERMES_WEBUI_EXTENSION_SCRIPT_URLS`.

### Changed

- **#336 tactical: wizard local-fallback alert surfaces real backend errors.** `packages/fox-overlay/fox_overlay/webui_modules/local_fallback.py:enable()` now collects exception context into `errors: [...]` on the returned status instead of silently swallowing into `logger.exception`. `packages/fox-overlay/webui_static/setup.js:447` reads `r.data.error`, falls back to `r.data.errors.join('; ')`, falls back to HTTP-status + raw-body summary, never to "unknown error". Future Win11 repros carry diagnostics. **Root-cause fix for #336 still pending** — needs the Win11 `docker logs` Stan is capturing.

### Behind the scenes — test coverage closing SWE C's audit gaps

- **`tests/electron/tray-manager.test.js`** (new, +182 LOC). Was at 0% coverage when v0.7.18 #341 Reset Fox tray shipped. Now pins three contracts: cancel-confirm early-returns without touching state; confirm-confirm calls removeContainerAndImage → spawn detached cleanup → app.quit() in that order; dialog defaultId=cancelId=0.
- **`tests/electron/docker-manager.test.js`** (+151 LOC, 4 tests). Pins the v0.7.18 #340 stale-image recreate branch — mock returns stale ImageID, asserts force-remove + recreate.
- **`tests/electron/startup.test.js`** (+46 LOC, 2 tests). Pins the new v0.7.20 #361 WSL-transient tolerance + the WSL-process-gone fast-bail path.
- **`qa/playwright/tests/smoke/wizard-local-fallback.spec.ts`** (new). Contract spec for #336 — 2 live (status endpoint shape + UI state), 2 `describe.skip` pending v0.7.20 fix landing in `:stable`.

**Total jest tests: 71 → 83 (+12).** Total Playwright smoke: 14 → 18 (+4).

### What's next

- **v0.7.21:** #362 interactive install UX overhaul (Apple-polish step states with retry buttons + WebUI styling), #353 NVidia-style installer modes, tooling cleanup (regen-patch.sh rewrite, check-overlay-basis.sh stash leak fix, orphan-patch detection).
- **#336 root cause:** waiting on Stan's Win11 `docker logs` to identify the actual local-fallback failure on Windows. v0.7.20 ships diagnostics so the next repro carries the real error string.
- **#360 Fox-branded UI variant** (bot name + avatar + empty state) — defects in PR #327 documented; redo when someone scopes the trigger-class mechanism.

---

## [0.7.19] - 2026-05-23

**Substrate cleanup — no new features, all groundwork.** The systemic root of yesterday's cleanup mess (Electron's `@fox-in-the-box` userData dir name) gets fixed. The doc rot the 6-hat audit flagged (CLAUDE.md "Current State (as of v0.7.6)" 13 releases stale, dead `docs/GATEWAY.md` describing a parked product line, empty `CODE_OF_CONDUCT.md` broken link) gets cleared. The `qa/SMOKE_LOG.md` gate that's been routed around in writing for 4 consecutive releases gets teeth. Branch protection finally enforces the smoke + validate-overlay checks v0.7.15 designed as required.

### Changed

- **`productName: fox-in-the-box` in `packages/electron/package.json`.** Electron's userData path now resolves to `~/AppData/Roaming/fox-in-the-box` on Windows, `~/Library/Application Support/fox-in-the-box` on macOS, `~/.config/fox-in-the-box` on Linux — dropping the `@` prefix that came from the npm scope `@fox-in-the-box/electron` leaking into Electron's default app-name resolution. The wrong path was the systemic root of the v0.7.17→v0.7.18 cleanup mess where every standard cleanup command (Remove-Item, the old `clean-windows-desktop.ps1`) targeted `Fox in the box` and silently no-op'd.
- **One-time migration shim** at `packages/electron/src/main.js`. If the legacy `@fox-in-the-box` userData dir exists and the new `fox-in-the-box` dir doesn't, rename it. Runs before `app.whenReady()` so Electron creates its session/LevelDB in the right place. Zero-loss for existing users; falls back gracefully if the rename fails (permissions, locks).
- **`app.setName('Fox in the box')` removed** from main.js. Was no-op'd by Electron's path-resolution timing anyway; productName in package.json is now the canonical control.

### Fixed (audit-discovered)

- **`docs/GATEWAY.md` deleted.** 410-line doc described a Stripe-billed LLM proxy that was parked alongside #90 + #91 weeks ago; README.md linked to it as "Hermes Agent gateway internals" — completely wrong subject. Worst doc rot in the repo per Architect B's audit.
- **`CODE_OF_CONDUCT.md` deleted** (was 0 bytes; broken link from README + CONTRIBUTING). Both references removed.
- **`docs/DEV_MODE.md` version refs refreshed** (3 places: `0.5.0` → `0.7.19`, `FITB_VERSION=v0.7.6` → `v0.7.19`).
- **`qa/SMOKE_CHECKLIST.md` header refreshed** (currently-testing line: v0.7.6 → v0.7.19).
- **`packages/fox-overlay/README.md`** — patch count 2 → 3 (the v0.7.13/v0.7.15 onboarding-redirect patch was never added). `webui_modules` list updated with `test_hooks`.
- **`docs/architecture/upstream-overlay.md`** — same patch count + test_hooks fixes.

### Behind the scenes

- **SMOKE_LOG gate teeth (`release.yml`).** v0.7.15's gate required only a matching `## vX.Y.Z` header. v0.7.19 adds a body-content check: the entry MUST contain at least one `- [x]` (real smoke was performed) OR an explicit `Bypass reason:` line (in-writing waiver). Closes the v0.7.16-v0.7.18 loophole where the header existed but every checkbox was `[ ]` placeholder — "structurally non-bypass, factually bypass."
- **Branch protection flipped** post-merge: `main` requires Playwright `smoke` + `validate-overlay` jobs in addition to the existing container build/smoke. The v0.7.15 "intended REQUIRED" deferral that's sat for 3 weeks is closed.
- **8 issues silently fixed but never closed → closed by audit:** #340 (v0.7.18), #341 (v0.7.18 in-app; carved to #346), #330 (v0.7.16), #325 (v0.7.16), #343 (dup of #278), #280 (v0.7.18 #337), #290 (windows-real-smoke.yml shipped), #319 (automation noise). Backlog drops 27 → ~20 actionable.

### What's next

- **v0.7.20:** Picker sanity + #336. Chat auto-preselect (#344), Ollama dedupe in Custom (#278), wizard local-fallback "unknown error" diagnosis (#336 — needs Win11 logs).
- **v0.7.21:** Tooling cleanup. `check-overlay-basis.sh` stash leak, `regen-patch.sh` rewrite, orphan-patch detection, test coverage for `tray-manager.js` + `docker-manager.js` #340 stale-image branch.

---

## [0.7.18] - 2026-05-23

**Upgrades just work + Reset Fox tray menu + Ollama tile always present.** Most of v0.7.18 traces back to one debugging session with @roadhero post-v0.7.17 release where we discovered: (1) Fox doesn't re-create the container when the image updates, so users stay on the old container after upgrading, (2) cleaning Fox state required `cmd /c rd /s /q` voodoo because there was no in-app reset, and (3) the Ollama provider tile was hidden entirely when Ollama wasn't installed, so users couldn't even discover local-models support.

### Added

- **Tray menu: "Reset Fox completely…"** — one click to stop the container, remove the image, and delete all Fox data + settings + conversations. Replaces the manual docker-stop / docker-rm / docker-rmi / cmd-rd dance documented in the v0.7.17 debug thread. Spawns a detached cleanup process so the userData dir deletion happens AFTER Electron releases its LevelDB locks (the inline-delete-while-running failure mode we hit). Includes a destructive-action confirmation dialog (default = Cancel). (`packages/electron/src/{tray-manager,docker-manager}.js`)

### Fixed

- **#340 Container is re-created when the image updates.** `ensureContainerRunning` (`packages/electron/src/docker-manager.js:453+`) now compares the existing container's `ImageID` to the currently-tagged `:stable` image digest. If they differ, the old container is stopped, removed, and a fresh one is created from the new image. Bind mounts on `/data` and `/app/workspace` preserve all user data across the recreate. Closes the root cause of the v0.7.17→v0.7.18 upgrade-loop debug session.
- **#337 Ollama tile is always present in the model picker.** `_splice_ollama_group` (`packages/fox-overlay/fox_overlay/webui_patches/config.py:120+`) was a no-op when the Ollama daemon wasn't reachable or had no installed models — so users without Ollama saw no hint that Fox supported local models at all. Now the group is always present, with state-aware content: "Install Ollama from ollama.com/download" when no daemon, "Pull a model: ollama pull phi4-mini" when daemon-up-but-empty, and the standard model list otherwise. Synthetic hint entries use the `__ollama_hint:` ID prefix so future frontend work can render them as non-selectable.

### Changed

- **`wizard-renders` redirect-fires + `test-hooks-safety` specs are both live in CI smoke now.** `test-hooks-safety.spec.ts:30` was `describe.skip` for v0.7.17 only (chicken-and-egg from the patch-003 `/test/` whitelist landing in the same release). With `:stable` advancing to v0.7.17, the unskip can finally land. Both regression nets are live + asserting from this release forward.

### Behind the scenes

- **First non-bypass `qa/SMOKE_LOG.md` entry — for real this time.** v0.7.14, v0.7.15, v0.7.16 shipped as bypass entries; v0.7.17 was tagged with the entry header but checkboxes unchecked. v0.7.18 runs the Section L row against a real Win11 + Mac smoke before tag.
- The Reset Fox spawn-detached-cleanup pattern is documented for re-use: the `spawnDetachedCleanup` helper in `tray-manager.js` is the canonical "delete userData on exit" primitive.

### What's next

- **v0.7.19:** path alignment — `productName: fox-in-the-box` in package.json so userData drops the `@` prefix; one-time migration shim from old `@fox-in-the-box` dir. Surfaced by @roadhero in the v0.7.17 debug as the systemic root of the cleanup mess.
- **#336 wizard local-fallback "unknown error":** still open; waiting on Win11 container logs to diagnose. Likely scoped into v0.7.19 or v0.7.20.
- Remaining meta-gaps from the v0.7.15 audit: orphan-patch detection in `check-overlay-basis.sh`, the broken `regen-patch.sh` rewrite.

---

## [0.7.17] - 2026-05-23

**Anthropic, Gemini, and Bedrock providers actually work now + the redirect-fires Playwright spec goes live.** v0.7.16's post-release smoke surfaced a class of bug: upstream's hermes-agent gates each provider's Python package behind an optional `pyproject.toml` extra (their lazy-deps policy), and the container build was installing hermes-agent without any extras. Result: a user adding an Anthropic key (or picking Gemini natively) hit `ImportError: The 'anthropic' package is required` at first message. Same shape would have surfaced for Gemini + Bedrock the moment anyone tried them. All three now installed at container build time. Also unskips the `wizard-renders` redirect-fires assertions deferred from v0.7.15 (chicken-and-egg now resolved — `:stable` is v0.7.16 which has patch 003 actually applied).

### Fixed

- **Onboarding redirect now whitelists `/test/` — catches latent v0.7.15+ bug.** `packages/fox-overlay/fox_overlay/webui_modules/onboarding.py:30-53` was missing `/test/` in `_SETUP_PREFIXES`, so patch 003's redirect middleware was 302'ing POST `/test/reset` to `/setup` on fresh containers. Safe to whitelist because `/test/*` routes are gated by `FITB_TEST_MODE=1` and don't exist in production builds. Latent since v0.7.15 (added patch 003); surfaced only in v0.7.17 PR CI because that was the first time PR-time `:stable` actually had patch 003 applied (v0.7.13/14 had it written but the series file missed it — see v0.7.15 retro). `qa/playwright/tests/smoke/test-hooks-safety.spec.ts` test is now `describe.skip` for one release while `:stable` advances (unskip in v0.7.18).
- **Container installs `[anthropic,bedrock,google]` extras for hermes-agent.** `packages/integration/Dockerfile:305-313` was `pip install -e /app/hermes-agent` — now `pip install -e '/app/hermes-agent[anthropic,bedrock,google]'`. Coverage: Anthropic native (Sonnet / Haiku / Opus models in the picker — `forks/hermes-webui/static/index.html:620-626`), Gemini native (`google/gemini-*` in the picker + `agent/gemini_native_adapter.py` + `agent/gemini_cloudcode_adapter.py`), Bedrock (`agent/bedrock_adapter.py`). OpenRouter / OpenAI / Codex / Ollama don't need extras (openai package is in core, Ollama is HTTP-only). Surfaced in v0.7.16 post-release smoke by @roadhero on Win11 when adding an Anthropic key.

### Changed

- **`wizard-renders` redirect-fires assertions enabled.** `qa/playwright/tests/smoke/wizard-renders.spec.ts:64-114` was `test.describe.skip` since v0.7.15 because PR CI pulls `:stable` and `:stable` was v0.7.14 at that PR's CI time (no patch 003). v0.7.16 shipped patch 003 to `:stable`; now the spec can actually validate that `GET /` on a fresh container redirects to `/setup`. The whole point of the spec was to be the permanent regression net for #331 — it's finally live.

### Behind the scenes

- **Breaks the `qa/SMOKE_LOG.md` bypass streak.** v0.7.14, v0.7.15, v0.7.16 all shipped as bypass entries. v0.7.17's entry is real — pre-tag smoke run on the PR-built container image, Anthropic key → message → response path verified live (Gemini + Bedrock surface in normal use, single smoke covers all three).
- Container size +~50MB from the three extras (boto3 is the biggest contributor). Build time +~20s.

### What's next

- **#1 from v0.7.16 smoke** (filed as separate issue): `/api/local-fallback/enable` returns "unknown error" when triggered from the wizard's local-model button on Windows. Needs container-side log dive.
- **#2 from v0.7.16 smoke** (filed as separate issue): Ollama provider tile missing entirely from Settings → Providers when Ollama isn't installed on the host. UX expectation is "tile present with install hint."
- Remaining meta-gaps from the v0.7.15 audit: orphan-patch detection in `check-overlay-basis.sh`, the broken `regen-patch.sh` rewrite.
- v0.7.x continues until "ship-to-a-stranger" quality holds.

---

## [0.7.16] - 2026-05-22

**Windows installer UX: three fixes for dialogs hidden behind the FITB spinner.** All three were P0 user-reported issues blocking fresh Windows installs — the Docker Desktop installer dialog disappearing behind the FITB progress window (#324), the same z-order race for the "How this container should be accessed" modal (#330), and the absence of any user-facing copy explaining that the install will auto-resume after the Docker-required reboot (#325). Manual Win11 + macOS smoke verification on the published artifact happens post-tag rather than pre-tag (third consecutive bypass entry in `qa/SMOKE_LOG.md`); if a smoke item fails it lands as v0.7.17.

### Fixed

- **#324 — Docker Desktop install dialog appears behind the FITB installer.** The FITB progress window opens with `alwaysOnTop: true` so the user can see startup status. When the same flow then launches Docker Desktop (via `winget install` for fresh installs or by spawning `Docker Desktop.exe` for existing installs), Docker's GUI dialogs were competing with that always-on-top claim and losing. Fix: the progress window now drops `alwaysOnTop` for the duration of any external Docker-Desktop launch (`startup.js` calls a new `setForegroundYield()` dep wired from `main.js`), then reclaims it once Docker's window has come up. Bracketed at the `state.action === 'start'` spawn paths and the `action === 'install'` winget flow. (`packages/electron/src/{startup,main}.js`)
- **#330 — "How this container should be accessed" modal appears behind the install window.** `ensureDockerAccessModeChosen` was calling `dialog.showMessageBox(opts)` without a parent BrowserWindow — Electron's API supports both signatures but parent-less message boxes on Windows can render behind any pre-existing always-on-top window. Fix: the function now accepts `{ parent }` and passes it as the first arg when present; `startup-orchestrator` + `startFromTray` thread the active progress window through. (`packages/electron/src/{docker-manager,startup-orchestrator,main}.js`)
- **#325 — User isn't told installation will auto-resume after the post-Docker-install reboot.** The reboot prompt copy read only "A restart is recommended before trying Fox in the box again," leaving users uncertain whether they had to re-run the installer themselves. RunOnce was already being registered (no behavior change), but the dialog never told the user. Fix: dialog now reads "Fox in the box will resume installation automatically after your PC restarts — you do not need to re-launch the installer manually," with buttons "Restart now" / "I'll restart later" instead of "Restart now" / "Close." (`packages/electron/src/main.js` — `showDaemonRecoveryRequired`)

### Behind the scenes

- **Third consecutive `qa/SMOKE_LOG.md` bypass entry.** v0.7.14 + v0.7.15 bypassed because they were infrastructure-only; v0.7.16 bypasses because the post-tag smoke is faster against the real signed artifact than a `workflow_dispatch` build. The "first non-bypass" milestone slips to v0.7.17 — the bypass streak must end there.
- `qa/SMOKE_CHECKLIST.md` gains a v0.7.16 row in Section L covering all three fixes + regression sanity for the saved-access-mode path (must NOT prompt when prefs already saved). Smoke executes post-release.

### What's next

- **v0.7.17:** the meta-gaps surfaced by the v0.7.15 audit — orphan-patch detection in `check-overlay-basis.sh`, a working `regen-patch.sh` (the v0.7.14 ship was broken-on-arrival), and unskipping the `wizard-renders` redirect-fires Playwright assertions (chicken-and-egg now resolved by v0.7.15 having shipped).
- v0.7.x continues until "ship-to-a-stranger" quality holds.

---

## [0.7.15] - 2026-05-22

**Permanent regression net for #331 + SMOKE_LOG enforcement gate.** The infrastructure half of the v0.7.13 retrospective's findings — Playwright spec that would have caught #331 had it existed, plus a release-time gate that refuses to publish a tag without a written audit-trail entry in `qa/SMOKE_LOG.md`. The deferral pattern that let #331 ship for 6 releases is closed at the bone.

### Added

- **`wizard-renders` redirect-fires spec** in `qa/playwright/tests/smoke/wizard-renders.spec.ts`. The deferred half of v0.7.13's spec (chicken-and-egg with `:stable`-at-PR-CI now unblocked — v0.7.13 has been live since this morning). Asserts: (a) `POST /test/reset` succeeds; (b) GET `/` on a fresh container redirects to `/setup`; (c) `/setup` serves the Fox wizard with `#wizard` + `#progress-bar` elements (NOT upstream's chat shell). Three independent assertions catching three distinct failure modes — the patch missing, the patch wired wrong, or the wizard HTML overwritten with garbage. **This spec is the permanent regression net for #331.**
- **`release.yml` SMOKE_LOG gate.** Per the v0.7.13 retro's "stop shipping without verification" recommendation: every release tag must have a matching `## vX.Y.Z` entry in `qa/SMOKE_LOG.md` before the GitHub Release publishes. Bypass via "Bypass reason:" line — the gate just requires the header, so the maintainer must consciously lie in writing if they skip the smoke. Both states leave audit trails.

### Changed

- **Playwright `smoke` job marked intended-required.** Workflow comment updated from "non-blocking" to "intended REQUIRED check as of v0.7.15." The actual branch-protection enforcement is a GitHub-UI setting the workflow can't toggle itself; `qa/playwright/README.md` now has a "Required CI checks" section documenting the 2-click flip. **Per the v0.7.13 retro, the indefinite "Phase 1 makes smoke required" deferral was exactly the structural gap that let #331 slip — closing it.**

### Behind the scenes

- Total Playwright smoke suite: **7 specs** (was 6 — added the wizard-renders redirect-fires + Fox-wizard-HTML-serves assertions).
- v0.7.15 itself ships with a `qa/SMOKE_LOG.md` bypass entry — the release that *adds* the SMOKE_LOG gate can't pre-exist its own gate. Forward, v0.7.16+ must have real entries (no more pure-bypass releases).

### What's next

- **v0.7.16:** Windows installer UX bundle (#324 + #325 + #330) — z-order fixes for Docker Desktop install dialog + access-mode modal, plus "installation auto-resumes after reboot" copy. First release subject to the new SMOKE_LOG gate; must include a real Section H/L gate run.
- **v0.7.17:** Minimum brand alignment for installer (#323 — Fox avatar + 1 accent color, scoped down; defer full design-system pass to v0.8/#64).

---

## [0.7.14] - 2026-05-22

**Process meta-fixes from the v0.7.13 retrospective.** Three convergent recommendations from the 6-perspective retro that caught #331: (1) catch anchor drift locally instead of waiting 3+ minutes for CI Docker build; (2) atomic patch generation that prevents the "uncommitted fork state leaks into the diff" failure mode (commit e9bd4cd); (3) written audit trail forcing actual smoke-checklist execution before a tag publishes. No user-visible change — pure infrastructure.

### Added

- **`make validate-overlay` + `.github/workflows/validate-overlay.yml`** — three-check overlay gate that runs in <30s on every PR touching `packages/fox-overlay/**` or `forks/**`. Same gate runs locally via the Makefile target. The three checks (per #328): (a) submodule cleanliness — `forks/hermes-{agent,webui}` must be at the pinned commit with no uncommitted changes (catches the commit-e9bd4cd class of failure); (b) `check-overlay-basis.sh` — patch series + `.fox-removals` apply cleanly; (c) bootstrap import smoke — `webui_patches.apply_all()` runs against actual submodule sources, surfacing anchor + signature drift in `webui_patches/{config,streaming}.py` that today only fires at container runtime.
- **`make regen-patch FORK=… PATCH=…`** — atomic patch regeneration per #328's solution sketch. Force-resets the fork to its pinned commit, applies all earlier series patches, hands off to a shell for the developer to make edits, then exports the diff and force-resets the fork. Eliminates the entire "uncommitted fork state contaminates the diff" category.
- **`qa/SMOKE_LOG.md`** — written audit trail for which release was actually smoke-tested by a human. Pre-v0.7.14, the only evidence anyone ran SMOKE_CHECKLIST.md was its "Currently testing: vX.Y.Z" header — which sat at v0.7.6 for 6 releases, exactly because nobody was updating it. Forward: every release must have a matching `## vX.Y.Z` entry here; empty entries are OK if the maintainer explicitly notes the bypass reason. v0.7.15+ will wire `release.yml` to refuse publish without a matching entry (5-line bash grep).

### Behind the scenes — #328 closes

The patch-fragility-caught-only-in-CI class of bug closes here. Anchor drift now surfaces at 3 layers: local `make validate-overlay`, the new PR-time `validate-overlay.yml` (<30s), and the existing `check-overlay-basis.sh` in `build-container.yml` (~3 min, kept as belt-and-suspenders). The cost-of-iteration drops from "3 minutes per failed CI cycle" to "<2 seconds per failed local run."

### What's next

- **v0.7.15:** flip Playwright smoke to a required CI check (was deferred to "Phase 1" indefinitely; the indefinite deferral is exactly what bit us in #331). Add the v0.7.13-deferred `wizard-renders.spec.ts` redirect-fires assertion (chicken-and-egg unblocked now that `:stable` will be v0.7.13). Plus `SMOKE_LOG.md` gate enforcement.
- **v0.7.16:** Windows installer UX bundle (#324 + #325 + #330).
- **v0.7.17:** Minimum brand alignment for installer (#323 scoped down).

---

## [0.7.13] - 2026-05-22

**Onboarding restored — P0 fix.** New-install users get the Fox wizard at `/setup` again instead of dropping straight into a half-styled chat shell. The redirect middleware that v0.5.x had inline at `server.py` was missing from the v0.6.0/v0.7.0 overlay migration — `should_redirect_to_setup` and `redirect_to_setup` were moved into the overlay package but the patch to re-wire them into upstream's `server.py:do_GET`/`_handle_write` was never written. Every fresh install since v0.7.0 has shipped without onboarding.

### Fixed

- **Onboarding redirect re-wired (#331 — closes).** New patch `003-server-py-onboarding-redirect.patch` imports Fox's two onboarding helpers (guarded so vanilla webui without `fox_overlay` keeps booting), then inserts `if should_redirect_to_setup(parsed.path) and redirect_to_setup is not None: return redirect_to_setup(self)` at the top of both `do_GET` and `_handle_write` (which is shared by `do_POST` / `do_PATCH` / `do_DELETE` — so the single insertion covers all write methods). Pattern matches the v0.5.4 fork's inline edits at `server.py:147-148, 167-168`. The "custom styling lost" symptom from #331 is a downstream cascade: when boot.js crashes mid-init referencing `loadOnboardingWizard` (gone via `.fox-removals`), the DOM state attributes never get set and Fox CSS selectors don't match. Restoring the redirect prevents un-onboarded users from reaching `/` at all, so `boot.js` never tries to load the missing wizard.
- **`_SETUP_PREFIXES` whitelist cleanup.** Replaced stale `/static/setup.` (dead code since v0.6.0 P2 — assets moved to `/extensions/`) with `/extensions/`. Wizard CSS/JS/fonts/images load cleanly without being bounced back to `/setup` mid-page-render.

### Behind the scenes

- **A 6-perspective retrospective drove this release.** 3 architects + 3 SWE subagents dug into how a P0 onboarding regression shipped across 12 releases this morning without anyone noticing. The convergent finding: `qa/SMOKE_CHECKLIST.md`'s Section B (wizard renders) explicitly covered the regression case, but the checklist hadn't been re-run between v0.5.x and v0.7.12 — its own "Currently testing: v0.7.6" header is the evidence. 12 releases in one day cannot accommodate a 2-hour manual checklist between each. The Playwright smoke suite that nominally replaces it has zero specs asserting the wizard actually renders.
- New `qa/playwright/tests/smoke/wizard-renders.spec.ts` ships the asset-served half (works against any `:stable`). The redirect-actually-fires assertion has the same chicken-and-egg as v0.7.10's mobile-avatar spec — it can't run on this PR's CI because `:stable` is still v0.7.12. Lands as a v0.7.14 PR once `:stable` advances. The pattern of split-the-spec-by-shipping-window is now established.
- The 6-perspective retro also surfaced the **process meta-fixes** that should land as v0.7.14+: make Playwright smoke a required CI check (deferred to "Phase 1" indefinitely; today the indefinite deferral is exactly what bit us); add a `SMOKE_LOG.md` that `release.yml` refuses to publish without a matching entry per tag; delete SUPERSEDED checklist sections eroded by accretion.

### What's next

- **v0.7.14:** anchor-drift caught locally (#328) — `make validate-overlay` + `validate-overlay.yml` PR gate + `regen-patch.sh`. Stops the overlay-patch-fragility class of bug at commit-time, not 3+ minutes into CI.
- **v0.7.15:** Windows installer UX bundle (#324 + #325 + #330) — z-order fixes for Docker Desktop install dialog + access-mode modal, plus the "installation auto-resumes after reboot" copy.
- **v0.7.16:** minimum brand alignment for installer (#323 scoped down — Fox avatar + 1 accent color; defer full design-system pass to v0.8/#64).

---

## [0.7.12] - 2026-05-22

Tailscale auth link, sticky. The `/api/tailscale/up/poll` response now serves a stable auth URL across the entire `awaiting-auth` window even when the daemon thread momentarily returns empty mid-poll — fixes the "link flashes for ~1s and disappears" symptom Safari users hit (#146). Server-side fix in `tailscale.py`; client-side tile rebuild (the bigger architectural piece per the 4-architect scoping) deferred to v0.7.13 if this MVP doesn't fully resolve.

### Fixed

- **Tailscale auth link stays visible until the auth flow actually ends (#146 — closes pending Safari verification).** Three latent races in `webui_modules/tailscale.py` were causing transient empty `auth_url` values in the poll response: the daemon thread's 1-second scrape loop could return empty between the attempt start and the first successful URL capture, a stale daemon thread from a superseded attempt could overwrite the active attempt's URL with empty, and the `awaiting-auth → running` state promotion in `get_up_progress()` left the `auth_url` field as-was while the state itself flipped. Safari with default popup-blocker settings re-renders the auth tile from every poll response — a single tick of empty `auth_url` would clear the link from the DOM, then the user lost the click. Now: `_up_state` maintains a sticky `last_auth_url` whenever a non-empty value is ever observed for the current attempt; `get_up_progress()` prefers the live `auth_url` and falls back to the sticky copy when the live value is transiently empty; sticky is cleared only on `logout()` + on a fresh `start_up()` (new attempt = new URL). Added a `cleared: bool` field to the poll response so client code that knows about the new contract can distinguish "transient empty — keep your rendered link" from "attempt is over — remove the link." Terminal states (`running` / `failed` / `idle`) clear the URL regardless of stickiness — once the attempt is done, continuing to serve the link would confuse the user.

### Heads-up

- **Real Safari verification on a Mac with an active tailnet is still needed** before declaring #146 fully closed. The server-side fix removes the source of the transient blank — if Safari's render logic re-renders from every poll, the link should now stay because the poll value stays. If Safari users still report the symptom post-merge, the bug is client-side (upstream's JS clearing the link on its own timer) and v0.7.13 brings the client-side tile rebuild (`fox-overlay.js` DOM mutation observer + sticky render) per the original 4-architect scoping plan.
- The `/test/tailscale/set-state` hook (planned for this release per scoping) is **not** included — it's a separate test-infra PR worth doing on its own when the Playwright Phase 1 wizard specs need it.

### Behind the scenes

- **7 new pytest tests** in `packages/fox-overlay/tests/test_tailscale_overlay.py` covering: sticky population on non-empty auth_url, no overwrite on empty auth_url, fallback on transient blank, terminal-state clearing for running/failed/idle, state promotion clears link cleanly, `cleared` field always present in poll response.
- The scoped server-side-only MVP is intentional: smaller fix, faster ship, tests the hypothesis that the bug is the source data (server-side race) and not the rendering (client-side timer). If the hypothesis holds, the bigger client-side rebuild becomes unnecessary. The scoping doc estimated 8-12h for the full rebuild; this MVP came in at ~2h.

### What's next

- **v0.7.13 candidates** depending on user feedback: (a) client-side Tailscale tile rebuild in `fox-overlay.js` if Safari still hits the symptom; (b) "Docker Desktop installed but not running" detection (the broader class of WSL2-bootstrap regression not fully addressed by v0.7.11); (c) Windows installer Docker Desktop dialog z-order fix (#324, filed today).
- v0.7.x continues — v0.8.0 only when the verification rebuild is genuinely solid.

---

## [0.7.11] - 2026-05-22

Windows users no longer cycle through a 4-minute WSL repair + reboot loop when Docker Desktop is in Windows-containers mode. Fox now detects the mismatch in ~10 seconds and shows the exact tray-menu steps to switch modes.

### Fixed

- **Windows-containers-mode detection + actionable error (#291 — closes; also resolves #286 follow-up).** When Docker Desktop is running but set to Windows-containers mode, both Linux engine pipes return ENOENT. Pre-v0.7.11, Fox couldn't tell the difference between "Docker not installed" and "Docker installed but wrong mode," so it ran the WSL-repair flow — a ~4-minute UAC dance that ends in a reboot prompt. The user reboots, comes back, and hits the same failure because the mode persists across reboots. Real user impact, reported live during the v0.7.10 release window. Now: after both Linux pipes return ENOENT, Fox runs `docker info --format "{{.OSType}}"` (3s timeout). If `OSType` ends with `windows`, sets a new error code `DOCKER_WINDOWS_CONTAINERS_MODE`; the startup orchestrator short-circuits the recovery flow and surfaces a non-recoverable error dialog with the exact tray-menu steps: *"Right-click the Docker Desktop tray icon → 'Switch to Linux containers...' → wait for it to finish, then relaunch Fox in the box."* No more reboot loop.

### Heads-up

- **If you're stuck in the reboot loop right now on v0.7.10 or earlier:** the manual workaround is exactly what v0.7.11's error message says — right-click Docker Desktop tray → "Switch to Linux containers..." → wait ~30s → relaunch Fox. v0.7.11 just automates surfacing the message instead of cycling through WSL repair first.
- **Non-Docker-Desktop Windows installs** (Docker CE on Windows Server, Mirantis, Rancher Desktop) would also report `OSType=windows` legitimately. The error message specifically names Docker Desktop's tray menu — if you're using a different runtime and hit this, the underlying detection still saved you 4 minutes of recovery, just the suggested remediation will be off. File an issue if it surfaces.

### Behind the scenes

- Added `getLastDaemonErrorCode()` to docker-manager.js exports — a non-breaking pattern that lets the orchestrator distinguish "daemon not running" from richer failure causes without changing the `isDaemonRunning() → bool` contract that ~5 callers depend on.
- **6 new Jest tests** in `tests/electron/docker-manager.test.js` covering: Windows-containers detection, Linux-mode does NOT set code, CLI-unavailable graceful fallthrough, non-Windows platforms skip the probe entirely (saves wall time on macOS/Linux), banner-prefixed CLI output tolerated (some Docker Desktop 4.x builds prepend "Using context..."), stale code reset between calls. Total Electron test suite: **71 specs, all green**.
- Per the 4-architect scoping pass: realistic estimate was 4-6h; actual was ~2h once the existing `getRemediationForCode` table at `main.js:358-391` made the UI wiring trivial.

### What's next

- **v0.7.12: Tailscale Safari auth-link rebuild (#146).** Largest remaining bug — scoping revealed it's a rebuild-from-scratch (the v0.7.0 migration dropped the client tile) plus a server-side data race. ~8-12h with real Safari verification + test-hook expansion.
- **Also pending: #324** (Windows installer: Docker Desktop dialog appears behind installer window) — filed today, likely small NSIS z-order fix.

---

## [0.7.10] - 2026-05-22

Mobile gets the Fox. The titlebar on phones now shows the Fox avatar photo instead of the upstream Hermes caduceus logomark — small change, but it's the difference between "generic app" and "my assistant" on a 375px viewport.

### Changed

- **Mobile titlebar avatar (#299 — closes).** Below 768px viewport, the titlebar swaps the upstream Hermes caduceus SVG for the Fox avatar photo (`/extensions/images/fox_avatar_cropped.jpg`). 40px circular, 44px touch target (Apple HIG / WCAG 2.5.5). Desktop view unchanged — logomark stays on ≥768px. CSS-only change in `packages/fox-overlay/webui_static/fox-in-the-box.css`; the asset was already in the project (512×512 source, way over the retina threshold).

### Added

- **Playwright spec for the mobile-viewport surface.** `mobile-avatar.spec.ts` runs at iPhone SE dimensions (375×667) and asserts (a) the avatar asset is served from `/extensions/images/`, (b) the titlebar icon's computed `background-image` references the Fox avatar, (c) touch target ≥ 44×44px, (d) the upstream embedded SVG is hidden. Catches three regression classes: CSS load-order, missing asset, upstream selector rename. Total smoke suite: **6 specs** running on every PR.

### Behind the scenes

- The 4-architect scoping pass that preceded this release flagged `fox_avatar_cropped.jpg` dimension verification as a pre-flight check (asset must be ≥88×88 for retina). Verified at 512×512 before implementation. The lightweight scoping pattern worked: an issue that the original report estimated at "30 minutes" was scoped to ~2-3h including verification + a regression-catching spec, which is what shipped.
- Mobile breakpoint deliberately `max-width: 767px` (not 768px) so the 768px boundary cleanly belongs to desktop. iOS Safari portrait reports `device-width: 375px` on iPhone SE/8 (and `390px` on iPhone 14), so the breakpoint catches both.

### What's next

- **v0.7.11**: Windows-containers-mode detection (#291) — bsdigital-class regression. Closed-bug effort ~4-6h, requires Windows VM verification.
- **v0.7.12**: Tailscale Safari auth-link fix (#146) — discovered during scoping to be a "rebuild from scratch" effort (~8-12h) because the v0.7.0 virgin-upstream migration dropped the client-side tile that v0.5.4 originally fixed. Needs real Safari verification + `/test/tailscale/set-state` test-hook expansion first.

---

## [0.7.9] - 2026-05-22

Three real bug fixes off the backlog. One was a P1 data-loss bug that had been quietly costing users their workspace files since v0.3.x.

### Fixed

- **Workspace files now persist across container restarts (#145 — closes).** Pre-v0.7.9, when the agent wrote a file (via `terminal()` or `execute_code`), it landed in `/app/workspace` inside the container — which was on the writable layer of an `AutoRemove` container that recreated on every Fox app launch. Every restart silently wiped the workspace. Now `/app/workspace` is a host-bound volume next to the existing `/data` mount, so files survive. For Electron users: workspace lives at `~/.foxinthebox/workspace` (or `~/Library/Application Support/Fox in the Box/workspace` on macOS). For `install.sh` users: same — `$FOX_DATA_DIR/workspace`. **Heads-up: existing pre-v0.7.9 workspace contents were on the ephemeral layer and are already gone — this fix prevents future loss, not recovery.**
- **A runaway agent script can no longer hang the WebUI (#149 — closes).** The hermes-gateway supervisord program is now launched with `nice -n 10`, so the gateway and all its child processes (terminal, execute_code, MCP servers) run at lower CPU priority. The WebUI stays at normal priority and preempts cleanly when the user clicks anything. Reproduction case the bug originally documented (benchmark script pegging all cores, requiring a reboot) is no longer fatal — the WebUI stays responsive even while the runaway script keeps running.
- **Fox overlay bootstrap signature now lands in `docker logs` (#302 — closes).** Pre-v0.7.9, `[fox-overlay] bootstrap installed: dispatcher frozen, N GET + M POST handlers registered` went only to Python's logging at WARNING level, which supervisord captured to `/data/logs/hermes-webui.err`. Ops running `docker logs <container>` to check "did Fox load?" saw nothing — even though the overlay loaded fine. Bootstrap now ALSO writes the line directly to PID 1's stdout via `/proc/1/fd/1`, bypassing supervisord's per-program capture. The file-logged copy stays for searchability + rotation.

### Heads-up for upgraders

- The first launch after upgrade creates `~/.foxinthebox/workspace` (or platform-equivalent) — empty. If you previously had files inside the agent's workspace, they're already lost; this fix means new files going forward will persist.
- The CPU-priority change is invisible in normal use. You may notice slightly higher latency on agent tool calls under heavy CPU load (the gateway is now preemptible) — that's the point. WebUI is never starved.
- `docker logs` will now show the `[fox-overlay] bootstrap installed: ...` line within ~1s of container start. If you've been monitoring container health by other signals, this is one more.

### Behind the scenes

- The bootstrap log dual-write is best-effort: silently no-ops if `/proc/1/fd/1` isn't writable (non-Linux container runtime, restricted namespaces). The Python log path is unchanged so observability isn't worse than v0.7.8 anywhere.
- `nice -n 10` on the gateway means descendant processes inherit niceness (Linux kernel behavior). No code change inside the agent or its tool implementations — pure ops fix at the supervisord layer.

### What's next

- v0.7.10 candidates: testid retrofit + wizard-happy-path Playwright spec (the largest remaining Phase 1 single piece); #146 Tailscale Safari auth-link timing (needs Safari verification); #291 Windows-containers detection.
- v0.7.x continues — v0.8.0 only when the verification rebuild is genuinely solid.

---

## [0.7.8] - 2026-05-22

Playwright Phase 1 partial — 4 new integration specs added on top of Phase 0's `/health` baseline. Total verification suite: **5 specs** running on every PR against `:stable`. The remaining 8 Phase 1 specs (wizard flows, retry-panel, settings persistence, sentinel checks, `.fox-removals` enforcement) land in v0.7.9+ once the supporting test-hooks expand.

### Added

- **`endpoints-sweep.spec.ts`** — parametrizes over 5 Fox-claimed route prefixes (Ollama, Tailscale, local-fallback, local-models, /setup). Each must return 200, 404, or 503; anything else (especially 500) signals the dispatcher didn't claim the prefix.
- **`health-deep.spec.ts`** — `/health` now checked beyond just "200" — content-type is JSON or plain text, body is non-empty, no HTML error page. Catches upstream returning a default error page for `/health` while still 200.
- **`static-overlay.spec.ts`** — sample of `/extensions/*` assets (Fox CSS + JS) served correctly. Catches the v0.6.0 P2 class of regression where `HERMES_WEBUI_EXTENSION_DIR` isn't set or the Dockerfile didn't COPY `webui_static/`.
- **`test-hooks-safety.spec.ts`** — `POST /test/reset` returns `{ok: true}` under `FITB_TEST_MODE=1`. Proves the gate works from the outside (the unit tests in `test_test_hooks.py` cover the gate from the inside).

### Heads-up (not in v0.7.8)

- **The `playwright-smoke` CI job is still NOT a required check.** Phase 1 full landing (8 more specs covering the stateful flows + testid retrofit on overlay JS) is when it becomes required. Promoting the job to required needs a manual branch-protection edit anyway.
- **No specs for stateful flows yet** — the wizard, settings persistence, and the v0.6.1 retry-panel specs need `/test/ollama/set-state`, `/test/openrouter/set-key`, or container-restart orchestration. Coming as part of the test-hooks expansion that the v0.7.9 spec authoring will require.

### Behind the scenes

- The 5 specs run in parallel inside the smoke job's chromium project. Wall time on PR: still well under 1 minute.
- Each spec is failure-mode-driven: the assertion's error message names the most likely root cause ("`HERMES_WEBUI_EXTENSION_DIR` isn't set on supervisord's hermes-webui block"). When CI fails, the message points at the fix, not just the symptom.

### What's next

- **v0.7.9**: testid retrofit on `webui_static/setup.js` + `hostname-prompt.js` + the wizard-happy-path spec that depends on them. Likely the largest remaining piece.
- **v0.7.10+**: incremental spec additions; sentinel/`.fox-removals` checks; promotion of smoke to required CI gate when count crosses ~10.

The v0.7.x cycle continues — v0.8.0 only when the verification rebuild is genuinely solid.

---

## [0.7.7] - 2026-05-22

Docs at parity with shipped reality + the verification rebuild starts. Two big-effort PRs without a single user-visible code change to the running app — the kind of release that pays back over the entire v0.7.x stabilization cycle.

### Changed

- **Documentation audit (#310 — closes).** Six rewritten docs, 20 archived, two deletions, no code change. The high-leverage rewrites: `CLAUDE.md` "Current State" now reflects v0.7.6 (was stuck at v0.5.3 across the v0.6.x and v0.7.x cycle); `docs/RELEASE_WORKFLOW.md` now documents both Flow A (Fox-code release with the v0.7.5 PR-A + PR-B split) and Flow B (Option B upstream-only bump with the v0.7.5 diff guard); `docs/architecture/upstream-overlay.md` got a "Testing" pointer + the v0.7.4 wrap-and-splice / v0.7.5 fail-loud-bootstrap / v0.7.6 multi-substitution patterns documented; `packages/fox-overlay/README.md` went from 14-line placeholder to a real inventory; the top-level `README.md` roadmap section caught up to current reality. Twenty files moved to `docs/archive/` (15 task docs from pre-v0.5, 4 v0.6.0 planning/research docs, 1 v0.4.7 verification doc). Two strategy docs deleted as byte-identical to their existing archived copies. Acceptance test: `git grep` for v0.5/v0.6 mentions in non-archive markdown now returns only intentional historical context (per-version smoke rows, the "post-v0.6.0" architecture title, historical narrative).

### Added

- **Playwright Phase 0 infrastructure (#264 — closes).** New `qa/playwright/` workspace + 3-job CI workflow (`smoke` on PR, `full` nightly across 3 browsers × 4 shards, `electron-parity` weekly on macOS + Windows) + ONE trivial `/health` spec proving the rails work end-to-end against the released `:stable` container. New `fox_overlay/webui_modules/test_hooks.py` exposes `POST /test/reset` (nukes `/data/state/webui/*.json` + session dirs + the onboarding hint) and a `POST /test/tailscale/set-state` stub for Phase 1 — **only registered when `FITB_TEST_MODE=1`**, production builds see zero new attack surface, verified by three dedicated tests. Smoke job is non-required for Phase 0 by design (lets us iterate the infrastructure); becomes required in Phase 1.

### Behind the scenes

- The Playwright smoke job actually runs against the released `:stable` container — not a local build. The /health spec also asserts that a Fox-added `/api/ollama/status` route is registered, which catches "dispatcher didn't initialize" regressions.
- First CI run of the new `playwright.yml` workflow caught one issue (pnpm/action-setup@v4 rejects having both `version:` in the workflow AND `packageManager:` in package.json) and resolved on the second run. Pattern for future workflow additions: don't pin pnpm version in two places.
- Six tests added to `packages/fox-overlay/tests/` verify the `FITB_TEST_MODE=1` gate works in both directions — production safety isn't a "we believed it" claim, it's a unit test.

### What's next

- **v0.7.8: Playwright Phase 1 (#265).** ~12 specs replacing the manual smoke checklist as the release gate. Wizard + endpoints + overlay bootstrap + v0.6.1 retry. Becomes a required CI check once landed.
- v0.7.8 will likely bundle: bootstrap log surfaced to docker logs (#302), one-click diagnostic report button (#293), release-channels split (#306), Windows automated-testing strategy doc (#290).

---

## [0.7.6] - 2026-05-22

Silent failover, back. The other half of the local-AI story — automatic swap to the local llama-server when a remote provider has a transient failure — works again, closing the last open symptom of #303.

### Fixed

- **Silent failover on transient remote errors (#303 symptom 3 — closes #303 fully).** When a remote provider returns a failover-eligible error (rate-limit / 429 / 5xx / no response) and the local llama-server is ready, Fox now swaps to local + emits a `provider_switched` event. The user sees their original message still in the transcript with a "Switched to local model. Re-send your message to retry." note, and their next send hits local — no manual provider switch needed. Was lost in the v0.6.0 ATOMIC refactor (#241) when upstream rewrote the error-handling architecture; rebuilt on the new architecture with two new substitutions in `fox_overlay/webui_patches/streaming.py` — one for the success path (provider returned error response), one for the exception path (agent's `run_conversation()` raised). The first time Fox has used `substitute_function` for more than one substitution against `_run_agent_streaming` since the original v0.5.2 engine.

### Heads-up

- **Auth errors are still handled by upstream's `_attempt_credential_self_heal`** (not by Fox's failover). That's deliberate — Fox would otherwise double-retry. The `should_failover` filter explicitly excludes `auth_mismatch`.
- **Quota errors are NOT failed over.** Retrying on local doesn't fix a billing-side problem — the user has to address their account. Fox surfaces the original quota error in that case.
- **No auto-retry of the message.** Failover emits the switch event and stops the current stream cleanly. The user re-sends with one tap; their next message hits local. Auto-retry was the v0.5.2 behavior but adds real complexity (rebuilding the agent + replaying context against a different model's context window) for marginal UX gain over a single tap.

### Behind the scenes

- The failover splice spends a real engineering decision: `substitute_function` (in-function textual insertion) was the right tool, not the wrap-and-splice pattern from v0.7.4. `_run_agent_streaming` is a stream-emitting function with no return value to mutate — wrapping would have been the wrong shape. Two anchors, two splice points, each verified unique in upstream v0.51.107 before commit.
- Anchor self-checks fail loudly thanks to v0.7.5's fail-loud bootstrap — if a future upstream refactor breaks either anchor, container boot aborts at CI time and we know immediately.

### What's next

- **v0.7.7:** docs at parity with shipped reality (#310) and Playwright Phase 0 (#264) — replacing the manual smoke checklist as the release gate.
- **v0.7.8:** Playwright Phase 1 (#265, ~12 specs), bootstrap log surfaced to docker logs (#302), one-click diagnostic report button (#293), release-channels split (#306).

---

## [0.7.5] - 2026-05-22

Cleanup and guardrails — the kind of release nobody asks for but everybody benefits from. Eight audit items from a five-perspective code review, bundled into one focused PR. No new features; quieter failures, cleaner offline behavior, fewer ways to ship broken code.

### Fixed

- **Anchor drift no longer ships silently.** Pre-v0.7.5, an upstream refactor that broke a Fox patch's textual anchor was demoted to a WARNING — Fox would boot in a quietly-broken state and ship that to users. Now: `AssertionError` from `bootstrap.apply_all()` aborts container boot, so CI catches it and broken Fox never reaches a release tag.
- **Offline launches no longer fail because of a force re-pull.** The Electron app and `install.sh` used to `docker rmi` the `:stable` image before every pull, discarding the offline fallback. Removed. `docker pull` already checks the manifest for tagged refs and pulls a new digest when `:stable` is re-tagged. Side effect: corporate networks that throttle `ghcr.io` no longer eat a 15-minute stall on every restart.
- **Per-service container logs are bounded.** Added `stdout_logfile_maxbytes=10MB stdout_logfile_backups=3` to all six supervisord program blocks. Was effectively unbounded (per-program defaults are 50MB × 10); a chatty Qdrant or hermes-webui could fill the user's `/data` volume over time.

### Added

- **`FITB_IMAGE` rollback escape hatch.** Users stranded by a bad release can now roll back without waiting for a hotfix: `FITB_IMAGE=ghcr.io/fox-in-the-box-ai/cloud:v0.7.3 ./install.sh` from the terminal, or set the same env var before launching the desktop app. Default container reference unchanged.
- **CI gate: Option B diff guard.** New `.github/workflows/option-b-diff-guard.yml` fails any PR titled `bump(upstream): …` whose diff touches anything outside the upstream-pin allow-list (submodule pointers + `versions.toml`). Closes the last hole in the auto-bump trust model — a typo'd Fox-code PR can no longer silently ship arbitrary code to `:stable`.

### Behind the scenes

- **Removed 459 lines of legacy.** Extracted the duplicated `_helpers.py` (webui + agent sides had already drifted once — webui added `substitute_method`, agent didn't) to a single `fox_overlay/_substitute.py`; both `_helpers.py` files are now 3-line re-export shims. Deleted `tests/test_providers_patch.py` (201 lines, imported a module retired in v0.6.2). Trimmed 60-line "Phase 8 refresh history" docstrings to focused single-purpose ones.
- Test suite: 125/125 passing post-cleanup, basis check clean against current pin (webui v0.51.107).

### What's next

- **v0.7.6: silent failover rebuild.** The other half of the local-AI story — the silent-failover engine that swaps to local on `auth_mismatch` / `quota_exhausted` — is still missing (dropped in the v0.6.0 ATOMIC refactor). Rebuilding it on upstream's new `_classify_provider_error()` + `_attempt_credential_self_heal()` architecture is the v0.7.6 theme.
- v0.7.7: docs at parity with shipped reality (#310) + Playwright Phase 0 (#264).

---

## [0.7.4] - 2026-05-22

Local Ollama, finally working in the picker. Models you pulled via Settings now show up in the chat model dropdown — the missing half of the local-AI happy path (#303).

### Fixed

- **Local Ollama models now appear in the chat model picker (#303 symptoms 1+2).** Pulled models in Settings → Local Ollama → Pull are now selectable from the chat dropdown's OLLAMA group. Previously they appeared in the Settings pulled-list but were invisible to the picker, so users had no way to actually send a message to a local model — making the entire local-AI value prop dead even after a successful pull. Fix is an overlay wrap of upstream's `get_available_models()` that splices in a Fox-detected OLLAMA group sourced from `fox_overlay.webui_modules.ollama.get_models()` (which already owns daemon detection, custom-URL handling per #109, and TTL caching).

### Heads-up

- **Symptom 4 (messages queue with no response) is expected to resolve alongside this fix.** It was likely a downstream cascade: if a user clicked "Use" on a pulled model but the picker still showed the old remote model selected, chat-send routed to the wrong target. Verify per the smoke checklist; if it persists, file a separate issue.
- **Local fallback / silent failover (#303 symptom 3) is still broken** — the v0.5.2 failover engine was dropped in the v0.6.0 ATOMIC refactor (#241), and upstream has since rewritten the error-handling architecture, so rebuilding the engine is non-trivial. Tracked for v0.7.5.

### Behind the scenes

- New patch pattern in `fox_overlay/webui_patches/config.py`: **wrap-and-splice** for post-call mutations, alongside the existing `substitute_function` pattern for in-function modifications. Chosen here because the upstream function is ~1200 lines — anchored textual substitutions deep inside it would be fragile against upstream refactors. The wrap only depends on the function signature + return-shape, both of which have signature self-checks that fail loudly on drift.
- Upstream bug at `nesquena/hermes-webui` is drafted but not yet filed — the overlay is the short-term fix while the long-term resolution is decided. The wrap-and-splice approach means once upstream lands its own ollama branch we just delete the wrap; the guard against double-adding (the OLLAMA group won't appear twice if upstream returns one) makes the transition seamless.
- Regression suite for the wrap: 7 new tests in `tests/test_config_patch.py` covering happy path, daemon-down, no-models, double-add guard, malformed entries, and signature-drift detection.

### What's next

- v0.7.5: rebuild the silent-failover engine (#303 symptom 3) onto upstream's new `_classify_provider_error()` + `_attempt_credential_self_heal()` architecture. Then docs audit (#310).

---

## [0.7.3] - 2026-05-22

Fox gets its own voice. New users meet **Fox in the Box** the agent — laid-back, opinionated, brief by default, no corporate filler.

### Added

- **Fox-specific persona via `SOUL.md` overlay (#297 by @bsgdigital).** New installs now ship with Fox's own persona file: anthropomorphic fox AI assistant, business-first systems thinker, "no bullshit / no sycophancy / 3-line max unless you say deep dive." Replaces upstream Hermes's generic persona. Implemented as an agent-side overlay (`packages/fox-overlay/agent_overlay/SOUL.md`) that the Dockerfile copies over `/app/hermes-agent/docker/SOUL.md` at build time; upstream's entrypoint then seeds it into `$HERMES_HOME/SOUL.md` on first run — the same mechanism upstream uses for its default persona.

### Heads-up for existing installs

The new persona ships in the container but only seeds into your home directory on **first run** (it doesn't overwrite an existing `SOUL.md`). If you've been running Fox already, your `$HERMES_HOME/SOUL.md` is the older / customized version — to pick up the new Fox persona, either:
- Delete `$HERMES_HOME/SOUL.md` (or `/data/SOUL.md` inside the container) and restart, OR
- Edit your existing `SOUL.md` manually with the new content (see the source at `packages/fox-overlay/agent_overlay/SOUL.md`)

A future release may add a migration that surfaces this choice in the UI.

### Behind the scenes

- New **agent-side content-overlay pattern** for Fox-only content files (vs. patches or runtime monkey-patches): place file under `packages/fox-overlay/agent_overlay/`, add a Dockerfile `RUN cp` block at build time. Use this for any future Fox-only content file that needs to overwrite an upstream content file. Mirrors the existing `agent_memory_plugins/` install pattern.
- `FITB_DISABLE_AGENT_OVERLAY=1` build arg short-circuits the SOUL.md copy too, consistent with the other agent-side overlay paths.
- Test suite covering artifact + Dockerfile wiring + manifest classification (`tests/integration/test_fox_soul_overlay.py`). Tests currently run via local `pytest`; CI wiring deferred to a follow-up issue.

### What's next

#303 — Local Ollama integration end-to-end fix is the highest-priority remaining v0.7.x item. v0.7.4 candidate.

---

## [0.7.2] - 2026-05-20

Two safe quick-wins continuing the v0.7.x stabilization train.

### Fixed

- **Recovery banner now hides when you navigate away from Chat (#147 part 2).** The "Your remote provider looks reachable again. Switch off local fallback?" banner was relevant only on the Chat panel but stayed visible across Settings, Workspaces, Insights, and every other tab — blocking page headings + adding noise. Now: visibility tracks the active panel; banner shows on Chat, hides everywhere else, restores when you return. State is preserved (no re-fetch); just a display toggle. Closes #147 (part 1 shipped in v0.7.1 with the opaque-background fix).
- **Windows app icon now embedded in the installed `FoxInTheBox.exe` (#287, reported by bsdigital).** Before: the inner Windows executable shipped with the default Electron icon, while the NSIS installer + uninstaller had the correct Fox icon (so users saw Fox during install but a generic Electron icon afterward). Root cause: our `signAndEditExecutable: false` electron-builder setting (added for Azure Trusted Signing compatibility) disabled BOTH signing AND rcedit's icon embedding. Fix: dedicated `afterPack` hook (`packages/electron/build/afterPack.js`) that runs rcedit only — runs BEFORE NSIS packing, so the signed installer wraps the iconned exe.

### Behind the scenes

- New devDep `rcedit@^4.0.1` in `packages/electron` for the afterPack hook
- Mac path is unaffected (the afterPack hook gates on `electronPlatformName === 'win32'`; `icon.icns` continues to be embedded by electron-builder for darwin builds independently)

### Versioning

Patch v0.7.2 per the v0.7.x cadence policy. Continuing the stabilization train; no minor bump until backlog clears.

---

## [0.7.1] - 2026-05-20

Two quick polish fixes from yesterday's grooming pass.

### Fixed

- **Recovery banner background is now opaque (#147 part 1).** The "Your remote provider looks reachable again. Switch off local fallback to use it?" banner had a translucent teal background that bled chat / Settings content from underneath, making both the banner text and the page hard to read. Switched to a solid dark surface (matching the failover-modal palette) with a teal accent border. Banner is now legible against any content. Part 2 (hide banner when navigating away from Chat) deferred to a follow-up; this v0.7.1 ships the cosmetic-only fix to clear the readability blocker.

### Behind the scenes

- **`build-container.yml`'s Option B `:stable` auto-bump step now logs the actual resulting `:stable` digest** instead of the input digest. Cosmetic fix; the prior log line said `✅ :stable now points at $DIGEST` but `$DIGEST` was the pre-re-tag `:latest` digest — `docker buildx imagetools create` generates a NEW manifest-list digest on each invocation, so the value `:stable` actually points at differs. Re-read the digest after the operation so future Option B runs are accurately debuggable.

### Versioning

Per the v0.7.x cadence policy committed today: this is patch v0.7.1, not a minor bump. v0.7.x continues until the current backlog clears (~37 open issues at v0.7.0 ship).

---

## [0.7.0] - 2026-05-20

**Versioning policy shift.** Fox's version number now reflects **Fox-code changes only**. Upstream `nesquena/hermes-webui` ships several patch versions per day; treating each as a full Fox release was inflating version numbers, churning signed binaries, and burning ~25 min of CI per push for no Fox-side change to report.

From v0.7.0 forward: **upstream-pin advances ship as container-only updates** — the `:stable` Docker tag advances; existing DMG/exe installations pick up the new container automatically on next Electron launch (Electron pulls `:stable` at startup); no DMG re-download required. Fox version bumps happen only when Fox code changes (overlay code, Electron, packaging, smoke fixes, etc.).

### How it works

A commit-message convention. The merge step in `build-container.yml` now auto-bumps `:stable` if-and-only-if the merged commit subject starts with `bump(upstream):`. This is the marker reserved for pure upstream-pin advances. Fox-code commits never use this prefix, so the original FITB#122 protection (`:stable` doesn't follow main on Fox-code commits) is preserved.

### Practical effect

| Change type | What happens | What gets bumped |
|---|---|---|
| Fox-code release (overlay change, bug fix, feature) | Tag `vX.Y.Z` → `release.yml` → DMG + exe + container + GitHub Release | `VERSION`, `package.json`, CHANGELOG, `:stable`, `:vX.Y.Z` |
| Upstream-only bump (just submodule + `versions.toml`) | Merge PR with `bump(upstream): …` subject → `build-container.yml` auto-bumps `:stable` | `:stable` only (no version bump, no DMG/exe, no GitHub Release) |

### What you'll notice

- **DMG / exe downloads bump less often.** Probably 1-2× per month instead of multiple times per week.
- **Container `:stable` continues to advance.** Often daily during active upstream cadence. Existing installs get the latest on Electron relaunch.
- **GitHub Releases** are now reserved for things you actually want to read about. Upstream-pin advances don't create a release; they accumulate (and can be summarized in the next Fox-code release's notes).
- **No user action required for the policy change** — auto-pickup happens via the existing Electron startup flow.

See [`docs/architecture/upstream-overlay.md`](docs/architecture/upstream-overlay.md) → "Versioning policy (Option B)" + "Bumping the upstream pin" for the full operational guide.

### Behind the scenes

- `build-container.yml` merge job gets the new conditional `:stable` auto-bump step (~15 lines, gated on commit-subject prefix).
- `docs/architecture/upstream-overlay.md` Operational section rewritten to cover the policy + the bump-PR conventions.
- `CLAUDE.md` Branching & Release Flow section updated with the `bump(upstream):` convention.
- No code in Fox-overlay or Electron changed.

### What's next

Future improvements (deferred):
- Auto-bump workflow that opens the `bump(upstream): …` PR automatically when an `upstream-update-available` issue is labeled. Today it's still manual: read the auto-issue from `upstream-watch.yml`, run the few commands it lists, open a PR with the right subject. ~5 minutes.
- Date-stamped container tags (e.g. `:container-20260520-abc1234`) for forensic traceability between `:stable` advances.

---

## [0.6.4] - 2026-05-20

Tight stabilization fix for a user-flow gap discovered during v0.6.3 manual smoke. **Closes #281.**

### Fixed

- **Chat model picker now refreshes immediately after activating a new Ollama model (#281).** Before: pull an Ollama model in Settings → Local Ollama → click "Use" → return to chat → the new model wasn't visible in the picker until a full page reload. After: the picker reflects the new model on next open (no reload required). Root cause: `ollama.py`'s `use_model()` was only calling upstream's `reload_config()` (which clears the on-disk models cache) but not `invalidate_models_cache()` (which flushes the in-memory cache the picker actually reads from). Upstream's own convention — see the comment at `api/providers.py:2049-2051` — is to call `invalidate_models_cache()` directly when config changes affect models. The fix wires `ollama.py` into that same convention.

### Behind the scenes

- Removed a dead `from api.providers import _reload_provider_runtime` import inside `use_model()` that has always failed silently (the function was only ever injected into `set_provider_key`'s scope via `extra_globals`, never a module-level name). The matching overlay was retired in v0.6.2 (#269); the misleading try/except block in `ollama.py` is now also gone.

### What's next

After this, the versioning policy shifts to **Option B**: container `:stable` auto-advances when upstream pulls land clean; FITB version (and DMG/exe rebuilds) only bump when Fox-side code changes. Ships as v0.7.0 with the policy as the headline. See [`docs/architecture/upstream-overlay.md`](docs/architecture/upstream-overlay.md) once the policy ships.

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
