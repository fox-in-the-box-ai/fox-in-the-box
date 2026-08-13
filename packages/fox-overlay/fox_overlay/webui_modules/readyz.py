"""GET /readyz — readiness probe (INSTANCE_CONTRACT §4.2).

Returns a structured readiness snapshot: ``ready`` (bool) is true iff
every check passes; ``checks`` is a dict of ``{ok, detail?}`` entries
whose keys are runtime-specific.

Auth position (§4.5): always unauthenticated.  At import time this
module adds ``/readyz`` to upstream ``api.auth.PUBLIC_PATHS`` so
``check_auth`` lets the request through before the dispatch hook runs.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)

_GATEWAY_PROGRAM = "hermes-gateway"
_QDRANT_HEALTH_URL = "http://127.0.0.1:6333/healthz"
_SUPERVISOR_CONF = os.environ.get(
    "SUPERVISORD_CONF", "/etc/supervisor/supervisord.conf"
)
_EMBED_HEALTH_URL = "http://127.0.0.1:8644/health"


def _check_http_server() -> dict:
    return {"ok": True}


def _supervisorctl_status(program: str) -> str | None:
    if not shutil.which("supervisorctl"):
        return None
    try:
        result = subprocess.run(
            ["supervisorctl", "-c", _SUPERVISOR_CONF, "status", program],
            capture_output=True,
            text=True,
            timeout=5.0,
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


def _memory_state_path() -> str:
    """Path to the mem0_oss plugin's state.json (no hermes-agent import —
    this module runs inside the webui process)."""
    override = os.environ.get("MEM0_OSS_STATE_PATH", "").strip()
    if override:
        return override
    hermes_home = os.environ.get("HERMES_HOME", "/data/data/hermes")
    return os.path.join(hermes_home, "mem0_oss", "state.json")


def _embed_server_alive() -> bool:
    """Any HTTP response from :8644 counts as alive (sleep-agnostic, §1.4);
    only connection refused / timeout is dead."""
    try:
        with urllib.request.urlopen(_EMBED_HEALTH_URL, timeout=2):
            return True
    except urllib.error.HTTPError:
        return True
    except (urllib.error.URLError, OSError, ValueError):
        return False


def _check_memory() -> dict:
    """Memory component (design §a.2): read state.json; ``ok: false`` ONLY
    for severity=error states.  "off" is a visible-but-healthy state; a
    missing or unreadable state file is tolerated (tolerant reader)."""
    path = _memory_state_path()
    try:
        with open(path, encoding="utf-8") as fh:
            state = json.load(fh)
    except FileNotFoundError:
        return {"ok": True, "detail": "memory state not reported yet"}
    except (OSError, ValueError):
        return {"ok": True, "detail": "memory state unreadable"}
    if not isinstance(state, dict):
        return {"ok": True, "detail": "memory state unreadable"}

    status = str(state.get("status", "")).strip().lower()
    reason = str(state.get("reason", "") or "").strip()
    if status == "error":
        return {"ok": False, "detail": reason or "memory error"}
    if status == "ready":
        # state.json says ready — cross-check the embed-server port (state 8),
        # but only when the local default embedder is in use.
        embedder = str(state.get("embedder", "") or "").strip()
        if embedder.startswith("local:") and not _embed_server_alive():
            return {"ok": False, "detail": "embed-server :8644 unreachable"}
        llm = str(state.get("llm", "") or "").strip()
        detail = f"memory ready (llm={llm})" if llm else "memory ready"
        return {"ok": True, "detail": detail}
    if status == "off":
        return {"ok": True, "detail": reason or "memory off"}
    return {"ok": True, "detail": f"memory state '{status}' unrecognized"}


def get_readiness() -> dict:
    checks = {
        "http_server": _check_http_server(),
        "agent_runtime": _check_agent_runtime(),
        "vector_store": _check_vector_store(),
        "config_loaded": _check_config_loaded(),
        "memory": _check_memory(),
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
