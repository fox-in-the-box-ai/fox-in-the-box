"""GET /readyz — readiness probe (INSTANCE_CONTRACT §4.2).

Returns a structured readiness snapshot: ``ready`` (bool) is true iff
every check passes; ``checks`` is a dict of ``{ok, detail?}`` entries
whose keys are runtime-specific.

Auth position (§4.5): always unauthenticated.  At import time this
module adds ``/readyz`` to upstream ``api.auth.PUBLIC_PATHS`` so
``check_auth`` lets the request through before the dispatch hook runs.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)

_GATEWAY_PROGRAM = "hermes-gateway"
_QDRANT_HEALTH_URL = "http://127.0.0.1:6333/healthz"
_SUPERVISOR_CONF = os.environ.get("SUPERVISORD_CONF", "/etc/supervisor/supervisord.conf")


def _check_http_server() -> dict:
    return {"ok": True}


def _supervisorctl_status(program: str) -> str | None:
    if not shutil.which("supervisorctl"):
        return None
    try:
        result = subprocess.run(
            ["supervisorctl", "-c", _SUPERVISOR_CONF, "status", program],
            capture_output=True, text=True, timeout=5.0,
        )
        for line in (result.stdout or "").splitlines():
            parts = line.split()
            if parts and parts[0] == program and len(parts) >= 2:
                return parts[1]
    except (subprocess.TimeoutExpired, OSError):
        pass
    return None


def _check_agent_runtime() -> dict:
    status = _supervisorctl_status(_GATEWAY_PROGRAM)
    if status is None:
        return {"ok": True, "detail": "supervisor unavailable (standalone)"}
    if status == "RUNNING":
        return {"ok": True, "detail": f"{_GATEWAY_PROGRAM} {status}"}
    return {"ok": False, "detail": f"{_GATEWAY_PROGRAM} {status}"}


def _check_vector_store() -> dict:
    try:
        with urllib.request.urlopen(_QDRANT_HEALTH_URL, timeout=2) as resp:
            if resp.status == 200:
                return {"ok": True, "detail": "qdrant :6333 reachable"}
    except (urllib.error.URLError, OSError, ValueError):
        pass
    if not os.environ.get("QDRANT_URL") and not os.path.exists("/data/qdrant"):
        return {"ok": True, "detail": "qdrant not configured (standalone)"}
    return {"ok": False, "detail": "qdrant :6333 unreachable"}


def _check_config_loaded() -> dict:
    try:
        from api.config import load_settings
        settings = load_settings()
        if isinstance(settings, dict):
            return {"ok": True}
        return {"ok": False, "detail": "settings returned non-dict"}
    except Exception as exc:
        return {"ok": False, "detail": str(exc)}


def get_readiness() -> dict:
    checks = {
        "http_server": _check_http_server(),
        "agent_runtime": _check_agent_runtime(),
        "vector_store": _check_vector_store(),
        "config_loaded": _check_config_loaded(),
    }
    ready = all(c["ok"] for c in checks.values())
    return {"ready": ready, "checks": checks}


# ── Dispatcher integration ─────────────────────────────────────────────
# Expand PUBLIC_PATHS so check_auth lets /readyz through (§4.5).
try:
    import api.auth as _auth
    if "/readyz" not in _auth.PUBLIC_PATHS:
        _auth.PUBLIC_PATHS = _auth.PUBLIC_PATHS | frozenset({"/readyz"})
except ImportError:
    pass

from fox_overlay import dispatch  # noqa: E402


def _handle_get(handler, parsed) -> bool:
    if parsed.path != "/readyz":
        return False
    from api.helpers import j
    j(handler, get_readiness())
    return True


dispatch.register_get("/readyz", _handle_get, allow_bare=True)
