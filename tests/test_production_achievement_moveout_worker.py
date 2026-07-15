# -*- coding: utf-8 -*-
"""Unit tests for the 轉出 (move-out) worker (production-achievement-moveout,
business-rules.md PA-18). Mirrors test_production_achievement_unified_job.py's
structure for the 產出 worker, but the spool grain is
(output_date, shift_code, raw_workcenter_group, PACKAGE_LF) -- raw_workcenter_group
(FROMWORKCENTER) instead of SPECNAME -- and the canonical spool key uses
source='moveout'.
"""

from __future__ import annotations

import importlib
from datetime import date
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

_REPO_ROOT = Path(__file__).parent.parent
_WORKER_SRC_PATH = _REPO_ROOT / "src/mes_dashboard/workers/production_achievement_moveout_worker.py"


def _make_job(job_id: str = "test-pa-mo-001", params: dict | None = None):
    from mes_dashboard.workers.production_achievement_moveout_worker import (
        ProductionAchievementMoveoutJob,
    )
    return ProductionAchievementMoveoutJob(
        job_id=job_id,
        params=params or {"start_date": "2024-03-01", "end_date": "2024-03-02"},
    )


def _write_chunk_parquet(chunk_dir: Path, name: str, rows: list[dict]) -> None:
    """Write a fake per-chunk parquet using the RAW Oracle-cursor column names
    the moveout SQL produces: OUTPUT_DATE, SHIFT_CODE, RAW_WORKCENTER_GROUP,
    PACKAGE_LF, ACTUAL_OUTPUT_QTY."""
    table = pa.table({
        "OUTPUT_DATE": pa.array([r["OUTPUT_DATE"] for r in rows], type=pa.date32()),
        "SHIFT_CODE": pa.array([r["SHIFT_CODE"] for r in rows], type=pa.string()),
        "RAW_WORKCENTER_GROUP": pa.array([r["RAW_WORKCENTER_GROUP"] for r in rows], type=pa.string()),
        "PACKAGE_LF": pa.array([r.get("PACKAGE_LF") for r in rows], type=pa.string()),
        "ACTUAL_OUTPUT_QTY": pa.array([r["ACTUAL_OUTPUT_QTY"] for r in rows], type=pa.int64()),
    })
    pq.write_table(table, str(chunk_dir / name))


class TestProductionAchievementMoveoutJob:
    def test_namespace_is_production_achievement_moveout(self):
        from mes_dashboard.workers.production_achievement_moveout_worker import (
            ProductionAchievementMoveoutJob,
        )
        assert ProductionAchievementMoveoutJob.namespace == "production_achievement_moveout"

    def test_chunk_strategy_is_time(self):
        from mes_dashboard.workers.production_achievement_moveout_worker import (
            ProductionAchievementMoveoutJob,
        )
        from mes_dashboard.core.base_chunked_duckdb_job import ChunkStrategy
        assert ProductionAchievementMoveoutJob.chunk_strategy == ChunkStrategy.TIME

    def test_pre_query_builds_daily_chunks_plus_d6_closing(self):
        """PA-18/PA-15: same TIME-chunk + D6 closing-chunk shape as the 產出
        worker (move-out also has an overnight N-shift tail on TXNDATE)."""
        job = _make_job(params={"start_date": "2024-03-01", "end_date": "2024-03-03"})
        job.pre_query()
        assert len(job._chunks) == 4
        assert job._chunks[0] == {"start_date": "2024-03-01", "chunk_end_excl": "2024-03-02 00:00:00"}
        assert job._chunks[2] == {"start_date": "2024-03-03", "chunk_end_excl": "2024-03-04 00:00:00"}
        assert job._chunks[3] == {"start_date": "2024-03-04", "chunk_end_excl": "2024-03-04 07:30:00"}

    def test_pre_query_spool_key_uses_moveout_source(self):
        """The moveout worker's spool key must equal the canonical helper with
        source='moveout' -- and must DIFFER from the 'output' key for the same
        dates (distinct sources never collide)."""
        from mes_dashboard.services.production_achievement_service import (
            make_canonical_pa_spool_id,
        )
        job = _make_job(params={"start_date": "2024-03-01", "end_date": "2024-03-02"})
        job.pre_query()
        assert job._spool_key == make_canonical_pa_spool_id("2024-03-01", "2024-03-02", source="moveout")
        assert job._spool_key != make_canonical_pa_spool_id("2024-03-01", "2024-03-02", source="output")
        assert "production_achievement_moveout" in job._spool_path

    def test_build_chunk_sql_binds_dates_no_placeholder(self):
        job = _make_job()
        sql, params = job.build_chunk_sql(
            {"start_date": "2024-03-01", "chunk_end_excl": "2024-03-02 00:00:00"}
        )
        assert "DW_MES_HM_LOTMOVEOUT" in sql
        assert "FROMWORKCENTER" in sql
        assert params["start_date"] == "2024-03-01"
        assert params["chunk_end_excl"] == "2024-03-02 00:00:00"

    def test_always_async_registered_on_shared_queue(self):
        """PA-18: registered always_async=True, distinct job_type, SAME RQ queue
        as the 產出 worker (dequeue by queue name, not job_type)."""
        import mes_dashboard.workers.production_achievement_moveout_worker as _w
        importlib.reload(_w)
        from mes_dashboard.services.job_registry import get_job_type_config
        config = get_job_type_config("production-achievement-moveout")
        assert config is not None
        assert config.always_async is True
        assert config.queue_name == "production-achievement-query"

    def test_no_manual_heavy_query_slot_acquire(self):
        src = _WORKER_SRC_PATH.read_text(encoding="utf-8")
        assert "acquire_heavy_query_slot" not in src
        assert "read_sql_df" not in src


class TestMoveoutPostAggregate:
    def test_post_aggregate_groups_by_raw_workcenter_group(self, tmp_path, monkeypatch):
        """post_aggregate re-aggregates across chunk seams on
        (output_date, shift_code, raw_workcenter_group, PACKAGE_LF)."""
        monkeypatch.setenv("DUCKDB_JOB_DIR", str(tmp_path / "duckdb_jobs"))
        job = _make_job(job_id="mo-seam-001")
        job._spool_key = "mo-seam-key-1"
        job._spool_path = str(tmp_path / "spool" / "mo-seam-key-1.parquet")

        chunk_dir = job._make_chunk_parquet_dir(job.job_id)
        _write_chunk_parquet(chunk_dir, "chunk-0000-0000.parquet", [
            {"OUTPUT_DATE": date(2024, 3, 4), "SHIFT_CODE": "N", "RAW_WORKCENTER_GROUP": "掛鍍", "PACKAGE_LF": "PKG-1", "ACTUAL_OUTPUT_QTY": 100},
            {"OUTPUT_DATE": date(2024, 3, 4), "SHIFT_CODE": "D", "RAW_WORKCENTER_GROUP": "切割", "PACKAGE_LF": "PKG-1", "ACTUAL_OUTPUT_QTY": 20},
        ])
        # D6 closing chunk contributes more of the same (end_date, N, 掛鍍) group.
        _write_chunk_parquet(chunk_dir, "chunk-0001-0000.parquet", [
            {"OUTPUT_DATE": date(2024, 3, 4), "SHIFT_CODE": "N", "RAW_WORKCENTER_GROUP": "掛鍍", "PACKAGE_LF": "PKG-1", "ACTUAL_OUTPUT_QTY": 50},
        ])

        job.post_aggregate(None)

        con = duckdb.connect()
        try:
            rows = {
                (r[0], r[1], r[2]): r[3]
                for r in con.execute(
                    f"SELECT output_date, shift_code, raw_workcenter_group, actual_output_qty "
                    f"FROM read_parquet('{job._spool_path}')"
                ).fetchall()
            }
        finally:
            con.close()

        assert len(rows) == 2
        assert rows[(date(2024, 3, 4), "N", "掛鍍")] == 150  # seam-merged
        assert rows[(date(2024, 3, 4), "D", "切割")] == 20

    def test_empty_window_writes_valid_empty_parquet_with_schema(self, tmp_path, monkeypatch):
        """No qualifying rows -> a VALID empty parquet with the canonical
        5-column moveout schema (raw_workcenter_group, not SPECNAME)."""
        monkeypatch.setenv("DUCKDB_JOB_DIR", str(tmp_path / "duckdb_jobs"))
        job = _make_job(job_id="mo-empty-001")
        job._spool_key = "mo-empty-key-1"
        job._spool_path = str(tmp_path / "spool" / "mo-empty-key-1.parquet")
        job._make_chunk_parquet_dir(job.job_id)  # no chunk parquets written

        job.post_aggregate(None)

        schema = pq.read_schema(job._spool_path)
        assert schema.names == [
            "output_date", "shift_code", "raw_workcenter_group", "PACKAGE_LF", "actual_output_qty",
        ]
        assert pq.read_table(job._spool_path).num_rows == 0
