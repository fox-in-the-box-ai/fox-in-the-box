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


def _check_managed_mode_invariant() -> None:
    """Refuse to boot if FOX_PLANE_AUTH_SECRET is set but upstream auth is disabled.

    ENTERPRISE_ARCHITECTURE.md §5.4: managed-mode requires upstream auth
    (password or passkeys) so that check_auth's PATH 4 rejects sessionless,
    secretless callers. Without upstream auth, is_auth_enabled() returns
    False and check_auth's PATH 1 bypasses ALL auth — making
    FOX_PLANE_AUTH_SECRET meaningless and the instance wide-open.

    Standalone mode (no FOX_PLANE_AUTH_SECRET) skips this check entirely.
    """
    secret = os.environ.get("FOX_PLANE_AUTH_SECRET", "")
    if not secret:
        return

    try:
        from api.auth import is_auth_enabled
    except ImportError:
        _log.warning(
            "[fox-overlay] cannot import api.auth to check managed-mode invariant; "
            "skipping (non-webui context)"
        )
        return

    if not is_auth_enabled():
        _msg = (
            "[fox-overlay] FATAL: FOX_PLANE_AUTH_SECRET is set but upstream auth "
            "is disabled (no password, no passkeys). Managed mode requires upstream "
            "auth — without it, check_auth bypasses ALL authentication. Either set "
            "HERMES_WEBUI_PASSWORD / configure passkeys, or remove "
            "FOX_PLANE_AUTH_SECRET to run in standalone mode."
        )
        _log.critical(_msg)
        try:
            import sys
            print(_msg, file=sys.stderr)
        except Exception:
            pass
        raise SystemExit(1)


def install() -> None:
    """Apply Fox overlay to a running hermes-webui process. Idempotent + thread-safe."""
    global _INSTALLED
    with _INSTALL_LOCK:
        if _INSTALLED:
            return

        _check_managed_mode_invariant()

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
        # The "did Fox load?" signal for ops smoke checks. Goes to two
        # destinations:
        #
        # 1. Python's logging at WARNING — lands in /data/logs/hermes-webui.err
        #    via supervisord's capture (or wherever webui's logging config
        #    routes WARNING). Filterable, structured, persisted across
        #    rotation.
        #
        # 2. Direct write to PID 1's stdout — lands in `docker logs`.
        #    v0.7.9 #302 fix: pre-v0.7.9 only (1) happened, and supervisord
        #    captures program output to files, not container stdout. Ops
        #    running `docker logs` would never see the bootstrap signature.
        #    Writing to /proc/1/fd/1 directly bypasses Python's logging
        #    config and supervisord's per-program capture entirely.
        #    Best-effort: silently no-op if /proc isn't writable (non-Linux
        #    container, restricted namespace).
        _msg = (
            "[fox-overlay] bootstrap installed: dispatcher frozen, "
            "%d GET + %d POST handlers registered"
            % (len(dispatch.GET_TABLE), len(dispatch.POST_TABLE))
        )
        _log.warning(_msg)
        try:
            with open("/proc/1/fd/1", "w") as _stdout:
                _stdout.write(_msg + "\n")
        except Exception:
            pass

        _INSTALLED = True


if os.environ.get("FOX_OVERLAY_AUTOINSTALL", "1") != "0":
    install()
