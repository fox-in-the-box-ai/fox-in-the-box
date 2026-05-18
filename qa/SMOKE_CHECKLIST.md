# Fox in the Box — Smoke Test Checklist

**When to run:** Before tagging any minor version bump (v0.5.0, v0.6.0, …) and after any change to onboarding, providers, Tailscale, local fallback, or the Docker image. Per roadmap Rule 5: stabilization pass before every minor release.

**How long it takes:** ~30 minutes if everything passes. Plan ~2 hours if something fails (fix → rebuild → re-run from the failed step).

**Setup:**
1. Build the candidate image: `docker build -f packages/integration/Dockerfile -t fitb:smoke .`
2. Reset state: `docker rm -f fitb-smoke 2>/dev/null; docker volume rm fitb-smoke-data 2>/dev/null; docker volume create fitb-smoke-data`
3. Start: `docker run -d --name fitb-smoke --cap-add=NET_ADMIN --device /dev/net/tun --sysctl net.ipv4.ip_forward=1 -p 127.0.0.1:8788:8787 -v fitb-smoke-data:/data fitb:smoke`
4. Wait: `until curl -fsS http://127.0.0.1:8788/health >/dev/null; do sleep 2; done`
5. Wait 15 seconds more for entrypoint to finish (operator grant, etc.)

**The container is at `http://127.0.0.1:8788`. The user's real install (port 8787) is unaffected.**

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

## Section G — Reactive failover modal (3 min)

Requires local fallback to be **OFF** for this section.

- [ ] **G1.** Use a configured remote provider that's healthy → send a chat → normal response
- [ ] **G2.** Force a failure: temporarily set the OR base_url to a dead endpoint (or use an invalid key) → send a chat → error appears in the chat: "No response received: HTTP 4xx" or "Stream interrupted"
- [ ] **G3.** **Reactive modal appears**: "Your provider is having trouble. Want to enable a local AI model as a fallback?"
- [ ] **G4.** Click "Not now" → modal closes
- [ ] **G5.** Trigger another failure in the same tab → modal does NOT re-fire (sessionStorage flag)
- [ ] **G6.** Reload page (clears session flag) → trigger failure → modal CAN fire again
- [ ] **G7.** This time click "Enable" → POST `/api/local-fallback/enable` fires, modal shows "Enabled. Your next failure will silently use local."
- [ ] **G8.** With local now enabled, trigger another remote failure → silent failover, real local response in chat (no error to user)

---

## Section H — Recovery banner (3 min)

Requires local fallback to be **ON** AND a recent remote failure (set up in Section G).

- [ ] **H1.** With local fallback ON, restore the remote provider to working state
- [ ] **H2.** Within ~90s, top banner appears: "Your remote provider looks reachable again. Switch off local fallback to use it?"
- [ ] **H3.** Click "Keep local" → banner closes, no re-appearance this session
- [ ] **H4.** Reload page → banner can re-appear once
- [ ] **H5.** This time click "Switch back" → POST `/api/local-fallback/disable` fires, banner closes, polling stops

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
| #122 v0.5.1 stabilization | (a) `/api/ollama/status` and `/api/local-fallback/status` return **200** (not 302) when onboarding incomplete · (b) "Use [model]" on Step 1 advances to Step 2 (NOT chat) and `onboarding.json` stays `completed: false` until Step 3's "Open Fox" · (c) Step 2 shows "Add OpenRouter (optional)" + "Continue with local only" button when state.localModel set · (d) `/api/tailscale/status` response includes `serve_state` + `serve_error` fields · (e) "Configure HTTPS" retry button visible in Settings → Tailscale tile after Connect · (f) Reactive modal fires on `auth_mismatch` and `quota_exhausted` (set OpenRouter key to garbage with fallback OFF, send chat) · (g) Recovery banner appears within 30s when fallback is enabled mid-session and provider is restored · (h) `:stable` digest equals `:vX.Y.Z` digest after release tag (no drift from main pushes) · (i) `/app/version.txt` populated with `dev-<sha>` or `vX.Y.Z` (never empty) |
| #127 / #128 / #129 v0.5.2 stabilization | **#127:** (a) `ts-operator-watchdog` RUNNING in supervisord status · (b) Force-clear OperatorUser → restored within 35s · (c) `tailscale up` after force-logout produces auth URL (not `Access denied: checkprefs`). **#128:** (d) `localStorage.setItem('fitb.timeout_modal_ms','5000')` → bad provider key → modal in 5s · (e) "Switch now" with fallback OFF → 400 + reason=disabled with actionable copy · (f) With fallback READY → click Switch now → success + dismiss in ~2.5s · (g) Real SSE arrival post-modal → auto-dismisses. **#129:** (h) Bad cloud key + fallback ready → response includes `*Switched to phi4-mini — re-send your message…*` system note (NO red error) · (i) Fallback enabled but model NOT installed → confirm modal "Download local model to keep working?" with size hint · (j) Click Download → progress poll updates inline · (k) On ready → activate → "Ready. Re-send your message…" · (l) Already-local guard: with active = phi4, force a local-side failure → original error surfaces (no redundant `provider_switched`) · (m) Mid-stream truncate: partial tokens then fail → partial cleared, system note appended · (n) `/api/local-fallback/status` includes top-level `ready` field · (o) `/api/local-fallback/activate` registered (200 when ready, 400 + granular `reason` when not) |
| #109 v0.5.3 (custom Ollama URL) | (a) Settings → Providers → Ollama tile has a "Custom Ollama URL" input · (b) Save with `http://192.168.1.50:11434` → probe uses the new URL · (c) Wizard's Ollama detection respects the custom URL · (d) Empty value falls back to host.docker.internal default. **#110** (Tailscale Serve retry button) was already shipped in v0.5.1 hermes-webui#9 — confirm working and close. |
| v0.6.1 stream-error-retry (#254 + #255) | (a) Force `auth_mismatch`: in Settings → Providers, set OpenRouter key to `sk-or-v1-invalid`; send a chat message → upstream's inline error markdown does NOT appear in the transcript; Fox "Something went wrong, please try again" panel appears at the bottom of chat with a Retry button. · (b) Click Retry → the previous user message appears in the composer + auto-sends; chat continues normally (will fail again until a real key is configured — that's expected). · (c) Click Dismiss instead → panel disappears, last user message stays in transcript, no retry. · (d) Force `interrupted` (mid-stream break): start a long-running chat response; from another terminal run `docker exec <container> pkill -KILL -f hermes-gateway` mid-response → panel appears, partial assistant tokens wiped from transcript. · (e) User-cancelled (`type:cancelled`): start a streaming response, click the Stop button → NO Fox panel should appear (cancel is user-initiated, not an error). · (f) Multiple errors in a row: after panel fires once, send another message that also errors → panel appears again (no once-per-session lockout). · (g) `[data-fitb-retry-panel]` element present in DOM after fire, with `[data-fitb-retry-action="retry"]` and `[data-fitb-retry-action="dismiss"]` buttons (these will be the Playwright selectors when E2E lands). |
| v0.6.0 upstream-separation migration | (a) `forks/hermes-webui` HEAD == pinned tag in `packages/fox-overlay/versions.toml` (and same for `forks/hermes-agent`) · (b) `./packages/fox-overlay/scripts/check-overlay-basis.sh` exits 0 locally · (c) Container boot log includes `[fox-overlay] bootstrap installed: dispatcher frozen, N GET + M POST handlers registered` (N + M match the current `webui_modules/` registrations) · (d) Container boot log includes `[fox-overlay] webui_patches.apply_all() complete` with the current patch count · (e) Agent boot log has **zero** `fox-overlay-failed` warnings · (f) `ls /app/hermes-agent/plugins/memory/` shows `mem0_oss/` (Dockerfile COPY landed) · (g) Fox-claimed endpoints all return 200: `/setup`, `/api/profiles`, `/api/ollama/status`, `/api/tailscale/status`, `/api/local-fallback/status`, `/api/local-models`, `/api/settings/hostname` · (h) `FITB_DISABLE_WEBUI_OVERLAY=1` + `FITB_DISABLE_AGENT_OVERLAY=1` build still produces a container that boots (bisect-flag smoke) · (i) **Known regressions** intentional, NOT crashes — verify: mid-stream gateway break shows upstream's apperror surface (no "Stream interrupted" label / no partial-text preservation — #254 deferred); `auth_mismatch`/`quota_exhausted` shows upstream apperror, no auto-failover modal (#255 deferred) — manual switch via Settings → Providers still works. |
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

**Last updated:** v0.6.1 — universal stream-error retry panel (closes #254 + #255). Verification methodology rule unchanged: run against released `:stable` (or candidate `:latest` for pre-tag), not against a local `docker build` from source. The DMG-equivalent install command is the canonical path:

```bash
docker run -d --name fox-in-the-box \
  --cap-add=NET_ADMIN --device /dev/net/tun --sysctl net.ipv4.ip_forward=1 \
  -p 127.0.0.1:8787:8787 \
  -v "$HOME/Library/Application Support/Fox in the Box:/data" \
  ghcr.io/fox-in-the-box-ai/cloud:stable
```
