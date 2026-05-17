"""Phase 6 regression tests for fox_overlay.webui_patches.providers.

Verifies the substitute_function-based monkey-patch correctly inserts
the gateway-hot-reload call into ``set_provider_key`` while leaving
the rest of the upstream behavior intact.

The patch uses ``inspect.getsource`` which needs a real file backing
the function — so the test fixture writes a stub file to ``tmp_path``
and imports it as ``api.providers``.
"""
import importlib
import importlib.util
import sys
import types

import pytest


# Stub source matching upstream merge-base api/providers.py around the
# anchor we patch (verified against 9e31a2a). Keeping the anchor area
# verbatim catches anchor drift at the test level too.
_UPSTREAM_PROVIDERS_SOURCE = '''\
import logging
from typing import Any

logger = logging.getLogger(__name__)


def invalidate_models_cache():
    """Stub for tests."""
    invalidate_models_cache.calls += 1
invalidate_models_cache.calls = 0


_PROVIDER_DISPLAY = {"openai": "OpenAI"}


def set_provider_key(provider_id: str, api_key: str | None) -> dict[str, Any]:
    """Persist an API key for a provider."""
    if provider_id == "fail-write":
        logger.exception("Failed to write env file for provider %s", provider_id)
        return {"ok": False, "error": "Failed to save API key: simulated"}

    # Invalidate the model cache so the dropdown refreshes on next request.
    # Using invalidate_models_cache() instead of reload_config() to avoid
    # disrupting active streaming sessions that may be reading config.cfg.
    invalidate_models_cache()

    return {
        "ok": True,
        "provider": provider_id,
        "display_name": _PROVIDER_DISPLAY.get(provider_id, provider_id),
        "action": "updated" if api_key else "removed",
    }
'''


def _install_stub(tmp_path, source: str, monkeypatch):
    """Write `source` to tmp_path/api/providers.py and import it as `api.providers`.

    Using a real file (not exec) is required because the patch uses
    inspect.getsource which needs a file backing.
    """
    api_dir = tmp_path / "api"
    api_dir.mkdir(exist_ok=True)
    (api_dir / "__init__.py").write_text("")
    providers_path = api_dir / "providers.py"
    providers_path.write_text(source)
    monkeypatch.syspath_prepend(str(tmp_path))
    # Ensure clean re-import — drop any cached api/* modules
    for name in list(sys.modules):
        if name == "api" or name.startswith("api."):
            del sys.modules[name]
    import api.providers as fake_providers  # noqa: F401  (registers in sys.modules)
    return sys.modules["api.providers"]


@pytest.fixture
def fake_providers_module(tmp_path, monkeypatch):
    """Install upstream stub + reload patch module so apply() targets the stub."""
    fake_providers = _install_stub(tmp_path, _UPSTREAM_PROVIDERS_SOURCE, monkeypatch)

    import fox_overlay.webui_patches.providers as patch_mod
    importlib.reload(patch_mod)

    yield fake_providers, patch_mod

    importlib.reload(patch_mod)
    # Drop cached api/* so the next test gets a clean slate
    for name in list(sys.modules):
        if name == "api" or name.startswith("api."):
            del sys.modules[name]


# ── basic apply() smoke ────────────────────────────────────────────────────

def test_apply_is_idempotent(fake_providers_module):
    """apply() can be called multiple times safely (sentinel guard)."""
    fake_providers, patch_mod = fake_providers_module
    patch_mod.apply()
    patch_mod.apply()
    assert getattr(fake_providers.set_provider_key, "_fox_patched_set_provider_key", False) is True


def test_apply_does_not_corrupt_unrelated_functions(fake_providers_module):
    """invalidate_models_cache survives the patch unmodified."""
    fake_providers, patch_mod = fake_providers_module
    pre_count = fake_providers.invalidate_models_cache.calls
    patch_mod.apply()
    # invalidate_models_cache should still be callable + behave normally
    fake_providers.invalidate_models_cache()
    assert fake_providers.invalidate_models_cache.calls == pre_count + 1


# ── patched behavior ───────────────────────────────────────────────────────

def test_patched_set_provider_key_calls_reload_runtime(fake_providers_module, monkeypatch):
    """After patch, set_provider_key calls _reload_provider_runtime exactly once."""
    fake_providers, patch_mod = fake_providers_module
    calls = []
    monkeypatch.setattr(patch_mod, "_reload_provider_runtime", lambda: calls.append("called"))
    patch_mod.apply()
    # Pre-patch invocation count baseline
    fake_providers.invalidate_models_cache.calls = 0
    result = fake_providers.set_provider_key("openai", "sk-test")
    assert result == {
        "ok": True,
        "provider": "openai",
        "display_name": "OpenAI",
        "action": "updated",
    }
    assert calls == ["called"]
    # invalidate_models_cache should still fire BEFORE the reload
    assert fake_providers.invalidate_models_cache.calls == 1


def test_patched_failure_path_does_not_call_reload(fake_providers_module, monkeypatch):
    """The early-return failure path skips the reload."""
    fake_providers, patch_mod = fake_providers_module
    calls = []
    monkeypatch.setattr(patch_mod, "_reload_provider_runtime", lambda: calls.append("called"))
    patch_mod.apply()
    result = fake_providers.set_provider_key("fail-write", "sk-test")
    assert result["ok"] is False
    assert calls == []  # reload NOT called on the failure path


def test_patched_remove_path_calls_reload(fake_providers_module, monkeypatch):
    """api_key=None ('remove') is on the same success path — also reloads."""
    fake_providers, patch_mod = fake_providers_module
    calls = []
    monkeypatch.setattr(patch_mod, "_reload_provider_runtime", lambda: calls.append("called"))
    patch_mod.apply()
    result = fake_providers.set_provider_key("openai", None)
    assert result["action"] == "removed"
    assert calls == ["called"]


# ── anchor-drift detection ────────────────────────────────────────────────

def test_apply_fails_loud_when_anchor_missing(tmp_path, monkeypatch):
    """If upstream removes or renames invalidate_models_cache, the patch fails fast."""
    drifted_source = '''\
def set_provider_key(provider_id, api_key):
    return {"ok": True, "provider": provider_id}
'''
    _install_stub(tmp_path, drifted_source, monkeypatch)
    import fox_overlay.webui_patches.providers as patch_mod
    importlib.reload(patch_mod)
    with pytest.raises(AssertionError, match="anchor expected EXACTLY ONCE"):
        patch_mod.apply()
    importlib.reload(patch_mod)
    for name in list(sys.modules):
        if name == "api" or name.startswith("api."):
            del sys.modules[name]


# ── _reload_provider_runtime helper (Fox-side, defined in the patch module) ──

def test_reload_runtime_noop_when_supervisorctl_missing(monkeypatch):
    """Helper is a silent no-op outside FITB supervisor deployments."""
    import fox_overlay.webui_patches.providers as patch_mod
    monkeypatch.setattr(patch_mod.shutil, "which", lambda binary: None)
    # Capture subprocess.run to ensure it's NOT called
    calls = []
    monkeypatch.setattr(patch_mod.subprocess, "run", lambda *a, **kw: calls.append(a))
    patch_mod._reload_provider_runtime()
    assert calls == []


def test_reload_runtime_invokes_supervisorctl_when_present(monkeypatch):
    """Helper shells out to supervisorctl restart when it's on PATH."""
    import fox_overlay.webui_patches.providers as patch_mod
    monkeypatch.setattr(patch_mod.shutil, "which", lambda binary: "/usr/bin/supervisorctl")
    captured = []
    monkeypatch.setattr(patch_mod.subprocess, "run", lambda *a, **kw: captured.append(a[0]))
    patch_mod._reload_provider_runtime()
    assert captured == [
        ["supervisorctl", "-c", "/etc/supervisor/supervisord.conf",
         "restart", "hermes-gateway"],
    ]
