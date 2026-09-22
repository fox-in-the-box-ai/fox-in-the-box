"""Embedded → server Qdrant memory migration (issue #780).

Fox memory has two physically distinct vector stores:

  * **Embedded** — on-disk Qdrant opened in LOCAL mode at
    ``$HERMES_HOME/mem0_oss/qdrant`` (the historical default; exclusive
    file lock, one process at a time).
  * **Server**   — the in-container Qdrant server reached over HTTP at
    ``127.0.0.1:6333`` (the #780 server mode; shared by gateway + WebUI).

Switching a live install from embedded to server mode strands every memory
already written to the embedded store — they live in a different physical
place.  This module copies them across.

The vectors are ALREADY computed (768-dim nomic); migration is a pure
POINT-COPY — id + vector + payload verbatim — never a re-embed.  Three
invariants hold it together:

  * **Dims guard** — the source collection must hold ``expected_dims``
    (768) vectors, and any pre-existing destination collection must match
    the source.  A mismatch ABORTS LOUDLY (``MigrationError``) rather than
    silently corrupting the store.  (Mirrors the plugin's
    ``_check_collection_dims`` shape-tolerant read.)
  * **Idempotent** — points are upserted under their own stable ids, so a
    re-run after a crash replaces in place and never duplicates.
  * **Lossless** — the stored vector and payload are copied exactly; the
    embedder is never invoked.

This module ships the mechanism only.  It is NOT auto-invoked from
preflight or plugin initialize — #803 wires it into the mode switch.  Run
it explicitly inside the running container, where the overlay is installed
as the ``plugins.memory`` package (``agent_memory_plugins/`` is COPYd to
``<hermes-agent>/plugins/memory/`` at build/install time):

    python3 -m plugins.memory.mem0_oss.migrate_store

(with the hermes-agent root on ``PYTHONPATH`` — the same invocation shape
as the boot preflight).  From a source checkout under
``packages/fox-overlay/`` the package is instead ``agent_memory_plugins``.

``qdrant_client`` is imported lazily (only ``run_migration`` / the CLI need
it), so the pure ``migrate_store`` core can be exercised against hand-rolled
fakes without the dependency installed.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Single source of truth for the migration defaults.  These mirror the
# plugin's own defaults (see __init__.py: _LOCAL_EMBED_DIMS, the "hermes"
# collection, and the embedded vector-store path) but are restated here so
# this module imports without the heavy plugin package (and its
# hermes-agent runtime deps).
DEFAULT_COLLECTION = "hermes"
DEFAULT_DIMS = 768
DEFAULT_SERVER_URL = "http://127.0.0.1:6333"
DEFAULT_SCROLL_BATCH = 256

# External-call timeout for the server client (seconds).  No timeout means an
# infinite hang on a stuck server; the migration is a one-shot job, so a
# generous-but-bounded value is right.
_SERVER_TIMEOUT_S = 30.0

# ── Boot migration (issue #803) ────────────────────────────────────────────
# The sentinel that records a completed (or verified-empty) embedded→server
# migration.  It lives beside the embedded store under $HERMES_HOME/mem0_oss/.
# WRITE-ORDERING invariant: the sentinel is written ONLY after a verified
# success or a verified-empty source — NEVER before the server is touched and
# NEVER on a partial/crashed run — so a crashed run re-attempts on the next
# boot instead of silently marking itself done.
_SENTINEL_NAME = ".migrated-to-server"
_SENTINEL_SCHEMA = 1

# Truthy spellings for MEM0_OSS_DISABLED.  Mirrors __init__._TRUE_VALUES, restated
# so this module stays free of the heavy plugin package (issue #803 keeps the
# boot wrapper decoupled from __init__).
_TRUE_VALUES = {"1", "true", "yes", "on"}

# Boot /readyz poll bounds: a one-shot job can wait out a slow Qdrant start, but
# must give up rather than hang the migration unit forever.  A 2 s per-attempt
# timeout across up to 15 attempts with a 2 s sleep between them ≈ 30 s worst
# case before the job gives up (and retries on the next boot).
_READYZ_TIMEOUT_S = 2.0
_READYZ_ATTEMPTS = 15
_READYZ_SLEEP_S = 2.0


class MigrationError(RuntimeError):
    """A migration could not complete.  The message names the fix.

    Raised for a dims mismatch, an unreachable server, a read failure, or a
    write failure — every fail-loud path lands here with context.
    """


@dataclass
class MigrationSummary:
    """Result of a completed migration — returned to the caller and printed."""

    collection: str
    dims: int
    source_count: int
    migrated: int

    def __str__(self) -> str:  # human-readable one-liner for the CLI
        return (
            f"migrated {self.migrated}/{self.source_count} points into "
            f"collection {self.collection!r} ({self.dims}-dim)"
        )


# ---------------------------------------------------------------------------
# Dims reading — shape-tolerant, mirrors _check_collection_dims in __init__.py
# ---------------------------------------------------------------------------


def _vector_size(client: Any, collection: str) -> Optional[int]:
    """Read a collection's vector dimension, or ``None`` if the collection is
    absent.  Tolerant of both the single-vector (``params.size``) and named-
    vector (``{name: VectorParams}``) shapes, exactly like the plugin's
    ``_check_collection_dims``.  A genuinely unreachable client raises so the
    caller can fail loud — only a *missing collection* returns ``None``."""
    try:
        info = client.get_collection(collection)
    except Exception:
        # Collection absent (or API drift) — treated as "not present" so the
        # caller can create it.  A transport failure surfaces later on the
        # first scroll/upsert, which wraps it into a MigrationError.
        return None
    params = info.config.params.vectors
    if hasattr(params, "size"):
        return int(params.size)
    if isinstance(params, dict):
        for value in params.values():
            candidate = getattr(value, "size", None)
            if candidate is not None:
                return int(candidate)
    return None


def _vector_distance(client: Any, collection: str) -> Any:
    """Read a collection's distance metric so a newly created destination
    mirrors the source.  Returns ``None`` when it cannot be determined (the
    caller then falls back to the models' default)."""
    try:
        info = client.get_collection(collection)
        params = info.config.params.vectors
    except Exception:
        return None
    if hasattr(params, "distance"):
        return params.distance
    if isinstance(params, dict):
        for value in params.values():
            distance = getattr(value, "distance", None)
            if distance is not None:
                return distance
    return None


# ---------------------------------------------------------------------------
# Pure migration core — injectable clients, testable with fakes
# ---------------------------------------------------------------------------


def _scroll_all(source: Any, collection: str, batch_size: int) -> List[Any]:
    """Read every point (id + vector + payload) from the source collection
    using scroll pagination.  Fails loud on a read error."""
    records: List[Any] = []
    offset: Any = None
    try:
        while True:
            batch, offset = source.scroll(
                collection_name=collection,
                limit=batch_size,
                offset=offset,
                with_vectors=True,
                with_payload=True,
            )
            records.extend(batch)
            if offset is None:
                break
    except Exception as exc:  # external read boundary — wrap with context
        raise MigrationError(
            f"failed reading embedded collection {collection!r}: {exc}"
        ) from exc
    return records


def _ensure_dest_collection(
    dest: Any,
    collection: str,
    dims: int,
    distance: Any,
    models: Any,
) -> None:
    """Create the destination collection with matching dims if absent; if it
    already exists, assert its dims match the source and ABORT LOUDLY
    otherwise (never upsert into a mismatched store)."""
    existing = _vector_size(dest, collection)
    if existing is not None:
        if existing != dims:
            raise MigrationError(
                f"destination collection {collection!r} holds {existing}-dim "
                f"vectors but the source holds {dims}-dim vectors — refusing "
                "to migrate into a mismatched store (this would corrupt "
                "search); reconcile the embedder dimensions first"
            )
        return  # matching collection already present — nothing to create
    vectors_config = models.VectorParams(
        size=dims,
        distance=distance if distance is not None else models.Distance.COSINE,
    )
    try:
        dest.create_collection(
            collection_name=collection, vectors_config=vectors_config
        )
    except Exception as exc:  # external write boundary — wrap with context
        raise MigrationError(
            f"failed creating destination collection {collection!r}: {exc}"
        ) from exc


def _upsert_all(
    dest: Any,
    collection: str,
    records: List[Any],
    models: Any,
    batch_size: int,
) -> int:
    """Upsert points under their own stable ids (idempotent — a re-run
    replaces in place, never duplicates).  Copies the stored vector and
    payload verbatim; never re-embeds.  Fails loud on a write error."""
    migrated = 0
    try:
        for start in range(0, len(records), batch_size):
            chunk = records[start : start + batch_size]
            points = [
                models.PointStruct(
                    id=record.id,
                    vector=record.vector,
                    payload=record.payload,
                )
                for record in chunk
            ]
            dest.upsert(collection_name=collection, points=points)
            migrated += len(points)
    except Exception as exc:  # external write boundary — wrap with context
        raise MigrationError(
            f"failed writing to destination collection {collection!r} after "
            f"{migrated} point(s): {exc}"
        ) from exc
    return migrated


def migrate_store(
    source: Any,
    dest: Any,
    *,
    collection: str = DEFAULT_COLLECTION,
    expected_dims: int = DEFAULT_DIMS,
    models: Any = None,
    batch_size: int = DEFAULT_SCROLL_BATCH,
) -> MigrationSummary:
    """Copy every point from the embedded ``source`` client to the server
    ``dest`` client.

    ``source`` and ``dest`` are qdrant-client-shaped objects (real
    ``QdrantClient`` instances in production; hand-rolled fakes in tests).
    ``models`` is the ``qdrant_client.models`` namespace, imported lazily
    when not supplied so this core stays usable without the dependency.

    Guards, in order:
      1. Source collection must hold ``expected_dims`` vectors — else abort.
      2. Destination, if it exists, must match the source dims — else abort.
         If absent, it is created with the source dims + distance.
      3. Points upsert under their own ids (idempotent) with vector + payload
         copied verbatim (lossless).

    Returns a :class:`MigrationSummary`.  Raises :class:`MigrationError` on
    any dims mismatch, read failure, or write failure.
    """
    if models is None:
        from qdrant_client import models  # lazy: prod-only dep

    source_dims = _vector_size(source, collection)
    if source_dims is None:
        raise MigrationError(
            f"source collection {collection!r} not found in the embedded "
            "store — nothing to migrate (is MEM0_OSS_VECTOR_STORE_PATH "
            "correct?)"
        )
    if source_dims != expected_dims:
        raise MigrationError(
            f"source collection {collection!r} holds {source_dims}-dim "
            f"vectors but {expected_dims} was expected — aborting rather than "
            "migrating a store the configured embedder cannot read; set "
            "expected_dims to the store's real dimension only if you know it "
            "is correct"
        )

    distance = _vector_distance(source, collection)
    _ensure_dest_collection(dest, collection, source_dims, distance, models)

    records = _scroll_all(source, collection, batch_size)
    migrated = _upsert_all(dest, collection, records, models, batch_size)

    logger.info(
        "mem0_oss.migrate: collection=%s dims=%d source_count=%d migrated=%d",
        collection,
        source_dims,
        len(records),
        migrated,
    )
    return MigrationSummary(
        collection=collection,
        dims=source_dims,
        source_count=len(records),
        migrated=migrated,
    )


# ---------------------------------------------------------------------------
# Composition root — opens the real qdrant clients, then delegates
# ---------------------------------------------------------------------------


def _default_source_path() -> str:
    """The embedded store path, honoring the same override the plugin uses."""
    override = os.environ.get("MEM0_OSS_VECTOR_STORE_PATH")
    if override:
        return override
    hermes_home = os.environ.get("HERMES_HOME", "/data/data/hermes")
    return str(Path(hermes_home) / "mem0_oss" / "qdrant")


def run_migration(
    *,
    source_path: Optional[str] = None,
    server_url: Optional[str] = None,
    collection: Optional[str] = None,
    expected_dims: Optional[int] = None,
    api_key: Optional[str] = None,
) -> MigrationSummary:
    """Open the embedded (local-mode) and server (HTTP) Qdrant clients and run
    the migration.  This is the only function that touches ``qdrant_client``
    and real connections; everything else is injectable.

    Defaults resolve from the plugin's environment: the embedded path from
    ``MEM0_OSS_VECTOR_STORE_PATH`` / ``$HERMES_HOME``, the server from
    ``MEM0_OSS_QDRANT_URL`` (else ``127.0.0.1:6333``), the collection from
    ``MEM0_OSS_COLLECTION``, and the dims from ``MEM0_OSS_EMBEDDER_DIMS``.
    """
    from qdrant_client import QdrantClient  # lazy: prod-only dep

    source_path = source_path or _default_source_path()
    server_url = (
        server_url
        or os.environ.get("MEM0_OSS_QDRANT_URL", "").strip()
        or DEFAULT_SERVER_URL
    )
    collection = collection or os.environ.get("MEM0_OSS_COLLECTION", DEFAULT_COLLECTION)
    if expected_dims is None:
        expected_dims = int(os.environ.get("MEM0_OSS_EMBEDDER_DIMS", DEFAULT_DIMS))
    api_key = api_key or os.environ.get("MEM0_OSS_QDRANT_API_KEY", "").strip() or None

    if not Path(source_path).exists():
        raise MigrationError(
            f"embedded store path does not exist: {source_path} — nothing to migrate"
        )

    source = QdrantClient(path=source_path)
    try:
        dest = QdrantClient(
            url=server_url,
            api_key=api_key,
            timeout=int(_SERVER_TIMEOUT_S),
            # Suppress qdrant-client's client/server version-skew warning on an
            # otherwise-successful migrate, matching the op-path client in
            # __init__._build_qdrant_client (the server is pinned in lockstep
            # with the client, so the check is noise here).
            check_compatibility=False,
        )
        try:
            return migrate_store(
                source,
                dest,
                collection=collection,
                expected_dims=expected_dims,
            )
        finally:
            _safe_close(dest)
    finally:
        # Release the embedded file lock promptly so the plugin can reopen it.
        _safe_close(source)


def _safe_close(client: Any) -> None:
    close = getattr(client, "close", None)
    if callable(close):
        try:
            close()
        except Exception:  # closing must never mask the real result
            logger.debug("mem0_oss.migrate: client close failed", exc_info=True)


# ---------------------------------------------------------------------------
# Boot migration (issue #803) — one-shot, sentinel-guarded, self-contained
# ---------------------------------------------------------------------------
#
# Wired into supervisord as [program:mem0-migrate] (autostart, autorestart=false)
# ahead of the gateway/webui, so a live install that just flipped to Qdrant
# server mode copies its embedded memories across exactly once, before either
# process opens memory.  This wrapper stays decoupled from the heavy plugin
# ``__init__`` (no import of it): server-mode detection, the /readyz poll, and
# the state idioms are reimplemented here against stdlib only.


def _boot_server_url() -> str:
    """Resolve the destination server URL from the env exactly as the plugin
    does — ``MEM0_OSS_QDRANT_URL`` wins; otherwise a bare
    ``MEM0_OSS_QDRANT_HOST`` (+ ``_PORT``) is composed into one (HTTPS iff an
    api key is present, mirroring ``__init__._resolve_qdrant_target``).  Returns
    ``""`` when neither is set — i.e. the install is still on the embedded
    store and there is nothing to migrate to."""
    url = os.environ.get("MEM0_OSS_QDRANT_URL", "").strip()
    if url:
        return url
    host = os.environ.get("MEM0_OSS_QDRANT_HOST", "").strip()
    if not host:
        return ""
    port = os.environ.get("MEM0_OSS_QDRANT_PORT", "6333").strip() or "6333"
    scheme = (
        "https" if os.environ.get("MEM0_OSS_QDRANT_API_KEY", "").strip() else "http"
    )
    return f"{scheme}://{host}:{port}"


def _sentinel_path() -> Path:
    """``$HERMES_HOME/mem0_oss/.migrated-to-server`` — HERMES_HOME from the env,
    same default the embedded-store path resolution uses."""
    hermes_home = os.environ.get("HERMES_HOME", "/data/data/hermes")
    return Path(hermes_home) / "mem0_oss" / _SENTINEL_NAME


def _write_sentinel(reason: str, source_count: int, migrated: int) -> None:
    """Atomically write the migration sentinel (tmp + os.replace, mirroring
    ``__init__._write_state``).  Called ONLY on verified success or a
    verified-empty source — see the WRITE-ORDERING invariant above."""
    payload = {
        "schema": _SENTINEL_SCHEMA,
        "reason": reason,
        "migrated_at": int(time.time()),
        "collection": DEFAULT_COLLECTION,
        "dims": DEFAULT_DIMS,
        "source_count": source_count,
        "migrated": migrated,
    }
    path = _sentinel_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / f".{path.name}.{os.getpid()}.tmp"
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _wait_for_readyz(server_url: str, api_key: str = "") -> bool:
    """Poll ``<server_url>/readyz`` until the server answers or the bounded
    budget is spent.  ANY HTTP response (including 5xx while Qdrant warms up)
    means the server is live; only connection-refused / timeout / DNS failure
    counts as not-ready.  Self-contained ``urllib`` — deliberately NOT importing
    ``__init__._qdrant_server_healthy`` (same shape, local reimplementation)."""
    import urllib.error
    import urllib.request

    readyz_url = server_url.rstrip("/") + "/readyz"
    for attempt in range(1, _READYZ_ATTEMPTS + 1):
        req = urllib.request.Request(readyz_url, method="GET")
        if api_key:
            req.add_header("api-key", api_key)
        try:
            with urllib.request.urlopen(req, timeout=_READYZ_TIMEOUT_S):
                return True
        except urllib.error.HTTPError:
            return True  # an HTTP status IS a live server (readiness-agnostic)
        except Exception:
            pass  # refused / timeout / DNS — not ready yet, keep polling
        if attempt < _READYZ_ATTEMPTS:
            time.sleep(_READYZ_SLEEP_S)
    return False


def _load_qdrant_models() -> Any:
    """The ``qdrant_client.models`` namespace — a seam so tests can inject
    fakes without the dependency installed."""
    from qdrant_client import models  # lazy: prod-only dep

    return models


def _open_boot_clients(
    source_path: str, server_url: str, api_key: str
) -> Tuple[Any, Any]:
    """Open the embedded (local-mode) source and server (HTTP) dest clients.
    The sole ``qdrant_client``-touching seam of the boot path, monkeypatched in
    tests with hand-rolled fakes."""
    from qdrant_client import QdrantClient  # lazy: prod-only dep

    source = QdrantClient(path=source_path)
    dest = QdrantClient(
        url=server_url,
        api_key=api_key or None,
        timeout=int(_SERVER_TIMEOUT_S),
        check_compatibility=False,
    )
    return source, dest


def _dest_count(client: Any, collection: str) -> int:
    """Read the destination point count back from the server to VERIFY the
    upsert actually landed — the migration core returns the *attempted* count,
    not a server-confirmed one."""
    try:
        result = client.count(collection_name=collection, exact=True)
    except Exception as exc:  # external read boundary — wrap with context
        raise MigrationError(
            f"failed verifying destination collection {collection!r}: {exc}"
        ) from exc
    return int(getattr(result, "count", result))


def run_boot_migration() -> int:
    """One-shot boot migration.  Returns a process exit code: 0 for migrated,
    skipped, or verified-empty; 1 when the server never came up or a migration
    failed.  Every "skip" exits 0.

    Decision ladder (issue #803), each rung failing closed toward "leave the
    embedded store in place":

      1. memory disabled       → exit 0, no sentinel (re-check if re-enabled)
      2. not in server mode    → exit 0, no sentinel (embedded store is live)
      3. sentinel already present → exit 0 (single source of truth)
      4. server /readyz poll   → exit 1, no sentinel if it never comes up
      5. empty source          → sentinel reason:"empty-source", exit 0
      6. migrate + verify count→ sentinel reason:"migrated", exit 0
      7. any MigrationError    → exit 1, no sentinel
    """
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    # 1. Memory disabled → nothing to migrate; no sentinel, so a later enable
    #    re-evaluates from scratch.
    if os.environ.get("MEM0_OSS_DISABLED", "").strip().lower() in _TRUE_VALUES:
        logger.info("mem0_oss.migrate: memory disabled — skipping boot migration")
        return 0

    # 2. Not in server mode → the embedded store is still the live store.
    server_url = _boot_server_url()
    if not server_url:
        logger.info(
            "mem0_oss.migrate: no Qdrant server target set — embedded store "
            "mode, skipping boot migration"
        )
        return 0

    # 3. Already migrated → the sentinel is the single source of truth.
    sentinel = _sentinel_path()
    if sentinel.exists():
        logger.info("mem0_oss.migrate: already migrated (%s) — skipping", sentinel)
        return 0

    api_key = os.environ.get("MEM0_OSS_QDRANT_API_KEY", "").strip()

    # 4. Wait for the server — fail loud (exit 1, no sentinel) if it never comes
    #    up, so the migration retries on the next boot rather than losing data.
    if not _wait_for_readyz(server_url, api_key):
        logger.error(
            "mem0_oss.migrate: Qdrant server at %s never became ready after %d "
            "attempts — leaving the embedded store in place, will retry next boot",
            server_url,
            _READYZ_ATTEMPTS,
        )
        return 1

    collection = os.environ.get("MEM0_OSS_COLLECTION", DEFAULT_COLLECTION)
    expected_dims = int(os.environ.get("MEM0_OSS_EMBEDDER_DIMS", DEFAULT_DIMS))

    # 5a. No embedded store on disk at all → verified empty; record the sentinel
    #     so we never re-check, and exit success.
    source_path = _default_source_path()
    if not Path(source_path).exists():
        logger.info(
            "mem0_oss.migrate: no embedded store at %s — nothing to migrate",
            source_path,
        )
        _write_sentinel("empty-source", source_count=0, migrated=0)
        return 0

    source, dest = _open_boot_clients(source_path, server_url, api_key)
    try:
        # 5b. Store present but no source collection → also verified empty.
        if _vector_size(source, collection) is None:
            logger.info(
                "mem0_oss.migrate: embedded store has no %r collection — "
                "nothing to migrate",
                collection,
            )
            _write_sentinel("empty-source", source_count=0, migrated=0)
            return 0

        # 6. Migrate, then read the destination count back to confirm it landed.
        try:
            summary = migrate_store(
                source,
                dest,
                collection=collection,
                expected_dims=expected_dims,
                models=_load_qdrant_models(),
            )
            landed = _dest_count(dest, collection)
        except MigrationError as exc:  # 7. loud, no sentinel — retry next boot
            logger.error("mem0_oss.migrate: boot migration FAILED — %s", exc)
            return 1

        if landed < summary.source_count:
            logger.error(
                "mem0_oss.migrate: post-migration verify FAILED — destination "
                "collection %r holds %d point(s) but the source had %d; refusing "
                "to record the migration as complete (will retry next boot)",
                collection,
                landed,
                summary.source_count,
            )
            return 1

        _write_sentinel(
            "migrated",
            source_count=summary.source_count,
            migrated=summary.migrated,
        )
        logger.info(
            "mem0_oss.migrate: boot migration OK — %s (embedded store kept for "
            "rollback)",
            summary,
        )
        return 0
    finally:
        # Release the embedded file lock promptly so the plugin can reopen it.
        _safe_close(dest)
        _safe_close(source)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main(argv: Optional[List[str]] = None) -> int:
    """CLI job boundary.  Exit 0 on success, 1 on a migration failure, 2 on a
    usage error (argparse convention)."""
    parser = argparse.ArgumentParser(
        prog="python -m plugins.memory.mem0_oss.migrate_store",
        description=(
            "Copy Fox memories from the embedded Qdrant store to the "
            "in-container Qdrant server (point-copy, never a re-embed)."
        ),
    )
    parser.add_argument(
        "--source-path", default=None, help="embedded Qdrant path (local mode)"
    )
    parser.add_argument(
        "--server-url", default=None, help="destination server URL (HTTP)"
    )
    parser.add_argument("--collection", default=None, help="collection name")
    parser.add_argument(
        "--dims", type=int, default=None, help="expected source dimension"
    )
    parser.add_argument(
        "--boot",
        action="store_true",
        help=(
            "one-shot boot migration: sentinel-guarded, self-contained "
            "readiness poll, resolves everything from the env; safe to run on "
            "every container start (used by [program:mem0-migrate])"
        ),
    )
    args = parser.parse_args(argv)

    # Boot mode is env-driven and idempotent; it ignores the explicit
    # source/server/collection/dims flags (those are for manual invocations).
    if args.boot:
        return run_boot_migration()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        summary = run_migration(
            source_path=args.source_path,
            server_url=args.server_url,
            collection=args.collection,
            expected_dims=args.dims,
        )
    except MigrationError as exc:
        print(f"memory migration: ERROR — {exc}", file=sys.stderr)
        return 1
    print(f"memory migration: OK — {summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
