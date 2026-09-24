"""GET /readyz — readiness probe (INSTANCE_CONTRACT §4.2).

Returns a structured readiness snapshot: ``ready`` (bool) is true iff
every check passes; ``checks`` is a dict of ``{ok, detail?}`` entries
whose keys are runtime-specific.

Auth position (§4.5): always unauthenticated.  At import time this
module adds ``/readyz`` to upstream ``api.auth.PUBLIC_PATHS`` so
``check_auth`` lets the request through before the dispatch hook runs.
"""

from __future__ import annotations

import configparser
import http.client
import json
import logging
import os
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import xmlrpc.client

logger = logging.getLogger(__name__)

_GATEWAY_PROGRAM = "hermes-gateway"
_SUPERVISOR_CONF = os.environ.get(
    "SUPERVISORD_CONF", "/etc/supervisor/supervisord.conf"
)
_EMBED_HEALTH_URL = "http://127.0.0.1:8644/health"

# Single-flight, short-TTL cache over the whole readiness snapshot.  /readyz
# is public, unauthenticated, and served one-thread-per-request, so a burst
# must collapse to one underlying probe per window instead of dialing every
# dependency per request.  The TTL is well under the 30s Docker HEALTHCHECK
# interval, so a real dependency transition still surfaces within one window
# (#914).  The unhealthy snapshot is cached too — a flood during an outage
# must not re-probe per request.
_READINESS_TTL_S = 1.0
_readiness_lock = threading.Lock()
_readiness_cache: tuple[float, dict] | None = None  # (monotonic_ts, snapshot)


def _check_http_server() -> dict:
    return {"ok": True}


def _supervisor_sock() -> str | None:
    """Resolve the supervisord control-socket path.

    ``SUPERVISORD_SOCK`` wins (container-vs-deb topologies differ:
    /run/fitb/supervisor.sock vs /run/foxinthebox/supervisor.sock); otherwise
    read ``[unix_http_server] file=`` from ``_SUPERVISOR_CONF``.  None means
    'no supervisord configured' (standalone)."""
    override = os.environ.get("SUPERVISORD_SOCK", "").strip()
    if override:
        return override
    parser = configparser.ConfigParser()
    try:
        parser.read(_SUPERVISOR_CONF)
        path = parser.get("unix_http_server", "file", fallback="").strip()
    except (configparser.Error, OSError):
        return None
    return path or None


def _supervisorctl_available() -> bool:
    """True iff a supervisord control socket is present on disk.

    Its ABSENCE is the one positively-verified 'standalone' signal.  A present
    socket whose XML-RPC query cannot be read is 'unknown', not standalone —
    the two must never be conflated (see ``_check_agent_runtime``, #904)."""
    sock = _supervisor_sock()
    return bool(sock) and os.path.exists(sock)


class _UnixStreamHTTPConnection(http.client.HTTPConnection):
    """HTTPConnection over an AF_UNIX stream socket (``host`` is the path)."""

    def connect(self) -> None:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(self.timeout)
        s.connect(self.host)
        self.sock = s


class _UnixStreamTransport(xmlrpc.client.Transport):
    """xmlrpc.client transport that dials supervisord's unix socket directly —
    stdlib only, so /readyz no longer forks a supervisorctl subprocess per
    request (#914)."""

    def __init__(self, sock_path: str) -> None:
        super().__init__()
        self._sock_path = sock_path

    def make_connection(self, host):  # noqa: ARG002 — path carried on the transport
        return _UnixStreamHTTPConnection(self._sock_path, timeout=2.0)


def _supervisorctl_status(program: str) -> str | None:
    """supervisord process ``statename`` for *program* over the unix-socket
    XML-RPC API, or None when it could not be read (socket gone, timeout,
    connection error, or an XML-RPC fault such as BAD_NAME).

    Callers MUST treat None as 'unknown' and fail closed, never as
    'standalone'; the standalone case is detected separately via
    ``_supervisorctl_available()`` (#904).  The 2s socket timeout is tighter
    than the old 5s subprocess timeout so a wedged supervisord yields None
    rather than pinning the single-flight lock."""
    sock = _supervisor_sock()
    if not sock:
        return None
    try:
        proxy = xmlrpc.client.ServerProxy(
            "http://localhost", transport=_UnixStreamTransport(sock)
        )
        info = proxy.supervisor.getProcessInfo(program)
    except (OSError, xmlrpc.client.Fault, xmlrpc.client.ProtocolError):
        return None
    if isinstance(info, dict):
        return info.get("statename")
    return None


def _check_agent_runtime() -> dict:
    # Genuine standalone / runtime-agnostic deployment: no supervisor at all.
    if not _supervisorctl_available():
        return {"ok": True, "detail": "supervisor unavailable (standalone)"}
    # Supervisor is present — its gateway status must be verified.  A status
    # we could not read (timeout / error / gateway absent from output) is
    # 'unknown' and fails closed; masking it as healthy is the #904 fail-open.
    status = _supervisorctl_status(_GATEWAY_PROGRAM)
    if status is None:
        logger.warning("agent_runtime status unknown: supervisor query failed")
        return {
            "ok": False,
            "detail": "gateway status unknown (supervisor query failed)",
        }
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
        try:
            parsed = urllib.parse.urlparse(url)
            # Intentional divergence from the plugin's _resolve_qdrant_target,
            # which falls back to "" here: this side builds a dial-able probe URL,
            # so a hostless URL falls back to 127.0.0.1 (the co-located server).
            host = parsed.hostname or "127.0.0.1"
            port = parsed.port or port_default
            scheme = "https" if parsed.scheme == "https" else "http"
        except ValueError:
            # A malformed URL (out-of-range/non-numeric port, unbracketed IPv6)
            # makes urlparse / parsed.port raise.  Mirror the bad-port env
            # fallback above so the probe URL stays well-formed and /readyz
            # returns a structured result instead of a 500 traceback (#885).
            # Fail-loud on the bad config is carried by the MEMORY check, not
            # this one: the plugin's _resolve_qdrant_target raises on the same
            # value -> state.json status=error -> _check_memory ok:false ->
            # aggregate ready:false.  vector_store is only a best-effort probe
            # of this fallback target, which on a default instance IS the live
            # co-located server (127.0.0.1:6333) and so may still read
            # reachable -- don't rely on vector_store to flag the typo.
            host, port, scheme = "127.0.0.1", port_default, "http"
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
            embed_url = _embed_health_url()
            target = urllib.parse.urlparse(embed_url).netloc or embed_url
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


def _compute_readiness() -> dict:
    checks = {
        "http_server": _check_http_server(),
        "agent_runtime": _check_agent_runtime(),
        "vector_store": _check_vector_store(),
        "config_loaded": _check_config_loaded(),
        "memory": _check_memory(),
    }
    ready = all(c["ok"] for c in checks.values())
    return {"ready": ready, "checks": checks}


def get_readiness() -> dict:
    """Cached front door over ``_compute_readiness`` (#914).

    Double-checked locking collapses a concurrent burst of /readyz probes onto
    a single underlying computation per TTL window; the single-flight lock caps
    concurrent external work (the supervisord query plus the two 2s HTTP probes
    on a configured instance) at exactly one probe per window.  The returned
    dict is shared by reference across a window and must not be mutated."""
    global _readiness_cache
    cached = _readiness_cache
    if cached is not None and time.monotonic() - cached[0] < _READINESS_TTL_S:
        return cached[1]
    with _readiness_lock:
        cached = _readiness_cache
        if cached is not None and time.monotonic() - cached[0] < _READINESS_TTL_S:
            return cached[1]
        snapshot = _compute_readiness()
        _readiness_cache = (time.monotonic(), snapshot)
        return snapshot


def clear_cache() -> None:
    """Drop the cached snapshot (tests / explicit refresh; mirrors ollama.py)."""
    global _readiness_cache
    with _readiness_lock:
        _readiness_cache = None


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
