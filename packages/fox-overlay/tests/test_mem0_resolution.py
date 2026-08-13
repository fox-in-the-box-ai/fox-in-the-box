"""Tests for the mem0_oss resolution core (design §a / §1.3 / §g.1).

These tests exercise the REAL resolution pipeline against the real
``hermes_cli.providers`` / ``hermes_cli.config`` / ``hermes_cli.auth``
modules from forks/hermes-agent (the repo has them checked out) — only the
network surfaces are stubbed:

  * ``agent.models_dev``     — pins the models.dev contract; no network
  * ``agent.credential_pool``— recording in-memory fake
  * ``agent.bedrock_adapter``— no AWS credentials by default
  * ``agent.auxiliary_client``— deterministic config.yaml readers
  * ``mem0`` / ``openai``    — behavioral fakes for the §1.3 truth table

Where forks/hermes-agent is not importable (e.g. the validate-overlay CI
context, which has neither the fork on PYTHONPATH nor httpx installed) the
whole module skips; the ``_WELL_KNOWN``/``_POOL_ID_MAP`` sync assertions run
in-image (image-selftest phase A), not here.
"""

from __future__ import annotations

import json
import os
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

# Make forks/hermes-agent importable regardless of the caller's PYTHONPATH.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_HERMES_AGENT = _REPO_ROOT / "forks" / "hermes-agent"
if _HERMES_AGENT.is_dir() and str(_HERMES_AGENT) not in sys.path:
    sys.path.insert(0, str(_HERMES_AGENT))

pytest.importorskip(
    "hermes_cli.providers",
    reason="forks/hermes-agent not importable in this environment "
    "(sync assertions run in-image; see design §g.1)",
)

plugin = pytest.importorskip("agent_memory_plugins.mem0_oss")

from agent_memory_plugins.mem0_oss import (  # noqa: E402
    MemoryUnavailable,
    ResolvedConfig,
    _LOCAL_EMBED_BASE_URL,
    _LOCAL_EMBED_MODEL,
)


# ── Environment fixture ────────────────────────────────────────────────


def _all_provider_env_vars():
    """Every env var chat's registry knows, plus the plugin's own."""
    variables = {
        "OPENAI_API_KEY",
        "OPENROUTER_API_KEY",
        "ANTHROPIC_API_KEY",
        "OPENAI_BASE_URL",
        "OPENROUTER_BASE_URL",
        "OLLAMA_BASE_URL",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_PROFILE",
        "AZURE_FOUNDRY_API_KEY",
        "AZURE_FOUNDRY_BASE_URL",
        "KIMI_BASE_URL",
        "HERMES_HOME",
    }
    variables.update(v for v in os.environ if v.startswith("MEM0_OSS_"))
    try:
        from hermes_cli.auth import PROVIDER_REGISTRY

        for pconfig in PROVIDER_REGISTRY.values():
            variables.update(getattr(pconfig, "api_key_env_vars", ()) or ())
            base_var = getattr(pconfig, "base_url_env_var", "")
            if base_var:
                variables.add(base_var)
    except Exception:
        pass
    return variables


class _FakePool:
    def __init__(self, entries):
        self._entries = list(entries)

    def has_credentials(self):
        return bool(self._entries)

    def peek(self):
        return self._entries[0] if self._entries else None


@pytest.fixture()
def env(monkeypatch, tmp_path):
    """Hermetic resolution environment: tmp HERMES_HOME, no provider env,
    stubbed network/pool/bedrock surfaces, reset plugin caches."""
    home = tmp_path / "hermes"
    home.mkdir()
    for var in sorted(_all_provider_env_vars()):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("HERMES_HOME", str(home))

    # models.dev stub — healthy-but-empty catalog by default (no network).
    models_dev = types.ModuleType("agent.models_dev")
    models_dev._catalog = {"openrouter": {"models": {}}}
    models_dev.get_provider_info = lambda provider_id: None
    models_dev.fetch_models_dev = lambda force_refresh=False: models_dev._catalog
    monkeypatch.setitem(sys.modules, "agent.models_dev", models_dev)

    # credential pool stub — empty, recording.
    pool_mod = types.ModuleType("agent.credential_pool")
    pool_mod._pools = {}
    pool_mod.calls = []

    def _load_pool(provider_id):
        pool_mod.calls.append(provider_id)
        return _FakePool(pool_mod._pools.get(provider_id, []))

    pool_mod.load_pool = _load_pool
    monkeypatch.setitem(sys.modules, "agent.credential_pool", pool_mod)

    # bedrock stub — no AWS credentials.
    bedrock = types.ModuleType("agent.bedrock_adapter")
    bedrock.has_aws_credentials = lambda env=None: False
    monkeypatch.setitem(sys.modules, "agent.bedrock_adapter", bedrock)

    # auxiliary_client stub — deterministic config.yaml readers (the real
    # module drags a large import surface; behavior mirrored exactly).
    aux = types.ModuleType("agent.auxiliary_client")

    def _read_main_provider():
        from hermes_cli.config import load_config

        model = (load_config() or {}).get("model") or {}
        if isinstance(model, dict):
            return str(model.get("provider", "") or "").strip().lower()
        return ""

    def _read_main_base_url():
        from hermes_cli.config import load_config

        model = (load_config() or {}).get("model") or {}
        if isinstance(model, dict):
            return str(model.get("base_url", "") or "").strip()
        return ""

    aux._read_main_provider = _read_main_provider
    aux._read_main_base_url = _read_main_base_url
    monkeypatch.setitem(sys.modules, "agent.auxiliary_client", aux)

    plugin._invalidate_memo()
    with plugin._memo_lock:
        plugin._embed_health_cache.update({"ts": 0.0, "ok": None})

    yield SimpleNamespace(
        home=home, models_dev=models_dev, pool=pool_mod, bedrock=bedrock
    )

    plugin._invalidate_memo()


def _write_config(home: Path, text: str) -> None:
    (home / "config.yaml").write_text(text, encoding="utf-8")


# ── State-table rows (design §a.2) ─────────────────────────────────────


class TestFlagshipRows:
    def test_openrouter_env_key_probe_ready(self, env, monkeypatch):
        """Row 1 via probe t3: OpenRouter-only install → READY offline
        (well-known base_url, no catalog needed) with the local embedder."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test-1234")
        resolved = plugin._resolve_memoized()
        assert resolved.provider_id == "openrouter"
        assert resolved.mem0_llm_provider == "openai"
        assert resolved.base_url == "https://openrouter.ai/api/v1"
        assert resolved.api_key == "sk-or-test-1234"
        assert resolved.llm_model == "openai/gpt-4o-mini"

        embedder = plugin._resolve_embedder({})
        assert embedder["is_local_default"] is True
        assert embedder["config"]["openai_base_url"] == _LOCAL_EMBED_BASE_URL
        assert embedder["config"]["api_key"] == "fox-local"
        assert "embedding_dims" not in embedder["config"]  # dims on store only
        assert embedder["store_dims"] == 768
        assert embedder["description"] == f"local:{_LOCAL_EMBED_MODEL}"

    def test_lone_openai_key_routes_to_openrouter_like_chat(self, env, monkeypatch):
        """Probe t3 mirrors chat: a lone OPENAI_API_KEY is an OpenRouter
        credential (auth.py auto-chain), never a guess at direct OpenAI."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-lone-openai-1234")
        resolved = plugin._resolve_memoized()
        assert resolved.provider_id == "openrouter"
        assert resolved.api_key == "sk-lone-openai-1234"

    def test_anthropic_only_ready(self, env, monkeypatch):
        """Row 2 via the explicit step-7 anthropic arm (transport is
        anthropic_messages — the 6b catch-all must not swallow it)."""
        _write_config(env.home, "model:\n  provider: anthropic\n")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-1234")
        resolved = plugin._resolve_memoized()
        assert resolved.provider_id == "anthropic"
        assert resolved.mem0_llm_provider == "anthropic"
        assert resolved.api_key == "sk-ant-test-1234"
        assert resolved.llm_model == "claude-haiku-4-5-20251001"

    def test_openai_api_direct_ready_via_well_known(self, env, monkeypatch):
        """Row 3: openai-api resolves its key via the §a.0 well-known row —
        the overlay has NO env vars and models.dev never matches this id."""
        _write_config(env.home, "model:\n  provider: openai-api\n")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-real-1234")
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-env")
        resolved = plugin._resolve_memoized()
        assert resolved.provider_id == "openai-api"
        assert resolved.base_url == "https://api.openai.com/v1"
        assert resolved.api_key == "sk-openai-real-1234"  # never the OR key


class TestLocalFamily:
    def test_ollama_with_main_base_url(self, env):
        _write_config(
            env.home,
            "model:\n  provider: ollama\n  base_url: http://127.0.0.1:11434/v1\n",
        )
        resolved = plugin._resolve_memoized()
        assert resolved.provider_id == "ollama"
        assert resolved.mem0_llm_provider == "openai"
        assert resolved.base_url == "http://127.0.0.1:11434/v1"  # verbatim
        assert resolved.api_key == "fox-local"

    def test_vllm_spelling_reaches_local_fallback(self, env):
        _write_config(
            env.home, "model:\n  provider: vllm\n  base_url: http://127.0.0.1:8000/v1\n"
        )
        resolved = plugin._resolve_memoized()
        assert resolved.provider_id == "vllm"
        assert resolved.base_url == "http://127.0.0.1:8000/v1"

    def test_ollama_env_fallback_appends_v1(self, env, monkeypatch):
        _write_config(env.home, "model:\n  provider: ollama\n")
        monkeypatch.setenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
        resolved = plugin._resolve_memoized()
        assert resolved.base_url == "http://127.0.0.1:11434/v1"

    def test_local_family_without_endpoint_is_explicit_error(self, env):
        _write_config(env.home, "model:\n  provider: llamacpp\n")
        with pytest.raises(MemoryUnavailable) as excinfo:
            plugin._resolve_memoized()
        assert excinfo.value.severity == "error"
        assert "local provider 'llamacpp'" in excinfo.value.reason


class TestOffStates:
    def test_no_provider_anywhere_is_visible_off(self, env):
        """State 6: reachable only when chat's own auto-chain would fail."""
        with pytest.raises(MemoryUnavailable) as excinfo:
            plugin._resolve_memoized()
        assert excinfo.value.severity == "off"
        assert "no provider configured and no credentials found" in excinfo.value.reason
        assert "Finish onboarding" in excinfo.value.reason

    def test_disabled_env_is_first_check(self, env, monkeypatch):
        """State 9 wins over everything, including a fully working config."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test-1234")
        monkeypatch.setenv("MEM0_OSS_DISABLED", "1")
        with pytest.raises(MemoryUnavailable) as excinfo:
            plugin._resolve_memoized()
        assert excinfo.value.severity == "off"
        assert excinfo.value.reason == "disabled (MEM0_OSS_DISABLED=1)"

    def test_oauth_provider_lands_in_6b_catch_all(self, env):
        _write_config(env.home, "model:\n  provider: openai-codex\n")
        with pytest.raises(MemoryUnavailable) as excinfo:
            plugin._resolve_memoized()
        assert excinfo.value.severity == "off"
        assert "doesn't support provider 'openai-codex'" in excinfo.value.reason


class TestCatalogDispositions:
    def test_catalog_unreachable_names_the_catalog(self, env):
        """5c id with empty env tuple + unreachable catalog → the explicit
        state-7 catalog reason, and NO IndexError (empty-tuple guard)."""
        env.models_dev._catalog = {}  # fetch_models_dev() → falsy = unreachable
        _write_config(env.home, "model:\n  provider: deepseek\n")
        with pytest.raises(MemoryUnavailable) as excinfo:
            plugin._resolve_memoized()
        assert excinfo.value.severity == "error"
        assert "models.dev" in excinfo.value.reason
        assert "unreachable and not cached" in excinfo.value.reason

    def test_catalog_healthy_id_absent_names_the_override(self, env):
        _write_config(env.home, "model:\n  provider: deepseek\n")
        with pytest.raises(MemoryUnavailable) as excinfo:
            plugin._resolve_memoized()
        assert excinfo.value.severity == "error"
        assert "no known API key variable" in excinfo.value.reason
        assert "MEM0_OSS_API_KEY" in excinfo.value.reason

    def test_missing_key_with_known_var_never_blames_catalog(self, env):
        """openrouter with no key: the reason names OPENROUTER_API_KEY and
        the credential pool, never the catalog."""
        _write_config(env.home, "model:\n  provider: openrouter\n")
        with pytest.raises(MemoryUnavailable) as excinfo:
            plugin._resolve_memoized()
        assert excinfo.value.severity == "error"
        assert "OPENROUTER_API_KEY" in excinfo.value.reason
        assert "hermes auth add" in excinfo.value.reason
        assert "models.dev" not in excinfo.value.reason


class TestAzureFoundry:
    def test_ready_with_both_env_vars(self, env, monkeypatch):
        """Openai-mode azure-foundry: key from the §a.0 well-known row, URL
        from the overlay's base_url_env_var — exactly the pair chat needs."""
        _write_config(env.home, "model:\n  provider: azure-foundry\n")
        monkeypatch.setenv("AZURE_FOUNDRY_API_KEY", "azf-key-1234")
        monkeypatch.setenv("AZURE_FOUNDRY_BASE_URL", "https://myinstance.example/v1")
        resolved = plugin._resolve_memoized()
        assert resolved.provider_id == "azure-foundry"
        assert resolved.api_key == "azf-key-1234"
        assert resolved.base_url == "https://myinstance.example/v1"

    def test_missing_url_names_the_url_var_not_the_catalog(self, env, monkeypatch):
        _write_config(env.home, "model:\n  provider: azure-foundry\n")
        monkeypatch.setenv("AZURE_FOUNDRY_API_KEY", "azf-key-1234")
        with pytest.raises(MemoryUnavailable) as excinfo:
            plugin._resolve_memoized()
        assert excinfo.value.severity == "error"
        assert "AZURE_FOUNDRY_BASE_URL" in excinfo.value.reason

    def test_missing_key_names_the_key_var(self, env):
        _write_config(env.home, "model:\n  provider: azure-foundry\n")
        with pytest.raises(MemoryUnavailable) as excinfo:
            plugin._resolve_memoized()
        assert excinfo.value.severity == "error"
        assert "AZURE_FOUNDRY_API_KEY" in excinfo.value.reason


class TestCredentialPool:
    def test_pool_only_openrouter_resolves_ready(self, env):
        """#42130: `hermes auth add openrouter` with no env var → READY via
        probe t4 + the step-8 pool fallback."""
        env.pool._pools["openrouter"] = [
            SimpleNamespace(access_token="", runtime_api_key="sk-pool-1234")
        ]
        resolved = plugin._resolve_memoized()
        assert resolved.provider_id == "openrouter"
        assert resolved.api_key == "sk-pool-1234"
        assert "openrouter" in env.pool.calls

    def test_pool_id_map_bridges_kimi(self, env, monkeypatch):
        """kimi's providers.py id (kimi-for-coding) diverges from the pool id
        (kimi-coding); the bridge must query the pool space first."""
        _write_config(env.home, "model:\n  provider: kimi\n")
        monkeypatch.setenv("KIMI_BASE_URL", "https://api.kimi.com/v1")
        env.pool._pools["kimi-coding"] = [
            SimpleNamespace(access_token="", runtime_api_key="sk-kimi-pool-1234")
        ]
        resolved = plugin._resolve_memoized()
        assert resolved.provider_id == "kimi-for-coding"
        assert resolved.api_key == "sk-kimi-pool-1234"
        # The mapped id was queried (and first), not only the providers id.
        assert env.pool.calls[0] == "kimi-coding"


class TestResolutionMemo:
    def test_positive_memo_and_config_mtime_invalidation(self, env, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test-1234")
        config_path = env.home / "config.yaml"
        _write_config(env.home, "model:\n  provider: openrouter\n")

        calls = {"n": 0}
        real_resolve = plugin._resolve

        def counting_resolve():
            calls["n"] += 1
            return real_resolve()

        monkeypatch.setattr(plugin, "_resolve", counting_resolve)

        first = plugin._resolve_memoized()
        second = plugin._resolve_memoized()
        assert calls["n"] == 1  # positive memo hit
        assert second is first

        os.utime(config_path, ns=(1_000_000_000, 999_999_999_000_000_000))
        plugin._resolve_memoized()
        assert calls["n"] == 2  # watched mtime invalidated

    def test_negative_memo_and_dotenv_invalidation(self, env, monkeypatch):
        calls = {"n": 0}
        real_resolve = plugin._resolve

        def counting_resolve():
            calls["n"] += 1
            return real_resolve()

        monkeypatch.setattr(plugin, "_resolve", counting_resolve)

        with pytest.raises(MemoryUnavailable):
            plugin._resolve_memoized()
        with pytest.raises(MemoryUnavailable):
            plugin._resolve_memoized()
        assert calls["n"] == 1  # negative memo hit

        # The exact fix the reason prescribes (adding a key to .env) must
        # take effect without a restart: .env is in the watched set.
        (env.home / ".env").write_text(
            "OPENROUTER_API_KEY=sk-or-late-1234\n", encoding="utf-8"
        )
        with pytest.raises(MemoryUnavailable):
            # Still OFF (env probe uses os.environ for t3, matching chat),
            # but the memo MUST recompute — the stamp changed.
            plugin._resolve_memoized()
        assert calls["n"] == 2

    def test_missing_watched_files_are_tolerated(self, env):
        # auth.json / .env don't exist in the hermetic home — the stamp must
        # simply record them as absent, never raise.
        stamp = plugin._watched_stamp()
        assert isinstance(stamp, tuple) and stamp


# ── §1.3 truth table — pinned LLM adapter ──────────────────────────────


class _FakeOpenAIClient:
    def __init__(self, api_key=None, base_url=None):
        self.api_key = api_key
        self.base_url = base_url


class _EnvFirstOpenAILLM:
    """Behavioral fake of mem0ai 2.0.10's env-first OpenAILLM hijack."""

    parent_calls: list = []

    def __init__(self, config=None):
        type(self).parent_calls.append("parent_init")
        self.config = config
        openrouter_key = os.environ.get("OPENROUTER_API_KEY", "")
        if openrouter_key:  # the verified hijack: env beats config
            self.client = _FakeOpenAIClient(
                api_key=openrouter_key, base_url="https://openrouter.ai/api/v1"
            )
        else:
            self.client = _FakeOpenAIClient(
                api_key=getattr(config, "api_key", None),
                base_url=getattr(config, "openai_base_url", None),
            )


@pytest.fixture()
def pinned_llm(monkeypatch):
    """Import _pinned_llm against stubbed mem0/openai modules."""
    mem0 = types.ModuleType("mem0")
    mem0.__version__ = "2.0.10"
    llms = types.ModuleType("mem0.llms")
    llms_openai = types.ModuleType("mem0.llms.openai")
    _EnvFirstOpenAILLM.parent_calls = []
    llms_openai.OpenAILLM = _EnvFirstOpenAILLM
    utils = types.ModuleType("mem0.utils")
    factory = types.ModuleType("mem0.utils.factory")

    class LlmFactory:
        provider_to_class = {"openai": "mem0.llms.openai.OpenAILLM"}

    factory.LlmFactory = LlmFactory
    openai_mod = types.ModuleType("openai")
    openai_mod.OpenAI = _FakeOpenAIClient

    for name, module in (
        ("mem0", mem0),
        ("mem0.llms", llms),
        ("mem0.llms.openai", llms_openai),
        ("mem0.utils", utils),
        ("mem0.utils.factory", factory),
        ("openai", openai_mod),
    ):
        monkeypatch.setitem(sys.modules, name, module)

    module_name = "agent_memory_plugins.mem0_oss._pinned_llm"
    sys.modules.pop(module_name, None)
    import agent_memory_plugins.mem0_oss as _pkg

    if hasattr(_pkg, "_pinned_llm"):
        delattr(_pkg, "_pinned_llm")
    import agent_memory_plugins.mem0_oss._pinned_llm as pinned

    yield SimpleNamespace(module=pinned, mem0=mem0, factory=LlmFactory)
    sys.modules.pop(module_name, None)
    if hasattr(_pkg, "_pinned_llm"):
        delattr(_pkg, "_pinned_llm")


class TestPinnedLLMTruthTable:
    def test_case_i_openai_api_immune_to_openrouter_hijack(
        self, env, monkeypatch, pinned_llm
    ):
        """(i) target openai-api, built via the REAL §a.0/§a.1 path, with
        OPENROUTER_API_KEY exported → client pinned to api.openai.com with
        the config key, never the env OpenRouter key."""
        _write_config(env.home, "model:\n  provider: openai-api\n")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-real-1234")
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-env")
        resolved = plugin._resolve_memoized()

        config = SimpleNamespace(
            api_key=resolved.api_key, openai_base_url=resolved.base_url
        )
        llm = pinned_llm.module.PinnedOpenAILLM(config)
        assert llm.client.base_url == "https://api.openai.com/v1"
        assert llm.client.api_key == "sk-openai-real-1234"
        # The parent DID run (and built a hijacked client) — the pin
        # overwrote it afterwards.
        assert _EnvFirstOpenAILLM.parent_calls == ["parent_init"]

    def test_case_ii_openrouter_target_uses_resolved_url(
        self, env, monkeypatch, pinned_llm
    ):
        _write_config(env.home, "model:\n  provider: openrouter\n")
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-env")
        monkeypatch.setenv("OPENROUTER_BASE_URL", "https://or.example/v1")
        resolved = plugin._resolve_memoized()
        assert resolved.base_url == "https://or.example/v1"

        config = SimpleNamespace(
            api_key=resolved.api_key, openai_base_url=resolved.base_url
        )
        llm = pinned_llm.module.PinnedOpenAILLM(config)
        assert llm.client.base_url == "https://or.example/v1"
        assert llm.client.api_key == "sk-or-env"

    def test_case_iii_local_family_stays_local(self, env, monkeypatch, pinned_llm):
        _write_config(
            env.home,
            "model:\n  provider: ollama\n  base_url: http://127.0.0.1:11434/v1\n",
        )
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-env")
        resolved = plugin._resolve_memoized()

        config = SimpleNamespace(
            api_key=resolved.api_key, openai_base_url=resolved.base_url
        )
        llm = pinned_llm.module.PinnedOpenAILLM(config)
        assert llm.client.base_url == "http://127.0.0.1:11434/v1"
        assert llm.client.api_key == "fox-local"

    def test_case_iv_missing_creds_fail_before_parent_construction(self, pinned_llm):
        with pytest.raises(ValueError):
            pinned_llm.module.PinnedOpenAILLM(None)
        with pytest.raises(ValueError):
            pinned_llm.module.PinnedOpenAILLM(
                SimpleNamespace(api_key="sk-x", openai_base_url="")
            )
        with pytest.raises(ValueError):
            pinned_llm.module.PinnedOpenAILLM(
                SimpleNamespace(api_key="", openai_base_url="https://x.example")
            )
        assert _EnvFirstOpenAILLM.parent_calls == []  # parent never ran

    def test_case_v_version_tripwire(self, pinned_llm):
        pinned_llm.mem0.__version__ = "2.1.0"
        with pytest.raises(MemoryUnavailable) as excinfo:
            pinned_llm.module.ensure_registered()
        assert excinfo.value.severity == "error"
        assert "2.1.0" in excinfo.value.reason

    def test_registration_is_idempotent(self, pinned_llm):
        pinned_llm.module.ensure_registered()
        registered = pinned_llm.factory.provider_to_class["openai"]
        assert registered.endswith(".PinnedOpenAILLM")
        pinned_llm.module.ensure_registered()
        assert pinned_llm.factory.provider_to_class["openai"] == registered


# ── is_available() → state.json (design §a.2 structural guarantees) ────


class TestStateJson:
    def test_ready_state_written(self, env, monkeypatch, pinned_llm):
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test-1234")
        monkeypatch.setattr(plugin, "_embed_server_healthy", lambda: True)
        provider = plugin.Mem0OSSMemoryProvider()
        assert provider.is_available() is True
        state = json.loads((env.home / "mem0_oss" / "state.json").read_text())
        assert state["status"] == "ready"
        assert state["llm"] == "openrouter"
        assert state["embedder"] == f"local:{_LOCAL_EMBED_MODEL}"

    def test_off_state_written_with_reason(self, env, monkeypatch, pinned_llm):
        monkeypatch.setenv("MEM0_OSS_DISABLED", "1")
        provider = plugin.Mem0OSSMemoryProvider()
        assert provider.is_available() is False
        state = json.loads((env.home / "mem0_oss" / "state.json").read_text())
        assert state["status"] == "off"
        assert state["reason"] == "disabled (MEM0_OSS_DISABLED=1)"

    def test_dead_embed_server_is_error_state(self, env, monkeypatch, pinned_llm):
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test-1234")
        monkeypatch.setattr(plugin, "_embed_server_healthy", lambda: False)
        provider = plugin.Mem0OSSMemoryProvider()
        assert provider.is_available() is False
        state = json.loads((env.home / "mem0_oss" / "state.json").read_text())
        assert state["status"] == "error"
        assert "embed-server" in state["reason"]

    def test_error_state_written_for_explicit_misconfig(self, env, pinned_llm):
        _write_config(env.home, "model:\n  provider: openrouter\n")  # no key
        provider = plugin.Mem0OSSMemoryProvider()
        assert provider.is_available() is False
        state = json.loads((env.home / "mem0_oss" / "state.json").read_text())
        assert state["status"] == "error"
        assert "OPENROUTER_API_KEY" in state["reason"]


# ── Negative invariant: never auth.py resolution functions ─────────────


class TestNegativeInvariants:
    def test_plugin_never_calls_auth_resolution_functions(self):
        """Runtime NEVER calls auth.py RESOLUTION functions.  Allowed
        read-only mirror surfaces (per the §g.1 allowlist): normalize_provider,
        PROVIDER_REGISTRY iteration (t5), _load_auth_store / get_auth_status
        (t6), credential_pool.load_pool (t4 + step 8),
        bedrock_adapter.has_aws_credentials (t7), has_usable_secret."""
        source = (Path(plugin.__file__)).read_text(encoding="utf-8")
        # The name may appear in the _WELL_KNOWN invariant comment; assert
        # on CODE lines only (comment lines stripped).
        code_lines = [
            line for line in source.splitlines() if not line.strip().startswith("#")
        ]
        code = "\n".join(code_lines)
        assert "resolve_api_key_provider_credentials" not in code
        # auth.py's own resolve_provider (registry-space) — the plugin must
        # only use providers.resolve_provider_full.
        assert "from hermes_cli.auth import resolve_provider" not in source
