"""Fox patches in ``agent.auxiliary_client``.

Two patches restoring Fox edits from hermes-agent fork commits
5e0d847cb and 026a12487:

1. ``_resolve_task_provider_model``: when the auxiliary config provider
   is ``"auto"`` (or unset) but an explicit model is specified, resolve
   the provider explicitly via ``_read_main_provider()`` so the model
   hint actually wins. Without this, ``_resolve_auto`` ignores the
   model hint and always uses the main model.

2. ``_get_auxiliary_task_config``: fall back to ``auxiliary.default``
   when no task-specific config exists. Task-specific keys win over
   default keys (``{**default_config, **task_config}``).

Phase 0 PR campaign candidates; if upstream accepts, retire in Phase 10.
"""
from agent import auxiliary_client as _u

from ._helpers import substitute_function


def apply() -> None:
    # 1) _resolve_task_provider_model: insert explicit-provider branch
    substitute_function(
        upstream_module=_u,
        function_name="_resolve_task_provider_model",
        substitutions=[
            (
                '        if cfg_provider and cfg_provider != "auto":\n'
                '            return cfg_provider, resolved_model, None, None, resolved_api_mode\n'
                '\n'
                '        return "auto", resolved_model, None, None, resolved_api_mode\n',
                '        if cfg_provider and cfg_provider != "auto":\n'
                '            return cfg_provider, resolved_model, None, None, resolved_api_mode\n'
                '\n'
                '        # provider is "auto" (or unset) but config specified an explicit model\n'
                '        # (e.g. auxiliary.default.model = us.anthropic.claude-haiku-...).\n'
                '        # _resolve_auto ignores the model hint and always uses the main model,\n'
                '        # so we must resolve the provider explicitly here to honour cfg_model.\n'
                '        if resolved_model:\n'
                '            explicit_provider = _read_main_provider() or "auto"\n'
                '            if explicit_provider and explicit_provider != "auto":\n'
                '                return explicit_provider, resolved_model, None, None, resolved_api_mode\n'
                '\n'
                '        return "auto", resolved_model, None, None, resolved_api_mode\n',
            ),
        ],
        sentinel="_fox_patched_provider_auto_fallback",
    )

    # 2) _get_auxiliary_task_config: docstring + trailing logic
    substitute_function(
        upstream_module=_u,
        function_name="_get_auxiliary_task_config",
        substitutions=[
            (
                '    """Return the config dict for auxiliary.<task>, or {} when unavailable."""\n',
                '    """Return the config dict for auxiliary.<task>, or {} when unavailable.\n'
                '\n'
                '    Falls back to auxiliary.default when no task-specific config exists.\n'
                '    Task-specific keys win over default keys ({**default_config, **task_config}).\n'
                '    """\n',
            ),
            (
                '    aux = config.get("auxiliary", {}) if isinstance(config, dict) else {}\n'
                '    task_config = aux.get(task, {}) if isinstance(aux, dict) else {}\n'
                '    return task_config if isinstance(task_config, dict) else {}\n',
                '    aux = config.get("auxiliary", {}) if isinstance(config, dict) else {}\n'
                '    if not isinstance(aux, dict):\n'
                '        return {}\n'
                '    default_config = aux.get("default", {})\n'
                '    default_config = default_config if isinstance(default_config, dict) else {}\n'
                '    task_config = aux.get(task, {}) if isinstance(aux, dict) else {}\n'
                '    task_config = task_config if isinstance(task_config, dict) else {}\n'
                '    return {**default_config, **task_config}\n',
            ),
        ],
        sentinel="_fox_patched_auxiliary_default_fallback",
    )
