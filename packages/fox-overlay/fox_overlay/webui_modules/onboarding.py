"""Hermes Web UI -- Onboarding wizard backend.

Provides the /setup page and /api/setup/* endpoints for first-run configuration.
The redirect middleware sends users to /setup until onboarding is complete.

Part of Fox in the Box (issue #28).
"""

import json
import logging
import os
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Onboarding state file ────────────────────────────────────────────────────

ONBOARDING_PATH = Path(os.environ.get("ONBOARDING_PATH", "/data/config/onboarding.json"))

# ── Paths exempt from redirect ───────────────────────────────────────────────

# Wizard probes Ollama and the bundled local-fallback during boot to render
# the local-model fast-paths on Step 1 (#69). Without these prefixes the
# probes 302 to /setup, fetch follows, JSON.parse fails on HTML, the .catch
# in setup.js silently zeros state.ollama / state.localFallback, and the
# detection boxes never render — even when Ollama is running on the host.
_SETUP_PREFIXES = (
    "/setup",
    "/api/setup/",
    "/api/ollama/",
    "/api/local-fallback/",
    # v0.7.13 #331: setup assets now served at /extensions/ via
    # HERMES_WEBUI_EXTENSION_DIR (the Dockerfile env wire), not /static/.
    # The old /static/setup. entry was stale dead code since v0.6.0 P2 —
    # whitelisted a path that would 404 anyway. Updating to the live path
    # so the wizard's CSS + JS load cleanly without being bounced.
    "/extensions/",
    "/health",
    "/static/",
    # v0.7.17: /test/* routes are gated by FITB_TEST_MODE=1 in fox-overlay's
    # bootstrap, so in production builds they don't exist and whitelisting
    # them is a no-op. In CI / playwright runs FITB_TEST_MODE=1 is set and
    # /test/reset MUST return JSON, not get 302'd to /setup. Latent bug
    # since v0.7.15 (the release that added patch 003); only surfaced in
    # v0.7.17 PR CI because PR-time `:stable` was finally v0.7.16 (the
    # first :stable with patch 003 actually applied — v0.7.13/14 had
    # patch 003 written but the series file missed it).
    "/test/",
    # v0.7.21: /api/models is a public read endpoint that should work
    # regardless of onboarding state — it's how the chat UI populates the
    # model picker, and the model-picker.spec.ts smoke needs to hit it
    # against a fresh container without first completing onboarding.
    # Same shape as the /test/ whitelist above.
    "/api/models",
    # Contract endpoints: Fleet conformance suite probes these before
    # onboarding completes. Auth is handled by check_auth (X-Fox-Auth
    # or session cookie), not by onboarding state.
    "/readyz",
    "/version",
    "/capabilities",
    # Auth flow: check_auth redirects /setup → login?next=/setup, so
    # /login and /api/auth/ must be exempt to break the chicken-and-egg
    # (patch 003 places the onboarding redirect before check_auth).
    "/login",
    "/api/auth/",
)


def onboarding_complete() -> bool:
    """Check whether onboarding has been completed.

    Reads either of two state surfaces — historical FITB
    `onboarding.json:completed` and Hermes WebUI's
    `settings.json:onboarding_completed` — and returns True if either is
    set. Issue #11 added the `settings.json` write so future code that
    sets it directly (e.g. CLI bootstrappers) is honoured by the
    redirect middleware. Either flag flipping unlocks the chat UI.
    """
    try:
        with open(ONBOARDING_PATH) as f:
            if json.load(f).get("completed", False) is True:
                return True
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    try:
        from api.config import load_settings
        if load_settings().get("onboarding_completed") is True:
            return True
    except Exception:  # broad on purpose — settings are auxiliary state
        pass
    return False


def is_setup_path(path: str) -> bool:
    """Return True if the request path is exempt from the onboarding redirect."""
    return any(path.startswith(prefix) for prefix in _SETUP_PREFIXES)


def should_redirect_to_setup(path: str) -> bool:
    """Return True if the request should be redirected to /setup."""
    if onboarding_complete():
        return False
    if is_setup_path(path):
        return False
    return True


def redirect_to_setup(handler) -> None:
    """Send a 302 redirect to /setup."""
    handler.send_response(302)
    handler.send_header("Location", "/setup")
    handler.send_header("Content-Length", "0")
    handler.end_headers()


# ── ENV file helpers ─────────────────────────────────────────────────────────

_ENV_PATH = Path(os.environ.get("HERMES_ENV_PATH", "/data/config/hermes.env"))


def _write_env_key(key: str, value: str) -> None:
    """Write or update a key=value pair in the env file.

    Creates the file and parent directory if they do not exist.
    Preserves existing lines. Updates in-place if key already present.
    """
    _ENV_PATH.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    if _ENV_PATH.exists():
        lines = _ENV_PATH.read_text(encoding="utf-8").splitlines()

    found = False
    for i, raw in enumerate(lines):
        stripped = raw.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            existing_key = stripped.split("=", 1)[0].strip()
            if existing_key == key:
                lines[i] = f"{key}={value}"
                found = True
                break

    if not found:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append(f"{key}={value}")

    _ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ── Setup route handlers ─────────────────────────────────────────────────────


def handle_setup_page(handler) -> None:
    """Serve the setup.html page from overlay's webui_static (post-Phase-7)."""
    # Phase 7 (v0.6.0): setup.html moved from fork's static/ to overlay's
    # webui_static/. Read from overlay-local path; do NOT depend on
    # api.config.REPO_ROOT (fork-side concept).
    from pathlib import Path as _Path
    setup_path = _Path(__file__).resolve().parent.parent.parent / "webui_static" / "setup.html"
    if not setup_path.exists():
        handler.send_response(500)
        handler.send_header("Content-Type", "text/plain")
        body = b"Setup page not found"
        handler.send_header("Content-Length", str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)
        return
    html = setup_path.read_bytes()
    handler.send_response(200)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(html)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(html)


def handle_setup_openrouter(handler, body: dict) -> dict:
    """Validate and persist an OpenRouter API key.

    Returns a result dict. Never logs the key value.
    """
    key = body.get("key", "")
    if not isinstance(key, str):
        return {"ok": False, "error": "Key must be a string."}
    key = key.strip()
    if not key:
        return {"ok": False, "error": "API key is required."}
    if not key.startswith("sk-"):
        return {"ok": False, "error": "Key must start with sk-."}
    if len(key) > 512:
        return {"ok": False, "error": "Key is too long."}

    try:
        _write_env_key("OPENROUTER_API_KEY", key)
    except OSError as exc:
        logger.error("Failed to write env file: %s", exc)
        return {"ok": False, "error": "Failed to save key."}

    return {"ok": True}


def handle_setup_complete(handler, body: dict) -> dict:
    """Mark onboarding as complete and write the state files."""
    tailscale_connected = bool(body.get("tailscale_connected", False))
    return _mark_onboarding_complete(
        skipped=False,
        extra={"tailscale_connected": tailscale_connected},
    )


def handle_setup_skip(handler, body: dict) -> dict:
    """Mark onboarding as skipped (no API key collected). Issue #11.

    Provides an exit hatch for users who want to configure providers
    later via Settings → Providers, or who'll rely on local Ollama
    (#66). Sets the same completion flags as a normal finish — the
    redirect middleware unlocks the main UI immediately.
    """
    return _mark_onboarding_complete(skipped=True)


def _mark_onboarding_complete(*, skipped: bool, extra: dict | None = None) -> dict:
    """Write both `onboarding.json` and `settings.json:onboarding_completed`.

    Two state surfaces are kept in sync (issue #11) so the redirect
    middleware and the WebUI settings panel agree. Failure to write
    settings.json is non-fatal — onboarding.json is the authoritative
    flag for the redirect.
    """
    ONBOARDING_PATH.parent.mkdir(parents=True, exist_ok=True)
    state = {
        "completed": True,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "skipped": bool(skipped),
    }
    if extra:
        state.update(extra)
    ONBOARDING_PATH.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")

    # Mirror to settings.json:onboarding_completed so any code path that
    # consults settings (e.g. future CLI bootstrappers) sees the same truth.
    try:
        from api.config import load_settings, save_settings
        s = load_settings()
        s["onboarding_completed"] = True
        save_settings(s)
    except Exception as exc:
        logger.debug("Could not mirror onboarding flag to settings.json: %s", exc)

    return {"ok": True, "skipped": bool(skipped)}


# ── Welcome content ─────────────────────────────────────────────────────────

# Externalized so the welcome message can be edited per install without a
# code change (issue #11 AC: "Script is externalised — editable without
# code change"). Plain text, paragraphs separated by blank lines. The
# default below ships in packages/integration/default-configs/onboarding.md
# and is copied into /data/config on first container run by entrypoint.sh.

_ONBOARDING_MD_PATH = Path(os.environ.get(
    "ONBOARDING_MD_PATH", "/data/config/onboarding.md"
))

_DEFAULT_WELCOME = (
    "Let's get you set up. This will only take a minute.\n\n"
    "Bring an OpenRouter API key for cloud models, or skip this wizard "
    "if you're running a local AI on your computer (Ollama, LM Studio, "
    "etc.) — you can configure providers any time from Settings."
)


def read_welcome_text() -> str:
    """Return the welcome paragraph(s) for the wizard's first step.
    Reads /data/config/onboarding.md if present, falls back to the
    bundled default."""
    try:
        if _ONBOARDING_MD_PATH.exists():
            text = _ONBOARDING_MD_PATH.read_text(encoding="utf-8").strip()
            if text:
                return text
    except OSError as exc:
        logger.debug("Could not read %s: %s", _ONBOARDING_MD_PATH, exc)
    return _DEFAULT_WELCOME


def handle_setup_welcome(handler) -> dict:
    """GET /api/setup/welcome — returns the (editable) welcome text."""
    return {"text": read_welcome_text()}


def handle_setup_restart(handler) -> dict:
    """Restart hermes-gateway and hermes-webui via supervisorctl."""
    try:
        result = subprocess.run(
            [
                "supervisorctl",
                "-c", os.environ.get("SUPERVISORD_CONF", "/etc/supervisor/supervisord.conf"),
                "restart", "hermes-gateway", "hermes-webui",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            return {"ok": True}
        return {"ok": False, "error": result.stderr.strip() or "Restart failed."}
    except FileNotFoundError:
        return {"ok": False, "error": "supervisorctl not found."}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "Restart timed out."}
    except OSError as exc:
        return {"ok": False, "error": str(exc)}


# ──────────────────────────────────────────────────────────────────────
# Fox dispatcher integration — Phase 7 of v0.6.0 migration.
# Three dispatcher registrations:
#   * GET  /setup            (allow_bare=True) — handle_setup_page
#   * GET  /api/setup/       — handle_setup_welcome
#   * POST /api/setup/       — handle_setup_{openrouter,complete,skip,restart}
# api.helpers lazy-imported inside each wrapper (see ollama.py rationale).
#
# `_write_env_key` (defined above at line ~93) is also exported by name so
# fox_overlay.webui_modules.hostname can import it from here (pre-Phase-7
# hostname read it from api.onboarding — fork's api/onboarding.py removed
# in fork PR #30 so the import had to move).
# ──────────────────────────────────────────────────────────────────────
from fox_overlay import dispatch  # noqa: E402


def _handle_get(handler, parsed) -> bool:
    """GET /setup — returns True if handled, False to fall through.

    allow_bare=True boundary: must reject /setupX adjacency. The single
    exact-match check below does this naturally (any /setupX path fails
    the == check and returns False).
    """
    if parsed.path == "/setup":
        handle_setup_page(handler)
        return True
    return False


def _handle_api_setup_get(handler, parsed) -> bool:
    """GET /api/setup/* — returns True if handled, False to fall through."""
    from api.helpers import j

    if parsed.path == "/api/setup/welcome":
        j(handler, handle_setup_welcome(handler))
        return True
    return False


def _handle_api_setup_post(handler, parsed) -> bool:
    """POST /api/setup/* — returns True if handled, False to fall through."""
    from api.helpers import j, read_body

    body = read_body(handler)

    if parsed.path == "/api/setup/openrouter":
        result = handle_setup_openrouter(handler, body)
        j(handler, result)  # pre-migration: j(handler, result) no ok-check
        return True

    if parsed.path == "/api/setup/complete":
        result = handle_setup_complete(handler, body)
        j(handler, result)
        return True

    if parsed.path == "/api/setup/restart":
        result = handle_setup_restart(handler)
        j(handler, result)
        return True

    if parsed.path == "/api/setup/skip":
        result = handle_setup_skip(handler, body)
        j(handler, result)
        return True

    return False


dispatch.register_get("/setup", _handle_get, allow_bare=True)
dispatch.register_get("/api/setup/", _handle_api_setup_get)
dispatch.register_post("/api/setup/", _handle_api_setup_post)
