"""Fox overlay entry-points for hermes-agent's plugin manager.

Both ``fox_overlay`` (this module's :func:`register`) and ``mem0_oss``
(`mem0_oss.register` via the manifest) are wired in ``packages/fox-overlay/
pyproject.toml`` under the ``[project.entry-points."hermes_agent.plugins"]``
group.

``register(ctx)`` is called once per process by hermes-agent's
``PluginManager.discover_and_load``. We apply our three agent-side
monkey-patches here so the patched behavior is in place before any
runtime code path touches the patched symbols.

mem0_oss has its own ``register`` (in mem0_oss/__init__.py) and is
discovered as a separate plugin — this module does not need to touch
it.

Phase 3 of the v0.6.0 upstream-separation migration (fox-in-the-box-ai/
fox-in-the-box#155).
"""
from .fox_overlay_plugin.monkey_patches import (
    auxiliary_client,
    cron_diagnostics,
    runtime_provider,
)


def register(ctx) -> None:
    """Entry point. ``ctx`` is a ``PluginContext`` from ``hermes_cli.plugins``.

    Idempotent: each ``apply()`` no-ops on its second call via per-target
    sentinel attribute.
    """
    runtime_provider.apply()
    auxiliary_client.apply()
    cron_diagnostics.apply()
