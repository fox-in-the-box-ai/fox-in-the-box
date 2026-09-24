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

from __future__ import annotations

import ipaddress
import json
import logging
import re
import socket
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlsplit

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


_NONPUBLIC_MSG = "Base URL must resolve to a public address."


def _assert_public_destination(base_url: str) -> tuple[bool, str]:
    """Resolve base_url's host; reject if ANY resolved address is
    loopback/private/link-local/multicast/reserved/unspecified (SSRF guard,
    #900). Deny-by-default: any resolution failure is a rejection.

    Belongs in the fetch path (test_provider) only — NOT in _validate_base_url,
    which upsert_provider shares and which legitimately stores LAN base URLs.
    Returns (ok, error).
    """
    host = urlsplit(base_url).hostname
    if not host:
        return False, _NONPUBLIC_MSG
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        return False, _NONPUBLIC_MSG
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            return False, _NONPUBLIC_MSG
        mapped = getattr(ip, "ipv4_mapped", None)
        if mapped is not None:  # unwrap ::ffff:127.0.0.1 style
            ip = mapped
        # Explicit flags are the primary, readable check; `not is_global`
        # (safe here because ipv4_mapped is already unwrapped) is the
        # version-robust backstop that also denies CGNAT (100.64.0.0/10),
        # which is_private classifies inconsistently across Python releases.
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
            or not ip.is_global
        ):
            return False, _NONPUBLIC_MSG
    return True, ""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Disable redirect-following on the probe so a public URL cannot 30x-bounce
    into a private target after the destination guard has run (#900)."""

    def redirect_request(self, *args, **kwargs):
        return None


_PROBE_OPENER = urllib.request.build_opener(_NoRedirect)


def _validate_models(models: Any) -> tuple[bool, list[str] | str]:
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


def _modify_custom_providers(mutator) -> None:
    """Read-modify-write custom_providers atomically under _cfg_lock."""
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
        entries = cfg.get("custom_providers", [])
        if not isinstance(entries, list):
            entries = []
        entries = [e for e in entries if isinstance(e, dict) and e.get("name")]
        entries = mutator(entries)
        cfg["custom_providers"] = entries
        _save_yaml_config_file(_get_config_path(), cfg)

    from api.config import invalidate_models_cache, reload_config

    reload_config()
    invalidate_models_cache()


def get_providers_list() -> dict[str, Any]:
    entries = _read_custom_providers()
    result = []
    for entry in entries:
        result.append(
            {
                "name": entry.get("name", ""),
                "base_url": entry.get("base_url", ""),
                "api_key": _mask_key(entry.get("api_key")),
                "models": entry.get("models", []),
            }
        )
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
    if api_key == "****":
        api_key = ""

    new_entry: dict[str, Any] = {
        "name": name,
        "base_url": base_url,
        "models": models,
    }
    if api_key:
        new_entry["api_key"] = api_key

    name_lower = name.lower()

    def _mutate(entries: list[dict]) -> list[dict]:
        for i, entry in enumerate(entries):
            if str(entry.get("name", "")).strip().lower() == name_lower:
                if not api_key and entry.get("api_key"):
                    new_entry["api_key"] = entry["api_key"]
                entries[i] = new_entry
                return entries
        entries.append(new_entry)
        return entries

    try:
        _modify_custom_providers(_mutate)
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
    found = [False]

    def _mutate(entries: list[dict]) -> list[dict]:
        result = [
            e for e in entries if str(e.get("name", "")).strip().lower() != target
        ]
        found[0] = len(result) < len(entries)
        return result

    try:
        _modify_custom_providers(_mutate)
    except Exception as exc:
        logger.exception("Failed to delete custom provider: %s", exc)
        return {"ok": False, "error": f"Failed to save: {exc}"}

    if not found[0]:
        return {"ok": False, "error": f"Provider '{raw_name.strip()}' not found."}

    logger.info("Custom provider deleted: %s", raw_name.strip())
    return {"ok": True}


def test_provider(body: dict) -> dict[str, Any]:
    ok, base_url = _validate_base_url(body.get("base_url", ""))
    if not ok:
        return {"ok": False, "error": base_url}

    ok, guard_err = _assert_public_destination(base_url)
    if not ok:
        logger.warning(
            "custom_provider_test_blocked host=%s", urlsplit(base_url).hostname
        )
        return {"ok": False, "error": guard_err}

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
        with _PROBE_OPENER.open(req, timeout=5) as resp:  # nosec B310 -- host-guarded to public address + redirects disabled
            data = json.loads(resp.read(1_048_576).decode("utf-8", errors="replace"))
            models_found = 0
            if isinstance(data, dict) and isinstance(data.get("data"), list):
                models_found = len(data["data"])
            return {"ok": True, "models_found": models_found}
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            return {"ok": False, "error": "Authentication required or denied."}
        logger.warning("custom_provider_test_http_error code=%s", exc.code)
        return {"ok": False, "error": "Could not reach the provider endpoint."}
    except urllib.error.URLError as exc:
        logger.warning(
            "custom_provider_test_url_error reason=%s", getattr(exc, "reason", exc)
        )
        return {"ok": False, "error": "Could not reach the provider endpoint."}
    except Exception as exc:
        logger.warning("custom_provider_test_error err=%s", exc)
        return {"ok": False, "error": "Could not reach the provider endpoint."}


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
    from api.helpers import j

    from fox_overlay.webui_modules._body_shape import require_object_body

    if parsed.path == "/api/settings/custom-providers":
        body = require_object_body(handler)
        if body is None:
            return True
        result = handle_post(handler, body)
        j(handler, result, status=200 if result.get("ok") else 400)
        return True

    if parsed.path == "/api/settings/custom-providers/test":
        body = require_object_body(handler)
        if body is None:
            return True
        result = handle_test(handler, body)
        j(handler, result, status=200 if result.get("ok") else 400)
        return True

    if parsed.path == "/api/settings/custom-providers/delete":
        body = require_object_body(handler)
        if body is None:
            return True
        result = handle_delete(handler, body)
        j(handler, result, status=200 if result.get("ok") else 400)
        return True

    return False


dispatch.register_get("/api/settings/custom-providers", _handle_get, allow_bare=True)
dispatch.register_post("/api/settings/custom-providers", _handle_post, allow_bare=True)
