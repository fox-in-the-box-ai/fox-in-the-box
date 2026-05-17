"""Phase 5 regression tests for fox_overlay.webui_modules.tailscale.

Covers the dispatcher integration shape only — the underlying
tailscale subprocess / state / serve-config logic is exercised by the
smoke checklist Section E against a real tailscaled (per migration
plan §Validation gates).
"""
import importlib
import sys

import pytest


@pytest.fixture
def fresh_dispatch_and_module(monkeypatch):
    """Reload dispatch + tailscale module so register_* fires fresh."""
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
    import fox_overlay.webui_modules.tailscale as m
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
    assert "/api/tailscale/" in d.GET_TABLE
    assert "/api/tailscale/" in d.POST_TABLE


# ── GET routing ─────────────────────────────────────────────────────────────

def test_get_status(fresh_dispatch_and_module, monkeypatch):
    d, m = fresh_dispatch_and_module
    monkeypatch.setattr(m, "handle_get_status", lambda h: {"installed": True, "running": False})
    from urllib.parse import urlparse
    h = _FakeHandler()
    assert d.handle_get(h, urlparse("/api/tailscale/status")) is True
    assert h.responses == [{"status": 200, "payload": {"installed": True, "running": False}}]


def test_get_up_poll(fresh_dispatch_and_module, monkeypatch):
    d, m = fresh_dispatch_and_module
    monkeypatch.setattr(m, "handle_get_up_poll", lambda h: {"state": "running"})
    from urllib.parse import urlparse
    h = _FakeHandler()
    assert d.handle_get(h, urlparse("/api/tailscale/up/poll")) is True
    assert h.responses[-1]["payload"] == {"state": "running"}


def test_get_serve(fresh_dispatch_and_module, monkeypatch):
    d, m = fresh_dispatch_and_module
    monkeypatch.setattr(m, "handle_get_serve", lambda h: {"serving": True, "url": "https://fox.example.ts.net"})
    from urllib.parse import urlparse
    h = _FakeHandler()
    assert d.handle_get(h, urlparse("/api/tailscale/serve")) is True
    assert h.responses[-1]["payload"]["serving"] is True


def test_get_unknown_subpath_falls_through(fresh_dispatch_and_module):
    d, _m = fresh_dispatch_and_module
    from urllib.parse import urlparse
    h = _FakeHandler()
    assert d.handle_get(h, urlparse("/api/tailscale/nonexistent")) is False
    assert h.responses == []


# ── POST routing ────────────────────────────────────────────────────────────

def test_post_up_ok_status_200(fresh_dispatch_and_module, monkeypatch):
    d, m = fresh_dispatch_and_module
    monkeypatch.setattr(m, "handle_post_up", lambda h, body: {"ok": True, "attempt_id": 7})
    from urllib.parse import urlparse
    h = _FakeHandler(body={"hostname": "fox-test"})
    assert d.handle_post(h, urlparse("/api/tailscale/up")) is True
    assert h.responses[-1]["status"] == 200


def test_post_up_failure_status_400(fresh_dispatch_and_module, monkeypatch):
    d, m = fresh_dispatch_and_module
    monkeypatch.setattr(m, "handle_post_up", lambda h, body: {"ok": False, "error": "invalid hostname"})
    from urllib.parse import urlparse
    h = _FakeHandler(body={"hostname": ""})
    assert d.handle_post(h, urlparse("/api/tailscale/up")) is True
    assert h.responses[-1]["status"] == 400


def test_post_logout(fresh_dispatch_and_module, monkeypatch):
    d, m = fresh_dispatch_and_module
    monkeypatch.setattr(m, "handle_post_logout", lambda h, body: {"ok": True})
    from urllib.parse import urlparse
    h = _FakeHandler(body={})
    assert d.handle_post(h, urlparse("/api/tailscale/logout")) is True
    assert h.responses[-1] == {"status": 200, "payload": {"ok": True}}


def test_post_serve_ok(fresh_dispatch_and_module, monkeypatch):
    d, m = fresh_dispatch_and_module
    monkeypatch.setattr(m, "handle_post_serve", lambda h, body: {"ok": True, "url": "https://fox.example.ts.net"})
    from urllib.parse import urlparse
    h = _FakeHandler(body={})
    assert d.handle_post(h, urlparse("/api/tailscale/serve")) is True
    assert h.responses[-1]["status"] == 200


def test_post_serve_failure(fresh_dispatch_and_module, monkeypatch):
    d, m = fresh_dispatch_and_module
    monkeypatch.setattr(m, "handle_post_serve", lambda h, body: {"ok": False, "error": "tailscale not running"})
    from urllib.parse import urlparse
    h = _FakeHandler(body={})
    assert d.handle_post(h, urlparse("/api/tailscale/serve")) is True
    assert h.responses[-1]["status"] == 400


def test_post_unknown_subpath_falls_through(fresh_dispatch_and_module):
    d, _m = fresh_dispatch_and_module
    from urllib.parse import urlparse
    h = _FakeHandler()
    assert d.handle_post(h, urlparse("/api/tailscale/nonexistent")) is False


# ── prefix-boundary safety ──────────────────────────────────────────────────

def test_prefix_does_not_match_adjacent_paths(fresh_dispatch_and_module):
    d, _m = fresh_dispatch_and_module
    from urllib.parse import urlparse
    h = _FakeHandler()
    assert d.handle_get(h, urlparse("/api/tailscalex/status")) is False
    assert d.handle_get(h, urlparse("/api/tailscale-other/status")) is False
