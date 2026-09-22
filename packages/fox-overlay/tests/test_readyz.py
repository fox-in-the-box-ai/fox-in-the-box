"""Tests for fox_overlay.webui_modules.readyz — /readyz endpoint (INST-01)."""

from __future__ import annotations

import json
import sys
import types
import urllib.parse
from pathlib import Path
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
    sys.modules["api"] = api
    sys.modules["api.auth"] = auth
    sys.modules["api.config"] = config
    sys.modules["api.helpers"] = helpers
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
        with mock.patch.object(
            readyz,
            "get_readiness",
            return_value={
                "ready": True,
                "checks": {"http_server": {"ok": True}},
            },
        ):
            readyz._handle_get(handler, _parsed("/readyz"))
        body = json.loads(handler._body)
        assert body["ready"] is True
        assert "checks" in body
        assert body["checks"]["http_server"]["ok"] is True


# ── Readiness logic tests ─────────────────────────────────────────────


class TestGetReadiness:
    def test_all_checks_pass(self):
        readyz = _load_readyz()
        with (
            mock.patch.object(readyz, "_check_http_server", return_value={"ok": True}),
            mock.patch.object(
                readyz, "_check_agent_runtime", return_value={"ok": True}
            ),
            mock.patch.object(readyz, "_check_vector_store", return_value={"ok": True}),
            mock.patch.object(
                readyz, "_check_config_loaded", return_value={"ok": True}
            ),
            mock.patch.object(readyz, "_check_memory", return_value={"ok": True}),
        ):
            result = readyz.get_readiness()
        assert result["ready"] is True
        assert len(result["checks"]) == 5

    def test_one_check_fails(self):
        readyz = _load_readyz()
        with (
            mock.patch.object(readyz, "_check_http_server", return_value={"ok": True}),
            mock.patch.object(
                readyz,
                "_check_agent_runtime",
                return_value={"ok": False, "detail": "FATAL"},
            ),
            mock.patch.object(readyz, "_check_vector_store", return_value={"ok": True}),
            mock.patch.object(
                readyz, "_check_config_loaded", return_value={"ok": True}
            ),
            mock.patch.object(readyz, "_check_memory", return_value={"ok": True}),
        ):
            result = readyz.get_readiness()
        assert result["ready"] is False
        assert result["checks"]["agent_runtime"]["ok"] is False

    def test_check_keys_match_contract(self):
        # "memory" added per the mem0-default-on design (§f readyz row).
        readyz = _load_readyz()
        with (
            mock.patch.object(readyz, "_check_http_server", return_value={"ok": True}),
            mock.patch.object(
                readyz, "_check_agent_runtime", return_value={"ok": True}
            ),
            mock.patch.object(readyz, "_check_vector_store", return_value={"ok": True}),
            mock.patch.object(
                readyz, "_check_config_loaded", return_value={"ok": True}
            ),
            mock.patch.object(readyz, "_check_memory", return_value={"ok": True}),
        ):
            result = readyz.get_readiness()
        expected_keys = {
            "http_server",
            "agent_runtime",
            "vector_store",
            "config_loaded",
            "memory",
        }
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
        with (
            mock.patch("urllib.request.urlopen", side_effect=OSError("refused")),
            mock.patch.dict("os.environ", {"QDRANT_URL": "http://qdrant:6333"}),
        ):
            result = readyz._check_vector_store()
        assert result["ok"] is False

    def test_unreachable_standalone(self):
        readyz = _load_readyz()
        with (
            mock.patch("urllib.request.urlopen", side_effect=OSError("refused")),
            mock.patch.dict("os.environ", {}, clear=True),
            mock.patch("os.path.exists", return_value=False),
        ):
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


class TestMemoryCheck:
    """Memory component (mem0-default-on design §a.2): reads the plugin's
    state.json; ok:false ONLY for status=="error" (and the ready-but-dead
    embed-server cross-check); "off" is visible-but-healthy."""

    def _write_state(self, tmp_path, monkeypatch, payload):
        state_path = tmp_path / "state.json"
        state_path.write_text(json.dumps(payload), encoding="utf-8")
        monkeypatch.setenv("MEM0_OSS_STATE_PATH", str(state_path))
        return state_path

    def test_missing_state_file_is_ok(self, tmp_path, monkeypatch):
        readyz = _load_readyz()
        monkeypatch.setenv("MEM0_OSS_STATE_PATH", str(tmp_path / "absent.json"))
        result = readyz._check_memory()
        assert result["ok"] is True
        assert "not reported" in result["detail"]

    def test_corrupt_state_file_is_tolerated(self, tmp_path, monkeypatch):
        readyz = _load_readyz()
        state_path = tmp_path / "state.json"
        state_path.write_text("{not json", encoding="utf-8")
        monkeypatch.setenv("MEM0_OSS_STATE_PATH", str(state_path))
        result = readyz._check_memory()
        assert result["ok"] is True

    def test_ready_state_probes_embed_server(self, tmp_path, monkeypatch):
        readyz = _load_readyz()
        self._write_state(
            tmp_path,
            monkeypatch,
            {
                "status": "ready",
                "reason": "",
                "llm": "openrouter",
                "embedder": "local:nomic-embed-text-v1.5",
            },
        )
        with mock.patch.object(readyz, "_embed_server_alive", return_value=True):
            result = readyz._check_memory()
        assert result["ok"] is True
        assert "llm=openrouter" in result["detail"]

    def test_ready_state_dead_embed_server_fails(self, tmp_path, monkeypatch):
        readyz = _load_readyz()
        self._write_state(
            tmp_path,
            monkeypatch,
            {
                "status": "ready",
                "reason": "",
                "llm": "openrouter",
                "embedder": "local:nomic-embed-text-v1.5",
            },
        )
        with mock.patch.object(readyz, "_embed_server_alive", return_value=False):
            result = readyz._check_memory()
        assert result["ok"] is False
        assert "embed-server" in result["detail"]

    def test_ready_with_remote_embedder_skips_probe(self, tmp_path, monkeypatch):
        readyz = _load_readyz()
        self._write_state(
            tmp_path,
            monkeypatch,
            {
                "status": "ready",
                "reason": "",
                "llm": "openrouter",
                "embedder": "openai:text-embedding-3-small",
            },
        )
        with mock.patch.object(readyz, "_embed_server_alive", return_value=False):
            result = readyz._check_memory()
        assert result["ok"] is True

    def test_off_state_is_ok_with_reason(self, tmp_path, monkeypatch):
        readyz = _load_readyz()
        self._write_state(
            tmp_path,
            monkeypatch,
            {"status": "off", "reason": "disabled (MEM0_OSS_DISABLED=1)"},
        )
        result = readyz._check_memory()
        assert result["ok"] is True
        assert "disabled" in result["detail"]

    def test_error_state_fails_with_reason(self, tmp_path, monkeypatch):
        readyz = _load_readyz()
        self._write_state(
            tmp_path,
            monkeypatch,
            {"status": "error", "reason": "missing API key for provider 'openrouter'"},
        )
        result = readyz._check_memory()
        assert result["ok"] is False
        assert "openrouter" in result["detail"]


# ── Qdrant server-mode reachability (boot-race fail-loud, #780 blocker) ──


class _FakeResponse:
    """Hand-rolled context-manager response for a reachable probe."""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _FakeUrlopen:
    """Hand-rolled stand-in for ``urllib.request.urlopen`` (not a mock).

    Records every call so a test can assert the probe did — or did not —
    dial; raises ``raises`` when set (unreachable), else returns a reachable
    response."""

    def __init__(self, *, raises=None):
        self._raises = raises
        self.calls: list[str] = []

    def __call__(self, req, timeout=None):
        self.calls.append(getattr(req, "full_url", req))
        if self._raises is not None:
            raise self._raises
        return _FakeResponse()


class TestMemoryQdrantReachability:
    """``_check_memory`` re-probes the Qdrant server at request time in
    server mode (boot-race fail-loud); embedded mode never dials."""

    def _write_ready_state(self, tmp_path, monkeypatch):
        state_path = tmp_path / "state.json"
        state_path.write_text(
            json.dumps(
                {
                    "status": "ready",
                    "reason": "",
                    "llm": "openrouter",
                    "embedder": "local:nomic-embed-text-v1.5",
                }
            ),
            encoding="utf-8",
        )
        monkeypatch.setenv("MEM0_OSS_STATE_PATH", str(state_path))

    def test_server_mode_unreachable_qdrant_fails(self, tmp_path, monkeypatch):
        import urllib.error
        import urllib.request

        readyz = _load_readyz()
        self._write_ready_state(tmp_path, monkeypatch)
        monkeypatch.setenv("MEM0_OSS_QDRANT_URL", "http://127.0.0.1:6333")
        monkeypatch.setattr(readyz, "_embed_server_alive", lambda: True)
        fake = _FakeUrlopen(raises=urllib.error.URLError("refused"))
        monkeypatch.setattr(urllib.request, "urlopen", fake)

        result = readyz._check_memory()
        assert result["ok"] is False
        assert "qdrant server unreachable" in result["detail"]
        # The probe actually dialed the server-mode /readyz endpoint.
        assert fake.calls and fake.calls[0].endswith("/readyz")

    def test_embedded_mode_does_not_probe_qdrant(self, tmp_path, monkeypatch):
        import urllib.request

        readyz = _load_readyz()
        self._write_ready_state(tmp_path, monkeypatch)
        # No MEM0_OSS_QDRANT_URL / _HOST → embedded store, nothing to dial.
        monkeypatch.delenv("MEM0_OSS_QDRANT_URL", raising=False)
        monkeypatch.delenv("MEM0_OSS_QDRANT_HOST", raising=False)
        monkeypatch.setattr(readyz, "_embed_server_alive", lambda: True)
        fake = _FakeUrlopen()
        monkeypatch.setattr(urllib.request, "urlopen", fake)

        assert readyz._memory_qdrant_reachable() is True
        assert fake.calls == []  # embedded mode never probes
        result = readyz._check_memory()
        assert result["ok"] is True


# ── Cross-boundary drift guard (readyz resolver vs plugin resolver) ─────


class TestQdrantResolverDriftGuard:
    """``readyz._memory_qdrant_readyz_url`` hand-copies the plugin's
    ``_resolve_qdrant_target`` across the webui/agent process boundary (the
    webui cannot import the plugin — legitimate).  This guard — in the one
    suite that CAN import both — fails if the two ever disagree on
    host/port/scheme for representative configs, so a one-sided edit is
    caught."""

    def _plugin(self):
        repo_root = Path(__file__).resolve().parents[3]
        hermes_agent = repo_root / "forks" / "hermes-agent"
        if hermes_agent.is_dir() and str(hermes_agent) not in sys.path:
            sys.path.insert(0, str(hermes_agent))
        pytest.importorskip(
            "hermes_cli.providers",
            reason="forks/hermes-agent not importable in this environment",
        )
        return pytest.importorskip("agent_memory_plugins.mem0_oss")

    @pytest.mark.parametrize(
        "env",
        [
            pytest.param(
                {"MEM0_OSS_QDRANT_URL": "http://127.0.0.1:6333"}, id="keyless_url"
            ),
            pytest.param(
                {
                    "MEM0_OSS_QDRANT_URL": "http://qdrant.internal:6333",
                    "MEM0_OSS_QDRANT_API_KEY": "secret",
                },
                id="url_key_http",
            ),
            pytest.param(
                {
                    "MEM0_OSS_QDRANT_URL": "https://qdrant.example.com",
                    "MEM0_OSS_QDRANT_API_KEY": "secret",
                },
                id="url_key_https",
            ),
            pytest.param(
                {
                    "MEM0_OSS_QDRANT_HOST": "qdrant.local",
                    "MEM0_OSS_QDRANT_PORT": "6399",
                },
                id="host_port",
            ),
        ],
    )
    def test_resolvers_agree_on_host_port_scheme(self, env, monkeypatch):
        plugin = self._plugin()
        readyz = _load_readyz()
        for var in (
            "MEM0_OSS_QDRANT_URL",
            "MEM0_OSS_QDRANT_HOST",
            "MEM0_OSS_QDRANT_PORT",
            "MEM0_OSS_QDRANT_API_KEY",
        ):
            monkeypatch.delenv(var, raising=False)
        for key, value in env.items():
            monkeypatch.setenv(key, value)

        # Feed the plugin resolver the same inputs the readyz side reads
        # from the environment.
        runtime_cfg = {
            "qdrant_url": env.get("MEM0_OSS_QDRANT_URL", ""),
            "qdrant_host": env.get("MEM0_OSS_QDRANT_HOST", ""),
            "qdrant_port": env.get("MEM0_OSS_QDRANT_PORT", "6333"),
            "qdrant_api_key": env.get("MEM0_OSS_QDRANT_API_KEY", ""),
        }
        p_host, p_port, p_https = plugin._resolve_qdrant_target(runtime_cfg)
        p_scheme = "https" if p_https else "http"

        url = readyz._memory_qdrant_readyz_url()
        assert url is not None
        parsed = urllib.parse.urlparse(url)
        assert parsed.hostname == p_host
        assert parsed.port == p_port
        assert parsed.scheme == p_scheme
