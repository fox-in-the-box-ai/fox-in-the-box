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
it explicitly:

    python3 -m agent_memory_plugins.mem0_oss.migrate_store

``qdrant_client`` is imported lazily (only ``run_migration`` / the CLI need
it), so the pure ``migrate_store`` core can be exercised against hand-rolled
fakes without the dependency installed.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional

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
            url=server_url, api_key=api_key, timeout=int(_SERVER_TIMEOUT_S)
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
# CLI entry point
# ---------------------------------------------------------------------------


def main(argv: Optional[List[str]] = None) -> int:
    """CLI job boundary.  Exit 0 on success, 1 on a migration failure, 2 on a
    usage error (argparse convention)."""
    parser = argparse.ArgumentParser(
        prog="python -m agent_memory_plugins.mem0_oss.migrate_store",
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
    args = parser.parse_args(argv)

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
