"""Fox patch: use ``target_model`` for Bedrock api_mode routing.

Restores the Fox edit from hermes-agent fork commit f24911136 that
relocated to this overlay during the v0.6.0 upstream-separation
migration (Phase 3). Phase 0 PR campaign candidate; if upstream accepts
the PR, this monkey-patch becomes dead code and is removed in Phase 10.

Single-line substitution inside ``hermes_cli.runtime_provider.resolve_runtime_provider``
so the Bedrock dual-path routing honours the explicit ``target_model``
argument instead of always falling back to the auxiliary config's
default.
"""
from hermes_cli import runtime_provider as _u

from ._helpers import substitute_function


def apply() -> None:
    substitute_function(
        upstream_module=_u,
        function_name="resolve_runtime_provider",
        substitutions=[
            (
                '_current_model = str(model_cfg.get("default") or "").strip()',
                '_current_model = target_model or str(model_cfg.get("default") or "").strip()',
            ),
        ],
        sentinel="_fox_patched_target_model",
    )
