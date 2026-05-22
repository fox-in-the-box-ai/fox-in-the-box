# Fox WebUI: Build-vs-Fork Analysis

**Status:** RESEARCH COMPLETE / AWAITING DECISION
**Date:** 2026-05-16
**Author:** Architect 2 (build-our-own-WebUI feasibility)
**Audience:** Dennis Vorobyov (owner). Read alongside `upstream-separation-plan.md` (foundational research) and `upstream-migration-execution-plan.md` (Architect 1 lane).

---

## 0. TL;DR (read this first)

**Recommendation: do NOT replace hermes-webui with a Fox-owned React UI right now. Execute the 12-day Architect-1 overlay/patch-series migration; defer the React rewrite until after v0.6.0 ships and Phase 1 (Guardrails) is in production.** When you do build a Fox UI, build **Path A** (React frontend on top of the existing Python backend) — not Path B (full backend rewrite).

The cadence question — "based on hermes-webui's shipping schedule, how solid is them as a UI choice?" — has a sharper answer than the framing suggests: **upstream is shipping aggressively, but the surface Fox actually consumes is small, well-bounded, and stable enough**. The real risks are (a) `nesquena` is the bus-factor and (b) hermes-webui is tightly coupled to hermes-agent's in-process Python contracts. Those risks both *grow*, not shrink, if Fox writes its own UI without first owning the agent contract.

The 12-day Architect-1 plan reduces Fox's ongoing patch surface from "every file conflicts" to **2 patched files / 9 lines** in webui and **0 patched files** in agent, with ≤ 1 hour/week to track upstream. A full Fox-owned React rewrite is **35–55 engineering-days for Path A** and **65–110 engineering-days for Path B**, with permanent ownership cost of every endpoint contract and every feature upstream ships (e.g., Kanban v1) thereafter.

The most important fact to surface: **Fox's webui code calls into hermes-agent's Python directly via 18 distinct module imports across 49 import sites** (`agent.*`, `hermes_cli.*`, `cron.*`, `tools.*`). A new Fox-owned backend has to reproduce that surface or stay in-process Python — which is why Path B is so much more expensive than the React framing implies.

---

## 1. Surface-area audit

This section catalogs what a replacement must provide. Numbers in this section come from grepping the live deployed pin (`hermes-webui` at commit `62c0854`).

### 1.1 HTTP endpoints Fox's frontend depends on

**Total:** 158 distinct endpoint conditions in `api/routes.py` (`grep -cE 'parsed.path == ' api/routes.py`). Of those, ~140 are `==` exact matches and ~18 are `startswith` prefixes. Grouped:

| Group | Endpoints (sample) | Owner | Stability |
|---|---|---|---|
| **Auth** | `/api/auth/login`, `/api/auth/logout`, `/api/auth/status`, `/login` | Upstream | High |
| **Health/static** | `/health`, `/static/*`, `/extensions/*`, `/favicon.ico`, `/manifest.json`, `/sw.js` | Upstream | High |
| **Sessions (CRUD)** | `/api/session`, `/api/sessions`, `/api/session/{new,delete,rename,duplicate,branch,move,pin,update,clear,truncate,undo,retry,archive,compress,export,import,import_cli,handoff-summary,conversation-rounds}`, `/api/sessions/search`, `/api/sessions/cleanup{,_zero_message}` | Upstream | **Hot**: `api/routes.py` grew +1,510/-98 lines under Fox; upstream adds endpoints monthly |
| **Chat / streaming** | `/api/chat`, `/api/chat/{start,cancel,steer,stream,stream/status}` | Upstream | **Hot**: this is where SSE protocol lives |
| **Approvals (interactive tool calls)** | `/api/approval/{pending,respond,stream,inject_test}` | Upstream | Stable |
| **Clarify (mid-stream Q&A)** | `/api/clarify/{pending,respond,stream,inject_test}` | Upstream | Stable |
| **Models** | `/api/models`, `/api/models/live`, `/api/default-model`, `/api/reasoning`, `/api/personalities`, `/api/personality/set` | Upstream | Medium |
| **Providers** | `/api/providers`, `/api/providers/delete` | Upstream + Fox (custom OpenAI-compatible additions in flight, #144) | **Hot for Fox** |
| **Settings** | `/api/settings`, `/api/settings/hostname`, `/api/settings/hostname/dismiss-prompt` | Upstream + Fox (hostname is Fox) | Mixed |
| **Profiles** | `/api/profiles`, `/api/profile/{active,create,delete,switch}` | Upstream | Stable |
| **Workspaces** | `/api/workspaces`, `/api/workspaces/{add,remove,rename,reorder,suggest}` | Upstream | Stable |
| **Projects** | `/api/projects`, `/api/projects/{create,delete,rename}` | Upstream | Stable |
| **Files (filesystem ops)** | `/api/file`, `/api/file/{create,create-dir,delete,raw,rename,reveal,save}`, `/api/list` | Upstream | Stable |
| **Skills** | `/api/skills`, `/api/skills/{content,delete,save}` | Upstream | Stable |
| **Cron / routines** | `/api/crons`, `/api/crons/{create,delete,history,output,pause,recent,resume,run,status,update}` | Upstream | Stable (will grow when Fox does Phase 5 routines) |
| **MCP servers** | `/api/mcp/servers` | Upstream | Stable |
| **Memory (mem0)** | `/api/memory`, `/api/memory/write` | Upstream + Fox (mem0_oss plugin) | Stable |
| **OAuth (Codex)** | `/api/oauth/codex/{start,poll}` | Upstream | New |
| **Updates** | `/api/updates/{check,apply,force}` | Upstream + Fox patches | **Fox-modified** |
| **Rollback** | `/api/rollback/{list,diff,restore}` | Upstream | Stable |
| **Background tasks** | `/api/background`, `/api/background/status` | Upstream | Stable |
| **Insights / git-info / btw** | `/api/insights`, `/api/git-info`, `/api/btw` | Upstream | Stable |
| **Terminal** | `/api/terminal/{start,close,input,output,resize}` | Upstream | Stable |
| **Upload / transcribe / media** | `/api/upload`, `/api/upload/extract`, `/api/transcribe`, `/api/media` | Upstream | Stable |
| **Commands / gateway / admin** | `/api/commands`, `/api/gateway/status`, `/api/admin/reload` | Upstream | Stable |
| **Setup / onboarding (Fox-replaced)** | `/setup`, `/api/setup/{welcome,openrouter,complete,skip,restart}` | **Fox-owned** (replaces upstream) | **Frozen by Fox** |
| **Ollama (Fox)** | `/api/ollama/{status,models,pull,delete,refresh,use-model}` | **Fox-owned** | Stable |
| **Tailscale (Fox)** | `/api/tailscale/{status,up,up/poll,logout,serve}` | **Fox-owned** | Stable |
| **Local fallback (Fox)** | `/api/local-fallback/{status,enable,disable,activate,remote-health}`, `/api/local-models`, `/api/local-models/{id}/progress` | **Fox-owned** | Stable |

**Reality check:** There are >100 upstream endpoints Fox's frontend depends on **transitively** (i.e., the existing UI calls them, but Fox itself doesn't customize them). A from-scratch React UI must implement client integration for every one of those if we want feature parity (skills CRUD, file browser, terminal, cron, OAuth, MCP servers, etc.).

A Fox UI that targets only "chat + onboarding + settings + Tailscale" — i.e., the Fox-distinctive surface — is a non-starter; it would be a regression from what hermes-webui already provides.

### 1.2 SSE streams

Five SSE endpoints, all consumed by the frontend via `EventSource`:

| Stream | Consumer (file:line) | Purpose | Owner |
|---|---|---|---|
| `/api/chat/stream?stream_id=…` | `messages.js:1176, 1331, 1988` | The main streaming chat token feed | Upstream (Fox patches `api/streaming.py` for failover) |
| `/api/sessions/gateway/stream` | `sessions.js:1112` (with HEAD probe at `:1082`) | Real-time gateway session updates (CLI mirroring) | Upstream |
| `/api/approval/stream?session_id=…` | `messages.js:1508` | Tool-call approval prompts | Upstream |
| `/api/clarify/stream?session_id=…` | `messages.js:1870` | Mid-stream clarify Q&A | Upstream |
| `/api/local-models/{id}/progress` | `panels.js:4056` | Local model download progress | **Fox** |
| `/api/terminal/output` | `terminal.js:378` | Terminal session output (PTY tail) | Upstream |

The chat-stream protocol is **not** a documented contract. It is a JSON-encoded SSE event stream with at least these events: `delta`, `tool_call`, `tool_result`, `error`, `provider_switched` (Fox-added), `title_status`, `usage`, plus typed events on the approval/clarify channels (`initial`, `clarify`, `pending`, etc.). A Fox-owned frontend has to either mirror the upstream event taxonomy bug-for-bug, or adapt to its evolution every release.

### 1.3 Static assets served

| Asset | Owner |
|---|---|
| `static/index.html` (1,212 lines, 174+ Fox-modified) | Upstream + Fox shell wrapper |
| `static/style.css` (3,052 lines) | Upstream + Fox theme overrides (86 lines) |
| `static/{boot,sessions,messages,panels,ui,commands,workspace,terminal,login}.js` (~13k lines) | Upstream |
| `static/i18n.js` (7,814 lines, **7,339 keys across multiple locales**) | Upstream + Fox keys |
| `static/sw.js` (PWA service worker) | Upstream + Fox patches |
| `static/manifest.json` (PWA) | Upstream + Fox |
| `static/fonts/{Manrope,Sora}[wght].woff2` | **Fox** |
| `static/vendor/smd.min.js` (markdown renderer) | Upstream |
| `static/icons.js` (90 lines, inline SVG sprite) | Upstream |
| `static/{fox-in-the-box,setup,fallback-polish,hostname-prompt,onboarding-preview}.{css,js,html}` | **Fox** (additive — already isolated) |
| `static/fox_avatar_cropped.jpg`, `apple-touch-icon.png`, favicon variants | **Fox branding** |

The hermes-webui frontend is **NOT a SPA**. It's an HTML page that loads ~17 vanilla-JS files in order; each registers globals on `window`. Theming is done via CSS custom properties cascading from `:root` overrides defined in `fox-in-the-box.css`. The 7,339 i18n keys are a real surface.

### 1.4 Server-side state

Held in the Python process and on disk under `~/.hermes/webui/` (or `HERMES_WEBUI_STATE_DIR`):

| State | Location | Purpose |
|---|---|---|
| `STATE_DIR/sessions/*.json` + `_index.json` + `.bak` files | Disk | Session messages, atomic-write pattern, `.bak` is the #1558 data-loss fix |
| `STATE_DIR/settings.json` | Disk | All settings the UI persists |
| `STATE_DIR/workspaces.json`, `last_workspace.txt` | Disk | Workspace list |
| `STATE_DIR/projects.json` | Disk | Projects |
| `STATE_DIR/models_cache.json` | Disk | Cached provider model lists |
| `~/.hermes/.env` | Disk (in `$HERMES_HOME`, NOT state dir) | Provider API keys (Fox-relevant: written by both setup wizard and Settings panel) |
| `_RUNNING_CRON_JOBS: dict[str, float]` | In-process | Cron job tracking |
| `_approval_sse_subscribers: dict[str, list[Queue]]` | In-process | Approval SSE fan-out |
| `_models_cache_path` + `_active_profile_for_live_models_cache` | In-process | Live model cache |
| `_MESSAGING_SESSION_METADATA_CACHE` | In-process | Mirrors `~/.hermes/sessions/sessions.json` from agent |
| Active session pointer | URL/cookie (`/session/<id>`) + `STATE_DIR` | UI state |
| In-flight stream registry | In-process keyed by `stream_id` | Lets reload reattach |
| Session-recovery on startup (Fox) | In-process | Reads `.bak` files; restores on partial-write |
| Per-request profile context | Cookie + thread-local | Multi-profile support |
| Gateway watcher thread | Background thread | Mirrors agent session JSON |

A Fox-owned backend would need to reimplement (or share) all of these. Sessions on disk *must* stay JSON-compatible because the agent CLI also reads them.

### 1.5 Direct-to-disk operations

Listed above. The atomic-write pattern + `.bak` recovery is non-trivial. The settings file format is a free-form JSON shape that the UI assumes by key. Any new backend that "just owns settings" inherits all these schemas.

### 1.6 Direct calls into hermes-agent's Python (in-process imports)

**This is the single most important finding of the audit.** Fox's webui imports from hermes-agent across 49 import sites referencing 18 distinct modules:

```
agent.anthropic_adapter         tools.approval
agent.auxiliary_client          tools.mcp_tool
agent.credential_pool           tools.skills_tool
agent.manual_compression_feedback tools.transcription_tools
agent.model_metadata            cron.jobs
agent.redact                    cron.scheduler
hermes_cli.auth                 hermes_cli.profiles
hermes_cli.commands             hermes_cli.runtime_provider
hermes_cli.models               hermes_cli.tools_config
```

These are **in-process Python imports**, not HTTP calls. They reach into the agent's internals (e.g., `agent.credential_pool.load_pool`, `agent.anthropic_adapter.build_anthropic_kwargs`, `agent.model_metadata.get_model_context_length`, `cron.scheduler.run_job`). They are **undocumented**, change with upstream, and are the reason the webui is co-installed with the agent in the same Python venv (Dockerfile installs both with `pip install -e`).

Implication for Path B (full backend replacement):
- Either keep the new backend as Python in the same venv → you've replaced one Python wrapper with another, and you still have the `from agent.*` import surface to keep up with.
- Or write the backend in Node → you have to either spawn the agent CLI per request (cold-start cost) or reimplement those 18 modules' surfaces in Node (months of work, plus continuous re-sync).
- Or go HTTP-only → hermes-agent does not currently expose all of `agent.*` over HTTP. You'd be defining and maintaining a new agent-side HTTP API, which is out of scope per the brief.

**This finding alone should kill Path B for the foreseeable future.**

### 1.7 Browser-side features

| Feature | Implementation | Owner |
|---|---|---|
| PWA service worker (`sw.js`) | Vanilla JS service worker, opt-in app-shell cache | Upstream + Fox patches |
| PWA manifest | `manifest.json` | Upstream + Fox |
| Theme system | CSS custom properties on `:root`, dark/light auto + override | Upstream + Fox tokens in `fox-in-the-box.css` |
| i18n | `static/i18n.js`, `t(key, params)` global, **7,339 keys** | Upstream + Fox keys |
| Markdown rendering | `vendor/smd.min.js` (Streaming MD) | Upstream |
| Model picker | `panels.js`, populated from `/api/models` + `/api/models/live` | Upstream + Fox modifications |
| File uploads / drag-drop / paste | `messages.js`, `upload.py`/`upload/extract` endpoints | Upstream |
| Voice input | `static/messages.js`, `/api/transcribe` endpoint | Upstream |
| Speech locale | Per-locale `_speech` field in i18n bundle | Upstream |
| Onboarding wizard | `setup.{html,css,js}` + `api/setup/*` + redirect interstitial in `do_GET` | **Fox** |
| Failover modal | `fallback-polish.js` | **Fox** |
| Hostname prompt | `hostname-prompt.js` | **Fox** |
| Setup welcome / Ollama / Tailscale UI | `panels.js` + Fox additions | **Fox** |
| Login page | `login.{html,js}` | Upstream |

---

## 2. Two replacement paths (compared side-by-side)

### Path A — React/Next + shadcn/ui + Tailwind frontend; keep the Python webui server

Replace **only** the `static/` tree (and the index.html shell). The existing `server.py` + `api/routes.py` + every Python module (including the 18 agent imports) stays. From the browser's perspective, `index.html` becomes a thin React entry point; the React app speaks the existing REST + SSE protocol. The Python server keeps serving SSE, sessions, settings, models, providers, etc.

#### What we keep / drop / rebuild

| Layer | Status |
|---|---|
| `server.py` + `api/*.py` | **Keep, lightly fork** (still need ~2 patches as in Architect 1's plan) |
| All HTTP endpoints | **Keep upstream-owned** |
| All SSE protocols | **Keep upstream-owned** |
| Session storage on disk | **Keep upstream-owned** |
| `static/*.{css,html,js}` (everything) | **Drop and rewrite** |
| `static/i18n.js` (7,339 keys) | Rebuild as `react-i18next` JSON bundle (machine-portable, can keep keys) |
| `static/sw.js` (PWA worker) | Rewrite using `vite-plugin-pwa` or Workbox |
| `static/messages.js` SSE handling | Rewrite as a custom hook `useChatStream(streamId)` |
| `static/vendor/smd.min.js` | Replace with `react-markdown` + `remark-gfm` |

#### Engineering-day estimate

Assumes one full-time engineer; range, not point. Anchored to comparable rewrites (Open WebUI v0 → v0.4 = ~8 weeks for one core engineer; LibreChat's Vite migration = ~4 weeks).

| Workstream | Days (low–high) |
|---|---|
| Project setup (Vite + React + Tailwind + shadcn + i18n + PWA + SSE polyfill audit) | 2–3 |
| Design tokens migration (Fox CSS variables → Tailwind theme + shadcn theme) | 2–3 |
| Layout shell (sidebar, top bar, panel system) | 3–5 |
| Chat surface (message list, virtualized scroll, streaming markdown, attachments, voice button) | 5–8 |
| Sessions list + CRUD UI (rename, branch, delete, archive, pin, etc.) | 3–5 |
| Settings panels (8 settings areas: providers, models, hostname, Tailscale, fallback, profiles, workspace, theme) | 5–7 |
| Onboarding wizard rebuild (Fox-distinctive) | 2–3 |
| Approval/Clarify modals + SSE wiring | 2–3 |
| Cron / routines UI (will be fleshed out in Phase 5; build the shell) | 1–2 |
| File browser + terminal panel | 3–5 |
| Skills / MCP / OAuth screens | 2–3 |
| i18n re-keying (port 7,339 keys; or scope to en + 1–2) | 2–4 (scoped) / 8–12 (full) |
| PWA + SW + offline shell + manifest | 1–2 |
| Migration of Fox-distinctive UIs (Tailscale, Ollama panel, fallback modal, hostname prompt) | 2–3 |
| Build pipeline integration with Dockerfile + Electron | 1–2 |
| QA, accessibility pass, non-technical-user smoke (audience 45+) | 3–5 |
| Buffer (10%) | 4–7 |
| **Total Path A** | **42–80 eng-days, mid-point ≈ 55** |

If we scope i18n to English-only at launch (acceptable for Fox's US-first SMB target, with locale roadmap later): **35–55 eng-days, mid-point ≈ 45**.

#### Hermes-agent contracts we'd take on

Same as today: the in-process Python contract surface stays in `api/*.py`. **Path A does not change the agent-coupling situation.**

#### New dependency list (Path A)

- React 18+, Vite, TypeScript
- Tailwind CSS + `tailwindcss-animate`
- shadcn/ui (radix-based, copy-into-repo, no runtime dep on shadcn org)
- react-i18next + i18next
- TanStack Query (REST data) + a hand-rolled `useEventStream` hook for SSE
- react-hook-form + zod (settings forms)
- react-markdown + remark-gfm + rehype-sanitize + smd-style streaming wrapper (or keep `smd.min.js` from upstream)
- vite-plugin-pwa (Workbox under the hood)
- Vitest + @testing-library/react (unit), Playwright (e2e)
- Lucide React (icon set; replaces inline `icons.js` SVG sprite)

Ongoing maintenance cost: **2–4 hours/month** for routine dep bumps + 1 day/quarter for major bumps. Roughly the cost of any maintained React app.

#### Non-technical-user UX comparison

- **Hermes-webui today:** functional, dated, dense. Looks like a developer tool. Phase 3 (#64) was budgeted at 3–4 weeks of vanilla-CSS overhaul to fix this.
- **Path A new build:** native-app feel. shadcn defaults are restrained, accessible, keyboard-friendly. Better animation on transitions. Larger initial JS payload (Electron-wrapped → not a real concern).
- **Caveat:** "looks like a real app" is mostly typography + spacing + component polish, not framework choice. A 3-week vanilla-CSS overhaul *could* reach 80% of the visual gain. The framework win is in *consistency over time* — every new feature inherits the design system rather than re-implementing patterns ad-hoc, which is what `panels.js`'s 5,097 lines has become.

#### Migration sequencing

**Gradual page-by-page is not feasible** because hermes-webui is not a SPA — it's a full-page render with global JS. Two options:
- **Option A1 — Big bang at Phase 3.** Replace `static/` wholesale at v0.6.0. Ship Phase 3 as the React rewrite instead of as a CSS overhaul. **Recommended if Path A is chosen.**
- **Option A2 — Two URLs.** Keep `/` upstream, mount `/v2/` React app. Move users gradually. Doubles QA cost and confuses users 45+. **Not recommended.**

#### Risk register (Path A)

| Risk | Severity | Mitigation |
|---|---|---|
| SSE protocol drift between upstream and our React client | Med | Encapsulate event taxonomy in one TS module; pin upstream tag during dev. |
| `api/routes.py` adds an endpoint we now need a UI for (e.g., Kanban v1) | High | Track upstream weekly; budget continuous "absorb upstream" time. |
| Phase 3 ships late if React rewrite balloons | High | Set hard 60-day cap; if exceeded, fall back to vanilla-CSS overhaul. |
| Audience 45+ regressions: change-aversion, cognitive load on power users | Med | Beta with named friendly testers (already in Fox's QA practice per `feedback_qa_methodology.md`). |
| Service worker behavior diverges from upstream's careful cache opt-out (#114, etc.) | Med | Reuse upstream's `HERMES_WEBUI_PWA_SHELL_CACHE` opt-in semantics in our SW. |
| Lose i18n investment | Med | Port the en bundle 1:1, schedule other locales as Phase 4 work. |
| Electron CSP / file:// quirks | Low | shadcn/Tailwind have no exotic runtime requirements; vetted on Electron in many shipped products. |

---

### Path B — Full Fox-owned UI: React frontend + new Fox-owned thin Python (or Node) server

Drop hermes-webui entirely. New backend talks directly to hermes-agent. New frontend talks to new backend.

#### What we keep / drop / rebuild

| Layer | Status |
|---|---|
| All of `hermes-webui/` | **Drop entirely** |
| 158 endpoints | **Re-implement every one we need** |
| 5 SSE streams | **Re-implement** |
| Session storage | **Reimplement, must stay on-disk-compatible with agent CLI** |
| 18 `from agent.* / hermes_cli.* / cron.* / tools.*` imports | **Reimplement or maintain forever** |
| Session.save atomic-write + .bak recovery | **Reimplement** (P0 data-loss fix already lives here) |
| Auth, profiles, workspaces, projects, files, terminal, cron, skills, MCP, OAuth | **Reimplement** |

#### Engineering-day estimate

| Workstream | Days |
|---|---|
| Everything from Path A | 35–55 |
| New backend scaffold (Python aiohttp/FastAPI, or Node/Hono) | 5–8 |
| Re-implement 158 endpoints (avg 0.25 day each, weighted by complexity — chat/streaming/sessions are 3-5 days each) | 30–50 |
| In-process Python integration with hermes-agent (if Python backend) | 5–8 |
| Or build a new agent-HTTP API (if Node backend) | 30+ (out of scope per brief; would require coordinating with hermes-agent fork) |
| Session storage compatibility tests (must coexist with agent CLI on same files) | 3–5 |
| Auth, CSRF, profile cookies, security parity with upstream | 3–5 |
| Reproduce upstream's #1558 P0 data-loss fix and other quietly-shipped patches | 2–4 |
| Migration testing (must not lose anyone's existing sessions) | 3–5 |
| **Total Path B** | **86–140 eng-days, mid-point ≈ 110** |

If we stay in-process Python (i.e., new Python backend in same venv as agent): the lower end. If we go Node and reimplement agent surfaces: easily double.

#### Hermes-agent contracts taken on

**All of them.** Same 18 modules. Plus we now own the bug-for-bug compatibility surface for session JSON, gateway-session JSON (`~/.hermes/sessions/sessions.json`), credential pool semantics, model metadata lookups, profile config, etc. **This is the cost the React framing hides.**

#### New dependency list (Path B)

Path A list, plus:
- aiohttp or FastAPI (Python backend) — and we lose the BaseHTTPServer simplicity of upstream
- A new test matrix for the backend
- A CI pipeline for the backend
- A versioning + release story for it (currently the webui is just submoduled-and-installed)

#### Non-technical-user UX comparison

Same as Path A. The user can't see the backend.

#### Migration sequencing

Big bang. There is no gradual path that doesn't double-maintain two backends.

#### Risk register (Path B)

All of Path A's, plus:

| Risk | Severity | Mitigation |
|---|---|---|
| Reimplemented session storage drops messages on a corner case upstream caught (#1558 took weeks of debugging) | **Critical** | Mass-test against existing user session files; Fox's CHANGELOG already documents `:bak` recovery; need real test coverage |
| Auth / CSRF / cookie-handling gap creates a security regression | **High** | Mirror upstream's `api/auth.py` exactly; security review before launch |
| Cron / routines feature freeze: upstream Kanban-style features land but Fox can't absorb them | **High** | Permanent — this is the trade we're making |
| Lose mid-stream protocol enhancements upstream ships (e.g., new streaming event types) | High | Permanent ownership burden |
| Electron app refuses to install / certify because new server's startup signature changed | Low | Test on signed builds before merge |
| Upstream lands a feature that's load-bearing for Fox (e.g., new approval semantics for Llama Guard 3 in Phase 4) | High | Permanent ownership burden |

**Bottom line on Path B: plausible, but it costs 2–3× Path A and yields zero additional UX value over Path A. The only thing it buys is independence from the `nesquena/hermes-webui` Python dependency. It does not buy independence from hermes-agent — that coupling is unavoidable and Architect 1's plan already addresses it cleanly.**

---

## 3. Comparison matrix

| Dimension | Status quo (edit forks) | Plan A from existing doc (overlay + 12-day patch series) | Path A (React + keep Python backend) | Path B (Full Fox UI + new backend) |
|---|---|---|---|---|
| **Migration cost (eng-days)** | 0 | **12** | **35–55 + 12 (overlay)** = ~50–70 total | **86–140 + 12** = ~100–155 total |
| **Ongoing maintenance (hours/month)** | 30+ (and growing — currently *not done*) | **1–4** | 4–8 (deps + occasional upstream backend churn that affects frontend) | 15–30 (own everything) |
| **Upstream-track cost (per release)** | Unworkable; we don't track | **15–60 min** | 30–90 min (upstream may add endpoints we want to surface) | None for upstream-webui (gone), but we lose upstream features unless re-built |
| **Risk profile** | High & growing (security, drift) | **Low** | Medium (Phase 3 schedule risk; SSE protocol drift) | High (data-loss reimplementation risk; ownership of 158 endpoints) |
| **Time to Phase-3-UI-polish** | 3–4 weeks (per #64) | 3–4 weeks Phase-3 + 12 days migration; can run partly in parallel | **Phase 3 IS the rewrite** — 7–11 weeks instead of 3–4; but visual win is bigger | 14–22 weeks before Phase-3 polish ships |
| **Time to non-technical-user quality bar** | 3–4 weeks (CSS overhaul only) | Same as status quo + Architect-1 work invisible to user | 7–11 weeks (Phase 3 and rewrite combined) | 14–22 weeks |
| **Security cadence inheritance** | Falls behind every week | **Inherited automatically** (12 backend patches drift, but security is at agent + upstream-webui level) | Inherited (same backend) | **Lost** — Fox owns the entire surface |
| **Ability to absorb upstream features (Kanban, OAuth, etc.)** | Possible but currently blocked | Free for backend features; UI-side features need Fox to re-implement in React | Backend features free; UI features need re-implementation | **None** — every upstream UI feature is permanently lost unless re-implemented |
| **Lock-in / reversibility** | Already locked in | Reversible: we can still rewrite later | Reversible: backend is shared with upstream | **Hardest to reverse**: schema and endpoint divergence accumulates |
| **Developer experience (new feature work)** | Worst (vanilla JS, 5k-line files) | Same as status quo | Best (TS, components, hot reload) | Best on frontend, worst on backend (own everything) |

**Reading the matrix:** Architect-1's overlay plan dominates the status quo on every axis. Path A is the natural follow-on **if and when** the visual/Phase-3 cost is justified. Path B is dominated by Path A on every axis except "no longer dependent on nesquena."

---

## 4. Honest tech-stack opinion

### shadcn/ui

**Recommendation: use shadcn/ui for Path A.**

**Why:**
- Audience 45+ benefits from restrained, high-contrast, accessible defaults — shadcn nails this out of the box. Radix primitives underneath are the gold standard for keyboard nav and screen readers.
- Copy-into-repo model means **zero runtime dependency on the shadcn org**. We own the components after install. There is no shadcn version to track. This is the single best argument for it in an "install-and-forget" product.
- Big ecosystem; example code for every screen we'd build is one search away.

**Lock-ins:**
- Tailwind required (see below).
- Radix UI runtime is the actual dependency (well-maintained, ~stable).
- React-only.

**Compared to alternatives:**
- **Mantine**: more components out of the box, more polished defaults for forms — but heavier runtime (CSS-in-JS), larger bundle, less Tailwind-friendly. Picks more opinions for you. Reasonable second choice if we *don't* want Tailwind.
- **Radix-direct + Tailwind**: lower-level, more work; what shadcn already wraps. No reason to bypass.
- **Headless UI (Tailwind Labs) + Tailwind**: smaller library, fewer components, less momentum. Skip.
- **MUI**: looks like Google products, harder to feel "native." Default font size, color, density screams "Material" — bad fit for a non-technical SMB tool that should feel like Outlook/Slack/Quicken, not Google Workspace. Skip.

**Verdict:** shadcn/ui is the right choice if and only if Tailwind is also chosen. They are a paired bet.

### Tailwind

**Recommendation: use Tailwind for Path A.**

**Why for Fox specifically:**
- Fox today already uses CSS custom properties for theming (`fox-in-the-box.css`). Tailwind plays nicely with this — define design tokens as CSS vars, reference them in `tailwind.config.ts`. Theme switching keeps working.
- Co-located styling reduces drift between markup and styles, which has plagued `style.css` (3,052 lines) + 17 JS files.
- Tooling — JIT, PurgeCSS — means production CSS bundle is tiny (typically < 30 KB).

**Concerns the brief flags:**
- "Utility CSS in a product that aims to be themed for non-technical users" — themability for end-users is **not impacted** by Tailwind. Tailwind is a developer abstraction; the user still gets a `:root { --bg: …; --fg: …; }` runtime they can override. This is exactly how shadcn themes work.

**Compared to alternatives:**
- **CSS Modules**: fine but loses the design-system feel; we re-discover tokens per file.
- **Vanilla CSS variables (today's Fox approach)**: works, has been working. Loses the per-component encapsulation. Continues to grow `style.css` linearly. Accumulates dead code.
- **Linaria / styled-components / Emotion**: CSS-in-JS adds runtime cost or complex build, no payoff over Tailwind for our use case.

**Verdict:** Tailwind. The "utility CSS for non-technical users" framing conflates two different things — we use Tailwind to *build* the UI; users still see CSS variables.

### React framework

**Recommendation: Vite + React Router (NOT Next.js, NOT Remix).**

Reasoning:
- The app runs in **Electron-wrapped browser served from a local Docker container**. There is no SEO, no edge rendering, no cold-start tradeoff — the whole "Next.js/Remix make sense for SSR" argument doesn't apply.
- Next.js's App Router pulls in opinions we don't need (server actions, RSC, middleware). The complexity tax is real.
- Vite is the cleanest possible toolchain: pnpm install, vite dev, vite build, done. Output is a static folder we can drop into `static/` or serve from a sidecar.
- React Router 6+ handles every routing need we have (sessions, settings, projects).
- Lighter dependency surface = easier upgrades, smaller maintenance burden.

**SvelteKit (the foil)**: smaller bundles, lovely DX, but (a) shadcn has no first-class Svelte port (shadcn-svelte exists but lags), (b) team-mobility cost — fewer engineers know Svelte than React, (c) we'd be re-deciding everything around it. Real argument against SvelteKit: ecosystem and hireability for a small team. Skip.

**Verdict:** **Vite + React + React Router** as the foundation; keep options to migrate to Next or Remix later if SSR or data-loading patterns warrant it (they won't).

### State / data

**Recommendation:**
- **TanStack Query** for REST data fetching (caching, retries, invalidation, mutations). Battle-tested, Electron-friendly, plays nicely with SSE invalidation patterns.
- **Hand-rolled `useEventStream(url)` hook** for SSE — TanStack Query has subscription support but our streams are too custom (chat tokens, approvals, clarify) to map cleanly. Wrap `EventSource` in ~80 lines of typed hook code.
- **Zustand** for tiny client-only state (active session id, sidebar open/closed, theme). Avoid Redux Toolkit unless complexity actually appears.
- **No SWR** — TanStack Query has more features and similar ergonomics; pick one.
- **No RTK Query** — we don't need Redux for this app.

**Streaming SSE pattern sketch:**
```ts
function useChatStream(streamId: string | null) {
  const [events, append] = useReducer(chatEventsReducer, []);
  useEffect(() => {
    if (!streamId) return;
    const es = new EventSource(`/api/chat/stream?stream_id=${streamId}`);
    es.addEventListener('delta', (e) => append({ type: 'delta', data: JSON.parse(e.data) }));
    es.addEventListener('tool_call', /* … */);
    es.addEventListener('error', () => es.close());
    return () => es.close();
  }, [streamId]);
  return events;
}
```

### Forms

**Recommendation: react-hook-form + zod + `@hookform/resolvers/zod`.**

Reasoning: small, fast, no rerender storms, schema-first validation that doubles as TypeScript types. The settings panels (8 areas, lots of conditional fields, server-validated) benefit enormously from this combo. Alternatives (formik, vanilla `useState`) lose on either DX or correctness.

### Testing

**Recommendation: Vitest + React Testing Library for unit, Playwright for e2e and onboarding-flow regressions.**

Reasoning:
- Vitest co-runs with Vite, zero extra config.
- Playwright is the industry standard for Electron-app e2e (Microsoft uses it for VS Code) and gives us screenshot diffing for the visual-regression bar Phase-3 needs.
- Skip Cypress (heavier, slower, less Electron-friendly).
- Don't skip e2e: Fox's `qa/SMOKE_CHECKLIST.md` discipline maps to Playwright runs naturally.

### Build / packaging into Docker + Electron

**Recommendation:**
- Build React with `vite build --outDir=dist` in CI.
- In the Dockerfile, after `COPY forks/hermes-webui /app/hermes-webui`, **also `COPY packages/fox-react/dist /app/hermes-webui/static`** (or to `HERMES_WEBUI_EXTENSION_DIR`).
- The existing Python server keeps serving from `static/`. **No new sidecar needed.** This is the single cleanest packaging path.
- For Electron: nothing changes — the renderer points at `http://127.0.0.1:8787/` as today. The React app is just what `index.html` loads.
- For dev: `vite dev` proxies `/api/*` and `/extensions/*` to `localhost:8787`. Hot-reload works.

This packaging story is the **biggest pragmatic argument for Path A over Path B**: Path A slots into the existing Docker build with one extra `COPY` line. Path B requires a new supervisord program, a new port story, a new install-script update, a new auth flow review, and probably new GitHub Action steps.

---

## 5. The hermes-webui-cadence question

> "Based on hermes-webui shipping schedule, how solid is them as a web ui choice?"

### What the data says

From `git log upstream/master` in the standalone clone:

- **661 commits in last 7 days** (~94/day)
- **1,329 commits in last 14 days** (~95/day)
- **1,724 commits in last 30 days** (~57/day, includes a slower week)
- **Tag cadence:** 50 most-recent tags span only a few weeks; current tag at time of writing is `v0.51.74`. Tags are released multiple times per day.

Top contributors (last 30 days):

| Author | Commits |
|---|---|
| `nesquena-hermes` (bot, owned by Nathan) | 573 |
| `Hermes Agent` (CI bot) | 231 |
| Frank Song | 155 |
| Michael Lam | 127 |
| `Hermes Bot` | 95 |
| `test`, `bergeouss`, `ai-ag2026`, etc. | 50 / 50 / 45 / 38 / 33 |
| Nathan Esquenazi (real account) | 44 |

**Reality:** the project is `nesquena`-driven with bot-mediated PR-merge automation. The bot accounts (`nesquena-hermes`, `Hermes Agent`, `Hermes Bot`) are all his automation. Real human contributors are a long tail. **Bus factor = 1**, full stop. The "stage-NNN: stamp CHANGELOG" commits are clearly automation Nathan owns.

### Alignment with hermes-agent

Hermes WebUI versions itself independently of hermes-agent (`v0.51.x` vs agent's `v0.13.x`). They do not ship in lockstep. **However**, the in-process imports (Section 1.6) mean a webui release that depends on a not-yet-released agent change *can* break. The Fox-bundled images pin both to specific tags at Docker build time, which mostly contains this risk.

### Feature alignment with Fox needs

- Recent shipped: Kanban v1 (would compete with Fox's Phase 5 routines if we wanted that surface), `transform_llm_output` plugin hook (which hermes-agent v0.13.0 added — Fox guardrails directly benefits), settings i18n, custom-providers list-format fix.
- Recent missed-by-Fox: `:free`/`:beta`/`:thinking` suffix routing fix; named custom-provider routing (Stage-306) — these are exactly the things Fox patches `api/providers.py` for. Architect 1's plan calls these out as patches Fox should drop.

### Has it ever been abandoned / restructured

Per Architect 1's audit: no abandonment. Heavy continuous evolution. Some restructures (`api/onboarding.py` was rewritten when Codex OAuth landed). The patch surface Fox carries on `api/onboarding.py` is +227/−916 — meaning Fox effectively replaced upstream's onboarding wholesale. If upstream restructures something Fox has fully replaced, Fox is unaffected (already off the upstream code path). Where Fox tracks upstream (chat, sessions, models), restructures matter — and the overlay/monkey-patch model in Architect 1 buys debounceability.

### What if `nesquena` disappears tomorrow

Three scenarios:
1. **Project continues under another maintainer:** plausible — Frank Song and Michael Lam are routinely landing PRs. Cadence might slow, security cadence is the worry.
2. **Project goes dormant:** Fox is fine for ~6–12 months because we've already pinned tags and don't *need* every release. The day we need a security fix, we take ownership of one specific patch.
3. **Project hostile fork by another party:** Fox can fork at the last good tag and own from there. Architect 1's plan already isolates Fox's deltas, so a fork-takeover by Fox would be feasible from the patch-series state.

### The honest verdict on cadence

The cadence is **a feature, not a bug, from Fox's perspective**. ~95 commits/day means upstream is fixing real bugs and adding capabilities Fox would otherwise have to build (PWA improvements, accessibility passes, locale work, Kanban, OAuth). The cadence is a *risk* only because Fox isn't tracking it — solve that with Architect 1's plan.

Bus-factor (single maintainer) is the real risk. Mitigate by:
1. Pinning tags in `versions.toml` (Architect 1 plan does this).
2. Forking-and-owning if `nesquena` disappears — Fox is well-positioned to do this from the post-Architect-1 state, *less* well-positioned from a Path-B "we already replaced everything" state because then we have no patch series to graft back onto upstream code if we want re-alignment.

**Path A is consistent with cadence resilience. Path B sacrifices it.**

---

## 6. Recommendation

**Take Architect 1's overlay/patch-series plan now (12 eng-days). Defer the React rewrite. When you do build it, build Path A — not Path B — and time it as the v0.6.0 (Phase 3) UI overhaul work.**

Three concrete moves, in order:

1. **Now (Phase 0 cleanup, parallel to v0.5.4 / Phase 1 work):** Execute Architect 1's 12-day overlay+patch-series plan. This is non-optional and non-controversial regardless of any UI decision. Once shipped, Fox can absorb upstream weekly with ≤ 1 hour of effort per release.

2. **At v0.6.0 (Phase 3, the planned 3–4 week UI overhaul):** **Replace the planned vanilla-CSS overhaul with Path A — React + shadcn/ui + Tailwind, keeping the Python backend.** Budget 7–11 calendar weeks (35–55 eng-days, plus QA/buffer). The visual quality lift will exceed what 3–4 weeks of vanilla-CSS overhaul could achieve, and the foundation makes Phase 4–5 UI work (Llama Guard banners, routines tab, status indicators) cheaper.

3. **Never (or only on a customer-driven trigger):** Path B. The cost is 2–3× Path A for zero user-visible benefit. The only thing Path B buys is independence from `nesquena/hermes-webui`, and Architect 1's plan already buys 90% of that benefit at 8% of the cost.

### The trade-off in one sentence

> *We accept a continued (well-bounded) dependency on `nesquena/hermes-webui`'s Python backend in exchange for skipping a 100+ eng-day rewrite of code we don't get to upgrade thereafter — and we'll still get the React/shadcn/Tailwind UX upgrade by replacing only the static frontend in Phase 3.*

### What this depends on (the two facts that could change the recommendation)

1. **If `nesquena` disappears or hermes-webui goes hostile-fork in the next 6 months:** Path B becomes the right move because we can no longer benefit from upstream tracking. Today: not the case.
2. **If hermes-agent changes its in-process import surface in a way that makes `from agent.* import …` calls untenable for Fox:** Path B's cost balloons further (now we need to build the agent-HTTP API too) — meaning Path A becomes even more strongly preferred. So this fact actually pushes harder toward A, not B.

Neither fact is currently in motion. Recommendation stands.

---

## 7. Open questions for Dennis

1. **Is the v0.6.0 Phase-3 UI overhaul the right vehicle for the React rewrite?** The roadmap calls Phase 3 a "3–4 week vanilla-CSS overhaul." Path A is 7–11 weeks. Are you willing to slip Phase 3 by ~6 weeks for the qualitative jump, or do you prefer the cheap CSS-only overhaul now and Path A later (e.g., as v0.7.5 between Llama Guard and Routines)?
2. **Do you want i18n parity at React-rewrite launch, or English-only with locales as fast-follow?** Affects estimate by ~6–8 days.
3. **Are you OK with Vite + React (no Next/Remix), Tailwind + shadcn, TanStack Query + Zustand?** If you have a stack preference (e.g., you've been building landing pages in Next), say so now — switching frameworks mid-rewrite costs ~5 days.
4. **Are there any contracts where you'd want a Fox-owned alternative regardless** (e.g., the chat-stream SSE format)? This is the only place Path B's case strengthens — but the answer would be "build a Fox-owned SSE shim layer," not "build a whole new backend."
5. **PWA / offline behavior**: today, Fox runs Electron-wrapped, so PWA install isn't user-facing. Should the React rewrite drop SW/manifest entirely, or maintain it for the (rare) "open in browser instead of Electron" path?
6. **Browser/Electron version floor**: confirm we can target evergreen Chromium only (no IE/Safari ancients). Affects bundle size and dependency choices.
7. **Headcount/runway for the rewrite window**: the 35–55 eng-day estimate assumes one full-time engineer. If it's a 50% engineer, double the calendar time. What's the actual capacity?
