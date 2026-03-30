# -*- coding: utf-8 -*-
"""Integration test: Parquet spool round-trip through query_spool_store.

Verifies that store_spooled_df writes a valid Parquet file and
load_spooled_df reads back identical data. Redis is mocked (in-memory
dict) so that only the Parquet I/O path is exercised for real.
"""

import json
import os
import pytest
import pandas as pd
from pathlib import Path
from unittest.mock import MagicMock


def _make_fake_redis():
    """Create a dict-backed fake Redis client that supports get/setex/delete."""
    store = {}

    client = MagicMock()
    client.get = lambda key: store.get(key)
    client.setex = lambda key, ttl, value: store.__setitem__(key, value)
    client.delete = lambda *keys: sum(store.pop(k, None) is not None for k in keys)

    def pipeline_fn(transaction=True):
        pipe = MagicMock()
        _ops = []

        def setex(key, ttl, value):
            _ops.append(("setex", key, ttl, value))
            return pipe

        def delete(*keys):
            _ops.append(("delete", keys))
            return pipe

        def execute():
            for op in _ops:
                if op[0] == "setex":
                    store[op[1]] = op[3]
                elif op[0] == "delete":
                    for k in op[1]:
                        store.pop(k, None)
            _ops.clear()
            return []

        pipe.setex = setex
        pipe.delete = delete
        pipe.execute = execute
        return pipe

    client.pipeline = pipeline_fn
    return client


class TestSpoolParquetRoundTrip:
    """Real Parquet write/read through query_spool_store API with mock Redis."""

    @pytest.fixture(autouse=True)
    def _setup_spool_dir(self, tmp_path, monkeypatch):
        """Point spool directory to a clean temp folder per test."""
        spool_dir = tmp_path / "spool"
        spool_dir.mkdir()

        monkeypatch.setenv("QUERY_SPOOL_DIR", str(spool_dir))
        monkeypatch.setenv("QUERY_SPOOL_ENABLED", "true")
        monkeypatch.setenv("REDIS_ENABLED", "true")

        import mes_dashboard.core.query_spool_store as qss
        monkeypatch.setattr(qss, "QUERY_SPOOL_DIR", Path(str(spool_dir)))
        monkeypatch.setattr(qss, "QUERY_SPOOL_ENABLED", True)

        fake_redis = _make_fake_redis()
        monkeypatch.setattr(
            "mes_dashboard.core.query_spool_store.get_redis_client",
            lambda: fake_redis,
        )
        self.qss = qss
        self.spool_dir = spool_dir

    def test_store_and_load_df(self):
        """Write a DataFrame, read it back, verify equality."""
        df = pd.DataFrame({
            "LOT_ID": ["A001", "A002", "A003"],
            "DEFECT_QTY": [10, 0, 5],
            "STATION": ["WC1", "WC2", "WC1"],
        })
        ns = "test_roundtrip"
        qid = "rt_001"

        ok = self.qss.store_spooled_df(ns, qid, df)
        assert ok is True

        loaded = self.qss.load_spooled_df(ns, qid)
        assert loaded is not None
        pd.testing.assert_frame_equal(loaded.reset_index(drop=True), df)

    def test_store_creates_parquet_file(self):
        """Verify the spool file is a real Parquet file on disk."""
        df = pd.DataFrame({"x": [1, 2]})
        ns = "test_file"
        qid = "file_001"

        self.qss.store_spooled_df(ns, qid, df)
        path = self.qss.get_spool_file_path(ns, qid)
        assert path is not None
        assert os.path.isfile(path)
        assert path.endswith(".parquet")

    def test_load_nonexistent_returns_none(self):
        """Spool miss returns None, not an error."""
        result = self.qss.load_spooled_df("no_such_ns", "no_such_qid")
        assert result is None

    def test_get_spool_file_path_nonexistent_returns_none(self):
        """Path resolution for missing spool returns None."""
        path = self.qss.get_spool_file_path("missing", "missing_id")
        assert path is None

    def test_empty_dataframe_returns_false(self):
        """An empty DataFrame is rejected by store_spooled_df (by design)."""
        df = pd.DataFrame({"col_a": pd.Series([], dtype="str")})
        ns = "test_empty"
        qid = "empty_001"

        ok = self.qss.store_spooled_df(ns, qid, df)
        # store_spooled_df returns False for empty DataFrames
        assert ok is False

    def test_duckdb_can_read_stored_spool(self):
        """Verify DuckDB can query a file produced by store_spooled_df."""
        try:
            import duckdb  # noqa: F401
        except ImportError:
            pytest.skip("duckdb not installed")

        df = pd.DataFrame({
            "ID": list(range(100)),
            "VALUE": [float(i) * 1.5 for i in range(100)],
        })
        ns = "test_duckdb"
        qid = "duck_001"

        self.qss.store_spooled_df(ns, qid, df)
        path = self.qss.get_spool_file_path(ns, qid)
        assert path is not None

        from mes_dashboard.core.duckdb_runtime import create_heavy_query_connection
        conn = create_heavy_query_connection()
        try:
            row = conn.execute(
                f"SELECT COUNT(*) AS cnt, SUM(\"VALUE\") AS total FROM read_parquet('{path}')"
            ).fetchone()
            assert row[0] == 100
            assert abs(row[1] - sum(i * 1.5 for i in range(100))) < 0.01
        finally:
            conn.close()

    def test_spool_metadata_roundtrip(self):
        """Verify that metadata is stored and retrievable via get_spool_metadata."""
        df = pd.DataFrame({"A": [1, 2, 3]})
        ns = "test_meta"
        qid = "meta_001"

        self.qss.store_spooled_df(ns, qid, df)

        meta = self.qss.get_spool_metadata(ns, qid)
        assert meta is not None
        assert meta["query_id"] == qid
        assert meta["row_count"] == 3
        assert meta["file_size_bytes"] > 0
        assert "relative_path" in meta
        assert "created_at" in meta
        assert "expires_at" in meta
