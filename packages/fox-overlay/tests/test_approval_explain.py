"""Tests for fox_overlay.webui_modules.approval_explain — /api/approval-explain/ endpoint (#150)."""
from __future__ import annotations

import json
import sys
import types
from types import SimpleNamespace
from unittest import mock

import pytest


def _stub_upstream():
    api = types.ModuleType("api")
    helpers = types.ModuleType("api.helpers")

    def _j(handler, data, status=200):
        body = json.dumps(data).encode()
        handler.send_response(status)
        handler.send_header("Content-Type", "application/json")
        handler.end_headers()
        handler._body = body

    def _bad(handler, msg, status=400):
        _j(handler, {"error": msg}, status=status)

    def _read_body(handler):
        return handler._request_body

    helpers.j = _j
    helpers.bad = _bad
    helpers.read_body = _read_body
    api.helpers = helpers
    sys.modules["api"] = api
    sys.modules["api.helpers"] = helpers


@pytest.fixture(autouse=True)
def _upstream():
    _stub_upstream()
    from fox_overlay import dispatch
    dispatch._GET_TABLE.clear()
    dispatch._POST_TABLE.clear()
    dispatch._BootstrapState.frozen = False
    yield
    sys.modules.pop("fox_overlay.webui_modules.approval_explain", None)
    sys.modules.pop("agent", None)
    sys.modules.pop("agent.auxiliary_client", None)


def _load_module():
    sys.modules.pop("fox_overlay.webui_modules.approval_explain", None)
    import fox_overlay.webui_modules as _pkg
    if hasattr(_pkg, "approval_explain"):
        delattr(_pkg, "approval_explain")
    from fox_overlay.webui_modules import approval_explain
    return approval_explain


def _make_handler(body=None):
    h = SimpleNamespace()
    h._headers_sent = []
    h._body = None
    h._status = None
    h._request_body = body or {}
    h.send_response = lambda status: setattr(h, "_status", status)
    h.send_header = lambda k, v: h._headers_sent.append((k, v))
    h.end_headers = lambda: None
    return h


def _parsed(path):
    return SimpleNamespace(path=path)


class TestRegistration:
    def test_registers_post_handler(self):
        _load_module()
        from fox_overlay.dispatch import POST_TABLE
        assert "/api/approval-explain/" in POST_TABLE

    def test_no_get_handler(self):
        _load_module()
        from fox_overlay.dispatch import GET_TABLE
        assert "/api/approval-explain/" not in GET_TABLE


class TestHandler:
    def test_handles_matching_path(self):
        mod = _load_module()
        handler = _make_handler({"command": "rm -rf /tmp/test"})
        with mock.patch.object(mod, "_generate_explanation", return_value="Deletes the test directory."):
            assert mod._handle_post(handler, _parsed("/api/approval-explain/")) is True
        body = json.loads(handler._body)
        assert body["explanation"] == "Deletes the test directory."

    def test_declines_non_matching_path(self):
        mod = _load_module()
        handler = _make_handler()
        assert mod._handle_post(handler, _parsed("/api/approval-explain")) is False
        assert mod._handle_post(handler, _parsed("/api/approval-explain/extra")) is False
        assert mod._handle_post(handler, _parsed("/api/other/")) is False

    def test_returns_400_when_command_missing(self):
        mod = _load_module()
        handler = _make_handler({"description": "some desc"})
        assert mod._handle_post(handler, _parsed("/api/approval-explain/")) is True
        body = json.loads(handler._body)
        assert "error" in body
        assert handler._status == 400

    def test_returns_400_when_command_empty(self):
        mod = _load_module()
        handler = _make_handler({"command": "   "})
        assert mod._handle_post(handler, _parsed("/api/approval-explain/")) is True
        body = json.loads(handler._body)
        assert "error" in body

    def test_returns_null_when_explanation_fails(self):
        mod = _load_module()
        handler = _make_handler({"command": "ls -la"})
        with mock.patch.object(mod, "_generate_explanation", return_value=None):
            mod._handle_post(handler, _parsed("/api/approval-explain/"))
        body = json.loads(handler._body)
        assert body["explanation"] is None


class TestGenerateExplanation:
    def test_returns_none_when_call_llm_not_importable(self):
        mod = _load_module()
        sys.modules.pop("agent", None)
        sys.modules.pop("agent.auxiliary_client", None)
        result = mod._generate_explanation("ls", "list files")
        assert result is None

    def test_returns_explanation_on_success(self):
        mod = _load_module()
        fake_response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="Lists directory contents."))]
        )
        agent_mod = types.ModuleType("agent")
        aux_mod = types.ModuleType("agent.auxiliary_client")
        aux_mod.call_llm = mock.Mock(return_value=fake_response)
        sys.modules["agent"] = agent_mod
        sys.modules["agent.auxiliary_client"] = aux_mod

        result = mod._generate_explanation("ls -la", "list files")
        assert result == "Lists directory contents."
        aux_mod.call_llm.assert_called_once()
        call_kwargs = aux_mod.call_llm.call_args
        assert call_kwargs[1]["temperature"] == 0

    def test_returns_none_on_exception(self):
        mod = _load_module()
        agent_mod = types.ModuleType("agent")
        aux_mod = types.ModuleType("agent.auxiliary_client")
        aux_mod.call_llm = mock.Mock(side_effect=RuntimeError("no provider"))
        sys.modules["agent"] = agent_mod
        sys.modules["agent.auxiliary_client"] = aux_mod

        result = mod._generate_explanation("ls", "list")
        assert result is None

    def test_returns_none_on_empty_response(self):
        mod = _load_module()
        fake_response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=""))]
        )
        agent_mod = types.ModuleType("agent")
        aux_mod = types.ModuleType("agent.auxiliary_client")
        aux_mod.call_llm = mock.Mock(return_value=fake_response)
        sys.modules["agent"] = agent_mod
        sys.modules["agent.auxiliary_client"] = aux_mod

        result = mod._generate_explanation("ls", "list")
        assert result is None


class TestSanitizeExplanation:
    def test_first_sentence_only(self):
        mod = _load_module()
        assert mod._sanitize_explanation("First sentence. Second sentence.") == "First sentence."

    def test_strips_after_newline(self):
        mod = _load_module()
        assert mod._sanitize_explanation("First line.\nSecond line.") == "First line."

    def test_truncates_long_text(self):
        mod = _load_module()
        long_text = "A" * 300
        result = mod._sanitize_explanation(long_text)
        assert len(result) <= 200

    def test_returns_none_for_empty(self):
        mod = _load_module()
        assert mod._sanitize_explanation("") is None
        assert mod._sanitize_explanation("   ") is None

    def test_preserves_short_single_sentence(self):
        mod = _load_module()
        assert mod._sanitize_explanation("Removes temporary files.") == "Removes temporary files."
