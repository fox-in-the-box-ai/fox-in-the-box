"""Test-only HTTP routes — registered only when FITB_TEST_MODE=1.

Lets Playwright specs reset state between specs and drive deterministic
internal states that would otherwise require docker exec or filesystem
manipulation from the test runner.

**Production safety:** the module-level `register_*` calls below are
guarded by an `FITB_TEST_MODE` env check. When the env var is not "1",
this module imports cleanly but registers nothing — production builds
have zero new attack surface.

Routes today (Phase 0):

- `POST /test/reset` — nuke `/data/state/webui/*.json` + sessionStorage
  hint files (lets a spec re-test onboarding from a clean state without
  re-creating the container).
- `POST /test/tailscale/set-state {state: "...", magicdns_name?: "..."}` —
  drive the Tailscale state machine to a deterministic state (eg
  "running" / "needs-login" / "disconnected") without actually running
  the daemon. Used by wizard + settings specs in Phase 1.

Phase 1 will likely add:
- `GET /test/logs/tail?lines=N` — return the last N lines of
  `/data/logs/{hermes-webui,hermes-gateway}.log` so the runner can assert
  on container-side log output (eg the v0.7.5 anchor-drift abort line).
- `POST /test/ollama/set-state` — drive the Fox Ollama detection cache
  to a known state without running a real Ollama daemon.

All routes accept JSON bodies (read via upstream's `api.helpers.read_body`)
and respond with `j(handler, {"ok": True/False, ...})`.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Module-level gate — registration only happens when FITB_TEST_MODE=1.
_ENABLED = os.environ.get("FITB_TEST_MODE") == "1"


def _state_dir() -> Path:
    """The webui state directory — where session JSON files and onboarding
    hint files live. Mirrors `HERMES_WEBUI_STATE_DIR` in supervisord.conf."""
    return Path(os.environ.get("HERMES_WEBUI_STATE_DIR", "/data/state/webui"))


def handle_post_reset(handler) -> dict[str, Any]:
    """POST /test/reset — clear webui state. Returns a summary of what was
    removed. Idempotent: re-running against an already-clean state is OK."""
    state_dir = _state_dir()
    removed = {"json_files": 0, "session_dirs": 0}
    if state_dir.exists():
        for p in state_dir.iterdir():
            if p.is_file() and p.suffix == ".json":
                try:
                    p.unlink()
                    removed["json_files"] += 1
                except OSError as e:
                    logger.warning("[test-hooks] /test/reset: failed to remove %s: %s", p, e)
            elif p.is_dir() and p.name.startswith("session_"):
                try:
                    shutil.rmtree(p)
                    removed["session_dirs"] += 1
                except OSError as e:
                    logger.warning("[test-hooks] /test/reset: failed to remove %s: %s", p, e)
    # Onboarding hint file may live elsewhere — best-effort clear.
    onboarding = Path(os.environ.get("ONBOARDING_PATH", "/data/config/onboarding.json"))
    onboarding_removed = False
    if onboarding.exists():
        try:
            onboarding.unlink()
            onboarding_removed = True
        except OSError as e:
            logger.warning("[test-hooks] /test/reset: failed to remove %s: %s", onboarding, e)
    # Clear any injected failures so a reset always leaves the system clean.
    try:
        from fox_overlay.webui_modules import local_fallback
        local_fallback._INJECTED_FAILURE = None
    except Exception:
        pass
    return {"ok": True, "removed": removed, "onboarding_removed": onboarding_removed}


# Stub for /test/tailscale/set-state — Phase 1 spec will exercise this.
# Pattern: Phase 0 ships the route shape so Phase 1 specs can plumb against it;
# the actual state-machine drive logic lives in fox_overlay/webui_modules/tailscale
# and is wired here in Phase 1 alongside the wizard specs that need it.
def handle_post_tailscale_set_state(handler, body: dict) -> dict[str, Any]:
    """POST /test/tailscale/set-state — Phase 1 will plumb to webui_modules.tailscale's
    internal cache. Phase 0 returns 501 to make the route surface visible while signalling
    "not implemented yet" to any spec that tries to use it."""
    return {
        "ok": False,
        "error": "not_implemented_phase_0",
        "hint": "Phase 1 wires this to webui_modules.tailscale's cache; see #265.",
    }


def handle_post_skip_onboarding(handler) -> dict[str, Any]:
    """POST /test/skip-onboarding — mark onboarding complete so / lands on chat.

    Lets specs that test the chat UI bypass the /setup redirect without
    having to simulate the full wizard flow. Calls the same
    _mark_onboarding_complete path the wizard uses, so all downstream
    checks (onboarding.json + settings.json:onboarding_completed) are
    satisfied identically to a real wizard completion.
    """
    try:
        from fox_overlay.webui_modules.onboarding import _mark_onboarding_complete
        result = _mark_onboarding_complete(skipped=True, extra={"via": "test-hook"})
        return {"ok": True, "result": result}
    except Exception as exc:
        logger.exception("[test-hooks] /test/skip-onboarding failed")
        return {"ok": False, "error": str(exc)}


def handle_post_seed_provider(handler, body: dict) -> dict[str, Any]:
    """POST /test/seed-provider — write a provider key to settings.

    Body: { "provider": "openrouter", "api_key": "sk-or-test-..." }

    Writes api_key into settings.json under the provider's key name, then
    triggers a gateway hot-reload. This lets specs that need a configured
    provider (e.g. #344 auto-preselect) operate deterministically without
    going through the wizard.

    Only "openrouter" is supported for now (covers the #344 use-case).
    Extend body["provider"] handling as specs need additional providers.
    """
    provider = str(body.get("provider", "")).strip().lower()
    api_key = str(body.get("api_key", "")).strip()
    if not provider or not api_key:
        return {"ok": False, "error": "provider and api_key are required"}
    if provider not in {"openrouter", "anthropic", "gemini", "openai"}:
        return {"ok": False, "error": f"unsupported provider: {provider}"}

    PROVIDER_KEY_MAP = {
        "openrouter": "openrouter_api_key",
        "anthropic":  "anthropic_api_key",
        "gemini":     "gemini_api_key",
        "openai":     "openai_api_key",
    }
    settings_key = PROVIDER_KEY_MAP[provider]
    try:
        from api.config import load_settings, save_settings
        s = load_settings()
        s[settings_key] = api_key
        save_settings(s)
    except Exception as exc:
        logger.exception("[test-hooks] /test/seed-provider: save_settings failed")
        return {"ok": False, "error": f"save_settings: {exc}"}

    # Best-effort hot-reload so the gateway picks up the new key immediately.
    try:
        from api.providers import _reload_provider_runtime
        _reload_provider_runtime()
    except Exception:
        pass  # not fatal — the key is persisted, next request will reload

    return {"ok": True, "provider": provider, "key_field": settings_key}


def handle_post_inject_failure(handler, body: dict) -> dict[str, Any]:
    """POST /test/inject-failure — arm a failure for a named internal function.

    Body: { "target": "local_fallback.enable", "kind": "supervisor-unavailable" }

    Sets a module-level flag in the target module. The target function checks
    the flag at entry and raises (or returns an error dict) when set. Clear
    with POST /test/reset (which also clears _INJECTED_FAILURE).

    Currently only "local_fallback.enable" is supported.
    """
    target = str(body.get("target", "")).strip()
    kind = str(body.get("kind", "injected-test-failure")).strip()

    if target == "local_fallback.enable":
        try:
            from fox_overlay.webui_modules import local_fallback
            local_fallback._INJECTED_FAILURE = kind
            return {"ok": True, "target": target, "kind": kind}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    return {"ok": False, "error": f"unknown target: {target}"}


def _handle_post(handler, parsed) -> bool:
    """Dispatch POST /test/*. Returns True if handled, False to fall through."""
    from api.helpers import j, read_body

    if parsed.path == "/test/reset":
        j(handler, handle_post_reset(handler))
        return True

    if parsed.path == "/test/skip-onboarding":
        j(handler, handle_post_skip_onboarding(handler))
        return True

    if parsed.path == "/test/seed-provider":
        body = read_body(handler) or {}
        j(handler, handle_post_seed_provider(handler, body))
        return True

    if parsed.path == "/test/inject-failure":
        body = read_body(handler) or {}
        j(handler, handle_post_inject_failure(handler, body))
        return True

    if parsed.path == "/test/tailscale/set-state":
        body = read_body(handler) or {}
        j(handler, handle_post_tailscale_set_state(handler, body), status=501)
        return True

    return False


# Register only when explicitly enabled. The dispatch table freezes after
# bootstrap (see fox_overlay/dispatch.py), so this is a one-shot at import.
if _ENABLED:
    from fox_overlay import dispatch  # noqa: E402

    dispatch.register_post("/test/", _handle_post)
    logger.warning(
        "[fox-overlay] test_hooks ENABLED (FITB_TEST_MODE=1) — registered POST /test/*. "
        "Never set FITB_TEST_MODE=1 in production: these routes bypass auth and "
        "mutate persisted state."
    )
