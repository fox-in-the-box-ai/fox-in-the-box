"""Tests for fox_overlay.webui_modules._body_shape.require_object_body (#901).

A valid-JSON-but-non-object body (list / bare string / number / bool / null)
must produce a clean 400 and return None, not be passed through to a handler
that will crash on ``.get(...)``. A JSON object (including the empty ``{}``)
passes through unchanged.
"""

import sys
import types

import pytest


@pytest.fixture
def stub_helpers(monkeypatch):
    """Stub api.helpers with j/bad/read_body fakes that record on the handler.

    read_body is driven per-handler via handler._body so each test can feed a
    specific parsed shape.
    """
    helpers = types.ModuleType("api.helpers")

    def _j(handler, payload, status=200, extra_headers=None):
        handler.responses.append({"status": status, "payload": payload})

    def _bad(handler, msg, status=400):
        _j(handler, {"error": msg}, status=status)

    def _read_body(handler):
        return handler._body

    helpers.j = _j
    helpers.bad = _bad
    helpers.read_body = _read_body

    api = types.ModuleType("api")
    api.helpers = helpers
    monkeypatch.setitem(sys.modules, "api", api)
    monkeypatch.setitem(sys.modules, "api.helpers", helpers)
    yield


class _FakeHandler:
    def __init__(self, body):
        self._body = body
        self.responses = []


def _require(body):
    from fox_overlay.webui_modules._body_shape import require_object_body

    h = _FakeHandler(body)
    return h, require_object_body(h)


@pytest.mark.parametrize(
    "body",
    [
        [1, 2, 3],
        ["x"],
        "astring",
        42,
        3.14,
        True,
        None,
    ],
)
def test_non_object_body_writes_400_and_returns_none(stub_helpers, body):
    h, result = _require(body)
    assert result is None
    assert h.responses[-1]["status"] == 400
    assert h.responses[-1]["payload"] == {"error": "Request body must be a JSON object"}


def test_object_body_passes_through(stub_helpers):
    h, result = _require({"key": "v"})
    assert result == {"key": "v"}
    assert h.responses == []  # no error written


def test_empty_object_body_passes_through(stub_helpers):
    h, result = _require({})
    assert result == {}
    assert h.responses == []
