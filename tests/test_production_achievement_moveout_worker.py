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
    PACKAGE_LF, ACTUAL_OUTPUT_QTY, MAX_TXN_TS (extra per-row aggregate input
    column post_aggregate() MAX()s across chunks for the "資料最新一筆時間"
    freshness indicator -- optional per row, defaults to None when omitted)."""
    table = pa.table({
        "OUTPUT_DATE": pa.array([r["OUTPUT_DATE"] for r in rows], type=pa.date32()),
        "SHIFT_CODE": pa.array([r["SHIFT_CODE"] for r in rows], type=pa.string()),
        "RAW_WORKCENTER_GROUP": pa.array([r["RAW_WORKCENTER_GROUP"] for r in rows], type=pa.string()),
        "PACKAGE_LF": pa.array([r.get("PACKAGE_LF") for r in rows], type=pa.string()),
        "ACTUAL_OUTPUT_QTY": pa.array([r["ACTUAL_OUTPUT_QTY"] for r in rows], type=pa.int64()),
        "MAX_TXN_TS": pa.array([r.get("MAX_TXN_TS") for r in rows], type=pa.timestamp("us")),
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


class TestMoveoutPostAggregateFreshnessMetadata:
    """MAX_TXN_TS -> register_spool_file extra_metadata["latest_data_ts"]
    plumbing (UI "資料最新一筆時間" indicator), mirrors the 產出 worker's
    TestPostAggregateFreshnessMetadata in test_production_achievement_unified_job.py."""

    def test_register_spool_file_receives_max_txn_ts_as_latest_data_ts(self, tmp_path, monkeypatch):
        """post_aggregate must compute the GLOBAL MAX(MAX_TXN_TS) across ALL
        chunk parquets (not per-group) and forward it, formatted as
        "%Y-%m-%d %H:%M:%S", to register_spool_file(extra_metadata=...)."""
        import datetime as _dt

        monkeypatch.setenv("DUCKDB_JOB_DIR", str(tmp_path / "duckdb_jobs"))

        job = _make_job(job_id="mo-freshness-001")
        job._spool_key = "mo-freshness-key"
        job._spool_path = str(tmp_path / "spool" / "mo-freshness-key.parquet")

        chunk_dir = job._make_chunk_parquet_dir(job.job_id)
        _write_chunk_parquet(chunk_dir, "chunk-0000-0000.parquet", [
            {
                "OUTPUT_DATE": date(2024, 3, 4), "SHIFT_CODE": "N", "RAW_WORKCENTER_GROUP": "掛鍍",
                "PACKAGE_LF": "PKG-1", "ACTUAL_OUTPUT_QTY": 100,
                "MAX_TXN_TS": _dt.datetime(2024, 3, 4, 23, 10, 5),
            },
        ])
        _write_chunk_parquet(chunk_dir, "chunk-0001-0000.parquet", [
            {
                "OUTPUT_DATE": date(2024, 3, 5), "SHIFT_CODE": "D", "RAW_WORKCENTER_GROUP": "切割",
                "PACKAGE_LF": "PKG-2", "ACTUAL_OUTPUT_QTY": 7,
                # This is the global max across both chunks.
                "MAX_TXN_TS": _dt.datetime(2024, 3, 5, 7, 29, 59),
            },
        ])

        calls = []

        def _fake_register(*args, **kwargs):
            calls.append((args, kwargs))
            return True

        import mes_dashboard.core.query_spool_store as spool_mod
        monkeypatch.setattr(spool_mod, "register_spool_file", _fake_register)

        job.post_aggregate(None)

        assert len(calls) == 1
        _args, kwargs = calls[0]
        assert kwargs["extra_metadata"] == {
            "latest_data_ts": "2024-03-05 07:29:59",
            "query_started_at": job._query_started_at,
        }

    def test_empty_window_still_registers_latest_data_ts_none(self, tmp_path, monkeypatch):
        """Empty/no-chunk-parquet window must never query a non-existent
        parquet for the freshness indicator -- latest_data_ts is passed as
        plain None to register_spool_file's extra_metadata."""
        monkeypatch.setenv("DUCKDB_JOB_DIR", str(tmp_path / "duckdb_jobs"))

        job = _make_job(job_id="mo-empty-freshness-001")
        job._spool_key = "mo-empty-freshness-key"
        job._spool_path = str(tmp_path / "spool" / "mo-empty-freshness-key.parquet")
        job._make_chunk_parquet_dir(job.job_id)  # no chunk parquets written

        calls = []

        def _fake_register(*args, **kwargs):
            calls.append((args, kwargs))
            return True

        import mes_dashboard.core.query_spool_store as spool_mod
        monkeypatch.setattr(spool_mod, "register_spool_file", _fake_register)

        job.post_aggregate(None)

        assert len(calls) == 1
        _args, kwargs = calls[0]
        assert kwargs["extra_metadata"] == {
            "latest_data_ts": None,
            "query_started_at": job._query_started_at,
        }


class TestMoveoutInflightStateAndCas:
    """Moveout counterpart of TestInflightStateAndCas
    (test_production_achievement_unified_job.py) -- race-condition fix:
    pre_query publishes inflight state and records query_started_at;
    post_aggregate forwards it as a CAS guard to register_spool_file and
    always clears inflight state afterward."""

    def test_pre_query_records_started_at_and_sets_inflight_state(self, monkeypatch):
        import mes_dashboard.workers.production_achievement_moveout_worker as worker_mod
        import mes_dashboard.core.query_spool_store as spool_mod

        monkeypatch.setattr(worker_mod.time, "time", lambda: 2_000.0)

        calls = []
        monkeypatch.setattr(
            spool_mod, "set_inflight_state",
            lambda *args, **kwargs: calls.append((args, kwargs)) or True,
        )

        job = _make_job(params={"start_date": "2024-03-01", "end_date": "2024-03-02"})
        job.pre_query()

        assert job._query_started_at == 2_000.0
        assert len(calls) == 1
        args, kwargs = calls[0]
        assert args[0] == worker_mod._NAMESPACE
        assert args[1] == job._spool_key
        assert args[2] == {"started_at": 2_000.0, "job_id": job.job_id}

    def test_post_aggregate_passes_cas_field_and_value_to_register_spool_file(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("DUCKDB_JOB_DIR", str(tmp_path / "duckdb_jobs"))

        job = _make_job(job_id="mo-cas-test-001")
        job._spool_key = "mo-cas-test-key"
        job._spool_path = str(tmp_path / "spool" / "mo-cas-test-key.parquet")
        job._query_started_at = 54321.9
        job._make_chunk_parquet_dir(job.job_id)  # empty branch is fine here

        calls = []

        def _fake_register(*args, **kwargs):
            calls.append((args, kwargs))
            return True

        import mes_dashboard.core.query_spool_store as spool_mod
        monkeypatch.setattr(spool_mod, "register_spool_file", _fake_register)
        monkeypatch.setattr(spool_mod, "clear_inflight_state", lambda *a, **k: None)

        job.post_aggregate(None)

        assert len(calls) == 1
        _args, kwargs = calls[0]
        assert kwargs["cas_field"] == "query_started_at"
        assert kwargs["cas_value"] == 54321.9
        assert kwargs["extra_metadata"]["query_started_at"] == 54321.9

    def test_post_aggregate_clears_inflight_state_before_returning(self, tmp_path, monkeypatch):
        import mes_dashboard.workers.production_achievement_moveout_worker as worker_mod

        monkeypatch.setenv("DUCKDB_JOB_DIR", str(tmp_path / "duckdb_jobs"))

        job = _make_job(job_id="mo-clear-inflight-001")
        job._spool_key = "mo-clear-inflight-key"
        job._spool_path = str(tmp_path / "spool" / "mo-clear-inflight-key.parquet")
        job._query_started_at = 84.0
        job._make_chunk_parquet_dir(job.job_id)

        import mes_dashboard.core.query_spool_store as spool_mod
        monkeypatch.setattr(spool_mod, "register_spool_file", lambda *a, **k: True)

        clear_calls = []
        monkeypatch.setattr(
            spool_mod, "clear_inflight_state",
            lambda *args, **kwargs: clear_calls.append(args),
        )

        result_path = job.post_aggregate(None)

        assert result_path == job._spool_path
        assert clear_calls == [(worker_mod._NAMESPACE, job._spool_key)]
