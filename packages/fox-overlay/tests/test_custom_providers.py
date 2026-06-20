"""Tests for fox_overlay.webui_modules.custom_providers — /api/settings/custom-providers (#144)."""
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
    config = types.ModuleType("api.config")

    def _j(handler, data, status=200):
        body = json.dumps(data).encode()
        handler.send_response(status)
        handler.send_header("Content-Type", "application/json")
        handler.end_headers()
        handler._body = body

    def _read_body(handler):
        return handler._request_body

    helpers.j = _j
    helpers.read_body = _read_body
    api.helpers = helpers

    import threading
    config._cfg_lock = threading.Lock()
    config._config_store = {"custom_providers": []}

    def _get_config_path():
        return "/fake/config.yaml"

    def _load_yaml_config_file(path):
        import copy
        return copy.deepcopy(config._config_store)

    def _save_yaml_config_file(path, cfg):
        import copy
        config._config_store = copy.deepcopy(cfg)

    def get_config():
        import copy
        return copy.deepcopy(config._config_store)

    config._get_config_path = _get_config_path
    config._load_yaml_config_file = _load_yaml_config_file
    config._save_yaml_config_file = _save_yaml_config_file
    config.get_config = get_config
    config.reload_config = lambda: None
    config.invalidate_models_cache = lambda: None

    api.config = config
    sys.modules["api"] = api
    sys.modules["api.helpers"] = helpers
    sys.modules["api.config"] = config


@pytest.fixture(autouse=True)
def _upstream():
    _stub_upstream()
    from fox_overlay import dispatch
    dispatch._GET_TABLE.clear()
    dispatch._POST_TABLE.clear()
    dispatch._BootstrapState.frozen = False
    yield
    sys.modules.pop("fox_overlay.webui_modules.custom_providers", None)


def _load_module():
    sys.modules.pop("fox_overlay.webui_modules.custom_providers", None)
    import fox_overlay.webui_modules as _pkg
    if hasattr(_pkg, "custom_providers"):
        delattr(_pkg, "custom_providers")
    from fox_overlay.webui_modules import custom_providers
    return custom_providers


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


def _set_providers(entries):
    sys.modules["api.config"]._config_store["custom_providers"] = entries


class TestRegistration:
    def test_registers_get_handler(self):
        _load_module()
        from fox_overlay.dispatch import GET_TABLE
        assert "/api/settings/custom-providers" in GET_TABLE

    def test_registers_post_handler(self):
        _load_module()
        from fox_overlay.dispatch import POST_TABLE
        assert "/api/settings/custom-providers" in POST_TABLE


class TestGetProviders:
    def test_empty_list(self):
        mod = _load_module()
        result = mod.get_providers_list()
        assert result["ok"] is True
        assert result["providers"] == []

    def test_returns_providers_with_masked_keys(self):
        _set_providers([
            {"name": "Local LLM", "base_url": "http://localhost:8080/v1", "api_key": "sk-secret-123", "models": ["llama3"]},
            {"name": "No Key", "base_url": "http://example.com/v1", "models": ["gpt4"]},
        ])
        mod = _load_module()
        result = mod.get_providers_list()
        assert result["ok"] is True
        assert len(result["providers"]) == 2
        assert result["providers"][0]["api_key"] == "****"
        assert result["providers"][0]["name"] == "Local LLM"
        assert result["providers"][1]["api_key"] == ""

    def test_get_handler_dispatches(self):
        _set_providers([{"name": "Test", "base_url": "http://x/v1", "models": ["m1"]}])
        mod = _load_module()
        handler = _make_handler()
        assert mod._handle_get(handler, _parsed("/api/settings/custom-providers")) is True
        body = json.loads(handler._body)
        assert body["ok"] is True
        assert len(body["providers"]) == 1

    def test_get_declines_wrong_path(self):
        mod = _load_module()
        handler = _make_handler()
        assert mod._handle_get(handler, _parsed("/api/settings/custom-providersX")) is False


class TestUpsertProvider:
    def test_add_valid_provider(self):
        mod = _load_module()
        result = mod.upsert_provider({
            "name": "My LLM",
            "base_url": "http://192.168.1.10:8080/v1",
            "models": ["llama3", "phi4"],
        })
        assert result["ok"] is True
        stored = sys.modules["api.config"]._config_store["custom_providers"]
        assert len(stored) == 1
        assert stored[0]["name"] == "My LLM"
        assert stored[0]["base_url"] == "http://192.168.1.10:8080/v1"
        assert stored[0]["models"] == ["llama3", "phi4"]
        assert "api_key" not in stored[0]

    def test_add_with_api_key(self):
        mod = _load_module()
        result = mod.upsert_provider({
            "name": "Keyed",
            "base_url": "https://api.example.com/v1",
            "api_key": "sk-test-key-123",
            "models": ["model1"],
        })
        assert result["ok"] is True
        stored = sys.modules["api.config"]._config_store["custom_providers"]
        assert stored[0]["api_key"] == "sk-test-key-123"

    def test_update_existing_provider(self):
        _set_providers([
            {"name": "My LLM", "base_url": "http://old/v1", "models": ["old-model"]},
        ])
        mod = _load_module()
        result = mod.upsert_provider({
            "name": "My LLM",
            "base_url": "http://new/v1",
            "models": ["new-model"],
        })
        assert result["ok"] is True
        stored = sys.modules["api.config"]._config_store["custom_providers"]
        assert len(stored) == 1
        assert stored[0]["base_url"] == "http://new/v1"
        assert stored[0]["models"] == ["new-model"]

    def test_update_preserves_key_when_masked(self):
        _set_providers([
            {"name": "Keyed", "base_url": "http://x/v1", "api_key": "real-secret", "models": ["m1"]},
        ])
        mod = _load_module()
        result = mod.upsert_provider({
            "name": "Keyed",
            "base_url": "http://x/v1",
            "api_key": "****",
            "models": ["m1", "m2"],
        })
        assert result["ok"] is True
        stored = sys.modules["api.config"]._config_store["custom_providers"]
        assert stored[0]["api_key"] == "real-secret"

    def test_rejects_empty_name(self):
        mod = _load_module()
        result = mod.upsert_provider({"name": "", "base_url": "http://x/v1", "models": ["m"]})
        assert result["ok"] is False
        assert "required" in result["error"].lower()

    def test_rejects_invalid_url_scheme(self):
        mod = _load_module()
        result = mod.upsert_provider({"name": "Bad", "base_url": "ftp://evil/v1", "models": ["m"]})
        assert result["ok"] is False
        assert "http" in result["error"].lower()

    def test_rejects_empty_models(self):
        mod = _load_module()
        result = mod.upsert_provider({"name": "Bad", "base_url": "http://x/v1", "models": []})
        assert result["ok"] is False
        assert "model" in result["error"].lower()

    def test_strips_trailing_slash_from_url(self):
        mod = _load_module()
        mod.upsert_provider({"name": "T", "base_url": "http://x:8080/v1/", "models": ["m"]})
        stored = sys.modules["api.config"]._config_store["custom_providers"]
        assert stored[0]["base_url"] == "http://x:8080/v1"

    def test_case_insensitive_name_matching(self):
        _set_providers([{"name": "My LLM", "base_url": "http://x/v1", "models": ["m"]}])
        mod = _load_module()
        mod.upsert_provider({"name": "my llm", "base_url": "http://y/v1", "models": ["n"]})
        stored = sys.modules["api.config"]._config_store["custom_providers"]
        assert len(stored) == 1
        assert stored[0]["base_url"] == "http://y/v1"


class TestDeleteProvider:
    def test_delete_existing(self):
        _set_providers([
            {"name": "Keep", "base_url": "http://a/v1", "models": ["m"]},
            {"name": "Remove", "base_url": "http://b/v1", "models": ["m"]},
        ])
        mod = _load_module()
        result = mod.delete_provider({"name": "Remove"})
        assert result["ok"] is True
        stored = sys.modules["api.config"]._config_store["custom_providers"]
        assert len(stored) == 1
        assert stored[0]["name"] == "Keep"

    def test_delete_nonexistent(self):
        mod = _load_module()
        result = mod.delete_provider({"name": "ghost"})
        assert result["ok"] is False
        assert "not found" in result["error"].lower()

    def test_delete_handler_dispatches(self):
        _set_providers([{"name": "X", "base_url": "http://x/v1", "models": ["m"]}])
        mod = _load_module()
        handler = _make_handler({"name": "X"})
        assert mod._handle_post(handler, _parsed("/api/settings/custom-providers/delete")) is True
        body = json.loads(handler._body)
        assert body["ok"] is True


class TestTestProvider:
    def test_rejects_invalid_url(self):
        mod = _load_module()
        result = mod.test_provider({"base_url": "not-a-url"})
        assert result["ok"] is False

    def test_successful_probe(self):
        mod = _load_module()
        response_data = json.dumps({"data": [{"id": "m1"}, {"id": "m2"}]}).encode()
        mock_resp = mock.MagicMock()
        mock_resp.read.return_value = response_data
        mock_resp.__enter__ = mock.Mock(return_value=mock_resp)
        mock_resp.__exit__ = mock.Mock(return_value=False)
        with mock.patch.object(mod.urllib.request, "urlopen", return_value=mock_resp):
            result = mod.test_provider({"base_url": "http://localhost:8080/v1"})
        assert result["ok"] is True
        assert result["models_found"] == 2

    def test_connection_refused(self):
        mod = _load_module()
        import urllib.error
        with mock.patch.object(mod.urllib.request, "urlopen", side_effect=urllib.error.URLError("Connection refused")):
            result = mod.test_provider({"base_url": "http://localhost:9999/v1"})
        assert result["ok"] is False
        assert "connection" in result["error"].lower()

    def test_auth_error(self):
        mod = _load_module()
        import urllib.error
        with mock.patch.object(mod.urllib.request, "urlopen", side_effect=urllib.error.HTTPError(
            "http://x/models", 401, "Unauthorized", {}, None
        )):
            result = mod.test_provider({"base_url": "http://x/v1"})
        assert result["ok"] is False
        assert "auth" in result["error"].lower()

    def test_handler_dispatches(self):
        mod = _load_module()
        response_data = json.dumps({"data": []}).encode()
        mock_resp = mock.MagicMock()
        mock_resp.read.return_value = response_data
        mock_resp.__enter__ = mock.Mock(return_value=mock_resp)
        mock_resp.__exit__ = mock.Mock(return_value=False)
        handler = _make_handler({"base_url": "http://localhost:8080/v1"})
        with mock.patch.object(mod.urllib.request, "urlopen", return_value=mock_resp):
            assert mod._handle_post(handler, _parsed("/api/settings/custom-providers/test")) is True
        body = json.loads(handler._body)
        assert body["ok"] is True


class TestDispatchBoundary:
    def test_post_declines_wrong_path(self):
        mod = _load_module()
        handler = _make_handler()
        assert mod._handle_post(handler, _parsed("/api/settings/custom-providersX")) is False

    def test_post_handles_upsert(self):
        mod = _load_module()
        handler = _make_handler({"name": "X", "base_url": "http://x/v1", "models": ["m"]})
        assert mod._handle_post(handler, _parsed("/api/settings/custom-providers")) is True
        body = json.loads(handler._body)
        assert body["ok"] is True

    def test_post_returns_400_on_validation_error(self):
        mod = _load_module()
        handler = _make_handler({"name": "", "base_url": "http://x/v1", "models": ["m"]})
        assert mod._handle_post(handler, _parsed("/api/settings/custom-providers")) is True
        assert handler._status == 400
