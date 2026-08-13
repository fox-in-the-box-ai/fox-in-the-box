"""Fox: gate Bedrock auth on EC2/Lightsail IMDS instance roles.

Upstream Hermes treats any boto3-resolved credential as authenticated
Bedrock (``resolve_aws_auth_env_var`` → ``\"iam-role\"``). On AWS VMs the
default instance profile is always reachable via IMDS, so Fox/WebUI show
Bedrock as logged in (mislabelled \"OAuth\") and auto-select it — then
``InvokeModel`` fails with AccessDenied when the role has no Bedrock
rights.

Default Fox behaviour: ignore botocore credential method ``iam-role``
unless ``HERMES_BEDROCK_ALLOW_INSTANCE_ROLE=1`` (or ``true``/``yes``).

Explicit sources still count: bearer token, access keys, ``AWS_PROFILE``,
ECS container URI, IRSA web identity, and non-IMDS boto3 methods
(``shared-credentials-file``, ``container-role``, etc.).
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

_log = logging.getLogger("fox_overlay.aws_bedrock_auth")

_ADAPTER_SENTINEL = "_fox_patched_bedrock_imds_gate"
_AUTH_STATUS_SENTINEL = "_fox_patched_bedrock_auth_status"
_ALLOW_ENV = "HERMES_BEDROCK_ALLOW_INSTANCE_ROLE"

# botocore InstanceMetadataProvider reports method \"iam-role\".
_IMDS_METHODS = frozenset({"iam-role"})


def instance_role_allowed(env: Optional[Dict[str, str]] = None) -> bool:
    e = env if env is not None else os.environ
    return str(e.get(_ALLOW_ENV, "")).strip().lower() in ("1", "true", "yes")


def _boto3_credential_method() -> Optional[str]:
    """Return botocore's credential ``method`` string, or None."""
    try:
        import botocore.session

        session = botocore.session.get_session()
        credentials = session.get_credentials()
        if credentials is None:
            return None
        method = getattr(credentials, "method", None)
        # Empty/missing method returns "" so the caller gates conservatively.
        return str(method) if method else ""
    except Exception:
        return None


def apply_bedrock_adapter_patches() -> None:
    """Wrap ``agent.bedrock_adapter`` credential helpers. Idempotent."""
    try:
        from agent import bedrock_adapter as ba
    except ImportError:
        _log.debug("agent.bedrock_adapter not importable; skipping IMDS gate")
        return

    if getattr(ba, _ADAPTER_SENTINEL, False):
        return

    _orig_resolve = ba.resolve_aws_auth_env_var

    def resolve_aws_auth_env_var(
        env: Optional[Dict[str, str]] = None,
    ) -> Optional[str]:
        source = _orig_resolve(env)
        if source != "iam-role":
            return source
        # Upstream labels every boto3 fallback as \"iam-role\". Re-check the
        # real botocore method so ~/.aws/credentials still works without
        # AWS_PROFILE, while IMDS instance roles stay gated.
        method = _boto3_credential_method()
        if method in _IMDS_METHODS or method in (None, ""):
            # Empty method: conservative — treat as IMDS-like on AWS hosts.
            if not instance_role_allowed(env):
                return None
            return "iam-role"
        # shared-credentials-file, container-role, assume-role, …
        return method

    def has_aws_credentials(env: Optional[Dict[str, str]] = None) -> bool:
        # Do not fall through to upstream's second boto3 probe — that would
        # re-accept IMDS after we gated resolve_aws_auth_env_var.
        return resolve_aws_auth_env_var(env) is not None

    ba.resolve_aws_auth_env_var = resolve_aws_auth_env_var
    ba.has_aws_credentials = has_aws_credentials
    setattr(ba, _ADAPTER_SENTINEL, True)
    _log.info(
        "[fox-overlay] Bedrock IMDS instance-role gate enabled (opt-in via %s=1)",
        _ALLOW_ENV,
    )


def apply_auth_status_patch() -> None:
    """Enrich aws_sdk ``get_auth_status`` with ``key_source``. Idempotent."""
    try:
        from hermes_cli import auth as auth_mod
    except ImportError:
        _log.debug("hermes_cli.auth not importable; skipping auth_status patch")
        return

    upstream = auth_mod.get_auth_status
    if getattr(upstream, _AUTH_STATUS_SENTINEL, False):
        return

    def get_auth_status(provider_id: str) -> Dict[str, Any]:
        result = upstream(provider_id)
        if not isinstance(result, dict):
            return result
        try:
            target = str(result.get("provider") or provider_id or "").strip()
            pconfig = auth_mod.PROVIDER_REGISTRY.get(target)
            if not pconfig or getattr(pconfig, "auth_type", None) != "aws_sdk":
                return result
            if not result.get("logged_in"):
                out = dict(result)
                out.setdefault("key_source", "")
                return out
            from agent.bedrock_adapter import resolve_aws_auth_env_var

            out = dict(result)
            out["key_source"] = resolve_aws_auth_env_var() or "aws_sdk"
            return out
        except Exception:
            return result

    setattr(get_auth_status, _AUTH_STATUS_SENTINEL, True)
    get_auth_status.__name__ = upstream.__name__
    get_auth_status.__doc__ = upstream.__doc__
    auth_mod.get_auth_status = get_auth_status
    _log.info(
        "[fox-overlay] hermes_cli.auth.get_auth_status aws_sdk key_source enrich enabled"
    )
