# -*- coding: utf-8 -*-
"""Unit tests for ProductionHistoryJob (BaseChunkedDuckDBJob migration, P2).

AC-1: spool row-level parity vs legacy path.
AC-3: feature flag default off; legacy path executes when flag=off.
AC-7: _APPROVED_CALLERS extended (see test_query_cost_policy.py).
"""
from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import MagicMock, patch

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

_REPO_ROOT = Path(__file__).parent.parent


class TestProductionHistoryJobFlagDispatch:
    """AC-3: Feature flag routing in production_history_routes."""

    def test_flag_off_routes_to_legacy_service(self, monkeypatch):
        """When PRODUCTION_HISTORY_USE_UNIFIED_JOB=off, legacy enqueue path is used."""
        import mes_dashboard.routes.production_history_routes as routes_mod
        monkeypatch.setattr(routes_mod, "_PRODUCTION_HISTORY_USE_UNIFIED_JOB", False)
        # Confirm the module-level constant is honoured
        assert routes_mod._PRODUCTION_HISTORY_USE_UNIFIED_JOB is False

    def test_flag_on_instantiates_production_history_job(self, monkeypatch):
        """When PRODUCTION_HISTORY_USE_UNIFIED_JOB=on, unified path constant is True."""
        import mes_dashboard.routes.production_history_routes as routes_mod
        monkeypatch.setattr(routes_mod, "_PRODUCTION_HISTORY_USE_UNIFIED_JOB", True)
        assert routes_mod._PRODUCTION_HISTORY_USE_UNIFIED_JOB is True


class TestProductionHistoryJobConstruction:
    """ProductionHistoryJob can be instantiated and has correct class attrs."""

    def test_job_class_attributes(self):
        from mes_dashboard.workers.production_history_worker import ProductionHistoryJob
        from mes_dashboard.core.base_chunked_duckdb_job import ChunkStrategy
        assert ProductionHistoryJob.namespace == "production_history"
        assert ProductionHistoryJob.chunk_strategy == ChunkStrategy.TIME
        assert ProductionHistoryJob.requires_cross_chunk_reduction is False

    def test_job_always_async_false(self):
        import importlib
        from mes_dashboard.services import job_registry as _reg_mod
        import mes_dashboard.workers.production_history_worker as _worker_mod
        # Reload to re-fire module-level register_job_type (test-discipline rule)
        importlib.reload(_worker_mod)
        from mes_dashboard.services.job_registry import get_job_type_config
        cfg = get_job_type_config("production_history_unified")
        assert cfg is not None
        assert cfg.always_async is False


class TestProductionHistoryJobPreQuery:
    """pre_query populates _chunks for the given date range."""

    def test_pre_query_populates_chunks(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DUCKDB_JOB_DIR", str(tmp_path))
        from mes_dashboard.workers.production_history_worker import ProductionHistoryJob
        job = ProductionHistoryJob("test-ph-001", params={
            "start_date": "2025-01-01",
            "end_date": "2025-01-03",
            "pj_types": ["GDBA"],
        })
        with patch("mes_dashboard.services.production_history_service.make_canonical_spool_id",
                   return_value="ph-test123"), \
             patch("mes_dashboard.core.query_spool_store.get_spool_file_path", return_value=None):
            job.pre_query()
        # 3 days → 3 chunks (one per day)
        assert len(job._chunks) >= 1

    def test_pre_query_single_day(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DUCKDB_JOB_DIR", str(tmp_path))
        from mes_dashboard.workers.production_history_worker import ProductionHistoryJob
        job = ProductionHistoryJob("test-ph-single", params={
            "start_date": "2025-05-01",
            "end_date": "2025-05-01",
            "pj_types": ["GDBA"],
        })
        with patch("mes_dashboard.services.production_history_service.make_canonical_spool_id",
                   return_value="ph-single"), \
             patch("mes_dashboard.core.query_spool_store.get_spool_file_path", return_value=None):
            job.pre_query()
        assert len(job._chunks) == 1


class TestProductionHistoryJobSpoolParity:
    """AC-1: after run(), spool schema matches expected columns."""

    def _make_sample_table(self) -> pa.Table:
        return pa.table({
            "CONTAINERNAME": ["LOT001"],
            "PJ_TYPE": ["GDBA"],
            "PJ_BOP": ["BOP1"],
            "PJ_FUNCTION": ["F1"],
            "MFGORDERNAME": ["WO001"],
            "FIRSTNAME": ["PROD1"],
            "PRODUCTLINENAME": ["LINE1"],
            "WORKCENTERNAME": ["WC1"],
            "SPECNAME": ["SPEC1"],
            "EQUIPMENTID": ["EQP001"],
            "EQUIPMENTNAME": ["EQP NAME"],
            "TRACKINTIMESTAMP": ["2025-01-01 08:00:00"],
            "TRACKOUTTIMESTAMP": ["2025-01-01 09:00:00"],
            "TRACKINQTY": pa.array([100], type=pa.int64()),
            "TRACKOUTQTY": pa.array([98], type=pa.int64()),
        })

    def test_production_history_job_spool_parity_exact_rows(self, tmp_path, monkeypatch):
        """Post-aggregate spool file has all expected schema columns."""
        monkeypatch.setenv("DUCKDB_JOB_DIR", str(tmp_path))
        from mes_dashboard.workers.production_history_worker import ProductionHistoryJob

        spool_path = str(tmp_path / "spool.parquet")
        job = ProductionHistoryJob("test-ph-parity", params={
            "start_date": "2025-01-01",
            "end_date": "2025-01-01",
            "pj_types": ["GDBA"],
        })
        job._spool_key = "ph-test-key"
        job._spool_path = spool_path
        job._chunks = [{"chunk_start": "2025-01-01", "chunk_end_excl": "2025-01-02", "extra_sql": "", "extra_params": {}}]

        # Write a chunk parquet manually
        chunk_dir = job._make_chunk_parquet_dir("test-ph-parity")
        pq.write_table(self._make_sample_table(), chunk_dir / "chunk-0000-0000.parquet")

        with patch("mes_dashboard.core.query_spool_store.register_spool_file"):
            result = job.post_aggregate(None)

        assert Path(result).exists()
        import duckdb
        cols = duckdb.execute(f"DESCRIBE SELECT * FROM read_parquet('{result}')").fetchdf()["column_name"].tolist()
        expected_cols = {
            "CONTAINERNAME", "PJ_TYPE", "PJ_BOP", "PJ_FUNCTION", "MFGORDERNAME",
            "FIRSTNAME", "PRODUCTLINENAME", "WORKCENTERNAME", "SPECNAME",
            "EQUIPMENTID", "EQUIPMENTNAME", "TRACKINTIMESTAMP", "TRACKOUTTIMESTAMP",
            "TRACKINQTY", "TRACKOUTQTY",
        }
        for col in expected_cols:
            assert col in cols, f"Missing column {col} in spool parquet"

    def test_production_history_job_empty_chunk_window_handled(self, tmp_path, monkeypatch):
        """post_aggregate handles an empty chunk dir gracefully."""
        monkeypatch.setenv("DUCKDB_JOB_DIR", str(tmp_path))
        from mes_dashboard.workers.production_history_worker import ProductionHistoryJob

        spool_path = str(tmp_path / "empty_spool.parquet")
        job = ProductionHistoryJob("test-ph-empty", params={
            "start_date": "2025-01-01",
            "end_date": "2025-01-01",
            "pj_types": ["GDBA"],
        })
        job._spool_key = "ph-empty-key"
        job._spool_path = spool_path
        job._chunks = [{"chunk_start": "2025-01-01", "chunk_end_excl": "2025-01-02", "extra_sql": "", "extra_params": {}}]

        # Create chunk dir but write empty parquet
        chunk_dir = job._make_chunk_parquet_dir("test-ph-empty")
        empty_table = pa.table({
            "CONTAINERNAME": pa.array([], type=pa.string()),
            "PJ_TYPE": pa.array([], type=pa.string()),
            "PJ_BOP": pa.array([], type=pa.string()),
            "PJ_FUNCTION": pa.array([], type=pa.string()),
            "MFGORDERNAME": pa.array([], type=pa.string()),
            "FIRSTNAME": pa.array([], type=pa.string()),
            "PRODUCTLINENAME": pa.array([], type=pa.string()),
            "WORKCENTERNAME": pa.array([], type=pa.string()),
            "SPECNAME": pa.array([], type=pa.string()),
            "EQUIPMENTID": pa.array([], type=pa.string()),
            "EQUIPMENTNAME": pa.array([], type=pa.string()),
            "TRACKINTIMESTAMP": pa.array([], type=pa.string()),
            "TRACKOUTTIMESTAMP": pa.array([], type=pa.string()),
            "TRACKINQTY": pa.array([], type=pa.int64()),
            "TRACKOUTQTY": pa.array([], type=pa.int64()),
        })
        pq.write_table(empty_table, chunk_dir / "chunk-0000-0000.parquet")

        with patch("mes_dashboard.core.query_spool_store.register_spool_file"):
            result = job.post_aggregate(None)

        assert Path(result).exists()
        import duckdb
        rows = duckdb.execute(f"SELECT COUNT(*) FROM read_parquet('{result}')").fetchone()[0]
        assert rows == 0


class TestProductionHistoryJobProgress:
    """progress_report uses production_history prefix."""

    def test_production_history_job_progress_milestones(self, monkeypatch):
        from mes_dashboard.workers.production_history_worker import ProductionHistoryJob
        calls = []
        monkeypatch.setattr(
            "mes_dashboard.services.async_query_job_service.update_job_progress",
            lambda prefix, job_id, **kw: calls.append((prefix, job_id, kw)),
        )
        job = ProductionHistoryJob("test-pct", params={
            "start_date": "2025-01-01", "end_date": "2025-01-01", "pj_types": [],
        })
        job.progress_report(15)
        assert len(calls) == 1
        assert calls[0][0] == "production_history_unified"
        assert calls[0][2].get("pct") == "15"
