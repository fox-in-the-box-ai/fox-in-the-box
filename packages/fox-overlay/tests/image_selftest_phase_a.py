#!/usr/bin/env python3
"""image-selftest phase A — in-image sync assertions for the mem0_oss plugin.

Asserts that the plugin's provider fallback tables (`_WELL_KNOWN`,
`_POOL_ID_MAP`) stay in sync with the read-only hermes_cli surfaces they
mirror. Runs INSIDE the Fox container (build-container.yml `image-selftest`
job, per-PR) via `docker exec … python3 <this file>` — the only context where
the full hermes-agent import surface (hermes_cli.auth, hermes_constants,
httpx) is guaranteed importable. validate-overlay's pytest context has neither
forks/hermes-agent on PYTHONPATH nor httpx installed, so these assertions
deliberately do NOT live there.

HARD-FAIL contract: no importorskip, no soft skip. Any import failure or
assertion mismatch exits non-zero with a clear message — table drift against
hermes_cli is a release blocker, never a skipped test.

Per-row sync sources (design §a.0):
  openai-api    → PROVIDER_REGISTRY["openai-api"] (env vars + inference URL)
  anthropic     → PROVIDER_REGISTRY["anthropic"] — SUBSET + FIRST-VAR only
                  (the registry tuple is a 3-tuple incl. OAuth-token extras;
                  tuple equality would be wrong by design)
  openrouter    → hermes_constants.OPENROUTER_BASE_URL for the URL
                  (PROVIDER_REGISTRY has NO openrouter entry) + the auth.py
                  auto-chain literal OPENROUTER_API_KEY for the env var
  azure-foundry → PROVIDER_REGISTRY["azure-foundry"] first env var; the URL
                  entry is "" (registry inference_base_url is "" — the
                  endpoint resolves via AZURE_FOUNDRY_BASE_URL at runtime)
  _POOL_ID_MAP  → every value is a PROVIDER_REGISTRY key, every key is a
                  canonical providers.py id, and each entry round-trips
                  through hermes_cli.providers.ALIASES (pool id → providers id)
"""

from __future__ import annotations

import os
import sys

# Runtime install first (what the gateway actually imports), image copy second.
AGENT_DIR_CANDIDATES = (
    "/data/apps/hermes-agent",
    "/app/hermes-agent",
)


def _die(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def _import_surfaces():
    agent_dir = next((d for d in AGENT_DIR_CANDIDATES if os.path.isdir(d)), None)
    if agent_dir is None:
        _die(
            "no hermes-agent directory found (tried: %s) — is this running "
            "inside the Fox container?" % ", ".join(AGENT_DIR_CANDIDATES)
        )
    sys.path.insert(0, agent_dir)

    # Real imports, read-only. An ImportError here is a hard failure by
    # contract — never downgraded to a skip.
    from hermes_cli.auth import PROVIDER_REGISTRY  # noqa: E402
    from hermes_cli.providers import ALIASES, HERMES_OVERLAYS  # noqa: E402
    from hermes_constants import OPENROUTER_BASE_URL  # noqa: E402

    # The plugin ships into hermes-agent's plugins/memory/ (install-core
    # _install_memory_plugins), importable as plugins.memory.mem0_oss with the
    # agent dir on sys.path. Fall back to the image's fox-overlay source copy.
    try:
        from plugins.memory.mem0_oss import _POOL_ID_MAP, _WELL_KNOWN  # noqa: E402
    except ImportError:
        overlay_dir = "/app/fox-overlay/agent_memory_plugins"
        if not os.path.isdir(overlay_dir):
            raise
        sys.path.insert(0, overlay_dir)
        from mem0_oss import _POOL_ID_MAP, _WELL_KNOWN  # noqa: E402

    return (
        PROVIDER_REGISTRY,
        ALIASES,
        HERMES_OVERLAYS,
        OPENROUTER_BASE_URL,
        _WELL_KNOWN,
        _POOL_ID_MAP,
    )


def main() -> None:
    (
        registry,
        aliases,
        overlays,
        openrouter_base_url,
        well_known,
        pool_id_map,
    ) = _import_surfaces()

    errors: list[str] = []

    def check(cond: bool, msg: str) -> None:
        if not cond:
            errors.append(msg)

    # ── _WELL_KNOWN shape ────────────────────────────────────────────────────
    for row in ("openai-api", "openrouter", "anthropic", "azure-foundry"):
        check(row in well_known, f"_WELL_KNOWN is missing the '{row}' row")
    if errors:
        for e in errors:
            print(f"FAIL: {e}", file=sys.stderr)
        sys.exit(1)

    # ── openai-api: full equality vs PROVIDER_REGISTRY ───────────────────────
    reg = registry["openai-api"]
    tbl_vars, tbl_url = well_known["openai-api"]
    check(
        tuple(tbl_vars) == tuple(reg.api_key_env_vars),
        "openai-api env vars drifted: _WELL_KNOWN=%r vs PROVIDER_REGISTRY=%r"
        % (tbl_vars, reg.api_key_env_vars),
    )
    check(
        tbl_url == reg.inference_base_url,
        "openai-api URL drifted: _WELL_KNOWN=%r vs PROVIDER_REGISTRY=%r"
        % (tbl_url, reg.inference_base_url),
    )

    # ── anthropic: SUBSET + FIRST-VAR (never tuple equality) ────────────────
    reg = registry["anthropic"]
    tbl_vars, tbl_url = well_known["anthropic"]
    check(
        set(tbl_vars) <= set(reg.api_key_env_vars),
        "anthropic env vars drifted: _WELL_KNOWN=%r is not a subset of "
        "PROVIDER_REGISTRY=%r" % (tbl_vars, reg.api_key_env_vars),
    )
    check(
        len(tbl_vars) > 0
        and len(reg.api_key_env_vars) > 0
        and tbl_vars[0] == reg.api_key_env_vars[0],
        "anthropic first env var drifted: _WELL_KNOWN[0]=%r vs "
        "PROVIDER_REGISTRY[0]=%r"
        % (
            tbl_vars[0] if tbl_vars else None,
            reg.api_key_env_vars[0] if reg.api_key_env_vars else None,
        ),
    )
    check(
        tbl_url == reg.inference_base_url,
        "anthropic URL drifted: _WELL_KNOWN=%r vs PROVIDER_REGISTRY=%r"
        % (tbl_url, reg.inference_base_url),
    )

    # ── openrouter: hermes_constants URL + auto-chain literal env var ───────
    check(
        "openrouter" not in registry,
        "PROVIDER_REGISTRY gained an 'openrouter' entry — the _WELL_KNOWN "
        "openrouter row's sync source (hermes_constants + the auth.py "
        "auto-chain literal) must be re-evaluated against it",
    )
    tbl_vars, tbl_url = well_known["openrouter"]
    check(
        tbl_url == openrouter_base_url,
        "openrouter URL drifted: _WELL_KNOWN=%r vs "
        "hermes_constants.OPENROUTER_BASE_URL=%r" % (tbl_url, openrouter_base_url),
    )
    check(
        tuple(tbl_vars) == ("OPENROUTER_API_KEY",),
        "openrouter env vars drifted: _WELL_KNOWN=%r vs the auth.py "
        "auto-chain literal ('OPENROUTER_API_KEY',)" % (tbl_vars,),
    )

    # ── azure-foundry: registry first var; URL entry deliberately "" ────────
    reg = registry["azure-foundry"]
    tbl_vars, tbl_url = well_known["azure-foundry"]
    check(
        len(tbl_vars) > 0
        and len(reg.api_key_env_vars) > 0
        and tbl_vars[0] == reg.api_key_env_vars[0],
        "azure-foundry first env var drifted: _WELL_KNOWN[0]=%r vs "
        "PROVIDER_REGISTRY[0]=%r"
        % (
            tbl_vars[0] if tbl_vars else None,
            reg.api_key_env_vars[0] if reg.api_key_env_vars else None,
        ),
    )
    check(
        tbl_url == "" and reg.inference_base_url == "",
        "azure-foundry URL expectation drifted: _WELL_KNOWN=%r, "
        "PROVIDER_REGISTRY.inference_base_url=%r — both must be '' (the "
        "endpoint is user-provided via AZURE_FOUNDRY_BASE_URL)"
        % (tbl_url, reg.inference_base_url),
    )

    # ── _POOL_ID_MAP: providers-id → registry/pool-id bridge ────────────────
    alias_targets = set(aliases.values())
    for prov_id, pool_id in pool_id_map.items():
        check(
            pool_id in registry,
            "_POOL_ID_MAP value %r (for key %r) is not a PROVIDER_REGISTRY "
            "key — pool lookups through it can never hit" % (pool_id, prov_id),
        )
        check(
            prov_id in overlays or prov_id in alias_targets,
            "_POOL_ID_MAP key %r is not a canonical providers.py id (not in "
            "HERMES_OVERLAYS or ALIASES targets) — the id spaces converged "
            "or diverged; re-verify the bridge" % (prov_id,),
        )
        check(
            aliases.get(pool_id) == prov_id,
            "_POOL_ID_MAP entry %r → %r does not round-trip through "
            "hermes_cli.providers.ALIASES (ALIASES[%r]=%r)"
            % (prov_id, pool_id, pool_id, aliases.get(pool_id)),
        )

    if errors:
        for e in errors:
            print(f"FAIL: {e}", file=sys.stderr)
        print(
            f"FAIL: {len(errors)} sync assertion(s) failed — _WELL_KNOWN/"
            "_POOL_ID_MAP drifted against hermes_cli",
            file=sys.stderr,
        )
        sys.exit(1)

    print("OK: _WELL_KNOWN rows match their hermes_cli sync sources")
    print("OK: _POOL_ID_MAP entries are registry-valid and ALIASES round-trip")


if __name__ == "__main__":
    main()
