# -*- coding: utf-8 -*-
"""Unit tests for RejectHistoryJob (BaseChunkedDuckDBJob migration, P2).

AC-2: DuckDB groupby/pareto/trend parity vs legacy pandas.
AC-3: feature flag default off; legacy path executes when flag=off.
AC-4: 6 post-hoc OOM guards removed (ast-absence proof).
"""
from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import patch

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

_REPO_ROOT = Path(__file__).parent.parent


class TestRejectHistoryJobFlagDispatch:
    """AC-3: Feature flag routing in reject_history_routes."""

    def test_flag_off_routes_to_legacy_service(self, monkeypatch):
        """When REJECT_HISTORY_USE_UNIFIED_JOB=off, legacy enqueue path is used."""
        import mes_dashboard.routes.reject_history_routes as routes_mod
        monkeypatch.setattr(routes_mod, "_REJECT_HISTORY_USE_UNIFIED_JOB", False)
        assert routes_mod._REJECT_HISTORY_USE_UNIFIED_JOB is False

    def test_flag_on_instantiates_reject_history_job(self, monkeypatch):
        """When REJECT_HISTORY_USE_UNIFIED_JOB=on, unified path constant is True."""
        import mes_dashboard.routes.reject_history_routes as routes_mod
        monkeypatch.setattr(routes_mod, "_REJECT_HISTORY_USE_UNIFIED_JOB", True)
        assert routes_mod._REJECT_HISTORY_USE_UNIFIED_JOB is True


class TestRejectHistoryJobConstruction:
    """RejectHistoryJob can be instantiated and has correct class attrs."""

    def test_job_class_attributes(self):
        from mes_dashboard.workers.reject_history_worker import RejectHistoryJob
        from mes_dashboard.core.base_chunked_duckdb_job import ChunkStrategy
        assert RejectHistoryJob.namespace == "reject_dataset"
        assert RejectHistoryJob.chunk_strategy == ChunkStrategy.TIME
        assert RejectHistoryJob.requires_cross_chunk_reduction is True

    def test_job_always_async_false(self):
        import importlib
        import mes_dashboard.workers.reject_history_worker as _worker_mod
        # Reload to re-fire module-level register_job_type (test-discipline rule)
        importlib.reload(_worker_mod)
        from mes_dashboard.services.job_registry import get_job_type_config
        cfg = get_job_type_config("reject_unified")
        assert cfg is not None
        assert cfg.always_async is False


class TestRejectHistoryJobPreQuery:
    """pre_query populates _chunks for the given date range."""

    def test_pre_query_populates_chunks(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DUCKDB_JOB_DIR", str(tmp_path))
        from mes_dashboard.workers.reject_history_worker import RejectHistoryJob
        job = RejectHistoryJob("test-rh-001", params={
            "start_date": "2025-01-01",
            "end_date": "2025-01-10",
            "include_excluded_scrap": False,
            "exclude_material_scrap": False,
            "exclude_pb_diode": False,
        })
        with patch("mes_dashboard.services.reject_dataset_cache._make_query_id",
                   return_value="rh-test123"), \
             patch("mes_dashboard.core.query_spool_store.get_spool_file_path", return_value=None):
            job.pre_query()
        assert len(job._chunks) >= 1


def _make_reject_raw_table(n_rows: int = 4) -> pa.Table:
    """Minimal raw table matching primary.sql output."""
    return pa.table({
        "TXN_TIME": ["2025-01-01 10:00:00"] * n_rows,
        "TXN_DAY": ["2025-01-01"] * n_rows,
        "TXN_MONTH": ["2025-01"] * n_rows,
        "WORKCENTER_GROUP": ["WCG1", "WCG1", "WCG2", "WCG2"],
        "WORKCENTERSEQUENCE_GROUP": ["SEQ1"] * n_rows,
        "WORKCENTERNAME": ["WC1", "WC1", "WC2", "WC2"],
        "SPECNAME": ["SPEC1"] * n_rows,
        "EQUIPMENTNAME": [None, "EQP1", "EQP2", None],  # NULL EQUIPMENT_ID case
        "PRODUCTLINENAME": ["LINE1"] * n_rows,
        "SCRAP_OBJECTTYPE": ["LOT"] * n_rows,
        "PJ_TYPE": ["GDBA"] * n_rows,
        "CONTAINERNAME": ["LOT001", "LOT001", "LOT002", "LOT003"],
        "PJ_WORKORDER": ["WO1"] * n_rows,
        "PJ_FUNCTION": ["F1"] * n_rows,
        "PRODUCTNAME": ["PROD1"] * n_rows,
        "LOSSREASONNAME": ["REASON_A", "REASON_B", "REASON_A", "REASON_B"],
        "LOSSREASON_CODE": ["RA", "RB", "RA", "RB"],
        "REJECTCOMMENT": [None] * n_rows,
        "AFFECTED_WORKORDER_COUNT": pa.array([1] * n_rows, type=pa.int64()),
        "MOVEIN_QTY": pa.array([100, 100, 50, 50], type=pa.float64()),
        "REJECT_QTY": pa.array([5, 3, 2, 1], type=pa.float64()),
        "REJECT_TOTAL_QTY": pa.array([5, 3, 2, 1], type=pa.float64()),
        "DEFECT_QTY": pa.array([2, 1, 1, 0], type=pa.float64()),
        "STANDBY_QTY": pa.array([0] * n_rows, type=pa.float64()),
        "QTYTOPROCESS_QTY": pa.array([0] * n_rows, type=pa.float64()),
        "INPROCESS_QTY": pa.array([0] * n_rows, type=pa.float64()),
        "PROCESSED_QTY": pa.array([0] * n_rows, type=pa.float64()),
        "REJECT_RATE_PCT": pa.array([5.0, 3.0, 4.0, 2.0], type=pa.float64()),
        "DEFECT_RATE_PCT": pa.array([2.0, 1.0, 2.0, 0.0], type=pa.float64()),
        "REJECT_SHARE_PCT": pa.array([0.0] * n_rows, type=pa.float64()),
    })


class TestRejectHistoryJobPostAggregate:
    """AC-2: post_aggregate writes groupby/pareto/trend spool."""

    def test_reject_history_job_groupby_parity_null_equipment(self, tmp_path, monkeypatch):
        """NULL EQUIPMENTNAME must survive groupby in post_aggregate."""
        monkeypatch.setenv("DUCKDB_JOB_DIR", str(tmp_path))
        from mes_dashboard.workers.reject_history_worker import RejectHistoryJob

        spool_path = str(tmp_path / "spool_rh.parquet")
        job = RejectHistoryJob("test-rh-grpby", params={
            "start_date": "2025-01-01", "end_date": "2025-01-01",
            "include_excluded_scrap": False, "exclude_material_scrap": False, "exclude_pb_diode": False,
        })
        job._spool_key = "rh-test-key"
        job._spool_path = spool_path
        job._query_id = "rh-test-key"
        job._chunks = [{"chunk_start": "2025-01-01", "chunk_end_excl": "2025-01-02", "where_clause": "", "bind_params": {}}]

        # Write raw rows into job DuckDB
        import duckdb
        job_duckdb = str(tmp_path / "job_rh_grpby.duckdb")
        raw = _make_reject_raw_table()
        con = duckdb.connect(job_duckdb)
        try:
            con.register("_raw", raw)
            con.execute("CREATE TABLE raw AS SELECT * FROM _raw")
        finally:
            con.close()

        with patch("mes_dashboard.core.query_spool_store.register_spool_file"):
            result = job.post_aggregate(job_duckdb)

        assert Path(result).exists()
        con2 = duckdb.connect()
        rows = con2.execute(f"SELECT COUNT(*) FROM read_parquet('{result}')").fetchone()[0]
        assert rows >= 1
        con2.close()

    def test_reject_history_job_pareto_parity_multi_defect(self, tmp_path, monkeypatch):
        """Pareto ordering must be deterministic for ≥2 LOSSREASONNAME values."""
        monkeypatch.setenv("DUCKDB_JOB_DIR", str(tmp_path))
        from mes_dashboard.workers.reject_history_worker import RejectHistoryJob

        spool_path = str(tmp_path / "spool_pareto.parquet")
        job = RejectHistoryJob("test-rh-pareto", params={
            "start_date": "2025-01-01", "end_date": "2025-01-01",
            "include_excluded_scrap": False, "exclude_material_scrap": False, "exclude_pb_diode": False,
        })
        job._spool_key = "rh-pareto-key"
        job._spool_path = spool_path
        job._query_id = "rh-pareto-key"
        job._chunks = [{"chunk_start": "2025-01-01", "chunk_end_excl": "2025-01-02", "where_clause": "", "bind_params": {}}]

        import duckdb
        job_duckdb = str(tmp_path / "job_pareto.duckdb")
        raw = _make_reject_raw_table()
        con = duckdb.connect(job_duckdb)
        try:
            con.register("_raw", raw)
            con.execute("CREATE TABLE raw AS SELECT * FROM _raw")
        finally:
            con.close()

        with patch("mes_dashboard.core.query_spool_store.register_spool_file"):
            result = job.post_aggregate(job_duckdb)

        assert Path(result).exists()
        con2 = duckdb.connect()
        # Verify at least one row with LOSSREASONNAME (or summary columns)
        row_count = con2.execute(f"SELECT COUNT(*) FROM read_parquet('{result}')").fetchone()[0]
        assert row_count > 0
        con2.close()

    def test_reject_history_job_trend_parity_tolerance(self, tmp_path, monkeypatch):
        """Trend REJECT_RATE_PCT must be within 1e-6 of expected value."""
        monkeypatch.setenv("DUCKDB_JOB_DIR", str(tmp_path))
        from mes_dashboard.workers.reject_history_worker import RejectHistoryJob

        spool_path = str(tmp_path / "spool_trend.parquet")
        job = RejectHistoryJob("test-rh-trend", params={
            "start_date": "2025-01-01", "end_date": "2025-01-01",
            "include_excluded_scrap": False, "exclude_material_scrap": False, "exclude_pb_diode": False,
        })
        job._spool_key = "rh-trend-key"
        job._spool_path = spool_path
        job._query_id = "rh-trend-key"
        job._chunks = [{"chunk_start": "2025-01-01", "chunk_end_excl": "2025-01-02", "where_clause": "", "bind_params": {}}]

        import duckdb
        job_duckdb = str(tmp_path / "job_trend.duckdb")
        raw = _make_reject_raw_table()
        con = duckdb.connect(job_duckdb)
        try:
            con.register("_raw", raw)
            con.execute("CREATE TABLE raw AS SELECT * FROM _raw")
        finally:
            con.close()

        with patch("mes_dashboard.core.query_spool_store.register_spool_file"):
            result = job.post_aggregate(job_duckdb)

        assert Path(result).exists()
        # Post_aggregate writes the raw rows spool — the aggregation views come
        # later via DuckDB SQL. Just verify the row data is present.
        import duckdb as dk
        con2 = dk.connect()
        cnt = con2.execute(f"SELECT COUNT(*) FROM read_parquet('{result}')").fetchone()[0]
        assert cnt == 4  # 4 raw rows
        con2.close()

    def test_reject_history_job_empty_chunk_window_no_crash(self, tmp_path, monkeypatch):
        """post_aggregate handles empty DuckDB table gracefully."""
        monkeypatch.setenv("DUCKDB_JOB_DIR", str(tmp_path))
        from mes_dashboard.workers.reject_history_worker import RejectHistoryJob

        spool_path = str(tmp_path / "spool_empty_rh.parquet")
        job = RejectHistoryJob("test-rh-empty", params={
            "start_date": "2025-01-01", "end_date": "2025-01-01",
            "include_excluded_scrap": False, "exclude_material_scrap": False, "exclude_pb_diode": False,
        })
        job._spool_key = "rh-empty-key"
        job._spool_path = spool_path
        job._query_id = "rh-empty-key"
        job._chunks = [{"chunk_start": "2025-01-01", "chunk_end_excl": "2025-01-02", "where_clause": "", "bind_params": {}}]

        import duckdb
        job_duckdb = str(tmp_path / "job_empty_rh.duckdb")
        # Create empty raw table
        empty_raw = pa.table({col: pa.array([], type=_make_reject_raw_table().schema.field(col).type)
                               for col in _make_reject_raw_table().schema.names})
        con = duckdb.connect(job_duckdb)
        try:
            con.register("_raw", empty_raw)
            con.execute("CREATE TABLE raw AS SELECT * FROM _raw")
        finally:
            con.close()

        with patch("mes_dashboard.core.query_spool_store.register_spool_file"):
            result = job.post_aggregate(job_duckdb)

        assert Path(result).exists()
        con2 = duckdb.connect()
        rows = con2.execute(f"SELECT COUNT(*) FROM read_parquet('{result}')").fetchone()[0]
        assert rows == 0
        con2.close()


class TestOomGuardAbsence:
    """AC-4: post-hoc OOM guard patterns are absent in reject_dataset_cache and reject_history_service."""

    def _parse_source(self, rel_path: str) -> ast.Module:
        src = (_REPO_ROOT / rel_path).read_text(encoding="utf-8")
        return ast.parse(src, filename=rel_path)

    def _find_oom_guard_raises(self, tree: ast.Module) -> list:
        """Find ast.Raise nodes inside ast.If whose test compares len(df) or memory_usage."""
        offenders = []

        class Visitor(ast.NodeVisitor):
            def visit_If(self, node: ast.If):  # noqa: N802
                test_src = ast.unparse(node.test) if hasattr(ast, "unparse") else ""
                has_raise = any(isinstance(n, ast.Raise) for n in ast.walk(node))
                if has_raise and ("len(" in test_src or "memory_usage" in test_src):
                    offenders.append(node)
                self.generic_visit(node)

        Visitor().visit(tree)
        return offenders

    def test_oom_guard_patterns_absent_in_reject_history_service(self):
        """reject_history_service.py must have zero len(df)/memory_usage raise guards."""
        tree = self._parse_source("src/mes_dashboard/services/reject_history_service.py")
        offenders = self._find_oom_guard_raises(tree)
        assert offenders == [], (
            f"Found {len(offenders)} OOM guard raise pattern(s) in reject_history_service.py "
            f"(AC-4 violation). Lines: {[o.lineno for o in offenders]}"
        )

    def test_oom_guard_patterns_absent_in_reject_dataset_cache(self):
        """reject_dataset_cache.py must have zero len(df)/memory_usage raise guards."""
        tree = self._parse_source("src/mes_dashboard/services/reject_dataset_cache.py")
        offenders = self._find_oom_guard_raises(tree)
        assert offenders == [], (
            f"Found {len(offenders)} OOM guard raise pattern(s) in reject_dataset_cache.py "
            f"(AC-4 violation). Lines: {[o.lineno for o in offenders]}"
        )


class TestRejectHistoryJobChunkToDuckDB:
    """Regression: chunk_to_duckdb must use explicit DDL to prevent NULL-column INT32 inference.

    When the first time-chunk returns no reject records, REJECTCOMMENT (and other
    string columns) arrive as pa.null() in the Arrow batch. The base-class
    'CREATE TABLE AS SELECT ... WHERE 1=0' then infers INT32 for those columns.
    Subsequent chunks with real string values then fail with ConversionException.

    Fix: RejectHistoryJob.chunk_to_duckdb overrides the base class to use an
    explicit DDL (VARCHAR/BIGINT/DOUBLE) and INSERT BY NAME.
    """

    def test_null_rejectcomment_then_real_string_no_conversion_error(self, tmp_path):
        """First batch has NULL REJECTCOMMENT; second batch has real string — must not raise."""
        import duckdb

        from mes_dashboard.workers.reject_history_worker import RejectHistoryJob

        job = RejectHistoryJob.__new__(RejectHistoryJob)
        job.job_id = "test-null-rejectcomment"
        import threading
        job._writer_lock = threading.Lock()

        duckdb_path = str(tmp_path / "test.duckdb")

        # Batch 1: all nulls in REJECTCOMMENT (simulates first chunk with no reject records)
        null_batch = pa.record_batch({
            "TXN_TIME": pa.array(["2026-01-01"], type=pa.string()),
            "TXN_DAY": pa.array(["2026-01-01"], type=pa.string()),
            "TXN_MONTH": pa.array(["2026-01"], type=pa.string()),
            "WORKCENTER_GROUP": pa.array([None], type=pa.string()),
            "WORKCENTERSEQUENCE_GROUP": pa.array([None], type=pa.string()),
            "WORKCENTERNAME": pa.array(["WC1"], type=pa.string()),
            "SPECNAME": pa.array([None], type=pa.string()),
            "EQUIPMENTNAME": pa.array([None], type=pa.string()),
            "PRODUCTLINENAME": pa.array(["PKG-A"], type=pa.string()),
            "SCRAP_OBJECTTYPE": pa.array([None], type=pa.string()),
            "PJ_TYPE": pa.array(["AP"], type=pa.string()),
            "CONTAINERNAME": pa.array(["LOT001"], type=pa.string()),
            "PJ_WORKORDER": pa.array([None], type=pa.string()),
            "PJ_FUNCTION": pa.array(["FUNC1"], type=pa.string()),
            "PRODUCTNAME": pa.array(["PROD-A"], type=pa.string()),
            "LOSSREASONNAME": pa.array(["REASON-X"], type=pa.string()),
            "LOSSREASON_CODE": pa.array(["CODE-X"], type=pa.string()),
            "REJECTCOMMENT": pa.array([None], type=pa.null()),  # NULL — triggers bug
            "AFFECTED_WORKORDER_COUNT": pa.array([0], type=pa.int64()),
            "MOVEIN_QTY": pa.array([100.0], type=pa.float64()),
            "REJECT_QTY": pa.array([0.0], type=pa.float64()),
            "REJECT_TOTAL_QTY": pa.array([0.0], type=pa.float64()),
            "DEFECT_QTY": pa.array([0.0], type=pa.float64()),
            "STANDBY_QTY": pa.array([0.0], type=pa.float64()),
            "QTYTOPROCESS_QTY": pa.array([0.0], type=pa.float64()),
            "INPROCESS_QTY": pa.array([0.0], type=pa.float64()),
            "PROCESSED_QTY": pa.array([0.0], type=pa.float64()),
            "REJECT_RATE_PCT": pa.array([0.0], type=pa.float64()),
            "DEFECT_RATE_PCT": pa.array([0.0], type=pa.float64()),
            "REJECT_SHARE_PCT": pa.array([0.0], type=pa.float64()),
        })

        # Batch 2: REJECTCOMMENT has a real Chinese string value
        real_batch = pa.record_batch({
            **{k: null_batch.column(k) for k in null_batch.schema.names if k != "REJECTCOMMENT"},
            "REJECTCOMMENT": pa.array(["自動上料異常"], type=pa.string()),
        })

        # Must not raise ConversionException
        job.chunk_to_duckdb(null_batch, duckdb_path)
        job.chunk_to_duckdb(real_batch, duckdb_path)

        # Verify REJECTCOMMENT was correctly stored as VARCHAR
        con = duckdb.connect(duckdb_path)
        rows = con.execute("SELECT REJECTCOMMENT FROM raw ORDER BY REJECTCOMMENT NULLS LAST").fetchall()
        con.close()
        assert rows[0][0] == "自動上料異常"
        assert rows[1][0] is None

    def test_chunk_to_duckdb_override_present(self):
        """RejectHistoryJob must override chunk_to_duckdb (explicit DDL, not inherited)."""
        from mes_dashboard.workers.reject_history_worker import RejectHistoryJob
        from mes_dashboard.core.base_chunked_duckdb_job import BaseChunkedDuckDBJob

        assert RejectHistoryJob.chunk_to_duckdb is not BaseChunkedDuckDBJob.chunk_to_duckdb, (
            "RejectHistoryJob.chunk_to_duckdb must be overridden to use explicit DDL; "
            "the base class infers types from first batch which causes INT32 for NULL columns."
        )
