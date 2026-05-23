"""Hermes Web UI -- Local Ollama integration.

Auto-detects a host-side Ollama daemon (issue #66) and exposes it as a
first-class provider tile. Routes user-selected models through the
existing `custom` OpenAI-compat path by writing model.{provider,base_url,name}
into config.yaml and triggering a gateway hot-reload — no hermes-agent
patches required.

The container can reach a host-side Ollama at:
- `http://host.docker.internal:11434` on Docker Desktop (macOS/Windows)
- `http://host.docker.internal:11434` on Linux IF the container was
  started with `--add-host=host.docker.internal:host-gateway` (Docker
  Engine 20.10+; Fox in the Box's Electron + install.sh do this in v0.3.0+)
- `http://localhost:11434` on native installs (rare; Fox normally runs
  inside Docker)

Older containers that predate the v0.3.0 host-gateway addition will see
"not detected" on Linux until they're re-created.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Iterator

logger = logging.getLogger(__name__)


# Ollama accepts model names like `llama3.1:8b`, `library/llama3.1:8b`,
# `myorg/mymodel:latest`. We allow letters, digits, dot, colon, slash,
# underscore, hyphen — explicitly reject shell metacharacters, whitespace,
# path traversal, control chars. Cap length to a generous 200 to keep
# error states friendly. (#67)
_MODEL_NAME_RE = re.compile(r"^[A-Za-z0-9._:/-]+$")
_MODEL_NAME_MAX = 200


# Ordered probe candidates. host.docker.internal first because that's the
# canonical Docker → host route; localhost as a fallback for rare native
# installs. Both share the default Ollama port.
#
# FITB#109: a user-supplied custom URL (settings.ollama_custom_url) is
# prepended to this list at probe time — it's an explicit user choice,
# so it always wins over auto-detection. Empty / unset means "use the
# defaults below."
_PROBE_HOSTS_DEFAULT = (
    "http://host.docker.internal:11434",
    "http://localhost:11434",
)
_PROBE_TIMEOUT_SEC = 1.0
_CACHE_TTL_SEC = 10.0  # keep Settings-page loads snappy without hiding state changes too long

# FITB#109: minimal validator for the custom Ollama URL. Reject malformed
# values at save time AND at probe time (defense in depth). Allows
# http(s)://host[:port][/path]; rejects leading dashes (would be parsed
# as flags by some downstream subprocess invocations) and control chars.
_OLLAMA_URL_RE = re.compile(r"^https?://[a-zA-Z0-9.\-_:/]+(?:/[a-zA-Z0-9.\-_:/?&=%~]*)?$")
_OLLAMA_URL_MAX_LEN = 512


def validate_custom_ollama_url(value: Any) -> tuple[bool, str]:
    """Validate + normalize a user-supplied Ollama URL.

    Returns ``(ok, normalized_or_error)``. Empty input is valid (means
    "unset"). Trailing slash stripped on success. Used by both
    /api/settings save (api/config.validate_settings_dict) and probe-time
    consumption (defense in depth in case settings.json was edited
    manually).
    """
    if value is None:
        return True, ""
    if not isinstance(value, str):
        return False, "ollama_custom_url must be a string"
    s = value.strip()
    if not s:
        return True, ""
    if len(s) > _OLLAMA_URL_MAX_LEN:
        return False, "ollama_custom_url is too long"
    if any(ord(c) < 0x20 for c in s):
        return False, "ollama_custom_url contains control characters"
    if not _OLLAMA_URL_RE.match(s):
        return False, "ollama_custom_url must be http(s)://host[:port]"
    return True, s.rstrip("/")

# Module-level cache for the detection probe. We expect a few calls per
# Settings render; caching avoids waiting on two TCP connect timeouts each
# time. Cleared via `clear_cache()` for tests / explicit refresh.
_cache_lock = threading.Lock()
_cache: dict[str, Any] | None = None
_cache_at: float = 0.0


def clear_cache() -> None:
    """Drop the detection cache (used by the Settings refresh button)."""
    global _cache, _cache_at
    with _cache_lock:
        _cache = None
        _cache_at = 0.0


def _http_json(url: str, method: str = "GET", body: dict | None = None,
               timeout: float = _PROBE_TIMEOUT_SEC) -> dict | None:
    """Minimal urllib JSON client. Returns parsed JSON or None on any
    failure. Stays inside stdlib — Hermes WebUI is intentionally
    framework-free."""
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, method=method, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310 — internal HTTP only
            raw = resp.read()
        if not raw:
            return {}
        return json.loads(raw)
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, json.JSONDecodeError):
        return None


def _probe_hosts() -> tuple[str, ...]:
    """Build the probe-host list. FITB#109: a settings-supplied custom
    URL is tried first when present (explicit user choice wins over
    auto-detection). Falls back to the default Docker / localhost pair.

    Re-validates the stored value (settings.json could have been hand-
    edited bypass the api/settings save path); silently drops invalid
    entries rather than blocking detection entirely.
    """
    try:
        from api.config import load_settings
        raw = (load_settings() or {}).get("ollama_custom_url", "")
    except Exception:
        raw = ""
    ok, normalized = validate_custom_ollama_url(raw)
    if ok and normalized:
        return (normalized, *_PROBE_HOSTS_DEFAULT)
    return _PROBE_HOSTS_DEFAULT


def _probe() -> dict[str, Any]:
    """Return {up, host, version} for the first reachable Ollama daemon, or
    {up: False} if none. `host` is the base URL (no `/api` suffix)."""
    for base in _probe_hosts():
        info = _http_json(f"{base}/api/version", timeout=_PROBE_TIMEOUT_SEC)
        if info and isinstance(info, dict) and "version" in info:
            return {"up": True, "host": base, "version": info.get("version", "")}
    return {"up": False, "host": "", "version": ""}


def _cached_probe(force: bool = False) -> dict[str, Any]:
    """Return a cached probe result, refreshing if the entry is older than
    `_CACHE_TTL_SEC` or `force=True`."""
    global _cache, _cache_at
    now = time.time()
    with _cache_lock:
        if not force and _cache is not None and (now - _cache_at) < _CACHE_TTL_SEC:
            return dict(_cache)
        result = _probe()
        _cache = result
        _cache_at = now
        return dict(result)


# ── Status + model-list endpoints ───────────────────────────────────────────


def get_status(force_refresh: bool = False) -> dict[str, Any]:
    """Return the current Ollama detection state for Settings UI."""
    p = _cached_probe(force=force_refresh)
    return {
        "running": bool(p.get("up")),
        "host": p.get("host", ""),
        "version": p.get("version", ""),
    }


def get_models() -> dict[str, Any]:
    """Return installed models from the detected Ollama daemon plus
    aggregate disk usage. Returns `{"running": False, "models": [],
    "total_size_bytes": 0}` if no daemon was found."""
    p = _cached_probe()
    if not p.get("up"):
        return {"running": False, "host": "", "models": [], "total_size_bytes": 0}
    base = p["host"]
    raw = _http_json(f"{base}/api/tags", timeout=3.0)
    if raw is None or not isinstance(raw, dict):
        return {
            "running": False, "host": base, "models": [], "total_size_bytes": 0,
            "error": "Ollama responded but /api/tags failed",
        }
    models = []
    total = 0
    for entry in raw.get("models", []) or []:
        if not isinstance(entry, dict):
            continue
        details = entry.get("details") or {}
        size = entry.get("size") or 0
        if isinstance(size, (int, float)):
            total += int(size)
        models.append({
            "name": entry.get("name") or entry.get("model") or "",
            "size_bytes": size,
            "parameter_size": details.get("parameter_size") or "",
            "quantization": details.get("quantization_level") or "",
            "family": details.get("family") or "",
            "modified_at": entry.get("modified_at") or "",
        })
    return {
        "running": True,
        "host": base,
        "models": models,
        "total_size_bytes": total,
    }


def _validate_model_name(raw: Any) -> tuple[str, str | None]:
    """Return (sanitized, error). Reject anything that smells like a
    shell escape, path traversal, or empty input. Errors are
    user-visible — keep them descriptive, never leak internals."""
    if not isinstance(raw, str):
        return "", "model name must be a string"
    name = raw.strip()
    if not name:
        return "", "model name is required"
    if len(name) > _MODEL_NAME_MAX:
        return "", f"model name longer than {_MODEL_NAME_MAX} characters"
    if not _MODEL_NAME_RE.match(name):
        return "", "model name has invalid characters (allowed: letters, digits, . : / _ -)"
    return name, None


def _model_size_bytes(name: str) -> int:
    """Look up an installed model's size from the cached tags listing.
    Used to compute `freed_bytes` after a delete. Returns 0 if the model
    isn't found (delete will surface the not-found error itself)."""
    try:
        listing = get_models()
    except Exception:
        return 0
    for m in listing.get("models", []) or []:
        if m.get("name") == name:
            return int(m.get("size_bytes") or 0)
    return 0


# ── Pull (SSE-proxied) ─────────────────────────────────────────────────────


def _iter_pull_stream(name: str) -> Iterator[dict[str, Any]]:
    """Stream NDJSON events from Ollama's /api/pull. Yields parsed dicts.
    Raises RuntimeError on probe-not-running or HTTP failure."""
    p = _cached_probe()
    if not p.get("up"):
        raise RuntimeError("Local Ollama daemon not detected. Is it running?")
    base = p["host"]
    body = json.dumps({"model": name, "stream": True}).encode("utf-8")
    req = urllib.request.Request(
        f"{base}/api/pull",
        method="POST",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    try:
        # Long-running stream — use a generous read timeout per chunk; the
        # Ollama daemon emits progress lines steadily during a pull.
        resp = urllib.request.urlopen(req, timeout=60.0)  # nosec B310 — internal HTTP only
    except urllib.error.HTTPError as exc:
        # Ollama returns 4xx with a JSON error body when e.g. the model
        # name is unknown to its registry.
        try:
            err_body = json.loads(exc.read().decode("utf-8") or "{}")
            msg = err_body.get("error") or f"Ollama HTTP {exc.code}"
        except (ValueError, UnicodeDecodeError):
            msg = f"Ollama HTTP {exc.code}"
        raise RuntimeError(msg)
    except (urllib.error.URLError, OSError) as exc:
        raise RuntimeError(f"Could not reach Ollama: {exc}")

    try:
        for raw_line in resp:
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                logger.warning("ollama pull: skipping non-JSON line: %r", line[:120])
                continue
    finally:
        try:
            resp.close()
        except Exception:
            pass


def stream_pull(handler, name_raw: Any) -> None:
    """Proxy Ollama's NDJSON pull stream as Server-Sent Events.

    The browser uses EventSource (or a fetch+TextDecoder reader) to consume
    the stream. We emit three event types:
      - ``progress`` — every Ollama status line, with name/total/completed
      - ``done`` — terminal success (Ollama emitted ``status: success``)
      - ``error`` — anything that prevents completion (validation, daemon,
        HTTP, JSON, network). On error we still close the stream cleanly.

    On successful completion the detection cache is invalidated so the
    next /api/ollama/models call sees the new model immediately.
    """
    name, err = _validate_model_name(name_raw)

    # Header send — once started, no more `send_response` etc.
    handler.send_response(200)
    handler.send_header("Content-Type", "text/event-stream; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("X-Accel-Buffering", "no")
    handler.send_header("Connection", "keep-alive")
    handler.end_headers()

    def emit(event: str, data: dict[str, Any]) -> None:
        payload = f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
        try:
            handler.wfile.write(payload.encode("utf-8"))
            handler.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            raise  # let outer code stop iterating

    if err:
        try:
            emit("error", {"error": err})
        except Exception:
            pass
        return

    saw_success = False
    try:
        for evt in _iter_pull_stream(name):
            # Pass through verbatim plus the requested model name so the
            # frontend can render multi-pull UIs in the future. Compute
            # speed/ETA on the client side from total + completed deltas.
            evt_with_ctx = dict(evt)
            evt_with_ctx.setdefault("model", name)
            emit("progress", evt_with_ctx)
            if evt.get("status") == "success":
                saw_success = True
            # Ollama can also emit explicit error lines mid-stream
            if "error" in evt and not saw_success:
                emit("error", {"error": str(evt["error"])})
                return
        if saw_success:
            clear_cache()
            emit("done", {"model": name})
        else:
            emit("error", {"error": "Pull ended without a success marker"})
    except RuntimeError as exc:
        try:
            emit("error", {"error": str(exc)})
        except Exception:
            pass
    except (BrokenPipeError, ConnectionResetError):
        # Client disconnected mid-pull — Ollama keeps pulling in the
        # background (its design). We just stop streaming.
        logger.info("ollama pull: client disconnected")


# ── Delete ─────────────────────────────────────────────────────────────────


def delete_model(name_raw: Any) -> dict[str, Any]:
    """Delete a model. Returns ``{ok, freed_bytes, error?}``.
    Looks up the model's size before delete so the UI can render
    \"freed N MB\" feedback."""
    name, err = _validate_model_name(name_raw)
    if err:
        return {"ok": False, "error": err}

    p = _cached_probe()
    if not p.get("up"):
        return {"ok": False, "error": "Local Ollama daemon not detected. Is it running?"}

    freed = _model_size_bytes(name)

    base = p["host"]
    body = json.dumps({"model": name}).encode("utf-8")
    req = urllib.request.Request(
        f"{base}/api/delete",
        method="DELETE",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10.0) as resp:  # nosec B310
            resp.read()  # drain any short body
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return {"ok": False, "error": f"Model not installed: {name}"}
        try:
            err_body = json.loads(exc.read().decode("utf-8") or "{}")
            msg = err_body.get("error") or f"Ollama HTTP {exc.code}"
        except (ValueError, UnicodeDecodeError):
            msg = f"Ollama HTTP {exc.code}"
        return {"ok": False, "error": msg}
    except (urllib.error.URLError, OSError) as exc:
        return {"ok": False, "error": f"Could not reach Ollama: {exc}"}

    clear_cache()
    return {"ok": True, "model": name, "freed_bytes": freed}


# ── Model selection (writes config.yaml, hot-reloads gateway) ──────────────


def use_model(model_name: str) -> dict[str, Any]:
    """Activate a local Ollama model for chat by writing
    model.{provider,base_url,name} into config.yaml and reloading the
    runtime. Routes through the existing `custom` OpenAI-compat path —
    no hermes-agent change needed."""
    if not isinstance(model_name, str):
        return {"ok": False, "error": "model name must be a string"}
    name = model_name.strip()
    if not name:
        return {"ok": False, "error": "model name is required"}

    p = _cached_probe()
    if not p.get("up"):
        return {"ok": False, "error": "Local Ollama daemon not detected. Is it running?"}

    base_url = f"{p['host']}/v1"

    # Lazy import to keep this module import-cheap at WebUI startup.
    from api.config import (
        _get_config_path,
        _save_yaml_config_file,
        get_config,
        invalidate_models_cache,
        reload_config,
    )

    cfg = get_config()
    if not isinstance(cfg, dict):
        cfg = {}
    # QA fix: previously we mutated the existing model_cfg dict and only
    # popped api_key. Provider-specific keys (azure_endpoint,
    # azure_api_version, aws_region, aws_access_key_id, aws_secret_access_key,
    # vertex_project, openai_organization, custom headers, etc.) leaked
    # through into the local-Ollama config — at minimum a stale-secrets
    # exposure in the config file the user thought they "switched away from",
    # at worst those keys riding along on requests if the OpenAI-compat
    # client respects them. Replace the model block wholesale instead of
    # patching it.
    # v0.7.20 #278: write `provider: "ollama"` instead of `provider: "custom"` so
    # the chat model picker classifies the active Ollama model under the OLLAMA
    # group instead of CUSTOM. Backend routing is unaffected — upstream's
    # `hermes_cli.auth._PROVIDER_ALIASES` maps `"ollama" -> "custom"` (auth.py:1412),
    # so the model still routes through the OpenAI-compat custom provider for
    # the actual HTTP request to host.docker.internal:11434. Also aligns with
    # upstream's own URL-based provider detection at api/config.py:3284 which
    # writes `provider = "ollama"` when the base_url contains "ollama"/127.0.0.1/
    # localhost — Fox is just being explicit about it here at active-model write
    # time. Closes the user-visible "model appears in two categories" bug
    # @bsgdigital flagged (also closes the v0.7.18 #343 dup-of-#278 instance).
    model_cfg = {
        "provider": "ollama",
        "base_url": base_url,
        "name": name,
    }
    cfg["model"] = model_cfg

    try:
        _save_yaml_config_file(_get_config_path(), cfg)
        reload_config()
        # reload_config() only deletes the on-disk models cache; the
        # picker reads from an in-memory cache that survives until the
        # next call to invalidate_models_cache(). Without this call, the
        # newly-activated Ollama model doesn't appear in the chat model
        # picker until a full page reload (FITB #281).
        invalidate_models_cache()
    except Exception as exc:
        logger.exception("Failed to switch active model to local Ollama: %s", exc)
        return {"ok": False, "error": f"Failed to update config: {exc}"}

    # Note: prior versions tried to call _reload_provider_runtime() here
    # via `from api.providers import _reload_provider_runtime`, but that
    # import has never resolved — _reload_provider_runtime was only ever
    # injected into set_provider_key's scope via extra_globals (it was
    # never a module-level name in api.providers). The accompanying
    # overlay was retired in v0.6.2 (FITB #269) once we verified upstream's
    # _reload_runtime_env_preserving_config_authority handles env-key
    # rotation per-turn without a supervisor restart. Removing the dead
    # try/except block here; nothing was happening at runtime.

    return {
        "ok": True,
        "active_model": name,
        "base_url": base_url,
        "provider": "ollama",  # v0.7.20 #278: matches what was written to config above.
    }


# ── Route handlers ─────────────────────────────────────────────────────────


def handle_get_status(handler) -> dict[str, Any]:
    """GET /api/ollama/status — fast detection probe."""
    return get_status()


def handle_get_models(handler) -> dict[str, Any]:
    """GET /api/ollama/models — installed models on the detected daemon."""
    return get_models()


def handle_post_use_model(handler, body: dict) -> dict[str, Any]:
    """POST /api/ollama/use-model {"model": "<name>"} — activate a model."""
    return use_model(body.get("model", ""))


def handle_post_refresh(handler) -> dict[str, Any]:
    """POST /api/ollama/refresh — drop the detection cache and re-probe."""
    clear_cache()
    return get_status(force_refresh=True)


# ──────────────────────────────────────────────────────────────────────
# Fox dispatcher integration — Phase 5 of v0.6.0 migration.
# Replaces 36 lines of inline routing in api/routes.py with a single
# registration each for GET + POST. The dispatcher hook in routes.py
# (Phase 4) intercepts /api/ollama/* before upstream's if/elif chain
# runs, so requests land here first.
#
# `api.helpers` is imported lazily inside each wrapper (not at module
# load) so that a broken/missing api.helpers does NOT cascade into
# bootstrap.install() swallowing the ImportError and leaving the
# dispatcher table partially populated — registration still succeeds
# even when the helpers import would have failed. Matches upstream's
# lazy-import-per-route pattern.
# ──────────────────────────────────────────────────────────────────────
from fox_overlay import dispatch  # noqa: E402


def _handle_get(handler, parsed) -> bool:
    """GET /api/ollama/* — returns True if handled, False to fall through."""
    from api.helpers import j

    if parsed.path == "/api/ollama/status":
        j(handler, handle_get_status(handler))
        return True
    if parsed.path == "/api/ollama/models":
        j(handler, handle_get_models(handler))
        return True
    return False


def _handle_post(handler, parsed) -> bool:
    """POST /api/ollama/* — returns True if handled, False to fall through."""
    from api.helpers import j, read_body

    body = read_body(handler)

    if parsed.path == "/api/ollama/refresh":
        j(handler, handle_post_refresh(handler))
        return True

    if parsed.path == "/api/ollama/use-model":
        result = handle_post_use_model(handler, body)
        j(handler, result, status=200 if result.get("ok") else 400)
        return True

    # SSE-streamed pull (#67) — stream_pull manages its own response.
    if parsed.path == "/api/ollama/pull":
        stream_pull(handler, body.get("model", ""))
        return True

    # POST (not DELETE) for symmetry — hermes-webui doesn't route DELETE.
    if parsed.path == "/api/ollama/delete":
        result = delete_model(body.get("model", ""))
        j(handler, result, status=200 if result.get("ok") else 400)
        return True

    return False


dispatch.register_get("/api/ollama/", _handle_get)
dispatch.register_post("/api/ollama/", _handle_post)

