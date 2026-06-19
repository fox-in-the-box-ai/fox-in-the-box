"""Fox webui patch: csrf.py — CSRF token bypass for X-Fox-Auth (CSRF-01).

Substitutes ``_check_csrf`` in ``api/routes.py`` to skip CSRF token
verification when the request carries a valid ``X-Fox-Auth`` header.

## Why this is needed

When Fleet proxies browser requests to a managed Fox instance, it
injects ``X-Fox-Auth`` for authentication (the auth.py patch already
handles this in ``check_auth``). However, the browser has no Fox
``hermes_session`` cookie — it only has Fleet's ``fox_cloud_session``.
The CSRF token check in ``_check_csrf`` requires a valid session cookie
to derive and verify the CSRF token, so ALL browser POST requests
through Fleet fail with 403 "Session expired".

## Why this is safe

X-Fox-Auth is a custom HTTP header. CORS preflight blocks cross-origin
requests from setting custom headers unless the server's
``Access-Control-Allow-Headers`` explicitly permits it — Fox does not.
Additionally, Fleet's session cookie uses ``SameSite=Lax``, preventing
cross-origin POST requests from carrying the cookie. Therefore,
X-Fox-Auth-authenticated requests are inherently immune to CSRF attacks:
the attack vector (forged cross-origin POST with credentials) cannot
inject a custom header.

## Contract references

* INSTANCE_CONTRACT.md §3.1 — X-Fox-Auth shared secret
"""
import inspect
import os

from ._helpers import substitute_function

_CHECK_CSRF_SENTINEL = "_fox_patched_check_csrf"
_EXPECTED_CHECK_CSRF_SIG = "(handler) -> bool"


def _check_signature(callable_obj, expected: str, label: str) -> None:
    actual = str(inspect.signature(callable_obj))
    if actual != expected:
        raise AssertionError(
            "[fox-overlay] csrf patch: %s signature drift.\n"
            "  expected: %s\n"
            "  actual:   %s\n"
            "Refresh both the expected signature and the substitution "
            "anchors in fox_overlay/webui_patches/csrf.py." % (label, expected, actual)
        )


def apply() -> None:
    from api import routes as _r

    if getattr(_r._check_csrf, _CHECK_CSRF_SENTINEL, False):
        return

    _check_signature(_r._check_csrf, _EXPECTED_CHECK_CSRF_SIG, "_check_csrf")

    substitute_function(
        upstream_module=_r,
        function_name="_check_csrf",
        substitutions=[
            (
                "    from api.auth import CSRF_HEADER_NAME, is_auth_enabled, parse_cookie, verify_csrf_token\n",

                "    if _fox_csrf_plane_bypass(handler):\n"
                "        return True\n"
                "    from api.auth import CSRF_HEADER_NAME, is_auth_enabled, parse_cookie, verify_csrf_token\n",
            ),
        ],
        sentinel=_CHECK_CSRF_SENTINEL,
        extra_globals={
            "_fox_csrf_plane_bypass": _fox_csrf_plane_bypass,
        },
    )


def _fox_csrf_plane_bypass(handler) -> bool:
    import hmac
    secret = os.environ.get("FOX_PLANE_AUTH_SECRET", "")
    if not secret:
        return False
    auth_header = handler.headers.get("X-Fox-Auth", "")
    if not auth_header:
        return False
    return hmac.compare_digest(auth_header.encode("utf-8"), secret.encode("utf-8"))
