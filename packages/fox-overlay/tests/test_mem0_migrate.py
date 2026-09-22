"""Tests for the embedded → server Qdrant memory migration (issue #780).

The migration core is a pure point-copy between two qdrant-client-shaped
objects, so these tests drive it with hand-rolled, stateful fakes (real
in-memory stores keyed by point id) — never mocks — per the repo's test
discipline.  ``qdrant_client`` is not required.

The module under test lives in ``agent_memory_plugins/mem0_oss``, whose
package ``__init__`` imports the hermes-agent runtime (not importable in the
validate-overlay context).  ``migrate_store`` is deliberately self-contained,
so it is loaded directly by file path to avoid dragging in that package init.
"""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pytest

_MODULE_NAME = "_fox_migrate_store"
_MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "agent_memory_plugins"
    / "mem0_oss"
    / "migrate_store.py"
)
_spec = importlib.util.spec_from_file_location(_MODULE_NAME, _MODULE_PATH)
assert _spec and _spec.loader
migrate_store_mod = importlib.util.module_from_spec(_spec)
# Register before exec so the module's @dataclass can resolve its own module.
sys.modules[_MODULE_NAME] = migrate_store_mod
_spec.loader.exec_module(migrate_store_mod)

migrate_store = migrate_store_mod.migrate_store
MigrationError = migrate_store_mod.MigrationError


# ── Fakes: a working in-memory stand-in for the qdrant-client surface ────────


@dataclass
class FakeRecord:
    """Mirrors a qdrant scroll Record: id + vector + payload."""

    id: Any
    vector: List[float]
    payload: Optional[Dict[str, Any]]


class FakePointStruct:
    def __init__(self, id: Any, vector: List[float], payload: Any = None):
        self.id = id
        self.vector = vector
        self.payload = payload


class FakeVectorParams:
    def __init__(self, size: int, distance: str = "Cosine"):
        self.size = size
        self.distance = distance


class FakeModels:
    """Stand-in for the ``qdrant_client.models`` namespace."""

    PointStruct = FakePointStruct
    VectorParams = FakeVectorParams

    class Distance:
        COSINE = "Cosine"


@dataclass
class _CollectionState:
    size: int
    distance: str
    # id -> (vector, payload); a dict makes upsert idempotent by construction.
    points: Dict[Any, Tuple[List[float], Optional[Dict[str, Any]]]] = field(
        default_factory=dict
    )


class FakeQdrant:
    """A stateful in-memory Qdrant fake covering the surface the migration
    touches: get_collection / scroll / create_collection / upsert."""

    def __init__(self) -> None:
        self._collections: Dict[str, _CollectionState] = {}

    # -- test helpers --------------------------------------------------------
    def seed(
        self,
        collection: str,
        size: int,
        records: List[FakeRecord],
        distance: str = "Cosine",
    ) -> None:
        state = _CollectionState(size=size, distance=distance)
        for rec in records:
            state.points[rec.id] = (rec.vector, rec.payload)
        self._collections[collection] = state

    def point_ids(self, collection: str) -> List[Any]:
        return list(self._collections[collection].points.keys())

    def point_count(self, collection: str) -> int:
        return len(self._collections[collection].points)

    def get_point(self, collection: str, pid: Any):
        return self._collections[collection].points[pid]

    # -- qdrant-client surface ----------------------------------------------
    def get_collection(self, collection: str):
        if collection not in self._collections:
            raise ValueError(f"collection {collection!r} not found")
        state = self._collections[collection]
        params = FakeVectorParams(size=state.size, distance=state.distance)
        config = type("C", (), {"params": type("P", (), {"vectors": params})()})()
        return type("Info", (), {"config": config})()

    def scroll(
        self,
        collection_name: str,
        limit: int,
        offset: Any = None,
        with_vectors: bool = False,
        with_payload: bool = False,
    ):
        state = self._collections[collection_name]
        ids = list(state.points.keys())
        start = offset or 0
        chunk_ids = ids[start : start + limit]
        records = [
            FakeRecord(
                id=pid,
                vector=list(state.points[pid][0]) if with_vectors else None,
                payload=(
                    dict(state.points[pid][1])
                    if with_payload and state.points[pid][1] is not None
                    else None
                ),
            )
            for pid in chunk_ids
        ]
        next_offset = start + limit if start + limit < len(ids) else None
        return records, next_offset

    def create_collection(self, collection_name: str, vectors_config: Any):
        self._collections[collection_name] = _CollectionState(
            size=vectors_config.size, distance=vectors_config.distance
        )

    def upsert(self, collection_name: str, points: List[Any]):
        state = self._collections[collection_name]
        for point in points:
            state.points[point.id] = (point.vector, point.payload)


def _make_records(n: int, dims: int = 768) -> List[FakeRecord]:
    return [
        FakeRecord(
            id=i,
            vector=[float(i)] * dims,
            payload={"data": f"memory-{i}", "user_id": "hermes-user"},
        )
        for i in range(n)
    ]


# ── Tests ────────────────────────────────────────────────────────────────


def test_migrates_all_points_identically():
    records = _make_records(5)
    source = FakeQdrant()
    source.seed("hermes", 768, records)
    dest = FakeQdrant()

    summary = migrate_store(source, dest, models=FakeModels(), batch_size=2)

    assert summary.source_count == 5
    assert summary.migrated == 5
    assert summary.dims == 768
    assert dest.point_count("hermes") == 5
    # Vectors and payloads copied verbatim (lossless, no re-embed).
    for rec in records:
        vector, payload = dest.get_point("hermes", rec.id)
        assert vector == rec.vector
        assert payload == rec.payload


def test_creates_destination_collection_with_matching_dims():
    source = FakeQdrant()
    source.seed("hermes", 768, _make_records(3), distance="Cosine")
    dest = FakeQdrant()  # destination collection absent

    migrate_store(source, dest, models=FakeModels())

    info = dest.get_collection("hermes")
    assert info.config.params.vectors.size == 768
    assert info.config.params.vectors.distance == "Cosine"


def test_rerun_is_idempotent_no_duplicates():
    source = FakeQdrant()
    source.seed("hermes", 768, _make_records(4))
    dest = FakeQdrant()

    first = migrate_store(source, dest, models=FakeModels())
    second = migrate_store(source, dest, models=FakeModels())

    assert first.migrated == 4
    assert second.migrated == 4  # re-copied, but...
    assert dest.point_count("hermes") == 4  # ...replaced in place, no dupes
    assert sorted(dest.point_ids("hermes")) == [0, 1, 2, 3]


def test_source_dims_mismatch_aborts_loudly():
    source = FakeQdrant()
    source.seed("hermes", 512, _make_records(2, dims=512))  # wrong dimension
    dest = FakeQdrant()

    with pytest.raises(MigrationError) as excinfo:
        migrate_store(source, dest, expected_dims=768, models=FakeModels())

    assert "512" in str(excinfo.value)
    assert "768" in str(excinfo.value)
    # Nothing written on abort.
    assert "hermes" not in dest._collections


def test_destination_dims_mismatch_aborts_loudly():
    source = FakeQdrant()
    source.seed("hermes", 768, _make_records(3))
    dest = FakeQdrant()
    dest.seed("hermes", 1024, [])  # pre-existing collection, wrong dims

    with pytest.raises(MigrationError) as excinfo:
        migrate_store(source, dest, models=FakeModels())

    assert "1024" in str(excinfo.value)
    assert "768" in str(excinfo.value)
    # Destination left untouched.
    assert dest.point_count("hermes") == 0


def test_missing_source_collection_aborts_loudly():
    source = FakeQdrant()  # no "hermes" collection at all
    dest = FakeQdrant()

    with pytest.raises(MigrationError) as excinfo:
        migrate_store(source, dest, models=FakeModels())

    assert "not found" in str(excinfo.value)


def test_read_failure_is_wrapped_fail_loud():
    class ExplodingSource(FakeQdrant):
        def scroll(self, *a, **k):
            raise RuntimeError("qdrant connection reset")

    source = ExplodingSource()
    source.seed("hermes", 768, _make_records(1))
    dest = FakeQdrant()

    with pytest.raises(MigrationError) as excinfo:
        migrate_store(source, dest, models=FakeModels())

    assert "connection reset" in str(excinfo.value)
