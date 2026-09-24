"""Tests for mem0_oss memory-tool dispatch (#911).

Model-supplied tool-call arguments are untrusted deserialized input. A
malformed ``top_k``/``query``/``content`` must degrade to a clean
``tool_error`` or a safe default — it must NEVER raise and must NEVER trip
the circuit breaker (a formatting mistake is not a backend outage).

Fakes, not mocks (spine §8.3): ``_get_memory`` is replaced by a hand-rolled
fake that records the ``top_k`` it was called with.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Make forks/hermes-agent importable regardless of the caller's PYTHONPATH.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_HERMES_AGENT = _REPO_ROOT / "forks" / "hermes-agent"
if _HERMES_AGENT.is_dir() and str(_HERMES_AGENT) not in sys.path:
    sys.path.insert(0, str(_HERMES_AGENT))

pytest.importorskip(
    "hermes_cli.providers",
    reason="forks/hermes-agent not importable in this environment",
)

plugin = pytest.importorskip("agent_memory_plugins.mem0_oss")

from agent_memory_plugins.mem0_oss import Mem0OSSMemoryProvider  # noqa: E402


class _FakeMemory:
    """Records the args it was called with; returns deterministic results."""

    def __init__(self):
        self.search_calls = []
        self.add_calls = []

    def search(self, query, top_k, filters):
        self.search_calls.append({"query": query, "top_k": top_k, "filters": filters})
        return {"results": [{"memory": "recalled fact"}]}

    def add(self, messages, user_id, infer):
        self.add_calls.append({"messages": messages, "user_id": user_id})


def _provider():
    provider = Mem0OSSMemoryProvider()
    fake = _FakeMemory()
    provider._get_memory = lambda: fake
    provider._user_id = "hermes-user"
    provider._top_k = 10
    return provider, fake


def _is_tool_error(payload: str) -> bool:
    return "error" in json.loads(payload)


class TestSearchArgCoercion:
    @pytest.mark.parametrize("bad_top_k", ["10.0", "ten", None, [], {}])
    def test_non_numeric_top_k_falls_back_to_default(self, bad_top_k):
        provider, fake = _provider()
        out = provider._handle_search({"query": "x", "top_k": bad_top_k})
        assert not _is_tool_error(out)
        assert fake.search_calls[0]["top_k"] == provider._top_k

    def test_negative_top_k_clamps_to_one(self):
        provider, fake = _provider()
        provider._handle_search({"query": "x", "top_k": "-5"})
        assert fake.search_calls[0]["top_k"] == 1

    def test_zero_top_k_clamps_to_one(self):
        provider, fake = _provider()
        provider._handle_search({"query": "x", "top_k": 0})
        assert fake.search_calls[0]["top_k"] == 1

    def test_high_top_k_clamps_to_fifty(self):
        provider, fake = _provider()
        provider._handle_search({"query": "x", "top_k": 100})
        assert fake.search_calls[0]["top_k"] == 50

    def test_valid_numeric_string_top_k_coerces(self):
        provider, fake = _provider()
        provider._handle_search({"query": "x", "top_k": "3"})
        assert fake.search_calls[0]["top_k"] == 3

    def test_absent_top_k_uses_default(self):
        provider, fake = _provider()
        provider._handle_search({"query": "x"})
        assert fake.search_calls[0]["top_k"] == provider._top_k

    @pytest.mark.parametrize("bad_query", [5, None, [], {"a": 1}])
    def test_non_string_query_returns_tool_error(self, bad_query):
        provider, fake = _provider()
        out = provider._handle_search({"query": bad_query})
        assert _is_tool_error(out)
        assert fake.search_calls == []  # never runs a garbage search

    def test_empty_query_still_rejected(self):
        provider, fake = _provider()
        assert _is_tool_error(provider._handle_search({"query": "   "}))
        assert fake.search_calls == []


class TestAddArgCoercion:
    @pytest.mark.parametrize("bad_content", [5, None, [], {"a": 1}])
    def test_non_string_content_returns_tool_error(self, bad_content):
        provider, fake = _provider()
        out = provider._handle_add({"content": bad_content})
        assert _is_tool_error(out)
        assert fake.add_calls == []

    def test_valid_content_stores(self):
        provider, fake = _provider()
        out = provider._handle_add({"content": "remember this"})
        assert not _is_tool_error(out)
        assert fake.add_calls[0]["messages"][0]["content"] == "remember this"


class TestNoBreakerTripOnMalformedArgs:
    """A malformed arg must not call _record_failure / trip the breaker."""

    @pytest.mark.parametrize(
        "args",
        [
            {"query": 5},
            {"query": None},
            {"query": "x", "top_k": "10.0"},
            {"query": "x", "top_k": None},
        ],
    )
    def test_search_never_raises_and_keeps_breaker_at_zero(self, args):
        provider, _ = _provider()
        out = provider._handle_search(args)  # must not raise
        assert isinstance(out, str)
        assert provider._fail_count == 0

    @pytest.mark.parametrize("args", [{"content": 5}, {"content": None}, {}])
    def test_add_never_raises_and_keeps_breaker_at_zero(self, args):
        provider, _ = _provider()
        out = provider._handle_add(args)  # must not raise
        assert isinstance(out, str)
        assert provider._fail_count == 0
