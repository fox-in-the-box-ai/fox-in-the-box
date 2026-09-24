"""Phase 7 regression tests for fox_overlay.webui_modules.onboarding.

Covers:
* 3 dispatcher registrations: GET /setup (allow_bare), GET /api/setup/, POST /api/setup/
* /setup wrapper boundary check (allow_bare)
* /api/setup/welcome routes to handle_setup_welcome
* POST /api/setup/{openrouter,complete,skip,restart} dispatch
* _write_env_key still importable (hostname coupling)

Behavioral parity for setup wizard is exercised by smoke checklist
Section B (full first-run wizard against real container).
"""

import importlib
import os
import sys

import pytest


@pytest.fixture
def fresh_dispatch_and_module(monkeypatch, tmp_path):
    """Reload dispatch + onboarding module so register_* fires fresh."""
    fake_helpers = type(sys)("api.helpers")

    def _j(handler, payload, status=200, extra_headers=None):
        handler.responses.append({"status": status, "payload": payload})

    def _read_body(handler):
        return getattr(handler, "_body", {})

    def _bad(handler, msg, status=400):
        _j(handler, {"error": msg}, status=status)

    fake_helpers.j = _j
    fake_helpers.read_body = _read_body
    fake_helpers.bad = _bad

    # onboarding.py imports `from api.config import load_settings` inside
    # onboarding_complete; stub that so the module loads.
    fake_config = type(sys)("api.config")
    fake_config.load_settings = lambda: {}

    fake_api = type(sys)("api")
    fake_api.helpers = fake_helpers
    fake_api.config = fake_config

    monkeypatch.setitem(sys.modules, "api", fake_api)
    monkeypatch.setitem(sys.modules, "api.helpers", fake_helpers)
    monkeypatch.setitem(sys.modules, "api.config", fake_config)

    # Redirect ONBOARDING_PATH + HERMES_ENV_PATH to tmp so tests don't write to /data
    monkeypatch.setenv("ONBOARDING_PATH", str(tmp_path / "onboarding.json"))
    monkeypatch.setenv("HERMES_ENV_PATH", str(tmp_path / "hermes.env"))

    import fox_overlay.dispatch as d

    importlib.reload(d)
    import fox_overlay.webui_modules.onboarding as m

    importlib.reload(m)
    yield d, m
    importlib.reload(d)
    importlib.reload(m)


class _FakeHandler:
    def __init__(self, body=None):
        self._body = body or {}
        self.responses = []
        # For handle_setup_page (sends raw bytes)
        self._written = []
        self._response_code = None
        self._headers = []

    def send_response(self, code):
        self._response_code = code

    def send_header(self, key, val):
        self._headers.append((key, val))

    def end_headers(self):
        pass

    @property
    def wfile(self):
        class _W:
            def write(_self, b):
                self._written.append(b)

        return _W()


# ── registration ────────────────────────────────────────────────────────────


def test_module_registers_setup_bare_get(fresh_dispatch_and_module):
    """/setup is registered with allow_bare=True."""
    d, _m = fresh_dispatch_and_module
    assert "/setup" in d.GET_TABLE


def test_module_registers_api_setup_get_and_post(fresh_dispatch_and_module):
    d, _m = fresh_dispatch_and_module
    assert "/api/setup/" in d.GET_TABLE
    assert "/api/setup/" in d.POST_TABLE


# ── /setup (GET, allow_bare) ───────────────────────────────────────────────


def test_get_setup_serves_html_when_file_exists(fresh_dispatch_and_module, monkeypatch):
    """handle_setup_page reads setup.html from overlay's webui_static."""
    d, m = fresh_dispatch_and_module
    # Stub handle_setup_page to just record the call (real one reads from disk)
    called = []

    def _stub(handler):
        called.append("page")
        handler.send_response(200)

    monkeypatch.setattr(m, "handle_setup_page", _stub)
    from urllib.parse import urlparse

    h = _FakeHandler()
    assert d.handle_get(h, urlparse("/setup")) is True
    assert called == ["page"]


def test_get_setup_boundary_rejects_adjacent(fresh_dispatch_and_module):
    """allow_bare contract: /setupX must NOT match (wrapper rejects)."""
    d, _m = fresh_dispatch_and_module
    from urllib.parse import urlparse

    h = _FakeHandler()
    assert d.handle_get(h, urlparse("/setupX")) is False
    assert d.handle_get(h, urlparse("/setup-other")) is False


# ── /api/setup/* (GET) ─────────────────────────────────────────────────────


def test_get_api_setup_welcome(fresh_dispatch_and_module, monkeypatch):
    d, m = fresh_dispatch_and_module
    monkeypatch.setattr(m, "handle_setup_welcome", lambda h: {"welcome": True})
    from urllib.parse import urlparse

    h = _FakeHandler()
    assert d.handle_get(h, urlparse("/api/setup/welcome")) is True
    assert h.responses[-1]["payload"] == {"welcome": True}


def test_get_api_setup_unknown_falls_through(fresh_dispatch_and_module):
    d, _m = fresh_dispatch_and_module
    from urllib.parse import urlparse

    h = _FakeHandler()
    assert d.handle_get(h, urlparse("/api/setup/nonexistent")) is False


# ── /api/setup/* (POST) ────────────────────────────────────────────────────


def test_post_api_setup_openrouter(fresh_dispatch_and_module, monkeypatch):
    d, m = fresh_dispatch_and_module
    captured = []
    monkeypatch.setattr(
        m,
        "handle_setup_openrouter",
        lambda h, body: captured.append(body) or {"ok": True},
    )
    from urllib.parse import urlparse

    h = _FakeHandler(body={"key": "sk-test"})
    assert d.handle_post(h, urlparse("/api/setup/openrouter")) is True
    assert captured == [{"key": "sk-test"}]


def test_post_api_setup_complete(fresh_dispatch_and_module, monkeypatch):
    d, m = fresh_dispatch_and_module
    monkeypatch.setattr(m, "handle_setup_complete", lambda h, body: {"ok": True})
    from urllib.parse import urlparse

    h = _FakeHandler(body={})
    assert d.handle_post(h, urlparse("/api/setup/complete")) is True


def test_post_api_setup_skip(fresh_dispatch_and_module, monkeypatch):
    d, m = fresh_dispatch_and_module
    monkeypatch.setattr(
        m, "handle_setup_skip", lambda h, body: {"ok": True, "skipped": True}
    )
    from urllib.parse import urlparse

    h = _FakeHandler(body={})
    assert d.handle_post(h, urlparse("/api/setup/skip")) is True


def test_post_api_setup_restart(fresh_dispatch_and_module, monkeypatch):
    d, m = fresh_dispatch_and_module
    monkeypatch.setattr(m, "handle_setup_restart", lambda h: {"ok": True})
    from urllib.parse import urlparse

    h = _FakeHandler(body={})
    assert d.handle_post(h, urlparse("/api/setup/restart")) is True


def test_post_api_setup_unknown_falls_through(fresh_dispatch_and_module):
    d, _m = fresh_dispatch_and_module
    from urllib.parse import urlparse

    h = _FakeHandler(body={})
    assert d.handle_post(h, urlparse("/api/setup/nonexistent")) is False


def test_post_api_setup_non_object_body_returns_400(fresh_dispatch_and_module):
    """#901: a valid-JSON non-object body yields a clean 400, not an
    AttributeError → HTTP 500."""
    d, _m = fresh_dispatch_and_module
    from urllib.parse import urlparse

    h = _FakeHandler(body=["x"])
    assert d.handle_post(h, urlparse("/api/setup/openrouter")) is True
    assert h.responses[-1]["status"] == 400


# ── _write_env_key re-export (hostname coupling) ───────────────────────────


def test_write_env_key_importable_from_overlay(fresh_dispatch_and_module):
    """hostname.py imports _write_env_key from this module — must be exposed."""
    _d, m = fresh_dispatch_and_module
    assert callable(getattr(m, "_write_env_key", None))


def test_write_env_key_writes_file(fresh_dispatch_and_module, tmp_path, monkeypatch):
    """Quick smoke that _write_env_key still functions."""
    _d, m = fresh_dispatch_and_module
    # Override module-level _ENV_PATH via attribute assignment (it's a module-level
    # Path at import — re-bind it for this test)
    m._ENV_PATH = tmp_path / "test.env"
    m._write_env_key("FOO", "bar")
    assert m._ENV_PATH.read_text().strip() == "FOO=bar"


# ── #899: env-injection rejection + 0600 mode ─────────────────────────────


@pytest.mark.parametrize(
    "bad_value", ["sk-a\nB=2", "sk-a\rB=2", "sk-a\x00B=2", "sk-a\tB=2"]
)
def test_write_env_key_rejects_control_chars_in_value(
    fresh_dispatch_and_module, tmp_path, bad_value
):
    """#899: a control char in the value would inject extra env lines."""
    _d, m = fresh_dispatch_and_module
    m._ENV_PATH = tmp_path / "test.env"
    with pytest.raises(ValueError):
        m._write_env_key("OPENROUTER_API_KEY", bad_value)
    assert not m._ENV_PATH.exists()  # nothing written


def test_openrouter_rejects_newline_injection(fresh_dispatch_and_module, tmp_path):
    """#899 repro: sk-…\\nFOX_EVIL=1 is rejected and writes zero extra lines."""
    _d, m = fresh_dispatch_and_module
    m._ENV_PATH = tmp_path / "hermes.env"
    result = m.handle_setup_openrouter(
        _FakeHandler(), {"key": "sk-" + "a" * 20 + "\nFOX_EVIL_INJECTED=1\nMORE=2"}
    )
    assert result["ok"] is False
    assert "FOX_EVIL_INJECTED" not in result["error"]  # error must not echo the key
    assert not m._ENV_PATH.exists()


def test_openrouter_valid_key_writes_single_line(fresh_dispatch_and_module, tmp_path):
    """Regression: a clean key still saves exactly one line."""
    _d, m = fresh_dispatch_and_module
    m._ENV_PATH = tmp_path / "hermes.env"
    key = "sk-" + "a" * 20
    result = m.handle_setup_openrouter(_FakeHandler(), {"key": key})
    assert result["ok"] is True
    assert m._ENV_PATH.read_text().strip() == f"OPENROUTER_API_KEY={key}"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX mode bits only")
def test_write_env_key_sets_0600(fresh_dispatch_and_module, tmp_path):
    """#899: the provider-secret file is written owner-only."""
    import stat

    _d, m = fresh_dispatch_and_module
    m._ENV_PATH = tmp_path / "hermes.env"
    m._write_env_key("OPENROUTER_API_KEY", "sk-value")
    assert stat.S_IMODE(m._ENV_PATH.stat().st_mode) == 0o600


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX mode bits only")
def test_write_env_key_new_file_created_0600_no_window(
    fresh_dispatch_and_module, tmp_path, monkeypatch
):
    """#899: the NEW-file path must create the secret file 0600 from the first
    byte — never a 0644 window before a follow-up chmod. Assert the create
    (O_CREAT) call passes mode 0600, and the final file is 0600."""
    import stat

    _d, m = fresh_dispatch_and_module
    m._ENV_PATH = tmp_path / "hermes.env"

    captured = {}
    real_open = os.open

    def _spy_open(path, flags, mode=0o777, *a, **kw):
        if flags & os.O_CREAT:
            captured["mode"] = mode
        return real_open(path, flags, mode, *a, **kw)

    monkeypatch.setattr(m.os, "open", _spy_open)
    m._write_env_key("OPENROUTER_API_KEY", "sk-value")

    assert captured.get("mode") == 0o600
    assert stat.S_IMODE(m._ENV_PATH.stat().st_mode) == 0o600


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX mode bits only")
def test_write_env_key_self_heals_0644_to_0600(fresh_dispatch_and_module, tmp_path):
    """#899: a pre-existing world-readable file is normalized on next write."""
    import stat

    _d, m = fresh_dispatch_and_module
    m._ENV_PATH = tmp_path / "hermes.env"
    m._ENV_PATH.write_text("FOX_HOSTNAME=fox-clever\n", encoding="utf-8")
    m._ENV_PATH.chmod(0o644)
    m._write_env_key("OPENROUTER_API_KEY", "sk-value")
    assert stat.S_IMODE(m._ENV_PATH.stat().st_mode) == 0o600
    # existing key preserved
    assert "FOX_HOSTNAME=fox-clever" in m._ENV_PATH.read_text()
