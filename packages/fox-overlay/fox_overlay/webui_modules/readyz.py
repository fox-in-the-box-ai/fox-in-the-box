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
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)

_GATEWAY_PROGRAM = "hermes-gateway"
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
    """Vector store (Qdrant) reachability — INSTANCE_CONTRACT §4.2.

    Resolves and probes the SAME endpoint ``_check_memory`` dials (the #803
    helpers) so the two checks can never contradict on Qdrant reachability.
    This check reflects ONLY Qdrant reachability: it stays ``ok: true`` when
    the embed-server or memory state is unhealthy but the store itself is up
    (those are ``_check_memory``'s concern, not this one).  Re-probed each
    request, like memory — no caching."""
    # Opt-out wins over any baked-in server URL.  MEM0_OSS_QDRANT_URL is set
    # unconditionally at the supervisord baseline and is NOT cleared when
    # memory is disabled (the entrypoint only sets MEM0_OSS_DISABLED=1), so
    # the server-mode branch would otherwise always win on a disabled
    # instance — reporting a misleading "reachable" and, if [program:qdrant]
    # is ever gated off alongside memory, a false ok:false.  Check disabled
    # FIRST, keyed off the SAME state.json "off" signal _check_memory reads
    # (via _memory_disabled), so the two fields can never contradict (#865).
    if _memory_disabled():
        return {"ok": True, "detail": "qdrant not in use (memory disabled)"}
    url = _memory_qdrant_readyz_url()
    if url is not None:
        # Server mode (MEM0_OSS_QDRANT_URL / _HOST set — the v0.7.63 default).
        parsed = urllib.parse.urlparse(url)
        target = f"{parsed.hostname}:{parsed.port}"
        if _memory_qdrant_reachable():
            return {"ok": True, "detail": f"qdrant server {target} reachable"}
        return {"ok": False, "detail": f"qdrant server {target} unreachable"}
    # No server to dial and memory is on: the embedded on-disk store is in
    # use.  Not a reachability failure — never probe here.
    return {"ok": True, "detail": "qdrant embedded (on-disk store)"}


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


def _memory_disabled() -> bool:
    """True iff the mem0_oss plugin reports status ``off`` (memory opted out).

    Tolerant read, mirroring ``_check_memory``: a missing, unreadable, or
    non-dict state is treated as NOT disabled, so the embedded on-disk store
    is assumed present rather than claiming memory is off."""
    path = _memory_state_path()
    try:
        with open(path, encoding="utf-8") as fh:
            state = json.load(fh)
    except (OSError, ValueError):
        return False
    if not isinstance(state, dict):
        return False
    return str(state.get("status", "")).strip().lower() == "off"


def _embed_health_url() -> str:
    """The embed-server /health URL the mem0_oss plugin actually probes.

    Read from env only — this module runs inside the webui process and must
    not import the hermes-agent plugin package.  Mirrors the plugin's own
    resolution EXACTLY (MEM0_OSS_EMBED_HEALTH_URL override, else the local
    default) so the readiness snapshot reflects the same endpoint memory
    dials.  Full-URL contract: the override is a complete URL (https works
    natively via urlopen); no host+port composition."""
    return os.environ.get("MEM0_OSS_EMBED_HEALTH_URL", "").strip() or _EMBED_HEALTH_URL


def _embed_server_alive() -> bool:
    """Any HTTP response from the embed server counts as alive (sleep-agnostic,
    §1.4); only connection refused / timeout is dead."""
    try:
        with urllib.request.urlopen(_embed_health_url(), timeout=2):
            return True
    except urllib.error.HTTPError:
        return True
    except (urllib.error.URLError, OSError, ValueError):
        return False


def _memory_qdrant_readyz_url() -> str | None:
    """When the mem0_oss plugin is in Qdrant server mode (MEM0_OSS_QDRANT_URL
    or _HOST set), return the ``/readyz`` URL of that server; else ``None``.

    Read from env only — this module runs inside the webui process and must
    not import the hermes-agent plugin package.  Mirrors the plugin's
    ``_resolve_qdrant_target`` scheme/port rules so the readiness snapshot
    reflects the same endpoint memory actually dials."""
    url = os.environ.get("MEM0_OSS_QDRANT_URL", "").strip()
    host_env = os.environ.get("MEM0_OSS_QDRANT_HOST", "").strip()
    if not (url or host_env):
        return None
    api_key = os.environ.get("MEM0_OSS_QDRANT_API_KEY", "").strip()
    port_env = os.environ.get("MEM0_OSS_QDRANT_PORT", "").strip()
    try:
        port_default = int(port_env) if port_env else 6333
    except ValueError:
        # A bad port is a plugin-side config error surfaced via state.json;
        # here just fall back so the probe URL is still well-formed.
        port_default = 6333
    if url:
        parsed = urllib.parse.urlparse(url)
        # Intentional divergence from the plugin's _resolve_qdrant_target,
        # which falls back to "" here: this side builds a dial-able probe URL,
        # so a hostless URL falls back to 127.0.0.1 (the co-located server).
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or port_default
        scheme = "https" if parsed.scheme == "https" else "http"
    else:
        host = host_env
        port = port_default
        scheme = "https" if api_key else "http"
    return f"{scheme}://{host}:{port}/readyz"


def _memory_qdrant_reachable() -> bool:
    """Probe the server-mode Qdrant ``/readyz`` (2 s timeout).  Any HTTP
    response means live (readiness-agnostic, mirroring the plugin's probe);
    only connection refused / timeout / DNS failure is unreachable."""
    url = _memory_qdrant_readyz_url()
    if url is None:
        return True  # not server mode — nothing to probe
    req = urllib.request.Request(url, method="GET")
    api_key = os.environ.get("MEM0_OSS_QDRANT_API_KEY", "").strip()
    if api_key:
        req.add_header("api-key", api_key)
    try:
        with urllib.request.urlopen(req, timeout=2):
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
            # Name the RESOLVED endpoint (mirrors _check_vector_store's qdrant
            # target) so an operator overriding MEM0_OSS_EMBED_HEALTH_URL sees
            # the address actually dialed, not a stale ":8644".  Fall back to
            # the full URL if a malformed override leaves netloc empty.
            parsed = urllib.parse.urlparse(_embed_health_url())
            target = parsed.netloc or _embed_health_url()
            return {"ok": False, "detail": f"embed-server {target} unreachable"}
        # Re-evaluate the Qdrant server reachability at request time (boot
        # ordering: preflight seeds "ready" before supervisord starts qdrant,
        # so state.json alone would contradict vector_store during the window
        # before the server is up).  In server mode a genuinely-down qdrant
        # fails loud here — consistent with vector_store — rather than reading
        # ready while the store is unreachable.
        if not _memory_qdrant_reachable():
            return {"ok": False, "detail": "memory qdrant server unreachable"}
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
