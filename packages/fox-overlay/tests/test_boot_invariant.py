"""Regression tests for AUTH-02: managed-mode boot invariant.

Covers:
* FOX_PLANE_AUTH_SECRET set + auth disabled → SystemExit(1)
* FOX_PLANE_AUTH_SECRET set + auth enabled → no error
* Standalone mode (no secret) → no check performed
* api.auth not importable → warning, no crash
"""
import importlib
import sys

import pytest


_UPSTREAM_AUTH_ENABLED = '''\
def is_auth_enabled() -> bool:
    return True

def is_password_auth_enabled():
    return True

def are_passkeys_enabled():
    return False
'''

_UPSTREAM_AUTH_DISABLED = '''\
def is_auth_enabled() -> bool:
    return False

def is_password_auth_enabled():
    return False

def are_passkeys_enabled():
    return False
'''


def _install_auth_stub(tmp_path, source, monkeypatch):
    api_dir = tmp_path / "api"
    api_dir.mkdir(exist_ok=True)
    (api_dir / "__init__.py").write_text("")
    (api_dir / "auth.py").write_text(source)
    monkeypatch.syspath_prepend(str(tmp_path))
    for name in list(sys.modules):
        if name == "api" or name.startswith("api."):
            del sys.modules[name]


def _reload_bootstrap(monkeypatch):
    monkeypatch.setenv("FOX_OVERLAY_AUTOINSTALL", "0")
    import fox_overlay.bootstrap as b
    importlib.reload(b)
    return b


@pytest.fixture(autouse=True)
def _cleanup_api_modules():
    yield
    for name in list(sys.modules):
        if name == "api" or name.startswith("api."):
            del sys.modules[name]


def test_secret_set_auth_disabled_exits(tmp_path, monkeypatch):
    """FOX_PLANE_AUTH_SECRET + auth disabled → SystemExit(1)."""
    _install_auth_stub(tmp_path, _UPSTREAM_AUTH_DISABLED, monkeypatch)
    monkeypatch.setenv("FOX_PLANE_AUTH_SECRET", "test-secret")
    b = _reload_bootstrap(monkeypatch)

    with pytest.raises(SystemExit) as exc_info:
        b._check_managed_mode_invariant()
    assert exc_info.value.code == 1


def test_secret_set_auth_enabled_ok(tmp_path, monkeypatch):
    """FOX_PLANE_AUTH_SECRET + auth enabled → no error."""
    _install_auth_stub(tmp_path, _UPSTREAM_AUTH_ENABLED, monkeypatch)
    monkeypatch.setenv("FOX_PLANE_AUTH_SECRET", "test-secret")
    b = _reload_bootstrap(monkeypatch)

    b._check_managed_mode_invariant()


def test_standalone_no_secret_skips_check(monkeypatch):
    """No FOX_PLANE_AUTH_SECRET → check is a no-op."""
    monkeypatch.delenv("FOX_PLANE_AUTH_SECRET", raising=False)
    b = _reload_bootstrap(monkeypatch)

    b._check_managed_mode_invariant()


def test_standalone_empty_secret_skips_check(monkeypatch):
    """Empty FOX_PLANE_AUTH_SECRET → treated as unset."""
    monkeypatch.setenv("FOX_PLANE_AUTH_SECRET", "")
    b = _reload_bootstrap(monkeypatch)

    b._check_managed_mode_invariant()


def test_api_auth_not_importable_warns(tmp_path, monkeypatch, caplog):
    """If api.auth can't be imported, warn but don't crash."""
    for name in list(sys.modules):
        if name == "api" or name.startswith("api."):
            del sys.modules[name]
    monkeypatch.setenv("FOX_PLANE_AUTH_SECRET", "test-secret")
    b = _reload_bootstrap(monkeypatch)

    import logging
    with caplog.at_level(logging.WARNING, logger="fox_overlay.bootstrap"):
        b._check_managed_mode_invariant()
    assert any("cannot import api.auth" in r.message for r in caplog.records)


def test_exit_message_mentions_remediation(tmp_path, monkeypatch, capsys):
    """Error message should tell the operator how to fix the problem."""
    _install_auth_stub(tmp_path, _UPSTREAM_AUTH_DISABLED, monkeypatch)
    monkeypatch.setenv("FOX_PLANE_AUTH_SECRET", "test-secret")
    b = _reload_bootstrap(monkeypatch)

    with pytest.raises(SystemExit):
        b._check_managed_mode_invariant()

    captured = capsys.readouterr()
    assert "HERMES_WEBUI_PASSWORD" in captured.err or "standalone mode" in captured.err
