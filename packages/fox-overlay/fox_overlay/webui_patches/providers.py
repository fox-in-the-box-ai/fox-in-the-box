"""Fox webui patch: Bedrock must not be labelled OAuth / IMDS-silent-auth.

Wraps ``api.providers.get_providers`` so AWS Bedrock (``auth_type=aws_sdk``)
never sets ``is_oauth=True``. Upstream's fallback treats any ``logged_in``
provider without an API-key env var as OAuth with hint
\"Authenticated via OAuth. No API key needed.\" — wrong for Bedrock and
misleading when the only credential source is the Lightsail/EC2 instance
role via IMDS.

Also re-applies the shared Bedrock IMDS gate so WebUI's
``get_auth_status`` / ``has_aws_credentials`` path matches the gateway.
"""
from __future__ import annotations

import inspect
import logging
from typing import Any

from fox_overlay.aws_bedrock_auth import (
    apply_auth_status_patch,
    apply_bedrock_adapter_patches,
)

_log = logging.getLogger("fox_overlay.webui_patches.providers")

_GET_PROVIDERS_SENTINEL = "_fox_patched_bedrock_providers"
_EXPECTED_GET_PROVIDERS_SIG = "() -> 'dict[str, Any]'"

# UI maps config_yaml → "Configured"; oauth → OAuth hint. Prefer Configured
# for any authentic aws_sdk source that isn't already a known UI label.
_UI_KEY_SOURCES = frozenset(
    {"oauth", "env", "config", "token", "env_file", "env_var", "config_yaml", "none"}
)


def _check_signature(callable_obj, expected: str, label: str) -> None:
    actual = str(inspect.signature(callable_obj))
    if actual != expected:
        raise AssertionError(
            "[fox-overlay] providers patch: %s signature drift.\n"
            "  expected: %s\n"
            "  actual:   %s\n"
            "Refresh the expected signature in "
            "fox_overlay/webui_patches/providers.py."
            % (label, expected, actual)
        )


def _normalize_bedrock_provider(entry: dict[str, Any]) -> None:
    if entry.get("id") != "bedrock":
        return
    # Bedrock is never OAuth.
    if entry.get("is_oauth"):
        entry["is_oauth"] = False
    ks = str(entry.get("key_source") or "").strip()
    if entry.get("has_key"):
        if ks in ("", "oauth", "none") or ks not in _UI_KEY_SOURCES:
            # Show "Configured" rather than "API key" / "OAuth".
            entry["key_source"] = "config_yaml"
    elif ks == "oauth":
        entry["key_source"] = "none"


def _wrap_get_providers(upstream_module) -> None:
    upstream_fn = upstream_module.get_providers
    if getattr(upstream_fn, _GET_PROVIDERS_SENTINEL, False):
        return

    _check_signature(upstream_fn, _EXPECTED_GET_PROVIDERS_SIG, "get_providers")

    def get_providers() -> dict[str, Any]:
        result = upstream_fn()
        try:
            providers = result.get("providers") if isinstance(result, dict) else None
            if isinstance(providers, list):
                for entry in providers:
                    if isinstance(entry, dict):
                        _normalize_bedrock_provider(entry)
        except Exception:
            _log.exception(
                "[fox-overlay] bedrock provider normalize failed — "
                "returning upstream get_providers() result unchanged"
            )
        return result

    setattr(get_providers, _GET_PROVIDERS_SENTINEL, True)
    get_providers.__name__ = upstream_fn.__name__
    get_providers.__doc__ = upstream_fn.__doc__
    upstream_module.get_providers = get_providers
    _log.info(
        "[fox-overlay] wrapped api.providers.get_providers — "
        "Bedrock OAuth mislabel + IMDS gate"
    )


def apply() -> None:
    # Gate IMDS before get_providers probes hermes_cli.auth.
    apply_bedrock_adapter_patches()
    apply_auth_status_patch()

    from api import providers as _u

    _wrap_get_providers(_u)
