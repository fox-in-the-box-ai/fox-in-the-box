"""Fox overlay bootstrap.

Imported by hermes-webui's server.py before any api.* imports, starting
in Phase 4. Until then this module is loadable but unreferenced.

Phase 1: install() is a no-op log line. Phases 4-6 grow it with real
monkey-patch invocations + dispatcher wiring.

**Auto-install warning.** This module calls install() at import time so
the patches Phases 4-6 will register apply automatically when server.py
imports the bootstrap. Any other import path (pytest collection, REPL
inspection, IDE indexer, `python -c`, hot-reloader) ALSO triggers the
install — which becomes load-bearing once Phases 4-6 add real patches.

Set FOX_OVERLAY_AUTOINSTALL=0 to disable auto-install and require an
explicit `install()` call from server.py only. Use this in test
environments and any context where unintended patching would corrupt
state isolation.
"""
import logging
import os

_log = logging.getLogger("fox_overlay.bootstrap")
_INSTALLED = False


def install() -> None:
    """Apply Fox overlay to a running hermes-webui process. Idempotent."""
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True
    # Phase 5+ will import webui_modules here (e.g.
    # `from fox_overlay import webui_modules`) so they can call
    # register_get/post() at module-load time before freeze().
    from fox_overlay import dispatch
    dispatch.freeze()
    _log.info("[fox-overlay] bootstrap installed (dispatcher frozen, table empty in Phase 4)")


if os.environ.get("FOX_OVERLAY_AUTOINSTALL", "1") != "0":
    install()
