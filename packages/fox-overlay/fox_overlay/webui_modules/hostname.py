"""Hermes Web UI -- Tailscale hostname management.

Persists ``FOX_HOSTNAME`` to the FITB env file and applies it live to the
running tailscaled via ``tailscale set --hostname``. Re-reads
``tailscale status --json`` after applying so collision suffixes
(`-1`, `-2`, …) are surfaced to the caller.

Issue #44 — Electron desktop-app first-run parity with the install.sh
hostname work from #3.
"""

from __future__ import annotations

import json
import logging
import os
import random
import re
import subprocess
from pathlib import Path
from typing import Any

# Phase 7 (v0.6.0): _write_env_key moved from api.onboarding (fork removed
# the file) to fox_overlay.webui_modules.onboarding. Same function, same
# behavior — just relocated to the overlay package.
from fox_overlay.webui_modules.onboarding import _write_env_key

logger = logging.getLogger(__name__)


# Mirrors the curated list in packages/scripts/install.sh:_default_hostname().
# Kept in sync intentionally — both places generate names from the same pool so
# host-script users and Electron users produce indistinguishable defaults.
_ADJECTIVES = (
    "quick", "clever", "bright", "swift", "keen",
    "amber", "nimble", "fierce", "bold", "sly",
    "golden", "autumn",
)

# Tailscale's effective hostname rule, derived from
# util/dnsname/dnsname.go:SanitizeLabel — RFC 1035 DNS label form.
_HOSTNAME_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")
_MAX_LEN = 63

_ENV_PATH = Path(os.environ.get("HERMES_ENV_PATH", "/data/config/hermes.env"))
_FOX_HOSTNAME_KEY = "FOX_HOSTNAME"


def default_hostname() -> str:
    """Generate a fox-<adjective> default. Random pick keeps tailnets
    collision-free best-effort; Tailscale auto-suffixes on real collision."""
    return f"fox-{random.choice(_ADJECTIVES)}"


def sanitize_hostname(raw: str) -> str:
    """Lowercase, replace runs of non-[a-z0-9-] with a single -, strip
    leading/trailing -, truncate to 63 chars. Mirrors install.sh's
    _sanitize_hostname() byte-for-byte."""
    if not raw:
        return ""
    s = raw.strip().lower()
    s = re.sub(r"[^a-z0-9-]+", "-", s)
    s = s.strip("-")
    return s[:_MAX_LEN]


def validate_hostname(s: str) -> str | None:
    """Return ``None`` if valid, else a human-readable error message.
    Stricter than sanitize_hostname — caller should sanitize first if it
    wants automatic correction; this rejects anything not already valid."""
    if not s:
        return "Hostname is required."
    if len(s) > _MAX_LEN:
        return f"Hostname must be {_MAX_LEN} characters or fewer."
    if not _HOSTNAME_RE.match(s):
        return (
            "Hostname must contain only lowercase letters, digits, and hyphens, "
            "and must start and end with a letter or digit."
        )
    return None


def _read_configured_hostname() -> str:
    """Read FOX_HOSTNAME from hermes.env, or empty string if unset."""
    try:
        if not _ENV_PATH.exists():
            return ""
        for raw in _ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.strip() == _FOX_HOSTNAME_KEY:
                return value.strip().strip('"').strip("'")
    except OSError:
        pass
    return ""


def _run_tailscale(args: list[str], timeout: float = 10.0) -> tuple[int, str, str]:
    """Run a `tailscale` subcommand. Returns (returncode, stdout, stderr).
    Returncode 127 indicates the binary isn't on PATH (e.g. running outside
    the FITB container during dev/tests)."""
    try:
        result = subprocess.run(
            ["tailscale", *args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode, result.stdout, result.stderr
    except FileNotFoundError:
        return 127, "", "tailscale binary not found"
    except subprocess.TimeoutExpired:
        return 124, "", f"tailscale {args[0] if args else ''} timed out"


def _read_effective_hostname() -> str | None:
    """Read the running daemon's current effective hostname from
    ``tailscale status --json``. Returns ``None`` if tailscaled isn't
    reachable. The control plane appends `-1`, `-2`, … on hostname
    collision; ``Self.HostName`` reflects the suffixed form."""
    rc, out, _err = _run_tailscale(["status", "--json"], timeout=5.0)
    if rc != 0 or not out:
        return None
    try:
        status = json.loads(out)
    except json.JSONDecodeError:
        return None
    self_node = status.get("Self") or {}
    return self_node.get("HostName") or None


def _read_backend_state() -> str:
    """Return the BackendState (NoState / NeedsLogin / NeedsMachineAuth /
    Stopped / Starting / Running) or empty string. Used to gate the
    post-wizard hostname prompt — Self.HostName is set well before the
    user has actually authenticated, so checking only "tailscale running"
    fired the prompt before the user joined the tailnet (#68 QA bug)."""
    rc, out, _err = _run_tailscale(["status", "--json"], timeout=5.0)
    if rc != 0 or not out:
        return ""
    try:
        status = json.loads(out)
    except json.JSONDecodeError:
        return ""
    return status.get("BackendState") or ""


def get_hostname_state() -> dict[str, Any]:
    """Read everything the Settings UI needs to render the hostname field."""
    configured = _read_configured_hostname()
    effective = _read_effective_hostname()
    # `prompted` is the post-wizard one-time-prompt flag (#68). The chat-UI
    # reads it on first load to decide whether to show the hostname modal;
    # Settings ignores it.
    try:
        from api.config import load_settings
        prompted = bool(load_settings().get("hostname_prompted", False))
    except Exception:
        prompted = False
    return {
        "configured": configured,
        "effective": effective or "",
        "default_suggestion": default_hostname() if not configured else "",
        "tailscale_running": effective is not None,
        # QA fix: explicit BackendState so the post-wizard prompt
        # (hostname-prompt.js) can fire only after the user has actually
        # joined the tailnet — Self.HostName is populated long before
        # BackendState reaches Running, so the previous predicate
        # (tailscale_running && !configured && !prompted) fired the
        # prompt during NeedsLogin state and the user dismissed it
        # because "I haven't even auth'd yet".
        "backend_state": _read_backend_state(),
        "prompted": prompted,
    }


def mark_hostname_prompted() -> dict[str, Any]:
    """Persist hostname_prompted=true so the post-wizard modal never re-fires.
    Used by both the explicit "Skip" button and implicitly when the modal saves."""
    try:
        from api.config import save_settings
        save_settings({"hostname_prompted": True})
        return {"ok": True}
    except Exception as exc:
        logger.exception("Failed to mark hostname_prompted")
        return {"ok": False, "error": str(exc)}


def apply_hostname(hostname: str) -> dict[str, Any]:
    """Persist FOX_HOSTNAME and apply it live to tailscaled.

    Sanitizes and validates, then:
      1. Writes ``FOX_HOSTNAME=<name>`` to /data/config/hermes.env so the
         next container start (or supervisord restart) picks it up.
      2. Calls ``tailscale set --hostname=<name>`` against the running
         daemon. Surgical mutation — only the hostname pref is changed
         (cf. ``tailscale up``, which would re-apply a full preferences
         set and risk resetting unrelated flags).
      3. Re-reads ``tailscale status --json`` so the caller sees the
         effective name (control plane may have appended a collision
         suffix).
    """
    sanitized = sanitize_hostname(hostname)
    err = validate_hostname(sanitized)
    if err:
        return {"ok": False, "error": err}

    try:
        _write_env_key(_FOX_HOSTNAME_KEY, sanitized)
    except OSError as exc:
        logger.error("Failed to write FOX_HOSTNAME to hermes.env: %s", exc)
        return {"ok": False, "error": "Failed to persist hostname."}

    rc, _out, err_text = _run_tailscale(["set", f"--hostname={sanitized}"], timeout=10.0)

    # The persist already succeeded — `FOX_HOSTNAME` is in hermes.env. The
    # live `tailscale set` is a best-effort hot-apply: if it fails (daemon
    # not authed yet, not running, binary missing, etc.) the value still
    # takes effect on the next container/daemon start. Surface the reason
    # in `note` rather than failing the whole call, so first-run users who
    # haven't yet authed Tailscale don't see a scary error for what is
    # actually a successful save.
    if rc != 0:
        if rc == 127:
            note = ("Saved. Tailscale binary not on PATH from this process; "
                    "the new name will apply on the next container start.")
        else:
            note = ("Saved. Live apply skipped — Tailscale daemon may not be "
                    "running or authenticated yet. The new name will apply "
                    "on the next start.")
        if err_text.strip():
            logger.info("tailscale set --hostname rc=%d stderr=%s", rc, err_text.strip())
        return {
            "ok": True,
            "requested_hostname": sanitized,
            "effective_hostname": "",
            "applied_live": False,
            "note": note,
        }

    effective = _read_effective_hostname() or sanitized
    return {
        "ok": True,
        "requested_hostname": sanitized,
        "effective_hostname": effective,
        "applied_live": True,
        "collision_suffixed": effective != sanitized,
    }


# ── Route handlers ──────────────────────────────────────────────────────────


def handle_get_hostname(handler) -> dict[str, Any]:
    """GET /api/settings/hostname — returns current state for the UI."""
    return get_hostname_state()


def handle_set_hostname(handler, body: dict) -> dict[str, Any]:
    """POST /api/settings/hostname — body {"hostname": "<name>"}."""
    raw = body.get("hostname", "")
    if not isinstance(raw, str):
        return {"ok": False, "error": "hostname must be a string"}
    result = apply_hostname(raw)
    # Setting a hostname (whether from the wizard modal or Settings) implicitly
    # answers the post-wizard prompt — never re-fire it. Best-effort; failure
    # to set the flag must not fail the hostname save itself.
    if result.get("ok"):
        try:
            mark_hostname_prompted()
        except Exception:
            logger.exception("Failed to set hostname_prompted after save")
    return result


def handle_dismiss_hostname_prompt(handler, body: dict) -> dict[str, Any]:
    """POST /api/settings/hostname/dismiss-prompt — Skip button on the
    post-wizard modal. Marks prompted=true without setting any hostname,
    so Tailscale auto-naming continues to apply."""
    return mark_hostname_prompted()


# ──────────────────────────────────────────────────────────────────────
# Fox dispatcher integration — Phase 5 of v0.6.0 migration.
# Uses allow_bare=True because the module owns BOTH the bare
# /api/settings/hostname (GET + POST) and the /dismiss-prompt sub-path
# (POST). Wrapper does its own boundary check.
#
# Phase 7 update: `_write_env_key` now imported from
# fox_overlay.webui_modules.onboarding (was: api.onboarding before
# fork removed the file in Phase 7a). Same function, no behavior change.
# ──────────────────────────────────────────────────────────────────────
from fox_overlay import dispatch  # noqa: E402


def _handle_get(handler, parsed) -> bool:
    """GET /api/settings/hostname — returns True if handled, False to fall through."""
    from api.helpers import j

    if parsed.path == "/api/settings/hostname":
        j(handler, handle_get_hostname(handler))
        return True
    return False


def _handle_post(handler, parsed) -> bool:
    """POST /api/settings/hostname[/dismiss-prompt] — returns True if handled, False to fall through."""
    from api.helpers import j, read_body

    if parsed.path == "/api/settings/hostname":
        body = read_body(handler)
        result = handle_set_hostname(handler, body)
        j(handler, result, status=200 if result.get("ok") else 400)
        return True

    if parsed.path == "/api/settings/hostname/dismiss-prompt":
        body = read_body(handler)
        result = handle_dismiss_hostname_prompt(handler, body)
        j(handler, result, status=200 if result.get("ok") else 400)
        return True

    # /api/settings/hostnameX adjacency, or unknown sub-path → not ours.
    return False


# allow_bare=True: prefix omits trailing slash so dispatcher matches both
# /api/settings/hostname (bare) and /api/settings/hostname/dismiss-prompt.
# Boundary check above rejects /api/settings/hostnameX etc.
dispatch.register_get("/api/settings/hostname", _handle_get, allow_bare=True)
dispatch.register_post("/api/settings/hostname", _handle_post, allow_bare=True)

