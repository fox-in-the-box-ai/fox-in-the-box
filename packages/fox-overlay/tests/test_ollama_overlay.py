"""Phase 5 regression tests for fox_overlay.webui_modules.ollama.

Covers the dispatcher integration shape only — the underlying Ollama
HTTP probing / pull / delete logic is exercised by the smoke checklist
Sections D5-D7 against a real Ollama daemon (per migration plan
§Validation gates).

These tests prove:
* Module-load registers /api/ollama/ at the dispatcher.
* GET/POST sub-dispatch routes to the right inner handler.
* Unknown sub-paths under /api/ollama/ return False (dispatcher falls
  through; routes.py 404s — same as pre-migration).
"""
import importlib
import sys

import pytest


@pytest.fixture
def fresh_dispatch_and_module(monkeypatch):
    """Reload dispatch + ollama module so register_* fires fresh.

    Patches api.helpers so we don't need a real hermes-webui install in
    test environment — the module imports `j` and `read_body` from there.
    """
    # Stub api.helpers BEFORE importing ollama (which does `from api.helpers ...`)
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

    # Reset dispatch
    import fox_overlay.dispatch as d
    importlib.reload(d)
    # Reload ollama module so its register_* fires against the fresh table
    import fox_overlay.webui_modules.ollama as m
    importlib.reload(m)
    yield d, m
    # Reload BOTH on teardown so the next test (with/without this fixture)
    # sees consistent state. Reloading dispatch alone would leave ollama's
    # module-level reference pointing at the previous (now-stale) GET/POST
    # tables, and the next dispatch call from inside ollama would silently
    # use the wrong table.
    importlib.reload(d)
    importlib.reload(m)


class _FakeHandler:
    def __init__(self, body=None):
        self._body = body or {}
        self.responses = []


# ── registration ────────────────────────────────────────────────────────────

def test_module_registers_get_and_post(fresh_dispatch_and_module):
    d, _m = fresh_dispatch_and_module
    assert "/api/ollama/" in d.GET_TABLE
    assert "/api/ollama/" in d.POST_TABLE


# ── GET routing ─────────────────────────────────────────────────────────────

def test_get_status_routes_to_handle_get_status(fresh_dispatch_and_module, monkeypatch):
    d, m = fresh_dispatch_and_module
    monkeypatch.setattr(m, "handle_get_status", lambda h: {"ollama": "ok"})
    from urllib.parse import urlparse
    h = _FakeHandler()
    assert d.handle_get(h, urlparse("/api/ollama/status")) is True
    assert h.responses == [{"status": 200, "payload": {"ollama": "ok"}}]


def test_get_models_routes_to_handle_get_models(fresh_dispatch_and_module, monkeypatch):
    d, m = fresh_dispatch_and_module
    monkeypatch.setattr(m, "handle_get_models", lambda h: {"models": []})
    from urllib.parse import urlparse
    h = _FakeHandler()
    assert d.handle_get(h, urlparse("/api/ollama/models")) is True
    assert h.responses[-1]["payload"] == {"models": []}


def test_get_unknown_subpath_falls_through(fresh_dispatch_and_module):
    """Unknown /api/ollama/* GET returns False — dispatcher continues, upstream 404s."""
    d, _m = fresh_dispatch_and_module
    from urllib.parse import urlparse
    h = _FakeHandler()
    # /api/ollama/nonexistent — overlay declines, dispatcher returns False overall
    assert d.handle_get(h, urlparse("/api/ollama/nonexistent")) is False
    assert h.responses == []


# ── POST routing ────────────────────────────────────────────────────────────

def test_post_refresh_routes_to_handle_post_refresh(fresh_dispatch_and_module, monkeypatch):
    d, m = fresh_dispatch_and_module
    monkeypatch.setattr(m, "handle_post_refresh", lambda h: {"refreshed": True})
    from urllib.parse import urlparse
    h = _FakeHandler()
    assert d.handle_post(h, urlparse("/api/ollama/refresh")) is True
    assert h.responses[-1]["payload"] == {"refreshed": True}


def test_post_use_model_ok_status_200(fresh_dispatch_and_module, monkeypatch):
    d, m = fresh_dispatch_and_module
    monkeypatch.setattr(m, "handle_post_use_model", lambda h, body: {"ok": True, "model": body["model"]})
    from urllib.parse import urlparse
    h = _FakeHandler(body={"model": "llama3"})
    assert d.handle_post(h, urlparse("/api/ollama/use-model")) is True
    assert h.responses == [{"status": 200, "payload": {"ok": True, "model": "llama3"}}]


def test_post_use_model_failure_status_400(fresh_dispatch_and_module, monkeypatch):
    d, m = fresh_dispatch_and_module
    monkeypatch.setattr(m, "handle_post_use_model", lambda h, body: {"ok": False, "error": "no such model"})
    from urllib.parse import urlparse
    h = _FakeHandler(body={"model": "bogus"})
    assert d.handle_post(h, urlparse("/api/ollama/use-model")) is True
    assert h.responses == [{"status": 400, "payload": {"ok": False, "error": "no such model"}}]


def test_post_pull_calls_stream_pull(fresh_dispatch_and_module, monkeypatch):
    """stream_pull manages its own SSE response — wrapper just calls + returns True."""
    d, m = fresh_dispatch_and_module
    calls = []
    monkeypatch.setattr(m, "stream_pull", lambda h, name: calls.append(name))
    from urllib.parse import urlparse
    h = _FakeHandler(body={"model": "qwen2:1.5b"})
    assert d.handle_post(h, urlparse("/api/ollama/pull")) is True
    assert calls == ["qwen2:1.5b"]
    # stream_pull owns the response, no j() wrapping
    assert h.responses == []


def test_post_delete_ok_status_200(fresh_dispatch_and_module, monkeypatch):
    d, m = fresh_dispatch_and_module
    monkeypatch.setattr(m, "delete_model", lambda name: {"ok": True, "deleted": name})
    from urllib.parse import urlparse
    h = _FakeHandler(body={"model": "llama3"})
    assert d.handle_post(h, urlparse("/api/ollama/delete")) is True
    assert h.responses[-1] == {"status": 200, "payload": {"ok": True, "deleted": "llama3"}}


def test_post_delete_failure_status_400(fresh_dispatch_and_module, monkeypatch):
    d, m = fresh_dispatch_and_module
    monkeypatch.setattr(m, "delete_model", lambda name: {"ok": False, "error": "in use"})
    from urllib.parse import urlparse
    h = _FakeHandler(body={"model": "in-use"})
    assert d.handle_post(h, urlparse("/api/ollama/delete")) is True
    assert h.responses[-1]["status"] == 400


def test_post_unknown_subpath_falls_through(fresh_dispatch_and_module):
    d, _m = fresh_dispatch_and_module
    from urllib.parse import urlparse
    h = _FakeHandler()
    assert d.handle_post(h, urlparse("/api/ollama/nonexistent")) is False


# ── prefix-boundary safety ──────────────────────────────────────────────────

def test_prefix_does_not_match_adjacent_paths(fresh_dispatch_and_module):
    """Dispatcher must NOT match /api/ollamaX/... or /api/ollamax."""
    d, _m = fresh_dispatch_and_module
    from urllib.parse import urlparse
    h = _FakeHandler()
    # "/api/ollamax" doesn't start with "/api/ollama/" → no match
    assert d.handle_get(h, urlparse("/api/ollamax")) is False
    assert d.handle_get(h, urlparse("/api/ollama-cloud/status")) is False
