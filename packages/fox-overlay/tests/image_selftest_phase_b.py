#!/usr/bin/env python3
"""image-selftest phase B — REAL memory activation with a stub key.

Runs INSIDE the Fox container (build-container.yml `image-selftest` job,
per-PR) via `docker exec … python3 <this file>`, as the runtime user, with a
stub ``OPENROUTER_API_KEY`` exported. The exported key is deliberately both
the credential (probe tier t3 → openrouter, design §a.1) and the hijack
vector (mem0ai 2.0.10's ``OpenAILLM.__init__`` prefers ``OPENROUTER_API_KEY``
from the environment — design §1.3).

Load-bearing assertions (design §g.3 phase B):
  1. The installed mem0ai version equals the audited pin (2.0.10) — a pin
     bump in requirements.lock cannot stay latent past this per-PR gate.
  2. The version tripwire is ARMED: with ``mem0.__version__`` monkeypatched
     to "2.1.0", ``_get_memory()`` raises ``MemoryUnavailable`` with
     ``severity="error"`` (never constructs a Memory against an un-audited
     library).
  3. Real activation: ``Mem0OSSMemoryProvider()._get_memory()`` constructs a
     mem0 ``Memory`` whose LLM is ``PinnedOpenAILLM`` (type assert — the
     load-bearing anti-hijack signal) and whose client base_url equals the
     plugin-resolved OpenRouter URL despite the exported hijack env var.
  4. One search-only op runs through the local embed-server on :8644 and
     returns a result list (search embeds the query locally and hits the
     embedded Qdrant store; it never calls the fact-extraction LLM, so the
     stub key is never sent anywhere).

HARD-FAIL contract: no importorskip, no soft skip — any failure exits
non-zero with a clear message.
"""

from __future__ import annotations

import os
import sys
import time
import urllib.error
import urllib.request

# Runtime install first (what the gateway actually imports), image copy second.
AGENT_DIR_CANDIDATES = (
    "/data/apps/hermes-agent",
    "/app/hermes-agent",
)

EMBED_HEALTH_URL = "http://127.0.0.1:8644/health"
# §1.4 semantics: ANY HTTP response (incl. errors) means the server process is
# up; only connection-refused/timeout means dead. Retries cover first-request
# model load and the --sleep-idle-seconds wake path.
EMBED_WAIT_ATTEMPTS = 12
EMBED_WAIT_DELAY_S = 5
SEARCH_ATTEMPTS = 6
SEARCH_DELAY_S = 5


def _die(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def _import_plugin():
    agent_dir = next((d for d in AGENT_DIR_CANDIDATES if os.path.isdir(d)), None)
    if agent_dir is None:
        _die(
            "no hermes-agent directory found (tried: %s) — is this running "
            "inside the Fox container?" % ", ".join(AGENT_DIR_CANDIDATES)
        )
    sys.path.insert(0, agent_dir)

    try:
        import plugins.memory.mem0_oss as plugin  # noqa: E402
        from plugins.memory.mem0_oss import _pinned_llm  # noqa: E402
    except ImportError:
        overlay_dir = "/app/fox-overlay/agent_memory_plugins"
        if not os.path.isdir(overlay_dir):
            raise
        sys.path.insert(0, overlay_dir)
        import mem0_oss as plugin  # noqa: E402
        from mem0_oss import _pinned_llm  # noqa: E402

    return plugin, _pinned_llm


def _wait_for_embed_server() -> None:
    for attempt in range(1, EMBED_WAIT_ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(EMBED_HEALTH_URL, timeout=2):
                pass
            print(f"OK: embed-server answering on :8644 (attempt {attempt})")
            return
        except urllib.error.HTTPError:
            # An HTTP error IS a response — the server process is up (§1.4).
            print(f"OK: embed-server answering on :8644 (attempt {attempt})")
            return
        except OSError:
            print(f"  embed-server not answering yet ({attempt}/{EMBED_WAIT_ATTEMPTS})")
            time.sleep(EMBED_WAIT_DELAY_S)
    _die(
        "embed-server did not answer on 127.0.0.1:8644 within "
        f"{EMBED_WAIT_ATTEMPTS * EMBED_WAIT_DELAY_S}s — check "
        "/data/logs/embed-server.err"
    )


def main() -> None:
    stub_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not stub_key:
        _die(
            "OPENROUTER_API_KEY must be exported (stub value) — it is both "
            "the resolution credential and the §1.3 hijack condition"
        )

    plugin, _pinned_llm = _import_plugin()

    import mem0  # noqa: E402  (hard import — mem0ai is baked into the image)

    # ── 1. Audited pin holds in-image ───────────────────────────────────────
    installed = str(getattr(mem0, "__version__", "unknown"))
    if installed != _pinned_llm._AUDITED_MEM0_VERSION:
        _die(
            f"installed mem0ai version {installed!r} does not equal the "
            f"audited pin {_pinned_llm._AUDITED_MEM0_VERSION!r} — "
            "requirements.lock and _pinned_llm drifted; re-audit before "
            "bumping either"
        )
    if _pinned_llm._AUDITED_MEM0_VERSION != "2.0.10":
        _die(
            "audited pin changed to "
            f"{_pinned_llm._AUDITED_MEM0_VERSION!r} without updating this "
            "selftest — re-audit mem0's library internals (design §1.3) and "
            "update phase B deliberately"
        )
    print(f"OK: mem0ai {installed} matches the audited pin")

    provider = plugin.Mem0OSSMemoryProvider()

    # ── 2. Tripwire is ARMED: un-audited version fails loudly ──────────────
    original_version = mem0.__version__
    try:
        mem0.__version__ = "2.1.0"
        try:
            provider._get_memory()
        except plugin.MemoryUnavailable as exc:
            if exc.severity != "error":
                _die(
                    "version tripwire raised MemoryUnavailable with "
                    f"severity={exc.severity!r} — must be 'error' (explicit, "
                    "visible failure until re-audit)"
                )
            print("OK: version tripwire armed (2.1.0 → MemoryUnavailable/error)")
        except Exception as exc:  # noqa: BLE001 — diagnostic reporting only
            _die(
                "version tripwire raised the wrong exception type "
                f"{type(exc).__name__}: {exc}"
            )
        else:
            _die(
                "version tripwire NOT armed — _get_memory() succeeded with "
                "mem0.__version__ == '2.1.0'"
            )
    finally:
        mem0.__version__ = original_version

    # ── 3. Real activation: pinned LLM + anti-hijack base_url ──────────────
    _wait_for_embed_server()

    memory = provider._get_memory()  # raises loudly on failure — correct signal

    llm = getattr(memory, "llm", None)
    if not isinstance(llm, _pinned_llm.PinnedOpenAILLM):
        _die(
            "constructed Memory.llm is "
            f"{type(llm).__name__ if llm is not None else None!r}, not "
            "PinnedOpenAILLM — the §1.3 hijack neutralization is not on the "
            "real construction path"
        )
    print("OK: Memory.llm is PinnedOpenAILLM (anti-hijack adapter active)")

    resolved = plugin._resolve_memoized()
    if resolved.provider_id != "openrouter":
        _die(
            f"expected the stub OPENROUTER_API_KEY to resolve provider "
            f"'openrouter' (probe tier t3), got {resolved.provider_id!r} — "
            "did the image default config start shipping a provider?"
        )
    client_url = str(getattr(llm.client, "base_url", "")).rstrip("/")
    resolved_url = resolved.base_url.rstrip("/")
    if not resolved_url or client_url != resolved_url:
        _die(
            f"client base_url {client_url!r} != plugin-resolved OpenRouter "
            f"URL {resolved_url!r} — the exported OPENROUTER_API_KEY hijack "
            "condition redirected the client (design §1.3 regression)"
        )
    print(f"OK: client base_url pinned to the resolved URL ({client_url})")

    # ── 4. Search-only op through the local embed-server ────────────────────
    user_id = provider._runtime_cfg.get("user_id", "hermes-user")
    last_exc: Exception | None = None
    results = None
    for attempt in range(1, SEARCH_ATTEMPTS + 1):
        try:
            results = memory.search(
                "what do you know about the fox?", user_id=user_id, limit=3
            )
            last_exc = None
            break
        except Exception as exc:  # noqa: BLE001 — retried, then reported verbatim
            last_exc = exc
            print(f"  search attempt {attempt}/{SEARCH_ATTEMPTS} failed: {exc}")
            time.sleep(SEARCH_DELAY_S)
    if last_exc is not None:
        _die(
            f"search op did not succeed after {SEARCH_ATTEMPTS} attempts — "
            f"last error: {type(last_exc).__name__}: {last_exc}"
        )

    # Shape-tolerant: mem0 2.x returns {"results": [...]}; older API a list.
    if isinstance(results, dict):
        result_list = results.get("results")
    else:
        result_list = results
    if not isinstance(result_list, list):
        _die(
            "search op returned no result list "
            f"(got {type(results).__name__}: {results!r})"
        )
    print(
        f"OK: search op ran through embed-server :8644 and returned a list "
        f"({len(result_list)} results)"
    )


if __name__ == "__main__":
    main()
