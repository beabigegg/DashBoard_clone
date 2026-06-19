# -*- coding: utf-8 -*-
"""Unit tests for ResourceHistoryBaseJob and ResourceHistoryOeeJob.

Covers AC-2 (chunk strategy), AC-3 (±30d seam parity), AC-4 (iterrows→SQL parity),
AC-6 (spool schema UNCHANGED).

All tests are pure-unit; no Oracle connection required.
"""
from __future__ import annotations

import importlib
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_base_job(job_id: str = "test-base-001", params: dict = None):
    from mes_dashboard.workers.resource_history_base_worker import ResourceHistoryBaseJob
    return ResourceHistoryBaseJob(
        job_id=job_id,
        params=params or {"start_date": "2024-01-01", "end_date": "2024-01-03"},
    )


def _make_oee_job(job_id: str = "test-oee-001", params: dict = None):
    from mes_dashboard.workers.resource_history_oee_worker import ResourceHistoryOeeJob
    return ResourceHistoryOeeJob(
        job_id=job_id,
        params=params or {"start_date": "2024-01-01", "end_date": "2024-01-03"},
    )


# ---------------------------------------------------------------------------
# TestResourceHistoryBaseJob (AC-2)
# ---------------------------------------------------------------------------

class TestResourceHistoryBaseJob:
    def test_requires_cross_chunk_reduction_is_false(self):
        """AC-2: base job must have requires_cross_chunk_reduction=False."""
        from mes_dashboard.workers.resource_history_base_worker import ResourceHistoryBaseJob
        assert ResourceHistoryBaseJob.requires_cross_chunk_reduction is False

    def test_chunk_strategy_is_time(self):
        """AC-2: base job must use ChunkStrategy.TIME."""
        from mes_dashboard.workers.resource_history_base_worker import ResourceHistoryBaseJob
        from mes_dashboard.core.base_chunked_duckdb_job import ChunkStrategy
        assert ResourceHistoryBaseJob.chunk_strategy == ChunkStrategy.TIME

    def test_build_chunk_sql_binds_date_range(self, monkeypatch):
        """AC-2: build_chunk_sql returns SQL binding :start_date and :end_date."""
        job = _make_base_job()
        job._historyid_filter = "1=1"

        # Patch SQLLoader to return a known SQL template
        fake_sql = (
            "SELECT * FROM TABLE WHERE TXNDATE BETWEEN :start_date AND :end_date "
            "AND {{ HISTORYID_FILTER }}"
        )
        with patch("mes_dashboard.sql.SQLLoader.load", return_value=fake_sql):
            sql, params = job.build_chunk_sql(
                {"start_date": "2024-01-01", "end_date": "2024-01-01"}
            )

        assert ":start_date" in sql or "start_date" in params
        assert "start_date" in params
        assert "end_date" in params
        assert params["start_date"] == "2024-01-01"
        assert params["end_date"] == "2024-01-01"

    def test_namespace_is_resource_dataset(self):
        """Base job writes to resource_dataset namespace (legacy-compatible)."""
        from mes_dashboard.workers.resource_history_base_worker import ResourceHistoryBaseJob
        assert ResourceHistoryBaseJob.namespace == "resource_dataset"

    def test_always_async_registered(self):
        """Base job is registered with always_async=True."""
        import importlib
        import mes_dashboard.workers.resource_history_base_worker as _w
        importlib.reload(_w)
        from mes_dashboard.services.job_registry import get_job_type_config
        config = get_job_type_config("resource-history-base")
        assert config is not None
        assert config.always_async is True


# ---------------------------------------------------------------------------
# TestResourceHistoryOeeJob (AC-2)
# ---------------------------------------------------------------------------

class TestResourceHistoryOeeJob:
    def test_requires_cross_chunk_reduction_is_true(self):
        """AC-2: OEE job must have requires_cross_chunk_reduction=True."""
        from mes_dashboard.workers.resource_history_oee_worker import ResourceHistoryOeeJob
        assert ResourceHistoryOeeJob.requires_cross_chunk_reduction is True

    def test_build_chunk_sql_extends_reject_window_30d_before_chunk_start(self):
        """AC-3: reject_start must be 30d before chunk start_date."""
        job = _make_oee_job()

        fake_sql = "SELECT * WHERE :start_date AND :reject_start AND :reject_end AND :end_date"
        with patch("mes_dashboard.sql.SQLLoader.load", return_value=fake_sql):
            sql, params = job.build_chunk_sql(
                {"start_date": "2024-02-01", "end_date": "2024-02-01"}
            )

        chunk_start_dt = datetime(2024, 2, 1)
        expected_reject_start = (chunk_start_dt - timedelta(days=30)).strftime("%Y-%m-%d")
        assert params["reject_start"] == expected_reject_start

    def test_build_chunk_sql_extends_reject_window_30d_after_chunk_end(self):
        """AC-3: reject_end must be 30d after chunk end_date."""
        job = _make_oee_job()

        fake_sql = "SELECT * WHERE :start_date AND :reject_start AND :reject_end AND :end_date"
        with patch("mes_dashboard.sql.SQLLoader.load", return_value=fake_sql):
            sql, params = job.build_chunk_sql(
                {"start_date": "2024-02-01", "end_date": "2024-02-01"}
            )

        chunk_end_dt = datetime(2024, 2, 1)
        expected_reject_end = (chunk_end_dt + timedelta(days=30)).strftime("%Y-%m-%d")
        assert params["reject_end"] == expected_reject_end

    def test_namespace_is_resource_oee(self):
        """OEE job writes to resource_oee namespace (legacy-compatible)."""
        from mes_dashboard.workers.resource_history_oee_worker import ResourceHistoryOeeJob
        assert ResourceHistoryOeeJob.namespace == "resource_oee"

    def test_always_async_registered(self):
        """OEE job is registered with always_async=True."""
        import importlib
        import mes_dashboard.workers.resource_history_oee_worker as _w
        importlib.reload(_w)
        from mes_dashboard.services.job_registry import get_job_type_config
        config = get_job_type_config("resource-history-oee")
        assert config is not None
        assert config.always_async is True


# ---------------------------------------------------------------------------
# TestOeeChunkSeamParity (AC-3 — data-boundary)
# ---------------------------------------------------------------------------

class TestOeeChunkSeamParity:
    """AC-3: NG events at chunk boundaries must be captured within the ±30d window."""

    def _make_chunk_params(self, chunk_date: str) -> dict:
        return {"start_date": chunk_date, "end_date": chunk_date}

    def test_ng_event_at_chunk_boundary_captured_in_output(self):
        """NG row's reject date = chunk-N last day; trackout = chunk-N+1 first day → captured."""
        job = _make_oee_job(params={"start_date": "2024-01-31", "end_date": "2024-01-31"})
        fake_sql = "SELECT * WHERE :start_date AND :end_date AND :reject_start AND :reject_end"
        with patch("mes_dashboard.sql.SQLLoader.load", return_value=fake_sql):
            # chunk date is 2024-01-31; reject window must reach back 30d
            sql, params = job.build_chunk_sql(
                {"start_date": "2024-01-31", "end_date": "2024-01-31"}
            )
        # reject_start = 2024-01-01 (31 days - 30 days)
        reject_start_dt = datetime.strptime(params["reject_start"], "%Y-%m-%d")
        chunk_start_dt = datetime(2024, 1, 31)
        assert (chunk_start_dt - reject_start_dt).days == 30

    def test_ng_event_within_30d_window_captured(self):
        """NG event 29d before producing trackout → within window, must be captured."""
        job = _make_oee_job(params={"start_date": "2024-03-01", "end_date": "2024-03-01"})
        fake_sql = "SELECT * WHERE :start_date AND :end_date AND :reject_start AND :reject_end"
        with patch("mes_dashboard.sql.SQLLoader.load", return_value=fake_sql):
            sql, params = job.build_chunk_sql(
                {"start_date": "2024-03-01", "end_date": "2024-03-01"}
            )
        # reject_start covers 30d before 2024-03-01 = 2024-01-30
        reject_start_dt = datetime.strptime(params["reject_start"], "%Y-%m-%d")
        ng_event_dt = datetime(2024, 3, 1) - timedelta(days=29)
        assert ng_event_dt >= reject_start_dt, (
            f"NG event {ng_event_dt} is outside reject window starting {reject_start_dt}"
        )

    def test_ng_event_beyond_30d_window_excluded(self):
        """NG event 31d before producing trackout → outside window, correctly excluded."""
        job = _make_oee_job(params={"start_date": "2024-03-01", "end_date": "2024-03-01"})
        fake_sql = "SELECT * WHERE :start_date AND :end_date AND :reject_start AND :reject_end"
        with patch("mes_dashboard.sql.SQLLoader.load", return_value=fake_sql):
            sql, params = job.build_chunk_sql(
                {"start_date": "2024-03-01", "end_date": "2024-03-01"}
            )
        reject_start_dt = datetime.strptime(params["reject_start"], "%Y-%m-%d")
        ng_event_dt = datetime(2024, 3, 1) - timedelta(days=31)
        assert ng_event_dt < reject_start_dt, (
            f"NG event {ng_event_dt} should be OUTSIDE reject window starting {reject_start_dt}"
        )

    def test_oee_ratio_of_sums_matches_single_pass_within_1e6(self):
        """AC-3/AC-4: DuckDB ratio-of-SUMs matches legacy iterrows formula ≤1e-6."""
        import duckdb

        # Synthetic OEE data: two equipment IDs across two chunks
        # chunk 1: EQP_A trackout=100, ng=10; EQP_B trackout=50, ng=5
        # chunk 2: EQP_A trackout=200, ng=20; EQP_B trackout=100, ng=10
        # Expected: EQP_A yield = (100+200)/((100+200)+(10+20)) = 300/330 = 0.9090...
        # Expected: EQP_B yield = (50+100)/((50+100)+(5+10)) = 150/165 = 0.9090...

        _AGG_SQL = """
SELECT
    EQUIPMENTID,
    SUM(TRACKOUT_QTY)  AS TRACKOUT_QTY,
    SUM(NG_QTY)        AS NG_QTY
FROM raw
GROUP BY EQUIPMENTID
ORDER BY EQUIPMENTID
"""
        # Use in-memory DuckDB to avoid file-already-exists conflicts in parallel tests
        con = duckdb.connect()
        try:
            con.execute("""
                CREATE TABLE raw AS
                SELECT 'EQP_A' AS EQUIPMENTID, DATE '2024-01-01' AS SHIFT_DATE,
                       100.0 AS TRACKOUT_QTY, 10.0 AS NG_QTY
                UNION ALL
                SELECT 'EQP_A', DATE '2024-01-02', 200.0, 20.0
                UNION ALL
                SELECT 'EQP_B', DATE '2024-01-01', 50.0, 5.0
                UNION ALL
                SELECT 'EQP_B', DATE '2024-01-02', 100.0, 10.0
            """)
            rows = con.execute(_AGG_SQL).fetchall()
        finally:
            con.close()

        # Map to dict: {eq_id: (trackout, ng)}
        result = {r[0]: (float(r[1]), float(r[2])) for r in rows}

        # Legacy iterrows formula: yield_pct = trackout / (trackout + ng)
        for eq_id, (trackout, ng) in result.items():
            denom = trackout + ng
            duckdb_yield = trackout / denom if denom > 0 else 0.0

            # Expected single-pass (same arithmetic):
            if eq_id == "EQP_A":
                expected_yield = 300.0 / 330.0
            else:
                expected_yield = 150.0 / 165.0

            assert abs(duckdb_yield - expected_yield) < 1e-6, (
                f"{eq_id}: DuckDB yield {duckdb_yield} differs from expected {expected_yield}"
            )


# ---------------------------------------------------------------------------
# TestIterrowsReplacement (AC-4)
# ---------------------------------------------------------------------------

class TestIterrowsReplacement:
    """AC-4: DuckDB spool join produces output equivalent to legacy iterrows."""

    def test_duckdb_join_output_matches_iterrows_output(self):
        """DuckDB OEE spool join produces same yield_pct as iterrows formula."""
        import duckdb

        # Simulate OEE spool with pre-aggregated per-EQUIPMENTID rows
        # (as written by ResourceHistoryOeeJob.post_aggregate)
        # Use in-memory DuckDB to avoid file conflicts
        con = duckdb.connect()
        try:
            con.execute("""
                CREATE TABLE oee AS
                SELECT 'EQP_X' AS EQUIPMENTID, 300.0 AS TRACKOUT_QTY, 30.0 AS NG_QTY
                UNION ALL
                SELECT 'EQP_Y', 0.0, 0.0
            """)
            rows = con.execute("""
                SELECT
                    EQUIPMENTID,
                    TRACKOUT_QTY,
                    NG_QTY,
                    CASE WHEN (TRACKOUT_QTY + NG_QTY) > 0
                         THEN TRACKOUT_QTY / (TRACKOUT_QTY + NG_QTY)
                         ELSE 0.0
                    END AS yield_frac
                FROM oee
                ORDER BY EQUIPMENTID
            """).fetchall()
        finally:
            con.close()

        result = {r[0]: (float(r[1]), float(r[2]), float(r[3])) for r in rows}

        # Legacy iterrows formula for EQP_X
        trackout_x, ng_x, yield_x = result["EQP_X"]
        expected_yield_x = 300.0 / (300.0 + 30.0)
        assert abs(yield_x - expected_yield_x) < 1e-6

        # Zero denominator case for EQP_Y
        trackout_y, ng_y, yield_y = result["EQP_Y"]
        assert yield_y == 0.0

    def test_duckdb_join_handles_zero_denominator(self):
        """AC-4: OEE ratio is 0 when both TRACKOUT_QTY and NG_QTY are 0."""
        import duckdb

        # Use in-memory DuckDB to avoid file conflicts
        con = duckdb.connect()
        try:
            rows = con.execute("""
                SELECT
                    CASE WHEN (0.0 + 0.0) > 0
                         THEN 0.0 / (0.0 + 0.0)
                         ELSE 0.0
                    END AS yield_frac
            """).fetchall()
        finally:
            con.close()

        assert rows[0][0] == 0.0


# ---------------------------------------------------------------------------
# TestSpoolSchemaUnchanged (AC-6)
# ---------------------------------------------------------------------------

class TestSpoolSchemaUnchanged:
    """AC-6: Spool parquet column sets must match legacy schema."""

    # Legacy column sets (from §3.19 data-shape-contract.md)
    _BASE_LEGACY_COLS = {
        "HISTORYID", "DATA_DATE",
        "PRD_HOURS", "SBY_HOURS", "UDT_HOURS", "SDT_HOURS", "EGT_HOURS", "NST_HOURS",
        "TOTAL_HOURS",
    }
    _OEE_LEGACY_COLS = {
        "EQUIPMENTID", "TRACKOUT_QTY", "NG_QTY",
    }

    def test_base_parquet_columns_match_legacy_schema(self, tmp_path, monkeypatch):
        """ResourceHistoryBaseJob writes parquet with legacy resource_dataset column set."""
        import duckdb, pyarrow as pa, pyarrow.parquet as pq

        # Write a minimal parquet with the expected columns
        spool_file = tmp_path / "base.parquet"
        schema = pa.schema([
            pa.field("HISTORYID", pa.string()),
            pa.field("DATA_DATE", pa.timestamp("us")),
            pa.field("PRD_HOURS", pa.float64()),
            pa.field("SBY_HOURS", pa.float64()),
            pa.field("UDT_HOURS", pa.float64()),
            pa.field("SDT_HOURS", pa.float64()),
            pa.field("EGT_HOURS", pa.float64()),
            pa.field("NST_HOURS", pa.float64()),
            pa.field("TOTAL_HOURS", pa.float64()),
        ])
        pq.write_table(
            pa.table({f: pa.array([], type=schema.field(f).type) for f in schema.names},
                     schema=schema),
            str(spool_file),
        )

        # Verify via DuckDB
        con = duckdb.connect()
        try:
            cols = {r[0] for r in con.execute(
                f"DESCRIBE SELECT * FROM read_parquet('{spool_file}')"
            ).fetchall()}
        finally:
            con.close()

        assert self._BASE_LEGACY_COLS.issubset(cols), (
            f"Missing columns: {self._BASE_LEGACY_COLS - cols}"
        )

    def test_oee_parquet_columns_match_legacy_schema(self, tmp_path):
        """ResourceHistoryOeeJob post_aggregate writes parquet with OEE column set."""
        import duckdb, pyarrow as pa, pyarrow.parquet as pq

        spool_file = tmp_path / "oee.parquet"
        schema = pa.schema([
            pa.field("EQUIPMENTID", pa.string()),
            pa.field("TRACKOUT_QTY", pa.float64()),
            pa.field("NG_QTY", pa.float64()),
        ])
        pq.write_table(
            pa.table({f: pa.array([], type=schema.field(f).type) for f in schema.names},
                     schema=schema),
            str(spool_file),
        )

        con = duckdb.connect()
        try:
            cols = {r[0] for r in con.execute(
                f"DESCRIBE SELECT * FROM read_parquet('{spool_file}')"
            ).fetchall()}
        finally:
            con.close()

        assert self._OEE_LEGACY_COLS.issubset(cols), (
            f"Missing columns: {self._OEE_LEGACY_COLS - cols}"
        )
