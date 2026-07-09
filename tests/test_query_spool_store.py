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
