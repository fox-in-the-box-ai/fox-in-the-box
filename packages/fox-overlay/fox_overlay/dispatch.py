"""Fox dispatcher: called by the 6-line patch in api/routes.py before
the upstream `if/elif` chain.

Phase 4 ships an EMPTY dispatch table — ``handle_get`` and
``handle_post`` return ``False`` so every request falls through to
upstream. The mechanism exists; nothing claims any route yet.

* Phase 5 populates the table for Fox additive modules (ollama,
  tailscale, local_fallback, models_download, hostname,
  session_recovery) via ``register_get/post`` calls at module load.
* Phase 7 wires the onboarding wholesale-replace through the same
  table.

## Threading contract

Registration is bootstrap-only — call ``register_get/register_post``
during ``fox_overlay.bootstrap`` (i.e. at server-module import, BEFORE
``ThreadingHTTPServer.serve_forever``). Hermes WebUI runs on
``ThreadingHTTPServer`` with ``daemon_threads=True`` (server.py),
so mutating the tables after the server is serving requests races
with iteration in ``handle_get``/``handle_post`` and CPython raises
``RuntimeError: dictionary changed size during iteration``. The
``_BootstrapState.frozen`` flag enforces this: any registration
after ``freeze()`` raises.

## Path-prefix contract

``register_get/post`` enforces:

* prefix MUST start with ``/`` and end with ``/`` (so
  ``startswith`` matching can't accept ``/api/fox-evil`` as a hit on
  prefix ``/api/fox``)
* prefix MUST NOT be empty or ``/`` (would shadow everything)
* prefix MUST NOT overlap auth-public namespaces (``/static/``,
  ``/session/static/``, ``/login``, ``/api/auth/``, ``/health``,
  ``/favicon.ico``, ``/sw.js``, ``/manifest``) — those bypass
  ``check_auth`` in upstream, so a Fox handler registered there
  would be reachable unauthenticated.

Path-traversal note: ``parsed.path`` from ``urllib.parse.urlparse``
is NOT normalized; ``/api/fox/../etc/passwd`` would match prefix
``/api/fox/``. Each Fox handler is responsible for its own
path-traversal sandbox (Phase 5+ handlers MUST use
``pathlib.Path.resolve().relative_to(...)`` for any filesystem
operation, matching upstream's ``_serve_static`` convention).

## CSRF note (for Phase 5 handlers)

Upstream's ``_check_csrf`` (api/routes.py) bypasses cross-origin
rejection when the request has neither ``Origin`` nor ``Referer``
headers — i.e. any non-browser caller (curl, native app, SSRF from
inside the container's LAN) bypasses CSRF entirely. The
dispatcher inherits this behavior because the hook runs AFTER
``_check_csrf`` in ``handle_post``. Phase 5 handlers that perform
state-changing operations (ollama install, tailscale auth,
hostname rename) MUST treat all POSTs as potentially unauthenticated
cross-origin until the Phase 5 design decision on per-prefix
``requires_csrf=True`` lands.

## Handler return contract

Handlers receive ``(handler, parsed)``:

* ``handler``: ``http.server.BaseHTTPRequestHandler`` subclass with
  the active request. Read body with the upstream ``read_body(handler)``
  helper if needed; the dispatcher does NOT consume the body.
* ``parsed``: ``urllib.parse.ParseResult`` from ``urlparse(self.path)``.

Return value:

* ``True`` — the handler responded; the dispatcher returns ``True``
  and upstream's ``if/elif`` chain is skipped.
* ``False`` — the handler declined; the dispatcher moves to the next
  registered prefix (or returns ``False`` so upstream handles it).
* ``None`` or anything else — explicit ``RuntimeError``. Falsy
  returns are too easy to produce by mistake (``return j(handler, ...)``
  returns ``None``) and would silently double-respond when upstream
  also takes the route. The dispatcher rejects them loudly.
"""
from __future__ import annotations

import logging
from http.server import BaseHTTPRequestHandler
from types import MappingProxyType
from typing import Callable
from urllib.parse import ParseResult

logger = logging.getLogger(__name__)

HandlerFn = Callable[[BaseHTTPRequestHandler, ParseResult], bool]

# Upstream namespaces that bypass check_auth (see hermes-webui api/auth.py
# PUBLIC_PATHS and is_public_path). Registering a Fox handler on any of
# these would make it reachable unauthenticated.
_AUTH_PUBLIC_PREFIXES = (
    "/static/",
    "/session/static/",
    "/login",
    "/api/auth/",
    "/health",
    "/favicon.ico",
    "/sw.js",
    "/manifest",
)

_GET_TABLE: dict[str, HandlerFn] = {}
_POST_TABLE: dict[str, HandlerFn] = {}


class _BootstrapState:
    frozen: bool = False


def _validate_prefix(path_prefix: str, allow_bare: bool = False) -> None:
    if not isinstance(path_prefix, str):
        raise TypeError(f"path_prefix must be str, got {type(path_prefix).__name__}")
    if not path_prefix.startswith("/"):
        raise ValueError(f"path_prefix must start with '/': {path_prefix!r}")
    if not allow_bare and not path_prefix.endswith("/"):
        raise ValueError(
            f"path_prefix must end with '/' so startswith() can't match "
            f"adjacent paths (e.g. '/api/fox' matches '/api/fox-evil'): "
            f"{path_prefix!r}. If you need to dispatch both the bare path "
            f"and sub-paths (e.g. /api/foo for list, /api/foo/<id> for item), "
            f"pass allow_bare=True and do your own boundary check inside the "
            f"handler."
        )
    if path_prefix == "/":
        raise ValueError("path_prefix '/' would shadow every upstream route")
    for public in _AUTH_PUBLIC_PREFIXES:
        if path_prefix.startswith(public) or public.startswith(path_prefix):
            raise ValueError(
                f"path_prefix {path_prefix!r} overlaps auth-public namespace "
                f"{public!r}; a Fox handler here would be reachable "
                f"unauthenticated. If this is intentional, register from a "
                f"non-overlapping prefix and forward."
            )


def _register(table: dict[str, HandlerFn], path_prefix: str, handler: HandlerFn,
              allow_bare: bool = False) -> None:
    if _BootstrapState.frozen:
        raise RuntimeError(
            f"dispatcher table frozen; register {path_prefix!r} during "
            f"fox_overlay.bootstrap, not after serve_forever()"
        )
    _validate_prefix(path_prefix, allow_bare=allow_bare)
    if path_prefix in table:
        logger.warning(
            "fox_overlay.dispatch: overwriting handler for %r "
            "(previous: %s, new: %s)",
            path_prefix,
            getattr(table[path_prefix], "__qualname__", repr(table[path_prefix])),
            getattr(handler, "__qualname__", repr(handler)),
        )
    else:
        logger.info(
            "fox_overlay.dispatch: registered %r -> %s",
            path_prefix,
            getattr(handler, "__qualname__", repr(handler)),
        )
    table[path_prefix] = handler


def register_get(path_prefix: str, handler: HandlerFn, *, allow_bare: bool = False) -> None:
    """Register a GET handler for the given path prefix.

    ``allow_bare=True`` lets the prefix omit the trailing ``/``, which is
    required for modules that need to handle BOTH a bare path (e.g.
    ``/api/local-models`` for a list endpoint) AND sub-paths (e.g.
    ``/api/local-models/<id>/progress``). In that mode, the handler MUST
    do its own boundary check (reject paths like ``/api/local-modelsX``)
    because ``startswith()`` cannot enforce the segment boundary alone.
    """
    _register(_GET_TABLE, path_prefix, handler, allow_bare=allow_bare)


def register_post(path_prefix: str, handler: HandlerFn, *, allow_bare: bool = False) -> None:
    """Register a POST handler for the given path prefix.

    See ``register_get`` for the ``allow_bare`` semantics.
    """
    _register(_POST_TABLE, path_prefix, handler, allow_bare=allow_bare)


def freeze() -> None:
    """Freeze the dispatch tables; subsequent registrations raise.

    Called by ``fox_overlay.bootstrap`` after all Phase 5+ overlay
    modules have registered. Iteration after freeze is safe because
    the dicts are never mutated again.
    """
    _BootstrapState.frozen = True


def _dispatch(table: dict[str, HandlerFn], handler, parsed) -> bool:
    for prefix, fn in table.items():
        if parsed.path.startswith(prefix):
            result = fn(handler, parsed)
            if result is True:
                return True
            if result is False:
                continue
            raise RuntimeError(
                f"Fox handler {getattr(fn, '__qualname__', fn)} returned "
                f"{result!r} for {parsed.path!r}; must return True (handled) "
                f"or False (decline). Falsy returns risk double-responding."
            )
    return False


def handle_get(handler, parsed) -> bool:
    """Dispatch a GET request. Returns False if no Fox handler claims it."""
    return _dispatch(_GET_TABLE, handler, parsed)


def handle_post(handler, parsed) -> bool:
    """Dispatch a POST request. Returns False if no Fox handler claims it."""
    return _dispatch(_POST_TABLE, handler, parsed)


# Read-only views — for tests and introspection without leaking mutability.
GET_TABLE = MappingProxyType(_GET_TABLE)
POST_TABLE = MappingProxyType(_POST_TABLE)
