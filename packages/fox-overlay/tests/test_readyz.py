"""Tests for fox_overlay.webui_modules.readyz — /readyz endpoint (INST-01)."""

from __future__ import annotations

import json
import subprocess
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

    def test_every_check_is_dict_with_bool_ok(self):
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
        for name, check in result["checks"].items():
            assert isinstance(check, dict), name
            assert isinstance(check["ok"], bool), name


# ── Individual check tests ─────────────────────────────────────────────


class TestHttpServerCheck:
    def test_always_ok(self):
        readyz = _load_readyz()
        assert readyz._check_http_server() == {"ok": True}


class TestAgentRuntimeCheck:
    def test_running(self):
        # Supervisor present + gateway RUNNING → ok.  Must patch
        # _supervisorctl_available too, else on a host without supervisorctl
        # the standalone short-circuit fires before the status is consulted.
        readyz = _load_readyz()
        with (
            mock.patch.object(readyz, "_supervisorctl_available", return_value=True),
            mock.patch.object(readyz, "_supervisorctl_status", return_value="RUNNING"),
        ):
            result = readyz._check_agent_runtime()
        assert result["ok"] is True

    def test_fatal(self):
        readyz = _load_readyz()
        with (
            mock.patch.object(readyz, "_supervisorctl_available", return_value=True),
            mock.patch.object(readyz, "_supervisorctl_status", return_value="FATAL"),
        ):
            result = readyz._check_agent_runtime()
        assert result["ok"] is False

    def test_no_supervisor(self):
        # Genuine standalone: supervisorctl is not present at all → ok:true.
        # This is now the ONLY path that may be ok:true for a non-RUNNING
        # state; a present-but-unverifiable supervisor fails closed (#904).
        readyz = _load_readyz()
        with mock.patch.object(readyz, "_supervisorctl_available", return_value=False):
            result = readyz._check_agent_runtime()
        assert result["ok"] is True
        assert "standalone" in result.get("detail", "")

    def test_present_but_status_unknown_fails(self):
        # #904 regression guard: supervisor present but its status could not be
        # verified (None) must FAIL CLOSED, never map to standalone ok:true.
        readyz = _load_readyz()
        with (
            mock.patch.object(readyz, "_supervisorctl_available", return_value=True),
            mock.patch.object(readyz, "_supervisorctl_status", return_value=None),
        ):
            result = readyz._check_agent_runtime()
        assert result["ok"] is False
        assert "unknown" in result.get("detail", "")


class TestSupervisorStatusProbe:
    """``_supervisorctl_status`` returns None ONLY for the 'unknown' cases —
    timeout, OSError, and the gateway program absent from the output — so the
    caller can fail closed on each (#904).  It never encodes 'standalone'."""

    def test_timeout_is_unknown(self, monkeypatch):
        readyz = _load_readyz()

        def _timeout(*args, **kwargs):
            raise subprocess.TimeoutExpired(cmd="supervisorctl", timeout=5.0)

        monkeypatch.setattr(readyz.subprocess, "run", _timeout)
        assert readyz._supervisorctl_status("hermes-gateway") is None

    def test_oserror_is_unknown(self, monkeypatch):
        readyz = _load_readyz()

        def _oserror(*args, **kwargs):
            raise OSError("connection refused")

        monkeypatch.setattr(readyz.subprocess, "run", _oserror)
        assert readyz._supervisorctl_status("hermes-gateway") is None

    def test_program_absent_from_output_is_unknown(self, monkeypatch):
        # The loop fall-through: supervisorctl answered, but hermes-gateway is
        # not in the output.  Folded into the same fail-closed None (#904).
        readyz = _load_readyz()
        monkeypatch.setattr(
            readyz.subprocess,
            "run",
            lambda *a, **k: SimpleNamespace(
                stdout="other-prog RUNNING pid 1, uptime 0:10\n", returncode=0
            ),
        )
        assert readyz._supervisorctl_status("hermes-gateway") is None

    def test_running_line_parsed(self, monkeypatch):
        readyz = _load_readyz()
        monkeypatch.setattr(
            readyz.subprocess,
            "run",
            lambda *a, **k: SimpleNamespace(
                stdout="hermes-gateway RUNNING pid 42, uptime 0:10\n", returncode=0
            ),
        )
        assert readyz._supervisorctl_status("hermes-gateway") == "RUNNING"


def _clear_qdrant_env(monkeypatch):
    """Drop every Qdrant server-mode var so a test controls the mode
    outright regardless of the ambient environment."""
    for var in (
        "MEM0_OSS_QDRANT_URL",
        "MEM0_OSS_QDRANT_HOST",
        "MEM0_OSS_QDRANT_PORT",
        "MEM0_OSS_QDRANT_API_KEY",
        "QDRANT_URL",
    ):
        monkeypatch.delenv(var, raising=False)


class TestVectorStoreCheck:
    """vector_store reflects ONLY Qdrant reachability and probes the SAME
    server-mode endpoint ``_check_memory`` dials (#865): server mode probes
    the resolved ``/readyz``; embedded / opt-out mode never dials.  The old
    ``QDRANT_URL`` / ``/data/qdrant`` escape hatch is gone."""

    def test_server_mode_unreachable_qdrant_fails(self, monkeypatch):
        # Primary #865 repro: server configured, server down → fail loud.
        import urllib.error
        import urllib.request

        readyz = _load_readyz()
        _clear_qdrant_env(monkeypatch)
        monkeypatch.setenv("MEM0_OSS_QDRANT_URL", "http://127.0.0.1:6333")
        fake = _FakeUrlopen(raises=urllib.error.URLError("refused"))
        monkeypatch.setattr(urllib.request, "urlopen", fake)

        result = readyz._check_vector_store()
        assert result["ok"] is False
        assert "unreachable" in result["detail"]
        # Probed the server-mode /readyz, not the legacy /healthz.
        assert fake.calls and fake.calls[0].endswith("/readyz")

    def test_server_mode_reachable_ok(self, monkeypatch):
        import urllib.request

        readyz = _load_readyz()
        _clear_qdrant_env(monkeypatch)
        monkeypatch.setenv("MEM0_OSS_QDRANT_URL", "http://127.0.0.1:6333")
        fake = _FakeUrlopen()
        monkeypatch.setattr(urllib.request, "urlopen", fake)

        result = readyz._check_vector_store()
        assert result["ok"] is True
        assert fake.calls and fake.calls[0].endswith("/readyz")

    def test_embedded_mode_ok_without_probe(self, monkeypatch):
        import urllib.request

        readyz = _load_readyz()
        _clear_qdrant_env(monkeypatch)  # no server vars → embedded store
        fake = _FakeUrlopen()
        monkeypatch.setattr(urllib.request, "urlopen", fake)

        result = readyz._check_vector_store()
        assert result["ok"] is True
        assert fake.calls == []  # embedded mode never dials

    def test_remote_host_unreachable_not_false_healthy(self, monkeypatch):
        # Was false-healthy before #865: a remote _HOST with no local
        # /data/qdrant and no QDRANT_URL used to report ok:true.
        import urllib.error
        import urllib.request

        readyz = _load_readyz()
        _clear_qdrant_env(monkeypatch)
        monkeypatch.setenv("MEM0_OSS_QDRANT_HOST", "qdrant.remote")
        fake = _FakeUrlopen(raises=urllib.error.URLError("no route to host"))
        monkeypatch.setattr(urllib.request, "urlopen", fake)

        result = readyz._check_vector_store()
        assert result["ok"] is False
        assert fake.calls and fake.calls[0].endswith("/readyz")

    def test_https_api_key_probes_correct_target(self, monkeypatch):
        import urllib.request

        readyz = _load_readyz()
        _clear_qdrant_env(monkeypatch)
        monkeypatch.setenv("MEM0_OSS_QDRANT_URL", "https://qdrant.example.com")
        monkeypatch.setenv("MEM0_OSS_QDRANT_API_KEY", "secret")
        fake = _FakeUrlopen()
        monkeypatch.setattr(urllib.request, "urlopen", fake)

        result = readyz._check_vector_store()
        assert result["ok"] is True
        assert fake.requests, "server mode must dial the resolved target"
        req = fake.requests[0]
        # Parse the URL rather than substring-matching it (a startswith host
        # check would also accept https://qdrant.example.com.evil.com).
        parsed = urllib.parse.urlparse(req.full_url)
        assert parsed.scheme == "https"
        assert parsed.hostname == "qdrant.example.com"
        assert parsed.path == "/readyz"
        # api-key header rides along (urllib capitalizes to "Api-key").
        assert req.get_header("Api-key") == "secret"


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
        self.requests: list = []

    def __call__(self, req, timeout=None):
        self.calls.append(getattr(req, "full_url", req))
        self.requests.append(req)
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


# ── vector_store ↔ memory consistency (full get_readiness, #865) ────────


class TestVectorStoreMemoryConsistency:
    """#865 regression: driven through ``get_readiness()``, ``vector_store``
    and ``memory`` must agree on Qdrant server reachability (both probe the
    same resolved ``/readyz``) — while still diverging legitimately when
    memory fails for a non-Qdrant reason (dead embed-server) or is off."""

    def _seed_ready(self, tmp_path, monkeypatch):
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

    def _seed_state(self, tmp_path, monkeypatch, payload):
        state_path = tmp_path / "state.json"
        state_path.write_text(json.dumps(payload), encoding="utf-8")
        monkeypatch.setenv("MEM0_OSS_STATE_PATH", str(state_path))

    def test_server_down_both_agree(self, tmp_path, monkeypatch):
        # The regression: with a server configured and down, both the
        # vector_store and memory checks must fail — not disagree.
        import urllib.error
        import urllib.request

        readyz = _load_readyz()
        self._seed_ready(tmp_path, monkeypatch)
        _clear_qdrant_env(monkeypatch)
        monkeypatch.setenv("MEM0_OSS_QDRANT_URL", "http://127.0.0.1:6333")
        monkeypatch.setattr(readyz, "_check_agent_runtime", lambda: {"ok": True})
        monkeypatch.setattr(readyz, "_embed_server_alive", lambda: True)
        fake = _FakeUrlopen(raises=urllib.error.URLError("refused"))
        monkeypatch.setattr(urllib.request, "urlopen", fake)

        checks = readyz.get_readiness()["checks"]
        assert checks["vector_store"]["ok"] is False
        assert checks["memory"]["ok"] is False
        assert checks["vector_store"]["ok"] == checks["memory"]["ok"]
        assert readyz.get_readiness()["ready"] is False

    def test_server_up_both_ok(self, tmp_path, monkeypatch):
        import urllib.request

        readyz = _load_readyz()
        self._seed_ready(tmp_path, monkeypatch)
        _clear_qdrant_env(monkeypatch)
        monkeypatch.setenv("MEM0_OSS_QDRANT_URL", "http://127.0.0.1:6333")
        monkeypatch.setattr(readyz, "_check_agent_runtime", lambda: {"ok": True})
        monkeypatch.setattr(readyz, "_embed_server_alive", lambda: True)
        fake = _FakeUrlopen()
        monkeypatch.setattr(urllib.request, "urlopen", fake)

        result = readyz.get_readiness()
        checks = result["checks"]
        assert checks["vector_store"]["ok"] is True
        assert checks["memory"]["ok"] is True
        assert checks["vector_store"]["ok"] == checks["memory"]["ok"]
        assert result["ready"] is True

    def test_embedded_both_ok_no_dial(self, tmp_path, monkeypatch):
        import urllib.request

        readyz = _load_readyz()
        self._seed_ready(tmp_path, monkeypatch)
        _clear_qdrant_env(monkeypatch)  # embedded store — nothing to dial
        monkeypatch.setattr(readyz, "_check_agent_runtime", lambda: {"ok": True})
        monkeypatch.setattr(readyz, "_embed_server_alive", lambda: True)
        fake = _FakeUrlopen()
        monkeypatch.setattr(urllib.request, "urlopen", fake)

        result = readyz.get_readiness()
        checks = result["checks"]
        assert checks["vector_store"]["ok"] is True
        assert checks["memory"]["ok"] is True
        assert fake.calls == []
        assert result["ready"] is True

    def test_memory_disabled_vector_store_ok(self, tmp_path, monkeypatch):
        # Real disabled-instance config: MEM0_OSS_QDRANT_URL stays baked in at
        # the supervisord baseline (never cleared on disable) AND state.json
        # reads "off".  vector_store must report disabled off the same signal
        # as memory — never dial the still-configured server (#865).
        import urllib.request

        readyz = _load_readyz()
        self._seed_state(
            tmp_path,
            monkeypatch,
            {"status": "off", "reason": "disabled (MEM0_OSS_DISABLED=1)"},
        )
        _clear_qdrant_env(monkeypatch)
        monkeypatch.setenv("MEM0_OSS_QDRANT_URL", "http://127.0.0.1:6333")
        monkeypatch.setattr(readyz, "_check_agent_runtime", lambda: {"ok": True})
        fake = _FakeUrlopen()
        monkeypatch.setattr(urllib.request, "urlopen", fake)

        result = readyz.get_readiness()
        checks = result["checks"]
        assert checks["memory"]["ok"] is True
        assert checks["vector_store"]["ok"] is True
        # Disabled reported off the same state.json signal as memory, not a probe.
        assert "disabled" in checks["vector_store"]["detail"]
        assert checks["vector_store"]["ok"] == checks["memory"]["ok"]
        assert fake.calls == []  # disabled → nothing to dial despite the URL
        assert result["ready"] is True

    def test_embed_dead_keeps_vector_store_true(self, tmp_path, monkeypatch):
        # Guards against a naive ``vector_store = memory.ok`` fix: the store
        # is up, memory fails only because the embed-server is dead.
        import urllib.request

        readyz = _load_readyz()
        self._seed_ready(tmp_path, monkeypatch)
        _clear_qdrant_env(monkeypatch)
        monkeypatch.setenv("MEM0_OSS_QDRANT_URL", "http://127.0.0.1:6333")
        monkeypatch.setattr(readyz, "_check_agent_runtime", lambda: {"ok": True})
        monkeypatch.setattr(readyz, "_embed_server_alive", lambda: False)
        fake = _FakeUrlopen()  # qdrant reachable
        monkeypatch.setattr(urllib.request, "urlopen", fake)

        result = readyz.get_readiness()
        checks = result["checks"]
        assert checks["memory"]["ok"] is False
        assert "embed-server" in checks["memory"]["detail"]
        assert checks["vector_store"]["ok"] is True
        assert result["ready"] is False

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
    def test_never_false_healthy_across_server_configs(
        self, env, tmp_path, monkeypatch
    ):
        import urllib.error
        import urllib.request

        readyz = _load_readyz()
        self._seed_ready(tmp_path, monkeypatch)
        _clear_qdrant_env(monkeypatch)
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        monkeypatch.setattr(readyz, "_check_agent_runtime", lambda: {"ok": True})
        monkeypatch.setattr(readyz, "_embed_server_alive", lambda: True)
        fake = _FakeUrlopen(raises=urllib.error.URLError("refused"))
        monkeypatch.setattr(urllib.request, "urlopen", fake)

        result = readyz.get_readiness()
        assert result["checks"]["vector_store"]["ok"] is False
        assert result["ready"] is False


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

    @pytest.mark.parametrize(
        "bad_url",
        [
            pytest.param("http://host:notaport", id="non_numeric_port"),
            pytest.param("http://host:99999999", id="port_out_of_range"),
            pytest.param("http://host:-1", id="negative_port"),
            pytest.param("http://[::1", id="truncated_ipv6"),
        ],
    )
    def test_malformed_url_falls_back_instead_of_raising(self, bad_url, monkeypatch):
        """#885: a malformed MEM0_OSS_QDRANT_URL (bad port / unbracketed IPv6)
        must not raise out of the resolver — it falls back to a well-formed
        probe URL so /readyz fails loud via the reachability check, not a 500."""
        readyz = _load_readyz()
        for var in (
            "MEM0_OSS_QDRANT_URL",
            "MEM0_OSS_QDRANT_HOST",
            "MEM0_OSS_QDRANT_PORT",
            "MEM0_OSS_QDRANT_API_KEY",
        ):
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setenv("MEM0_OSS_QDRANT_URL", bad_url)

        # Must not raise (the pre-#885 bug raised ValueError here).
        url = readyz._memory_qdrant_readyz_url()
        # Falls back to the co-located default, and the result is itself a
        # well-formed, re-parseable probe URL.
        assert url == "http://127.0.0.1:6333/readyz"
        parsed = urllib.parse.urlparse(url)
        assert parsed.hostname == "127.0.0.1"
        assert parsed.port == 6333

    @pytest.mark.parametrize(
        "bad_url",
        [
            pytest.param("http://host:notaport", id="non_numeric_port"),
            pytest.param("http://host:99999999", id="port_out_of_range"),
            pytest.param("http://host:-1", id="negative_port"),
            pytest.param("http://[::1", id="truncated_ipv6"),
        ],
    )
    def test_check_vector_store_no_500_on_malformed_url(self, bad_url, monkeypatch):
        """#885: _check_vector_store must return a structured ok:false when the
        server URL is malformed and memory is active — never propagate a
        ValueError to the request boundary (which surfaced as HTTP 500).  Covers
        both raise sites: bad ports (at parsed.port) and truncated IPv6 (at
        urlparse itself), plus the downstream re-parse in _check_vector_store."""
        readyz = _load_readyz()
        for var in (
            "MEM0_OSS_QDRANT_HOST",
            "MEM0_OSS_QDRANT_PORT",
            "MEM0_OSS_QDRANT_API_KEY",
        ):
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setenv("MEM0_OSS_QDRANT_URL", bad_url)
        # Memory active (not opted out), server unreachable — keep it hermetic.
        monkeypatch.setattr(readyz, "_memory_disabled", lambda: False)
        monkeypatch.setattr(readyz, "_memory_qdrant_reachable", lambda: False)

        result = readyz._check_vector_store()
        assert result["ok"] is False
        assert "unreachable" in result["detail"]


# ── Embed-probe health URL resolution (MEM0_OSS_EMBED_HEALTH_URL, #869) ──


class TestEmbedHealthUrlResolution:
    """#869: the embed-server probe must dial the resolved health URL — the
    ``MEM0_OSS_EMBED_HEALTH_URL`` override when set, else the default — not a
    hardcoded ``127.0.0.1:8644``.  These exercise the REAL ``_embed_health_url``
    / ``_embed_server_alive`` with a fake ``urlopen`` that captures the dialed
    URL, so they would catch a probe that ignores the override."""

    def _write_ready_local_state(self, tmp_path, monkeypatch):
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

    def test_embed_health_url_honors_env_override(self, monkeypatch):
        readyz = _load_readyz()
        monkeypatch.setenv(
            "MEM0_OSS_EMBED_HEALTH_URL", "http://embedder.internal:9000/health"
        )
        assert readyz._embed_health_url() == "http://embedder.internal:9000/health"

    def test_embed_health_url_defaults_when_unset(self, monkeypatch):
        readyz = _load_readyz()
        monkeypatch.delenv("MEM0_OSS_EMBED_HEALTH_URL", raising=False)
        assert readyz._embed_health_url() == readyz._EMBED_HEALTH_URL
        assert readyz._embed_health_url() == "http://127.0.0.1:8644/health"

    def test_embed_probe_dials_override_not_8644(self, monkeypatch):
        # Primary #869 repro: with the override set, the real probe must dial
        # the override host — not the hardcoded co-located default.
        import urllib.request

        readyz = _load_readyz()
        monkeypatch.setenv(
            "MEM0_OSS_EMBED_HEALTH_URL", "http://embedder.internal:9000/health"
        )
        fake = _FakeUrlopen()
        monkeypatch.setattr(urllib.request, "urlopen", fake)

        assert readyz._embed_server_alive() is True
        assert fake.calls, "embed probe must dial the resolved health URL"
        parsed = urllib.parse.urlparse(fake.calls[0])
        assert parsed.hostname == "embedder.internal"
        assert parsed.port == 9000
        assert "127.0.0.1:8644" not in fake.calls[0]

    def test_embed_probe_default_dials_8644(self, monkeypatch):
        # No override → default install behavior unchanged.
        import urllib.request

        readyz = _load_readyz()
        monkeypatch.delenv("MEM0_OSS_EMBED_HEALTH_URL", raising=False)
        fake = _FakeUrlopen()
        monkeypatch.setattr(urllib.request, "urlopen", fake)

        assert readyz._embed_server_alive() is True
        assert fake.calls
        parsed = urllib.parse.urlparse(fake.calls[0])
        assert parsed.hostname == "127.0.0.1"
        assert parsed.port == 8644

    def test_check_memory_embed_dead_names_resolved_target(self, tmp_path, monkeypatch):
        # Guards the detail-string fix: a dead embed-server names the RESOLVED
        # endpoint, not a hardcoded ":8644".  Embedded Qdrant (no server env)
        # is trivially reachable, so the only dial is the embed probe.
        import urllib.error
        import urllib.request

        readyz = _load_readyz()
        self._write_ready_local_state(tmp_path, monkeypatch)
        _clear_qdrant_env(monkeypatch)
        monkeypatch.setenv(
            "MEM0_OSS_EMBED_HEALTH_URL", "http://embedder.internal:9000/health"
        )
        monkeypatch.setattr(readyz, "_check_agent_runtime", lambda: {"ok": True})
        fake = _FakeUrlopen(raises=urllib.error.URLError("refused"))
        monkeypatch.setattr(urllib.request, "urlopen", fake)

        checks = readyz.get_readiness()["checks"]
        assert checks["memory"]["ok"] is False
        detail = checks["memory"]["detail"]
        assert "embedder.internal:9000" in detail
        assert ":8644" not in detail

    def test_non_local_embedder_never_dials(self, tmp_path, monkeypatch):
        # Behavior preserved: a remote embedder skips the probe entirely, even
        # with an override configured — nothing is dialed.
        import urllib.request

        readyz = _load_readyz()
        state_path = tmp_path / "state.json"
        state_path.write_text(
            json.dumps(
                {
                    "status": "ready",
                    "reason": "",
                    "llm": "openrouter",
                    "embedder": "openai:text-embedding-3-small",
                }
            ),
            encoding="utf-8",
        )
        monkeypatch.setenv("MEM0_OSS_STATE_PATH", str(state_path))
        _clear_qdrant_env(monkeypatch)
        monkeypatch.setenv(
            "MEM0_OSS_EMBED_HEALTH_URL", "http://embedder.internal:9000/health"
        )
        fake = _FakeUrlopen()
        monkeypatch.setattr(urllib.request, "urlopen", fake)

        result = readyz._check_memory()
        assert result["ok"] is True
        assert fake.calls == []  # remote embedder never probes the embed server
