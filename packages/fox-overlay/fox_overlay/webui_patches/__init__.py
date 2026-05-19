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
    """Apply every Fox webui monkey-patch. Called once from bootstrap.install().

    Ordering: config FIRST per issue #190 — Phase 5 webui modules read
    settings whose defaults config.py provides. (For Phase 6 internal
    ordering only — historical providers/models PRs already shipped and
    don't read config keys.)
    """
    from . import config
    config.apply()
    # providers.py patch retired in v0.6.2 (#269) — the Fox supervisor-
    # restart hook on set_provider_key was dead code. Upstream already
    # reloads ~/.hermes/.env per-turn via
    # _reload_runtime_env_preserving_config_authority() at
    # gateway/run.py:15103, which picks up rotated keys without any
    # gateway restart. Repro at fox-in-the-box-ai/fox-in-the-box#163.
    # The overlay was actively worse than upstream — it disrupted
    # in-flight SSE streams that upstream deliberately preserves by
    # using invalidate_models_cache() instead of reload_config()
    # (see upstream api/providers.py:2039-2041).
    #
    # models.py patch removed in Phase 8 follow-up #239 — upstream
    # v0.51.84 now provides Fox's #1558 P0 guard NATIVELY.
    from . import streaming
    streaming.apply()
    _log.warning(
        "[fox-overlay] webui_patches.apply_all() complete (%d patch modules)",
        2,  # config + streaming (providers retired v0.6.2 #269; models removed Phase 8 #239; updates DELETE PATH Phase 6)
    )
