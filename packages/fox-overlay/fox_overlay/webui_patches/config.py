"""Fox webui patch: config.py — settings defaults + cache invalidation + save-gate validation.

Re-applies the Fox edits to ``api/config.py``. Originally targeted Fox
merge-base 9e31a2a; refreshed for v0.51.84 in Phase 8 follow-up #238.

## Phase 8 refresh notes

v0.51.84's upstream changes:

1. **``get_config()``** — upstream NOW implements mtime-based cache
   invalidation NATIVELY (with a more sophisticated ``_cfg_fingerprint``
   mechanism). Fox's patch is REDUNDANT. The get_config substitution
   is dropped from this version.
2. **``reload_config()``** — upstream expanded the ``global`` declaration
   from ``_cfg_mtime`` only to ``_cfg_mtime, _cfg_path, _cfg_fingerprint``.
   Fox's anchor updated accordingly.
3. **``save_settings()``** — unchanged in v0.51.84; all 3 substitutions
   apply with their original anchors.
4. **``_SETTINGS_DEFAULTS`` + ``_SETTINGS_BOOL_KEYS``** — still
   module-scope; dict/set additions still work.

## v0.7.4 addition (#303)

5. **``get_available_models()``** — wrap-and-splice (NOT
   ``substitute_function``). Local Ollama models pulled via
   Settings → Local Ollama don't appear in the chat picker because
   upstream's ``_build_available_models_uncached()`` has no
   ``elif pid == "ollama"`` branch alongside its ``ollama-cloud``
   one. Fox already has the daemon detection + installed-models
   listing via ``fox_overlay.webui_modules.ollama.get_models()``;
   this wrap splices that data into the picker output as an OLLAMA
   group. Wrap (vs ``substitute_function``) chosen because the change
   is post-call mutation of the return value, and the upstream
   function is ~1200 lines — textual anchors deep inside it would be
   fragile vs upstream refactors. Wrap-and-splice is invariant to
   internals as long as the function signature + return-shape hold.

## Fox edits restored

### Module-scope additions (direct dict/set mutation)

* ``_SETTINGS_DEFAULTS`` gains 9 Fox keys (local_fallback_enabled,
  hostname_prompted, 6 Tailscale flags, ollama_custom_url).
* ``_SETTINGS_BOOL_KEYS`` gains 4 Fox keys (the bool ones above).

### Function patches

* ``reload_config()`` — evict the in-memory ``_available_models_cache``
  after on-disk cache delete (#138 chat-model-picker stale-after-
  Ollama-switch fix).
* ``save_settings()`` — three additions:
  - Validate Tailscale power-user fields at the save gate
  - Validate Ollama custom URL + normalize + remember the change
  - Replace native ``bool(v)`` coercion with string-aware coercion
    (``bool("false") == True`` was silently flipping flags)
  - Invalidate Ollama probe cache after URL change

## Self-checks

* ``inspect.signature`` self-check on patched functions
* Anchor self-check via ``substitute_function``
* Per-patch sentinels + module-attribute flag for dict/set additions
"""
import inspect
import logging

from ._helpers import substitute_function

_log = logging.getLogger("fox_overlay.webui_patches.config")

_RELOAD_CONFIG_SENTINEL = "_fox_patched_reload_config"
_SAVE_SETTINGS_SENTINEL = "_fox_patched_save_settings"
_GET_AVAILABLE_MODELS_SENTINEL = "_fox_patched_get_available_models"
_MODULE_DEFAULTS_FLAG = "_fox_settings_defaults_applied"

_EXPECTED_RELOAD_CONFIG_SIG = "() -> None"
_EXPECTED_SAVE_SETTINGS_SIG = "(settings: dict) -> dict"
_EXPECTED_GET_AVAILABLE_MODELS_SIG = "() -> dict"

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


def _splice_ollama_group(result: dict) -> None:
    """Append a local-Ollama group to ``result['groups']``.

    v0.7.18 #337: ALWAYS adds the group, with state-aware content. Previously
    no-op'd when the daemon wasn't reachable or had no models, leaving users
    who hadn't installed Ollama with no way to discover Fox supports it.
    Now:
      * daemon reachable + models present → standard model list (pre-v0.7.18 behavior)
      * daemon reachable, no models      → synthetic placeholder entry with `pull` hint
      * daemon not reachable             → synthetic placeholder entry with `install` hint

    Synthetic entries use `id` prefix ``__ollama_hint:`` so the frontend (and
    any downstream selection code) can detect + render them as
    non-selectable. The placeholder is intentionally crude — a proper
    in-settings install/pull hint UI lands in a follow-up. This change is
    purely about making Ollama discoverable from the picker.

    Sourced from ``fox_overlay.webui_modules.ollama.get_models()``,
    which already owns daemon detection, custom-URL handling (#109),
    and TTL caching. Label formatting matches upstream's existing
    Ollama Cloud branch (which uses ``_format_ollama_label``).
    """
    try:
        from fox_overlay.webui_modules import ollama as _fox_ollama
        from api.config import _format_ollama_label
    except ImportError:
        return

    groups = result.setdefault("groups", [])
    if not isinstance(groups, list):
        return
    # Don't double-add if upstream ever lands its own ollama branch.
    if any(isinstance(g, dict) and g.get("provider_id") == "ollama" for g in groups):
        return

    status = _fox_ollama.get_models()
    daemon_running = isinstance(status, dict) and bool(status.get("running"))

    models: list[dict] = []
    if daemon_running:
        for entry in status.get("models") or []:
            if not isinstance(entry, dict):
                continue
            name = (entry.get("name") or "").strip()
            if not name:
                continue
            models.append({"id": name, "label": _format_ollama_label(name)})

    if daemon_running and models:
        ollama_status = "ready"
        status_message = None
    elif daemon_running and not models:
        ollama_status = "no_models"
        status_message = "Ollama detected. Pull a model: ollama pull phi4-mini"
        models = [{
            "id": "__ollama_hint:no_models",
            "label": "Pull a model: ollama pull phi4-mini",
        }]
    else:
        ollama_status = "no_daemon"
        status_message = "Ollama not installed. Download from ollama.com/download — refresh after."
        models = [{
            "id": "__ollama_hint:no_daemon",
            "label": "Install Ollama from ollama.com/download",
        }]

    # #389: upstream's alias resolution maps "ollama" → "custom", so it builds
    # a "Custom" group containing the same Ollama models.  Remove overlapping
    # model IDs from other groups so each model appears exactly once (under
    # the OLLAMA heading).
    ollama_ids = {m["id"] for m in models if not m["id"].startswith("__ollama_hint:")}
    if ollama_ids:
        surviving = []
        for g in groups:
            if not isinstance(g, dict):
                surviving.append(g)
                continue
            g_models = g.get("models")
            if not isinstance(g_models, list):
                surviving.append(g)
                continue
            filtered = [m for m in g_models if not (isinstance(m, dict) and m.get("id") in ollama_ids)]
            if filtered:
                g["models"] = filtered
                surviving.append(g)
            # else: group empty after removing Ollama dupes — drop it
        groups[:] = surviving

    group: dict = {
        "provider": "Ollama",
        "provider_id": "custom",
        "models": models,
    }
    if status_message:
        group["status_message"] = status_message
        group["ollama_status"] = ollama_status
    groups.append(group)


def _wrap_get_available_models(upstream_module) -> None:
    """Wrap upstream ``get_available_models()`` to splice in a Fox OLLAMA
    group post-call. See module docstring §"v0.7.4 addition (#303)" for
    why wrap-and-splice was chosen over ``substitute_function``.

    Idempotent via the standard per-target sentinel pattern.
    """
    upstream_fn = upstream_module.get_available_models
    if getattr(upstream_fn, _GET_AVAILABLE_MODELS_SENTINEL, False):
        return

    _check_signature(upstream_fn, _EXPECTED_GET_AVAILABLE_MODELS_SIG, "get_available_models")

    def _fox_get_available_models():
        result = upstream_fn()
        try:
            if isinstance(result, dict):
                _splice_ollama_group(result)
        except Exception:
            _log.exception(
                "[fox-overlay] _splice_ollama_group failed — picker returned without OLLAMA group"
            )
        return result

    setattr(_fox_get_available_models, _GET_AVAILABLE_MODELS_SENTINEL, True)
    _fox_get_available_models.__name__ = upstream_fn.__name__
    _fox_get_available_models.__doc__ = upstream_fn.__doc__
    upstream_module.get_available_models = _fox_get_available_models
    _log.info(
        "[fox-overlay] wrapped api.config.get_available_models — local Ollama group injection enabled (#303)"
    )


def apply() -> None:
    from api import config as _u

    # Apply-level idempotency: bail if reload_config already patched.
    # (get_config patch was dropped in Phase 8 follow-up #238 — upstream
    # v0.51.84 implements mtime-based cache invalidation natively.)
    if getattr(_u.reload_config, _RELOAD_CONFIG_SENTINEL, False):
        return

    # ── Signature self-checks ───────────────────────────────────────────
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

    # ── Patch reload_config: add in-memory models-cache eviction ────────
    # v0.51.84: upstream expanded `global _cfg_mtime` to `global _cfg_mtime,
    # _cfg_path, _cfg_fingerprint`. Anchor updated to match.
    substitute_function(
        upstream_module=_u,
        function_name="reload_config",
        substitutions=[
            (
                # Expand global declaration to include the models-cache vars.
                "    global _cfg_mtime, _cfg_path, _cfg_fingerprint\n"
                "    with _cfg_lock:\n",
                "    global _cfg_mtime, _cfg_path, _cfg_fingerprint, _available_models_cache, _available_models_cache_ts\n"
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

    # ── Wrap get_available_models: splice in local-Ollama group (#303) ──
    _wrap_get_available_models(_u)
