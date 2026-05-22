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
