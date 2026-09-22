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
import json
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
run_boot_migration = migrate_store_mod.run_boot_migration


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

    def count(self, collection_name: str, exact: bool = True):
        # Mirrors qdrant-client's CountResult (an object with a .count attr).
        n = len(self._collections[collection_name].points)
        return type("CountResult", (), {"count": n})()


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


# ── Boot wrapper: run_boot_migration() decision ladder (issue #803) ──────────
#
# These drive the sentinel-guarded boot job end to end with hand-rolled fakes —
# no network, no qdrant_client — by monkeypatching the module's three seams:
# the /readyz poll (_wait_for_readyz), the client factory (_open_boot_clients),
# and the models namespace (_load_qdrant_models).


@pytest.fixture
def boot_env(monkeypatch, tmp_path):
    """A clean env for the boot wrapper: HERMES_HOME under tmp (sentinel lives
    there), server mode on, and an existing embedded-store dir by default.  All
    other MEM0_OSS_* knobs are cleared so leakage from the ambient shell can't
    steer a test."""
    for name in (
        "MEM0_OSS_DISABLED",
        "MEM0_OSS_QDRANT_URL",
        "MEM0_OSS_QDRANT_HOST",
        "MEM0_OSS_QDRANT_PORT",
        "MEM0_OSS_QDRANT_API_KEY",
        "MEM0_OSS_COLLECTION",
        "MEM0_OSS_EMBEDDER_DIMS",
    ):
        monkeypatch.delenv(name, raising=False)

    store_dir = tmp_path / "store"
    store_dir.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))
    monkeypatch.setenv("MEM0_OSS_QDRANT_URL", "http://127.0.0.1:6333")
    monkeypatch.setenv("MEM0_OSS_VECTOR_STORE_PATH", str(store_dir))
    # Default: server is ready.  Individual tests override.
    monkeypatch.setattr(migrate_store_mod, "_wait_for_readyz", lambda *a, **k: True)
    return tmp_path


def _sentinel_file(hermes_home: Path) -> Path:
    return hermes_home / "hermes" / "mem0_oss" / ".migrated-to-server"


def _install_clients(monkeypatch, source: "FakeQdrant", dest: "FakeQdrant"):
    monkeypatch.setattr(
        migrate_store_mod, "_open_boot_clients", lambda *a, **k: (source, dest)
    )
    monkeypatch.setattr(migrate_store_mod, "_load_qdrant_models", lambda: FakeModels())


def test_boot_skips_when_memory_disabled(boot_env, monkeypatch):
    monkeypatch.setenv("MEM0_OSS_DISABLED", "1")
    # If a client were opened this would raise — proving the skip is early.
    monkeypatch.setattr(
        migrate_store_mod,
        "_open_boot_clients",
        lambda *a, **k: pytest.fail("must not open clients when disabled"),
    )

    assert run_boot_migration() == 0
    assert not _sentinel_file(boot_env).exists()


def test_boot_skips_when_not_server_mode(boot_env, monkeypatch):
    monkeypatch.delenv("MEM0_OSS_QDRANT_URL", raising=False)  # no URL and no HOST
    monkeypatch.setattr(
        migrate_store_mod,
        "_open_boot_clients",
        lambda *a, **k: pytest.fail("must not open clients in embedded mode"),
    )

    assert run_boot_migration() == 0
    assert not _sentinel_file(boot_env).exists()


def test_boot_skips_when_sentinel_present(boot_env, monkeypatch):
    sentinel = _sentinel_file(boot_env)
    sentinel.parent.mkdir(parents=True)
    sentinel.write_text('{"schema": 1, "reason": "migrated"}', encoding="utf-8")
    monkeypatch.setattr(
        migrate_store_mod,
        "_open_boot_clients",
        lambda *a, **k: pytest.fail("must not re-migrate once the sentinel exists"),
    )

    assert run_boot_migration() == 0


def test_boot_never_ready_no_sentinel_nonzero(boot_env, monkeypatch):
    monkeypatch.setattr(migrate_store_mod, "_wait_for_readyz", lambda *a, **k: False)
    monkeypatch.setattr(
        migrate_store_mod,
        "_open_boot_clients",
        lambda *a, **k: pytest.fail("must not open clients when server never ready"),
    )

    assert run_boot_migration() == 1
    assert not _sentinel_file(boot_env).exists()


def test_boot_empty_source_absent_path(boot_env, monkeypatch):
    # Point the embedded store at a path that does not exist.
    monkeypatch.setenv("MEM0_OSS_VECTOR_STORE_PATH", str(boot_env / "does-not-exist"))
    monkeypatch.setattr(
        migrate_store_mod,
        "_open_boot_clients",
        lambda *a, **k: pytest.fail("must not open clients when store is absent"),
    )

    assert run_boot_migration() == 0
    payload = json.loads(_sentinel_file(boot_env).read_text())
    assert payload["reason"] == "empty-source"
    assert payload["source_count"] == 0
    assert payload["migrated"] == 0


def test_boot_empty_source_no_collection(boot_env, monkeypatch):
    source = FakeQdrant()  # store dir exists (fixture) but no "hermes" collection
    dest = FakeQdrant()
    _install_clients(monkeypatch, source, dest)

    assert run_boot_migration() == 0
    payload = json.loads(_sentinel_file(boot_env).read_text())
    assert payload["reason"] == "empty-source"
    assert "hermes" not in dest._collections  # nothing created on an empty source


def test_boot_successful_migrate_writes_sentinel(boot_env, monkeypatch):
    records = _make_records(5)
    source = FakeQdrant()
    source.seed("hermes", 768, records)
    dest = FakeQdrant()
    _install_clients(monkeypatch, source, dest)

    assert run_boot_migration() == 0

    # Points copied and verified via the dest read-back.
    assert dest.point_count("hermes") == 5
    payload = json.loads(_sentinel_file(boot_env).read_text())
    assert payload["schema"] == 1
    assert payload["reason"] == "migrated"
    assert payload["collection"] == "hermes"
    assert payload["dims"] == 768
    assert payload["source_count"] == 5
    assert payload["migrated"] == 5
    assert isinstance(payload["migrated_at"], int)


def test_boot_partial_run_no_sentinel_then_idempotent_rerun(boot_env, monkeypatch):
    records = _make_records(4)

    class FailOnceDest(FakeQdrant):
        """Fails the first upsert (a partial/crashed run) then succeeds."""

        def __init__(self) -> None:
            super().__init__()
            self.fail_next_upsert = True

        def upsert(self, collection_name: str, points: List[Any]):
            if self.fail_next_upsert:
                self.fail_next_upsert = False
                raise RuntimeError("qdrant write interrupted")
            super().upsert(collection_name, points)

    source = FakeQdrant()
    source.seed("hermes", 768, records)
    dest = FailOnceDest()
    _install_clients(monkeypatch, source, dest)

    # First boot: the write blows up mid-flight → loud failure, NO sentinel.
    assert run_boot_migration() == 1
    assert not _sentinel_file(boot_env).exists()

    # Second boot: same stable ids upsert cleanly, verify passes, sentinel drops.
    assert run_boot_migration() == 0
    assert dest.point_count("hermes") == 4  # idempotent — no duplicates
    payload = json.loads(_sentinel_file(boot_env).read_text())
    assert payload["reason"] == "migrated"
    assert payload["migrated"] == 4


def test_boot_dims_mismatch_no_sentinel(boot_env, monkeypatch):
    source = FakeQdrant()
    source.seed("hermes", 512, _make_records(2, dims=512))  # wrong dimension
    dest = FakeQdrant()
    _install_clients(monkeypatch, source, dest)

    assert run_boot_migration() == 1
    assert not _sentinel_file(boot_env).exists()
    assert "hermes" not in dest._collections  # aborted before any write
