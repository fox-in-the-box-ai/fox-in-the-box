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
import threading

_log = logging.getLogger("fox_overlay.bootstrap")
_INSTALLED = False
_INSTALL_LOCK = threading.Lock()


def install() -> None:
    """Apply Fox overlay to a running hermes-webui process. Idempotent + thread-safe."""
    global _INSTALLED
    with _INSTALL_LOCK:
        if _INSTALLED:
            return
        # Phase 5: import webui_modules — each sub-module calls
        # dispatch.register_get/register_post() at module-load time. Wrap
        # in ImportError so a missing sub-module surfaces as a warning but
        # doesn't kill webui boot.
        try:
            from fox_overlay import webui_modules  # noqa: F401
        except ImportError as e:
            _log.warning("[fox-overlay] webui_modules import failed (%s); Fox routes degraded", e)

        # Phase 6: apply monkey-patches to upstream mid-file edits.
        # Each patch is idempotent (sentinel attribute guard inside
        # substitute_function). Distinguish two failure modes:
        #
        # - ImportError → the patches submodule itself didn't load
        #   (deployment problem, not Fox-code problem). Degrade with a
        #   warning so webui still boots with whatever modules did load.
        # - AssertionError → an anchor or signature self-check failed,
        #   meaning upstream drifted under us. This is the entire reason
        #   _helpers.substitute_function raises loudly; swallowing it
        #   here would ship silently-broken Fox behavior (bug v0.7.5
        #   audit caught: pre-v0.7.5, anchor drift logged WARNING and
        #   the user got a quietly-degraded app). Re-raise to abort boot
        #   so CI / smoke / users see the failure.
        # - Anything else → log full traceback (not just `e`) and degrade
        #   the affected patch; webui core is upstream so it survives.
        try:
            from fox_overlay import webui_patches
            webui_patches.apply_all()
        except ImportError as e:
            _log.warning("[fox-overlay] webui_patches import failed (%s); Fox mid-file edits degraded", e)
        except AssertionError:
            _log.exception(
                "[fox-overlay] webui_patches.apply_all() ABORTED — anchor/signature drift "
                "detected, refusing to boot with silently-broken Fox patches"
            )
            raise
        except Exception:
            _log.exception("[fox-overlay] webui_patches.apply_all() failed; Fox mid-file edits degraded")

        from fox_overlay import dispatch
        dispatch.freeze()
        # WARNING level so the line surfaces in webui's default logging
        # config — INFO is filtered by the stdlib default (WARNING) and
        # hermes-webui doesn't call basicConfig. This line is the "did
        # Fox load?" signal for ops smoke checks.
        _log.warning(
            "[fox-overlay] bootstrap installed: dispatcher frozen, "
            "%d GET + %d POST handlers registered",
            len(dispatch.GET_TABLE), len(dispatch.POST_TABLE),
        )
        _INSTALLED = True


if os.environ.get("FOX_OVERLAY_AUTOINSTALL", "1") != "0":
    install()
