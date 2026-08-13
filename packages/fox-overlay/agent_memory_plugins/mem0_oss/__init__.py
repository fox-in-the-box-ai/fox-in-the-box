"""Mem0 OSS (self-hosted) memory plugin — MemoryProvider interface.

LLM-powered fact extraction, semantic vector search, and automatic
deduplication using the open-source ``mem0ai`` library — no cloud API key
required.  All data is stored locally on disk.

Architecture (design §1/§a — default-on, fail-loud):
  Fact-extraction LLM : the user's MAIN chat provider, resolved through the
                        same surfaces chat uses (``resolve_provider_full`` +
                        env/.env keys + credential pool).  Never a silent
                        fallback — every unusable configuration produces an
                        explicit state with a reason.
  Embedder            : ALWAYS local — nomic-embed-text-v1.5 served by the
                        baked llama.cpp embed-server on 127.0.0.1:8644,
                        reached through mem0's OpenAI adapter with an
                        explicit base_url.  Memory content never leaves the
                        machine for embedding.
  Vector store        : embedded Qdrant (local path, no server), 768 dims.

State model — resolution produces exactly one of:
  READY            memory active (state.json status "ready")
  OFF   (visible)  nothing misconfigured, memory unsupported/disabled for
                   this setup (status "off" + reason)
  ERROR (visible)  explicit configuration that cannot work (status "error"
                   + reason naming the exact fix)

Overrides (precedence: computed defaults < env < $HERMES_HOME/mem0_oss.json):
  MEM0_OSS_DISABLED            — "1" disables memory entirely (state 9)
  MEM0_OSS_LLM_PROVIDER        — resolve this provider instead of the main one
  MEM0_OSS_LLM_MODEL           — fact-extraction model id
  MEM0_OSS_API_KEY             — dedicated key for memory LLM calls
  MEM0_OSS_BASE_URL            — dedicated endpoint for memory LLM calls
                                 (MEM0_OSS_OPENAI_BASE_URL kept as alias)
  MEM0_OSS_EMBEDDER_PROVIDER   — "openai" (any OpenAI-compatible endpoint)
                                 or "aws_bedrock"; overrides the local default
  MEM0_OSS_EMBEDDER_MODEL      — embedder model id
  MEM0_OSS_EMBEDDER_BASE_URL   — embedder endpoint override
  MEM0_OSS_EMBEDDER_DIMS       — embedding dimensions (flows to embedder AND
                                 vector store)
  MEM0_OSS_VECTOR_STORE_PATH   — on-disk path for Qdrant
  MEM0_OSS_HISTORY_DB_PATH     — SQLite history path
  MEM0_OSS_COLLECTION          — Qdrant collection name (default: hermes)
  MEM0_OSS_USER_ID             — memory namespace (default: hermes-user)
  MEM0_OSS_TOP_K               — max results per search (default: 10)
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Telemetry kill layer 1 (design §c): must run before any ``import mem0``
# anywhere in this process.  All mem0 imports in this package are lazy, so
# executing this at module import time is sufficient.
os.environ.setdefault("MEM0_TELEMETRY", "False")

from agent.memory_provider import MemoryProvider
from hermes_constants import get_hermes_home
from tools.registry import tool_error

logger = logging.getLogger(__name__)

# Circuit breaker: after this many consecutive failures, pause for cooldown.
_BREAKER_THRESHOLD = 5
_BREAKER_COOLDOWN_SECS = 120

# Qdrant embedded lock error substring — used to detect contention gracefully.
_QDRANT_LOCK_ERROR = "already accessed by another instance"

# Retry parameters for Qdrant lock contention in _get_memory().
_LOCK_RETRY_ATTEMPTS = 10  # total attempts
_LOCK_RETRY_DELAY_S = 0.8  # base seconds between retries (with jitter)

# ── Local embedder constants (design §1.1) — single source of truth ─────────
_LOCAL_EMBED_BASE_URL = "http://127.0.0.1:8644/v1"
_LOCAL_EMBED_HEALTH_URL = "http://127.0.0.1:8644/health"
_LOCAL_EMBED_MODEL = "nomic-embed-text-v1.5"
_LOCAL_EMBED_DIMS = 768
_LOCAL_EMBED_API_KEY = "fox-local"

# embed-server health probe (design §1.4): 2 s timeout, any HTTP response is
# healthy (sleep-agnostic), refused/timeout is an error; 15 s TTL cache.
_EMBED_HEALTH_TIMEOUT_S = 2.0
_EMBED_HEALTH_TTL_S = 15.0

# Resolution memo negative-cache window (design §a.0).
_NEGATIVE_MEMO_TTL_S = 600.0

_TRUE_VALUES = {"1", "true", "yes", "on"}


class MemoryUnavailable(Exception):
    """Resolution outcome: memory cannot run — visible OFF or explicit ERROR.

    ``severity`` is ``"off"`` (nothing misconfigured; memory unsupported or
    deliberately disabled for this setup) or ``"error"`` (explicit
    configuration that cannot work; the reason names the fix).
    """

    def __init__(self, reason: str, severity: str = "off"):
        if severity not in ("off", "error"):
            raise ValueError(f"invalid severity {severity!r}")
        super().__init__(reason)
        self.reason = reason
        self.severity = severity


@dataclass
class ResolvedConfig:
    """Outcome of a successful provider resolution (design §a.1)."""

    provider_id: str  # providers.py id-space (or synthesized local id)
    mem0_llm_provider: str  # "openai" | "anthropic" | "aws_bedrock"
    llm_model: str
    api_key: str = ""
    base_url: str = ""


# ── Well-known fallback table (design §a.0) ─────────────────────────────────
# The models.dev catalog is a runtime network dependency with no bundled
# snapshot; without this table the flagship rows resolve with empty key lists
# (openai-api ALWAYS — no PROVIDER_TO_MODELS_DEV entry) or empty base_urls
# (openrouter offline).  Invariant: runtime NEVER calls auth.py RESOLUTION
# functions (resolve_api_key_provider_credentials / resolve_provider);
# read-only mirror surfaces ARE used (PROVIDER_REGISTRY iteration in probe
# t5, _load_auth_store/get_auth_status in t6, credential_pool.load_pool in
# t4/step 8).  Sync assertions against the named sources run in-image
# (image-selftest phase A), NOT in the unit suite:
#   openai-api    → PROVIDER_REGISTRY["openai-api"]
#   anthropic     → PROVIDER_REGISTRY["anthropic"] (subset + first-var)
#   openrouter    → hermes_constants.OPENROUTER_BASE_URL + auto-chain literal
#   azure-foundry → PROVIDER_REGISTRY["azure-foundry"] (URL is "" by design —
#                   user-provided endpoint, resolved via AZURE_FOUNDRY_BASE_URL)
_WELL_KNOWN: Dict[str, Tuple[Tuple[str, ...], str]] = {
    "openai-api": (("OPENAI_API_KEY",), "https://api.openai.com/v1"),
    "openrouter": (("OPENROUTER_API_KEY",), "https://openrouter.ai/api/v1"),
    "anthropic": (("ANTHROPIC_API_KEY",), "https://api.anthropic.com"),
    "azure-foundry": (("AZURE_FOUNDRY_API_KEY",), ""),  # URL via base_url_env_var
}

# providers.py id → registry/credential-pool id, for the three verified
# divergences (design §a.1 step 8).  ``hermes auth add`` stores pools in
# registry space; this map is the plugin's bridge.  Sync-asserted in-image.
_POOL_ID_MAP: Dict[str, str] = {
    "kimi-for-coding": "kimi-coding",
    "opencode": "opencode-zen",
    "kilo": "kilocode",
}

# Default fact-extraction model per resolved provider id (openai-adapter rows
# fall back to the generic default).
_DEFAULT_LLM_MODELS: Dict[str, str] = {
    "openrouter": "openai/gpt-4o-mini",
    "openai-api": "gpt-4o-mini",
    "anthropic": "claude-haiku-4-5-20251001",
    "bedrock": "us.anthropic.claude-haiku-4-5-20251001-v1:0",
}
_GENERIC_LLM_MODEL = "gpt-4o-mini"


# ---------------------------------------------------------------------------
# Small helpers over hermes surfaces (all lazy, all defensive)
# ---------------------------------------------------------------------------


def _env_disabled() -> bool:
    return os.environ.get("MEM0_OSS_DISABLED", "").strip().lower() in _TRUE_VALUES


def _read_file_overrides() -> dict:
    """Read $HERMES_HOME/mem0_oss.json (highest-precedence overrides)."""
    config_path = get_hermes_home() / "mem0_oss.json"
    try:
        if config_path.exists():
            data = json.loads(config_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return {k: v for k, v in data.items() if v is not None and v != ""}
    except Exception as exc:
        logger.warning("mem0_oss: failed to read config file %s: %s", config_path, exc)
    return {}


def _env_prefer_dotenv(var: str) -> str:
    """Chat's credential-read semantics: ~/.hermes/.env wins over os.environ."""
    try:
        from hermes_cli.config import get_env_value_prefer_dotenv

        return (get_env_value_prefer_dotenv(var) or "").strip()
    except Exception:
        return (os.environ.get(var) or "").strip()


def _has_usable_secret(value: Any) -> bool:
    try:
        from hermes_cli.auth import has_usable_secret

        return has_usable_secret(value)
    except Exception:
        return bool(isinstance(value, str) and len(value.strip()) >= 4)


def _read_main_provider_raw() -> str:
    """Main chat provider name, raw lowercased (mirrors auxiliary_client)."""
    try:
        from agent.auxiliary_client import _read_main_provider

        return (_read_main_provider() or "").strip().lower()
    except Exception:
        pass
    try:
        from hermes_cli.config import load_config

        model_cfg = (load_config() or {}).get("model") or {}
        if isinstance(model_cfg, dict):
            provider = model_cfg.get("provider", "")
            if isinstance(provider, str):
                return provider.strip().lower()
    except Exception:
        pass
    return ""


def _read_main_base_url_raw() -> str:
    try:
        from agent.auxiliary_client import _read_main_base_url

        return (_read_main_base_url() or "").strip()
    except Exception:
        pass
    try:
        from hermes_cli.config import load_config

        model_cfg = (load_config() or {}).get("model") or {}
        if isinstance(model_cfg, dict):
            base = model_cfg.get("base_url", "")
            if isinstance(base, str):
                return base.strip()
    except Exception:
        pass
    return ""


def _read_provider_blocks() -> Tuple[Optional[dict], Optional[list]]:
    """providers: / custom_providers: blocks from config.yaml (loaded once)."""
    try:
        from hermes_cli.config import load_config

        cfg = load_config() or {}
    except Exception:
        return None, None
    if not isinstance(cfg, dict):
        return None, None
    user_providers = cfg.get("providers")
    custom_providers = cfg.get("custom_providers")
    return (
        user_providers if isinstance(user_providers, dict) else None,
        custom_providers if isinstance(custom_providers, list) else None,
    )


def _catalog_available() -> bool:
    """True when the models.dev catalog is reachable OR cached (design §a.0).

    Bounded: the library's single network attempt has a 15 s timeout and the
    resolution memo prevents repeats within the negative-cache window.
    """
    try:
        from agent.models_dev import fetch_models_dev

        return bool(fetch_models_dev())
    except Exception:
        return False


def _unsupported_reason(provider_id: str) -> str:
    return (
        f"memory fact-extraction doesn't support provider '{provider_id}' "
        "(no static API key / OpenAI-compatible endpoint) — set "
        "MEM0_OSS_LLM_PROVIDER + MEM0_OSS_API_KEY to use a different provider "
        "for memory"
    )


# ---------------------------------------------------------------------------
# Resolution memo (design §a.0) — watched-mtime invalidation set
# ---------------------------------------------------------------------------

_memo_lock = threading.Lock()
_memo: Dict[str, Any] = {"stamp": None, "result": None, "error": None, "error_ts": 0.0}


def _watched_paths() -> List[str]:
    """Files whose mtime change invalidates the resolution memo.

    Paths are derived from the SAME modules the probe tiers already import
    (never hardcoded): config.yaml + .env from hermes_cli.config, the auth
    store (which also persists the credential pool) from hermes_cli.auth.
    """
    paths: List[str] = []
    try:
        from hermes_cli.config import get_config_path, get_env_path

        paths.append(str(get_config_path()))
        paths.append(str(get_env_path()))
    except Exception:
        pass
    try:
        from hermes_cli.auth import _auth_file_path, _global_auth_file_path

        paths.append(str(_auth_file_path()))
        global_auth = _global_auth_file_path()
        if global_auth:
            # Pool reads fall back to the global-root auth.json in profile mode.
            paths.append(str(global_auth))
    except Exception:
        pass
    return paths


def _watched_stamp() -> tuple:
    stamp = []
    for path in _watched_paths():
        try:
            stamp.append((path, os.stat(path).st_mtime_ns))
        except OSError:
            # Missing file participates as "absent" (FileNotFoundError-tolerant).
            stamp.append((path, None))
    return tuple(stamp)


def _invalidate_memo() -> None:
    with _memo_lock:
        _memo.update({"stamp": None, "result": None, "error": None, "error_ts": 0.0})


def _resolve_memoized() -> ResolvedConfig:
    """Memoized ``_resolve()``: positive for process life, negative 10 min,
    both invalidated when any watched file's mtime changes."""
    # State 9 is env-driven (not covered by the watched-file set) and must be
    # the first check on every call, never served stale from the memo.
    if _env_disabled():
        raise MemoryUnavailable("disabled (MEM0_OSS_DISABLED=1)", severity="off")

    stamp = _watched_stamp()
    now = time.monotonic()
    with _memo_lock:
        if _memo["stamp"] == stamp:
            if _memo["result"] is not None:
                return _memo["result"]
            if (
                _memo["error"] is not None
                and (now - _memo["error_ts"]) < _NEGATIVE_MEMO_TTL_S
            ):
                raise _memo["error"]

    try:
        result = _resolve()
    except MemoryUnavailable as exc:
        with _memo_lock:
            _memo.update(
                {"stamp": stamp, "result": None, "error": exc, "error_ts": now}
            )
        raise
    with _memo_lock:
        _memo.update({"stamp": stamp, "result": result, "error": None, "error_ts": 0.0})
    return result


# ---------------------------------------------------------------------------
# Resolution pipeline (design §a.1)
# ---------------------------------------------------------------------------


def _resolve() -> ResolvedConfig:
    """Resolve the fact-extraction provider, or raise ``MemoryUnavailable``."""
    file_cfg = _read_file_overrides()
    user_providers, custom_providers = _read_provider_blocks()

    # Step 0: explicit override wins (file > env, matching the plugin's
    # standing precedence), resolved through the same pipeline below.
    override = (
        str(file_cfg.get("llm_provider") or "").strip().lower()
        or os.environ.get("MEM0_OSS_LLM_PROVIDER", "").strip().lower()
    )
    if override and override not in ("auto",):
        return _resolve_provider_name(
            override, user_providers, custom_providers, file_cfg
        )

    # Step 1: main chat provider from config.yaml.
    raw = _read_main_provider_raw()
    if raw in ("", "auto"):
        # Step 6: env/credential probe mirroring chat's auto-chain tiers 3-7.
        return _probe_credentials(user_providers, custom_providers, file_cfg)
    return _resolve_provider_name(raw, user_providers, custom_providers, file_cfg)


def _synth_local_pdef(provider_id: str, base_url: str):
    from hermes_cli.providers import ProviderDef

    return ProviderDef(
        id=provider_id,
        name=provider_id,
        transport="openai_chat",
        api_key_env_vars=(),
        base_url=base_url,
        auth_type="api_key",
        source="local-fallback",
    )


def _apply_well_known(pdef):
    """Union the §a.0 well-known row into a non-user-config ProviderDef."""
    well_known = _WELL_KNOWN.get(pdef.id)
    if well_known is None:
        return pdef
    wk_vars, wk_url = well_known
    merged = list(wk_vars) + [v for v in pdef.api_key_env_vars if v not in wk_vars]
    return replace(
        pdef, api_key_env_vars=tuple(merged), base_url=pdef.base_url or wk_url
    )


def _resolve_provider_name(
    raw: str, user_providers, custom_providers, file_cfg: dict
) -> ResolvedConfig:
    """Steps 2-5 + 7-8 of the §a.1 pipeline for a concrete provider name."""
    try:
        from hermes_cli.providers import resolve_provider_full, normalize_provider
    except Exception as exc:
        raise MemoryUnavailable(
            f"hermes provider resolution unavailable ({exc!r}) — memory cannot "
            "resolve the chat provider",
            severity="error",
        )

    raw = (raw or "").strip().lower()

    # Step 2: spelling special-cases.
    if raw == "codex":
        raw = "openai-codex"  # mirrors _normalize_aux_provider
    if raw.startswith("custom:") and not raw.split(":", 1)[1].strip():
        raw = "custom"
    # Named custom:<name> passes through UNMODIFIED — the raw string matches
    # the stored slug in resolve_custom_provider; a stripped suffix matches
    # nothing (design MAJOR-3 fix).

    pdef = None
    if raw == "custom":
        # Bare "custom": chat talks to model.base_url directly, so prefer it
        # over resolve_custom_provider's first-entry self-heal.
        main_base = _read_main_base_url_raw()
        if main_base:
            pdef = _synth_local_pdef("custom", main_base)  # URL taken verbatim

    if pdef is None:
        # Steps 3-4: full resolution + well-known union (non-user-config only:
        # user definitions are authoritative).
        pdef = resolve_provider_full(raw, user_providers, custom_providers)
        if pdef is not None and pdef.source != "user-config":
            pdef = _apply_well_known(pdef)

    if pdef is None:
        # Step 5: local-family fallback BEFORE any error.
        family = normalize_provider(raw)
        if family in ("local", "custom"):
            base_url = _read_main_base_url_raw()
            from_env_fallback = False
            if not base_url:
                base_url = (os.environ.get("OLLAMA_BASE_URL") or "").strip()
                from_env_fallback = True
            if base_url:
                # /v1 suffix appended only for the OLLAMA_BASE_URL env
                # fallback; main-config URLs are taken verbatim.
                if from_env_fallback and not base_url.rstrip("/").endswith("/v1"):
                    base_url = base_url.rstrip("/") + "/v1"
                pdef = _synth_local_pdef(raw, base_url)
            else:
                raise MemoryUnavailable(
                    f"local provider '{raw}' has no endpoint — set "
                    "model.base_url, OLLAMA_BASE_URL, or a custom_providers "
                    "entry",
                    severity="error",
                )
        else:
            reason = (
                f"unknown provider '{raw}' — not a built-in, models.dev, "
                "providers:, or custom_providers: entry"
            )
            if not _catalog_available():
                reason += (
                    " (the models.dev catalog is unreachable and not cached — "
                    "check network, or set MEM0_OSS_LLM_PROVIDER/"
                    "MEM0_OSS_API_KEY/MEM0_OSS_BASE_URL overrides)"
                )
            raise MemoryUnavailable(reason, severity="error")

    return _branch_and_credentials(raw, pdef, file_cfg)


def _branch_and_credentials(raw: str, pdef, file_cfg: dict) -> ResolvedConfig:
    """Step 7 (ProviderDef branching) + step 8 (credential resolution)."""
    llm_model = (
        str(file_cfg.get("llm_model") or "").strip()
        or os.environ.get("MEM0_OSS_LLM_MODEL", "").strip()
    )

    # Explicit anthropic arm — auth_type=api_key + transport=anthropic_messages
    # would otherwise fall through to the 6b catch-all; mem0's config-first
    # anthropic adapter is the transport here.
    if pdef.id == "anthropic":
        api_key = _resolve_api_key(pdef, raw=raw)
        return ResolvedConfig(
            provider_id="anthropic",
            mem0_llm_provider="anthropic",
            llm_model=llm_model or _DEFAULT_LLM_MODELS["anthropic"],
            api_key=api_key,
        )

    # Row 4: bedrock — boto3 default credential chain; step 8 never runs, so
    # the overlay-only pdef's empty api_key_env_vars tuple is inert.
    if pdef.auth_type == "aws_sdk":
        return ResolvedConfig(
            provider_id=pdef.id,
            mem0_llm_provider="aws_bedrock",
            llm_model=llm_model or _DEFAULT_LLM_MODELS["bedrock"],
        )

    # github-copilot: nominally api_key, but the raw GH token needs Copilot
    # token exchange before it is a usable bearer — a static-key call 401s.
    if pdef.id == "github-copilot":
        raise MemoryUnavailable(_unsupported_reason("github-copilot"), severity="off")

    # Rows 1/3/5/5b/5c: OpenAI-compatible chat-completions targets.
    # openai-api is eligible despite transport=codex_responses (api.openai.com
    # natively serves /v1/chat/completions — the API mem0's adapter speaks).
    if pdef.auth_type == "api_key" and (
        pdef.transport == "openai_chat"
        or pdef.id == "openai-api"
        or pdef.source == "local-fallback"
    ):
        api_key = _resolve_api_key(pdef, raw=raw)
        base_url = _resolve_base_url(pdef)
        return ResolvedConfig(
            provider_id=pdef.id,
            mem0_llm_provider="openai",
            llm_model=llm_model or _DEFAULT_LLM_MODELS.get(pdef.id, _GENERIC_LLM_MODEL),
            api_key=api_key,
            base_url=base_url,
        )

    # Row 6b: CATCH-ALL — oauth_*, external_process, virtual, any unrecognized
    # auth_type, and non-openai transports (codex_responses incl. xai,
    # anthropic_messages for non-anthropic ids).  Visible OFF, never an error:
    # nothing is misconfigured.
    raise MemoryUnavailable(_unsupported_reason(pdef.id), severity="off")


def _pool_api_key(provider_id: str) -> str:
    """Credential-pool fallback mirroring chat (auth.py:596-609).

    Tries the bridged pool id first (``_POOL_ID_MAP``), then ``pdef.id`` as a
    drift-tolerant fallback.  Never raises: pool machinery absent or broken
    degrades to "no pool key".
    """
    candidates = list(
        dict.fromkeys([_POOL_ID_MAP.get(provider_id, provider_id), provider_id])
    )
    for pool_id in candidates:
        try:
            from agent.credential_pool import load_pool

            pool = load_pool(pool_id)
            if pool and pool.has_credentials():
                entry = pool.peek()
                if entry is not None:
                    # getattr-defensive, exactly like chat: pool schema drift
                    # degrades to the missing-key path, never a traceback.
                    key = str(
                        getattr(entry, "access_token", "")
                        or getattr(entry, "runtime_api_key", "")
                        or ""
                    ).strip()
                    if _has_usable_secret(key):
                        return key
        except Exception as exc:
            logger.debug(
                "mem0_oss: credential pool lookup failed for %r: %s", pool_id, exc
            )
    return ""


def _resolve_api_key(pdef, raw: str = "") -> str:
    """Step 8 key resolution: overrides → env (.env-preferred) → pool →
    placeholder → explicit state-7 error.  Scoped to api_key rows."""
    file_cfg_key = str(_read_file_overrides().get("api_key") or "").strip()
    override = file_cfg_key or os.environ.get("MEM0_OSS_API_KEY", "").strip()
    if override:
        return override

    for env_var in pdef.api_key_env_vars:
        value = _env_prefer_dotenv(env_var)
        if _has_usable_secret(value):
            return value

    # Chat treats a lone OPENAI_API_KEY as an OpenRouter credential (the
    # auto-chain t3 literal, auth.py:1721) — mirror that here so a working
    # chat setup never false-errors, ordered AFTER OPENROUTER_API_KEY and
    # before the pool tier, matching chat's chain.
    if pdef.id == "openrouter":
        value = _env_prefer_dotenv("OPENAI_API_KEY")
        if _has_usable_secret(value):
            return value

    pool_key = _pool_api_key(pdef.id)
    if pool_key:
        return pool_key

    # Empty-key placeholder: lmstudio (chat's no-auth local server), the
    # local-fallback family, and keyless user-config entries — all
    # chat-supported keyless endpoints.
    if (
        pdef.id == "lmstudio"
        or pdef.source == "local-fallback"
        or (pdef.source == "user-config" and not pdef.api_key_env_vars)
    ):
        return _LOCAL_EMBED_API_KEY  # "fox-local" no-auth placeholder

    # Bare `model.provider: openai` routed to the aggregator with no usable
    # OpenRouter key: chat itself is broken too — teach, don't just fail.
    if raw == "openai" and pdef.id == "openrouter":
        raise MemoryUnavailable(
            "provider 'openai' routes through OpenRouter (set "
            "OPENROUTER_API_KEY); for direct OpenAI, use `provider: "
            "openai-api` or define `providers.openai` in config.yaml",
            severity="error",
        )

    if pdef.api_key_env_vars:
        # Empty-tuple guard: [0] is only reached behind this truthiness check.
        raise MemoryUnavailable(
            f"missing API key for provider '{pdef.id}' — set "
            f"{pdef.api_key_env_vars[0]} (env or ~/.hermes/.env) or add a key "
            f"with 'hermes auth add {pdef.id}' (credential pool was checked)",
            severity="error",
        )

    # Empty tuple on a non-user-config, non-local source: the catalog
    # disposition, split unreachable vs id-absent (design §a.0).
    if not _catalog_available():
        raise MemoryUnavailable(
            f"provider '{pdef.id}' needs the models.dev catalog, which is "
            "unreachable and not cached — check network, retry, or set "
            "MEM0_OSS_LLM_PROVIDER/MEM0_OSS_API_KEY/MEM0_OSS_BASE_URL "
            "overrides",
            severity="error",
        )
    raise MemoryUnavailable(
        f"provider '{pdef.id}' has no known API key variable — set "
        "MEM0_OSS_API_KEY, or define the provider under providers:/"
        "custom_providers: in config.yaml with a key_env",
        severity="error",
    )


def _resolve_base_url(pdef) -> str:
    """Step 8 base_url resolution with the empty-``base_url_env_var`` guard."""
    file_cfg = _read_file_overrides()
    override = (
        str(file_cfg.get("base_url") or file_cfg.get("openai_base_url") or "").strip()
        or os.environ.get("MEM0_OSS_BASE_URL", "").strip()
        or os.environ.get("MEM0_OSS_OPENAI_BASE_URL", "").strip()
    )
    if override:
        return override

    if getattr(pdef, "base_url_env_var", ""):
        env_url = _env_prefer_dotenv(pdef.base_url_env_var)
        if env_url:
            return env_url

    if pdef.base_url:
        return pdef.base_url

    # Empty base_url — the reason must name the true fix, never lie about the
    # catalog for user-config sources or already-set env vars.
    if pdef.source == "user-config":
        raise MemoryUnavailable(
            f"provider '{pdef.id}' has no endpoint — set base_url on its "
            "config.yaml entry",
            severity="error",
        )
    if not _catalog_available():
        raise MemoryUnavailable(
            f"provider '{pdef.id}' needs the models.dev catalog, which is "
            "unreachable and not cached — check network, retry, or set "
            "MEM0_OSS_LLM_PROVIDER/MEM0_OSS_API_KEY/MEM0_OSS_BASE_URL "
            "overrides",
            severity="error",
        )
    if getattr(pdef, "base_url_env_var", ""):
        raise MemoryUnavailable(
            f"provider '{pdef.id}' has no known endpoint — set "
            f"{pdef.base_url_env_var} (env or ~/.hermes/.env) or "
            "MEM0_OSS_BASE_URL",
            severity="error",
        )
    raise MemoryUnavailable(
        f"provider '{pdef.id}' has no known endpoint — set MEM0_OSS_BASE_URL "
        "or define it under providers:/custom_providers: in config.yaml",
        severity="error",
    )


def _resolve_detected(
    provider_id: str, user_providers, custom_providers, file_cfg: dict
) -> ResolvedConfig:
    """Feed a probe-detected id back through steps 2-5+7.

    A detected id that yields no ProviderDef lands in 6b naming it (visible
    OFF, never a crash) — nothing is misconfigured when detection guessed.
    """
    try:
        from hermes_cli.providers import resolve_provider_full, normalize_provider

        if resolve_provider_full(
            provider_id, user_providers, custom_providers
        ) is None and normalize_provider(provider_id) not in ("local", "custom"):
            raise MemoryUnavailable(_unsupported_reason(provider_id), severity="off")
    except MemoryUnavailable:
        raise
    except Exception:
        pass
    return _resolve_provider_name(
        provider_id, user_providers, custom_providers, file_cfg
    )


def _probe_credentials(
    user_providers, custom_providers, file_cfg: dict
) -> ResolvedConfig:
    """Step 6: config gave nothing — mirror chat's auto-chain tiers 3-7
    (auth.py:1710-1806).  Tiers 1-2 are handled by steps 0-5 upstream."""
    # t3: OPENAI/OPENROUTER env keys → openrouter, exactly like chat (a lone
    # OPENAI_API_KEY is treated as an OpenRouter credential; direct OpenAI is
    # config-explicit only).  os.getenv matches chat's tier semantics.
    if _has_usable_secret(os.getenv("OPENAI_API_KEY", "")) or _has_usable_secret(
        os.getenv("OPENROUTER_API_KEY", "")
    ):
        return _resolve_provider_name(
            "openrouter", user_providers, custom_providers, file_cfg
        )

    # t4: OpenRouter credential pool (hermes auth add openrouter, #42130).
    try:
        from agent.credential_pool import load_pool

        if load_pool("openrouter").has_credentials():
            return _resolve_provider_name(
                "openrouter", user_providers, custom_providers, file_cfg
            )
    except MemoryUnavailable:
        raise
    except Exception as exc:
        logger.debug("mem0_oss: OpenRouter pool probe failed: %s", exc)

    # t5: per-provider env keys from PROVIDER_REGISTRY (read-only iteration),
    # skipping copilot and lmstudio exactly as chat does.
    registry: Dict[str, Any] = {}
    try:
        from hermes_cli.auth import PROVIDER_REGISTRY

        registry = PROVIDER_REGISTRY
    except Exception as exc:
        logger.debug("mem0_oss: PROVIDER_REGISTRY unavailable for probe: %s", exc)
    for provider_id, pconfig in registry.items():
        if getattr(pconfig, "auth_type", "") != "api_key":
            continue
        if provider_id in ("copilot", "lmstudio"):
            continue
        for env_var in getattr(pconfig, "api_key_env_vars", ()) or ():
            if _has_usable_secret(os.getenv(env_var, "")):
                return _resolve_detected(
                    provider_id, user_providers, custom_providers, file_cfg
                )

    # t6: logged-in OAuth active_provider (read-only, try/except-continue —
    # a corrupt auth.json must never break resolution).  OAuth ids land in
    # 6b with the TRUE reason, never a false "finish onboarding".
    try:
        from hermes_cli.auth import _load_auth_store, get_auth_status

        store = _load_auth_store()
        active = store.get("active_provider")
        if active and active in registry and get_auth_status(active).get("logged_in"):
            return _resolve_detected(
                str(active), user_providers, custom_providers, file_cfg
            )
    except MemoryUnavailable:
        raise
    except Exception as exc:
        logger.debug("mem0_oss: auth-store probe failed: %s", exc)

    # t7: AWS Bedrock via boto3 default credential chain (ImportError-tolerant).
    try:
        from agent.bedrock_adapter import has_aws_credentials

        if has_aws_credentials():
            llm_model = (
                str(file_cfg.get("llm_model") or "").strip()
                or os.environ.get("MEM0_OSS_LLM_MODEL", "").strip()
                or _DEFAULT_LLM_MODELS["bedrock"]
            )
            return ResolvedConfig(
                provider_id="bedrock",
                mem0_llm_provider="aws_bedrock",
                llm_model=llm_model,
            )
    except MemoryUnavailable:
        raise
    except Exception:
        pass

    raise MemoryUnavailable(
        "Long-term memory needs a chat provider — no provider configured and "
        "no credentials found (env vars, credential pool, OAuth login, or AWS "
        "chain). Finish onboarding or set model.provider.",
        severity="off",
    )


# ---------------------------------------------------------------------------
# Embedder resolution (design §1.1 — always local unless explicitly overridden)
# ---------------------------------------------------------------------------


def _resolve_embedder(file_cfg: dict) -> dict:
    """Return the embedder plan: mem0 provider + config, vector-store dims,
    whether it is the local default (drives the :8644 probe), description."""
    env = os.environ
    provider = (
        str(file_cfg.get("embedder_provider") or "").strip().lower()
        or env.get("MEM0_OSS_EMBEDDER_PROVIDER", "").strip().lower()
    )
    model = (
        str(file_cfg.get("embedder_model") or "").strip()
        or env.get("MEM0_OSS_EMBEDDER_MODEL", "").strip()
    )
    base_url = (
        str(file_cfg.get("embedder_base_url") or "").strip()
        or env.get("MEM0_OSS_EMBEDDER_BASE_URL", "").strip()
    )
    dims_raw = str(
        file_cfg.get("embedder_dims") or env.get("MEM0_OSS_EMBEDDER_DIMS", "") or ""
    ).strip()
    try:
        dims = int(dims_raw) if dims_raw else None
    except ValueError:
        raise MemoryUnavailable(
            f"invalid MEM0_OSS_EMBEDDER_DIMS value {dims_raw!r} — must be an integer",
            severity="error",
        )

    overridden = bool(provider or model or base_url)
    if not overridden:
        # The default: always-local embedder through mem0's config-first
        # OpenAI adapter.  No embedding_dims on the embedder config (nomic
        # natively returns 768); dims live on the vector store only.
        cfg = {
            "model": _LOCAL_EMBED_MODEL,
            "api_key": _LOCAL_EMBED_API_KEY,
            "openai_base_url": _LOCAL_EMBED_BASE_URL,
        }
        if dims is not None:
            cfg["embedding_dims"] = dims  # explicit dims flow to BOTH surfaces
        return {
            "provider": "openai",
            "config": cfg,
            "store_dims": dims if dims is not None else _LOCAL_EMBED_DIMS,
            "is_local_default": True,
            "description": f"local:{_LOCAL_EMBED_MODEL}",
        }

    provider = provider or "openai"
    if provider == "aws_bedrock":
        cfg = {"model": model or "amazon.titan-embed-text-v2:0"}
        if dims is not None:
            cfg["embedding_dims"] = dims
        return {
            "provider": "aws_bedrock",
            "config": cfg,
            "store_dims": dims if dims is not None else 1024,
            "is_local_default": False,
            "description": f"aws_bedrock:{cfg['model']}",
        }
    if provider == "openai":
        cfg = {"model": model or "text-embedding-3-small"}
        if base_url:
            cfg["openai_base_url"] = base_url
        api_key = (
            str(file_cfg.get("api_key") or "").strip()
            or env.get("MEM0_OSS_API_KEY", "").strip()
            or _env_prefer_dotenv("OPENAI_API_KEY")
        )
        is_local_endpoint = base_url.startswith(
            ("http://127.0.0.1", "http://localhost")
        )
        if api_key:
            cfg["api_key"] = api_key
        elif is_local_endpoint:
            cfg["api_key"] = _LOCAL_EMBED_API_KEY
        else:
            raise MemoryUnavailable(
                f"explicit remote embedder ({cfg['model']}) has no API key — "
                "set MEM0_OSS_API_KEY or OPENAI_API_KEY",
                severity="error",
            )
        if dims is not None:
            cfg["embedding_dims"] = dims
        return {
            "provider": "openai",
            "config": cfg,
            "store_dims": dims if dims is not None else 1536,
            "is_local_default": False,
            "description": f"openai:{cfg['model']}",
        }
    raise MemoryUnavailable(
        f"unsupported embedder provider '{provider}' — use 'openai' (any "
        "OpenAI-compatible endpoint via MEM0_OSS_EMBEDDER_BASE_URL) or "
        "'aws_bedrock'; mem0's native ollama/lmstudio embedder classes are "
        "not supported",
        severity="error",
    )


# ---------------------------------------------------------------------------
# embed-server health probe (design §1.4)
# ---------------------------------------------------------------------------

_embed_health_cache: Dict[str, Any] = {"ts": 0.0, "ok": None}


def _embed_server_healthy() -> bool:
    """GET :8644/health, 2 s timeout.  ANY HTTP response (including 5xx —
    e.g. the model still loading or the server sleeping) is healthy; only
    connection-refused / timeout is an error.  15 s per-process TTL cache."""
    now = time.monotonic()
    with _memo_lock:
        if (
            _embed_health_cache["ok"] is not None
            and (now - _embed_health_cache["ts"]) < _EMBED_HEALTH_TTL_S
        ):
            return _embed_health_cache["ok"]

    import urllib.error
    import urllib.request

    url = (
        os.environ.get("MEM0_OSS_EMBED_HEALTH_URL", "").strip()
        or _LOCAL_EMBED_HEALTH_URL
    )
    try:
        with urllib.request.urlopen(url, timeout=_EMBED_HEALTH_TIMEOUT_S):
            ok = True
    except urllib.error.HTTPError:
        ok = True  # an HTTP status IS a live server (sleep-agnostic)
    except Exception:
        ok = False  # refused / timeout / DNS — dead port

    with _memo_lock:
        _embed_health_cache.update({"ts": now, "ok": ok})
    return ok


# ---------------------------------------------------------------------------
# state.json (design §a.2) — atomic, tolerant readers
# ---------------------------------------------------------------------------


def _state_path() -> Path:
    override = os.environ.get("MEM0_OSS_STATE_PATH", "").strip()
    if override:
        return Path(override)
    return get_hermes_home() / "mem0_oss" / "state.json"


def _write_state(
    status: str,
    reason: str = "",
    llm: str = "",
    embedder: str = "",
    strict: bool = False,
) -> None:
    """Atomically write state.json (tmp + os.replace).

    ``strict=True`` (preflight) re-raises ``PermissionError`` so the caller
    can surface it loudly; otherwise write failures are logged at ERROR and
    never break the caller.
    """
    payload = {
        "status": status,
        "reason": reason,
        "llm": llm,
        "embedder": embedder,
        "updated_at": time.time(),
    }
    path = _state_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.parent / f".{path.name}.{os.getpid()}.tmp"
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.replace(tmp, path)
    except PermissionError as exc:
        logger.error("mem0_oss: cannot write memory state file %s: %s", path, exc)
        if strict:
            raise
    except OSError as exc:
        logger.error("mem0_oss: failed writing memory state file %s: %s", path, exc)


def _write_ready_state() -> None:
    """Write status "ready" using the memoized resolution (best-effort)."""
    with _memo_lock:
        resolved = _memo.get("result")
    if resolved is None:
        return
    try:
        embedder = _resolve_embedder(_read_file_overrides())
        _write_state(
            "ready", "", llm=resolved.provider_id, embedder=embedder["description"]
        )
    except MemoryUnavailable:
        pass


# ---------------------------------------------------------------------------
# mem0 config assembly
# ---------------------------------------------------------------------------


def _load_runtime_config() -> dict:
    """Operational (non-provider) settings: paths, collection, namespace."""
    hermes_home = get_hermes_home()
    file_cfg = _read_file_overrides()
    config = {
        "vector_store_path": os.environ.get(
            "MEM0_OSS_VECTOR_STORE_PATH", str(hermes_home / "mem0_oss" / "qdrant")
        ),
        "history_db_path": os.environ.get(
            "MEM0_OSS_HISTORY_DB_PATH", str(hermes_home / "mem0_oss" / "history.db")
        ),
        "collection": os.environ.get("MEM0_OSS_COLLECTION", "hermes"),
        "user_id": os.environ.get("MEM0_OSS_USER_ID", "hermes-user"),
        "top_k": int(os.environ.get("MEM0_OSS_TOP_K", "10")),
    }
    for key in (
        "vector_store_path",
        "history_db_path",
        "collection",
        "user_id",
        "top_k",
    ):
        if key in file_cfg:
            config[key] = file_cfg[key]
    config["top_k"] = int(config["top_k"])
    return config


def _build_llm_cfg(resolved: ResolvedConfig) -> dict:
    """Provider-specific LLM config dict for mem0ai — always explicit."""
    if resolved.mem0_llm_provider == "aws_bedrock":
        return {"model": resolved.llm_model}
    if resolved.mem0_llm_provider == "anthropic":
        return {"model": resolved.llm_model, "api_key": resolved.api_key}
    cfg = {
        "model": resolved.llm_model,
        "api_key": resolved.api_key,
        "openai_base_url": resolved.base_url,
    }
    if resolved.provider_id == "openrouter":
        # Pin the OpenRouter-specific config field to the same resolved URL so
        # no mem0-internal branch can pick a different endpoint.
        cfg["openrouter_base_url"] = resolved.base_url
    return cfg


def _build_mem0_config(
    resolved: ResolvedConfig, embedder: dict, runtime_cfg: dict
) -> dict:
    """Build a mem0 MemoryConfig-compatible dict (design §a.2 rows)."""
    return {
        "vector_store": {
            "provider": "qdrant",
            "config": {
                "collection_name": runtime_cfg["collection"],
                "path": runtime_cfg["vector_store_path"],
                "embedding_model_dims": embedder["store_dims"],
                "on_disk": True,
            },
        },
        "llm": {
            "provider": resolved.mem0_llm_provider,
            "config": _build_llm_cfg(resolved),
        },
        "embedder": {
            "provider": embedder["provider"],
            "config": embedder["config"],
        },
        "history_db_path": runtime_cfg["history_db_path"],
        "version": "v1.1",
    }


def _check_collection_dims(memory_instance: Any, expected_dims: int) -> None:
    """Proactive dims-compat check (design §b.1): a pre-existing collection
    with different dims is a visible state-7b ERROR, never an AttributeError
    and never a silent qdrant no-op."""
    size: Optional[int] = None
    try:
        vector_store = getattr(memory_instance, "vector_store", None)
        client = getattr(vector_store, "client", None)
        collection = getattr(vector_store, "collection_name", "")
        if client is None or not collection:
            return
        info = client.get_collection(collection)
        params = info.config.params.vectors
        if hasattr(params, "size"):
            size = int(getattr(params, "size"))
        elif isinstance(params, dict):
            # Named-vector dict shape: {name: VectorParams}
            for value in params.values():
                candidate = getattr(value, "size", None)
                if candidate is not None:
                    size = int(candidate)
                    break
        # Unrecognized shapes: nothing to check (shape-tolerant by design).
    except Exception:
        return  # collection absent / API drift — the op path surfaces real errors
    if size is not None and size != int(expected_dims):
        raise MemoryUnavailable(
            f"memory store dimension mismatch: the existing collection holds "
            f"{size}-dim vectors but the configured embedder produces "
            f"{expected_dims}-dim vectors — either restore your previous "
            "embedder settings (MEM0_OSS_EMBEDDER_* env vars, or the embedder "
            "keys in $HERMES_HOME/mem0_oss.json if that file exists), or "
            "start fresh by deleting the $HERMES_HOME/mem0_oss/ data "
            "directory (nothing is deleted automatically)",
            severity="error",
        )


_DIMS_ERROR_SUBSTRINGS = ("dimension", "dim mismatch", "vector size")


def _op_error_reason(exc: Exception) -> str:
    """Classify an op-time failure; dimension errors get the 7b framing."""
    text = str(exc)
    if any(marker in text.lower() for marker in _DIMS_ERROR_SUBSTRINGS):
        return (
            f"memory store dimension error during operation: {text} — restore "
            "your previous embedder settings (MEM0_OSS_EMBEDDER_* / "
            "mem0_oss.json) or reset $HERMES_HOME/mem0_oss/"
        )
    return f"memory operation failed: {text}"


# ---------------------------------------------------------------------------
# Tool schemas
# ---------------------------------------------------------------------------

SEARCH_SCHEMA = {
    "name": "mem0_oss_search",
    "description": (
        "Search long-term memory using semantic similarity. Returns facts and context "
        "ranked by relevance.  Use this when you need information from past sessions "
        "that is not already in the current conversation."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "What to search for."},
            "top_k": {
                "type": "integer",
                "description": "Max results (default: 10, max: 50).",
            },
        },
        "required": ["query"],
    },
}

ADD_SCHEMA = {
    "name": "mem0_oss_add",
    "description": (
        "Store a durable fact to long-term memory — user preferences, environment"
        " details, architectural decisions, stable conventions, or corrections."
        " Only store facts that will still be useful in a future session."
        " Do NOT store session events, completed-work logs, commit SHAs, run"
        " stats, or anything that will be stale in a week."
        " mem0 deduplicates automatically."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "content": {"type": "string", "description": "The information to store."},
        },
        "required": ["content"],
    },
}


# ---------------------------------------------------------------------------
# Provider class
# ---------------------------------------------------------------------------


class Mem0OSSMemoryProvider(MemoryProvider):
    """Self-hosted mem0 memory provider backed by a local Qdrant vector store.

    Fact extraction uses the user's main chat provider; embeddings are always
    computed locally (design §1.1).  All data stays on disk.
    """

    def __init__(self):
        # Config / identity
        self._runtime_cfg: dict = {}
        self._user_id: str = "hermes-user"
        self._top_k: int = 10
        self._session_id: str = ""
        self._agent_context: str = "primary"
        # Circuit-breaker state (lock-protected)
        self._lock = threading.Lock()
        self._fail_count: int = 0
        self._last_fail_ts: float = 0.0
        # Background thread state
        self._sync_thread: Optional[threading.Thread] = None
        self._prefetch_thread: Optional[threading.Thread] = None
        self._prefetch_result: str = ""

    # -- MemoryProvider identity --------------------------------------------

    @property
    def name(self) -> str:
        return "mem0_oss"

    # -- Availability -------------------------------------------------------

    def is_available(self) -> bool:
        """Honest availability: memoized resolution (§a.1) + embed-server
        probe (§1.4) + atomic state.json write (§a.2).  Never raises."""
        try:
            import mem0  # noqa: F401
        except ImportError:
            _write_state("off", "mem0ai is not installed — memory disabled")
            return False

        try:
            resolved = _resolve_memoized()
            embedder = _resolve_embedder(_read_file_overrides())
        except MemoryUnavailable as exc:
            _write_state("error" if exc.severity == "error" else "off", exc.reason)
            return False
        except Exception as exc:  # availability must never raise (boot path)
            logger.error(
                "mem0_oss: unexpected resolution failure: %s", exc, exc_info=True
            )
            _write_state("error", f"memory resolution crashed: {exc!r}")
            return False

        if embedder["is_local_default"] and not _embed_server_healthy():
            _write_state(
                "error",
                "embed-server on 127.0.0.1:8644 is unreachable (connection "
                "refused/timeout) — check the embed-server unit and its log "
                "(embed-server.err)",
            )
            return False

        _write_state(
            "ready", "", llm=resolved.provider_id, embedder=embedder["description"]
        )
        return True

    # -- Lifecycle ----------------------------------------------------------

    def initialize(self, session_id: str, **kwargs) -> None:
        """Prepare per-session state.  Never raises on unusable config —
        the state model (state.json) carries the reason instead."""
        self._session_id = session_id
        self._agent_context = kwargs.get("agent_context", "primary")
        self._runtime_cfg = _load_runtime_config()
        self._user_id = self._runtime_cfg["user_id"]
        self._top_k = self._runtime_cfg["top_k"]
        # Reset circuit-breaker and prefetch state for this session.
        with self._lock:
            self._fail_count = 0
            self._last_fail_ts = 0.0
        self._prefetch_result = ""
        Path(self._runtime_cfg["vector_store_path"]).mkdir(parents=True, exist_ok=True)
        Path(self._runtime_cfg["history_db_path"]).parent.mkdir(
            parents=True, exist_ok=True
        )

    def _get_memory(self) -> Any:
        """Create a fresh mem0 Memory instance for each call.

        We intentionally do NOT cache the instance.  The embedded Qdrant store
        uses a portalocker (fcntl) exclusive lock that is held for the lifetime
        of the client object.  When both the WebUI and the gateway run on the
        same host they compete for this lock; we retry briefly with jitter.
        """
        import time as _time

        resolved = _resolve_memoized()  # raises MemoryUnavailable
        embedder = _resolve_embedder(_read_file_overrides())  # raises MemoryUnavailable
        if not self._runtime_cfg:
            self._runtime_cfg = _load_runtime_config()

        last_exc: Optional[Exception] = None
        for attempt in range(_LOCK_RETRY_ATTEMPTS):
            try:
                # Version tripwire + pinned-adapter registration, immediately
                # before Memory construction (design §1.3).
                from . import _pinned_llm

                _pinned_llm.ensure_registered()

                from mem0 import Memory
                from mem0.configs.base import MemoryConfig

                mem0_dict = _build_mem0_config(resolved, embedder, self._runtime_cfg)
                mem_cfg = MemoryConfig(
                    **{
                        "vector_store": mem0_dict["vector_store"],
                        "llm": mem0_dict["llm"],
                        "embedder": mem0_dict["embedder"],
                        "history_db_path": mem0_dict["history_db_path"],
                        "version": mem0_dict["version"],
                    }
                )
                memory = Memory(config=mem_cfg)
                _check_collection_dims(memory, embedder["store_dims"])
                return memory
            except MemoryUnavailable:
                raise
            except Exception as exc:
                last_exc = exc
                if _QDRANT_LOCK_ERROR in str(exc):
                    if attempt < _LOCK_RETRY_ATTEMPTS - 1:
                        import random as _random

                        jitter = _random.uniform(0, _LOCK_RETRY_DELAY_S * 0.5)
                        delay = _LOCK_RETRY_DELAY_S + jitter
                        logger.debug(
                            "mem0_oss: Qdrant lock busy (attempt %d/%d), retrying in %.2fs",
                            attempt + 1,
                            _LOCK_RETRY_ATTEMPTS,
                            delay,
                        )
                        _time.sleep(delay)
                        continue
                    # Last attempt also a lock error — fall through to raise below
                else:
                    # Non-lock error — fail fast, no retry
                    logger.error("mem0_oss: failed to initialize Memory: %s", exc)
                    raise
        logger.warning(
            "mem0_oss: Qdrant lock still held after %d attempts — giving up: %s",
            _LOCK_RETRY_ATTEMPTS,
            last_exc,
        )
        raise last_exc  # type: ignore[misc]

    # -- Circuit breaker helpers -------------------------------------------

    def _is_tripped(self) -> bool:
        with self._lock:
            if self._fail_count < _BREAKER_THRESHOLD:
                return False
            if time.monotonic() - self._last_fail_ts >= _BREAKER_COOLDOWN_SECS:
                self._fail_count = 0
                return False
            return True

    def _record_failure(self, reason: str = "") -> None:
        """Count a failure and surface it (design §a.2): the FIRST op failure
        flips state.json to "error" immediately; the threshold crossing logs
        one ERROR line."""
        with self._lock:
            self._fail_count += 1
            self._last_fail_ts = time.monotonic()
            crossed = self._fail_count == _BREAKER_THRESHOLD
        _write_state("error", reason or "memory operation failed")
        if crossed:
            logger.error(
                "mem0_oss: %d consecutive memory failures — pausing memory for "
                "%ds (last error: %s)",
                _BREAKER_THRESHOLD,
                _BREAKER_COOLDOWN_SECS,
                reason or "unknown",
            )

    def _record_success(self) -> None:
        with self._lock:
            had_failures = self._fail_count > 0
            self._fail_count = 0
        if had_failures:
            _write_ready_state()

    # -- System prompt block -----------------------------------------------

    def system_prompt_block(self) -> str:
        if not self.is_available():
            return ""
        return (
            "## Mem0 OSS Memory (self-hosted)\n"
            "You have access to long-term memory stored locally via mem0.\n"
            "- Use `mem0_oss_search` to recall relevant facts before answering.\n"
            "- Use `mem0_oss_add` to store **durable** facts only: user preferences,"
            " environment details, architectural decisions, stable conventions, corrections.\n"
            "- Do NOT store session events, completed-work logs, commit SHAs, run stats,"
            " or any fact that will be stale in a week — skip those entirely.\n"
            "- Facts are extracted and deduplicated automatically on each turn.\n"
            "- Search is semantic — natural-language queries work well.\n"
        )

    # -- Prefetch (background recall before each turn) ---------------------

    def queue_prefetch(self, query: str, *, session_id: str = "") -> None:
        """Start a background thread to recall context for the upcoming turn."""
        if self._is_tripped() or not self.is_available():
            return

        self._prefetch_result = ""
        self._prefetch_thread = threading.Thread(
            target=self._do_prefetch,
            args=(query,),
            daemon=True,
            name="mem0-oss-prefetch",
        )
        self._prefetch_thread.start()

    def _do_prefetch(self, query: str) -> None:
        try:
            mem = self._get_memory()
            results = mem.search(
                query=query[:500],
                top_k=self._top_k,
                filters={"user_id": self._user_id},
            )
            del mem  # release Qdrant lock ASAP — before any further processing
            memories = _extract_results(results)
            if memories:
                lines = "\n".join(f"- {m}" for m in memories)
                self._prefetch_result = f"Mem0 OSS Memory:\n{lines}"
            self._record_success()
        except MemoryUnavailable as exc:
            _write_state("error" if exc.severity == "error" else "off", exc.reason)
        except Exception as exc:
            if _QDRANT_LOCK_ERROR in str(exc):
                logger.debug(
                    "mem0_oss: prefetch skipped — Qdrant lock held by another process"
                )
                return  # not a real failure; don't trip the circuit breaker
            self._record_failure(_op_error_reason(exc))
            logger.debug("mem0_oss: prefetch error: %s", exc)

    def prefetch(self, query: str, *, session_id: str = "") -> str:
        """Return prefetched results (join background thread first)."""
        if self._prefetch_thread is not None:
            self._prefetch_thread.join(timeout=15.0)
            self._prefetch_thread = None
        return self._prefetch_result

    # -- Sync turn (auto-extract after each turn) --------------------------

    def sync_turn(
        self, user_content: str, assistant_content: str, *, session_id: str = ""
    ) -> None:
        """Spawn a background thread to extract and store facts from the turn."""
        if self._agent_context != "primary":
            return
        if self._is_tripped() or not self.is_available():
            return

        messages = [
            {"role": "user", "content": user_content},
            {"role": "assistant", "content": assistant_content},
        ]
        self._sync_thread = threading.Thread(
            target=self._do_sync,
            args=(messages,),
            daemon=True,
            name="mem0-oss-sync",
        )
        self._sync_thread.start()

    def _do_sync(self, messages: List[dict]) -> None:
        try:
            mem = self._get_memory()
            mem.add(messages=messages, user_id=self._user_id, infer=True)
            del mem  # release Qdrant lock ASAP
            self._record_success()
        except MemoryUnavailable as exc:
            _write_state("error" if exc.severity == "error" else "off", exc.reason)
        except Exception as exc:
            if _QDRANT_LOCK_ERROR in str(exc):
                logger.debug(
                    "mem0_oss: sync_turn skipped — Qdrant lock held by another process"
                )
                return  # not a real failure; don't trip the circuit breaker
            self._record_failure(_op_error_reason(exc))
            logger.debug("mem0_oss: sync_turn error: %s", exc)

    # -- Tool schemas & dispatch -------------------------------------------

    def get_tool_schemas(self) -> List[dict]:
        if not self.is_available():
            return []
        return [SEARCH_SCHEMA, ADD_SCHEMA]

    def handle_tool_call(self, tool_name: str, args: Dict[str, Any], **kwargs) -> str:
        if tool_name == "mem0_oss_search":
            return self._handle_search(args)
        if tool_name == "mem0_oss_add":
            return self._handle_add(args)
        return tool_error(f"Unknown tool: {tool_name}")

    def _handle_search(self, args: Dict[str, Any]) -> str:
        query = args.get("query", "").strip()
        if not query:
            return tool_error("mem0_oss_search requires 'query'")

        top_k = min(int(args.get("top_k", self._top_k)), 50)

        try:
            mem = self._get_memory()
            results = mem.search(
                query=query,
                top_k=top_k,
                filters={"user_id": self._user_id},
            )
            del mem  # release Qdrant lock ASAP
            memories = _extract_results(results)
            self._record_success()
            if not memories:
                return json.dumps({"result": "No relevant memories found."})
            return json.dumps({"result": "\n".join(f"- {m}" for m in memories)})
        except MemoryUnavailable as exc:
            _write_state("error" if exc.severity == "error" else "off", exc.reason)
            return tool_error(f"mem0_oss_search unavailable: {exc.reason}")
        except Exception as exc:
            if _QDRANT_LOCK_ERROR in str(exc):
                self._record_failure("storage locked by another process")
                logger.warning(
                    "mem0_oss: Qdrant lock held by another process — search skipped"
                )
                return json.dumps(
                    {
                        "result": "Memory temporarily unavailable (storage locked by another process)."
                    }
                )
            self._record_failure(_op_error_reason(exc))
            logger.error("mem0_oss: search error: %s", exc)
            return tool_error(f"mem0_oss_search failed: {exc}")

    def _handle_add(self, args: Dict[str, Any]) -> str:
        content = args.get("content", "").strip()
        if not content:
            return tool_error("mem0_oss_add requires 'content'")

        try:
            mem = self._get_memory()
            mem.add(
                messages=[{"role": "user", "content": content}],
                user_id=self._user_id,
                infer=True,
            )
            del mem  # release Qdrant lock ASAP
            self._record_success()
            return json.dumps({"result": "Memory stored successfully."})
        except MemoryUnavailable as exc:
            _write_state("error" if exc.severity == "error" else "off", exc.reason)
            return tool_error(f"mem0_oss_add unavailable: {exc.reason}")
        except Exception as exc:
            if _QDRANT_LOCK_ERROR in str(exc):
                self._record_failure("storage locked by another process")
                logger.warning(
                    "mem0_oss: Qdrant lock held by another process — add skipped"
                )
                return json.dumps(
                    {
                        "result": "Memory temporarily unavailable (storage locked by another process)."
                    }
                )
            self._record_failure(_op_error_reason(exc))
            logger.error("mem0_oss: add error: %s", exc)
            return tool_error(f"mem0_oss_add failed: {exc}")

    # -- Config schema (for setup wizard) ----------------------------------

    def get_config_schema(self) -> List[dict]:
        return [
            {
                "key": "llm_provider",
                "label": "LLM provider",
                "description": (
                    "Provider for fact extraction.  Empty = follow the main "
                    "chat provider (recommended)."
                ),
                "default": "",
                "env": "MEM0_OSS_LLM_PROVIDER",
                "required": False,
            },
            {
                "key": "llm_model",
                "label": "LLM model",
                "description": "Model id passed to the LLM provider (empty = provider default)",
                "default": "",
                "env": "MEM0_OSS_LLM_MODEL",
                "required": False,
            },
            {
                "key": "embedder_provider",
                "label": "Embedder provider",
                "description": (
                    "Embedder override — default is the bundled local model "
                    "(no key, no egress).  'openai' = any OpenAI-compatible "
                    "endpoint; 'aws_bedrock' = Titan."
                ),
                "default": "",
                "env": "MEM0_OSS_EMBEDDER_PROVIDER",
                "required": False,
            },
            {
                "key": "embedder_model",
                "label": "Embedding model id",
                "description": "Embedding model id (default: local nomic-embed-text-v1.5)",
                "default": _LOCAL_EMBED_MODEL,
                "env": "MEM0_OSS_EMBEDDER_MODEL",
                "required": False,
            },
            {
                "key": "embedder_dims",
                "label": "Embedding dimensions",
                "description": "Dimensions of the embedding model (must match the model)",
                "default": _LOCAL_EMBED_DIMS,
                "env": "MEM0_OSS_EMBEDDER_DIMS",
                "required": False,
            },
            {
                "key": "collection",
                "label": "Qdrant collection name",
                "description": "Name of the Qdrant collection storing memories",
                "default": "hermes",
                "env": "MEM0_OSS_COLLECTION",
                "required": False,
            },
            {
                "key": "user_id",
                "label": "User ID",
                "description": "Memory namespace / user identifier",
                "default": "hermes-user",
                "env": "MEM0_OSS_USER_ID",
                "required": False,
            },
            {
                "key": "top_k",
                "label": "Top-K results",
                "description": "Default number of memories returned per search",
                "default": 10,
                "env": "MEM0_OSS_TOP_K",
                "required": False,
            },
            {
                "key": "api_key",
                "label": "API key (mem0 LLM)",
                "description": (
                    "Dedicated API key for mem0 LLM calls.  Not needed when the "
                    "main chat provider has a usable key (env, .env, or "
                    "credential pool).  Not needed for AWS Bedrock."
                ),
                "default": "",
                "env": "MEM0_OSS_API_KEY",
                "secret": True,
                "required": False,
            },
            {
                "key": "base_url",
                "label": "OpenAI-compatible base URL",
                "description": (
                    "Custom LLM endpoint for memory fact extraction "
                    "(MEM0_OSS_OPENAI_BASE_URL is accepted as a legacy alias)."
                ),
                "default": "",
                "env": "MEM0_OSS_BASE_URL",
                "required": False,
            },
        ]

    def save_config(self, values: dict, hermes_home) -> None:
        """Write non-secret config to $HERMES_HOME/mem0_oss.json.

        Merges ``values`` into any existing file so that only the supplied keys
        are overwritten.  Secret keys (api_key) should be stored in ``.env``
        instead; this method stores them only if explicitly passed.
        """
        config_path = Path(hermes_home) / "mem0_oss.json"
        existing: dict = {}
        if config_path.exists():
            try:
                existing = json.loads(config_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        existing.update(values)
        config_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
        _invalidate_memo()

    # -- Shutdown ----------------------------------------------------------

    def on_memory_write(self, action: str, target: str, content: str) -> None:
        """Mirror built-in memory tool writes into mem0 store.

        Called by the framework whenever the agent uses the builtin memory tool,
        so writes go to mem0 automatically without the agent needing to call
        mem0_oss_add explicitly.
        """
        if action != "add" or not (content or "").strip():
            return
        if not self.is_available():
            return

        def _write():
            try:
                mem = self._get_memory()
                mem.add(
                    messages=[{"role": "user", "content": content.strip()}],
                    user_id=self._user_id,
                    infer=False,
                    metadata={"source": "hermes_memory_tool", "target": target},
                )
            except MemoryUnavailable as exc:
                _write_state("error" if exc.severity == "error" else "off", exc.reason)
            except Exception as e:
                if _QDRANT_LOCK_ERROR in str(e):
                    logger.debug(
                        "mem0_oss on_memory_write skipped — Qdrant lock held by another process"
                    )
                    return
                logger.debug("mem0_oss on_memory_write failed: %s", e)

        t = threading.Thread(target=_write, daemon=True, name="mem0-oss-memwrite")
        t.start()

    def shutdown(self) -> None:
        """Wait for any in-flight background threads."""
        for thread in (self._sync_thread, self._prefetch_thread):
            if thread is not None and thread.is_alive():
                thread.join(timeout=10.0)


# ---------------------------------------------------------------------------
# Result extraction helper
# ---------------------------------------------------------------------------


def _extract_results(results: Any) -> List[str]:
    """Normalize mem0 search results (v1 list or v2 dict) to plain strings."""
    if isinstance(results, dict) and "results" in results:
        items = results["results"]
    elif isinstance(results, list):
        items = results
    else:
        return []

    memories = []
    for item in items:
        if isinstance(item, dict):
            mem = item.get("memory") or item.get("text") or ""
        else:
            mem = str(item)
        if mem:
            memories.append(mem)
    return memories


# ---------------------------------------------------------------------------
# Plugin registration
# ---------------------------------------------------------------------------


def register(ctx) -> None:
    ctx.register_memory_provider(Mem0OSSMemoryProvider())
