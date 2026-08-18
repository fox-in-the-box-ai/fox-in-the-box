# fox-overlay

Sibling package holding all Fox-in-the-Box-specific code that overlays the
virgin upstream `hermes-agent` and `hermes-webui` submodules. Lets the
submodules point at unmodified upstream tags so Fox can absorb upstream
releases without carrying a perpetually-conflicting fork.

## What's inside

| Path | Purpose |
|---|---|
| `patches/{agent,webui}/` | Quilt-style patch series applied at Docker build time. Today: 1 agent patch (gateway bootstrap shim), 10 webui patches (001 server.py bootstrap, 002 routes.py dispatcher hook, 003 onboarding-redirect, 004 fox-bot-name, 005 fox-avatar, 006 empty-state-branding, 007 ui.js colon-split fix, 008 routes.py colon-split fix, 009 remove-onboarding-js-script-tag, 010 bedrock-settings-credentials). 001/003/007/010 were regenerated against the v0.52.113 pin (#740). |
| `.fox-removals` | File paths from upstream that Fox doesn't ship (consumed by the Dockerfile installer). |
| `fox_overlay/webui_modules/` | Additive HTTP route modules — register handlers with `fox_overlay.dispatch.register_get/post`. Today (13): ollama, tailscale, local_fallback, models_download, hostname, onboarding, approval_explain, capabilities, custom_providers, readyz, skillset, version, test_hooks (FITB_TEST_MODE=1 only). |
| `fox_overlay/webui_patches/` | Runtime monkey-patches on upstream webui modules via `inspect.getsource` + textual substitution. Today (6, per `apply_all()`): config (settings defaults + #303 OLLAMA picker splice), streaming (FITB#9 plumbing + #303 silent failover), auth (check_auth — re-anchored at #740), auth_body_drain, csrf, providers. |
| `fox_overlay/agent_plugins/` | Entry-point-loaded agent monkey-patches: auxiliary_client, cron_diagnostics, bedrock_imds. (runtime_provider was deleted at #740 — upstream v2026.8.16.2 absorbed the target_model fix; the cron run_one_job substitution was likewise absorbed.) |
| `agent_memory_plugins/` (package root) | Fox-only memory providers (mem0_oss) COPYd into upstream's `plugins/memory/` dir at build time. |
| `fox_overlay/_substitute.py` | Canonical substitution helpers (`substitute_function`, `substitute_method`). The two historical `_helpers.py` files are 3-line re-export shims since v0.7.5. |
| `agent_overlay/` | Content-overlay files (e.g. Fox's SOUL.md persona) copied over upstream's defaults at Dockerfile build time. New in v0.7.3. |
| `webui_brand/` + `install_webui_branding.py` | Canonical Fox branding (icons, favicons, PWA titles) installed over upstream assets at build time. New in v0.7.60. |
| `webui_static/` | Static assets (CSS, JS, images, fonts) served via the WebUI `/extensions/*` path. |
| `versions.toml` | Pinned upstream tags + their bump history. |
| `MANIFEST.toml` | Inventory of overlay artifacts (used by `scripts/check-overlay-basis.sh`). |
| `scripts/check-overlay-basis.sh` | CI gate — verifies every overlay artifact still applies cleanly against the current submodule pin. |
| `tests/` | Pytest regression suite (383 tests across 28 test modules covering dispatcher, monkey-patches, wraps, modules, memory provider). |

## Where to learn more

- **`fox-private-docs/architecture/upstream-overlay.md`** — the authoritative overlay-mechanisms doc (mechanism table, when to use which, wrap-and-splice / multi-substitution / fail-loud anchor patterns); maintainer-internal repo. External contributors: this README's table plus the patch/monkey-patch sources themselves (each carries a fail-loud anchor and docstring) are the public reference.
- **[`docs/architecture/upstream-overlay.md`](../../docs/architecture/upstream-overlay.md)** — the in-repo upstream-PR strategy doc (when to push a fix upstream instead of patching).
- **[`docs/RELEASE_WORKFLOW.md`](../../docs/RELEASE_WORKFLOW.md)** — Flow A (Fox-code release) vs Flow B (Option B upstream-only bump).
