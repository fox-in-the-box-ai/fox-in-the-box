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


def _handle_post(handler, parsed) -> bool:
    """Dispatch POST /test/*. Returns True if handled, False to fall through."""
    from api.helpers import j, read_body

    if parsed.path == "/test/reset":
        j(handler, handle_post_reset(handler))
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
