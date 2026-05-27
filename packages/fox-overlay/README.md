# fox-overlay

Sibling package holding all Fox-in-the-Box-specific code that overlays the
virgin upstream `hermes-agent` and `hermes-webui` submodules. Lets the
submodules point at unmodified upstream tags so Fox can absorb upstream
releases without carrying a perpetually-conflicting fork.

## What's inside

| Path | Purpose |
|---|---|
| `patches/{agent,webui}/` | Quilt-style patch series applied at Docker build time. Today: 1 agent patch (gateway bootstrap shim), 8 webui patches (001 server.py bootstrap, 002 routes.py dispatcher hook, 003 onboarding-redirect, 004 fox-bot-name, 005 fox-avatar, 006 empty-state-branding, 007 ui.js colon-split fix, 008 routes.py colon-split fix). |
| `.fox-removals` | File paths from upstream that Fox doesn't ship (consumed by the Dockerfile installer). |
| `fox_overlay/webui_modules/` | Additive HTTP route modules — register handlers with `fox_overlay.dispatch.register_get/post`. Today: ollama, tailscale, local_fallback, models_download, hostname, onboarding, test_hooks (FITB_TEST_MODE=1 only). |
| `fox_overlay/webui_patches/` | Runtime monkey-patches on upstream webui modules via `inspect.getsource` + textual substitution. Today: config (settings defaults + #303 OLLAMA picker splice), streaming (FITB#9 plumbing + #303 silent failover). |
| `fox_overlay/agent_plugins/` | Entry-point-loaded agent monkey-patches (runtime_provider, auxiliary_client, cron_diagnostics). |
| `fox_overlay/agent_memory_plugins/` | Fox-only memory providers COPYd into upstream's `plugins/memory/` dir at build time. |
| `fox_overlay/_substitute.py` | Canonical substitution helpers (`substitute_function`, `substitute_method`). The two historical `_helpers.py` files are 3-line re-export shims since v0.7.5. |
| `agent_overlay/` | Content-overlay files (e.g. Fox's SOUL.md persona) copied over upstream's defaults at Dockerfile build time. New in v0.7.3. |
| `webui_static/` | Static assets (CSS, JS, images, fonts) served via the WebUI `/extensions/*` path. |
| `versions.toml` | Pinned upstream tags + their bump history. |
| `MANIFEST.toml` | Inventory of overlay artifacts (used by `scripts/check-overlay-basis.sh`). |
| `scripts/check-overlay-basis.sh` | CI gate — verifies every overlay artifact still applies cleanly against the current submodule pin. |
| `tests/` | Pytest regression suite (~165 tests across 14 modules covering dispatcher, monkey-patches, wraps, modules). |

## Where to learn more

- **[`docs/architecture/upstream-overlay.md`](../../docs/architecture/upstream-overlay.md)** — authoritative architecture doc. Read this before writing overlay code. Covers the five overlay mechanisms + when to use which + the patterns discovered mid-migration (wrap-and-splice, multi-substitution, fail-loud anchors, etc.).
- **[`docs/RELEASE_WORKFLOW.md`](../../docs/RELEASE_WORKFLOW.md)** — Flow A (Fox-code release) vs Flow B (Option B upstream-only bump).
- **`docs/archive/upstream-migration-execution-plan.archive.md`** — the original 10-phase migration plan (historical).
