"""Tests for fox_overlay.webui_modules.readyz — /readyz endpoint (INST-01)."""
from __future__ import annotations

import json
import sys
import types
from types import SimpleNamespace
from unittest import mock

import pytest


# ── Upstream stubs (no real hermes-webui in test environment) ──────────

def _stub_upstream():
    """Inject minimal api.auth, api.config, api.helpers stubs."""
    api = types.ModuleType("api")
    auth = types.ModuleType("api.auth")
    auth.PUBLIC_PATHS = frozenset({"/login", "/health"})
    config = types.ModuleType("api.config")
    config.load_settings = lambda: {"theme": "dark"}
    helpers = types.ModuleType("api.helpers")

    def _j(handler, data, status=200):
        body = json.dumps(data).encode()
        handler.send_response(status)
        handler.send_header("Content-Type", "application/json")
        handler.end_headers()
        handler._body = body

    helpers.j = _j
    api.auth = auth
    api.config = config
    api.helpers = helpers
    sys.modules.setdefault("api", api)
    sys.modules.setdefault("api.auth", auth)
    sys.modules.setdefault("api.config", config)
    sys.modules.setdefault("api.helpers", helpers)
    return auth


@pytest.fixture(autouse=True)
def _upstream(monkeypatch):
    _stub_upstream()
    # Reset PUBLIC_PATHS on the actual module in sys.modules so
    # expansion tests see the before state.
    auth = sys.modules["api.auth"]
    auth.PUBLIC_PATHS = frozenset({"/login", "/health"})
    # Reset dispatch state so each test starts clean.
    from fox_overlay import dispatch
    dispatch._GET_TABLE.clear()
    dispatch._POST_TABLE.clear()
    dispatch._BootstrapState.frozen = False
    yield auth
    # Clean up readyz module so next test re-imports fresh.
    sys.modules.pop("fox_overlay.webui_modules.readyz", None)


def _load_readyz():
    """(Re)import the readyz module, triggering registration."""
    sys.modules.pop("fox_overlay.webui_modules.readyz", None)
    import fox_overlay.webui_modules as _pkg
    if hasattr(_pkg, "readyz"):
        delattr(_pkg, "readyz")
    from fox_overlay.webui_modules import readyz
    return readyz


def _make_handler():
    """Minimal handler stub with send_response / send_header / end_headers."""
    h = SimpleNamespace()
    h._headers_sent = []
    h._body = None
    h._status = None
    h.send_response = lambda status: setattr(h, "_status", status)
    h.send_header = lambda k, v: h._headers_sent.append((k, v))
    h.end_headers = lambda: None
    return h


def _parsed(path):
    return SimpleNamespace(path=path)


# ── Registration tests ─────────────────────────────────────────────────

class TestRegistration:
    def test_registers_get_handler(self):
        _load_readyz()
        from fox_overlay.dispatch import GET_TABLE
        assert "/readyz" in GET_TABLE

    def test_no_post_handler(self):
        _load_readyz()
        from fox_overlay.dispatch import POST_TABLE
        assert "/readyz" not in POST_TABLE

    def test_expands_public_paths(self):
        auth_mod = sys.modules["api.auth"]
        assert "/readyz" not in auth_mod.PUBLIC_PATHS
        _load_readyz()
        assert "/readyz" in auth_mod.PUBLIC_PATHS

    def test_preserves_existing_public_paths(self):
        _load_readyz()
        auth_mod = sys.modules["api.auth"]
        assert "/login" in auth_mod.PUBLIC_PATHS
        assert "/health" in auth_mod.PUBLIC_PATHS


# ── Handler tests ──────────────────────────────────────────────────────

class TestHandler:
    def test_handles_readyz_path(self):
        readyz = _load_readyz()
        handler = _make_handler()
        result = readyz._handle_get(handler, _parsed("/readyz"))
        assert result is True

    def test_declines_non_readyz(self):
        readyz = _load_readyz()
        handler = _make_handler()
        assert readyz._handle_get(handler, _parsed("/readyzXYZ")) is False
        assert readyz._handle_get(handler, _parsed("/readyz/extra")) is False
        assert readyz._handle_get(handler, _parsed("/health")) is False

    def test_response_shape(self):
        readyz = _load_readyz()
        handler = _make_handler()
        with mock.patch.object(readyz, "get_readiness", return_value={
            "ready": True,
            "checks": {"http_server": {"ok": True}},
        }):
            readyz._handle_get(handler, _parsed("/readyz"))
        body = json.loads(handler._body)
        assert body["ready"] is True
        assert "checks" in body
        assert body["checks"]["http_server"]["ok"] is True


# ── Readiness logic tests ─────────────────────────────────────────────

class TestGetReadiness:
    def test_all_checks_pass(self):
        readyz = _load_readyz()
        with mock.patch.object(readyz, "_check_http_server", return_value={"ok": True}), \
             mock.patch.object(readyz, "_check_agent_runtime", return_value={"ok": True}), \
             mock.patch.object(readyz, "_check_vector_store", return_value={"ok": True}), \
             mock.patch.object(readyz, "_check_config_loaded", return_value={"ok": True}):
            result = readyz.get_readiness()
        assert result["ready"] is True
        assert len(result["checks"]) == 4

    def test_one_check_fails(self):
        readyz = _load_readyz()
        with mock.patch.object(readyz, "_check_http_server", return_value={"ok": True}), \
             mock.patch.object(readyz, "_check_agent_runtime", return_value={"ok": False, "detail": "FATAL"}), \
             mock.patch.object(readyz, "_check_vector_store", return_value={"ok": True}), \
             mock.patch.object(readyz, "_check_config_loaded", return_value={"ok": True}):
            result = readyz.get_readiness()
        assert result["ready"] is False
        assert result["checks"]["agent_runtime"]["ok"] is False

    def test_check_keys_match_contract(self):
        readyz = _load_readyz()
        with mock.patch.object(readyz, "_check_http_server", return_value={"ok": True}), \
             mock.patch.object(readyz, "_check_agent_runtime", return_value={"ok": True}), \
             mock.patch.object(readyz, "_check_vector_store", return_value={"ok": True}), \
             mock.patch.object(readyz, "_check_config_loaded", return_value={"ok": True}):
            result = readyz.get_readiness()
        expected_keys = {"http_server", "agent_runtime", "vector_store", "config_loaded"}
        assert set(result["checks"].keys()) == expected_keys


# ── Individual check tests ─────────────────────────────────────────────

class TestHttpServerCheck:
    def test_always_ok(self):
        readyz = _load_readyz()
        assert readyz._check_http_server() == {"ok": True}


class TestAgentRuntimeCheck:
    def test_running(self):
        readyz = _load_readyz()
        with mock.patch.object(readyz, "_supervisorctl_status", return_value="RUNNING"):
            result = readyz._check_agent_runtime()
        assert result["ok"] is True

    def test_fatal(self):
        readyz = _load_readyz()
        with mock.patch.object(readyz, "_supervisorctl_status", return_value="FATAL"):
            result = readyz._check_agent_runtime()
        assert result["ok"] is False

    def test_no_supervisor(self):
        readyz = _load_readyz()
        with mock.patch.object(readyz, "_supervisorctl_status", return_value=None):
            result = readyz._check_agent_runtime()
        assert result["ok"] is True
        assert "standalone" in result.get("detail", "")


class TestVectorStoreCheck:
    def test_reachable(self):
        readyz = _load_readyz()
        mock_resp = mock.MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__ = mock.Mock(return_value=mock_resp)
        mock_resp.__exit__ = mock.Mock(return_value=False)
        with mock.patch("urllib.request.urlopen", return_value=mock_resp):
            result = readyz._check_vector_store()
        assert result["ok"] is True

    def test_unreachable_with_qdrant_configured(self):
        readyz = _load_readyz()
        with mock.patch("urllib.request.urlopen", side_effect=OSError("refused")), \
             mock.patch.dict("os.environ", {"QDRANT_URL": "http://qdrant:6333"}):
            result = readyz._check_vector_store()
        assert result["ok"] is False

    def test_unreachable_standalone(self):
        readyz = _load_readyz()
        with mock.patch("urllib.request.urlopen", side_effect=OSError("refused")), \
             mock.patch.dict("os.environ", {}, clear=True), \
             mock.patch("os.path.exists", return_value=False):
            result = readyz._check_vector_store()
        assert result["ok"] is True
        assert "standalone" in result.get("detail", "")


class TestConfigLoadedCheck:
    def test_config_ok(self):
        readyz = _load_readyz()
        result = readyz._check_config_loaded()
        assert result["ok"] is True

    def test_config_error(self):
        readyz = _load_readyz()
        config_mod = sys.modules["api.config"]
        original = config_mod.load_settings
        config_mod.load_settings = mock.Mock(side_effect=RuntimeError("corrupt"))
        try:
            result = readyz._check_config_loaded()
            assert result["ok"] is False
            assert "corrupt" in result.get("detail", "")
        finally:
            config_mod.load_settings = original
