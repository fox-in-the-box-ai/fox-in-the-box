"""Phase 5 regression tests for fox_overlay.webui_modules.models_download.

First module to use dispatch.register_get/post with allow_bare=True.
Tests focus on the dispatcher integration shape, the path-parameter
extraction for sub-paths, and the explicit boundary check that allows
the wrapper to safely register at /api/local-models (bare prefix).
"""

import importlib
import sys

import pytest


@pytest.fixture
def fresh_dispatch_and_module(monkeypatch):
    """Reload dispatch + models_download module so register_* fires fresh."""
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
    fake_api = type(sys)("api")
    fake_api.helpers = fake_helpers
    monkeypatch.setitem(sys.modules, "api", fake_api)
    monkeypatch.setitem(sys.modules, "api.helpers", fake_helpers)

    import fox_overlay.dispatch as d

    importlib.reload(d)
    import fox_overlay.webui_modules.models_download as m

    importlib.reload(m)
    yield d, m
    importlib.reload(d)
    importlib.reload(m)


class _FakeHandler:
    def __init__(self, body=None):
        self._body = body or {}
        self.responses = []


# ── registration ────────────────────────────────────────────────────────────


def test_module_registers_bare_prefix(fresh_dispatch_and_module):
    """Dispatcher should accept the bare /api/local-models (no trailing slash)."""
    d, _m = fresh_dispatch_and_module
    assert "/api/local-models" in d.GET_TABLE
    assert "/api/local-models" in d.POST_TABLE


# ── GET routing ─────────────────────────────────────────────────────────────


def test_get_bare_path_routes_to_list(fresh_dispatch_and_module, monkeypatch):
    d, m = fresh_dispatch_and_module
    monkeypatch.setattr(m, "handle_get_models", lambda h: {"models": []})
    from urllib.parse import urlparse

    h = _FakeHandler()
    assert d.handle_get(h, urlparse("/api/local-models")) is True
    assert h.responses[-1]["payload"] == {"models": []}


def test_get_progress_sse_extracts_model_id_and_returns_handler_result(
    fresh_dispatch_and_module, monkeypatch
):
    d, m = fresh_dispatch_and_module
    captured = []

    def _sse(handler, model_id):
        captured.append(model_id)
        return True

    monkeypatch.setattr(m, "handle_progress_sse", _sse)
    from urllib.parse import urlparse

    h = _FakeHandler()
    assert d.handle_get(h, urlparse("/api/local-models/qwen2:1.5b/progress")) is True
    assert captured == ["qwen2:1.5b"]
    # SSE owns its response — wrapper does NOT call j()
    assert h.responses == []


def test_get_unknown_subpath_falls_through(fresh_dispatch_and_module):
    """e.g. /api/local-models/qwen2 (no /progress, no method) — wrapper returns False."""
    d, _m = fresh_dispatch_and_module
    from urllib.parse import urlparse

    h = _FakeHandler()
    assert d.handle_get(h, urlparse("/api/local-models/qwen2")) is False
    assert h.responses == []


def test_get_boundary_rejects_adjacent_paths(fresh_dispatch_and_module):
    """Critical safety check — allow_bare requires the wrapper to reject /api/local-modelsX."""
    d, _m = fresh_dispatch_and_module
    from urllib.parse import urlparse

    h = _FakeHandler()
    assert d.handle_get(h, urlparse("/api/local-modelsX")) is False
    assert d.handle_get(h, urlparse("/api/local-modelsattack")) is False
    assert d.handle_get(h, urlparse("/api/local-models-other")) is False
    assert h.responses == []


# ── POST routing ────────────────────────────────────────────────────────────


def test_post_download_routes_with_model_id(fresh_dispatch_and_module, monkeypatch):
    d, m = fresh_dispatch_and_module
    captured = []

    def _dl(handler, body, model_id):
        captured.append((model_id, body))
        return {"ok": True, "model_id": model_id}

    monkeypatch.setattr(m, "handle_post_download", _dl)
    from urllib.parse import urlparse

    h = _FakeHandler(body={"force": True})
    assert d.handle_post(h, urlparse("/api/local-models/llama3.2:1b/download")) is True
    assert captured == [("llama3.2:1b", {"force": True})]
    assert h.responses[-1] == {
        "status": 200,
        "payload": {"ok": True, "model_id": "llama3.2:1b"},
    }


def test_post_cancel_failure_status_400(fresh_dispatch_and_module, monkeypatch):
    d, m = fresh_dispatch_and_module
    monkeypatch.setattr(
        m,
        "handle_post_cancel",
        lambda h, body, mid: {"ok": False, "error": "no in-flight"},
    )
    from urllib.parse import urlparse

    h = _FakeHandler()
    assert d.handle_post(h, urlparse("/api/local-models/llama3/cancel")) is True
    assert h.responses[-1]["status"] == 400


def test_post_delete_routes_with_model_id(fresh_dispatch_and_module, monkeypatch):
    d, m = fresh_dispatch_and_module
    monkeypatch.setattr(
        m, "handle_post_delete", lambda h, body, mid: {"ok": True, "deleted": mid}
    )
    from urllib.parse import urlparse

    h = _FakeHandler()
    assert d.handle_post(h, urlparse("/api/local-models/llama3/delete")) is True
    assert h.responses[-1]["payload"] == {"ok": True, "deleted": "llama3"}


def test_post_unknown_action_falls_through(fresh_dispatch_and_module):
    """Action not in {download, cancel, delete} → False → upstream 404."""
    d, _m = fresh_dispatch_and_module
    from urllib.parse import urlparse

    h = _FakeHandler()
    assert d.handle_post(h, urlparse("/api/local-models/llama3/teleport")) is False


def test_post_malformed_no_action_falls_through(fresh_dispatch_and_module):
    """/api/local-models/llama3 (no action suffix) → False."""
    d, _m = fresh_dispatch_and_module
    from urllib.parse import urlparse

    h = _FakeHandler()
    assert d.handle_post(h, urlparse("/api/local-models/llama3")) is False


def test_post_bare_path_falls_through(fresh_dispatch_and_module):
    """POST /api/local-models (bare, no model_id) → False (only GET list, no POST list)."""
    d, _m = fresh_dispatch_and_module
    from urllib.parse import urlparse

    h = _FakeHandler()
    assert d.handle_post(h, urlparse("/api/local-models")) is False


def test_post_boundary_rejects_adjacent_paths(fresh_dispatch_and_module):
    """allow_bare requires the wrapper to reject /api/local-modelsX style adjacency."""
    d, _m = fresh_dispatch_and_module
    from urllib.parse import urlparse

    h = _FakeHandler()
    assert d.handle_post(h, urlparse("/api/local-modelsX/download")) is False
    assert d.handle_post(h, urlparse("/api/local-modelsattack")) is False


# ── model_id parsing edge cases ─────────────────────────────────────────────


def test_post_model_id_with_slashes_in_name(fresh_dispatch_and_module, monkeypatch):
    """rsplit('/', 1) — model_id can contain slashes (e.g. namespace/name)."""
    d, m = fresh_dispatch_and_module
    captured = []
    monkeypatch.setattr(
        m,
        "handle_post_download",
        lambda h, body, mid: captured.append(mid) or {"ok": True},
    )
    from urllib.parse import urlparse

    h = _FakeHandler()
    assert (
        d.handle_post(h, urlparse("/api/local-models/qwen/2.5/1.5b/download")) is True
    )
    assert captured == ["qwen/2.5/1.5b"]


def test_get_progress_model_id_with_slashes(fresh_dispatch_and_module, monkeypatch):
    """SSE model_id extraction preserves slashes too."""
    d, m = fresh_dispatch_and_module
    captured = []
    monkeypatch.setattr(
        m, "handle_progress_sse", lambda h, mid: captured.append(mid) or True
    )
    from urllib.parse import urlparse

    h = _FakeHandler()
    assert d.handle_get(h, urlparse("/api/local-models/qwen/2.5/1.5b/progress")) is True
    assert captured == ["qwen/2.5/1.5b"]


# ── #910: fail-loud MODEL_SIZE_PHI4MINI coercion ─────────────────────────────


def _reload_clean(monkeypatch):
    """Reset dispatch + models_download to a clean, env-unset state so a
    mutated KNOWN_MODELS / failed reload does not leak into other tests."""
    monkeypatch.delenv("MODEL_SIZE_PHI4MINI", raising=False)
    import fox_overlay.dispatch as d

    importlib.reload(d)
    import fox_overlay.webui_modules.models_download as md

    importlib.reload(md)
    return md


def test_model_size_from_env_default(monkeypatch):
    monkeypatch.delenv("MODEL_SIZE_PHI4MINI", raising=False)
    from fox_overlay.webui_modules.models_download import _model_size_from_env

    assert _model_size_from_env("MODEL_SIZE_PHI4MINI", 2491874688) == 2491874688


def test_model_size_from_env_valid_override(monkeypatch):
    monkeypatch.setenv("MODEL_SIZE_PHI4MINI", "3000000000")
    from fox_overlay.webui_modules.models_download import _model_size_from_env

    assert _model_size_from_env("MODEL_SIZE_PHI4MINI", 2491874688) == 3000000000


def test_model_size_from_env_empty_is_default(monkeypatch):
    monkeypatch.setenv("MODEL_SIZE_PHI4MINI", "   ")
    from fox_overlay.webui_modules.models_download import _model_size_from_env

    assert _model_size_from_env("MODEL_SIZE_PHI4MINI", 2491874688) == 2491874688


@pytest.mark.parametrize(
    "garbage", ["2,491,874,688", "2491874688 bytes", "2.49e9", "0x9", "abc"]
)
def test_model_size_from_env_non_numeric_raises(monkeypatch, garbage):
    monkeypatch.setenv("MODEL_SIZE_PHI4MINI", garbage)
    from fox_overlay.webui_modules.models_download import _model_size_from_env

    with pytest.raises(ValueError) as exc:
        _model_size_from_env("MODEL_SIZE_PHI4MINI", 2491874688)
    assert "MODEL_SIZE_PHI4MINI" in str(exc.value)
    assert garbage in str(exc.value)


def test_known_models_reflects_valid_override(monkeypatch):
    """A valid numeric override still flows into KNOWN_MODELS at import."""
    import fox_overlay.dispatch as d

    importlib.reload(d)
    import fox_overlay.webui_modules.models_download as md

    monkeypatch.setenv("MODEL_SIZE_PHI4MINI", "12345")
    importlib.reload(md)
    try:
        assert md.KNOWN_MODELS["phi4-mini"]["size_bytes"] == 12345
    finally:
        _reload_clean(monkeypatch)


def test_known_models_import_raises_on_non_numeric(monkeypatch):
    """The bare int() used to crash at import; the helper now raises a
    ValueError naming the variable (bootstrap's guard degrades on it)."""
    import fox_overlay.dispatch as d

    importlib.reload(d)
    import fox_overlay.webui_modules.models_download as md

    monkeypatch.setenv("MODEL_SIZE_PHI4MINI", "2,491,874,688")
    try:
        with pytest.raises(ValueError) as exc:
            importlib.reload(md)
        assert "MODEL_SIZE_PHI4MINI" in str(exc.value)
    finally:
        _reload_clean(monkeypatch)
