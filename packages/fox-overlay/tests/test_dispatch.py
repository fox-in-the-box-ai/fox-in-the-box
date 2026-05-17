"""Phase 4 regression tests for fox_overlay.dispatch.

Covers the contract documented in dispatch.py: prefix validation,
re-registration warning, freeze, handler return semantics, and the
dispatch fall-through behavior.
"""
import importlib
import logging
from types import SimpleNamespace

import pytest


@pytest.fixture
def dispatch():
    """Fresh dispatch module per test — clears tables and freeze state."""
    import fox_overlay.dispatch as d
    importlib.reload(d)
    yield d
    importlib.reload(d)


def _parsed(path: str):
    """Minimal stand-in for urllib.parse.ParseResult (only .path is read)."""
    return SimpleNamespace(path=path)


# ── prefix validation ───────────────────────────────────────────────────────

def test_register_get_accepts_well_formed_prefix(dispatch):
    dispatch.register_get("/api/fox/ollama/", lambda h, p: True)
    assert "/api/fox/ollama/" in dispatch.GET_TABLE


def test_register_post_accepts_well_formed_prefix(dispatch):
    dispatch.register_post("/api/fox/hostname/", lambda h, p: True)
    assert "/api/fox/hostname/" in dispatch.POST_TABLE


def test_register_rejects_prefix_without_leading_slash(dispatch):
    with pytest.raises(ValueError, match="must start with '/'"):
        dispatch.register_get("api/fox/", lambda h, p: True)


def test_register_rejects_prefix_without_trailing_slash(dispatch):
    with pytest.raises(ValueError, match="must end with '/'"):
        dispatch.register_get("/api/fox", lambda h, p: True)


def test_register_rejects_root_prefix(dispatch):
    with pytest.raises(ValueError, match="shadow every upstream route"):
        dispatch.register_get("/", lambda h, p: True)


@pytest.mark.parametrize(
    "public_prefix",
    [
        "/static/foo/",
        "/session/static/x/",
        "/login/",
        "/api/auth/login/",
        "/health/",
        "/favicon.ico/",
        "/sw.js/",
        "/manifest.json/",
    ],
)
def test_register_rejects_auth_public_overlap(dispatch, public_prefix):
    with pytest.raises(ValueError, match="auth-public namespace"):
        dispatch.register_get(public_prefix, lambda h, p: True)


def test_register_rejects_non_string(dispatch):
    with pytest.raises(TypeError):
        dispatch.register_get(123, lambda h, p: True)  # type: ignore[arg-type]


# ── re-registration warning ─────────────────────────────────────────────────

def test_reregister_warns(dispatch, caplog):
    dispatch.register_get("/api/fox/ping/", lambda h, p: True)
    with caplog.at_level(logging.WARNING, logger="fox_overlay.dispatch"):
        dispatch.register_get("/api/fox/ping/", lambda h, p: True)
    assert any("overwriting handler" in r.message for r in caplog.records)


# ── freeze ──────────────────────────────────────────────────────────────────

def test_freeze_blocks_subsequent_registration(dispatch):
    dispatch.register_get("/api/fox/ping/", lambda h, p: True)
    dispatch.freeze()
    with pytest.raises(RuntimeError, match="dispatcher table frozen"):
        dispatch.register_get("/api/fox/late/", lambda h, p: True)


def test_freeze_does_not_break_dispatch(dispatch):
    """Frozen tables must still be iterable and dispatchable."""
    dispatch.register_get("/api/fox/ping/", lambda h, p: True)
    dispatch.freeze()
    assert dispatch.handle_get(None, _parsed("/api/fox/ping/x")) is True


# ── dispatch behavior ──────────────────────────────────────────────────────

def test_dispatch_returns_false_for_unregistered_prefix(dispatch):
    assert dispatch.handle_get(None, _parsed("/not/registered/")) is False
    assert dispatch.handle_post(None, _parsed("/not/registered/")) is False


def test_dispatch_returns_true_when_handler_handles(dispatch):
    called = []
    def h(handler, parsed):
        called.append(parsed.path)
        return True
    dispatch.register_get("/api/fox/ping/", h)
    assert dispatch.handle_get(None, _parsed("/api/fox/ping/v1")) is True
    assert called == ["/api/fox/ping/v1"]


def test_dispatch_continues_when_handler_declines(dispatch):
    """Handler returning False means 'not mine'; dispatcher tries next prefix."""
    fox_calls = []
    other_calls = []
    def fox(handler, parsed):
        fox_calls.append(parsed.path)
        return False  # decline
    def other(handler, parsed):
        other_calls.append(parsed.path)
        return True
    dispatch.register_get("/api/fox/", fox)
    dispatch.register_get("/api/fox/specific/", other)
    # /api/fox/specific/x matches fox prefix first (insertion order); fox
    # declines, dispatcher moves to next prefix (other), other handles.
    assert dispatch.handle_get(None, _parsed("/api/fox/specific/x")) is True
    assert fox_calls == ["/api/fox/specific/x"]
    assert other_calls == ["/api/fox/specific/x"]


def test_dispatch_raises_on_none_return(dispatch):
    """Handler returning None is a contract violation — fail loud."""
    def buggy(handler, parsed):
        return None  # forgot `return True` after handling
    dispatch.register_get("/api/fox/buggy/", buggy)
    with pytest.raises(RuntimeError, match="must return True"):
        dispatch.handle_get(None, _parsed("/api/fox/buggy/x"))


def test_dispatch_raises_on_non_bool_return(dispatch):
    """Truthy non-bool returns (e.g. accidental dict/string) also fail loud."""
    def buggy(handler, parsed):
        return {"status": "ok"}
    dispatch.register_get("/api/fox/buggy/", buggy)
    with pytest.raises(RuntimeError, match="must return True"):
        dispatch.handle_get(None, _parsed("/api/fox/buggy/x"))


# ── read-only views ─────────────────────────────────────────────────────────

def test_get_table_view_is_read_only(dispatch):
    dispatch.register_get("/api/fox/x/", lambda h, p: True)
    with pytest.raises(TypeError):
        dispatch.GET_TABLE["/api/fox/x/"] = lambda h, p: False  # type: ignore[index]


def test_post_table_view_is_read_only(dispatch):
    dispatch.register_post("/api/fox/x/", lambda h, p: True)
    with pytest.raises(TypeError):
        dispatch.POST_TABLE["/api/fox/x/"] = lambda h, p: False  # type: ignore[index]
