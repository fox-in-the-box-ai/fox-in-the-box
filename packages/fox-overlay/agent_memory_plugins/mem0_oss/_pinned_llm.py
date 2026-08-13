"""Pinned OpenAI LLM adapter for mem0 — neutralizes the env-first client hijack.

mem0ai 2.0.10's ``OpenAILLM.__init__`` prefers ``OPENROUTER_API_KEY`` from the
environment over the config it was handed (mem0/llms/openai.py:42-48), so a
stray exported OpenRouter key silently rebinds every openai-adapter target to
openrouter.ai.  ``PinnedOpenAILLM`` requires explicit credentials and rebuilds
the client strictly from config after parent construction, making the routing
deterministic regardless of environment contents.

Registration is lazy, guarded, and idempotent: ``ensure_registered()`` is
called from ``_get_memory()`` immediately before ``Memory`` construction.  It
also carries the audited-version tripwire — the hijack neutralization depends
on library-internal behavior verified against mem0ai 2.0.10 exactly, so any
other version fails memory loudly until re-audited.
"""

from __future__ import annotations

from mem0.llms.openai import OpenAILLM
from openai import OpenAI

# The mem0ai version whose library-internal behaviors (env-first OpenAILLM
# client construction, config-first embedder, mutable LlmFactory registry,
# qdrant no-delete-on-dims-mismatch, import-time MEM0_TELEMETRY read) were
# audited.  Bumping the pin requires re-auditing all of them.
_AUDITED_MEM0_VERSION = "2.0.10"


class PinnedOpenAILLM(OpenAILLM):
    """OpenAILLM with deterministic, config-only client construction."""

    def __init__(self, config=None):
        if config is None or not (
            getattr(config, "api_key", None)
            and getattr(config, "openai_base_url", None)
        ):
            raise ValueError(
                "mem0_oss: pinned LLM requires explicit api_key and openai_base_url"
            )
        super().__init__(config)  # may build a hijacked client; overwritten next
        self.client = OpenAI(
            api_key=self.config.api_key, base_url=self.config.openai_base_url
        )


def ensure_registered() -> None:
    """Version-tripwire + idempotent registration of the pinned adapter.

    Raises ``MemoryUnavailable(severity="error")`` when the installed mem0ai
    version differs from the audited pin.  Safe to call on every
    ``_get_memory()`` invocation.
    """
    from . import MemoryUnavailable  # lazy: avoid import cycle at package load

    import mem0

    version = str(getattr(mem0, "__version__", "unknown"))
    if version != _AUDITED_MEM0_VERSION:
        raise MemoryUnavailable(
            "installed mem0ai version {installed} does not match the audited pin "
            "{pin} — the pinned LLM adapter guards library-internal behavior and "
            "must be re-audited before a version bump".format(
                installed=version, pin=_AUDITED_MEM0_VERSION
            ),
            severity="error",
        )

    from mem0.utils.factory import LlmFactory

    # Register by dotted path: mem0's factory load_class() resolves string
    # paths; deriving from __module__ keeps this correct in both packaging
    # contexts (in-repo agent_memory_plugins.* and in-image plugins.memory.*).
    wanted = f"{PinnedOpenAILLM.__module__}.{PinnedOpenAILLM.__qualname__}"
    if LlmFactory.provider_to_class.get("openai") != wanted:
        LlmFactory.provider_to_class["openai"] = wanted
