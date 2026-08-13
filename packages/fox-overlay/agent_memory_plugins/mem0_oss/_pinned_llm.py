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

    # mem0ai 2.0.10's registry maps provider names to
    # (dotted_path_string, config_class) 2-tuples: Factory.create unpacks the
    # tuple (factory.py:80) and resolves element 0 via load_class(), which
    # rsplits the STRING (factory.py:27-30). Verified against the published
    # 2.0.10 wheel after image-selftest phase B caught two wrong models in a
    # row (bare string, then class-object tuple). Replace only the path
    # element, preserve the stock config class; deriving the path from
    # __module__ keeps it importable in both packaging contexts.
    entry = LlmFactory.provider_to_class.get("openai")
    if not (isinstance(entry, tuple) and len(entry) == 2 and isinstance(entry[0], str)):
        raise MemoryUnavailable(
            "mem0 LlmFactory registry shape changed: expected a "
            "(dotted_path_str, config_class) tuple for 'openai', got {got!r} — "
            "re-audit the pinned adapter against this mem0 version".format(got=entry),
            severity="error",
        )
    wanted = f"{PinnedOpenAILLM.__module__}.{PinnedOpenAILLM.__qualname__}"
    if entry[0] != wanted:
        LlmFactory.provider_to_class["openai"] = (wanted, entry[1])
