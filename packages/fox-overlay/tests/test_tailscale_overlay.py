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


# ── v0.7.12 #146: sticky auth_url + cleared flag ────────────────────────────
# The disappearing-link bug is a transient empty-auth_url window during the
# awaiting-auth state — daemon scrape returning briefly empty, or a stale
# poll racing a fresh attempt's reset. Server-side sticky `last_auth_url`
# rides out those gaps so the client always sees a stable URL until the
# attempt is genuinely terminal.

def test_set_up_state_populates_last_auth_url(fresh_dispatch_and_module):
    _d, m = fresh_dispatch_and_module
    # Establish a current attempt.
    m._up_state["attempt_id"] = 1
    m._up_state["state"] = "starting"
    m._up_state["auth_url"] = ""
    m._up_state["last_auth_url"] = ""

    m._set_up_state(attempt_id=1, state="awaiting-auth", auth_url="https://login.tailscale.com/abc123")

    assert m._up_state["auth_url"] == "https://login.tailscale.com/abc123"
    assert m._up_state["last_auth_url"] == "https://login.tailscale.com/abc123"


def test_set_up_state_does_not_overwrite_last_auth_url_with_empty(fresh_dispatch_and_module):
    """A stale or transient daemon update that sets auth_url='' must NOT
    clear the sticky last_auth_url — that's exactly the race we're fixing."""
    _d, m = fresh_dispatch_and_module
    m._up_state["attempt_id"] = 1
    m._up_state["state"] = "awaiting-auth"
    m._up_state["auth_url"] = "https://login.tailscale.com/abc123"
    m._up_state["last_auth_url"] = "https://login.tailscale.com/abc123"

    # Simulate the racy update that was clobbering the link in Safari
    m._set_up_state(attempt_id=1, auth_url="")

    # auth_url got cleared (caller asked), BUT sticky survives.
    assert m._up_state["auth_url"] == ""
    assert m._up_state["last_auth_url"] == "https://login.tailscale.com/abc123"


def test_get_up_progress_returns_last_auth_url_when_current_is_empty(fresh_dispatch_and_module, monkeypatch):
    """The whole point: poll responses must keep delivering the URL even
    when auth_url has been transiently blanked."""
    _d, m = fresh_dispatch_and_module
    # Stub get_status so we don't actually call tailscale CLI.
    monkeypatch.setattr(m, "get_status", lambda: {"backend_state": "NeedsLogin"})
    m._up_state["state"] = "awaiting-auth"
    m._up_state["auth_url"] = ""  # transient blank
    m._up_state["last_auth_url"] = "https://login.tailscale.com/abc123"
    m._up_state["attempt_id"] = 1

    resp = m.get_up_progress()
    assert resp["auth_url"] == "https://login.tailscale.com/abc123"
    assert resp["cleared"] is False  # not terminal, link should be kept rendered


def test_get_up_progress_clears_auth_url_on_running_state(fresh_dispatch_and_module, monkeypatch):
    """Once the attempt succeeds (state=running), the link should disappear
    from the poll response — its job is over and showing it would confuse."""
    _d, m = fresh_dispatch_and_module
    monkeypatch.setattr(m, "get_status", lambda: {"backend_state": "Running"})
    m._up_state["state"] = "running"
    m._up_state["auth_url"] = ""
    m._up_state["last_auth_url"] = "https://login.tailscale.com/abc123"  # leftover from awaiting-auth
    m._up_state["attempt_id"] = 1

    resp = m.get_up_progress()
    assert resp["auth_url"] == ""  # terminal state → clear
    assert resp["cleared"] is True


def test_get_up_progress_clears_auth_url_on_failed_state(fresh_dispatch_and_module, monkeypatch):
    """Same for failed — link is no longer actionable, error is what the user needs."""
    _d, m = fresh_dispatch_and_module
    monkeypatch.setattr(m, "get_status", lambda: {"backend_state": "NoState"})
    m._up_state["state"] = "failed"
    m._up_state["auth_url"] = ""
    m._up_state["last_auth_url"] = "https://login.tailscale.com/abc123"
    m._up_state["error"] = "auth timed out"
    m._up_state["attempt_id"] = 1

    resp = m.get_up_progress()
    assert resp["auth_url"] == ""
    assert resp["cleared"] is True
    assert resp["error"] == "auth timed out"


def test_get_up_progress_preserves_auth_url_through_state_promotion(fresh_dispatch_and_module, monkeypatch):
    """When get_up_progress promotes awaiting-auth → running mid-poll (via
    the get_status BackendState check), the auth_url field in the response
    should clear cleanly. Important because that's the natural success
    transition — link served, user clicked, daemon became Running."""
    _d, m = fresh_dispatch_and_module
    # Daemon is now Running — get_up_progress will promote state.
    monkeypatch.setattr(m, "get_status", lambda: {"backend_state": "Running"})
    monkeypatch.setattr(m, "_attempt_configure_serve", lambda _aid: None)
    m._up_state["state"] = "awaiting-auth"
    m._up_state["auth_url"] = "https://login.tailscale.com/abc123"
    m._up_state["last_auth_url"] = "https://login.tailscale.com/abc123"
    m._up_state["attempt_id"] = 1

    resp = m.get_up_progress()
    # State got promoted to running, link cleared (job done).
    assert resp["state"] == "running"
    assert resp["auth_url"] == ""
    assert resp["cleared"] is True


def test_get_up_progress_includes_cleared_field_for_all_responses(fresh_dispatch_and_module, monkeypatch):
    """Defensive: every response shape must include the `cleared` field so
    clients can rely on its presence without conditional checks."""
    _d, m = fresh_dispatch_and_module
    monkeypatch.setattr(m, "get_status", lambda: {"backend_state": "NoState"})
    m._up_state["state"] = "idle"
    m._up_state["auth_url"] = ""
    m._up_state["last_auth_url"] = ""
    m._up_state["attempt_id"] = 0

    resp = m.get_up_progress()
    assert "cleared" in resp
    assert resp["cleared"] is True  # idle is terminal-ish
