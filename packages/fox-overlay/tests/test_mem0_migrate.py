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
import types
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
run_migration = migrate_store_mod.run_migration


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
    def collection_exists(self, collection: str) -> bool:
        return collection in self._collections

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


def test_boot_present_but_unreadable_source_fails_loud_no_sentinel(
    boot_env, monkeypatch
):
    """A source collection that EXISTS but whose body cannot be read (corrupt /
    version-skewed / transient error) must NOT be misread as empty: fail loud,
    write no sentinel, so the next boot retries instead of stranding the user's
    memories behind a false "empty-source" completion (issue #803)."""

    class UnreadableSource(FakeQdrant):
        def get_collection(self, collection: str):
            # collection_exists still reports it PRESENT (seeded below); only the
            # read of its body fails.
            raise RuntimeError("qdrant storage corrupt: cannot read collection")

    source = UnreadableSource()
    source.seed("hermes", 768, _make_records(3))  # present in the registry
    dest = FakeQdrant()
    _install_clients(monkeypatch, source, dest)

    assert run_boot_migration() == 1
    assert not _sentinel_file(boot_env).exists()
    assert "hermes" not in dest._collections  # nothing written on a loud abort


def test_boot_verify_undershoot_fails_loud_no_sentinel(boot_env, monkeypatch):
    """If fewer points land than the source held (a silent upsert drop or an
    under-reported count), the post-migration read-back guard must fail loud
    with no sentinel — the migration retries next boot (issue #803)."""

    class DroppingDest(FakeQdrant):
        def upsert(self, collection_name: str, points: List[Any]):
            pass  # silently drop every point — dest count stays under source

    source = FakeQdrant()
    source.seed("hermes", 768, _make_records(5))
    dest = DroppingDest()
    _install_clients(monkeypatch, source, dest)

    assert run_boot_migration() == 1
    assert not _sentinel_file(boot_env).exists()
    assert dest.point_count("hermes") == 0  # collection created, points dropped


# ── _wait_for_readyz: readiness contract, offline + deterministic (issue #803) ─
#
# Inject a fake urllib.urlopen and neutralize time.sleep so these exercise the
# poll's decision logic with no real sockets and no wall-clock waits.


def test_wait_for_readyz_success_returns_true(monkeypatch):
    import urllib.request

    calls = {"n": 0}

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=None):
        calls["n"] += 1
        return _Resp()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(migrate_store_mod.time, "sleep", lambda _s: None)

    assert migrate_store_mod._wait_for_readyz("http://127.0.0.1:6333") is True
    assert calls["n"] == 1  # returns on first success — no needless polling


def test_wait_for_readyz_http_error_counts_as_ready(monkeypatch):
    import urllib.error
    import urllib.request

    def fake_urlopen(req, timeout=None):
        raise urllib.error.HTTPError(
            url="http://127.0.0.1:6333/readyz",
            code=500,
            msg="Internal Server Error",
            hdrs=None,
            fp=None,
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(migrate_store_mod.time, "sleep", lambda _s: None)

    # Any HTTP status means the server is live (readiness-agnostic).
    assert migrate_store_mod._wait_for_readyz("http://127.0.0.1:6333") is True


def test_wait_for_readyz_unreachable_returns_false_and_is_bounded(monkeypatch):
    import socket
    import urllib.error
    import urllib.request

    calls = {"n": 0}

    def fake_urlopen(req, timeout=None):
        calls["n"] += 1
        # Alternate the two "not ready yet" transport failures across attempts.
        if calls["n"] % 2:
            raise urllib.error.URLError("connection refused")
        raise socket.timeout("timed out")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(migrate_store_mod.time, "sleep", lambda _s: None)
    # Cap attempts low so the bound is obvious and the test stays fast.
    monkeypatch.setattr(migrate_store_mod, "_READYZ_ATTEMPTS", 4)

    assert migrate_store_mod._wait_for_readyz("http://127.0.0.1:6333") is False
    assert calls["n"] == 4  # bounded: exactly _READYZ_ATTEMPTS tries, no more


# ── _boot_server_url: env → destination URL resolution (issue #803) ───────────


def _clear_server_env(monkeypatch):
    for name in (
        "MEM0_OSS_QDRANT_URL",
        "MEM0_OSS_QDRANT_HOST",
        "MEM0_OSS_QDRANT_PORT",
        "MEM0_OSS_QDRANT_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)


def test_boot_server_url_url_wins_over_host(monkeypatch):
    _clear_server_env(monkeypatch)
    monkeypatch.setenv("MEM0_OSS_QDRANT_URL", "http://example:9999")
    monkeypatch.setenv("MEM0_OSS_QDRANT_HOST", "ignored")  # URL takes priority

    assert migrate_store_mod._boot_server_url() == "http://example:9999"


def test_boot_server_url_composes_host_and_port_http(monkeypatch):
    _clear_server_env(monkeypatch)
    monkeypatch.setenv("MEM0_OSS_QDRANT_HOST", "qdrant.internal")
    monkeypatch.setenv("MEM0_OSS_QDRANT_PORT", "6400")

    # No API key → plain http, explicit port composed in.
    assert migrate_store_mod._boot_server_url() == "http://qdrant.internal:6400"


def test_boot_server_url_default_port_and_https_with_api_key(monkeypatch):
    _clear_server_env(monkeypatch)
    monkeypatch.setenv("MEM0_OSS_QDRANT_HOST", "secure.host")
    monkeypatch.setenv("MEM0_OSS_QDRANT_API_KEY", "test-key")

    # No port → default 6333; api key present → https.
    assert migrate_store_mod._boot_server_url() == "https://secure.host:6333"


def test_boot_server_url_empty_when_nothing_set(monkeypatch):
    _clear_server_env(monkeypatch)

    # Neither URL nor HOST → embedded mode, nothing to migrate to.
    assert migrate_store_mod._boot_server_url() == ""


def test_boot_server_url_ignores_mem0_oss_json(monkeypatch, tmp_path):
    """#883 regression guard: the boot migration resolves the endpoint from the
    ENV only.  A ``qdrant_url`` in $HERMES_HOME/mem0_oss.json must NOT steer it
    — the file is never read here, so with no env set the URL stays empty."""
    _clear_server_env(monkeypatch)
    hermes_home = tmp_path / "hermes"
    hermes_home.mkdir()
    (hermes_home / "mem0_oss.json").write_text(
        json.dumps({"qdrant_url": "http://from-file:6333"}), encoding="utf-8"
    )
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))

    assert migrate_store_mod._boot_server_url() == ""


# ── run_migration: destination server resolution (issue #872) ─────────────────
#
# The manual recovery CLI (``python -m plugins.memory.mem0_oss.migrate_store``,
# no --boot, no --server-url) must target the SAME Qdrant the plugin talks to.
# run_migration resolves the destination through the full precedence chain —
# explicit arg → MEM0_OSS_QDRANT_URL → bare MEM0_OSS_QDRANT_HOST(+_PORT) →
# DEFAULT_SERVER_URL — reusing _boot_server_url so a bare-host config is honored
# instead of always falling through to 127.0.0.1:6333.  These drive the real
# run_migration with a recording fake QdrantClient injected as the qdrant_client
# module (no network, no dependency), asserting the URL the dest client is
# constructed with.


class _RecordingClient(FakeQdrant):
    """A stateful FakeQdrant that also records its construction kwargs, standing
    in for ``qdrant_client.QdrantClient``.  The path-based source seeds itself so
    the migration proceeds far enough to construct the url-based dest client."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__()
        self.init_kwargs = kwargs
        if "path" in kwargs:  # embedded source — give it something to migrate
            self.seed("hermes", 768, _make_records(2))

    def close(self) -> None:  # run_migration closes both clients in a finally
        pass


@pytest.fixture
def migrate_env(monkeypatch, tmp_path):
    """Clean env for run_migration plus a recording qdrant_client fake.  Returns
    the list every constructed client is appended to (source first, url-based
    dest second)."""
    for name in (
        "MEM0_OSS_QDRANT_URL",
        "MEM0_OSS_QDRANT_HOST",
        "MEM0_OSS_QDRANT_PORT",
        "MEM0_OSS_QDRANT_API_KEY",
        "MEM0_OSS_COLLECTION",
        "MEM0_OSS_EMBEDDER_DIMS",
    ):
        monkeypatch.delenv(name, raising=False)

    # A real dir so run_migration's source-existence check passes.
    store_dir = tmp_path / "store"
    store_dir.mkdir()
    monkeypatch.setenv("MEM0_OSS_VECTOR_STORE_PATH", str(store_dir))

    clients: List[_RecordingClient] = []

    class _Factory(_RecordingClient):
        def __init__(self, **kwargs: Any) -> None:
            super().__init__(**kwargs)
            clients.append(self)

    fake_module = types.ModuleType("qdrant_client")
    fake_module.QdrantClient = _Factory
    fake_module.models = FakeModels
    monkeypatch.setitem(sys.modules, "qdrant_client", fake_module)
    return clients


def _dest_client(clients: List[_RecordingClient]) -> _RecordingClient:
    """The url-based destination client (the source is the path-based one)."""
    dests = [c for c in clients if "url" in c.init_kwargs]
    assert len(dests) == 1
    return dests[0]


def test_run_migration_bare_host_targets_configured_host(migrate_env, monkeypatch):
    # Primary #872 repro: bare HOST(+PORT), no URL → dest must target the
    # configured host, NOT the 127.0.0.1:6333 default.  FAILS pre-fix.
    monkeypatch.setenv("MEM0_OSS_QDRANT_HOST", "qdrant.internal")
    monkeypatch.setenv("MEM0_OSS_QDRANT_PORT", "6400")

    run_migration()

    dest = _dest_client(migrate_env)
    assert dest.init_kwargs["url"] == "http://qdrant.internal:6400"
    assert "127.0.0.1" not in dest.init_kwargs["url"]


def test_run_migration_explicit_arg_wins_over_env(migrate_env, monkeypatch):
    # An explicit server_url arg beats every env source.  PASSES pre-fix
    # (guards the arg path against regression).
    monkeypatch.setenv("MEM0_OSS_QDRANT_HOST", "qdrant.internal")
    monkeypatch.setenv("MEM0_OSS_QDRANT_URL", "http://env-url:6333")

    run_migration(server_url="http://explicit:6333")

    dest = _dest_client(migrate_env)
    assert dest.init_kwargs["url"] == "http://explicit:6333"


def test_run_migration_unset_falls_back_to_default(migrate_env):
    # Neither URL nor HOST set → the historical 127.0.0.1:6333 default.
    # PASSES pre-fix (guards the no-config behavior against regression).
    run_migration()

    dest = _dest_client(migrate_env)
    assert dest.init_kwargs["url"] == migrate_store_mod.DEFAULT_SERVER_URL


def test_run_migration_authed_bare_host_uses_https_and_key(migrate_env, monkeypatch):
    # Bare HOST + api key → https scheme (mirroring the op-path client) and the
    # key carried through to the dest client.  FAILS pre-fix (host ignored →
    # http://127.0.0.1:6333).
    monkeypatch.setenv("MEM0_OSS_QDRANT_HOST", "secure.host")
    monkeypatch.setenv("MEM0_OSS_QDRANT_API_KEY", "test-key")

    run_migration()

    dest = _dest_client(migrate_env)
    assert dest.init_kwargs["url"] == "https://secure.host:6333"
    assert dest.init_kwargs["api_key"] == "test-key"
