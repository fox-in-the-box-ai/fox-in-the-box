"""Fox webui patch: config.py — settings defaults + cache invalidation + save-gate validation.

Re-applies the Fox edits to ``api/config.py`` reverted to upstream
merge-base in fork PR fox-in-the-box-ai/hermes-webui#NN (Phase 6
fork-side, parent #189). Closes monorepo issue #190.

## Fox edits restored

### Module-scope additions (direct dict/set mutation, no substitution)

* ``_SETTINGS_DEFAULTS`` gains 9 Fox keys:
  ``local_fallback_enabled``, ``hostname_prompted``,
  ``tailscale_login_server``, ``tailscale_advertise_routes``,
  ``tailscale_advertise_tags``, ``tailscale_accept_routes``,
  ``tailscale_accept_dns``, ``tailscale_exit_node``,
  ``ollama_custom_url``.
* ``_SETTINGS_BOOL_KEYS`` gains 4 Fox keys (the bool ones above).

These are persistent settings the Phase 5 webui modules (ollama,
tailscale, local_fallback, hostname) read at module-load. **Issue #190
flagged this PR as "MERGE FIRST"** — without these keys present,
Phase 5 modules would read missing settings and silently default to
None / KeyError on first run.

### Function patches

* ``get_config()`` — add mtime-based cache invalidation so config
  changes from out-of-process writers (gateway, supervisor) reach
  the webui without restart.
* ``reload_config()`` — also evict the in-memory ``_available_models_cache``
  (#138 chat-model-picker stale-after-Ollama-switch fix).
* ``save_settings()`` — three additions:
  - Validate Tailscale power-user fields at the save gate
  - Validate Ollama custom URL + normalize + remember the change
  - Replace native ``bool(v)`` coercion with string-aware coercion
    (``bool("false") == True`` was silently flipping flags)
  - Invalidate Ollama probe cache after URL change

## Self-checks

* ``inspect.signature`` self-check on all 3 functions
* Anchor self-check via ``substitute_function`` (each anchor MUST
  appear exactly once)
* Idempotent via per-patch sentinels + a module-attribute flag for the
  dict/set additions
"""
import inspect
import logging

from ._helpers import substitute_function

_log = logging.getLogger("fox_overlay.webui_patches.config")

_GET_CONFIG_SENTINEL = "_fox_patched_get_config"
_RELOAD_CONFIG_SENTINEL = "_fox_patched_reload_config"
_SAVE_SETTINGS_SENTINEL = "_fox_patched_save_settings"
_MODULE_DEFAULTS_FLAG = "_fox_settings_defaults_applied"

_EXPECTED_GET_CONFIG_SIG = "() -> dict"
_EXPECTED_RELOAD_CONFIG_SIG = "() -> None"
_EXPECTED_SAVE_SETTINGS_SIG = "(settings: dict) -> dict"

_FOX_DEFAULTS = {
    # Local AI fallback (#9). Toggling ON triggers a one-time GGUF
    # download (~2.5 GB) and starts a supervisord-managed llama-server.
    "local_fallback_enabled": False,
    # Tracks whether the post-wizard hostname prompt (#68) has been
    # shown. Once true, the prompt never re-fires.
    "hostname_prompted": False,
    # Power-user Tailscale flags (#96 phase 2). _build_up_argv() already
    # accepts these; persisting them here lets the UI pre-populate on
    # revisit. accept_dns defaults TRUE (Tailscale itself defaults true
    # and most users want MagicDNS).
    "tailscale_login_server": "",
    "tailscale_advertise_routes": "",
    "tailscale_advertise_tags": "",
    "tailscale_accept_routes": False,
    "tailscale_accept_dns": True,
    "tailscale_exit_node": "",
    # Custom Ollama base URL (#109). Empty = auto-detect.
    "ollama_custom_url": "",
}
_FOX_BOOL_KEYS = {
    "local_fallback_enabled",
    "hostname_prompted",
    "tailscale_accept_routes",
    "tailscale_accept_dns",
}


def _check_signature(callable_obj, expected: str, label: str) -> None:
    actual = str(inspect.signature(callable_obj))
    if actual != expected:
        raise AssertionError(
            "[fox-overlay] config patch: %s signature drift.\n"
            "  expected: %s\n"
            "  actual:   %s\n"
            "Refresh both the expected signature and the substitution "
            "anchors in fox_overlay/webui_patches/config.py." % (label, expected, actual)
        )


def apply() -> None:
    from api import config as _u

    # Apply-level idempotency: bail if get_config already patched.
    if getattr(_u.get_config, _GET_CONFIG_SENTINEL, False):
        return

    # ── Signature self-checks ───────────────────────────────────────────
    _check_signature(_u.get_config, _EXPECTED_GET_CONFIG_SIG, "get_config")
    _check_signature(_u.reload_config, _EXPECTED_RELOAD_CONFIG_SIG, "reload_config")
    _check_signature(_u.save_settings, _EXPECTED_SAVE_SETTINGS_SIG, "save_settings")

    # ── Module-scope additions: defaults dict + bool key set ────────────
    # Done BEFORE function patches so save_settings (which reads
    # _SETTINGS_BOOL_KEYS) sees the new keys.
    if not getattr(_u, _MODULE_DEFAULTS_FLAG, False):
        for key, value in _FOX_DEFAULTS.items():
            _u._SETTINGS_DEFAULTS.setdefault(key, value)
        _u._SETTINGS_BOOL_KEYS.update(_FOX_BOOL_KEYS)
        setattr(_u, _MODULE_DEFAULTS_FLAG, True)
        _log.info(
            "[fox-overlay] api.config _SETTINGS_DEFAULTS gained %d keys; "
            "_SETTINGS_BOOL_KEYS gained %d keys",
            len(_FOX_DEFAULTS), len(_FOX_BOOL_KEYS),
        )

    # ── Patch get_config: add mtime-based cache invalidation ────────────
    substitute_function(
        upstream_module=_u,
        function_name="get_config",
        substitutions=[
            (
                "    if not _cfg_cache:\n"
                "        reload_config()\n"
                "    return _cfg_cache\n",
                "    if not _cfg_cache:\n"
                "        reload_config()\n"
                "        return _cfg_cache\n"
                "\n"
                "    # Fox: file-mtime check — pick up out-of-process config writes\n"
                "    # (e.g. supervisorctl-managed gateway) without a webui restart.\n"
                "    try:\n"
                "        if _get_config_path().stat().st_mtime != _cfg_mtime:\n"
                "            with _cfg_lock:\n"
                "                if _get_config_path().stat().st_mtime != _cfg_mtime:\n"
                "                    reload_config()\n"
                "    except OSError:\n"
                "        pass\n"
                "\n"
                "    return _cfg_cache\n",
            ),
        ],
        sentinel=_GET_CONFIG_SENTINEL,
    )

    # ── Patch reload_config: add in-memory models-cache eviction ────────
    substitute_function(
        upstream_module=_u,
        function_name="reload_config",
        substitutions=[
            (
                # Expand global declaration to include the models-cache vars.
                "    global _cfg_mtime\n"
                "    with _cfg_lock:\n",
                "    global _cfg_mtime, _available_models_cache, _available_models_cache_ts\n"
                "    with _cfg_lock:\n",
            ),
            (
                # Add cache eviction after on-disk cache delete (#138).
                "        if _old_cfg_mtime != 0.0:\n"
                "            _delete_models_cache_on_disk()\n",
                "        if _old_cfg_mtime != 0.0:\n"
                "            _delete_models_cache_on_disk()\n"
                "            # Fox #138: evict in-memory cache too — same gating as\n"
                "            # on-disk delete (only on actual changes, not first load).\n"
                "            _available_models_cache = None\n"
                "            _available_models_cache_ts = 0.0\n",
            ),
        ],
        sentinel=_RELOAD_CONFIG_SENTINEL,
    )

    # ── Patch save_settings: three additions ────────────────────────────
    substitute_function(
        upstream_module=_u,
        function_name="save_settings",
        substitutions=[
            (
                # Top-of-function: Tailscale + Ollama URL validation gates.
                'def save_settings(settings: dict) -> dict:\n'
                '    """Save settings to disk. Returns the merged settings. Ignores unknown keys."""\n'
                '    current = load_settings()\n',
                'def save_settings(settings: dict) -> dict:\n'
                '    """Save settings to disk. Returns the merged settings. Ignores unknown keys.\n'
                '\n'
                '    Fox: validate Tailscale + Ollama URL fields BEFORE persisting.\n'
                '    See fox_overlay.webui_patches.config for rationale.\n'
                '    """\n'
                '    try:\n'
                '        from api.tailscale import validate_settings_dict as _ts_validate\n'
                '        ts_err = _ts_validate(settings)\n'
                '        if ts_err:\n'
                '            raise ValueError(f"Tailscale setting rejected: {ts_err}")\n'
                '    except ImportError:\n'
                '        pass\n'
                '    _ollama_url_changed = False\n'
                '    if "ollama_custom_url" in settings:\n'
                '        try:\n'
                '            from api.ollama import validate_custom_ollama_url\n'
                '            ok, normalized_or_err = validate_custom_ollama_url(settings["ollama_custom_url"])\n'
                '            if not ok:\n'
                '                raise ValueError(f"Ollama setting rejected: {normalized_or_err}")\n'
                '            settings["ollama_custom_url"] = normalized_or_err\n'
                '            _ollama_url_changed = True\n'
                '        except ImportError:\n'
                '            pass\n'
                '    current = load_settings()\n',
            ),
            (
                # Replace native bool coercion with string-aware coercion.
                "            # Coerce bool keys\n"
                "            if k in _SETTINGS_BOOL_KEYS:\n"
                "                v = bool(v)\n",
                "            # Fox: bool('false') is True in Python — a curl POST with\n"
                "            # {'hostname_prompted':'false'} would silently flip the flag\n"
                "            # to True. Accept native booleans, JSON-stringified booleans,\n"
                "            # and obvious truthy/falsy strings; reject other types by\n"
                "            # leaving the prior value intact.\n"
                "            if k in _SETTINGS_BOOL_KEYS:\n"
                "                if isinstance(v, bool):\n"
                "                    pass\n"
                "                elif isinstance(v, str):\n"
                "                    s = v.strip().lower()\n"
                "                    if s in ('true', '1', 'yes', 'on'):\n"
                "                        v = True\n"
                "                    elif s in ('false', '0', 'no', 'off', ''):\n"
                "                        v = False\n"
                "                    else:\n"
                "                        continue\n"
                "                elif isinstance(v, (int, float)):\n"
                "                    v = bool(v)\n"
                "                else:\n"
                "                    continue\n",
            ),
            (
                # Add Ollama cache invalidation after default_workspace resolve.
                "    global DEFAULT_WORKSPACE\n"
                '    if "default_workspace" in current:\n'
                '        DEFAULT_WORKSPACE = resolve_default_workspace(current["default_workspace"])\n'
                '    current["default_model"] = get_effective_default_model()\n',
                "    global DEFAULT_WORKSPACE\n"
                '    if "default_workspace" in current:\n'
                '        DEFAULT_WORKSPACE = resolve_default_workspace(current["default_workspace"])\n'
                '    # Fox #109: invalidate Ollama probe cache on URL change so the\n'
                '    # next /api/ollama/status reflects the new URL immediately.\n'
                '    if _ollama_url_changed:\n'
                '        try:\n'
                '            from api.ollama import clear_cache as _clear_ollama_cache\n'
                '            _clear_ollama_cache()\n'
                '        except Exception:\n'
                '            pass\n'
                '    current["default_model"] = get_effective_default_model()\n',
            ),
        ],
        sentinel=_SAVE_SETTINGS_SENTINEL,
    )
