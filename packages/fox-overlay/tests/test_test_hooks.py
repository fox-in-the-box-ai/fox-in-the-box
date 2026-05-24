"""Tests for fox_overlay.webui_modules.test_hooks (v0.7.7 #264 Phase 0).

Critical invariant: when FITB_TEST_MODE is NOT set to "1", the module
must NOT register anything with the dispatcher. Production builds need
zero new attack surface from this module.
"""
import importlib
import os
import sys

import pytest


@pytest.fixture
def fresh_dispatch(monkeypatch):
    """Stub api.helpers (test_hooks imports j/read_body from there) and
    give each test a fresh dispatch table."""
    fake_helpers = type(sys)("api.helpers")

    def _j(handler, payload, status=200, extra_headers=None):
        handler.responses.append({"status": status, "payload": payload})

    def _read_body(handler):
        return getattr(handler, "_body", {})

    fake_helpers.j = _j
    fake_helpers.read_body = _read_body
    fake_api = type(sys)("api")
    fake_api.helpers = fake_helpers
    monkeypatch.setitem(sys.modules, "api", fake_api)
    monkeypatch.setitem(sys.modules, "api.helpers", fake_helpers)

    import fox_overlay.dispatch as d
    importlib.reload(d)
    yield d
    importlib.reload(d)


# ── Module-load gating (the critical invariant) ───────────────────────────

def test_module_loads_cleanly_without_env(monkeypatch, fresh_dispatch):
    """FITB_TEST_MODE not set → module imports but registers nothing."""
    monkeypatch.delenv("FITB_TEST_MODE", raising=False)
    # Force re-evaluation by removing from sys.modules first
    sys.modules.pop("fox_overlay.webui_modules.test_hooks", None)
    import fox_overlay.webui_modules.test_hooks as _th  # noqa: F401

    # Dispatcher should have no /test/ entry
    d = fresh_dispatch
    assert "/test/" not in d._POST_TABLE
    assert "/test/" not in d._GET_TABLE


def test_module_loads_cleanly_with_env_zero(monkeypatch, fresh_dispatch):
    """FITB_TEST_MODE=0 (any value != '1') → no registration."""
    monkeypatch.setenv("FITB_TEST_MODE", "0")
    sys.modules.pop("fox_overlay.webui_modules.test_hooks", None)
    import fox_overlay.webui_modules.test_hooks as _th  # noqa: F401

    d = fresh_dispatch
    assert "/test/" not in d._POST_TABLE


def test_module_registers_when_env_set(monkeypatch, fresh_dispatch):
    """FITB_TEST_MODE=1 → POST /test/ prefix registered."""
    monkeypatch.setenv("FITB_TEST_MODE", "1")
    sys.modules.pop("fox_overlay.webui_modules.test_hooks", None)
    import fox_overlay.webui_modules.test_hooks as _th  # noqa: F401

    d = fresh_dispatch
    assert "/test/" in d._POST_TABLE


# ── Handler behavior (when enabled) ────────────────────────────────────────

def test_reset_handler_returns_ok_on_empty_state(monkeypatch, tmp_path, fresh_dispatch):
    """/test/reset on a clean state dir returns ok=True with zero removals."""
    monkeypatch.setenv("FITB_TEST_MODE", "1")
    monkeypatch.setenv("HERMES_WEBUI_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("ONBOARDING_PATH", str(tmp_path / "onboarding.json"))
    sys.modules.pop("fox_overlay.webui_modules.test_hooks", None)
    import fox_overlay.webui_modules.test_hooks as th

    # Empty state — directory may not exist yet, that's fine
    result = th.handle_post_reset(handler=None)
    assert result["ok"] is True
    assert result["removed"]["json_files"] == 0
    assert result["removed"]["session_dirs"] == 0
    assert result["onboarding_removed"] is False


def test_reset_handler_removes_json_files(monkeypatch, tmp_path, fresh_dispatch):
    """/test/reset removes *.json files and session_* dirs from state dir."""
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    (state_dir / "sessions.json").write_text("{}")
    (state_dir / "config.json").write_text("{}")
    (state_dir / "unrelated.txt").write_text("keep me")
    (state_dir / "session_abc").mkdir()
    (state_dir / "session_abc" / "msgs.json").write_text("[]")
    onboarding = tmp_path / "onboarding.json"
    onboarding.write_text('{"completed": true}')

    monkeypatch.setenv("FITB_TEST_MODE", "1")
    monkeypatch.setenv("HERMES_WEBUI_STATE_DIR", str(state_dir))
    monkeypatch.setenv("ONBOARDING_PATH", str(onboarding))
    sys.modules.pop("fox_overlay.webui_modules.test_hooks", None)
    import fox_overlay.webui_modules.test_hooks as th

    result = th.handle_post_reset(handler=None)
    assert result["ok"] is True
    assert result["removed"]["json_files"] == 2
    assert result["removed"]["session_dirs"] == 1
    assert result["onboarding_removed"] is True
    # Non-json files NOT touched
    assert (state_dir / "unrelated.txt").exists()


def test_tailscale_set_state_stub_returns_not_implemented(monkeypatch, fresh_dispatch):
    """Phase 0 stub returns 501-shaped {ok: false, error: not_implemented_phase_0}."""
    monkeypatch.setenv("FITB_TEST_MODE", "1")
    sys.modules.pop("fox_overlay.webui_modules.test_hooks", None)
    import fox_overlay.webui_modules.test_hooks as th

    result = th.handle_post_tailscale_set_state(handler=None, body={"state": "running"})
    assert result["ok"] is False
    assert result["error"] == "not_implemented_phase_0"
    assert "Phase 1" in result["hint"]


# ── New Phase 1 hooks ────────────────────────────────────────────────────────

def _make_fake_onboarding(monkeypatch, tmp_path):
    """Stub onboarding module and wire ONBOARDING_PATH to tmp_path."""
    monkeypatch.setenv("ONBOARDING_PATH", str(tmp_path / "onboarding.json"))
    (tmp_path / "onboarding.json").parent.mkdir(parents=True, exist_ok=True)

    # Stub api.config so _mark_onboarding_complete can import save_settings
    fake_config = type(sys)("api.config")
    settings_store: dict = {}

    def _load():
        return dict(settings_store)

    def _save(s):
        settings_store.clear()
        settings_store.update(s)

    fake_config.load_settings = _load
    fake_config.save_settings = _save
    fake_api = sys.modules.get("api") or type(sys)("api")
    fake_api.config = fake_config
    monkeypatch.setitem(sys.modules, "api.config", fake_config)
    monkeypatch.setitem(sys.modules, "api", fake_api)
    return settings_store


def test_skip_onboarding_marks_complete(monkeypatch, tmp_path, fresh_dispatch):
    """/test/skip-onboarding writes onboarding.json and returns ok=True."""
    monkeypatch.setenv("FITB_TEST_MODE", "1")
    store = _make_fake_onboarding(monkeypatch, tmp_path)
    sys.modules.pop("fox_overlay.webui_modules.test_hooks", None)
    sys.modules.pop("fox_overlay.webui_modules.onboarding", None)
    import fox_overlay.webui_modules.test_hooks as th

    result = th.handle_post_skip_onboarding(handler=None)
    assert result["ok"] is True
    onboarding_file = tmp_path / "onboarding.json"
    assert onboarding_file.exists(), "onboarding.json must be written"
    import json
    data = json.loads(onboarding_file.read_text())
    assert data.get("completed") is True


def test_seed_provider_requires_provider_and_key(monkeypatch, fresh_dispatch):
    """/test/seed-provider rejects empty body."""
    monkeypatch.setenv("FITB_TEST_MODE", "1")
    sys.modules.pop("fox_overlay.webui_modules.test_hooks", None)
    import fox_overlay.webui_modules.test_hooks as th

    result = th.handle_post_seed_provider(handler=None, body={})
    assert result["ok"] is False
    assert "required" in result["error"]


def test_seed_provider_rejects_unknown_provider(monkeypatch, fresh_dispatch):
    """/test/seed-provider rejects unsupported provider names."""
    monkeypatch.setenv("FITB_TEST_MODE", "1")
    sys.modules.pop("fox_overlay.webui_modules.test_hooks", None)
    import fox_overlay.webui_modules.test_hooks as th

    result = th.handle_post_seed_provider(
        handler=None, body={"provider": "cohere", "api_key": "sk-test"}
    )
    assert result["ok"] is False
    assert "unsupported" in result["error"]


def test_seed_provider_writes_settings(monkeypatch, tmp_path, fresh_dispatch):
    """/test/seed-provider writes api_key into settings via save_settings."""
    monkeypatch.setenv("FITB_TEST_MODE", "1")
    store = _make_fake_onboarding(monkeypatch, tmp_path)

    # Stub _reload_provider_runtime so the hot-reload best-effort doesn't fail
    fake_providers = type(sys)("api.providers")
    fake_providers._reload_provider_runtime = lambda: None
    monkeypatch.setitem(sys.modules, "api.providers", fake_providers)

    sys.modules.pop("fox_overlay.webui_modules.test_hooks", None)
    import fox_overlay.webui_modules.test_hooks as th

    result = th.handle_post_seed_provider(
        handler=None, body={"provider": "openrouter", "api_key": "sk-or-test-123"}
    )
    assert result["ok"] is True
    assert result["provider"] == "openrouter"
    assert store.get("openrouter_api_key") == "sk-or-test-123"


def test_inject_failure_sets_flag(monkeypatch, fresh_dispatch):
    """/test/inject-failure arms _INJECTED_FAILURE on local_fallback module."""
    monkeypatch.setenv("FITB_TEST_MODE", "1")
    sys.modules.pop("fox_overlay.webui_modules.test_hooks", None)
    import fox_overlay.webui_modules.test_hooks as th
    from fox_overlay.webui_modules import local_fallback

    local_fallback._INJECTED_FAILURE = None  # ensure clean state

    result = th.handle_post_inject_failure(
        handler=None, body={"target": "local_fallback.enable", "kind": "supervisor-unavailable"}
    )
    assert result["ok"] is True
    assert local_fallback._INJECTED_FAILURE == "supervisor-unavailable"

    # Cleanup
    local_fallback._INJECTED_FAILURE = None


def test_inject_failure_rejects_unknown_target(monkeypatch, fresh_dispatch):
    """/test/inject-failure returns error for unknown targets."""
    monkeypatch.setenv("FITB_TEST_MODE", "1")
    sys.modules.pop("fox_overlay.webui_modules.test_hooks", None)
    import fox_overlay.webui_modules.test_hooks as th

    result = th.handle_post_inject_failure(
        handler=None, body={"target": "nonexistent.func", "kind": "x"}
    )
    assert result["ok"] is False
    assert "unknown target" in result["error"]


def test_reset_clears_injected_failure(monkeypatch, tmp_path, fresh_dispatch):
    """/test/reset clears _INJECTED_FAILURE in local_fallback."""
    monkeypatch.setenv("FITB_TEST_MODE", "1")
    monkeypatch.setenv("HERMES_WEBUI_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("ONBOARDING_PATH", str(tmp_path / "onboarding.json"))
    sys.modules.pop("fox_overlay.webui_modules.test_hooks", None)
    import fox_overlay.webui_modules.test_hooks as th
    from fox_overlay.webui_modules import local_fallback

    local_fallback._INJECTED_FAILURE = "armed"
    th.handle_post_reset(handler=None)
    assert local_fallback._INJECTED_FAILURE is None
