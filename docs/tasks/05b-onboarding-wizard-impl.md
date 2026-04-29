# Task 05b: Onboarding Wizard — Implementation

| Field         | Value                                                                 |
|---------------|-----------------------------------------------------------------------|
| **Status**    | Ready                                                                 |
| **Executor**  | AI agent                                                              |
| **Depends on**| Task 02, Task 03, **Task 05a approved by Supervisor**                 |
| **Parallel**  | Task 04 (entrypoint.sh) — can run concurrently with this task         |
| **Blocks**    | Task 06 (Electron wrapper — needs a functioning webui to wrap)        |
| **Path**      | `forks/hermes-webui/` (served at `/setup` by the Hermes WebUI server) |

> **Note:** The test file (`tests/test_setup_api.py`) was written and approved
> in task 05a. It already exists in the repo. Your implementation is complete
> when `pytest tests/test_setup_api.py -v` shows **all tests passing**.

---

## Summary

Build a plain HTML/vanilla JS onboarding wizard served at `/setup` by the
Hermes WebUI Python backend. On first container start the wizard collects the
OpenRouter API key and optionally configures Tailscale, then writes config and
unlocks the main UI.

No React, no build step, no bundler. The wizard is a single static HTML file
plus a small CSS file loaded from the Python server. The Python backend gains a
handful of `/api/setup/*` endpoints that handle validation, subprocess
management, and state persistence.

---

## Prerequisites

1. **Task 02 complete** — `forks/hermes-webui/` submodule is present and the
   repo structure is in place.
2. **Task 03 complete** — the Docker image builds successfully and
   `hermes-webui` runs inside supervisord.
3. **Task 04 can run in parallel** — this task does not depend on the full
   entrypoint.sh (the stub from Task 03 is sufficient for local development).
4. The agent has read access to `forks/hermes-webui/` to inspect the existing
   server entry point before adding endpoints.

---

## Design Constraints

| Concern           | Decision                                                         |
|-------------------|------------------------------------------------------------------|
| Frontend          | Plain HTML5 + vanilla JS + minimal CSS — **no React, no bundler** |
| Served from       | `forks/hermes-webui/` — the existing Hermes WebUI Python server  |
| New routes        | `GET /setup`, `POST /api/setup/*`, `GET /api/setup/*`            |
| State file        | `/data/config/onboarding.json`                                   |
| Env file          | `/data/config/hermes.env`                                        |
| Redirect guard    | Middleware in server.py — redirects to `/setup` while not complete |
| QR code           | Generated client-side from qrcode.js (CDN, pinned version)       |
| Styling           | Single `setup.css` — mobile-first, no framework                  |
| Branding          | Text-only — no image assets required for this task               |

---

## Implementation

### Step 1 — Inspect the existing hermes-webui server

Before writing any code the agent **must** identify the correct entry point
file and understand the existing routing pattern:

```bash
ls forks/hermes-webui/
# Look for: server.py  app.py  main.py  src/server.py
cat forks/hermes-webui/server.py   # or whichever file is the entry point
```

Key things to determine:
- Which Python web framework is in use (Flask, FastAPI, aiohttp, etc.)
- How existing routes are registered (decorators, router objects, blueprints)
- Where static files are served from

All new endpoints must follow the same pattern as the existing code.

---

### Step 2 — Add onboarding middleware

In `server.py` (or a new `setup.py` imported by `server.py`), add middleware
that runs on every incoming request:

**Logic:**

```python
ONBOARDING_PATH = "/data/config/onboarding.json"

def onboarding_complete() -> bool:
    try:
        with open(ONBOARDING_PATH) as f:
            return json.load(f).get("completed", False)
    except (FileNotFoundError, json.JSONDecodeError):
        return False
```

**Redirect rule:**
- If `onboarding_complete()` is `False`, AND the request path does **not**
  start with `/setup` or `/api/setup/`, redirect to `/setup`.
- If `onboarding_complete()` is `True`, pass the request through normally.

The check must be a per-request check (not cached at startup) so that
completing the wizard immediately unlocks the main UI without a restart.

---

### Step 3 — Backend endpoints

Add the following endpoints. Adjust the exact routing syntax to match the
framework already in use.

#### `GET /setup`
Serve `setup.html` from the webui static directory.

---

#### `POST /api/setup/openrouter`

**Request body:** `{"key": "sk-or-..."}`

**Validation:**
- Key must be a non-empty string.
- Key must start with `sk-`.
- Reject keys longer than 512 characters.

**On success:**
1. Write (or append) `OPENROUTER_API_KEY=<key>` to `/data/config/hermes.env`
   (create the file and parent directory if they do not exist).
2. Return `{"ok": true}`.

**On failure:**
Return HTTP 400 with `{"ok": false, "error": "<reason>"}`.

---

#### `POST /api/setup/tailscale/start`

Start `tailscale login --timeout=120` as a background subprocess.

Store a module-level state object:

```python
tailscale_state = {
    "status": "waiting",   # waiting | url_ready | connected | error
    "login_url": None,
    "tailnet_url": None,
    "error": None,
}
```

Launch a daemon thread that:
1. Runs `tailscale login --timeout=120`.
2. Reads stdout/stderr line by line.
3. When a line matching `https://login.tailscale.com/...` is found, sets
   `status = "url_ready"` and `login_url = <url>`.
4. When `tailscale status --json` succeeds and returns a node with
   `Online: true`, sets `status = "connected"` and
   `tailnet_url = "https://<hostname>.<tailnet>.ts.net"`.
5. On subprocess error or timeout, sets `status = "error"` and
   `error = <message>`.

Return `{"ok": true}` immediately (the client polls for status).

If a Tailscale process is already running, return `{"ok": true}` without
starting a second one.

---

#### `GET /api/setup/tailscale/status`

Return the current `tailscale_state` dict as JSON:

```json
{
  "status": "url_ready",
  "login_url": "https://login.tailscale.com/a/...",
  "tailnet_url": null,
  "error": null
}
```

---

#### `POST /api/setup/complete`

**Request body:** `{"tailscale_connected": true|false}`

1. Ensure `/data/config/` directory exists.
2. Write `/data/config/onboarding.json`:

```json
{
  "completed": true,
  "completed_at": "<ISO 8601 UTC timestamp>",
  "tailscale_connected": <bool>
}
```

3. Return `{"ok": true}`.

---

#### `POST /api/setup/restart`

Restart the Hermes services so they pick up the newly written `hermes.env`:

```bash
supervisorctl -c /etc/supervisor/supervisord.conf restart hermes-gateway hermes-webui
```

Run this as a subprocess. Return `{"ok": true}` if exit code is 0, otherwise
`{"ok": false, "error": "<stderr>"}`.

> **Note:** The webui process itself is being restarted here. The client
> should handle a brief disconnect and retry `GET /` after 2–3 seconds.

---

### Step 4 — Frontend: `setup.html`

Save to `forks/hermes-webui/static/setup.html` (or wherever the framework
serves static files from — confirm in Step 1).

#### Overall page structure

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Fox in the Box — Setup</title>
  <link rel="stylesheet" href="/static/setup.css">
</head>
<body>
  <div id="wizard">
    <div id="progress-bar"><!-- step indicators injected by JS --></div>
    <div id="step-container"><!-- active step rendered by JS --></div>
  </div>
  <script src="https://cdn.jsdelivr.net/npm/qrcode@1.5.3/build/qrcode.min.js"
          integrity="sha384-..."
          crossorigin="anonymous"></script>
  <script src="/static/setup.js"></script>
</body>
</html>
```

> **SRI hash:** Generate the correct `integrity=` hash for the pinned qrcode.js
> version before writing the file:
> ```bash
> curl -fsSL https://cdn.jsdelivr.net/npm/qrcode@1.5.3/build/qrcode.min.js \
>   | openssl dgst -sha384 -binary | openssl base64 -A
> ```

Only **one step is visible at a time**. All step HTML is rendered by JS into
`#step-container`; previous steps are hidden (not removed) so the back button
can restore them without re-fetching.

---

#### Progress indicator

At the top of the wizard render four step indicators:

```
● ─── ○ ─── ○ ─── ○
1/4  Welcome
```

- Filled circle = completed or active step.
- Empty circle = future step.
- Label shows `<current>/<total>` and the step name.
- Update on every step transition.

---

#### Step 1 — Welcome

```
🦊 Fox in the Box

Let's get you set up.

Language: [English ▾]   ← <select> disabled, English only for now

                              [ Next → ]
```

- The language selector is a `<select>` with `<option value="en">English</option>`.
  Set `disabled` attribute and add a tooltip/note "More languages coming soon".
- "Next →" advances to Step 2.

---

#### Step 2 — OpenRouter API Key

```
OpenRouter API Key

Fox uses OpenRouter to access AI models.

[ sk-...                                    ]
  Get your free key at openrouter.ai ↗

                              [ Next → ]
```

- Input type `password` (toggleable to `text` via a show/hide button).
- On "Next →" click:
  1. Client-side validation: non-empty, starts with `sk-`. Show inline error
     (red border + message below input) without calling the API.
  2. If client-side passes: `POST /api/setup/openrouter` with `{key: value}`.
  3. On `{"ok": true}` → advance to Step 3.
  4. On `{"ok": false}` → show `error` message from response in red below input.
- "Next →" button shows a spinner while the request is in flight and is
  disabled to prevent double-submit.

---

#### Step 3 — Tailscale (optional)

```
Secure Remote Access  (optional)

Tailscale gives you HTTPS access from anywhere —
required for mobile / PWA use.

[ Set up Tailscale ]

                              [ Skip for now → ]
```

**"Set up Tailscale" button flow:**

1. `POST /api/setup/tailscale/start` — show spinner.
2. Begin polling `GET /api/setup/tailscale/status` every 2 seconds.
3. Status transitions:

   | Status      | UI shown                                              |
   |-------------|-------------------------------------------------------|
   | `waiting`   | Spinner + "Waiting for Tailscale…"                    |
   | `url_ready` | Login URL as a clickable link + QR code canvas        |
   | `connected` | Green checkmark + tailnet URL (clickable) + "Continue →" button |
   | `error`     | Red error message + "Try again" button                |

4. QR code: call `QRCode.toCanvas(canvasEl, loginUrl, {width: 200})` once
   `login_url` is available.
5. When `connected`: stop polling, show "Continue →" button that advances to
   Step 4.

**"Skip for now" link:**
- Stops any in-progress polling.
- Advances directly to Step 4 with `tailscale_connected = false`.

---

#### Step 4 — Done

```
🦊 Fox is ready!

Access Fox at:
  • http://localhost:8787
  • https://<tailnet-url>   ← only shown if tailscale_connected

                              [ Open Fox ]
```

**"Open Fox" button click:**

1. `POST /api/setup/complete` with `{tailscale_connected: <bool>}`.
2. On success: `POST /api/setup/restart`.
3. Show "Restarting…" message for 3 seconds.
4. Redirect to `/`.

If `/api/setup/restart` fails, still redirect to `/` — the config is written
and the wizard is complete; the user can manually restart if needed.

---

### Step 5 — `setup.css`

Save to `forks/hermes-webui/static/setup.css`.

Requirements:
- Mobile-first (`max-width: 480px` centered card on desktop).
- System font stack (`-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif`).
- Step container has padding so content never touches screen edges on mobile.
- Error states: `.error-msg { color: #d32f2f; font-size: 0.875rem; margin-top: 4px; }`,
  input with error gets `border-color: #d32f2f`.
- Success state: `.success { color: #388e3c; }`.
- Primary button: full-width on mobile, auto-width on desktop, clear focus ring.
- No external fonts, no animations beyond a simple CSS spinner.
- Accessible: all inputs have `<label>`, buttons have descriptive text,
  focus order follows reading order.

---

### Step 6 — `setup.js`

Save to `forks/hermes-webui/static/setup.js`.

Structure:

```js
// State
const state = {
  currentStep: 1,
  totalSteps: 4,
  apiKey: '',
  tailscaleConnected: false,
  tailnetUrl: null,
  pollInterval: null,
};

// Step renderers
function renderStep(n) { /* calls renderStep1/2/3/4 */ }
function renderStep1() { /* Welcome */ }
function renderStep2() { /* API key */ }
function renderStep3() { /* Tailscale */ }
function renderStep4() { /* Done */ }

// Navigation
function advance(n) {
  state.currentStep = n;
  renderStep(n);
  updateProgress(n);
}

// API helpers
async function post(path, body) { /* fetch wrapper, returns parsed JSON */ }
async function get(path)  { /* fetch wrapper */ }

// Tailscale polling
function startTailscalePoll() { /* sets state.pollInterval */ }
function stopTailscalePoll()  { /* clears state.pollInterval */ }

// Progress bar
function updateProgress(step) { /* updates #progress-bar DOM */ }

// Entry point
document.addEventListener('DOMContentLoaded', () => renderStep(1));
```

Keep the entire file under 300 lines. Prefer `async/await` over raw `.then()`.
Do not use `eval`, `innerHTML` for user-supplied data, or deprecated APIs.

---

## File Checklist

After completing this task the following files must exist:

```
forks/hermes-webui/
├── server.py               ← modified: new routes + middleware added
├── static/
│   ├── setup.html          ← new
│   ├── setup.css           ← new
│   └── setup.js            ← new
└── tests/
    └── test_setup_api.py   ← new (pytest)
```

> If `forks/hermes-webui/` uses a different static directory (e.g., `public/`,
> `www/`), place the files there and update the route accordingly.

---

## Acceptance Criteria

All criteria must pass before this task is considered complete.

| # | Criterion | How to verify |
|---|-----------|---------------|
| 1 | Fresh container with `onboarding.completed=false` (or missing `onboarding.json`) — any URL redirects to `/setup` | `curl -I http://localhost:8787/` returns `302` → `/setup` |
| 2 | `GET /setup` returns HTTP 200 with `Content-Type: text/html` | `curl -si http://localhost:8787/setup \| head -5` |
| 3 | Valid `sk-` key accepted: `POST /api/setup/openrouter {"key":"sk-test"}` returns `{"ok":true}`, `hermes.env` written | Check file contents after POST |
| 4 | Invalid key (missing `sk-` prefix) returns HTTP 400 `{"ok":false,...}`, UI shows red error, step does **not** advance | Manual browser test + unit test |
| 5 | Tailscale "Skip for now" works — wizard advances to Step 4 without any Tailscale calls | Manual browser test |
| 6 | Tailscale connect flow: `status=connected` reached after auth, tailnet URL displayed in Step 3 and Step 4 | Manual test with real Tailscale account (or mock in unit tests) |
| 7 | `POST /api/setup/complete` writes `onboarding.json` with `completed: true` | Read file after POST |
| 8 | After completion, `GET /` returns HTTP 200 (no redirect loop) | `curl -I http://localhost:8787/` |
| 9 | Completed container restart — `GET /` does **not** redirect to `/setup` | Stop + start container with existing `/data` volume |
| 10 | Entire wizard is usable on a 375 px wide mobile browser (no horizontal scroll, tap targets ≥ 44 px) | Chrome DevTools mobile emulation |

---

## Test Approach

### Unit tests (`forks/hermes-webui/tests/test_setup_api.py`)

The test file already exists — it was written and approved in task 05a.
Run it; make it pass. Do not modify the tests to fit your implementation.
If a test seems wrong, flag it in `DONE.md` and let the Supervisor decide.

```bash
cd forks/hermes-webui
pytest tests/test_setup_api.py -v
```

**Placeholder — see 05a for the full test list:**

| Test | Description |
|------|-------------|
| `test_redirect_when_not_complete` | Request to `/` with missing `onboarding.json` → 302 to `/setup` |

> Full list of 12 required test cases is in `docs/tasks/05a-onboarding-wizard-tests.md`.

Run tests with:

```bash
cd forks/hermes-webui
pytest tests/test_setup_api.py -v
```

All tests must pass.

### Browser smoke test checklist (manual)

Run the container and open `http://localhost:8787` in a browser. Work through
each item:

- [ ] Navigating to `http://localhost:8787/` redirects to `/setup`
- [ ] Step 1 loads with Fox heading, language selector, and Next button
- [ ] Progress bar shows `1 / 4`
- [ ] Language selector is visible but disabled
- [ ] Next → advances to Step 2 (API key)
- [ ] Clicking Next on Step 2 with empty input shows red inline error
- [ ] Entering `notvalid` (no `sk-` prefix) shows red inline error
- [ ] Entering `sk-test` submits successfully and advances to Step 3
- [ ] Step 3 shows "Set up Tailscale" and "Skip for now"
- [ ] "Skip for now" advances to Step 4
- [ ] Step 4 shows `localhost:8787` URL and "Open Fox" button
- [ ] Tailnet URL section is hidden (Tailscale was skipped)
- [ ] "Open Fox" writes completion, waits 3 s, redirects to `/`
- [ ] After redirect, `GET /` returns the main UI (no `/setup` redirect)
- [ ] Restart the container with existing `/data` — `/` loads directly, no wizard

---

## Notes for the Agent

- **One step visible at a time.** Use a JS `state.currentStep` variable.
  Show/hide with CSS class toggles, not DOM removal — the back button (if
  implemented) should work without re-running side effects.

- **No image assets needed.** Use the 🦊 emoji for the fox logo until a real
  SVG is available. Keep a `<!-- TODO: replace with SVG logo -->` comment.

- **Keep it clean.** This is the first thing users see. Prefer generous
  whitespace over decoration. When in doubt, remove rather than add.

- **SRI for CDN scripts.** Generate the correct SHA-384 hash for the pinned
  qrcode.js version and include the `integrity=` attribute. Do not load CDN
  scripts without SRI.

- **Never log the API key.** The key must not appear in server logs, subprocess
  args, or error messages.

- **Graceful `/data` missing.** The middleware must not crash if `/data/config/`
  does not exist — treat a missing `onboarding.json` as `completed: false`.

- **Framework-first.** Read the existing `server.py` before writing any new
  code. Match the style, error handling, and routing patterns already in use.
  Do not introduce a second web framework.

---

## Dependencies / Next Steps

| Task | Depends on this task because…                                         |
|------|-----------------------------------------------------------------------|
| 06   | Electron wrapper needs the webui to be stable and not hijack all routes |
| 07/08 | Install scripts can reference the wizard as the first-run UX          |
