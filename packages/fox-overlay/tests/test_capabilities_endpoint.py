"""Tests for fox_overlay.webui_modules.capabilities — /capabilities endpoint (INST-03)."""
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
    sys.modules.setdefault("api", api)
    sys.modules.setdefault("api.auth", auth)
    sys.modules.setdefault("api.config", config)
    sys.modules.setdefault("api.helpers", helpers)


@pytest.fixture(autouse=True)
def _upstream():
    _stub_upstream()
    from fox_overlay import dispatch
    dispatch._GET_TABLE.clear()
    dispatch._POST_TABLE.clear()
    dispatch._BootstrapState.frozen = False
    yield
    sys.modules.pop("fox_overlay.webui_modules.capabilities", None)


def _load_capabilities():
    sys.modules.pop("fox_overlay.webui_modules.capabilities", None)
    import fox_overlay.webui_modules as _pkg
    if hasattr(_pkg, "capabilities"):
        delattr(_pkg, "capabilities")
    from fox_overlay.webui_modules import capabilities
    return capabilities


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


class TestRegistration:
    def test_registers_get_handler(self):
        _load_capabilities()
        from fox_overlay.dispatch import GET_TABLE
        assert "/capabilities" in GET_TABLE

    def test_no_post_handler(self):
        _load_capabilities()
        from fox_overlay.dispatch import POST_TABLE
        assert "/capabilities" not in POST_TABLE

    def test_does_not_expand_public_paths(self):
        auth_mod = sys.modules["api.auth"]
        _load_capabilities()
        assert "/capabilities" not in auth_mod.PUBLIC_PATHS


class TestHandler:
    def test_handles_capabilities_path(self):
        mod = _load_capabilities()
        handler = _make_handler()
        assert mod._handle_get(handler, _parsed("/capabilities")) is True

    def test_declines_non_capabilities(self):
        mod = _load_capabilities()
        handler = _make_handler()
        assert mod._handle_get(handler, _parsed("/capabilitiesX")) is False
        assert mod._handle_get(handler, _parsed("/capabilities/extra")) is False
        assert mod._handle_get(handler, _parsed("/health")) is False

    def test_response_shape(self):
        mod = _load_capabilities()
        handler = _make_handler()
        mod._handle_get(handler, _parsed("/capabilities"))
        body = json.loads(handler._body)
        assert "contract_version" in body
        assert "capabilities" in body
        assert isinstance(body["capabilities"], dict)


class TestGetCapabilities:
    def test_contract_version(self):
        mod = _load_capabilities()
        result = mod.get_capabilities()
        assert result["contract_version"] == "2.0.0"

    def test_capabilities_are_booleans(self):
        mod = _load_capabilities()
        result = mod.get_capabilities()
        for key, value in result["capabilities"].items():
            assert isinstance(value, bool), f"{key} is {type(value)}, expected bool"

    def test_expected_capability_keys(self):
        mod = _load_capabilities()
        result = mod.get_capabilities()
        expected = {
            "local_fallback", "tailscale", "ollama", "web_search",
            "file_upload", "cron_jobs", "model_download", "data_plane_access",
        }
        assert set(result["capabilities"].keys()) == expected

    def test_data_plane_not_yet_supported(self):
        mod = _load_capabilities()
        result = mod.get_capabilities()
        assert result["capabilities"]["data_plane_access"] is False

    def test_local_fallback_reflects_module_availability(self):
        mod = _load_capabilities()
        with mock.patch.object(mod, "_has_module", side_effect=lambda n: n != "fox_overlay.webui_modules.local_fallback"):
            result = mod.get_capabilities()
        assert result["capabilities"]["local_fallback"] is False

    def test_tailscale_reflects_binary_availability(self):
        mod = _load_capabilities()
        with mock.patch("shutil.which", return_value=None):
            result = mod.get_capabilities()
        assert result["capabilities"]["tailscale"] is False

    def test_tailscale_true_when_binary_present(self):
        mod = _load_capabilities()
        with mock.patch("shutil.which", return_value="/usr/bin/tailscale"):
            result = mod.get_capabilities()
        assert result["capabilities"]["tailscale"] is True
