# -*- coding: utf-8 -*-
"""Unit tests for ProductionAchievementJob (BaseChunkedDuckDBJob unified path,
production-achievement-async-spool).

Covers AC-1 (TIME chunk construction, no direct read_sql_df), AC-4
(always_async registration, no manual heavy_query_slot re-acquire), AC-6
(SPECNAME-grain spool schema + _SCHEMA_VERSION), and AC-7 -- the
chunk-seam re-aggregation test is the HIGHEST-VALUE test in this file:
PA-03/PA-04's previous-day shift-tail attribution rule means a single
(output_date, shift_code, SPECNAME) group can draw TRACKOUTTIMESTAMP rows
from BOTH sides of a calendar-midnight TIME-chunk boundary; post_aggregate
MUST re-aggregate (GROUP BY ... SUM(...)) across all chunk parquets, not
plain-concat, or the spool would silently contain duplicate keys.

All tests are pure-unit; no Oracle connection required (mirrors
tests/test_resource_history_unified_job.py / tests/test_base_chunked_duckdb_job.py).
"""
from __future__ import annotations

import importlib
from datetime import date
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

_REPO_ROOT = Path(__file__).parent.parent
_WORKER_SRC_PATH = _REPO_ROOT / "src/mes_dashboard/workers/production_achievement_worker.py"


def _make_job(job_id: str = "test-pa-001", params: dict | None = None):
    from mes_dashboard.workers.production_achievement_worker import ProductionAchievementJob
    return ProductionAchievementJob(
        job_id=job_id,
        params=params or {"start_date": "2024-03-01", "end_date": "2024-03-02"},
    )


def _write_chunk_parquet(chunk_dir: Path, name: str, rows: list[dict]) -> None:
    """Write a fake per-chunk parquet using the RAW Oracle-cursor column
    names (SHIFT_CODE, OUTPUT_DATE, SPECNAME, ACTUAL_OUTPUT_QTY) that
    OracleArrowReader/production_achievement.sql would actually produce."""
    table = pa.table({
        "OUTPUT_DATE": pa.array([r["OUTPUT_DATE"] for r in rows], type=pa.date32()),
        "SHIFT_CODE": pa.array([r["SHIFT_CODE"] for r in rows], type=pa.string()),
        "SPECNAME": pa.array([r["SPECNAME"] for r in rows], type=pa.string()),
        "ACTUAL_OUTPUT_QTY": pa.array([r["ACTUAL_OUTPUT_QTY"] for r in rows], type=pa.int64()),
    })
    pq.write_table(table, str(chunk_dir / name))


# ---------------------------------------------------------------------------
# TestProductionAchievementJob (AC-1, AC-4)
# ---------------------------------------------------------------------------

class TestProductionAchievementJob:
    def test_namespace_is_production_achievement(self):
        from mes_dashboard.workers.production_achievement_worker import ProductionAchievementJob
        assert ProductionAchievementJob.namespace == "production_achievement"

    def test_chunk_strategy_is_time(self):
        from mes_dashboard.workers.production_achievement_worker import ProductionAchievementJob
        from mes_dashboard.core.base_chunked_duckdb_job import ChunkStrategy
        assert ProductionAchievementJob.chunk_strategy == ChunkStrategy.TIME

    def test_requires_cross_chunk_reduction_is_false(self):
        """AC-1: multi-parquet append path (chunk-seam correctness lives in
        post_aggregate's re-aggregation, not requires_cross_chunk_reduction=True)."""
        from mes_dashboard.workers.production_achievement_worker import ProductionAchievementJob
        assert ProductionAchievementJob.requires_cross_chunk_reduction is False

    def test_pre_query_builds_time_chunks_no_direct_read_sql_df(self):
        """AC-1: pre_query builds one daily TIME chunk per day in range;
        the worker module must never call read_sql_df directly (Oracle
        access goes exclusively through BaseChunkedDuckDBJob's
        OracleArrowReader fan-out)."""
        job = _make_job(params={"start_date": "2024-03-01", "end_date": "2024-03-03"})
        job.pre_query()

        assert len(job._chunks) == 3
        assert job._chunks[0] == {"start_date": "2024-03-01", "chunk_end_excl": "2024-03-02"}
        assert job._chunks[1] == {"start_date": "2024-03-02", "chunk_end_excl": "2024-03-03"}
        assert job._chunks[2] == {"start_date": "2024-03-03", "chunk_end_excl": "2024-03-04"}
        assert job._spool_key
        assert job._spool_path.endswith(f"{job._spool_key}.parquet")

        worker_src = _WORKER_SRC_PATH.read_text(encoding="utf-8")
        assert "read_sql_df" not in worker_src, (
            "production_achievement_worker.py must not call read_sql_df directly "
            "-- Oracle access must go through OracleArrowReader via BaseChunkedDuckDBJob"
        )

    def test_pre_query_spool_key_matches_service_canonical_helper(self):
        """AC-1/IP-2: the worker's spool key must equal the route's canonical
        helper output for the identical date range (shared spool-key resolution)."""
        from mes_dashboard.services.production_achievement_service import (
            make_canonical_pa_spool_id,
        )
        job = _make_job(params={"start_date": "2024-03-01", "end_date": "2024-03-02"})
        job.pre_query()
        assert job._spool_key == make_canonical_pa_spool_id("2024-03-01", "2024-03-02")

    def test_build_chunk_sql_binds_start_date_and_chunk_end_excl(self):
        """AC-1: build_chunk_sql binds :start_date/:chunk_end_excl per chunk."""
        job = _make_job()
        sql, params = job.build_chunk_sql(
            {"start_date": "2024-03-01", "chunk_end_excl": "2024-03-02"}
        )
        assert "CONTAINERNAME_FILTER" not in sql  # placeholder substituted (empty string)
        assert params["start_date"] == "2024-03-01"
        assert params["chunk_end_excl"] == "2024-03-02"

    def test_always_async_registered(self):
        """AC-4: production-achievement is registered with always_async=True."""
        import mes_dashboard.workers.production_achievement_worker as _w
        importlib.reload(_w)
        from mes_dashboard.services.job_registry import get_job_type_config
        config = get_job_type_config("production-achievement")
        assert config is not None
        assert config.always_async is True

    def test_no_manual_heavy_query_slot_acquire_in_worker_source(self):
        """AC-4: heavy_query_slot is inherited from BaseChunkedDuckDBJob.run()
        -- the worker must NOT manually re-acquire it (gotcha, implementation-plan.md)."""
        worker_src = _WORKER_SRC_PATH.read_text(encoding="utf-8")
        assert "acquire_heavy_query_slot" not in worker_src
        assert "heavy_query_slot(" not in worker_src


# ---------------------------------------------------------------------------
# TestChunkSeamReaggregation (AC-7 -- KEY test)
# ---------------------------------------------------------------------------

class TestChunkSeamReaggregation:
    """PA-03/PA-04 previous-day shift-tail attribution: a single
    (output_date, shift_code, SPECNAME) group can draw TRACKOUTTIMESTAMP rows
    from BOTH sides of a calendar-midnight TIME-chunk boundary. post_aggregate
    must SUM-merge these into exactly one row per key, not duplicate them."""

    def test_midnight_seam_group_produces_one_row_not_duplicate_keys(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DUCKDB_JOB_DIR", str(tmp_path / "duckdb_jobs"))

        job = _make_job(job_id="seam-test-001")
        job._spool_key = "seam-test-key"
        job._spool_path = str(tmp_path / "spool" / "seam-test-key.parquet")

        chunk_dir = job._make_chunk_parquet_dir(job.job_id)

        # Chunk 1 (day D-1, e.g. 2024-03-04): server-side GROUP BY already
        # summed same-chunk rows for the N-shift evening portion of
        # (output_date=2024-03-04, shift_code=N, SPECNAME=Epoxy D/B).
        _write_chunk_parquet(chunk_dir, "chunk-0000-0000.parquet", [
            {"OUTPUT_DATE": date(2024, 3, 4), "SHIFT_CODE": "N", "SPECNAME": "Epoxy D/B", "ACTUAL_OUTPUT_QTY": 100},
        ])
        # Chunk 2 (day D, 2024-03-05): the N-shift's pre-07:30 tail on the
        # NEXT calendar day still attributes to output_date=2024-03-04
        # (PA-03), but its TRACKOUTTIMESTAMP falls inside chunk-2's
        # [2024-03-05, 2024-03-06) window -- the seam this test tripwires.
        _write_chunk_parquet(chunk_dir, "chunk-0001-0000.parquet", [
            {"OUTPUT_DATE": date(2024, 3, 4), "SHIFT_CODE": "N", "SPECNAME": "Epoxy D/B", "ACTUAL_OUTPUT_QTY": 50},
        ])

        job.post_aggregate(None)

        con = duckdb.connect()
        try:
            rows = con.execute(
                f"SELECT output_date, shift_code, SPECNAME, actual_output_qty "
                f"FROM read_parquet('{job._spool_path}') "
                f"WHERE output_date = DATE '2024-03-04' AND shift_code = 'N' AND SPECNAME = 'Epoxy D/B'"
            ).fetchall()
        finally:
            con.close()

        assert len(rows) == 1, (
            f"Expected exactly ONE row for the seam-straddling key, got {len(rows)}: {rows} "
            "-- plain-concat post_aggregate would emit duplicate keys here (ADR-0016)"
        )
        assert rows[0][3] == 150, f"Expected SUM(actual_output_qty)=150, got {rows[0][3]}"

    def test_post_aggregate_sum_merges_same_key_across_chunks(self, tmp_path, monkeypatch):
        """Distinct keys stay distinct; only the matching key is SUM-merged
        (guards against an over-eager GROUP BY collapsing unrelated rows)."""
        monkeypatch.setenv("DUCKDB_JOB_DIR", str(tmp_path / "duckdb_jobs"))

        job = _make_job(job_id="seam-test-002")
        job._spool_key = "seam-test-key-2"
        job._spool_path = str(tmp_path / "spool" / "seam-test-key-2.parquet")

        chunk_dir = job._make_chunk_parquet_dir(job.job_id)
        _write_chunk_parquet(chunk_dir, "chunk-0000-0000.parquet", [
            {"OUTPUT_DATE": date(2024, 3, 4), "SHIFT_CODE": "N", "SPECNAME": "Epoxy D/B", "ACTUAL_OUTPUT_QTY": 100},
            {"OUTPUT_DATE": date(2024, 3, 4), "SHIFT_CODE": "D", "SPECNAME": "Epoxy D/B", "ACTUAL_OUTPUT_QTY": 20},
        ])
        _write_chunk_parquet(chunk_dir, "chunk-0001-0000.parquet", [
            {"OUTPUT_DATE": date(2024, 3, 4), "SHIFT_CODE": "N", "SPECNAME": "Epoxy D/B", "ACTUAL_OUTPUT_QTY": 50},
            {"OUTPUT_DATE": date(2024, 3, 5), "SHIFT_CODE": "D", "SPECNAME": "金線製程", "ACTUAL_OUTPUT_QTY": 7},
        ])

        job.post_aggregate(None)

        con = duckdb.connect()
        try:
            rows = {
                (r[0], r[1], r[2]): r[3]
                for r in con.execute(
                    f"SELECT output_date, shift_code, SPECNAME, actual_output_qty "
                    f"FROM read_parquet('{job._spool_path}')"
                ).fetchall()
            }
        finally:
            con.close()

        assert len(rows) == 3, f"Expected 3 distinct keys, got {len(rows)}: {rows}"
        assert rows[(date(2024, 3, 4), "N", "Epoxy D/B")] == 150
        assert rows[(date(2024, 3, 4), "D", "Epoxy D/B")] == 20
        assert rows[(date(2024, 3, 5), "D", "金線製程")] == 7


# ---------------------------------------------------------------------------
# TestSpoolSchema (AC-6)
# ---------------------------------------------------------------------------

class TestSpoolSchema:
    def test_parquet_columns_are_output_date_shift_code_specname_actual_output_qty(
        self, tmp_path, monkeypatch
    ):
        """Empty/no-qualifying-rows window still writes a VALID empty parquet
        with the exact data-shape-contract.md §3.28.1 schema."""
        monkeypatch.setenv("DUCKDB_JOB_DIR", str(tmp_path / "duckdb_jobs"))

        job = _make_job(job_id="empty-test-001")
        job._spool_key = "empty-test-key"
        job._spool_path = str(tmp_path / "spool" / "empty-test-key.parquet")

        # No chunk parquets written at all (mirrors zero qualifying Oracle
        # rows across every chunk -- chunk_iter yields nothing).
        job._make_chunk_parquet_dir(job.job_id)

        result_path = job.post_aggregate(None)
        assert result_path == job._spool_path

        con = duckdb.connect()
        try:
            cols = [r[0] for r in con.execute(
                f"DESCRIBE SELECT * FROM read_parquet('{job._spool_path}')"
            ).fetchall()]
            row_count = con.execute(
                f"SELECT COUNT(*) FROM read_parquet('{job._spool_path}')"
            ).fetchone()[0]
        finally:
            con.close()

        assert set(cols) == {"output_date", "shift_code", "SPECNAME", "actual_output_qty"}
        assert row_count == 0

    def test_schema_version_constant_pinned(self):
        """AC-6: _PA_SPOOL_SCHEMA_VERSION participates in the canonical spool
        key (cache-spool-patterns.md) and must be a stable positive integer."""
        from mes_dashboard.services.production_achievement_service import (
            _PA_SPOOL_SCHEMA_VERSION,
        )
        assert isinstance(_PA_SPOOL_SCHEMA_VERSION, int)
        assert _PA_SPOOL_SCHEMA_VERSION >= 1
