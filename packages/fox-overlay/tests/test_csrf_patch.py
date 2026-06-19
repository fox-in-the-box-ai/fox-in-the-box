"""Regression tests for fox_overlay.webui_patches.csrf (CSRF-01).

Covers:
* _fox_csrf_plane_bypass: valid secret, wrong secret, empty secret,
  no header, standalone mode (no FOX_PLANE_AUTH_SECRET)
* Substitution anchor present and unique in upstream _check_csrf
* apply() patches _check_csrf correctly against a stub
* Idempotency — re-apply is a no-op
* Signature drift detection
"""
import importlib
import sys
from types import SimpleNamespace

import pytest


_UPSTREAM_ROUTES_SOURCE = '''\
import os
import re as _re


def _clear_csrf_failure_reason(handler):
    handler._csrf_reason = None

def _set_csrf_failure_reason(handler, reason):
    handler._csrf_reason = reason
    return False

def _is_browser_unsafe_request(handler):
    return handler.headers.get("Origin", "") != ""

def _normalize_host_port(host):
    if ":" in host:
        h, p = host.rsplit(":", 1)
        return h, p
    return host, None

def _ports_match(scheme, p1, p2):
    return True

def _allowed_public_origins():
    val = os.getenv("HERMES_WEBUI_ALLOWED_ORIGINS", "")
    return set(v.strip().lower() for v in val.split(",") if v.strip())


def _check_csrf(handler) -> bool:
    """Reject cross-origin or tokenless authenticated browser unsafe requests."""
    _clear_csrf_failure_reason(handler)
    origin = handler.headers.get("Origin", "")
    referer = handler.headers.get("Referer", "")
    host = handler.headers.get("Host", "")
    if not _is_browser_unsafe_request(handler):
        return True
    target = origin or referer
    m = _re.match(r"^https?://([^/]+)", target)
    if not m:
        return _set_csrf_failure_reason(handler, "origin_mismatch")
    origin_host = m.group(1)
    origin_scheme = m.group(0).split("://")[0].lower()
    origin_name, origin_port = _normalize_host_port(origin_host)
    origin_allowed = False
    origin_value = m.group(0).rstrip("/").lower()
    if origin_value in _allowed_public_origins():
        origin_allowed = True
    if not origin_allowed:
        allowed_hosts = [h.strip() for h in [host] if h.strip()]
        trust_forwarded_host = os.getenv("HERMES_WEBUI_TRUST_FORWARDED_HOST", "").strip().lower()
        if trust_forwarded_host in ("1", "true", "yes", "on"):
            allowed_hosts.extend(
                h.strip()
                for h in [
                    handler.headers.get("X-Forwarded-Host", ""),
                    handler.headers.get("X-Real-Host", ""),
                ]
                if h.strip()
            )
        for allowed in allowed_hosts:
            allowed_name, allowed_port = _normalize_host_port(allowed)
            if origin_name == allowed_name and _ports_match(origin_scheme, origin_port, allowed_port):
                origin_allowed = True
                break
    if not origin_allowed:
        return _set_csrf_failure_reason(handler, "origin_mismatch")

    from api.auth import CSRF_HEADER_NAME, is_auth_enabled, parse_cookie, verify_csrf_token

    if not is_auth_enabled():
        return True
    cookie_val = parse_cookie(handler)
    submitted = handler.headers.get(CSRF_HEADER_NAME) or handler.headers.get("X-CSRF-Token")
    if verify_csrf_token(cookie_val or "", submitted or ""):
        return True
    return _set_csrf_failure_reason(handler, "token_mismatch")
'''

_UPSTREAM_AUTH_SOURCE = '''\
CSRF_HEADER_NAME = "X-CSRF-Token"

def is_auth_enabled():
    return True

def parse_cookie(handler):
    return None

def verify_csrf_token(cookie_val, submitted):
    return False
'''


def _install_stubs(tmp_path, monkeypatch):
    api_dir = tmp_path / "api"
    api_dir.mkdir(exist_ok=True)
    (api_dir / "__init__.py").write_text("")
    (api_dir / "routes.py").write_text(_UPSTREAM_ROUTES_SOURCE)
    (api_dir / "auth.py").write_text(_UPSTREAM_AUTH_SOURCE)
    monkeypatch.syspath_prepend(str(tmp_path))
    for name in list(sys.modules):
        if name == "api" or name.startswith("api."):
            del sys.modules[name]
    import api.routes as fake_routes  # noqa: F401
    return sys.modules["api.routes"]


def _make_handler(headers=None):
    h = SimpleNamespace(_csrf_reason=None)
    _headers = headers or {}
    h.headers = SimpleNamespace(get=lambda key, default="": _headers.get(key, default))
    return h


@pytest.fixture
def fresh_csrf(tmp_path, monkeypatch):
    fake_routes = _install_stubs(tmp_path, monkeypatch)
    import fox_overlay.webui_patches.csrf as patch_mod
    importlib.reload(patch_mod)
    yield fake_routes, patch_mod
    importlib.reload(patch_mod)
    for name in list(sys.modules):
        if name == "api" or name.startswith("api."):
            del sys.modules[name]


# ── _fox_csrf_plane_bypass unit tests ────────────────────────────────────────

def test_bypass_valid_secret(monkeypatch):
    from fox_overlay.webui_patches.csrf import _fox_csrf_plane_bypass
    monkeypatch.setenv("FOX_PLANE_AUTH_SECRET", "test-secret")
    handler = _make_handler({"X-Fox-Auth": "test-secret"})
    assert _fox_csrf_plane_bypass(handler) is True


def test_bypass_wrong_secret(monkeypatch):
    from fox_overlay.webui_patches.csrf import _fox_csrf_plane_bypass
    monkeypatch.setenv("FOX_PLANE_AUTH_SECRET", "test-secret")
    handler = _make_handler({"X-Fox-Auth": "wrong-secret"})
    assert _fox_csrf_plane_bypass(handler) is False


def test_bypass_empty_header(monkeypatch):
    from fox_overlay.webui_patches.csrf import _fox_csrf_plane_bypass
    monkeypatch.setenv("FOX_PLANE_AUTH_SECRET", "test-secret")
    handler = _make_handler({"X-Fox-Auth": ""})
    assert _fox_csrf_plane_bypass(handler) is False


def test_bypass_no_header(monkeypatch):
    from fox_overlay.webui_patches.csrf import _fox_csrf_plane_bypass
    monkeypatch.setenv("FOX_PLANE_AUTH_SECRET", "test-secret")
    handler = _make_handler({})
    assert _fox_csrf_plane_bypass(handler) is False


def test_bypass_standalone_no_secret(monkeypatch):
    from fox_overlay.webui_patches.csrf import _fox_csrf_plane_bypass
    monkeypatch.delenv("FOX_PLANE_AUTH_SECRET", raising=False)
    handler = _make_handler({"X-Fox-Auth": "anything"})
    assert _fox_csrf_plane_bypass(handler) is False


def test_bypass_empty_secret(monkeypatch):
    from fox_overlay.webui_patches.csrf import _fox_csrf_plane_bypass
    monkeypatch.setenv("FOX_PLANE_AUTH_SECRET", "")
    handler = _make_handler({"X-Fox-Auth": "anything"})
    assert _fox_csrf_plane_bypass(handler) is False


# ── Signature drift detection ────────────────────────────────────────────────

def test_signature_drift_fails_fast(tmp_path, monkeypatch):
    drifted = _UPSTREAM_ROUTES_SOURCE.replace(
        "def _check_csrf(handler) -> bool:",
        "def _check_csrf(handler, extra=None) -> bool:",
    )
    api_dir = tmp_path / "api"
    api_dir.mkdir(exist_ok=True)
    (api_dir / "__init__.py").write_text("")
    (api_dir / "routes.py").write_text(drifted)
    (api_dir / "auth.py").write_text(_UPSTREAM_AUTH_SOURCE)
    monkeypatch.syspath_prepend(str(tmp_path))
    for name in list(sys.modules):
        if name == "api" or name.startswith("api."):
            del sys.modules[name]
    import fox_overlay.webui_patches.csrf as patch_mod
    importlib.reload(patch_mod)
    with pytest.raises(AssertionError, match="_check_csrf signature drift"):
        patch_mod.apply()
    importlib.reload(patch_mod)
    for name in list(sys.modules):
        if name == "api" or name.startswith("api."):
            del sys.modules[name]


# ── apply() patches _check_csrf ──────────────────────────────────────────────

def test_apply_patches_check_csrf(fresh_csrf, monkeypatch):
    fake_routes, patch_mod = fresh_csrf
    monkeypatch.setenv("FOX_PLANE_AUTH_SECRET", "test-secret")
    monkeypatch.setenv("HERMES_WEBUI_ALLOWED_ORIGINS", "https://test.example.com")
    patch_mod.apply()
    assert getattr(fake_routes._check_csrf, patch_mod._CHECK_CSRF_SENTINEL, False)


def test_apply_idempotent(fresh_csrf, monkeypatch):
    fake_routes, patch_mod = fresh_csrf
    monkeypatch.setenv("FOX_PLANE_AUTH_SECRET", "test-secret")
    monkeypatch.setenv("HERMES_WEBUI_ALLOWED_ORIGINS", "https://test.example.com")
    patch_mod.apply()
    patch_mod.apply()
    assert getattr(fake_routes._check_csrf, patch_mod._CHECK_CSRF_SENTINEL, False)


# ── Patched _check_csrf behavior ─────────────────────────────────────────────

def test_patched_csrf_bypassed_with_valid_auth(fresh_csrf, monkeypatch):
    """X-Fox-Auth valid → CSRF check returns True even without session cookie."""
    fake_routes, patch_mod = fresh_csrf
    monkeypatch.setenv("FOX_PLANE_AUTH_SECRET", "plane-secret")
    monkeypatch.setenv("HERMES_WEBUI_ALLOWED_ORIGINS", "https://test.example.com")
    patch_mod.apply()

    handler = _make_handler({
        "Origin": "https://test.example.com",
        "Host": "localhost:8787",
        "X-Fox-Auth": "plane-secret",
    })
    assert fake_routes._check_csrf(handler) is True
    assert handler._csrf_reason is None


def test_patched_csrf_fails_without_auth(fresh_csrf, monkeypatch):
    """No X-Fox-Auth → original CSRF token check runs (and fails: no session)."""
    fake_routes, patch_mod = fresh_csrf
    monkeypatch.setenv("FOX_PLANE_AUTH_SECRET", "plane-secret")
    monkeypatch.setenv("HERMES_WEBUI_ALLOWED_ORIGINS", "https://test.example.com")
    patch_mod.apply()

    handler = _make_handler({
        "Origin": "https://test.example.com",
        "Host": "localhost:8787",
    })
    assert fake_routes._check_csrf(handler) is False
    assert handler._csrf_reason == "token_mismatch"


def test_patched_csrf_fails_with_wrong_auth(fresh_csrf, monkeypatch):
    """Wrong X-Fox-Auth → bypass skipped, original CSRF token check runs."""
    fake_routes, patch_mod = fresh_csrf
    monkeypatch.setenv("FOX_PLANE_AUTH_SECRET", "plane-secret")
    monkeypatch.setenv("HERMES_WEBUI_ALLOWED_ORIGINS", "https://test.example.com")
    patch_mod.apply()

    handler = _make_handler({
        "Origin": "https://test.example.com",
        "Host": "localhost:8787",
        "X-Fox-Auth": "wrong-secret",
    })
    assert fake_routes._check_csrf(handler) is False
    assert handler._csrf_reason == "token_mismatch"


def test_patched_csrf_standalone_mode(fresh_csrf, monkeypatch):
    """No FOX_PLANE_AUTH_SECRET → bypass is no-op, original CSRF check runs."""
    fake_routes, patch_mod = fresh_csrf
    monkeypatch.delenv("FOX_PLANE_AUTH_SECRET", raising=False)
    monkeypatch.setenv("HERMES_WEBUI_ALLOWED_ORIGINS", "https://test.example.com")
    patch_mod.apply()

    handler = _make_handler({
        "Origin": "https://test.example.com",
        "Host": "localhost:8787",
    })
    assert fake_routes._check_csrf(handler) is False
    assert handler._csrf_reason == "token_mismatch"


def test_patched_csrf_non_browser_request_passes(fresh_csrf, monkeypatch):
    """Non-browser request (no Origin) → CSRF check returns True."""
    fake_routes, patch_mod = fresh_csrf
    monkeypatch.setenv("FOX_PLANE_AUTH_SECRET", "plane-secret")
    patch_mod.apply()

    handler = _make_handler({"Host": "localhost:8787"})
    assert fake_routes._check_csrf(handler) is True
