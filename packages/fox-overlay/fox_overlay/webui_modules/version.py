"""GET /version — contract version and image identity (INSTANCE_CONTRACT §4.3).

Returns contract version, image digest, runtime name/version, and
overlay version.

Auth position (§4.5): behind the upstream auth gate in managed mode,
open in standalone.  This handler registers through normal dispatch —
no PUBLIC_PATHS expansion — so check_auth runs first.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

CONTRACT_VERSION = "2.0.0"
_VERSION_FILE = "/app/version.txt"


def _get_runtime_version() -> str:
    try:
        import sys
        mod = sys.modules.get("api.updates")
        if mod is not None:
            v = getattr(mod, "WEBUI_VERSION", None)
            if v:
                return str(v)
    except Exception:
        pass
    return "unknown"


def _get_overlay_version() -> str:
    try:
        from importlib.metadata import version as pkg_version
        return pkg_version("fox-overlay")
    except Exception:
        pass
    try:
        with open(_VERSION_FILE) as f:
            return f.read().strip()
    except Exception:
        return "unknown"


def get_version() -> dict:
    return {
        "contract_version": CONTRACT_VERSION,
        "image_digest": os.environ.get("FITB_IMAGE_DIGEST", ""),
        "runtime": "hermes",
        "runtime_version": _get_runtime_version(),
        "overlay_version": _get_overlay_version(),
    }


# ── Dispatcher integration ─────────────────────────────────────────────
from fox_overlay import dispatch  # noqa: E402


def _handle_get(handler, parsed) -> bool:
    if parsed.path != "/version":
        return False
    from api.helpers import j
    j(handler, get_version())
    return True


dispatch.register_get("/version", _handle_get, allow_bare=True)
