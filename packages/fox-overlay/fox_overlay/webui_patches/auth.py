"""Fox webui patch: auth.py — X-Fox-Auth shared-secret gate (AUTH-01).

Substitutes ``check_auth`` in ``api/auth.py`` to add PATH 5: a valid
``X-Fox-Auth`` header grants access before the session-cookie check.
This is the management-plane auth path — Fleet's ``fox-control`` sends
this header on every request to a managed instance.

## How it works

One substitution inserts a block BEFORE ``cookie_val = parse_cookie(handler)``
(after public-path checks, before session-cookie checks). The block:

1. Reads ``FOX_PLANE_AUTH_SECRET`` from the environment (cached at
   patch time — the secret doesn't change at runtime).
2. If the env var is unset or empty, skips (standalone mode — no-op).
3. Reads ``X-Fox-Auth`` from the request headers.
4. Compares with ``hmac.compare_digest`` (constant-time).
5. Returns ``True`` on match → request is authorized.

Standalone instances (no ``FOX_PLANE_AUTH_SECRET``) are byte-identical
in behavior to vanilla Hermes — the injected block exits immediately.

## Contract references

* INSTANCE_CONTRACT.md §3.1 — X-Fox-Auth shared secret
* ENTERPRISE_ARCHITECTURE.md §5.3 — check_auth substitution mechanism
* DEMO_TIER.md — managed-mode auth model
"""
import inspect
import logging
import os

from ._helpers import substitute_function

_log = logging.getLogger("fox_overlay.webui_patches.auth")

_CHECK_AUTH_SENTINEL = "_fox_patched_check_auth"
_EXPECTED_CHECK_AUTH_SIG = "(handler, parsed) -> bool"


def _check_signature(callable_obj, expected: str, label: str) -> None:
    actual = str(inspect.signature(callable_obj))
    if actual != expected:
        raise AssertionError(
            "[fox-overlay] auth patch: %s signature drift.\n"
            "  expected: %s\n"
            "  actual:   %s\n"
            "Refresh both the expected signature and the substitution "
            "anchors in fox_overlay/webui_patches/auth.py." % (label, expected, actual)
        )


def apply() -> None:
    from api import auth as _u

    if getattr(_u.check_auth, _CHECK_AUTH_SENTINEL, False):
        return

    _check_signature(_u.check_auth, _EXPECTED_CHECK_AUTH_SIG, "check_auth")

    substitute_function(
        upstream_module=_u,
        function_name="check_auth",
        substitutions=[
            (
                "    # Check session cookie\n"
                "    cookie_val = parse_cookie(handler)\n",

                "    # PATH 5 (Fox managed mode): X-Fox-Auth shared secret.\n"
                "    # Fleet's fox-control sends this header on every request.\n"
                "    # Standalone (no FOX_PLANE_AUTH_SECRET) skips this block.\n"
                "    _fox_plane_secret = _fox_get_plane_secret()\n"
                "    if _fox_plane_secret:\n"
                "        _fox_auth_header = handler.headers.get('X-Fox-Auth', '')\n"
                "        if _fox_auth_header and _hmac_compare(_fox_auth_header, _fox_plane_secret):\n"
                "            return True\n"
                "    # Check session cookie\n"
                "    cookie_val = parse_cookie(handler)\n",
            ),
        ],
        sentinel=_CHECK_AUTH_SENTINEL,
        extra_globals={
            "_fox_get_plane_secret": _fox_get_plane_secret,
            "_hmac_compare": _hmac_compare,
        },
    )


def _fox_get_plane_secret() -> str:
    return os.environ.get("FOX_PLANE_AUTH_SECRET", "")


def _hmac_compare(a: str, b: str) -> bool:
    import hmac
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))
