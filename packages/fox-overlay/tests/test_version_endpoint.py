"""Tests for fox_overlay.webui_modules.version — /version endpoint (INST-02)."""
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
    sys.modules.pop("fox_overlay.webui_modules.version", None)


def _load_version():
    sys.modules.pop("fox_overlay.webui_modules.version", None)
    import fox_overlay.webui_modules as _pkg
    if hasattr(_pkg, "version"):
        delattr(_pkg, "version")
    from fox_overlay.webui_modules import version
    return version


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
        _load_version()
        from fox_overlay.dispatch import GET_TABLE
        assert "/version" in GET_TABLE

    def test_no_post_handler(self):
        _load_version()
        from fox_overlay.dispatch import POST_TABLE
        assert "/version" not in POST_TABLE

    def test_does_not_expand_public_paths(self):
        auth_mod = sys.modules["api.auth"]
        _load_version()
        assert "/version" not in auth_mod.PUBLIC_PATHS


class TestHandler:
    def test_handles_version_path(self):
        mod = _load_version()
        handler = _make_handler()
        assert mod._handle_get(handler, _parsed("/version")) is True

    def test_declines_non_version(self):
        mod = _load_version()
        handler = _make_handler()
        assert mod._handle_get(handler, _parsed("/versionX")) is False
        assert mod._handle_get(handler, _parsed("/version/extra")) is False
        assert mod._handle_get(handler, _parsed("/health")) is False

    def test_response_shape(self):
        mod = _load_version()
        handler = _make_handler()
        mod._handle_get(handler, _parsed("/version"))
        body = json.loads(handler._body)
        assert "contract_version" in body
        assert "image_digest" in body
        assert "runtime" in body
        assert "runtime_version" in body
        assert "overlay_version" in body


class TestGetVersion:
    def test_contract_version(self):
        mod = _load_version()
        result = mod.get_version()
        assert result["contract_version"] == "2.0.0"

    def test_runtime_is_hermes(self):
        mod = _load_version()
        result = mod.get_version()
        assert result["runtime"] == "hermes"

    def test_image_digest_from_env(self):
        mod = _load_version()
        with mock.patch.dict("os.environ", {"FITB_IMAGE_DIGEST": "sha256:abc123"}):
            result = mod.get_version()
        assert result["image_digest"] == "sha256:abc123"

    def test_image_digest_empty_when_not_set(self):
        mod = _load_version()
        with mock.patch.dict("os.environ", {}, clear=True):
            result = mod.get_version()
        assert result["image_digest"] == ""

    def test_runtime_version_from_api_updates(self):
        mod = _load_version()
        updates_mod = types.ModuleType("api.updates")
        updates_mod.WEBUI_VERSION = "v0.51.145"
        with mock.patch.dict("sys.modules", {"api.updates": updates_mod}):
            result = mod.get_version()
        assert result["runtime_version"] == "v0.51.145"

    def test_runtime_version_unknown_when_no_updates(self):
        mod = _load_version()
        with mock.patch.dict("sys.modules", {}, clear=False):
            sys.modules.pop("api.updates", None)
            result = mod.get_version()
        assert result["runtime_version"] == "unknown"

    def test_overlay_version_from_package(self):
        mod = _load_version()
        with mock.patch("importlib.metadata.version", return_value="0.7.44"):
            result = mod.get_version()
        assert result["overlay_version"] == "0.7.44"

    def test_overlay_version_from_file_fallback(self):
        mod = _load_version()
        with mock.patch("importlib.metadata.version", side_effect=Exception("not installed")), \
             mock.patch("builtins.open", mock.mock_open(read_data="v0.7.44\n")):
            result = mod.get_version()
        assert result["overlay_version"] == "v0.7.44"

    def test_overlay_version_unknown_fallback(self):
        mod = _load_version()
        with mock.patch("importlib.metadata.version", side_effect=Exception("not installed")), \
             mock.patch("builtins.open", side_effect=FileNotFoundError):
            result = mod.get_version()
        assert result["overlay_version"] == "unknown"
