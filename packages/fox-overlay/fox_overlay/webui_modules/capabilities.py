"""GET /capabilities — feature manifest (INSTANCE_CONTRACT §4.4).

Returns the contract version and a flat dict of capabilities that this
instance *supports* (not what the plane has enabled/disabled — that's
the plane's injected CapabilityFlags).

Auth position (§4.5): behind the upstream auth gate in managed mode,
open in standalone.  Registers through normal dispatch — no
PUBLIC_PATHS expansion.
"""
from __future__ import annotations

import logging
import os
import shutil

logger = logging.getLogger(__name__)

CONTRACT_VERSION = "2.0.0"


def _has_module(name: str) -> bool:
    try:
        import importlib
        importlib.import_module(name)
        return True
    except ImportError:
        return False


def _check_data_plane_access() -> bool:
    return bool(
        os.environ.get("FOX_PLANE_AUTH_SECRET")
        and os.environ.get("FOX_DATA_PLANE_URL")
    )


def get_capabilities() -> dict:
    return {
        "contract_version": CONTRACT_VERSION,
        "capabilities": {
            "local_fallback": _has_module("fox_overlay.webui_modules.local_fallback"),
            "tailscale": shutil.which("tailscale") is not None,
            "ollama": _has_module("fox_overlay.webui_modules.ollama"),
            "web_search": True,
            "file_upload": True,
            "cron_jobs": True,
            "model_download": _has_module("fox_overlay.webui_modules.models_download"),
            "data_plane_access": _check_data_plane_access(),
        },
    }


# ── Dispatcher integration ─────────────────────────────────────────────
from fox_overlay import dispatch  # noqa: E402


def _handle_get(handler, parsed) -> bool:
    if parsed.path != "/capabilities":
        return False
    from api.helpers import j
    j(handler, get_capabilities())
    return True


dispatch.register_get("/capabilities", _handle_get, allow_bare=True)
