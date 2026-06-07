"""Regression tests for fox_overlay.webui_patches.auth (AUTH-01).

Covers:
* Module load + structural sanity (sentinel, signature constant, helpers)
* Signature drift fails fast with diagnostic
* Substitution anchor present and unique
* apply() patches check_auth correctly against a stub
* X-Fox-Auth grants access with valid secret (constant-time comparison)
* X-Fox-Auth rejected with wrong secret
* Standalone mode (no FOX_PLANE_AUTH_SECRET) — injected block is a no-op
* Idempotency — re-apply is a no-op
"""
import importlib
import sys
from types import SimpleNamespace

import pytest


_UPSTREAM_AUTH_SOURCE = '''\
PUBLIC_PATHS = {"/health"}

def is_auth_enabled():
    return True

def parse_cookie(handler):
    return None

def verify_session(cookie_val):
    return False

def check_auth(handler, parsed) -> bool:
    """Check if request is authorized. Returns True if OK.
    If not authorized, sends 401 (API) or 302 redirect (page) and returns False."""
    if not is_auth_enabled():
        return True
    # Public paths don't require auth
    if parsed.path in PUBLIC_PATHS or parsed.path.startswith('/static/') or parsed.path.startswith('/session/static/'):
        return True
    # Check session cookie
    cookie_val = parse_cookie(handler)
    if cookie_val and verify_session(cookie_val):
        return True
    # Not authorized
    if parsed.path.startswith('/api/'):
        handler._sent_status = 401
    else:
        handler._sent_status = 302
    return False
'''


def _install_stub(tmp_path, source, monkeypatch):
    api_dir = tmp_path / "api"
    api_dir.mkdir(exist_ok=True)
    (api_dir / "__init__.py").write_text("")
    (api_dir / "auth.py").write_text(source)
    monkeypatch.syspath_prepend(str(tmp_path))
    for name in list(sys.modules):
        if name == "api" or name.startswith("api."):
            del sys.modules[name]
    import api.auth as fake_auth  # noqa: F401
    return sys.modules["api.auth"]


def _make_handler(headers=None):
    h = SimpleNamespace(_sent_status=None)
    _headers = headers or {}
    h.headers = SimpleNamespace(get=lambda key, default='': _headers.get(key, default))
    return h


def _parsed(path):
    return SimpleNamespace(path=path)


@pytest.fixture
def fresh_auth(tmp_path, monkeypatch):
    fake_auth = _install_stub(tmp_path, _UPSTREAM_AUTH_SOURCE, monkeypatch)
    import fox_overlay.webui_patches.auth as patch_mod
    importlib.reload(patch_mod)
    yield fake_auth, patch_mod
    importlib.reload(patch_mod)
    for name in list(sys.modules):
        if name == "api" or name.startswith("api."):
            del sys.modules[name]


# ── Module load + structural sanity ──────────────────────────────────────────

def test_module_loads_without_error(fresh_auth):
    _u, patch_mod = fresh_auth
    assert hasattr(patch_mod, "_CHECK_AUTH_SENTINEL")
    assert hasattr(patch_mod, "_EXPECTED_CHECK_AUTH_SIG")
    assert hasattr(patch_mod, "_check_signature")
    assert hasattr(patch_mod, "apply")


# ── Signature drift detection ────────────────────────────────────────────────

def test_signature_drift_fails_fast(tmp_path, monkeypatch):
    drifted = _UPSTREAM_AUTH_SOURCE.replace(
        "def check_auth(handler, parsed) -> bool:",
        "def check_auth(handler, parsed, extra=None) -> bool:",
    )
    _install_stub(tmp_path, drifted, monkeypatch)
    import fox_overlay.webui_patches.auth as patch_mod
    importlib.reload(patch_mod)
    with pytest.raises(AssertionError, match="check_auth signature drift"):
        patch_mod.apply()
    importlib.reload(patch_mod)
    for name in list(sys.modules):
        if name == "api" or name.startswith("api."):
            del sys.modules[name]


def test_signature_check_helper_directly():
    import fox_overlay.webui_patches.auth as patch_mod
    def _fake(): pass
    with pytest.raises(AssertionError, match="signature drift"):
        patch_mod._check_signature(_fake, "(x, y)", "fake")


# ── Anchor presence ──────────────────────────────────────────────────────────

def test_substitution_anchor_present():
    import inspect
    import fox_overlay.webui_patches.auth as patch_mod
    src = inspect.getsource(patch_mod.apply)
    assert "cookie_val = parse_cookie(handler)" in src
    assert "X-Fox-Auth" in src
    assert "_hmac_compare" in src
    assert "_fox_get_plane_secret" in src


# ── apply() patches check_auth ───────────────────────────────────────────────

def test_apply_patches_check_auth(fresh_auth, monkeypatch):
    fake_auth, patch_mod = fresh_auth
    monkeypatch.setenv("FOX_PLANE_AUTH_SECRET", "test-secret-42")
    patch_mod.apply()
    assert getattr(fake_auth.check_auth, patch_mod._CHECK_AUTH_SENTINEL, False)


def test_apply_idempotent(fresh_auth, monkeypatch):
    fake_auth, patch_mod = fresh_auth
    monkeypatch.setenv("FOX_PLANE_AUTH_SECRET", "test-secret-42")
    patch_mod.apply()
    patch_mod.apply()
    assert getattr(fake_auth.check_auth, patch_mod._CHECK_AUTH_SENTINEL, False)


# ── X-Fox-Auth grants access with valid secret ──────────────────────────────

def test_valid_x_fox_auth_grants_access(fresh_auth, monkeypatch):
    fake_auth, patch_mod = fresh_auth
    monkeypatch.setenv("FOX_PLANE_AUTH_SECRET", "my-plane-secret")
    patch_mod.apply()

    handler = _make_handler({"X-Fox-Auth": "my-plane-secret"})
    result = fake_auth.check_auth(handler, _parsed("/api/sessions"))
    assert result is True
    assert handler._sent_status is None


# ── X-Fox-Auth rejected with wrong secret ────────────────────────────────────

def test_invalid_x_fox_auth_rejected(fresh_auth, monkeypatch):
    fake_auth, patch_mod = fresh_auth
    monkeypatch.setenv("FOX_PLANE_AUTH_SECRET", "my-plane-secret")
    patch_mod.apply()

    handler = _make_handler({"X-Fox-Auth": "wrong-secret"})
    result = fake_auth.check_auth(handler, _parsed("/api/sessions"))
    assert result is False
    assert handler._sent_status == 401


def test_empty_x_fox_auth_rejected(fresh_auth, monkeypatch):
    fake_auth, patch_mod = fresh_auth
    monkeypatch.setenv("FOX_PLANE_AUTH_SECRET", "my-plane-secret")
    patch_mod.apply()

    handler = _make_handler({"X-Fox-Auth": ""})
    result = fake_auth.check_auth(handler, _parsed("/api/sessions"))
    assert result is False
    assert handler._sent_status == 401


def test_missing_x_fox_auth_header_rejected(fresh_auth, monkeypatch):
    fake_auth, patch_mod = fresh_auth
    monkeypatch.setenv("FOX_PLANE_AUTH_SECRET", "my-plane-secret")
    patch_mod.apply()

    handler = _make_handler({})
    result = fake_auth.check_auth(handler, _parsed("/api/sessions"))
    assert result is False
    assert handler._sent_status == 401


# ── Standalone mode (no FOX_PLANE_AUTH_SECRET) ───────────────────────────────

def test_standalone_mode_no_secret_falls_through(fresh_auth, monkeypatch):
    fake_auth, patch_mod = fresh_auth
    monkeypatch.delenv("FOX_PLANE_AUTH_SECRET", raising=False)
    patch_mod.apply()

    handler = _make_handler({})
    result = fake_auth.check_auth(handler, _parsed("/api/sessions"))
    assert result is False
    assert handler._sent_status == 401


def test_standalone_with_x_fox_auth_header_ignored(fresh_auth, monkeypatch):
    """Without FOX_PLANE_AUTH_SECRET set, even a X-Fox-Auth header is ignored."""
    fake_auth, patch_mod = fresh_auth
    monkeypatch.delenv("FOX_PLANE_AUTH_SECRET", raising=False)
    patch_mod.apply()

    handler = _make_handler({"X-Fox-Auth": "anything"})
    result = fake_auth.check_auth(handler, _parsed("/api/sessions"))
    assert result is False
    assert handler._sent_status == 401


# ── Public paths still bypass auth ───────────────────────────────────────────

def test_public_path_bypasses_auth_after_patch(fresh_auth, monkeypatch):
    fake_auth, patch_mod = fresh_auth
    monkeypatch.setenv("FOX_PLANE_AUTH_SECRET", "secret")
    patch_mod.apply()

    handler = _make_handler({})
    result = fake_auth.check_auth(handler, _parsed("/health"))
    assert result is True


def test_static_path_bypasses_auth_after_patch(fresh_auth, monkeypatch):
    fake_auth, patch_mod = fresh_auth
    monkeypatch.setenv("FOX_PLANE_AUTH_SECRET", "secret")
    patch_mod.apply()

    handler = _make_handler({})
    result = fake_auth.check_auth(handler, _parsed("/static/css/main.css"))
    assert result is True


# ── Non-API path gets 302 redirect ──────────────────────────────────────────

def test_non_api_path_gets_redirect(fresh_auth, monkeypatch):
    fake_auth, patch_mod = fresh_auth
    monkeypatch.setenv("FOX_PLANE_AUTH_SECRET", "secret")
    patch_mod.apply()

    handler = _make_handler({})
    result = fake_auth.check_auth(handler, _parsed("/dashboard"))
    assert result is False
    assert handler._sent_status == 302


# ── Constant-time comparison helper ──────────────────────────────────────────

def test_hmac_compare_equal():
    from fox_overlay.webui_patches.auth import _hmac_compare
    assert _hmac_compare("abc", "abc") is True


def test_hmac_compare_not_equal():
    from fox_overlay.webui_patches.auth import _hmac_compare
    assert _hmac_compare("abc", "xyz") is False


def test_hmac_compare_empty():
    from fox_overlay.webui_patches.auth import _hmac_compare
    assert _hmac_compare("", "") is True


def test_fox_get_plane_secret_returns_env(monkeypatch):
    from fox_overlay.webui_patches.auth import _fox_get_plane_secret
    monkeypatch.setenv("FOX_PLANE_AUTH_SECRET", "test-secret")
    assert _fox_get_plane_secret() == "test-secret"


def test_fox_get_plane_secret_returns_empty_when_unset(monkeypatch):
    from fox_overlay.webui_patches.auth import _fox_get_plane_secret
    monkeypatch.delenv("FOX_PLANE_AUTH_SECRET", raising=False)
    assert _fox_get_plane_secret() == ""
