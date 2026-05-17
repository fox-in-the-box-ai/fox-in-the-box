"""Phase 6 regression tests for fox_overlay.webui_patches.config.

Covers:
* Module-scope additions: _SETTINGS_DEFAULTS + _SETTINGS_BOOL_KEYS gain
  the 9+4 Fox keys.
* Function patches applied (sentinels set) for get_config, reload_config,
  save_settings.
* Anchor self-check fires on drift in any of the 3 functions.
* Idempotency across multiple apply() calls.
* Behavioral spot-check: bool-string coercion fixes the bool("false")=True
  bug.
"""
import importlib
import sys

import pytest


# Upstream stub matching merge-base 9e31a2a around the anchor regions.
# Trimmed to the bare minimum needed by the substitution anchors —
# unrelated code is collapsed to comments to keep the stub short.
_UPSTREAM_CONFIG_SOURCE = '''\
import os
import threading
from pathlib import Path
from types import SimpleNamespace

_cfg_cache = {}
_cfg_lock = threading.RLock()
_cfg_mtime = 0.0

_available_models_cache = None
_available_models_cache_ts = 0.0

DEFAULT_WORKSPACE = "/tmp"


def _get_config_path() -> Path:
    return Path("/tmp/fox-test-config.yaml")


def _delete_models_cache_on_disk():
    pass


def get_effective_default_model():
    return "test-model"


def resolve_default_workspace(p):
    return p


def load_settings():
    return {}


def get_config() -> dict:
    """Return the cached config dict, loading from disk if needed."""
    if not _cfg_cache:
        reload_config()
    return _cfg_cache


def reload_config() -> None:
    """Reload config.yaml from the active profile's directory."""
    global _cfg_mtime
    with _cfg_lock:
        _cfg_cache.clear()
        config_path = _get_config_path()
        _old_cfg_mtime = _cfg_mtime
        # ... upstream content collapsed ...
        # still hits the fast path without a cold run.
        if _old_cfg_mtime != 0.0:
            _delete_models_cache_on_disk()


_SETTINGS_DEFAULTS = {
    "theme": "system",
    "skin": "default",
    "password_hash": None,
}

_SETTINGS_BOOL_KEYS = {
    "show_thinking",
    "simplified_tool_calling",
    "api_redact_enabled",
}

_SETTINGS_LANG_RE = None  # placeholder


def save_settings(settings: dict) -> dict:
    """Save settings to disk. Returns the merged settings. Ignores unknown keys."""
    current = load_settings()
    pending_theme = current.get("theme")
    pending_skin = current.get("skin")
    if isinstance(settings, dict):
        for k, v in settings.items():
            # Coerce bool keys
            if k in _SETTINGS_BOOL_KEYS:
                v = bool(v)
            current[k] = v
    theme_value = pending_theme
    skin_value = pending_skin
    # ... save to disk collapsed ...
    global DEFAULT_WORKSPACE
    if "default_workspace" in current:
        DEFAULT_WORKSPACE = resolve_default_workspace(current["default_workspace"])
    current["default_model"] = get_effective_default_model()
    return current
'''


def _install_stub(tmp_path, source, monkeypatch):
    api_dir = tmp_path / "api"
    api_dir.mkdir(exist_ok=True)
    (api_dir / "__init__.py").write_text("")
    (api_dir / "config.py").write_text(source)
    monkeypatch.syspath_prepend(str(tmp_path))
    for name in list(sys.modules):
        if name == "api" or name.startswith("api."):
            del sys.modules[name]
    import api.config as fake_config  # noqa: F401
    return sys.modules["api.config"]


@pytest.fixture
def fresh_config(tmp_path, monkeypatch):
    fake_config = _install_stub(tmp_path, _UPSTREAM_CONFIG_SOURCE, monkeypatch)
    import fox_overlay.webui_patches.config as patch_mod
    importlib.reload(patch_mod)
    yield fake_config, patch_mod
    importlib.reload(patch_mod)
    for name in list(sys.modules):
        if name == "api" or name.startswith("api."):
            del sys.modules[name]


# ── apply() applies all 3 function patches + module-scope additions ──────

def test_apply_marks_all_function_sentinels(fresh_config):
    _u, patch_mod = fresh_config
    patch_mod.apply()
    assert getattr(_u.get_config, "_fox_patched_get_config", False) is True
    assert getattr(_u.reload_config, "_fox_patched_reload_config", False) is True
    assert getattr(_u.save_settings, "_fox_patched_save_settings", False) is True


def test_apply_adds_fox_defaults(fresh_config):
    _u, patch_mod = fresh_config
    patch_mod.apply()
    for key in ("local_fallback_enabled", "hostname_prompted",
                "tailscale_login_server", "tailscale_advertise_routes",
                "tailscale_advertise_tags", "tailscale_accept_routes",
                "tailscale_accept_dns", "tailscale_exit_node",
                "ollama_custom_url"):
        assert key in _u._SETTINGS_DEFAULTS, f"missing default: {key}"


def test_apply_adds_fox_bool_keys(fresh_config):
    _u, patch_mod = fresh_config
    patch_mod.apply()
    for key in ("local_fallback_enabled", "hostname_prompted",
                "tailscale_accept_routes", "tailscale_accept_dns"):
        assert key in _u._SETTINGS_BOOL_KEYS, f"missing bool key: {key}"


def test_apply_preserves_upstream_defaults(fresh_config):
    """Fox additions must be additive; never overwrite upstream defaults."""
    _u, patch_mod = fresh_config
    pre_theme = _u._SETTINGS_DEFAULTS["theme"]
    patch_mod.apply()
    assert _u._SETTINGS_DEFAULTS["theme"] == pre_theme


def test_apply_is_idempotent(fresh_config):
    _u, patch_mod = fresh_config
    patch_mod.apply()
    defaults_count = len(_u._SETTINGS_DEFAULTS)
    bool_count = len(_u._SETTINGS_BOOL_KEYS)
    patch_mod.apply()  # second call — no-op
    assert len(_u._SETTINGS_DEFAULTS) == defaults_count
    assert len(_u._SETTINGS_BOOL_KEYS) == bool_count


# ── Behavioral check: bool-string coercion fix ───────────────────────────

def test_bool_string_false_does_not_flip_to_true(fresh_config):
    """Pre-patch: bool('false') == True. Patched: 'false' → False."""
    _u, patch_mod = fresh_config
    patch_mod.apply()
    result = _u.save_settings({"hostname_prompted": "false"})
    assert result.get("hostname_prompted") is False


def test_bool_string_true_recognized(fresh_config):
    _u, patch_mod = fresh_config
    patch_mod.apply()
    result = _u.save_settings({"local_fallback_enabled": "true"})
    assert result.get("local_fallback_enabled") is True


def test_bool_native_true_passes_through(fresh_config):
    _u, patch_mod = fresh_config
    patch_mod.apply()
    result = _u.save_settings({"local_fallback_enabled": True})
    assert result.get("local_fallback_enabled") is True


def test_bool_unrecognized_string_is_skipped(fresh_config):
    """Garbage string for a bool key — skip the setting, don't crash."""
    _u, patch_mod = fresh_config
    patch_mod.apply()
    # No prior value; skip means key absent from result
    result = _u.save_settings({"local_fallback_enabled": "maybe"})
    assert "local_fallback_enabled" not in result


# ── Anchor drift detection ───────────────────────────────────────────────

def test_anchor_drift_in_get_config_fails_fast(tmp_path, monkeypatch):
    drifted = _UPSTREAM_CONFIG_SOURCE.replace(
        "    if not _cfg_cache:\n        reload_config()\n    return _cfg_cache\n",
        "    return _cfg_cache  # upstream simplified\n",
    )
    _install_stub(tmp_path, drifted, monkeypatch)
    import fox_overlay.webui_patches.config as patch_mod
    importlib.reload(patch_mod)
    with pytest.raises(AssertionError, match="anchor expected EXACTLY ONCE"):
        patch_mod.apply()
    importlib.reload(patch_mod)
    for name in list(sys.modules):
        if name == "api" or name.startswith("api."):
            del sys.modules[name]


def test_signature_drift_in_save_settings_fails_fast(tmp_path, monkeypatch):
    drifted = _UPSTREAM_CONFIG_SOURCE.replace(
        "def save_settings(settings: dict) -> dict:",
        "def save_settings(settings: dict, force: bool = False) -> dict:",
    )
    _install_stub(tmp_path, drifted, monkeypatch)
    import fox_overlay.webui_patches.config as patch_mod
    importlib.reload(patch_mod)
    with pytest.raises(AssertionError, match="save_settings signature drift"):
        patch_mod.apply()
    importlib.reload(patch_mod)
    for name in list(sys.modules):
        if name == "api" or name.startswith("api."):
            del sys.modules[name]
