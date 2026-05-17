"""Fox overlay entry-point for hermes-agent's plugin manager.

``fox_overlay`` is wired in ``packages/fox-overlay/pyproject.toml`` under
the ``[project.entry-points."hermes_agent.plugins"]`` group.

``register(ctx)`` is called once per process by:

* hermes-agent's ``PluginManager.discover_and_load`` (only from ``hermes``
  CLI subcommands), AND
* the Fox bootstrap shim added to ``forks/hermes-agent/gateway/run.py`` for
  the gateway code path (upstream's gateway never calls PluginManager
  directly; the shim is a Phase-3 follow-on patch — see fork PR #2).

We apply the three agent-side monkey-patches here so the patched
behavior is in place before any runtime code path touches the patched
symbols.

Note on mem0_oss: the original Phase 3 plan relocated mem0_oss to this
overlay as a second entry-point plugin. During Phase 3b PR review,
Engineer discovered upstream's memory-provider discovery is a separate
system (``plugins/memory/__init__.py``) with its own ``FakePluginContext``
exposing ``register_memory_provider`` (which standard ``PluginContext``
lacks). The relocation was reverted (fork PR #3 + companion monorepo
changes); mem0_oss remains a bundled fork plugin until a dedicated
future phase properly relocates memory providers.

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
