"""Fox webui patch: auth_body_drain.py — close keep-alive on auth rejection (#559).

Wraps ``check_auth`` in ``api/auth.py`` so that when authentication
fails (``check_auth`` returns ``False``), ``handler.close_connection``
is set to ``True``.  Without this, a rejected POST request leaves its
unread body in the socket buffer; Python's ``BaseHTTPRequestHandler``
then tries to parse those bytes as the next HTTP request on the
keep-alive connection, corrupting the stream.

Setting ``close_connection = True`` causes ``handle_one_request`` to
exit its loop after the current response is flushed — the server
closes the TCP connection cleanly and never tries to read a second
request from the tainted buffer.

Uses the wrap-and-splice pattern (post-call behavior change) rather
than ``substitute_function`` (mid-function source edit) per the
guidance in ``_substitute.py``.  This avoids coupling to
``check_auth``'s internal anchors and composes cleanly with the
AUTH-01 substitution in ``auth.py``.
"""
import logging

_log = logging.getLogger("fox_overlay.webui_patches.auth_body_drain")

_SENTINEL = "_fox_patched_check_auth_body_drain"


def apply() -> None:
    from api import auth as _u

    if getattr(_u.check_auth, _SENTINEL, False):
        return

    _original = _u.check_auth

    def check_auth(handler, parsed):
        result = _original(handler, parsed)
        if not result:
            handler.close_connection = True
        return result

    for attr in dir(_original):
        if attr.startswith("_fox_patched"):
            setattr(check_auth, attr, getattr(_original, attr))
    setattr(check_auth, _SENTINEL, True)
    _u.check_auth = check_auth

    _log.info("[fox-overlay] patched api.auth.check_auth (body-drain wrapper)")
