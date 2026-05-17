"""Phase 5 regression tests for fox_overlay.webui_modules.local_fallback.

Covers dispatcher wrapper shape + the mixed status-code semantics
inherited from pre-migration routes.py:
  /enable, /disable → default 200 (no ok-check)
  /activate → 200 if result.get("ok") else 400
"""
import importlib
import sys

import pytest


@pytest.fixture
def fresh_dispatch_and_module(monkeypatch):
    """Reload dispatch + local_fallback module so register_* fires fresh."""
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
    import fox_overlay.webui_modules.local_fallback as m
    importlib.reload(m)
    yield d, m
    importlib.reload(d)
    importlib.reload(m)


class _FakeHandler:
    def __init__(self, body=None):
        self._body = body or {}
        self.responses = []


# ── registration ────────────────────────────────────────────────────────────

def test_module_registers_get_and_post(fresh_dispatch_and_module):
    d, _m = fresh_dispatch_and_module
    assert "/api/local-fallback/" in d.GET_TABLE
    assert "/api/local-fallback/" in d.POST_TABLE


# ── GET routing ─────────────────────────────────────────────────────────────

def test_get_status(fresh_dispatch_and_module, monkeypatch):
    d, m = fresh_dispatch_and_module
    monkeypatch.setattr(m, "handle_get_status", lambda h: {"enabled": False, "ready": False})
    from urllib.parse import urlparse
    h = _FakeHandler()
    assert d.handle_get(h, urlparse("/api/local-fallback/status")) is True
    assert h.responses[-1]["payload"] == {"enabled": False, "ready": False}


def test_get_remote_health(fresh_dispatch_and_module, monkeypatch):
    d, m = fresh_dispatch_and_module
    monkeypatch.setattr(m, "handle_get_remote_health", lambda h: {"healthy": True})
    from urllib.parse import urlparse
    h = _FakeHandler()
    assert d.handle_get(h, urlparse("/api/local-fallback/remote-health")) is True
    assert h.responses[-1]["payload"] == {"healthy": True}


def test_get_unknown_subpath_falls_through(fresh_dispatch_and_module):
    d, _m = fresh_dispatch_and_module
    from urllib.parse import urlparse
    h = _FakeHandler()
    assert d.handle_get(h, urlparse("/api/local-fallback/nonexistent")) is False


# ── POST routing — note the mixed status-code semantics ────────────────────

def test_post_enable_returns_200_regardless_of_ok(fresh_dispatch_and_module, monkeypatch):
    """Pre-migration parity: /enable always 200, even if result.ok=False."""
    d, m = fresh_dispatch_and_module
    monkeypatch.setattr(m, "handle_post_enable", lambda h, body: {"ok": False, "error": "missing binary"})
    from urllib.parse import urlparse
    h = _FakeHandler(body={})
    assert d.handle_post(h, urlparse("/api/local-fallback/enable")) is True
    assert h.responses[-1]["status"] == 200  # NOT 400 — pre-migration always-200


def test_post_disable_returns_200_regardless_of_ok(fresh_dispatch_and_module, monkeypatch):
    d, m = fresh_dispatch_and_module
    monkeypatch.setattr(m, "handle_post_disable", lambda h, body: {"ok": False, "error": "not enabled"})
    from urllib.parse import urlparse
    h = _FakeHandler(body={})
    assert d.handle_post(h, urlparse("/api/local-fallback/disable")) is True
    assert h.responses[-1]["status"] == 200  # NOT 400


def test_post_activate_ok_status_200(fresh_dispatch_and_module, monkeypatch):
    d, m = fresh_dispatch_and_module
    monkeypatch.setattr(m, "handle_post_activate", lambda h, body: {"ok": True, "model": "llama"})
    from urllib.parse import urlparse
    h = _FakeHandler(body={})
    assert d.handle_post(h, urlparse("/api/local-fallback/activate")) is True
    assert h.responses[-1]["status"] == 200


def test_post_activate_failure_status_400(fresh_dispatch_and_module, monkeypatch):
    """/activate IS ok-checked — pre-migration uses standard pattern."""
    d, m = fresh_dispatch_and_module
    monkeypatch.setattr(m, "handle_post_activate", lambda h, body: {"ok": False, "error": "no model"})
    from urllib.parse import urlparse
    h = _FakeHandler(body={})
    assert d.handle_post(h, urlparse("/api/local-fallback/activate")) is True
    assert h.responses[-1]["status"] == 400


def test_post_unknown_subpath_falls_through(fresh_dispatch_and_module):
    d, _m = fresh_dispatch_and_module
    from urllib.parse import urlparse
    h = _FakeHandler()
    assert d.handle_post(h, urlparse("/api/local-fallback/nonexistent")) is False


# ── prefix-boundary safety ──────────────────────────────────────────────────

def test_prefix_does_not_match_adjacent_paths(fresh_dispatch_and_module):
    d, _m = fresh_dispatch_and_module
    from urllib.parse import urlparse
    h = _FakeHandler()
    assert d.handle_get(h, urlparse("/api/local-fallbackx")) is False
    assert d.handle_get(h, urlparse("/api/local-fallback-x/status")) is False
