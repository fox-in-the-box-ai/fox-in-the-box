"""Boot-time memory preflight (design §1.5).

Runs from entrypoint step 5d, before the gateway starts:

    python3 -m plugins.memory.mem0_oss.preflight

Properties:
  * refuses to run as root (uid 0) — must run as the service user so the
    seeded state.json is writable by the gateway;
  * resolves the memory provider via the plugin's ``_resolve`` pipeline —
    NO embed-server (:8644) probe.  Resolution MAY perform one bounded
    models.dev catalog fetch (15 s library timeout, at most once per memo
    window, and only when no disk cache exists) — the flagship providers
    never need it (well-known table, §a.0);
  * prints exactly one ``memory: READY|OFF|ERROR — <reason>`` line;
  * atomically seeds state.json;
  * exits 0 on every resolution outcome; a ``PermissionError`` writing
    state.json is a loud ERROR (nonzero exit — the entrypoint wrapper is
    warn-never-fail either way).
"""

from __future__ import annotations

import os
import sys


def main() -> int:
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        print(
            "memory: ERROR — preflight refuses to run as root (uid 0); "
            "run as the service user"
        )
        return 1

    # Telemetry kill before any mem0 import (the package import below also
    # sets it; setdefault here keeps the guarantee even if imports reorder).
    os.environ.setdefault("MEM0_TELEMETRY", "False")

    from . import (
        MemoryUnavailable,
        _read_file_overrides,
        _resolve_embedder,
        _resolve_memoized,
        _write_state,
    )

    try:
        try:
            resolved = _resolve_memoized()
            embedder = _resolve_embedder(_read_file_overrides())
        except MemoryUnavailable as exc:
            status = "error" if exc.severity == "error" else "off"
            _write_state(status, exc.reason, strict=True)
            print(f"memory: {'ERROR' if status == 'error' else 'OFF'} — {exc.reason}")
            return 0
        _write_state(
            "ready",
            "",
            llm=resolved.provider_id,
            embedder=embedder["description"],
            strict=True,
        )
        print(
            f"memory: READY — llm={resolved.provider_id}, "
            f"embedder={embedder['description']}"
        )
        return 0
    except PermissionError as exc:
        # Loud: a state file the service user cannot write means every later
        # state transition would be invisible too.
        print(f"memory: ERROR — cannot write memory state file: {exc}")
        return 1
    except Exception as exc:  # job boundary: one line, never a traceback
        print(f"memory: ERROR — preflight failed unexpectedly: {exc!r}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
