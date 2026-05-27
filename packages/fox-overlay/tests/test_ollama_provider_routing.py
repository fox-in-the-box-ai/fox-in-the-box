"""Regression tests for Ollama provider routing (#278 / v0.7.20).

Three bugs surfaced when using a local Ollama model:
1. use_model() wrote `provider: "ollama"` to config.yaml — breaks
   auxiliary tasks because upstream's auxiliary_client.py doesn't map
   "ollama" -> "custom" in its _PROVIDER_ALIASES dict.
2. Frontend colon-split bugs in ui.js — three functions split on the
   wrong colon when parsing `@custom:llama3.1:latest`.
3. Backend _split_provider_qualified_model() used rsplit(":", 1) instead
   of split(":", 1) — same mis-parse for model tags containing colons.

This file covers bugs #1 (use_model config output) and #3 (split logic).
Bug #2 is JavaScript; tested in the Electron/Playwright suite.
"""
import importlib
import sys

import pytest


# ── use_model() writes provider: "custom" ──────────────────────────────────


@pytest.fixture
def use_model_isolated(monkeypatch, tmp_path):
    """Provide a callable use_model() with all I/O mocked out.

    Captures what was written to config.yaml via _save_yaml_config_file
    so assertions can inspect the provider, base_url, default, and name
    fields without touching disk or the network.
    """
    # Stub api.config so the lazy import inside use_model() resolves
    fake_config = type(sys)("api.config")
    fake_config._get_config_path = lambda: str(tmp_path / "config.yaml")

    saved = {}

    def _save(path, cfg):
        saved["path"] = path
        saved["cfg"] = cfg

    fake_config._save_yaml_config_file = _save
    fake_config.reload_config = lambda: None
    fake_config.invalidate_models_cache = lambda: None
    # get_config returns a minimal dict that use_model() can mutate
    fake_config.get_config = lambda: {"model": {}}

    monkeypatch.setitem(sys.modules, "api.config", fake_config)
    monkeypatch.setitem(sys.modules, "api", type(sys)("api"))

    # Stub the Ollama daemon probe — pretend it's running on the
    # canonical Docker Desktop host address.
    import fox_overlay.webui_modules.ollama as m
    importlib.reload(m)
    monkeypatch.setattr(m, "_cached_probe", lambda force=False: {
        "up": True,
        "host": "http://host.docker.internal:11434",
        "version": "0.6.3",
    })

    yield m.use_model, saved

    importlib.reload(m)


class TestUseModelProviderRouting:
    """use_model() must write provider: "custom" so auxiliary tasks work."""

    def test_provider_written_as_custom(self, use_model_isolated):
        use_model, saved = use_model_isolated
        result = use_model("llama3.1:latest")

        assert result["ok"] is True
        model_cfg = saved["cfg"]["model"]
        assert model_cfg["provider"] == "custom", (
            "config.yaml must contain provider: 'custom' — 'ollama' breaks "
            "auxiliary_client.py which doesn't alias it"
        )

    def test_return_dict_has_provider_custom(self, use_model_isolated):
        use_model, _saved = use_model_isolated
        result = use_model("llama3.1:latest")

        assert result["ok"] is True
        assert result["provider"] == "custom"

    def test_base_url_has_v1_suffix(self, use_model_isolated):
        use_model, saved = use_model_isolated
        result = use_model("phi4-mini:latest")

        assert result["ok"] is True
        model_cfg = saved["cfg"]["model"]
        assert model_cfg["base_url"] == "http://host.docker.internal:11434/v1"
        assert result["base_url"] == "http://host.docker.internal:11434/v1"

    def test_default_and_name_match_model(self, use_model_isolated):
        use_model, saved = use_model_isolated
        result = use_model("qwen2:7b")

        assert result["ok"] is True
        model_cfg = saved["cfg"]["model"]
        assert model_cfg["default"] == "qwen2:7b"
        assert model_cfg["name"] == "qwen2:7b"
        assert result["active_model"] == "qwen2:7b"

    def test_model_cfg_is_clean_dict(self, use_model_isolated):
        """model block must not carry stale keys from a prior provider."""
        use_model, saved = use_model_isolated
        use_model("llama3.1:latest")

        model_cfg = saved["cfg"]["model"]
        # Only the four keys we explicitly set should be present
        assert set(model_cfg.keys()) == {"provider", "base_url", "default", "name"}


# ── _split_provider_qualified_model() ──────────────────────────────────────


@pytest.fixture
def split_fn(monkeypatch):
    """Import _split_provider_qualified_model from the working tree.

    The function lives in forks/hermes-webui/api/routes.py. We add the
    parent directory to sys.path temporarily so we can import it without
    a full hermes-webui install. We also need to stub its upstream
    dependencies.
    """
    import pathlib
    routes_dir = pathlib.Path(__file__).resolve().parents[3] / "forks" / "hermes-webui"

    # routes.py imports many upstream modules at module level. Rather than
    # fighting with all of them, we extract just the two functions we need
    # by reading the source and exec-ing the relevant slice.
    routes_path = routes_dir / "api" / "routes.py"
    source = routes_path.read_text(encoding="utf-8")

    # Extract _clean_session_model_provider and _split_provider_qualified_model
    ns = {}
    # _clean_session_model_provider is a dependency of _split_provider_qualified_model
    for fn_name in ("_clean_session_model_provider", "_split_provider_qualified_model"):
        start = source.index(f"def {fn_name}(")
        # Find next top-level def or class (line starting with no indentation)
        rest = source[start:]
        lines = rest.split("\n")
        fn_lines = [lines[0]]
        for line in lines[1:]:
            if line and not line[0].isspace() and not line.startswith("#"):
                break
            fn_lines.append(line)
        exec("\n".join(fn_lines), ns)

    yield ns["_split_provider_qualified_model"]


class TestSplitProviderQualifiedModel:
    """Regression: rsplit(":", 1) mis-parses model tags with colons."""

    def test_custom_provider_with_model_tag(self, split_fn):
        """@custom:llama3.1:latest -> ("llama3.1:latest", "custom")"""
        bare, provider = split_fn("@custom:llama3.1:latest")
        assert bare == "llama3.1:latest"
        assert provider == "custom"

    def test_simple_provider_no_tag(self, split_fn):
        """@anthropic:claude-sonnet-4-20250514 -> ("claude-sonnet-4-20250514", "anthropic")"""
        bare, provider = split_fn("@anthropic:claude-sonnet-4-20250514")
        assert bare == "claude-sonnet-4-20250514"
        assert provider == "anthropic"

    def test_bare_model_no_prefix(self, split_fn):
        """llama3.1:latest -> ("llama3.1:latest", None)"""
        bare, provider = split_fn("llama3.1:latest")
        assert bare == "llama3.1:latest"
        assert provider is None

    def test_openrouter_slash_model(self, split_fn):
        """@openrouter:meta-llama/llama-3-8b-instruct -> correct split"""
        bare, provider = split_fn("@openrouter:meta-llama/llama-3-8b-instruct")
        assert bare == "meta-llama/llama-3-8b-instruct"
        assert provider == "openrouter"

    def test_ollama_provider_with_model_tag(self, split_fn):
        """@ollama:phi4-mini:latest -> ("phi4-mini:latest", "ollama")

        Even though we now write provider: "custom" to config.yaml,
        upstream URL-based detection may produce @ollama: prefixed
        model strings. The split must still handle them correctly.
        """
        bare, provider = split_fn("@ollama:phi4-mini:latest")
        assert bare == "phi4-mini:latest"
        assert provider == "ollama"

    def test_empty_string(self, split_fn):
        bare, provider = split_fn("")
        assert bare == ""
        assert provider is None

    def test_at_only(self, split_fn):
        """Edge case: bare @ with no colon."""
        bare, provider = split_fn("@")
        assert bare == "@"
        assert provider is None

    def test_model_with_multiple_colons_in_tag(self, split_fn):
        """@custom:org/model:v2:latest -> provider is 'custom', rest is model"""
        bare, provider = split_fn("@custom:org/model:v2:latest")
        assert bare == "org/model:v2:latest"
        assert provider == "custom"
