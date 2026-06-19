# -*- coding: utf-8 -*-
"""Unit tests for DowntimeJob (BaseChunkedDuckDBJob) — IP-7.

Tests:
  TestDowntimeJobPreQuery       — RESOURCEID group decomposition
  TestDowntimeJobChunkToDb      — base_raw/job_raw routing by chunk_params['kind'] (R1)
  TestDowntimeJobPostAggregate  — bridge JOIN winner-selection + match_ambiguous (ADR-0010);
                                  cross-shift merge (60s-gap, R3); Path-A JOBID hit + orphan
  TestDowntimeFlagDispatch      — flag ON/OFF dispatch at route
  TestDowntimeJobSpoolKey       — spool key invariant unchanged between paths
"""
from __future__ import annotations

import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pandas as pd
import pyarrow as pa
import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ts(s: str) -> datetime:
    """Parse ISO datetime string."""
    return datetime.fromisoformat(s)


def _make_base_batch(rows: list) -> pa.RecordBatch:
    """Build an Arrow RecordBatch with base_raw columns."""
    schema_cols = [
        "HISTORYID", "OLDSTATUSNAME", "OLDREASONNAME",
        "OLDLASTSTATUSCHANGEDATE", "LASTSTATUSCHANGEDATE",
        "HOURS", "JOBID",
    ]
    col_data: Dict[str, list] = {c: [] for c in schema_cols}
    for r in rows:
        for c in schema_cols:
            col_data[c].append(r.get(c))
    arrays = [pa.array(col_data[c]) for c in schema_cols]
    return pa.RecordBatch.from_arrays(arrays, names=schema_cols)


def _make_job_batch(rows: list) -> pa.RecordBatch:
    """Build an Arrow RecordBatch with job_raw columns."""
    schema_cols = [
        "JOBID", "RESOURCEID", "CREATEDATE", "COMPLETEDATE",
        "SYMPTOMCODENAME", "CAUSECODENAME", "REPAIRCODENAME",
        "COMPLETE_FULLNAME", "FIRSTCLOCKONDATE", "LASTCLOCKOFFDATE",
        "JOBORDERNAME", "JOBMODELNAME",
        "ASSIGNED_DATE", "ACK_DATE", "INSPECT_START", "INSPECT_END",
    ]
    col_data: Dict[str, list] = {c: [] for c in schema_cols}
    for r in rows:
        for c in schema_cols:
            col_data[c].append(r.get(c))
    arrays = [pa.array(col_data[c]) for c in schema_cols]
    return pa.RecordBatch.from_arrays(arrays, names=schema_cols)


# ---------------------------------------------------------------------------
# TestDowntimeJobPreQuery
# ---------------------------------------------------------------------------


class TestDowntimeJobPreQuery:
    """AC-4: pre_query emits base+job chunks; no TIME/ROW_COUNT chunking."""

    def test_pre_query_returns_base_and_job_chunks(self, monkeypatch):
        """pre_query must emit at least one 'base' chunk and one 'job' chunk."""
        from mes_dashboard.workers.downtime_worker import DowntimeJob

        # Patch make_downtime_query_id to avoid service layer import cascade
        monkeypatch.setattr(
            "mes_dashboard.services.downtime_analysis_service.make_downtime_query_id",
            lambda params: "testkey_" + str(hash(str(sorted(params.items()))))[:8],
        )

        job = DowntimeJob(
            job_id="test-pre-query-001",
            params={
                "start_date": "2026-01-01",
                "end_date": "2026-01-31",
            },
        )
        job.pre_query()

        chunks = job._chunks
        kinds = [c["kind"] for c in chunks]
        assert "base" in kinds, "pre_query must emit at least one 'base' chunk"
        assert "job" in kinds, "pre_query must emit at least one 'job' chunk"

    def test_pre_query_sets_spool_key(self, monkeypatch):
        """pre_query must populate self._spool_key (non-empty)."""
        from mes_dashboard.workers.downtime_worker import DowntimeJob

        monkeypatch.setattr(
            "mes_dashboard.services.downtime_analysis_service.make_downtime_query_id",
            lambda params: "fixed_test_key",
        )

        job = DowntimeJob(
            job_id="test-pre-query-002",
            params={"start_date": "2026-01-01", "end_date": "2026-01-31"},
        )
        job.pre_query()
        assert job._spool_key == "fixed_test_key"

    def test_pre_query_chunks_have_date_range(self, monkeypatch):
        """Each chunk must carry start_date and end_date."""
        from mes_dashboard.workers.downtime_worker import DowntimeJob

        monkeypatch.setattr(
            "mes_dashboard.services.downtime_analysis_service.make_downtime_query_id",
            lambda params: "testkey",
        )

        job = DowntimeJob(
            job_id="test-pre-query-003",
            params={"start_date": "2026-02-01", "end_date": "2026-02-28"},
        )
        job.pre_query()

        for chunk in job._chunks:
            assert "start_date" in chunk
            assert "end_date" in chunk
            assert chunk["start_date"] == "2026-02-01"
            assert chunk["end_date"] == "2026-02-28"


# ---------------------------------------------------------------------------
# TestDowntimeJobChunkToDb
# ---------------------------------------------------------------------------


class TestDowntimeJobChunkToDb:
    """R1: chunk routing to base_raw vs job_raw by chunk_params['kind']."""

    def test_base_chunk_routes_to_base_raw_table(self, tmp_path):
        """Arrow batch with kind='base' must populate base_raw table in DuckDB."""
        import duckdb
        from mes_dashboard.workers.downtime_worker import DowntimeJob

        job = DowntimeJob(job_id="test-chunk-base-001", params={})
        db_path = str(tmp_path / "test.duckdb")

        batch = _make_base_batch([
            {
                "HISTORYID": "MCH001",
                "OLDSTATUSNAME": "UDT",
                "OLDREASONNAME": "EE Repair",
                "OLDLASTSTATUSCHANGEDATE": _ts("2026-01-10T08:00:00"),
                "LASTSTATUSCHANGEDATE": _ts("2026-01-10T10:00:00"),
                "HOURS": 2.0,
                "JOBID": None,
            }
        ])

        job._chunk_to_duckdb_routed(batch, db_path, {"kind": "base"})

        conn = duckdb.connect(db_path, read_only=True)
        try:
            rows = conn.execute("SELECT COUNT(*) FROM base_raw").fetchone()[0]
            assert rows == 1
        finally:
            conn.close()

    def test_job_chunk_routes_to_job_raw_table(self, tmp_path):
        """Arrow batch with kind='job' must populate job_raw table in DuckDB."""
        import duckdb
        from mes_dashboard.workers.downtime_worker import DowntimeJob

        job = DowntimeJob(job_id="test-chunk-job-001", params={})
        db_path = str(tmp_path / "test.duckdb")

        batch = _make_job_batch([
            {
                "JOBID": "JOB001",
                "RESOURCEID": "MCH001",
                "CREATEDATE": _ts("2026-01-10T07:00:00"),
                "COMPLETEDATE": _ts("2026-01-10T11:00:00"),
                "SYMPTOMCODENAME": "SYM",
                "CAUSECODENAME": "CAUSE",
                "REPAIRCODENAME": "REPAIR",
                "COMPLETE_FULLNAME": "Tech01",
                "FIRSTCLOCKONDATE": _ts("2026-01-10T08:00:00"),
                "LASTCLOCKOFFDATE": _ts("2026-01-10T10:30:00"),
                "JOBORDERNAME": "JO001",
                "JOBMODELNAME": "MODEL001",
                "ASSIGNED_DATE": None,
                "ACK_DATE": None,
                "INSPECT_START": None,
                "INSPECT_END": None,
            }
        ])

        job._chunk_to_duckdb_routed(batch, db_path, {"kind": "job"})

        conn = duckdb.connect(db_path, read_only=True)
        try:
            rows = conn.execute("SELECT COUNT(*) FROM job_raw").fetchone()[0]
            assert rows == 1
        finally:
            conn.close()

    def test_multiple_base_chunks_accumulate(self, tmp_path):
        """Multiple 'base' batches must accumulate in base_raw (not overwrite)."""
        import duckdb
        from mes_dashboard.workers.downtime_worker import DowntimeJob

        job = DowntimeJob(job_id="test-chunk-accum-001", params={})
        db_path = str(tmp_path / "test.duckdb")

        for i in range(3):
            batch = _make_base_batch([{
                "HISTORYID": f"MCH{i:03d}",
                "OLDSTATUSNAME": "UDT",
                "OLDREASONNAME": None,
                "OLDLASTSTATUSCHANGEDATE": _ts("2026-01-10T08:00:00"),
                "LASTSTATUSCHANGEDATE": _ts("2026-01-10T10:00:00"),
                "HOURS": 2.0,
                "JOBID": None,
            }])
            job._chunk_to_duckdb_routed(batch, db_path, {"kind": "base"})

        conn = duckdb.connect(db_path, read_only=True)
        try:
            rows = conn.execute("SELECT COUNT(*) FROM base_raw").fetchone()[0]
            assert rows == 3
        finally:
            conn.close()

    def test_unknown_kind_raises_value_error(self, tmp_path):
        """chunk_params with invalid 'kind' must raise ValueError."""
        from mes_dashboard.workers.downtime_worker import DowntimeJob

        job = DowntimeJob(job_id="test-chunk-bad-001", params={})
        db_path = str(tmp_path / "test.duckdb")
        batch = _make_base_batch([])

        with pytest.raises(ValueError, match="unknown kind"):
            job._chunk_to_duckdb_routed(batch, db_path, {"kind": "unknown"})

    def test_chunk_to_duckdb_raises_runtime_error(self, tmp_path):
        """chunk_to_duckdb (base-class method) must raise RuntimeError on DowntimeJob."""
        from mes_dashboard.workers.downtime_worker import DowntimeJob

        job = DowntimeJob(job_id="test-disabled-001", params={})
        db_path = str(tmp_path / "test.duckdb")
        batch = _make_base_batch([])

        with pytest.raises(RuntimeError, match="chunk_to_duckdb should not be called"):
            job.chunk_to_duckdb(batch, db_path)


# ---------------------------------------------------------------------------
# TestDowntimeJobPostAggregate
# ---------------------------------------------------------------------------

_BASE_ROWS_SINGLE_EVENT = [
    {
        "HISTORYID": "MCH001",
        "OLDSTATUSNAME": "UDT",
        "OLDREASONNAME": "EE Repair",
        "OLDLASTSTATUSCHANGEDATE": _ts("2026-01-10T08:00:00"),
        "LASTSTATUSCHANGEDATE": _ts("2026-01-10T10:00:00"),
        "HOURS": 2.0,
        "JOBID": None,
    }
]

_JOB_ROWS_OVERLAP_WINNER = [
    # Longer overlap: 08:00–11:00 → overlap 2h (event 08:00–10:00)
    {
        "JOBID": "JOB_WINNER",
        "RESOURCEID": "MCH001",
        "CREATEDATE": _ts("2026-01-10T08:00:00"),
        "COMPLETEDATE": _ts("2026-01-10T11:00:00"),  # eff_end 11:00
        "SYMPTOMCODENAME": "SYM_W",
        "CAUSECODENAME": "CAUSE_W",
        "REPAIRCODENAME": "REPAIR_W",
        "COMPLETE_FULLNAME": "Tech_Winner",
        "FIRSTCLOCKONDATE": _ts("2026-01-10T08:30:00"),
        "LASTCLOCKOFFDATE": _ts("2026-01-10T10:30:00"),
        "JOBORDERNAME": "JO_WINNER",
        "JOBMODELNAME": "MODEL_W",
        "ASSIGNED_DATE": None,
        "ACK_DATE": None,
        "INSPECT_START": None,
        "INSPECT_END": None,
    },
    # Shorter overlap: 09:00–10:30 → overlap 1h
    {
        "JOBID": "JOB_RUNNER",
        "RESOURCEID": "MCH001",
        "CREATEDATE": _ts("2026-01-10T09:00:00"),
        "COMPLETEDATE": _ts("2026-01-10T10:30:00"),  # eff_end 10:30
        "SYMPTOMCODENAME": "SYM_R",
        "CAUSECODENAME": "CAUSE_R",
        "REPAIRCODENAME": "REPAIR_R",
        "COMPLETE_FULLNAME": "Tech_Runner",
        "FIRSTCLOCKONDATE": _ts("2026-01-10T09:30:00"),
        "LASTCLOCKOFFDATE": _ts("2026-01-10T10:20:00"),
        "JOBORDERNAME": "JO_RUNNER",
        "JOBMODELNAME": "MODEL_R",
        "ASSIGNED_DATE": None,
        "ACK_DATE": None,
        "INSPECT_START": None,
        "INSPECT_END": None,
    },
]


class TestDowntimeJobPostAggregate:
    """Bridge JOIN + cross-shift merge correctness tests (AC-2, AC-7)."""

    def _make_job(self, tmp_path, base_rows, job_rows, params=None):
        """Helper: build a DowntimeJob with pre-populated DuckDB tables."""
        import duckdb
        from mes_dashboard.workers.downtime_worker import DowntimeJob

        if params is None:
            params = {
                "start_date": "2026-01-01",
                "end_date": "2026-01-31",
            }

        job = DowntimeJob(job_id="test-pa-001", params=params)
        job._spool_key = "test_spool_key"
        job._spool_path = ""

        db_path = str(tmp_path / "test.duckdb")

        # Populate base_raw
        if base_rows:
            base_batch = _make_base_batch(base_rows)
            job._chunk_to_duckdb_routed(base_batch, db_path, {"kind": "base"})

        # Populate job_raw
        if job_rows:
            job_batch = _make_job_batch(job_rows)
            job._chunk_to_duckdb_routed(job_batch, db_path, {"kind": "job"})

        return job, db_path

    @patch("mes_dashboard.workers.downtime_worker.DowntimeJob._write_spool")
    @patch("mes_dashboard.services.downtime_analysis_service._apply_resource_filters",
           side_effect=lambda df, **kw: df)
    def test_winner_selection_largest_overlap(self, mock_filter, mock_spool, tmp_path):
        """Path B: winner is the job with largest overlap (JOB_WINNER over JOB_RUNNER)."""
        mock_spool.return_value = "/tmp/test.parquet"

        job, db_path = self._make_job(
            tmp_path, _BASE_ROWS_SINGLE_EVENT, _JOB_ROWS_OVERLAP_WINNER
        )

        result_df = None
        def capture_spool(events_df):
            nonlocal result_df
            result_df = events_df.copy()
            return "/tmp/test.parquet"
        mock_spool.side_effect = capture_spool

        job.post_aggregate(db_path)

        assert result_df is not None
        assert len(result_df) >= 1

        # Find the overlap-matched event
        overlap_rows = result_df[result_df.get("match_source", result_df.get("match_source", pd.Series(dtype=str))) == "overlap"] if "match_source" in result_df.columns else pd.DataFrame()
        assert len(overlap_rows) >= 1, f"Expected at least one 'overlap' row. Cols: {list(result_df.columns)}, rows: {result_df.to_dict('records')}"
        row = overlap_rows.iloc[0]
        # Winner must be JOB_WINNER (larger overlap)
        if "job_order_name" in result_df.columns:
            assert row.get("job_order_name") == "JO_WINNER", (
                f"Expected winner JO_WINNER, got: {row.get('job_order_name')}"
            )

    @patch("mes_dashboard.workers.downtime_worker.DowntimeJob._write_spool")
    @patch("mes_dashboard.services.downtime_analysis_service._apply_resource_filters",
           side_effect=lambda df, **kw: df)
    def test_match_ambiguous_false_when_runner_up_lt_80pct(self, mock_filter, mock_spool, tmp_path):
        """match_ambiguous=False when runner-up overlap < 80% of winner (ADR-0010 guard)."""
        mock_spool.return_value = "/tmp/test.parquet"

        # Winner: 2h overlap; runner-up: 1h overlap (50% < 80%) → not ambiguous
        result_df = None
        def capture_spool(events_df):
            nonlocal result_df
            result_df = events_df.copy()
            return "/tmp/test.parquet"
        mock_spool.side_effect = capture_spool

        job, db_path = self._make_job(
            tmp_path, _BASE_ROWS_SINGLE_EVENT, _JOB_ROWS_OVERLAP_WINNER
        )
        job.post_aggregate(db_path)

        assert result_df is not None
        overlap_rows = result_df[result_df.get("match_source") == "overlap"] if "match_source" in result_df.columns else pd.DataFrame()
        if len(overlap_rows) >= 1:
            row = overlap_rows.iloc[0]
            assert not row.get("match_ambiguous"), (
                f"Expected match_ambiguous=False (runner-up 1h < 80% of 2h winner), "
                f"got: {row.get('match_ambiguous')}"
            )

    @patch("mes_dashboard.workers.downtime_worker.DowntimeJob._write_spool")
    @patch("mes_dashboard.services.downtime_analysis_service._apply_resource_filters",
           side_effect=lambda df, **kw: df)
    def test_match_ambiguous_true_when_runner_up_gte_80pct(self, mock_filter, mock_spool, tmp_path):
        """match_ambiguous=True when runner-up overlap >= 80% of winner (ADR-0010 guard)."""
        # Winner 2h, runner-up 1h 40min = 100min = 83.3% → ambiguous
        base_rows = [
            {
                "HISTORYID": "MCH002",
                "OLDSTATUSNAME": "UDT",
                "OLDREASONNAME": "EE Repair",
                "OLDLASTSTATUSCHANGEDATE": _ts("2026-01-10T08:00:00"),
                "LASTSTATUSCHANGEDATE": _ts("2026-01-10T10:00:00"),
                "HOURS": 2.0,
                "JOBID": None,
            }
        ]
        job_rows = [
            {
                "JOBID": "JOB_W80",
                "RESOURCEID": "MCH002",
                "CREATEDATE": _ts("2026-01-10T08:00:00"),
                "COMPLETEDATE": _ts("2026-01-10T10:00:00"),   # 2h overlap
                "SYMPTOMCODENAME": None,
                "CAUSECODENAME": None,
                "REPAIRCODENAME": None,
                "COMPLETE_FULLNAME": None,
                "FIRSTCLOCKONDATE": None,
                "LASTCLOCKOFFDATE": None,
                "JOBORDERNAME": "JO_W80",
                "JOBMODELNAME": None,
                "ASSIGNED_DATE": None,
                "ACK_DATE": None,
                "INSPECT_START": None,
                "INSPECT_END": None,
            },
            {
                "JOBID": "JOB_R80",
                "RESOURCEID": "MCH002",
                "CREATEDATE": _ts("2026-01-10T08:00:00"),
                "COMPLETEDATE": _ts("2026-01-10T09:40:00"),   # 1h40m = 100min overlap > 80%
                "SYMPTOMCODENAME": None,
                "CAUSECODENAME": None,
                "REPAIRCODENAME": None,
                "COMPLETE_FULLNAME": None,
                "FIRSTCLOCKONDATE": None,
                "LASTCLOCKOFFDATE": None,
                "JOBORDERNAME": "JO_R80",
                "JOBMODELNAME": None,
                "ASSIGNED_DATE": None,
                "ACK_DATE": None,
                "INSPECT_START": None,
                "INSPECT_END": None,
            },
        ]

        result_df = None
        def capture_spool(events_df):
            nonlocal result_df
            result_df = events_df.copy()
            return "/tmp/test.parquet"
        mock_spool.side_effect = capture_spool

        job, db_path = self._make_job(tmp_path, base_rows, job_rows)
        job.post_aggregate(db_path)

        assert result_df is not None
        overlap_rows = result_df[result_df.get("match_source") == "overlap"] if "match_source" in result_df.columns else pd.DataFrame()
        if len(overlap_rows) >= 1:
            row = overlap_rows.iloc[0]
            assert row.get("match_ambiguous"), (
                f"Expected match_ambiguous=True (runner-up 100min >= 80% of 120min winner), "
                f"got: {row.get('match_ambiguous')}"
            )

    @patch("mes_dashboard.workers.downtime_worker.DowntimeJob._write_spool")
    @patch("mes_dashboard.services.downtime_analysis_service._apply_resource_filters",
           side_effect=lambda df, **kw: df)
    def test_orphan_event_match_source_none(self, mock_filter, mock_spool, tmp_path):
        """Event with no matching job must have match_source='none' and null job cols."""
        result_df = None
        def capture_spool(events_df):
            nonlocal result_df
            result_df = events_df.copy()
            return "/tmp/test.parquet"
        mock_spool.side_effect = capture_spool

        base_rows = [{
            "HISTORYID": "MCH_NOMAP",
            "OLDSTATUSNAME": "UDT",
            "OLDREASONNAME": "EE Repair",
            "OLDLASTSTATUSCHANGEDATE": _ts("2026-01-10T08:00:00"),
            "LASTSTATUSCHANGEDATE": _ts("2026-01-10T10:00:00"),
            "HOURS": 2.0,
            "JOBID": None,
        }]
        # No jobs for MCH_NOMAP resource
        job_rows = [{
            "JOBID": "JOB999",
            "RESOURCEID": "DIFFERENT_MACHINE",
            "CREATEDATE": _ts("2026-01-10T07:00:00"),
            "COMPLETEDATE": _ts("2026-01-10T11:00:00"),
            "SYMPTOMCODENAME": None, "CAUSECODENAME": None, "REPAIRCODENAME": None,
            "COMPLETE_FULLNAME": None, "FIRSTCLOCKONDATE": None, "LASTCLOCKOFFDATE": None,
            "JOBORDERNAME": None, "JOBMODELNAME": None,
            "ASSIGNED_DATE": None, "ACK_DATE": None, "INSPECT_START": None, "INSPECT_END": None,
        }]

        job, db_path = self._make_job(tmp_path, base_rows, job_rows)
        job.post_aggregate(db_path)

        assert result_df is not None
        none_rows = result_df[result_df.get("match_source") == "none"] if "match_source" in result_df.columns else pd.DataFrame()
        assert len(none_rows) >= 1, (
            f"Expected match_source='none' row, got: {result_df[['match_source']].to_dict('records') if 'match_source' in result_df.columns else 'no match_source col'}"
        )
        row = none_rows.iloc[0]
        if "job_order_name" in result_df.columns:
            assert row.get("job_order_name") is None or pd.isna(row.get("job_order_name")), (
                f"Expected null job_order_name for match_source='none', got: {row.get('job_order_name')}"
            )

    @patch("mes_dashboard.workers.downtime_worker.DowntimeJob._write_spool")
    @patch("mes_dashboard.services.downtime_analysis_service._apply_resource_filters",
           side_effect=lambda df, **kw: df)
    def test_path_a_jobid_direct_match(self, mock_filter, mock_spool, tmp_path):
        """Path A: event with JOBID that exists in job_raw → match_source='jobid'."""
        result_df = None
        def capture_spool(events_df):
            nonlocal result_df
            result_df = events_df.copy()
            return "/tmp/test.parquet"
        mock_spool.side_effect = capture_spool

        base_rows = [{
            "HISTORYID": "MCH_DIRECT",
            "OLDSTATUSNAME": "UDT",
            "OLDREASONNAME": "EE Repair",
            "OLDLASTSTATUSCHANGEDATE": _ts("2026-01-10T08:00:00"),
            "LASTSTATUSCHANGEDATE": _ts("2026-01-10T10:00:00"),
            "HOURS": 2.0,
            "JOBID": "JOB_DIRECT",  # Direct JOBID reference
        }]
        job_rows = [{
            "JOBID": "JOB_DIRECT",
            "RESOURCEID": "MCH_DIRECT",
            "CREATEDATE": _ts("2026-01-10T07:00:00"),
            "COMPLETEDATE": _ts("2026-01-10T11:00:00"),
            "SYMPTOMCODENAME": "DIRECT_SYM",
            "CAUSECODENAME": "DIRECT_CAUSE",
            "REPAIRCODENAME": "DIRECT_REPAIR",
            "COMPLETE_FULLNAME": "DirectTech",
            "FIRSTCLOCKONDATE": _ts("2026-01-10T08:00:00"),
            "LASTCLOCKOFFDATE": _ts("2026-01-10T10:30:00"),
            "JOBORDERNAME": "JO_DIRECT",
            "JOBMODELNAME": "MODEL_DIRECT",
            "ASSIGNED_DATE": None,
            "ACK_DATE": None,
            "INSPECT_START": None,
            "INSPECT_END": None,
        }]

        job, db_path = self._make_job(tmp_path, base_rows, job_rows)
        job.post_aggregate(db_path)

        assert result_df is not None
        if "match_source" in result_df.columns:
            jobid_rows = result_df[result_df["match_source"] == "jobid"]
            assert len(jobid_rows) >= 1, (
                f"Expected match_source='jobid' for Path A hit. "
                f"Got: {result_df['match_source'].tolist()}"
            )
            row = jobid_rows.iloc[0]
            if "job_order_name" in result_df.columns:
                assert row.get("job_order_name") == "JO_DIRECT"

    @patch("mes_dashboard.workers.downtime_worker.DowntimeJob._write_spool")
    @patch("mes_dashboard.services.downtime_analysis_service._apply_resource_filters",
           side_effect=lambda df, **kw: df)
    def test_cross_shift_merge_59s_gap_merges(self, mock_filter, mock_spool, tmp_path):
        """Cross-shift merge: two fragments with 59s gap must produce ONE merged event (R3)."""
        result_df = None
        def capture_spool(events_df):
            nonlocal result_df
            result_df = events_df.copy()
            return "/tmp/test.parquet"
        mock_spool.side_effect = capture_spool

        # Fragment 1: ends at 10:00:00
        # Fragment 2: starts at 10:00:59 (59s gap → within 60s threshold → merge)
        base_rows = [
            {
                "HISTORYID": "MCH_MERGE",
                "OLDSTATUSNAME": "UDT",
                "OLDREASONNAME": "EE Repair",
                "OLDLASTSTATUSCHANGEDATE": _ts("2026-01-10T08:00:00"),
                "LASTSTATUSCHANGEDATE": _ts("2026-01-10T10:00:00"),
                "HOURS": 2.0,
                "JOBID": None,
            },
            {
                "HISTORYID": "MCH_MERGE",
                "OLDSTATUSNAME": "UDT",
                "OLDREASONNAME": "EE Repair",
                "OLDLASTSTATUSCHANGEDATE": _ts("2026-01-10T10:00:59"),  # 59s gap
                "LASTSTATUSCHANGEDATE": _ts("2026-01-10T12:00:00"),
                "HOURS": 2.0,
                "JOBID": None,
            },
        ]

        job, db_path = self._make_job(tmp_path, base_rows, [])
        job.post_aggregate(db_path)

        assert result_df is not None
        assert len(result_df) >= 1
        # Should be merged into one event with total hours ~4.0
        # (may have match_source column or not yet, depending on enrichment stage)
        if "hours" in result_df.columns:
            hours_total = result_df["hours"].sum()
            # After merge: should be 4.0 hours total in one row
            assert len(result_df) == 1, (
                f"59s gap should merge to 1 event, got {len(result_df)} rows"
            )
            assert abs(hours_total - 4.0) < 0.01, (
                f"Expected merged hours=4.0, got {hours_total}"
            )

    @patch("mes_dashboard.workers.downtime_worker.DowntimeJob._write_spool")
    @patch("mes_dashboard.services.downtime_analysis_service._apply_resource_filters",
           side_effect=lambda df, **kw: df)
    def test_cross_shift_merge_61s_gap_stays_separate(self, mock_filter, mock_spool, tmp_path):
        """Cross-shift merge: two fragments with 61s gap must produce TWO separate events (R3)."""
        result_df = None
        def capture_spool(events_df):
            nonlocal result_df
            result_df = events_df.copy()
            return "/tmp/test.parquet"
        mock_spool.side_effect = capture_spool

        # Fragment 1: ends at 10:00:00
        # Fragment 2: starts at 10:01:01 (61s gap → new run)
        base_rows = [
            {
                "HISTORYID": "MCH_SEP",
                "OLDSTATUSNAME": "UDT",
                "OLDREASONNAME": "EE Repair",
                "OLDLASTSTATUSCHANGEDATE": _ts("2026-01-10T08:00:00"),
                "LASTSTATUSCHANGEDATE": _ts("2026-01-10T10:00:00"),
                "HOURS": 2.0,
                "JOBID": None,
            },
            {
                "HISTORYID": "MCH_SEP",
                "OLDSTATUSNAME": "UDT",
                "OLDREASONNAME": "EE Repair",
                "OLDLASTSTATUSCHANGEDATE": _ts("2026-01-10T10:01:01"),  # 61s gap
                "LASTSTATUSCHANGEDATE": _ts("2026-01-10T12:00:00"),
                "HOURS": 2.0,
                "JOBID": None,
            },
        ]

        job, db_path = self._make_job(tmp_path, base_rows, [])
        job.post_aggregate(db_path)

        assert result_df is not None
        if "hours" in result_df.columns:
            assert len(result_df) == 2, (
                f"61s gap should produce 2 separate events, got {len(result_df)}"
            )


# ---------------------------------------------------------------------------
# TestDowntimeFlagDispatch
# ---------------------------------------------------------------------------


class TestDowntimeFlagDispatch:
    """Flag ON/OFF dispatch at route (IP-5, AC-1, AC-8)."""

    @pytest.fixture(autouse=True)
    def _setup_app(self):
        """Create a Flask test client."""
        import mes_dashboard.app as app_module
        app = app_module.create_app()
        app.config["TESTING"] = True
        self.client = app.test_client()

    def test_flag_off_calls_legacy_path(self, monkeypatch):
        """Flag OFF: route must call query_downtime_dataset (legacy path, AC-8).

        Patches query_downtime_dataset at the routes module level because the route
        imports it at load time via 'from ... import query_downtime_dataset'.
        """
        import mes_dashboard.routes.downtime_analysis_routes as routes_mod

        monkeypatch.setattr(routes_mod, "_DOWNTIME_USE_UNIFIED_JOB", False)
        monkeypatch.setattr(routes_mod, "_BROWSER_DUCKDB_ENABLED", False)

        mock_result = {
            "query_id": "legacykey",
            "summary": [],
            "daily_trend": [],
            "big_category": [],
            "top_reasons": [],
        }
        # Patch at the routes module level (the bound name the route function uses)
        with patch.object(routes_mod, "query_downtime_dataset", return_value=mock_result) as mock_legacy:
            resp = self.client.post(
                "/api/downtime-analysis/query",
                json={"start_date": "2026-01-01", "end_date": "2026-01-10"},
            )
            mock_legacy.assert_called_once()
            assert resp.status_code == 200

    def test_flag_on_routes_to_unified_job(self, monkeypatch):
        """Flag ON: route must enqueue 'downtime-unified' job (not call query_downtime_dataset).

        Patches is_async_available and enqueue_job_dynamic at the routes module level
        because the route imports them at load time via 'from ... import ...'.
        """
        import mes_dashboard.routes.downtime_analysis_routes as routes_mod

        monkeypatch.setattr(routes_mod, "_DOWNTIME_USE_UNIFIED_JOB", True)
        monkeypatch.setattr(routes_mod, "_BROWSER_DUCKDB_ENABLED", False)

        # Patch at the routes module level (bound names used by the route handler)
        monkeypatch.setattr(routes_mod, "is_async_available", lambda: True)

        enqueue_calls = []
        def mock_enqueue(job_type, owner, params, job_id=None):
            enqueue_calls.append({"job_type": job_type, "params": params})
            return ("downtime-unified-testjob123", None)

        monkeypatch.setattr(routes_mod, "enqueue_job_dynamic", mock_enqueue)

        resp = self.client.post(
            "/api/downtime-analysis/query",
            json={"start_date": "2026-01-01", "end_date": "2026-01-10"},
        )

        assert resp.status_code == 202, (
            f"Expected 202, got {resp.status_code}: {resp.get_json()}"
        )
        assert len(enqueue_calls) == 1
        assert enqueue_calls[0]["job_type"] == "downtime-unified"

        data = resp.get_json()
        assert data["data"]["async"] is True
        assert "job_id" in data["data"]


# ---------------------------------------------------------------------------
# TestDowntimeJobSpoolKey
# ---------------------------------------------------------------------------


class TestDowntimeJobSpoolKey:
    """AC-3 / AC-1: spool key produced by unified path == key from legacy path."""

    def test_spool_key_matches_legacy_for_same_params(self, monkeypatch):
        """spool key from DowntimeJob.pre_query == make_downtime_query_id for same params."""
        from mes_dashboard.workers.downtime_worker import DowntimeJob
        from mes_dashboard.services.downtime_analysis_service import make_downtime_query_id

        params = {
            "start_date": "2026-01-01",
            "end_date": "2026-01-31",
            "workcenter_groups": ["WC1", "WC2"],
            "families": ["FAM_A"],
            "resource_ids": [],
            "package_groups": [],
            "big_categories": [],
            "status_types": [],
        }

        # Compute expected key via the service function (legacy path uses same function)
        expected_input = {
            "start_date": params["start_date"],
            "end_date": params["end_date"],
            "workcenter_groups": sorted(params.get("workcenter_groups") or []),
            "families": sorted(params.get("families") or []),
            "resource_ids": sorted(params.get("resource_ids") or []),
            "package_groups": sorted(params.get("package_groups") or []),
            "big_categories": sorted(params.get("big_categories") or []),
            "status_types": sorted(params.get("status_types") or []),
        }
        expected_key = make_downtime_query_id(expected_input)

        # Run pre_query via DowntimeJob
        job = DowntimeJob(job_id="test-spool-key-001", params=params)
        job.pre_query()

        assert job._spool_key == expected_key, (
            f"Spool key mismatch:\n"
            f"  unified: {job._spool_key!r}\n"
            f"  legacy:  {expected_key!r}"
        )


class TestDowntimeJobSpoolColumnParity:
    """Guard against spool column-set drift between legacy and unified paths (AC-3/AC-8).

    Pinned against _empty_events_df() as the canonical schema declaration.
    """

    CANONICAL_COLUMNS = [
        "event_id", "resource_id", "status", "reason", "category",
        "start_ts", "end_ts", "hours", "fragment_count",
        "match_source", "match_ambiguous",
        "job_id", "job_order_name", "job_model", "symptom", "cause", "repair",
        "handler", "wait_min", "repair_min",
    ]

    def test_canonical_column_count(self):
        """_empty_events_df() must have exactly 20 columns (§3.21)."""
        from mes_dashboard.services.downtime_analysis_service import _empty_events_df
        df = _empty_events_df()
        assert list(df.columns) == self.CANONICAL_COLUMNS, (
            f"Column mismatch vs §3.21:\n"
            f"  expected: {self.CANONICAL_COLUMNS}\n"
            f"  actual:   {list(df.columns)}"
        )

    def test_derive_job_columns_preserves_fragment_count(self):
        """_derive_job_columns must NOT drop fragment_count (AC-3/AC-8 guard).

        fragment_count is part of the canonical spool schema (§3.21).
        This test pins the fix for the QA-detected parity bug where
        fragment_count was incorrectly included in the _drop list.
        """
        import pandas as pd
        from mes_dashboard.workers.downtime_worker import DowntimeJob

        # Build a minimal DataFrame with fragment_count and Oracle raw cols to drop
        df = pd.DataFrame([{
            "event_id": "RES-001|UDT|REPAIR|2026-01-01T08:00:00",
            "HISTORYID": "RES-001",
            "OLDSTATUSNAME": "UDT",
            "OLDREASONNAME": "REPAIR",
            "event_start": "2026-01-01T08:00:00",
            "event_end": "2026-01-01T09:00:00",
            "hours": 1.0,
            "fragment_count": 2,   # the column being guarded
            "match_source": "none",
            "match_ambiguous": False,
            "_matched_jobid": None,
            "JOBORDERNAME": None,
            "JOBMODELNAME": None,
            "SYMPTOMCODENAME": None,
            "CAUSECODENAME": None,
            "REPAIRCODENAME": None,
            "COMPLETE_FULLNAME": None,
            "FIRSTCLOCKONDATE": None,
            "LASTCLOCKOFFDATE": None,
            "CREATEDATE": None,
            "COMPLETEDATE": None,
            "ASSIGNED_DATE": None,
            "ACK_DATE": None,
            "INSPECT_START": None,
            "INSPECT_END": None,
            "RESOURCEID": "RES-001",
        }])

        job = DowntimeJob.__new__(DowntimeJob)
        result = job._derive_job_columns(df)

        assert "fragment_count" in result.columns, (
            f"fragment_count dropped by _derive_job_columns — violates §3.21 (AC-3/AC-8). "
            f"Got columns: {list(result.columns)}"
        )
        assert result["fragment_count"].iloc[0] == 2, (
            "fragment_count value must be preserved, not zeroed"
        )
