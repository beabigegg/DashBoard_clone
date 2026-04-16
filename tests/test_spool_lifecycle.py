# -*- coding: utf-8 -*-
"""Task 6.3 — Spool TTL boundary, orphan cleanup, concurrent read, and atomic rename.

Integration tests covering query_spool_store lifecycle:
  - write and read-back equality
  - atomic rename: concurrent reader never sees a partially-written file
  - orphan cleanup removes files with past expires_at
  - missing query_id → get_spool_file_path returns None
"""

import json
import os
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

import mes_dashboard.core.query_spool_store as spool_mod
from mes_dashboard.core.query_spool_store import (
    _move_into_place,
    _target_path,
    cleanup_expired_spool,
    get_spool_file_path,
    store_spooled_df,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_df():
    return pd.DataFrame({"col_a": [1, 2, 3], "col_b": ["x", "y", "z"]})


def _mock_redis_client_factory(store: dict):
    """Return a minimal mock Redis that stores keys in *store*."""
    client = MagicMock()

    def _setex(key, ttl, value):
        store[key] = (value, time.time() + ttl)

    def _get(key):
        entry = store.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if expires_at <= time.time():
            del store[key]
            return None
        return value

    def _delete(key):
        store.pop(key, None)

    def _scan_iter(match="*", count=200):
        import fnmatch
        for k in list(store.keys()):
            if fnmatch.fnmatch(k, match):
                yield k

    client.setex.side_effect = _setex
    client.get.side_effect = _get
    client.delete.side_effect = _delete
    client.scan_iter.side_effect = _scan_iter
    client.ping.return_value = True
    return client


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestSpoolLifecycle:
    """Task 6.3 — TTL boundary, orphan cleanup, concurrent read, and atomic rename."""

    def test_write_and_read_spool(self, tmp_path):
        """store_spooled_df then load_spooled_df round-trips DataFrame correctly."""
        from mes_dashboard.core.query_spool_store import load_spooled_df

        redis_store: dict = {}
        mock_client = _mock_redis_client_factory(redis_store)

        with (
            patch.object(spool_mod, "QUERY_SPOOL_DIR", tmp_path),
            patch("mes_dashboard.core.query_spool_store.get_redis_client", return_value=mock_client),
            patch("mes_dashboard.core.query_spool_store.QUERY_SPOOL_ENABLED", True),
        ):
            df = _make_df()
            ok = store_spooled_df("test_ns", "query-abc123456", df, ttl_seconds=300)
            assert ok is True

            result = load_spooled_df("test_ns", "query-abc123456")
            assert result is not None
            assert list(result["col_a"]) == [1, 2, 3]
            assert list(result["col_b"]) == ["x", "y", "z"]

    def test_spool_miss_returns_none(self, tmp_path):
        """get_spool_file_path returns None for a query_id that has never been stored."""
        redis_store: dict = {}
        mock_client = _mock_redis_client_factory(redis_store)

        with (
            patch.object(spool_mod, "QUERY_SPOOL_DIR", tmp_path),
            patch("mes_dashboard.core.query_spool_store.get_redis_client", return_value=mock_client),
            patch("mes_dashboard.core.query_spool_store.QUERY_SPOOL_ENABLED", True),
        ):
            result = get_spool_file_path("test_ns", "nonexistent-id-xyz")
            assert result is None

    def test_atomic_rename_reader_never_sees_partial(self, tmp_path):
        """Concurrent reader thread observes either the file does not exist yet
        or it exists fully (complete parquet) — never a partial/corrupt state."""
        ns_dir = tmp_path / "test_ns"
        ns_dir.mkdir(parents=True, exist_ok=True)

        dest = ns_dir / "atomic-testquery.parquet"
        corruption_detected = {"found": False}

        def reader():
            for _ in range(50):
                time.sleep(0.001)
                if dest.exists():
                    # Try to read; a partial file would raise on read_parquet
                    try:
                        df = pd.read_parquet(dest, engine="pyarrow")
                        # If readable, must have expected columns
                        assert "col_a" in df.columns
                    except Exception:
                        corruption_detected["found"] = True

        reader_thread = threading.Thread(target=reader)
        reader_thread.start()

        # Writer: write to temp then atomically rename
        for i in range(5):
            df = pd.DataFrame({"col_a": range(100), "col_b": range(100, 200)})
            tmp_file = tmp_path / f"atomic-testquery-tmp-{i}.parquet"
            df.to_parquet(tmp_file, engine="pyarrow", index=False)
            _move_into_place(tmp_file, dest)
            time.sleep(0.005)

        reader_thread.join(timeout=2.0)
        assert not corruption_detected["found"], "Reader saw a partially-written file"

    def test_orphan_cleanup_removes_expired_files(self, tmp_path):
        """Files with expires_at in the past are deleted by cleanup_expired_spool."""
        redis_store: dict = {}
        mock_client = _mock_redis_client_factory(redis_store)

        ns_dir = tmp_path / "test_ns"
        ns_dir.mkdir(parents=True, exist_ok=True)
        orphan_parquet = ns_dir / "stale-id12345678.parquet"
        df = _make_df()
        df.to_parquet(orphan_parquet, engine="pyarrow", index=False)

        # Insert an already-expired metadata entry
        from mes_dashboard.core.redis_client import get_key as real_get_key
        meta = {
            "schema_version": 1,
            "namespace": "test_ns",
            "query_id": "stale-id12345678",
            "relative_path": f"test_ns/stale-id12345678.parquet",
            "row_count": 3,
            "column_count": 2,
            "columns_hash": "abc",
            "created_at": int(time.time()) - 7200,
            "expires_at": int(time.time()) - 3600,  # already expired
            "file_size_bytes": orphan_parquet.stat().st_size,
        }
        meta_key = real_get_key("test_ns:spool_meta:stale-id12345678")
        redis_store[meta_key] = (json.dumps(meta), time.time() + 60)

        with (
            patch.object(spool_mod, "QUERY_SPOOL_DIR", tmp_path),
            patch("mes_dashboard.core.query_spool_store.get_redis_client", return_value=mock_client),
            patch("mes_dashboard.core.query_spool_store.QUERY_SPOOL_ENABLED", True),
        ):
            stats = cleanup_expired_spool(namespace="test_ns")

        assert not orphan_parquet.exists(), "Expired spool file should have been deleted"
        assert stats["expired_files_deleted"] >= 1 or stats["meta_deleted"] >= 1

    def test_invalid_query_id_returns_none(self, tmp_path):
        """query_id containing path-traversal characters is rejected; returns None."""
        redis_store: dict = {}
        mock_client = _mock_redis_client_factory(redis_store)

        with (
            patch.object(spool_mod, "QUERY_SPOOL_DIR", tmp_path),
            patch("mes_dashboard.core.query_spool_store.get_redis_client", return_value=mock_client),
            patch("mes_dashboard.core.query_spool_store.QUERY_SPOOL_ENABLED", True),
        ):
            result = get_spool_file_path("test_ns", "../../etc/passwd")
            assert result is None
