"""Tests for fox_overlay.webui_modules.skillset — /skillset endpoint (INST-04)."""
from __future__ import annotations

import json
import sys
import types
from types import SimpleNamespace
from unittest import mock

import pytest


def _stub_upstream():
    api = types.ModuleType("api")
    auth = types.ModuleType("api.auth")
    auth.PUBLIC_PATHS = frozenset({"/login", "/health"})
    config = types.ModuleType("api.config")
    config.load_settings = lambda: {}
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


@pytest.fixture(autouse=True)
def _upstream():
    _stub_upstream()
    from fox_overlay import dispatch
    dispatch._GET_TABLE.clear()
    dispatch._POST_TABLE.clear()
    dispatch._BootstrapState.frozen = False
    yield
    sys.modules.pop("fox_overlay.webui_modules.skillset", None)


def _load_skillset():
    sys.modules.pop("fox_overlay.webui_modules.skillset", None)
    import fox_overlay.webui_modules as _pkg
    if hasattr(_pkg, "skillset"):
        delattr(_pkg, "skillset")
    from fox_overlay.webui_modules import skillset
    return skillset


def _make_handler():
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


_SAMPLE_MANIFEST = """\
name: fox-assistant
version: "1.0.0"
contract_version: "2.0.0"

persona:
  system_prompt_file: SOUL.md

tools:
  - name: web_search
    type: builtin

data_sources:
  - binding: customer_knowledge
    query_mode: rag
  - binding: product_docs
    query_mode: function_call

capabilities:
  local_fallback: true
  ollama: true
  web_search: true
  data_plane_access: true
  file_upload: false
"""

_MINIMAL_MANIFEST = """\
name: minimal
version: "0.1.0"
contract_version: "2.0.0"
"""


class TestRegistration:
    def test_registers_get_handler(self):
        _load_skillset()
        from fox_overlay.dispatch import GET_TABLE
        assert "/skillset" in GET_TABLE

    def test_no_post_handler(self):
        _load_skillset()
        from fox_overlay.dispatch import POST_TABLE
        assert "/skillset" not in POST_TABLE

    def test_does_not_expand_public_paths(self):
        auth_mod = sys.modules["api.auth"]
        _load_skillset()
        assert "/skillset" not in auth_mod.PUBLIC_PATHS


class TestHandler:
    def test_handles_skillset_path(self):
        mod = _load_skillset()
        handler = _make_handler()
        with mock.patch("builtins.open", mock.mock_open(read_data=_SAMPLE_MANIFEST)):
            assert mod._handle_get(handler, _parsed("/skillset")) is True

    def test_declines_non_skillset(self):
        mod = _load_skillset()
        handler = _make_handler()
        assert mod._handle_get(handler, _parsed("/skillsetX")) is False
        assert mod._handle_get(handler, _parsed("/skillset/extra")) is False
        assert mod._handle_get(handler, _parsed("/health")) is False

    def test_returns_404_when_no_manifest(self):
        mod = _load_skillset()
        handler = _make_handler()
        with mock.patch("builtins.open", side_effect=FileNotFoundError):
            mod._handle_get(handler, _parsed("/skillset"))
        assert handler._status == 404
        body = json.loads(handler._body)
        assert "error" in body

    def test_returns_200_with_manifest(self):
        mod = _load_skillset()
        handler = _make_handler()
        with mock.patch("builtins.open", mock.mock_open(read_data=_SAMPLE_MANIFEST)):
            mod._handle_get(handler, _parsed("/skillset"))
        assert handler._status == 200


class TestGetSkillset:
    def test_returns_none_when_no_file(self):
        mod = _load_skillset()
        with mock.patch("builtins.open", side_effect=FileNotFoundError):
            assert mod.get_skillset() is None

    def test_returns_none_for_invalid_yaml(self):
        mod = _load_skillset()
        with mock.patch("builtins.open", mock.mock_open(read_data=": invalid: yaml: [")):
            assert mod.get_skillset() is None

    def test_returns_none_for_yaml_without_name(self):
        mod = _load_skillset()
        with mock.patch("builtins.open", mock.mock_open(read_data="version: '1.0'\n")):
            assert mod.get_skillset() is None

    def test_response_shape(self):
        mod = _load_skillset()
        with mock.patch("builtins.open", mock.mock_open(read_data=_SAMPLE_MANIFEST)):
            result = mod.get_skillset()
        assert result is not None
        assert set(result.keys()) == {"name", "version", "contract_version", "data_sources", "capabilities_declared"}

    def test_extracts_name_and_version(self):
        mod = _load_skillset()
        with mock.patch("builtins.open", mock.mock_open(read_data=_SAMPLE_MANIFEST)):
            result = mod.get_skillset()
        assert result["name"] == "fox-assistant"
        assert result["version"] == "1.0.0"
        assert result["contract_version"] == "2.0.0"

    def test_extracts_data_source_bindings(self):
        mod = _load_skillset()
        with mock.patch("builtins.open", mock.mock_open(read_data=_SAMPLE_MANIFEST)):
            result = mod.get_skillset()
        assert result["data_sources"] == ["customer_knowledge", "product_docs"]

    def test_extracts_declared_capabilities(self):
        mod = _load_skillset()
        with mock.patch("builtins.open", mock.mock_open(read_data=_SAMPLE_MANIFEST)):
            result = mod.get_skillset()
        assert set(result["capabilities_declared"]) == {"local_fallback", "ollama", "web_search", "data_plane_access"}
        assert "file_upload" not in result["capabilities_declared"]

    def test_minimal_manifest_has_empty_lists(self):
        mod = _load_skillset()
        with mock.patch("builtins.open", mock.mock_open(read_data=_MINIMAL_MANIFEST)):
            result = mod.get_skillset()
        assert result["data_sources"] == []
        assert result["capabilities_declared"] == []

    def test_custom_path_from_env(self):
        mod = _load_skillset()
        env = {"FOX_SKILLSET_PATH": "/custom/skillset.yaml"}
        with mock.patch.dict("os.environ", env), \
             mock.patch("builtins.open", mock.mock_open(read_data=_MINIMAL_MANIFEST)) as m:
            result = mod.get_skillset()
        m.assert_called_once_with("/custom/skillset.yaml")
        assert result is not None

    def test_default_path(self):
        mod = _load_skillset()
        with mock.patch.dict("os.environ", {}, clear=True), \
             mock.patch("builtins.open", mock.mock_open(read_data=_MINIMAL_MANIFEST)) as m:
            mod.get_skillset()
        m.assert_called_once_with("/data/skillset.yaml")
