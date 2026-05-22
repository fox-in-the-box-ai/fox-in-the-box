# Fox in the Box — Smoke Test Checklist

**When to run:** Before tagging any minor version bump (v0.6.0, v0.7.0, v0.8.0, …) and after any change to onboarding, providers, Tailscale, local fallback, or the Docker image. Per roadmap Rule 5: stabilization pass before every minor release. Per v0.7.x cycle policy: v0.8.0 only when the verification rebuild (Playwright p0 → p1 → p2) covers the manual gates here.

**How long it takes:** ~30 minutes if everything passes. Plan ~2 hours if something fails (fix → rebuild → re-run from the failed step).

**Setup:**

Pull the image you're testing — **don't `docker build` locally** (a local build can mask CI-only behavior; we always smoke what users actually ship). The setup uses port 8788 on the host so the smoke container doesn't collide with a real install on 8787.

```bash
# Pick ONE of the three IMAGE variants below depending on what you're smoking:
IMAGE=ghcr.io/fox-in-the-box-ai/cloud:stable      # the just-released version (today: v0.7.6)
# IMAGE=ghcr.io/fox-in-the-box-ai/cloud:v0.7.6    # explicit pin (use during a multi-version comparison)
# IMAGE=ghcr.io/fox-in-the-box-ai/cloud:latest    # the candidate built from main, pre-tag

docker pull "$IMAGE"
docker rm -f fitb-smoke 2>/dev/null
docker volume rm fitb-smoke-data 2>/dev/null
docker volume create fitb-smoke-data
docker run -d --name fitb-smoke \
  --cap-add=NET_ADMIN --device /dev/net/tun --sysctl net.ipv4.ip_forward=1 \
  -p 127.0.0.1:8788:8787 \
  -v fitb-smoke-data:/data \
  "$IMAGE"
until curl -fsS http://127.0.0.1:8788/health >/dev/null; do sleep 2; done
sleep 15   # extra time for entrypoint operator-grant + supervisord settle
```

**The smoke container is at `http://127.0.0.1:8788`. Your real install (port 8787) is unaffected.**

**Currently testing:** v0.7.6 (= `:stable` as of 2026-05-22). Use `docker manifest inspect "$IMAGE" | jq -r '.manifests[0].digest'` to capture the digest for the current run; record it in the SMOKE log if a release is on the line.

---

## Section A — Container health (5 min)

- [ ] **A1.** `/health` returns 200 with `{"status":"ok"}`
- [ ] **A2.** Container logs show `[entrypoint] Granted foxinthebox tailscale operator access.` within ~15s of startup
- [ ] **A3.** `docker exec fitb-smoke supervisorctl -c /etc/supervisor/supervisord.conf status` — all programs RUNNING except `llama-server` (which should be STOPPED unless local fallback is enabled)
- [ ] **A4.** Architecture check on Apple Silicon: `docker exec fitb-smoke ls /app/llama-cpp/ | grep libggml-cpu | head -3` — output should contain `armv8` or `armv9` flavors (NOT `alderlake`/`cannonlake`/etc which would be x86_64 — that's #114)

---

## Section B — Onboarding wizard (5 min)

Open `http://127.0.0.1:8788` in a fresh browser tab (or incognito).

- [ ] **B1.** Wizard renders at `/setup` (not redirected to `/`)
- [ ] **B2.** Welcome step shows progress dots `1 / 3 — Welcome` (or 4 if Tailscale path)
- [ ] **B3.** Next button is disabled briefly with "Detecting local options…" while probes run, then enables
- [ ] **B4.** If Ollama is running on host: shows "Local model detected" CTA with the model name
- [ ] **B5.** If no Ollama: shows "Run a local model — no API key needed" CTA with "~2.5 GB" size hint
- [ ] **B6.** Click Next → API Key step renders with OpenRouter input + `sk-or-…` placeholder
- [ ] **B7.** Paste a valid OpenRouter key, click Next → Done step renders
- [ ] **B8.** Click "Open Fox" → redirects to `/`, chat UI loads
- [ ] **B9.** Skip footer ("Skip for now — I'll configure later") works on every step

---

## Section C — Settings persistence across restart (3 min)

- [ ] **C1.** Settings → toggle theme to `light`, change a few other things
- [ ] **C2.** Verify `docker exec fitb-smoke ls /data/state/webui/settings.json` exists, foxinthebox-owned (NOT in `/app/.hermes/webui/`)
- [ ] **C3.** `docker restart fitb-smoke`, wait for /health
- [ ] **C4.** Reload browser → all your changes survived
- [ ] **C5.** Same test for hostname-prompted flag and tailscale_* power-user fields

---

## Section D — Provider switching (5 min)

- [ ] **D1.** Settings → Providers → paste an OpenRouter key, save
- [ ] **D2.** Send a chat → real response from configured model
- [ ] **D3.** Pick a different model from the model picker → conversation continues
- [ ] **D4.** Settings → Providers → if Ollama detected, click "Use this model" on a local Ollama model
- [ ] **D5.** Verify config landed in the gateway's path: `docker exec fitb-smoke cat /data/data/hermes/config.yaml | head -10` shows `provider: custom` and the Ollama base URL (NOT in `/app/.hermes/config.yaml`)
- [ ] **D6.** Send a chat → response routes through Ollama (check Ollama's logs on host)
- [ ] **D7.** Switch back to OpenRouter → next chat routes through OR

---

## Section E — Tailscale full lifecycle (8 min)

Requires a real Tailscale account.

- [ ] **E1.** Settings → Network → click "Connect" → status badge transitions Disconnected → Connecting → Needs login
- [ ] **E2.** Auth URL opens in a new browser tab automatically (within ~3 seconds of clicking Connect)
- [ ] **E3.** Click through auth on Tailscale's site → badge flips to **Connected**
- [ ] **E4.** Tailnet URL (e.g. `https://fox-clever.<your-tailnet>.ts.net/`) shown in the tile
- [ ] **E5.** From your phone (also on tailnet): open the URL → chat UI loads (Chrome may show brief HTTPS warning during cert provisioning — refresh after a minute)
- [ ] **E6.** Settings → Network → expand Advanced → set advertise_routes (e.g. `10.0.0.0/24`), accept_dns to false → Save → confirm "Apply now?" prompt → click Yes → reconnects
- [ ] **E7.** Verify in [Tailscale admin console](https://login.tailscale.com/admin/machines): your machine shows the new routes/tags applied
- [ ] **E8.** Click Disconnect → confirms → badge flips to Disconnected, Tailscale admin console shows machine offline
- [ ] **E9.** No orphan `tailscale up` processes: `docker exec fitb-smoke ps aux 2>/dev/null | grep "tailscale up" | grep -v grep` returns nothing
- [ ] **E10.** Re-Connect → fresh auth URL, full flow works again

---

## Section F — Local AI fallback full flow (15 min — includes 2.5 GB download)

- [ ] **F1.** Settings → Providers → "Local fallback" tile shows status "Disabled"
- [ ] **F2.** Toggle ON → status: Downloading (X / 2491 MB)
- [ ] **F3.** Watch the download progress bar increment; should not be stuck at 0% (#index-out-of-bounds = check) and not be a frozen value
- [ ] **F4.** Once at 100%: `sha256_verified: true` in `/api/local-fallback/status` JSON
- [ ] **F5.** Status transitions Downloading → Starting → Warming → **Ready**
- [ ] **F6.** `endpoint: http://127.0.0.1:8643/v1` populated, `server_healthy: true`
- [ ] **F7.** Direct chat works: `docker exec fitb-smoke curl -s -X POST http://127.0.0.1:8643/v1/chat/completions -H 'Content-Type: application/json' -d '{"model":"phi4-mini","messages":[{"role":"user","content":"Reply PONG"}],"max_tokens":5,"stream":false}'` returns a real completion
- [ ] **F8.** Toggle OFF → llama-server stops within ~5s (frees RAM); model file stays on `/data/models/`
- [ ] **F9.** Toggle ON again → goes straight to Ready in seconds (model already on disk, no re-download)

---

## Section G — Reactive failover modal (SUPERSEDED in v0.6.1 — see Section L "v0.6.1 stream-error-retry" row instead)

> **v0.6.1 retired this flow.** The reactive failover modal that shipped in v0.5.x was tightly coupled to upstream-webui's streaming-error path. When upstream refactored that path in v0.51.84, the modal stopped firing (tracked as #255). v0.6.1 replaced it with a simpler universal **"Something went wrong, please try again"** panel that handles every streaming-error class via one surface — see the **v0.6.1 stream-error-retry** row in Section L below for the current test gates.
>
> **If you're smoking a pre-v0.6.1 image** (`:v0.5.4` or older), the G1–G8 gates below still apply. **If you're smoking `:stable` (v0.6.1+) or `:latest`, skip Section G entirely** — run the v0.6.1 Section L row instead.

- [ ] ~~**G1.**~~ ~~Use a configured remote provider that's healthy → send a chat → normal response~~ _(v0.6.1: covered by Section D and the new retry-panel happy-path)_
- [ ] ~~**G2.**~~ ~~Force a failure...~~ _(v0.6.1: covered by Section L "v0.6.1" row item (a))_
- [ ] ~~**G3–G8.**~~ ~~Reactive modal "Enable local fallback?"~~ _(v0.6.1: replaced; manual switch via Settings → Providers is the documented path now)_

---

## Section H — Recovery banner (SUPERSEDED in v0.6.1)

> **v0.6.1 retired this flow** for the same reason as Section G. The recovery banner was the second half of the auto-failover UX — it nudged the user back to remote when remote recovered. v0.6.1's retry-panel approach inverts the model: the user retries when ready, no banner needed.
>
> **If smoking pre-v0.6.1**, the H1–H5 gates below still apply. **For v0.6.1+, skip Section H entirely.**

- [ ] ~~**H1–H5.**~~ ~~Recovery banner "Switch back to remote?"~~ _(v0.6.1: replaced by the Retry button in the stream-error-retry panel — user re-sends via the panel after fixing the underlying issue)_

---

## Section I — Onboarding hostname prompt (#68) (2 min)

- [ ] **I1.** Wipe the volume, fresh container with Tailscale auth completed (so `BackendState=Running`)
- [ ] **I2.** Onboarding completed but no `FOX_HOSTNAME` set → first chat-UI load: modal appears: "Name this Fox"
- [ ] **I3.** Default fills with `fox-<adjective>`
- [ ] **I4.** Save → tailnet hostname applies; modal closes, never reappears
- [ ] **I5.** Wipe + redo, this time click Skip → no rename; modal still never reappears (prompted=true persisted)

---

## Section J — Linux install.sh (5 min, only on minor version bumps)

```bash
docker run --rm -v $PWD:/repo:ro ubuntu:22.04 bash -c "
  apt-get update -qq && apt-get install -qq -y bash shellcheck >/dev/null 2>&1
  bash --version | head -1
  bash -n /repo/packages/scripts/install.sh && echo 'syntax OK'
  shellcheck -S error /repo/packages/scripts/install.sh
"
```

- [ ] **J1.** Bash 5.x syntax check passes on `ubuntu:22.04`
- [ ] **J2.** Same for `ubuntu:24.04`
- [ ] **J3.** ShellCheck reports no errors at `-S error` level
- [ ] **J4.** (Manual) On a real Linux machine, run `install.sh` once: choose Tailscale, complete browser auth, verify the bounded-poll fix from #98 works (no hang)

---

## Section K — Multi-platform binaries (5 min, only on minor version bumps)

After the release tag publishes:

- [ ] **K1.** GitHub Release page has all 5 assets: `arm64-mac.dmg`, `arm64-mac.zip`, `setup-x64.exe`, `x64-mac.dmg`, `x64-mac.zip`
- [ ] **K2.** macOS arm64 DMG: download, `open <dmg>`, drag to Applications, launch — Electron starts, no Gatekeeper rejection. `codesign -dvv` shows Developer ID + `Notarization Ticket=stapled`. `spctl` accepts.
- [ ] **K3.** macOS x64 DMG: same on an Intel Mac (or Rosetta on Apple Silicon — should still launch)
- [ ] **K4.** Windows .exe: install on a Windows machine — SmartScreen accepts (signed by Icemint LLC). Launches Docker Desktop access-mode chooser → wizard.
- [ ] **K5.** All three platforms: walk through full wizard, verify chat works end-to-end with a real provider key

---

## Section L — Regression checks from prior releases (carry forward)

These checklists were testing gates from previous phases. Re-run before any minor bump.

| Phase / Issue | Checks |
|---|---|
| #105 Phase 0 (v0.5.0) | All A–K above |
| #122 v0.5.1 stabilization | (a) `/api/ollama/status` and `/api/local-fallback/status` return **200** (not 302) when onboarding incomplete · (b) "Use [model]" on Step 1 advances to Step 2 (NOT chat) and `onboarding.json` stays `completed: false` until Step 3's "Open Fox" · (c) Step 2 shows "Add OpenRouter (optional)" + "Continue with local only" button when state.localModel set · (d) `/api/tailscale/status` response includes `serve_state` + `serve_error` fields · (e) "Configure HTTPS" retry button visible in Settings → Tailscale tile after Connect · ~~(f) Reactive modal fires on `auth_mismatch` and `quota_exhausted`~~ **(SUPERSEDED v0.6.1 — see v0.6.1 row; this flow no longer exists)** · ~~(g) Recovery banner appears within 30s when fallback is enabled mid-session~~ **(SUPERSEDED v0.6.1)** · (h) `:stable` digest equals `:vX.Y.Z` digest after release tag (no drift from main pushes) · (i) `/app/version.txt` populated with `dev-<sha>` or `vX.Y.Z` (never empty) |
| #127 / #128 / #129 v0.5.2 stabilization | **#127:** (a) `ts-operator-watchdog` RUNNING in supervisord status · (b) Force-clear OperatorUser → restored within 35s · (c) `tailscale up` after force-logout produces auth URL (not `Access denied: checkprefs`). **#128:** ~~(d) `localStorage.setItem('fitb.timeout_modal_ms','5000')` → bad provider key → modal in 5s~~ **(SUPERSEDED v0.6.1 — timeout-modal flow replaced by stream-error-retry panel; see v0.6.1 row)** · ~~(e) "Switch now" with fallback OFF → 400 + reason=disabled~~ **(SUPERSEDED v0.6.1)** · ~~(f) With fallback READY → click Switch now → success + dismiss in ~2.5s~~ **(SUPERSEDED v0.6.1)** · ~~(g) Real SSE arrival post-modal → auto-dismisses~~ **(SUPERSEDED v0.6.1)**. **#129:** ~~(h) Bad cloud key + fallback ready → response includes `*Switched to phi4-mini — re-send your message…*` system note (NO red error)~~ **(SUPERSEDED v0.6.1 — silent auto-failover replaced by explicit Retry panel; user clicks Retry after switching provider in Settings)** · (i) Fallback enabled but model NOT installed → confirm modal "Download local model to keep working?" with size hint · (j) Click Download → progress poll updates inline · (k) On ready → activate → "Ready. Re-send your message…" · (l) Already-local guard: with active = phi4, force a local-side failure → original error surfaces (no redundant `provider_switched`) · ~~(m) Mid-stream truncate: partial tokens then fail → partial cleared, system note appended~~ **(SUPERSEDED v0.6.1 — partial-text wipe now handled by retry panel; see v0.6.1 row item (d))** · (n) `/api/local-fallback/status` includes top-level `ready` field · (o) `/api/local-fallback/activate` registered (200 when ready, 400 + granular `reason` when not) |
| #109 v0.5.3 (custom Ollama URL) | (a) Settings → Providers → Ollama tile has a "Custom Ollama URL" input · (b) Save with `http://192.168.1.50:11434` → probe uses the new URL · (c) Wizard's Ollama detection respects the custom URL · (d) Empty value falls back to host.docker.internal default. **#110** (Tailscale Serve retry button) was already shipped in v0.5.1 hermes-webui#9 — confirm working and close. |
| v0.7.11 Windows-containers detection (#291 — closes; resolves #286 too) | **REQUIRES WINDOWS HARDWARE.** (a) Windows machine with Docker Desktop installed. Verify currently in Linux-containers mode (right-click tray → menu shows "Switch to Windows containers..."). Launch Fox — should start normally (no regression on the happy path). · (b) Switch Docker Desktop to Windows-containers mode (right-click tray → "Switch to Windows containers..." → wait ~30s for the engine to swap). Verify the tray menu now shows "Switch to Linux containers..." (confirms mode switched). · (c) Launch Fox — within ~10s (NOT 4 minutes) a non-recoverable error dialog appears with the message: *"Docker Desktop is in Windows-containers mode. Fox needs Linux containers. Right-click the Docker Desktop tray icon → 'Switch to Linux containers...' → wait for it to finish, then relaunch Fox in the box."* · (d) Verify Fox electron-log (`%AppData%\fox-in-the-box\logs\main.log`) contains the line `Docker Desktop is in Windows-containers mode (docker info reports OSType=windows)`. · (e) NO RunOnce key written, NO reboot prompt — recovery flow was correctly skipped. · (f) Switch back to Linux containers. Relaunch Fox — starts normally. · (g) Optional: 71/71 Electron Jest tests pass (`cd packages/electron && pnpm test`). |
| v0.7.10 Mobile avatar (#299 — closes) | (a) Pull `:stable`. Open the app in a browser at a mobile viewport (DevTools → device toolbar → iPhone SE / 375×667). **Verify**: titlebar shows the Fox avatar photo (circular, ~40px), NOT the Hermes caduceus SVG. · (b) Resize viewport to ≥768px (e.g. iPad Mini 768×1024). **Verify**: desktop layout returns, titlebar hidden (per existing `.app-titlebar { display: none; }` rule). · (c) `curl -I http://127.0.0.1:8787/extensions/images/fox_avatar_cropped.jpg` returns 200 with `content-type: image/jpeg`. · (d) Click the avatar with touch emulation — bounding box ≥44×44px. · (e) Real iPhone Safari check (optional but recommended) — confirms there's no Safari-specific render gotcha. · (f) `qa/playwright` smoke job runs the new `mobile-avatar.spec.ts` and passes (4 assertions across asset + computed style + touch target + SVG hidden). |
| v0.7.9 Bug-fix pass (#145 + #149 + #302) | **#145 workspace persist:** (a) Fresh install. Open chat, ask agent to "write hello.txt with text 'hi'". · (b) Restart Fox app (or `docker restart fox-in-the-box`). · (c) Open chat, ask agent to "read hello.txt". **Verify:** content is "hi" (file survived). · (d) Inspect host: `ls ~/.foxinthebox/workspace` (or platform-equivalent) shows `hello.txt`. **#149 CPU caps:** (e) Open chat, ask agent to "run a CPU-intensive shell command for 30 seconds" (e.g. `dd if=/dev/zero of=/dev/null bs=1M count=10000`). · (f) While that runs, open another browser tab and load chat — WebUI must respond within ~2s, NOT stall waiting for the runaway. · (g) `docker top fox-in-the-box -o pid,ni,cmd` shows the gateway process with niceness 10 (was 0). **#302 bootstrap log:** (h) `docker logs fox-in-the-box 2>&1 \| grep '\[fox-overlay\] bootstrap installed'` returns a match within ~5s of container start (was 0 matches pre-v0.7.9). · (i) The same line also appears in `/data/logs/hermes-webui.err` (file-logged copy preserved). |
| v0.7.8 Playwright Phase 1 partial (5 of 12 specs) | (a) Open any PR that touches `qa/playwright/**` or `packages/fox-overlay/**` — the smoke job runs ALL 5 specs in parallel. **All 5 must pass.** · (b) Sections being incrementally automated: `endpoints-sweep.spec.ts` covers what was Section C item 7 (Fox-claimed endpoints 200 check); `health-deep.spec.ts` covers Section A header health check; `static-overlay.spec.ts` covers Section L row v0.6.0 P2 items (a)-(g); `test-hooks-safety.spec.ts` is new. **Manual checklist Section A-C runs still required until v0.7.10+** when full Phase 1 lands and smoke becomes a required CI check. · (c) Confirm smoke-job runtime in CI is well under 5min total. · (d) Spec failure messages name root-cause hints (verify by reading any one spec's `expect(...).toBe(...)` message argument). |
| v0.7.7 Docs audit + Playwright Phase 0 (#310 + #264) | **#310:** (a) Skim the rewritten docs: `CLAUDE.md` "Current State" reflects v0.7.6+ (not v0.5.3); `docs/RELEASE_WORKFLOW.md` has both Flow A + Flow B sections; `docs/architecture/upstream-overlay.md` mentions v0.7.4 wrap-and-splice + v0.7.5 fail-loud + v0.7.6 multi-substitution patterns. · (b) Acceptance: `git grep -E 'v0\.5\.\|v0\.6\.' -- '*.md' ':!CHANGELOG.md' ':!docs/archive/**'` returns only intentional historical mentions (no stale "current state is v0.5.x" claims). · (c) `docs/tasks/` is gone (moved to `docs/archive/tasks-v0.5/`). **#264:** (d) GitHub Actions → Playwright workflow exists with three jobs (smoke / full / electron-parity). · (e) Open any PR that touches `qa/playwright/**` or `packages/fox-overlay/**` — the smoke job runs and passes against `:stable`. · (f) `FITB_TEST_MODE=1` boot: `docker run -e FITB_TEST_MODE=1 ...` shows the `[fox-overlay] test_hooks ENABLED` warning in stdout; `curl -X POST http://127.0.0.1:8787/test/reset` returns `{"ok": true, "removed": {...}}`. · (g) Production-mode boot (`FITB_TEST_MODE` unset or `=0`): the `[fox-overlay] test_hooks ENABLED` warning is absent; `curl -X POST .../test/reset` returns upstream's 404 (route not registered). |
| v0.7.6 Silent failover engine (#303 symptom 3 — closes #303) | (a) Fresh container boot: log shows `[fox-overlay] patched api.streaming._run_agent_streaming (3 substitutions)` (was 1 substitution pre-v0.7.6). · (b) Enable local fallback per #9 flow (Settings → Providers → Local fallback ON; pull the model via Settings → Local fallback download if not yet present). Wait until `/api/local-fallback/status` returns `ready=true`. · (c) **Success path:** invalidate the remote provider's key (Settings → Providers → set OpenRouter key to `sk-or-v1-invalid`). Send a chat message. **Verify:** chat receives a `provider_switched` SSE event (visible in browser DevTools network → message stream), the upstream error message does NOT appear, and the WebUI's chat shows "Switched to local model. Re-send your message to retry." note. · (d) Re-send the message → response arrives from local model. · (e) **Exception path:** stop the remote provider entirely (e.g., disconnect from internet OR set base_url to an unroutable host like `https://10.255.255.1/v1`). Send a chat message. **Verify:** same `provider_switched` event + UX as (c). · (f) **Auth NOT failover'd (upstream handles it):** restore valid OpenRouter key, then test the auth-self-heal path — upstream's `_attempt_credential_self_heal` should retry automatically; Fox's failover should not fire because `auth_mismatch` is in `_NEVER_FAILOVER_SUBSTRINGS`. · (g) **Quota NOT failover'd:** simulate a quota error (provider-specific; OpenRouter "insufficient credits" usually requires draining the account — verify by manually injecting an error response matching `quota_exhausted` if testable). User should see the original quota error, NOT a switch to local. · (h) **Daemon-not-ready graceful skip:** stop the local llama-server (`docker exec ... supervisorctl stop llama-server`), trigger a remote error. **Verify:** upstream's normal `apperror` flow runs (v0.6.1 retry panel appears), no `provider_switched` event, no exception in container logs. |
| v0.7.5 Cleanup + guardrails (audit bundle) | (a) Fresh container boot: `docker logs fitb-smoke 2>&1 | grep -E "fox-overlay\] bootstrap installed"` returns the dispatcher-frozen line — patches applied normally. · (b) Anchor-drift fail-loud: edit any patch anchor in a local Fox checkout (e.g. break the `reload_config` substitution), rebuild, run container — boot now ABORTS with `AssertionError` in `docker logs` (pre-v0.7.5 it logged a WARNING and continued). · (c) Offline launch: stop Docker's network access OR `docker logout ghcr.io`, then run the Electron app — container starts against the locally-cached `:stable` image (pre-v0.7.5 the pre-pull `rmi` would have erased it). · (d) Rollback hatch: `FITB_IMAGE=ghcr.io/fox-in-the-box-ai/cloud:v0.7.3 ./install.sh` pulls + runs v0.7.3 instead of `:stable`. · (e) Log rotation: confirm `/data/logs/*.log` files cap at ~10MB with up to 3 `.1` / `.2` / `.3` backups (run a chatty workload or `docker exec ... truncate -s 11M /data/logs/hermes-webui.log && docker exec ... supervisorctl signal SIGUSR2 hermes-webui` to force rotation). · (f) Option B diff guard: open a draft PR titled `bump(upstream): test` that touches an unrelated file — the new workflow fails it. (Don't merge.) · (g) `check-overlay-basis.sh` clean against current pin. |
| v0.7.4 Local Ollama picker fix (#303 symptoms 1+2) | (a) Fresh install with Ollama running on host (`http://host.docker.internal:11434`). · (b) Settings → Local Ollama → confirm daemon detected (status green). · (c) Pull a small model (e.g. `phi3:mini` or any installed model). · (d) Return to Chat tab. **Verify**: model picker dropdown shows an **OLLAMA** group with the pulled model selectable. Pre-v0.7.4 the OLLAMA group was missing entirely. · (e) Select the Ollama model and send "hello". **Verify**: response arrives from the local model — this also validates symptom 4 of #303 (was likely a cascade of the picker bug). · (f) Stop Ollama daemon (`brew services stop ollama` on macOS or kill the process). Reload the chat page. **Verify**: picker degrades gracefully — OLLAMA group disappears, no errors in container log, other provider groups (OpenRouter etc.) still render. · (g) Restart Ollama. **Verify**: OLLAMA group reappears after the TTL cache expires (~10s) or after clicking the Settings refresh button. · (h) Check container boot log for `[fox-overlay] wrapped api.config.get_available_models — local Ollama group injection enabled (#303)`. |
| v0.7.3 Fox SOUL.md overlay (#297) | (a) Fresh install (or wipe `/data`): verify `$HERMES_HOME/SOUL.md` contains the Fox persona — `docker exec fitb-smoke grep "Fox in the Box" /data/SOUL.md` returns the matching line. · (b) Container boot log shows `[fox-soul] installed Fox SOUL.md → /app/hermes-agent/docker/SOUL.md`. · (c) Build with `--build-arg FITB_DISABLE_AGENT_OVERLAY=1` → boot log shows `[fox-soul] FITB_DISABLE_AGENT_OVERLAY=1 — skipping SOUL.md override` AND the container's `docker/SOUL.md` is upstream's default (NOT the Fox persona). · (d) Send a chat message in a fresh session → response style reflects new persona constraints (terse, no filler, direct). Subjective but should be obviously different from upstream Hermes's verbose default. · (e) Existing install (pre-v0.7.3 `$HERMES_HOME/SOUL.md` present) → upgrade to v0.7.3 → confirm existing SOUL.md is PRESERVED (not overwritten) per the entrypoint's seed-only-if-absent behavior. |
| v0.7.2 banner tab-aware hide (#147 part 2) + Windows app icon (#287) | **#147 part 2:** (a) Trigger the recovery banner (local fallback enabled, force remote failure + recovery so banner shows on Chat). · (b) Navigate Chat → Settings. **Verify**: banner is HIDDEN on Settings. · (c) Settings → Appearance / Workspaces / any non-Chat tab. **Verify**: banner stays HIDDEN. · (d) Return to Chat tab. **Verify**: banner is VISIBLE again (same state, no re-fetch). · (e) Click Dismiss → banner closes; tab-visibility watcher stops cleanly (no leftover poll). · (f) Click Switch back → banner closes; same. **#287:** (g) On a Windows machine: install the v0.7.2 .exe. After install, locate `%LOCALAPPDATA%\Programs\@fox-in-the-boxelectron\FoxInTheBox.exe` (or the unpacked install dir's `FoxInTheBox.exe`). **Verify**: file icon shown in Explorer matches the Fox icon (NOT the default Electron icon). Pre-v0.7.2 it showed the default Electron icon. · (h) The NSIS installer .exe + uninstaller already had correct icon (worked pre-v0.7.2); confirm those still do (no regression). · (i) macOS DMG: launch + check app icon in Dock — should be Fox icon as before (no regression; the rcedit hook is Windows-only). |
| v0.7.1 recovery banner opacity (#147 part 1) + Option B log accuracy | **#147:** (a) With local fallback enabled, force a remote failure (bad OpenRouter key + retry until banner appears). Wait for remote to recover and the recovery banner to appear at the top of chat. · (b) **Verify**: banner has solid dark background (NOT translucent); no text from chat / Settings bleeds through. · (c) Navigate from Chat → Settings → Appearance; banner stays visible (Part 2 hide-on-non-chat-tabs deferred to follow-up; this row covers only the opacity fix). · (d) Banner text + buttons are legible. **Option B log:** (e) Open the latest `bump(upstream): …` workflow run's "Merge into manifest list" job log; the "✅ :stable now points at" line should show TWO digests — the resulting `:stable` digest AND the input `:latest` digest in parentheses. Pre-v0.7.1 it showed only the input digest (misleading). |
| v0.6.4 picker refresh after Ollama Use (#281) | (a) Fresh container, complete onboarding to chat. · (b) Settings → Local Ollama → pull any Ollama model (e.g. \`phi4-mini\`) — wait for ready. · (c) Click "Use" on the just-pulled model — toast/UI confirms activation. · (d) Return to chat → open model picker → **the just-activated Ollama model appears IMMEDIATELY** without a page reload. (Before #281: page reload required.) · (e) Switch back to remote provider via Settings → Providers → OpenRouter → save. · (f) Re-open chat picker → remote models still show; Ollama model still shows; no orphaned entries. · (g) Container logs after step (c): should show NO failed `ImportError: cannot import name '_reload_provider_runtime'` traceback (the dead import was removed; if it appears, the fix didn't land). |
| v0.6.2 launcher race + retry polish + providers retirement | **#271:** (a) On Mac, launch the signed DMG → wait through wizard until container is healthy and browser opens → **launcher window closes cleanly** (the bug was: launcher stayed visible stuck on "Step 5/6 — Wait for services" even after the browser launched). · (b) Verify in the Electron log: after `[startup-phase] http_healthy ok`, the next line should be `[startup-phase] onboarding_opened ok` with NO new `showProgress` call after `closeProgress` between them. **#267:** (c) Force `auth_mismatch` (bad OpenRouter key, send chat). **Verify:** Fox "Something went wrong" panel appears at bottom AND upstream's inline `**Provider mismatch:** …` markdown is NOT visible in the transcript (was visible in v0.6.1 until Retry click; now wiped immediately on fire). · (d) Click Retry → composer auto-sends prior message; transcript stays clean. · (e) Click Dismiss → panel disappears; the original user message remains in transcript, no upstream error message reappears. **#269:** (f) After saving an API key via Settings → Providers, verify NO `supervisorctl restart hermes-gateway` in container logs (was the overlay's hook; now relies on upstream per-turn reload). · (g) Mid-stream key rotation: while a chat response is streaming, change OpenRouter key in Settings → Save → confirm the in-flight stream is NOT disrupted (was disrupted in v0.6.1 by the overlay's restart). · (h) Container boot log shows `[fox-overlay] webui_patches.apply_all() complete (2 patch modules)` (was 3 — now config + streaming only; providers retired). |
| v0.6.1 stream-error-retry (#254 + #255) | (a) Force `auth_mismatch`: in Settings → Providers, set OpenRouter key to `sk-or-v1-invalid`; send a chat message → Fox **"Something went wrong, please try again"** panel appears at the bottom of chat with a **Retry** + **Dismiss** button. **Known polish gap (filed):** upstream's inline `**Provider mismatch:** …` error message ALSO stays visible in the transcript above the panel until you click Retry; it then gets wiped. v0.6.2 will pop the upstream message immediately on apperror so only the Fox panel shows. · (b) Click Retry → upstream error message gets wiped from transcript, prior user message appears in the composer + auto-sends; chat continues normally (will fail again until a real key is configured — that's expected). · (c) Click Dismiss instead → Fox panel disappears, last user message + upstream error stay in transcript, no retry. · (d) Force `interrupted` (mid-stream break): start a long-running chat response; from another terminal run `docker exec fitb-smoke pkill -KILL -f hermes-gateway` mid-response → panel appears, partial assistant tokens stay in transcript (Retry wipes them). · (e) User-cancelled (`type:cancelled`): start a streaming response, click the Stop button → NO Fox panel should appear (cancel is user-initiated, not an error). · (f) Multiple errors in a row: after panel fires once, click Dismiss; send another message that also errors → panel appears again (no once-per-session lockout). · (g) DOM selectors present after fire: `[data-fitb-retry-panel]` root, `[data-fitb-retry-action="retry"]` button, `[data-fitb-retry-action="dismiss"]` button (these become the Playwright selectors when phase-1 E2E lands per #265). |
| v0.6.0 upstream-separation migration | (a) `forks/hermes-webui` HEAD == pinned tag in `packages/fox-overlay/versions.toml` (and same for `forks/hermes-agent`) · (b) `./packages/fox-overlay/scripts/check-overlay-basis.sh` exits 0 locally · (c) Container boot log includes `[fox-overlay] bootstrap installed: dispatcher frozen, N GET + M POST handlers registered` (N + M match the current `webui_modules/` registrations) · (d) Container boot log includes `[fox-overlay] webui_patches.apply_all() complete` with the current patch count · (e) Agent boot log has **zero** `fox-overlay-failed` warnings · (f) `ls /app/hermes-agent/plugins/memory/` shows `mem0_oss/` (Dockerfile COPY landed) · (g) Fox-claimed endpoints all return 200: `/setup`, `/api/profiles`, `/api/ollama/status`, `/api/tailscale/status`, `/api/local-fallback/status`, `/api/local-models`, `/api/settings/hostname` · (h) `FITB_DISABLE_WEBUI_OVERLAY=1` + `FITB_DISABLE_AGENT_OVERLAY=1` build still produces a container that boots (bisect-flag smoke) · (i) ~~**Known regressions** intentional~~ **OBSOLETE as of v0.6.1**: #254 + #255 are now fixed via the universal stream-error retry panel (see v0.6.1 row below). When smoking `:stable` (v0.6.1+) skip item (i); when smoking a `:v0.6.0` image specifically the regressions are intentional. |
| #138 / #139 / #140 v0.5.4 stabilization | **#138:** (a) Settings → Ollama tile → click "Use this model" → chat picker reflects the new model on next open (no 5-min wait, no reload required) · (b) `_available_models_cache` evicts on real config change (mtime-gated, not first load). **#139:** (c) Open Settings → Tailscale tile in **Safari** → click Connect → fallback link `Click to authenticate Tailscale` is visible in the tile · (d) Click the link → auth completes, status flips to Connected, link disappears · (e) Re-Connect after disconnect → fresh link appears, no leftover from prior attempt. **#140:** (f) Authenticate Tailscale via desktop app or `docker exec ... tailscale up` (bypassing the webui Connect button) → within ~15 seconds of opening Settings, `tailscale serve status` shows :8787 mapped without manual "Configure HTTPS" click · (g) HTTPS-toggle hint visible in the Tailscale tile pointing to admin/dns. |
| Phase 2 v0.6.0 (static overlay) | (a) `curl http://127.0.0.1:8788/extensions/fox-in-the-box.css` returns 200 · (b) `curl --globoff http://127.0.0.1:8788/extensions/fonts/Manrope[wght].woff2` returns 200 · (c) `curl http://127.0.0.1:8788/extensions/images/fox_avatar_cropped.jpg` returns 200 · (d) `curl http://127.0.0.1:8788/extensions/fox-overlay.js` and the 3 other Fox JS files (onboarding-preview, hostname-prompt, fallback-polish) all return 200 · (e) view-source of `/` (post `/api/setup/skip`) shows exactly 1 `<link rel="stylesheet" href="/extensions/fox-in-the-box.css">` and 4 `<script src="/extensions/*.js" defer>` tags injected by `api/extensions.py` · (f) SHA256 of each served `/extensions/*` asset matches the source file under `packages/fox-overlay/webui_static/` · (g) chat empty-state + assistant-message avatars render (no broken-image icon) — visual confirmation that `extensions/images/fox_avatar_cropped.jpg` resolves from `static/index.html` and `static/ui.js`. |
| #4 + #5 Phase 1 (v0.5.5) | Plugin loads cleanly · PII masking detects SSN/CC/phone/email · <30 ms p95 latency · toggle off = no impact |
| #7 Phase 2 (v0.5.6) | All 5 starter rules tested positive + negative · rules don't false-positive on normal conversation |
| #64 Phase 3 (v0.6.0) | Every page screenshot-compared · no overflow / truncation · mobile (375px) renders · onboarding still works |
| #6 Phase 4 (v0.7.0) | Safe messages: zero impact · unsafe messages caught and wiped · hardware probe disables on 8 GB · all prior guards still work · cold start <10s |
| #12 Phase 5 (v0.8.0) | Routine via conversation in <5 min · executes on schedule · failed routine surfaces clear error · all prior features unaffected |

---

## What "PASS" means

- Every box checked
- Any failure → fix it, rebuild, re-run from the failing section onward
- Don't tag if any box is unchecked. The 48-hour soak rule (roadmap Rule 2) starts when the tag actually publishes — not when this checklist starts.

## What's NOT in scope here

- Performance benchmarks (run separately if a release is performance-critical)
- Security audit (run before any release with new attack-surface code)
- Accessibility audit (run before #64 ships and again before v1.0)
- Localization (when i18n work happens; not before v0.7.0)

---

**Last updated:** v0.7.11 — Windows-containers-mode detection (#291 closes; #286 follow-up resolved): docker info OSType probe after pipe ENOENT surfaces actionable error in 10s instead of 4-min WSL repair + reboot loop. 6 new Electron Jest tests; total 71 passing. Verification methodology rule unchanged: run against released `:stable` (or candidate `:latest` for pre-tag), not against a local `docker build` from source. The DMG-equivalent install command is the canonical path:

```bash
docker run -d --name fox-in-the-box \
  --cap-add=NET_ADMIN --device /dev/net/tun --sysctl net.ipv4.ip_forward=1 \
  -p 127.0.0.1:8787:8787 \
  -v "$HOME/Library/Application Support/Fox in the Box:/data" \
  ghcr.io/fox-in-the-box-ai/cloud:stable
```
