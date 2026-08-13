"""Fox agent patch: Bedrock IMDS instance-role gate.

Delegates to :mod:`fox_overlay.aws_bedrock_auth` so the gateway process
and WebUI share one implementation.
"""
from fox_overlay.aws_bedrock_auth import (
    apply_auth_status_patch,
    apply_bedrock_adapter_patches,
)


def apply() -> None:
    apply_bedrock_adapter_patches()
    apply_auth_status_patch()
