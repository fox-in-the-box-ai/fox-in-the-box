"""Unit tests for fox_overlay.aws_bedrock_auth IMDS gate."""
from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock

import pytest

from fox_overlay import aws_bedrock_auth as gate


@pytest.fixture(autouse=True)
def _reset_sentinels(monkeypatch):
    """Each test starts without patches applied to real upstream modules."""
    # Ensure we don't leak patches across tests if agent is importable.
    yield
    for mod_name in ("agent.bedrock_adapter", "hermes_cli.auth"):
        mod = sys.modules.get(mod_name)
        if mod is None:
            continue
        if hasattr(mod, gate._ADAPTER_SENTINEL):
            try:
                delattr(mod, gate._ADAPTER_SENTINEL)
            except Exception:
                pass


def test_instance_role_allowed_default_false(monkeypatch):
    monkeypatch.delenv(gate._ALLOW_ENV, raising=False)
    assert gate.instance_role_allowed({}) is False
    assert gate.instance_role_allowed({gate._ALLOW_ENV: "0"}) is False


def test_instance_role_allowed_opt_in(monkeypatch):
    assert gate.instance_role_allowed({gate._ALLOW_ENV: "1"}) is True
    assert gate.instance_role_allowed({gate._ALLOW_ENV: "true"}) is True
    assert gate.instance_role_allowed({gate._ALLOW_ENV: "YES"}) is True


def _install_fake_bedrock_adapter(monkeypatch, *, resolve_return="iam-role"):
    """Install a minimal agent.bedrock_adapter stand-in and apply the gate."""
    adapter = ModuleType("agent.bedrock_adapter")
    adapter.resolve_aws_auth_env_var = lambda env=None: resolve_return
    adapter.has_aws_credentials = lambda env=None: resolve_return is not None

    agent_pkg = ModuleType("agent")
    agent_pkg.bedrock_adapter = adapter
    monkeypatch.setitem(sys.modules, "agent", agent_pkg)
    monkeypatch.setitem(sys.modules, "agent.bedrock_adapter", adapter)

    # Clear sentinel on module if re-used
    if hasattr(adapter, gate._ADAPTER_SENTINEL):
        delattr(adapter, gate._ADAPTER_SENTINEL)

    gate.apply_bedrock_adapter_patches()
    return adapter


def test_imds_iam_role_gated_by_default(monkeypatch):
    adapter = _install_fake_bedrock_adapter(monkeypatch, resolve_return="iam-role")
    monkeypatch.setattr(gate, "_boto3_credential_method", lambda: "iam-role")
    monkeypatch.delenv(gate._ALLOW_ENV, raising=False)

    assert adapter.resolve_aws_auth_env_var({}) is None
    assert adapter.has_aws_credentials({}) is False


def test_imds_iam_role_allowed_with_opt_in(monkeypatch):
    adapter = _install_fake_bedrock_adapter(monkeypatch, resolve_return="iam-role")
    monkeypatch.setattr(gate, "_boto3_credential_method", lambda: "iam-role")

    assert adapter.resolve_aws_auth_env_var({gate._ALLOW_ENV: "1"}) == "iam-role"
    assert adapter.has_aws_credentials({gate._ALLOW_ENV: "1"}) is True


def test_shared_credentials_file_still_counts(monkeypatch):
    adapter = _install_fake_bedrock_adapter(monkeypatch, resolve_return="iam-role")
    monkeypatch.setattr(
        gate, "_boto3_credential_method", lambda: "shared-credentials-file"
    )
    monkeypatch.delenv(gate._ALLOW_ENV, raising=False)

    assert adapter.resolve_aws_auth_env_var({}) == "shared-credentials-file"
    assert adapter.has_aws_credentials({}) is True


def test_explicit_profile_unaffected(monkeypatch):
    adapter = _install_fake_bedrock_adapter(monkeypatch, resolve_return="AWS_PROFILE")
    monkeypatch.delenv(gate._ALLOW_ENV, raising=False)

    assert adapter.resolve_aws_auth_env_var({"AWS_PROFILE": "prod"}) == "AWS_PROFILE"
    assert adapter.has_aws_credentials({"AWS_PROFILE": "prod"}) is True


def test_normalize_bedrock_provider_strips_oauth():
    from fox_overlay.webui_patches.providers import _normalize_bedrock_provider

    entry = {
        "id": "bedrock",
        "has_key": True,
        "is_oauth": True,
        "key_source": "oauth",
    }
    _normalize_bedrock_provider(entry)
    assert entry["is_oauth"] is False
    assert entry["key_source"] == "config_yaml"


def test_normalize_ignores_other_providers():
    from fox_overlay.webui_patches.providers import _normalize_bedrock_provider

    entry = {
        "id": "anthropic",
        "has_key": True,
        "is_oauth": True,
        "key_source": "oauth",
    }
    _normalize_bedrock_provider(entry)
    assert entry["is_oauth"] is True
    assert entry["key_source"] == "oauth"
