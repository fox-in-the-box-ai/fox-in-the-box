"""Phase 5 regression tests for fox_overlay.webui_modules.hostname.

Uses dispatch.register_*(allow_bare=True). Tests verify both the bare
endpoint (/api/settings/hostname GET + POST) and the sub-path
(/api/settings/hostname/dismiss-prompt POST), plus boundary checks.
"""
import importlib
import sys

import pytest


@pytest.fixture
def fresh_dispatch_and_module(monkeypatch):
    """Reload dispatch + hostname module so register_* fires fresh.

    hostname.py imports from api.helpers AND api.onboarding (the latter
    is Fox's setup-wizard module). Stub both.
    """
    fake_helpers = type(sys)("api.helpers")
    def _j(handler, payload, status=200, extra_headers=None):
        handler.responses.append({"status": status, "payload": payload})
    def _read_body(handler):
        return getattr(handler, "_body", {})
    fake_helpers.j = _j
    fake_helpers.read_body = _read_body

    fake_onboarding = type(sys)("api.onboarding")
    fake_onboarding._write_env_key = lambda *a, **kw: None

    fake_api = type(sys)("api")
    fake_api.helpers = fake_helpers
    fake_api.onboarding = fake_onboarding

    monkeypatch.setitem(sys.modules, "api", fake_api)
    monkeypatch.setitem(sys.modules, "api.helpers", fake_helpers)
    monkeypatch.setitem(sys.modules, "api.onboarding", fake_onboarding)

    import fox_overlay.dispatch as d
    importlib.reload(d)
    import fox_overlay.webui_modules.hostname as m
    importlib.reload(m)
    yield d, m
    importlib.reload(d)
    importlib.reload(m)


class _FakeHandler:
    def __init__(self, body=None):
        self._body = body or {}
        self.responses = []


# ── registration ────────────────────────────────────────────────────────────

def test_module_registers_bare_prefix(fresh_dispatch_and_module):
    """Bare prefix /api/settings/hostname (allow_bare=True)."""
    d, _m = fresh_dispatch_and_module
    assert "/api/settings/hostname" in d.GET_TABLE
    assert "/api/settings/hostname" in d.POST_TABLE


# ── GET routing ─────────────────────────────────────────────────────────────

def test_get_bare_path_routes_to_get_hostname(fresh_dispatch_and_module, monkeypatch):
    d, m = fresh_dispatch_and_module
    monkeypatch.setattr(m, "handle_get_hostname", lambda h: {"hostname": "fox-host"})
    from urllib.parse import urlparse
    h = _FakeHandler()
    assert d.handle_get(h, urlparse("/api/settings/hostname")) is True
    assert h.responses[-1]["payload"] == {"hostname": "fox-host"}


def test_get_unknown_subpath_falls_through(fresh_dispatch_and_module):
    """GET on dismiss-prompt (POST-only) → False."""
    d, _m = fresh_dispatch_and_module
    from urllib.parse import urlparse
    h = _FakeHandler()
    assert d.handle_get(h, urlparse("/api/settings/hostname/dismiss-prompt")) is False
    assert d.handle_get(h, urlparse("/api/settings/hostname/anything")) is False


# ── POST routing ────────────────────────────────────────────────────────────

def test_post_set_hostname_ok(fresh_dispatch_and_module, monkeypatch):
    d, m = fresh_dispatch_and_module
    monkeypatch.setattr(m, "handle_set_hostname", lambda h, body: {"ok": True, "hostname": body["hostname"]})
    from urllib.parse import urlparse
    h = _FakeHandler(body={"hostname": "fox-prod"})
    assert d.handle_post(h, urlparse("/api/settings/hostname")) is True
    assert h.responses[-1] == {"status": 200, "payload": {"ok": True, "hostname": "fox-prod"}}


def test_post_set_hostname_failure_status_400(fresh_dispatch_and_module, monkeypatch):
    d, m = fresh_dispatch_and_module
    monkeypatch.setattr(m, "handle_set_hostname", lambda h, body: {"ok": False, "error": "invalid"})
    from urllib.parse import urlparse
    h = _FakeHandler(body={"hostname": "INVALID..."})
    assert d.handle_post(h, urlparse("/api/settings/hostname")) is True
    assert h.responses[-1]["status"] == 400


def test_post_dismiss_prompt_ok(fresh_dispatch_and_module, monkeypatch):
    d, m = fresh_dispatch_and_module
    monkeypatch.setattr(m, "handle_dismiss_hostname_prompt", lambda h, body: {"ok": True, "prompted": True})
    from urllib.parse import urlparse
    h = _FakeHandler(body={})
    assert d.handle_post(h, urlparse("/api/settings/hostname/dismiss-prompt")) is True
    assert h.responses[-1]["status"] == 200


def test_post_unknown_subpath_falls_through(fresh_dispatch_and_module):
    d, _m = fresh_dispatch_and_module
    from urllib.parse import urlparse
    h = _FakeHandler()
    assert d.handle_post(h, urlparse("/api/settings/hostname/wrong-thing")) is False


# ── prefix-boundary safety (allow_bare requires explicit boundary check) ───

def test_boundary_rejects_adjacent_paths(fresh_dispatch_and_module):
    d, _m = fresh_dispatch_and_module
    from urllib.parse import urlparse
    h = _FakeHandler()
    assert d.handle_get(h, urlparse("/api/settings/hostnameX")) is False
    assert d.handle_get(h, urlparse("/api/settings/hostnameattack")) is False
    assert d.handle_post(h, urlparse("/api/settings/hostname-other")) is False
