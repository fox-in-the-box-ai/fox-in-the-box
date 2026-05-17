"""Fox webui monkey-patches — Phase 6 of v0.6.0 upstream-separation.

Each module here patches mid-file Fox edits into upstream hermes-webui
files (api/streaming.py, api/models.py, api/config.py, api/providers.py,
api/updates.py). Fork-side, those files are restored to virgin upstream
content (Phase 6 per-module fork PRs); the Fox behavior is reinstated
at runtime via these patches.

Each patch module exports an ``apply()`` function that is idempotent —
re-running it is a no-op once the per-target sentinel is set. The
``apply_all()`` function below invokes each module's ``apply()`` in
order; ``fox_overlay.bootstrap.install()`` calls ``apply_all()`` after
``webui_modules`` are imported (so dispatcher entries register first).

Substitution mechanics live in ``_helpers.substitute_function`` —
``inspect.getsource`` + textual anchor substitution. Anchors MUST be
unique within the target function; mismatched anchors fail at boot
with a precise diagnostic so Phase 9 nightly upstream-watch CI catches
upstream drift.
"""
import logging

_log = logging.getLogger("fox_overlay.webui_patches")


def apply_all() -> None:
    """Apply every Fox webui monkey-patch. Called once from bootstrap.install()."""
    from . import providers
    providers.apply()
    # Phase 6 adds more modules here:
    # from . import streaming; streaming.apply()
    # from . import models; models.apply()
    # from . import config; config.apply()
    # from . import updates; updates.apply()
    _log.warning(
        "[fox-overlay] webui_patches.apply_all() complete (%d patch modules)",
        1,  # update as modules are added
    )
