"""Fox additive webui module: custom OpenAI-compatible provider management (#144).

Exposes CRUD + connectivity-test endpoints for custom providers stored
in config.yaml's ``custom_providers`` list.  Follows the hostname.py
dispatcher pattern (allow_bare=True, own boundary check).

Routes:
    GET  /api/settings/custom-providers       → list (API keys masked)
    POST /api/settings/custom-providers       → add or update
    POST /api/settings/custom-providers/test  → probe base_url/models
    POST /api/settings/custom-providers/delete → remove by name
"""
import json
import logging
import re
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger("fox_overlay.webui_modules.custom_providers")

_URL_RE = re.compile(r"^https?://[^\s]+$", re.IGNORECASE)
_NAME_MAX_LEN = 64


def _mask_key(key: str | None) -> str:
    if not key or not str(key).strip():
        return ""
    return "****"


def _validate_name(name: str) -> tuple[bool, str]:
    if not isinstance(name, str):
        return False, "Name must be a string."
    name = name.strip()
    if not name:
        return False, "Name is required."
    if len(name) > _NAME_MAX_LEN:
        return False, f"Name must be {_NAME_MAX_LEN} characters or fewer."
    return True, name


def _validate_base_url(url: str) -> tuple[bool, str]:
    if not isinstance(url, str):
        return False, "Base URL must be a string."
    url = url.strip().rstrip("/")
    if not url:
        return False, "Base URL is required."
    if not _URL_RE.match(url):
        return False, "Base URL must start with http:// or https://."
    return True, url


def _validate_models(models: Any) -> tuple[bool, list[str]]:
    if not isinstance(models, list):
        return False, "Models must be a list."
    cleaned = []
    for m in models:
        if isinstance(m, str):
            s = m.strip()
            if s:
                cleaned.append(s)
    if not cleaned:
        return False, "At least one model is required."
    return True, cleaned


def _read_custom_providers() -> list[dict]:
    from api.config import get_config
    cfg = get_config()
    if not isinstance(cfg, dict):
        return []
    entries = cfg.get("custom_providers", [])
    if not isinstance(entries, list):
        return []
    return [e for e in entries if isinstance(e, dict) and e.get("name")]


def _write_custom_providers(entries: list[dict]) -> None:
    from api.config import (
        _cfg_lock,
        _get_config_path,
        _load_yaml_config_file,
        _save_yaml_config_file,
    )
    with _cfg_lock:
        cfg = _load_yaml_config_file(_get_config_path())
        if not isinstance(cfg, dict):
            cfg = {}
        cfg["custom_providers"] = entries
        _save_yaml_config_file(_get_config_path(), cfg)

    from api.config import invalidate_models_cache, reload_config
    reload_config()
    invalidate_models_cache()


def get_providers_list() -> dict[str, Any]:
    entries = _read_custom_providers()
    result = []
    for entry in entries:
        result.append({
            "name": entry.get("name", ""),
            "base_url": entry.get("base_url", ""),
            "api_key": _mask_key(entry.get("api_key")),
            "models": entry.get("models", []),
        })
    return {"ok": True, "providers": result}


def upsert_provider(body: dict) -> dict[str, Any]:
    ok, name = _validate_name(body.get("name", ""))
    if not ok:
        return {"ok": False, "error": name}

    ok, base_url = _validate_base_url(body.get("base_url", ""))
    if not ok:
        return {"ok": False, "error": base_url}

    ok, models = _validate_models(body.get("models", []))
    if not ok:
        return {"ok": False, "error": models}

    api_key = ""
    raw_key = body.get("api_key")
    if isinstance(raw_key, str):
        api_key = raw_key.strip()

    new_entry = {
        "name": name,
        "base_url": base_url,
        "models": models,
    }
    if api_key:
        new_entry["api_key"] = api_key

    entries = _read_custom_providers()
    name_lower = name.lower()
    replaced = False
    for i, entry in enumerate(entries):
        if str(entry.get("name", "")).strip().lower() == name_lower:
            if api_key == "****":
                new_entry["api_key"] = entry.get("api_key", "")
            entries[i] = new_entry
            replaced = True
            break
    if not replaced:
        entries.append(new_entry)

    try:
        _write_custom_providers(entries)
    except Exception as exc:
        logger.exception("Failed to save custom providers: %s", exc)
        return {"ok": False, "error": f"Failed to save: {exc}"}

    logger.info("Custom provider upserted: %s → %s", name, base_url)
    return {"ok": True}


def delete_provider(body: dict) -> dict[str, Any]:
    raw_name = body.get("name", "")
    if not isinstance(raw_name, str) or not raw_name.strip():
        return {"ok": False, "error": "Name is required."}
    target = raw_name.strip().lower()

    entries = _read_custom_providers()
    before_len = len(entries)
    entries = [e for e in entries if str(e.get("name", "")).strip().lower() != target]

    if len(entries) == before_len:
        return {"ok": False, "error": f"Provider '{raw_name.strip()}' not found."}

    try:
        _write_custom_providers(entries)
    except Exception as exc:
        logger.exception("Failed to delete custom provider: %s", exc)
        return {"ok": False, "error": f"Failed to save: {exc}"}

    logger.info("Custom provider deleted: %s", raw_name.strip())
    return {"ok": True}


def test_provider(body: dict) -> dict[str, Any]:
    ok, base_url = _validate_base_url(body.get("base_url", ""))
    if not ok:
        return {"ok": False, "error": base_url}

    api_key = ""
    raw_key = body.get("api_key")
    if isinstance(raw_key, str):
        api_key = raw_key.strip()
    if api_key == "****":
        api_key = ""

    models_url = base_url.rstrip("/") + "/models"
    req = urllib.request.Request(models_url, method="GET")
    req.add_header("Accept", "application/json")
    if api_key:
        req.add_header("Authorization", f"Bearer {api_key}")

    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
            models_found = 0
            if isinstance(data, dict) and isinstance(data.get("data"), list):
                models_found = len(data["data"])
            return {"ok": True, "models_found": models_found}
    except urllib.error.HTTPError as exc:
        if exc.code == 401 or exc.code == 403:
            return {"ok": False, "error": "Authentication required or denied."}
        return {"ok": False, "error": f"HTTP {exc.code}: {exc.reason}"}
    except urllib.error.URLError as exc:
        reason = str(getattr(exc, "reason", exc))
        return {"ok": False, "error": f"Connection failed: {reason}"}
    except Exception as exc:
        return {"ok": False, "error": f"Connection failed: {exc}"}


# ── Route handlers ──────────────────────────────────────────────────────────

def handle_get(handler) -> dict[str, Any]:
    return get_providers_list()


def handle_post(handler, body: dict) -> dict[str, Any]:
    return upsert_provider(body)


def handle_delete(handler, body: dict) -> dict[str, Any]:
    return delete_provider(body)


def handle_test(handler, body: dict) -> dict[str, Any]:
    return test_provider(body)


# ── Fox dispatcher integration ──────────────────────────────────────────────
from fox_overlay import dispatch  # noqa: E402


def _handle_get(handler, parsed) -> bool:
    from api.helpers import j
    if parsed.path == "/api/settings/custom-providers":
        j(handler, handle_get(handler))
        return True
    return False


def _handle_post(handler, parsed) -> bool:
    from api.helpers import j, read_body

    if parsed.path == "/api/settings/custom-providers":
        body = read_body(handler)
        result = handle_post(handler, body)
        j(handler, result, status=200 if result.get("ok") else 400)
        return True

    if parsed.path == "/api/settings/custom-providers/test":
        body = read_body(handler)
        result = handle_test(handler, body)
        j(handler, result, status=200 if result.get("ok") else 400)
        return True

    if parsed.path == "/api/settings/custom-providers/delete":
        body = read_body(handler)
        result = handle_delete(handler, body)
        j(handler, result, status=200 if result.get("ok") else 400)
        return True

    return False


dispatch.register_get("/api/settings/custom-providers", _handle_get, allow_bare=True)
dispatch.register_post("/api/settings/custom-providers", _handle_post, allow_bare=True)
