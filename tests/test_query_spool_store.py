# -*- coding: utf-8 -*-
"""Unit tests for parquet query spool store."""

from __future__ import annotations

import fnmatch
import json
import os
import time

import pandas as pd

from mes_dashboard.core.redis_client import get_key
from mes_dashboard.core import query_spool_store as spool


class FakeRedis:
    def __init__(self) -> None:
        self._data: dict[str, str] = {}
        self._expires: dict[str, int] = {}

    def _purge_if_expired(self, key: str) -> None:
        exp = self._expires.get(key)
        if exp is not None and exp <= int(time.time()):
            self._data.pop(key, None)
            self._expires.pop(key, None)

    def setex(self, key: str, ttl: int, value: str) -> bool:
        self._data[key] = value
        self._expires[key] = int(time.time()) + int(ttl)
        return True

    def get(self, key: str):
        self._purge_if_expired(key)
        return self._data.get(key)

    def delete(self, *keys) -> int:
        deleted = 0
        for key in keys:
            if key in self._data:
                deleted += 1
            self._data.pop(key, None)
            self._expires.pop(key, None)
        return deleted

    def scan_iter(self, match: str | None = None, count: int = 100):
        for key in list(self._data.keys()):
            self._purge_if_expired(key)
            if key not in self._data:
                continue
            if match and not fnmatch.fnmatch(key, match):
                continue
            yield key


def _build_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "CONTAINERID": ["C1", "C2"],
            "LOSSREASONNAME": ["001_A", "002_B"],
            "REJECT_TOTAL_QTY": [10, 20],
        }
    )


def test_spool_store_and_load_roundtrip(monkeypatch, tmp_path):
    fake = FakeRedis()
    monkeypatch.setattr(spool, "QUERY_SPOOL_ENABLED", True)
    monkeypatch.setattr(spool, "QUERY_SPOOL_DIR", tmp_path / "query_spool")
    monkeypatch.setattr(spool, "get_redis_client", lambda: fake)

    ok = spool.store_spooled_df("reject_dataset", "qid-roundtrip-1", _build_df(), ttl_seconds=1200)
    assert ok is True

    metadata = spool.get_spool_metadata("reject_dataset", "qid-roundtrip-1")
    assert metadata is not None
    assert metadata.get("row_count") == 2

    loaded = spool.load_spooled_df("reject_dataset", "qid-roundtrip-1")
    assert loaded is not None
    pd.testing.assert_frame_equal(
        loaded.sort_values("CONTAINERID").reset_index(drop=True),
        _build_df().sort_values("CONTAINERID").reset_index(drop=True),
    )


def test_spool_load_returns_none_when_metadata_hash_mismatch(monkeypatch, tmp_path):
    fake = FakeRedis()
    monkeypatch.setattr(spool, "QUERY_SPOOL_ENABLED", True)
    monkeypatch.setattr(spool, "QUERY_SPOOL_DIR", tmp_path / "query_spool")
    monkeypatch.setattr(spool, "get_redis_client", lambda: fake)

    assert spool.store_spooled_df("reject_dataset", "qid-hash-1", _build_df(), ttl_seconds=1200)
    key = get_key(spool._meta_key("reject_dataset", "qid-hash-1"))
    metadata = json.loads(fake.get(key))
    metadata["columns_hash"] = "deadbeefdeadbeef"
    fake.setex(key, 1200, json.dumps(metadata, ensure_ascii=False))

    loaded = spool.load_spooled_df("reject_dataset", "qid-hash-1")
    assert loaded is None
    assert fake.get(key) is None


def test_spool_load_returns_none_when_file_missing(monkeypatch, tmp_path):
    fake = FakeRedis()
    monkeypatch.setattr(spool, "QUERY_SPOOL_ENABLED", True)
    monkeypatch.setattr(spool, "QUERY_SPOOL_DIR", tmp_path / "query_spool")
    monkeypatch.setattr(spool, "get_redis_client", lambda: fake)

    assert spool.store_spooled_df("reject_dataset", "qid-missing-file-1", _build_df(), ttl_seconds=1200)
    metadata = spool.get_spool_metadata("reject_dataset", "qid-missing-file-1")
    assert metadata is not None
    path = spool._path_from_relative(metadata["relative_path"])
    assert path is not None and path.exists()
    path.unlink()

    loaded = spool.load_spooled_df("reject_dataset", "qid-missing-file-1")
    assert loaded is None
    assert spool.get_spool_metadata("reject_dataset", "qid-missing-file-1") is None


def test_register_spool_file_merges_extra_metadata(monkeypatch, tmp_path):
    """extra_metadata is merged into the Redis metadata dict and readable
    back via get_spool_metadata()."""
    fake = FakeRedis()
    monkeypatch.setattr(spool, "QUERY_SPOOL_ENABLED", True)
    monkeypatch.setattr(spool, "QUERY_SPOOL_DIR", tmp_path / "query_spool")
    monkeypatch.setattr(spool, "get_redis_client", lambda: fake)

    src_path = tmp_path / "src-extra-1.parquet"
    _build_df().to_parquet(src_path, engine="pyarrow", index=False)

    ok = spool.register_spool_file(
        "reject_dataset", "qid-extra-1", src_path, 2, ttl_seconds=1200,
        extra_metadata={"latest_data_ts": "2026-07-20 07:29:59"},
    )
    assert ok is True

    metadata = spool.get_spool_metadata("reject_dataset", "qid-extra-1")
    assert metadata is not None
    assert metadata.get("latest_data_ts") == "2026-07-20 07:29:59"
    # Core fields are untouched
    assert metadata.get("row_count") == 2


def test_register_spool_file_extra_metadata_cannot_clobber_reserved_keys(monkeypatch, tmp_path):
    """A caller-supplied extra_metadata key matching a reserved core field
    must never override the value register_spool_file itself computed."""
    fake = FakeRedis()
    monkeypatch.setattr(spool, "QUERY_SPOOL_ENABLED", True)
    monkeypatch.setattr(spool, "QUERY_SPOOL_DIR", tmp_path / "query_spool")
    monkeypatch.setattr(spool, "get_redis_client", lambda: fake)

    src_path = tmp_path / "src-extra-2.parquet"
    _build_df().to_parquet(src_path, engine="pyarrow", index=False)

    ok = spool.register_spool_file(
        "reject_dataset", "qid-extra-2", src_path, 2, ttl_seconds=1200,
        extra_metadata={"row_count": 99999, "namespace": "hijacked", "latest_data_ts": "safe"},
    )
    assert ok is True

    metadata = spool.get_spool_metadata("reject_dataset", "qid-extra-2")
    assert metadata is not None
    assert metadata.get("row_count") == 2
    assert metadata.get("namespace") == "reject_dataset"
    assert metadata.get("latest_data_ts") == "safe"


def test_register_spool_file_without_extra_metadata_unchanged(monkeypatch, tmp_path):
    """Omitting extra_metadata (the default) leaves behavior identical to
    before -- no extra keys appear in the stored metadata."""
    fake = FakeRedis()
    monkeypatch.setattr(spool, "QUERY_SPOOL_ENABLED", True)
    monkeypatch.setattr(spool, "QUERY_SPOOL_DIR", tmp_path / "query_spool")
    monkeypatch.setattr(spool, "get_redis_client", lambda: fake)

    src_path = tmp_path / "src-extra-3.parquet"
    _build_df().to_parquet(src_path, engine="pyarrow", index=False)

    ok = spool.register_spool_file("reject_dataset", "qid-extra-3", src_path, 2, ttl_seconds=1200)
    assert ok is True

    metadata = spool.get_spool_metadata("reject_dataset", "qid-extra-3")
    assert metadata is not None
    expected_keys = {
        "schema_version", "namespace", "query_id", "relative_path",
        "row_count", "column_count", "columns_hash", "created_at",
        "expires_at", "file_size_bytes",
    }
    assert set(metadata.keys()) == expected_keys


def test_register_spool_file_cas_skips_stale_write(monkeypatch, tmp_path):
    """A CAS write whose cas_value is SMALLER than the already-registered
    cas_field value (i.e. this write started its query BEFORE the result
    already stored) must be skipped entirely -- neither the parquet file nor
    the Redis metadata may change."""
    fake = FakeRedis()
    monkeypatch.setattr(spool, "QUERY_SPOOL_ENABLED", True)
    monkeypatch.setattr(spool, "QUERY_SPOOL_DIR", tmp_path / "query_spool")
    monkeypatch.setattr(spool, "get_redis_client", lambda: fake)

    winner_src = tmp_path / "src-cas-winner.parquet"
    _build_df().to_parquet(winner_src, engine="pyarrow", index=False)
    ok = spool.register_spool_file(
        "reject_dataset", "qid-cas-1", winner_src, 2, ttl_seconds=1200,
        extra_metadata={"query_started_at": 200.0},
        cas_field="query_started_at", cas_value=200.0,
    )
    assert ok is True
    metadata_before = spool.get_spool_metadata("reject_dataset", "qid-cas-1")
    assert metadata_before is not None
    assert metadata_before.get("query_started_at") == 200.0
    winner_relative_path = metadata_before["relative_path"]

    stale_src = tmp_path / "src-cas-stale.parquet"
    _build_df().to_parquet(stale_src, engine="pyarrow", index=False)
    stale_ok = spool.register_spool_file(
        "reject_dataset", "qid-cas-1", stale_src, 2, ttl_seconds=1200,
        extra_metadata={"query_started_at": 100.0},
        cas_field="query_started_at", cas_value=100.0,
    )
    assert stale_ok is False

    metadata_after = spool.get_spool_metadata("reject_dataset", "qid-cas-1")
    assert metadata_after == metadata_before
    assert metadata_after["relative_path"] == winner_relative_path
    # The stale write's own source file must never have been moved into place.
    assert stale_src.exists()


def test_register_spool_file_cas_writes_when_newer(monkeypatch, tmp_path):
    """A CAS write whose cas_value is LARGER than the existing cas_field
    value must proceed normally (the later-started query wins)."""
    fake = FakeRedis()
    monkeypatch.setattr(spool, "QUERY_SPOOL_ENABLED", True)
    monkeypatch.setattr(spool, "QUERY_SPOOL_DIR", tmp_path / "query_spool")
    monkeypatch.setattr(spool, "get_redis_client", lambda: fake)

    first_src = tmp_path / "src-cas-first.parquet"
    _build_df().to_parquet(first_src, engine="pyarrow", index=False)
    assert spool.register_spool_file(
        "reject_dataset", "qid-cas-2", first_src, 2, ttl_seconds=1200,
        extra_metadata={"query_started_at": 100.0},
        cas_field="query_started_at", cas_value=100.0,
    ) is True

    newer_src = tmp_path / "src-cas-newer.parquet"
    _build_df().to_parquet(newer_src, engine="pyarrow", index=False)
    assert spool.register_spool_file(
        "reject_dataset", "qid-cas-2", newer_src, 2, ttl_seconds=1200,
        extra_metadata={"query_started_at": 200.0},
        cas_field="query_started_at", cas_value=200.0,
    ) is True

    metadata = spool.get_spool_metadata("reject_dataset", "qid-cas-2")
    assert metadata is not None
    assert metadata.get("query_started_at") == 200.0


def test_register_spool_file_cas_writes_when_existing_metadata_missing_field(monkeypatch, tmp_path):
    """When the currently-registered metadata has no value under cas_field
    (e.g. an older spool entry written before this feature existed, or one
    registered without a cas_value), the write proceeds unconditionally --
    there is nothing to compare against."""
    fake = FakeRedis()
    monkeypatch.setattr(spool, "QUERY_SPOOL_ENABLED", True)
    monkeypatch.setattr(spool, "QUERY_SPOOL_DIR", tmp_path / "query_spool")
    monkeypatch.setattr(spool, "get_redis_client", lambda: fake)

    legacy_src = tmp_path / "src-cas-legacy.parquet"
    _build_df().to_parquet(legacy_src, engine="pyarrow", index=False)
    assert spool.register_spool_file(
        "reject_dataset", "qid-cas-3", legacy_src, 2, ttl_seconds=1200,
    ) is True

    cas_src = tmp_path / "src-cas-3-new.parquet"
    _build_df().to_parquet(cas_src, engine="pyarrow", index=False)
    ok = spool.register_spool_file(
        "reject_dataset", "qid-cas-3", cas_src, 2, ttl_seconds=1200,
        extra_metadata={"query_started_at": 50.0},
        cas_field="query_started_at", cas_value=50.0,
    )
    assert ok is True

    metadata = spool.get_spool_metadata("reject_dataset", "qid-cas-3")
    assert metadata is not None
    assert metadata.get("query_started_at") == 50.0


def test_register_spool_file_without_cas_args_unchanged(monkeypatch, tmp_path):
    """Omitting cas_field/cas_value (the default) is a plain unconditional
    overwrite, identical to pre-CAS behavior -- an "older" write must still
    be able to clobber a "newer" one when CAS is not opted into."""
    fake = FakeRedis()
    monkeypatch.setattr(spool, "QUERY_SPOOL_ENABLED", True)
    monkeypatch.setattr(spool, "QUERY_SPOOL_DIR", tmp_path / "query_spool")
    monkeypatch.setattr(spool, "get_redis_client", lambda: fake)

    first_src = tmp_path / "src-nocas-first.parquet"
    _build_df().to_parquet(first_src, engine="pyarrow", index=False)
    assert spool.register_spool_file(
        "reject_dataset", "qid-nocas-1", first_src, 2, ttl_seconds=1200,
        extra_metadata={"query_started_at": 200.0},
    ) is True

    second_src = tmp_path / "src-nocas-second.parquet"
    _build_df().to_parquet(second_src, engine="pyarrow", index=False)
    ok = spool.register_spool_file(
        "reject_dataset", "qid-nocas-1", second_src, 2, ttl_seconds=1200,
        extra_metadata={"query_started_at": 100.0},
    )
    assert ok is True

    metadata = spool.get_spool_metadata("reject_dataset", "qid-nocas-1")
    assert metadata is not None
    # The "older" 100.0 write clobbered the "newer" 200.0 write -- no CAS
    # protection when cas_field/cas_value are omitted.
    assert metadata.get("query_started_at") == 100.0


def test_cleanup_expired_and_orphan_files(monkeypatch, tmp_path):
    fake = FakeRedis()
    root = tmp_path / "query_spool"
    monkeypatch.setattr(spool, "QUERY_SPOOL_ENABLED", True)
    monkeypatch.setattr(spool, "QUERY_SPOOL_DIR", root)
    monkeypatch.setattr(spool, "QUERY_SPOOL_ORPHAN_GRACE_SECONDS", 1)
    monkeypatch.setattr(spool, "get_redis_client", lambda: fake)

    now = int(time.time())

    assert spool.store_spooled_df("reject_dataset", "qid-valid-1", _build_df(), ttl_seconds=1200)
    assert spool.store_spooled_df("reject_dataset", "qid-expired-1", _build_df(), ttl_seconds=1200)

    expired_key = get_key(spool._meta_key("reject_dataset", "qid-expired-1"))
    expired_meta = json.loads(fake.get(expired_key))
    expired_path = spool._path_from_relative(expired_meta["relative_path"])
    assert expired_path is not None and expired_path.exists()
    expired_meta["expires_at"] = now - 10
    fake.setex(expired_key, 1200, json.dumps(expired_meta, ensure_ascii=False))

    orphan_dir = root / "reject_dataset"
    orphan_dir.mkdir(parents=True, exist_ok=True)
    orphan_path = orphan_dir / "orphan.parquet"
    _build_df().to_parquet(orphan_path, engine="pyarrow", index=False)
    old_time = now - 120
    os.utime(orphan_path, (old_time, old_time))

    stats = spool.cleanup_expired_spool(namespace="reject_dataset")
    assert stats["meta_deleted"] >= 1
    assert stats["expired_files_deleted"] >= 1
    assert stats["orphan_files_deleted"] >= 1
    assert not orphan_path.exists()
    assert not expired_path.exists()
    assert spool.get_spool_metadata("reject_dataset", "qid-valid-1") is not None


def test_read_spool_records_closes_connection_on_read_error(monkeypatch):
    """Regression: a read_parquet/fetchall failure must not leak the DuckDB
    connection. Previously conn.close() ran only on the success path, so an
    error left the connection open — a slow drain across queries."""
    import mes_dashboard.core.duckdb_runtime as duckdb_runtime

    closed = {"value": False}

    class _FailingConn:
        def read_parquet(self, path):
            raise RuntimeError("parquet corrupt")

        def close(self):
            closed["value"] = True

    monkeypatch.setattr(
        spool, "get_spool_file_path", lambda ns, qid: "/tmp/does-not-matter.parquet"
    )
    monkeypatch.setattr(
        duckdb_runtime, "create_heavy_query_connection", lambda: _FailingConn()
    )

    result = spool.read_spool_records("reject_dataset", "qid-read-error")

    assert result is None
    assert closed["value"] is True, (
        "DuckDB connection must be closed even when read_parquet fails"
    )


def test_read_spool_records_closes_connection_on_success(monkeypatch):
    import mes_dashboard.core.duckdb_runtime as duckdb_runtime

    closed = {"value": False}

    class _Rel:
        columns = ["CONTAINERID"]
        types = ["VARCHAR"]

        def fetchall(self):
            return [("C1",)]

    class _OkConn:
        def read_parquet(self, path):
            return _Rel()

        def close(self):
            closed["value"] = True

    monkeypatch.setattr(
        spool, "get_spool_file_path", lambda ns, qid: "/tmp/x.parquet"
    )
    monkeypatch.setattr(
        duckdb_runtime, "create_heavy_query_connection", lambda: _OkConn()
    )

    result = spool.read_spool_records("reject_dataset", "qid-ok")

    assert result == [{"CONTAINERID": "C1"}]
    assert closed["value"] is True
