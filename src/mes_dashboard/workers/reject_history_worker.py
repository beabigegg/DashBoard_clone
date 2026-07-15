# -*- coding: utf-8 -*-
"""Reject History RQ worker (BaseChunkedDuckDBJob unified path, P2 migration).

Entry point: execute_reject_history_unified_job(job_id, params)

Design:
  - Subclasses BaseChunkedDuckDBJob (ADR-0009 P2 pattern).
  - ChunkStrategy.TIME: one Oracle query per REJECT_ENGINE_GRAIN_DAYS window.
  - requires_cross_chunk_reduction=True: rows accumulated into job-temp DuckDB;
    post_aggregate() writes canonical parquet spool directly from DuckDB SELECT.
  - The 6 post-hoc OOM guards (reject_dataset_cache.py L294, L387, L747, L961,
    L1170, L1864) are NOT reproduced here — DuckDB on-disk spill is the
    pre-emptive guard (AC-4).
  - always_async=False: sync fallback permitted; sync_fallback_allowed=True at route.
  - Feature flag: REJECT_HISTORY_USE_UNIFIED_JOB=on activates this path.
    Flag off → legacy enqueue_reject_query path (unchanged).

Module-level register_job_type() fires at import time (job-registry-central).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

from mes_dashboard.core.base_chunked_duckdb_job import BaseChunkedDuckDBJob, ChunkStrategy

logger = logging.getLogger("mes_dashboard.reject_history_worker")

# Re-use the legacy queue name so the same reject-query RQ workers pick up both job types.
REJECT_QUERY_WORKER_QUEUE: str = os.getenv("REJECT_WORKER_QUEUE", "reject-query")

REJECT_HISTORY_JOB_TIMEOUT_SECONDS: int = max(
    60, int(os.getenv("REJECT_HISTORY_JOB_TIMEOUT_SECONDS", "1800"))
)
REJECT_HISTORY_JOB_TTL_SECONDS: int = max(
    3600, int(os.getenv("REJECT_ENGINE_SPOOL_TTL_SECONDS", "21600"))
)

_JOB_PREFIX = "reject_unified"  # matches enqueue_job_dynamic prefix (job_type=reject_unified)

# Grain size for time-chunking (days per Oracle query)
_ENGINE_GRAIN_DAYS: int = max(1, int(os.getenv("REJECT_ENGINE_GRAIN_DAYS", "10")))


class RejectHistoryJob(BaseChunkedDuckDBJob):
    """Unified chunked Oracle→DuckDB job for Reject History (P2 migration).

    ChunkStrategy: TIME (one Oracle query per REJECT_ENGINE_GRAIN_DAYS window).
    requires_cross_chunk_reduction=True: raw rows accumulated into job-temp DuckDB;
    post_aggregate() reads from the 'raw' DuckDB table and writes canonical parquet
    spool via DuckDB SELECT … TO.  No pandas hot-path; DuckDB on-disk spill is the
    pre-emptive OOM guard replacing the 6 post-hoc raise guards (AC-4).
    """

    namespace = "reject_dataset"
    chunk_strategy = ChunkStrategy.TIME
    requires_cross_chunk_reduction = True

    def __init__(self, job_id: str, params: dict) -> None:
        super().__init__(job_id)
        self.params = params
        self._spool_key: str = ""
        self._spool_path: str = ""
        self._query_id: str = ""
        self._where_clause: str = ""
        self._where_params: Dict[str, Any] = {}
        self._base_where: str = ""
        self._base_params: Dict[str, Any] = {}

    def pre_query(self) -> None:
        """Parse params, compute canonical spool key, build time chunks."""
        from mes_dashboard.services.reject_dataset_cache import (
            _make_query_id,
            _CACHE_SCHEMA_VERSION,
            _REDIS_NAMESPACE,
        )
        from mes_dashboard.services.reject_history_service import _build_where_clause
        from mes_dashboard.core.query_spool_store import QUERY_SPOOL_DIR

        start_date: str = str(self.params.get("start_date") or "").strip()
        end_date: str = str(self.params.get("end_date") or "").strip()
        include_excluded_scrap: bool = bool(self.params.get("include_excluded_scrap", False))
        exclude_material_scrap: bool = bool(self.params.get("exclude_material_scrap", True))
        exclude_pb_diode: bool = bool(self.params.get("exclude_pb_diode", True))
        mode: str = str(self.params.get("mode", "date_range"))

        # Parse prefilter params (RHPF-05: must match sync path and legacy async path)
        _pj_types: List[str] = sorted({
            str(v).strip() for v in (self.params.get("pj_types") or []) if str(v).strip()
        })
        _packages: List[str] = sorted({
            str(v).strip() for v in (self.params.get("packages") or []) if str(v).strip()
        })
        _pj_functions: List[str] = sorted({
            str(v).strip() for v in (self.params.get("pj_functions") or []) if str(v).strip()
        })
        _reasons: List[str] = sorted({
            str(v).strip() for v in (self.params.get("reasons") or []) if str(v).strip()
        })

        # Compute deterministic query_id (same as legacy + sync paths — includes prefilters)
        query_id_input = {
            "cache_schema_version": _CACHE_SCHEMA_VERSION,
            "mode": mode,
            "start_date": start_date,
            "end_date": end_date,
            "container_input_type": self.params.get("container_input_type"),
            "container_values": sorted(self.params.get("container_values") or []),
            "pj_types": _pj_types,
            "packages": _packages,
            "pj_functions": _pj_functions,
            "reasons": _reasons,
        }
        self._query_id = _make_query_id(query_id_input)
        self._spool_key = self._query_id

        spool_dir = QUERY_SPOOL_DIR / _REDIS_NAMESPACE
        self._spool_path = str(spool_dir / f"{self._spool_key}.parquet")

        # Build WHERE clause for per-record filtering (policy filters)
        where_clause, where_params, _meta = _build_where_clause(
            include_excluded_scrap=include_excluded_scrap,
            exclude_material_scrap=exclude_material_scrap,
            exclude_pb_diode=exclude_pb_diode,
        )
        self._where_clause = where_clause
        self._where_params = where_params

        # Base WHERE clause — includes date filter AND prefilters (NVL form)
        # This is the per-chunk base_where; chunk start/end override start_date/end_date per chunk.
        from mes_dashboard.services.reject_history_service import _build_base_where
        _base_where_full, _base_params_full = _build_base_where(
            start_date,
            end_date,
            pj_types=_pj_types,
            packages=_packages,
            pj_functions=_pj_functions,
            reasons=_reasons,
        )
        self._base_where = _base_where_full
        self._base_params = _base_params_full

        # Extract prefilter bind params (pt_*, pkg_*, pf_*, reason_*) from _base_params_full
        # so each chunk carries them alongside its per-chunk date range.
        prefilter_bind: Dict[str, Any] = {
            k: v for k, v in _base_params_full.items()
            if k not in ("start_date", "end_date")
        }

        # Build time chunks
        grain = _ENGINE_GRAIN_DAYS
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        chunks: List[Dict[str, Any]] = []
        current = start_dt
        while current <= end_dt:
            chunk_end_dt = min(current + timedelta(days=grain - 1), end_dt)
            chunk_start_str = current.strftime("%Y-%m-%d")
            chunk_end_str = chunk_end_dt.strftime("%Y-%m-%d")
            chunk_bind: Dict[str, Any] = {
                "start_date": chunk_start_str,
                "end_date": chunk_end_str,
            }
            chunk_bind.update(where_params)
            chunk_bind.update(prefilter_bind)  # pt_*, pkg_*, pf_* params
            chunks.append({
                "chunk_start": chunk_start_str,
                "chunk_end_excl": chunk_end_str,
                "where_clause": where_clause,
                # Store the prefilter-extended base_where template — chunk dates still override
                # start_date/end_date in chunk_bind, so the date clause remains per-chunk.
                "base_where": _base_where_full,
                "bind_params": chunk_bind,
            })
            current = chunk_end_dt + timedelta(days=1)
        self._chunks = chunks

    def build_chunk_sql(self, chunk_params: dict) -> tuple[str, dict]:
        """Return (sql, binds) for a single time chunk."""
        from mes_dashboard.services.reject_history_service import _prepare_sql
        # Use the prefilter-extended base_where stored per-chunk (includes NVL prefilters)
        chunk_base_where = chunk_params.get("base_where") or (
            "r.TXNDATE >= TO_DATE(:start_date, 'YYYY-MM-DD')"
            " AND r.TXNDATE < TO_DATE(:end_date, 'YYYY-MM-DD') + 1"
        )
        sql = _prepare_sql(
            "primary",
            where_clause=chunk_params["where_clause"],
            base_where=chunk_base_where,
            base_variant="lot",
        )
        return sql, chunk_params["bind_params"]

    def post_aggregate(self, job_duckdb_path: "str | None") -> str:
        """Write canonical parquet spool from accumulated DuckDB raw table.

        For requires_cross_chunk_reduction=True: job_duckdb_path contains the
        accumulated 'raw' table.  DuckDB SELECT … TO writes the canonical spool.
        No pandas groupby/pandas raises — DuckDB on-disk spill is the guard (AC-4).
        """
        import duckdb

        spool_path = self._spool_path
        os.makedirs(os.path.dirname(spool_path), exist_ok=True)

        if job_duckdb_path is None or not Path(job_duckdb_path).exists():
            # Edge case: no chunks were written. Write empty spool.
            _write_empty_reject_spool(spool_path)
            row_count = 0
        else:
            con = duckdb.connect(job_duckdb_path)
            try:
                # Check if raw table has any rows
                has_raw = con.execute(
                    "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'raw'"
                ).fetchone()[0] > 0

                if not has_raw:
                    con.close()
                    _write_empty_reject_spool(spool_path)
                    row_count = 0
                else:
                    raw_count = con.execute("SELECT COUNT(*) FROM raw").fetchone()[0]
                    if raw_count == 0:
                        con.close()
                        _write_empty_reject_spool(spool_path)
                        row_count = 0
                    else:
                        # Write all raw rows directly to spool parquet.
                        # Aggregation views (summary/trend/pareto) are computed
                        # by the existing DuckDB view layer at read time —
                        # this spool is the input to apply_view(), not the aggregated output.
                        con.execute(
                            f"COPY (SELECT * FROM raw) "
                            f"TO '{spool_path}' (FORMAT PARQUET, CODEC 'SNAPPY')"
                        )
                        row_count = con.execute(
                            f"SELECT COUNT(*) FROM read_parquet('{spool_path}')"
                        ).fetchone()[0]
                        con.close()
            except Exception:
                try:
                    con.close()
                except Exception:
                    pass
                raise

        logger.info(
            "RejectHistoryJob.post_aggregate: parquet written path=%s rows=%d job_id=%s",
            spool_path, row_count, self.job_id,
        )

        try:
            from mes_dashboard.core.query_spool_store import register_spool_file
            register_spool_file(
                "reject_dataset", self._spool_key, Path(spool_path),
                row_count, ttl_seconds=REJECT_HISTORY_JOB_TTL_SECONDS,
            )
        except Exception as reg_exc:
            logger.warning(
                "RejectHistoryJob.post_aggregate: spool registration failed: %s", reg_exc
            )

        return spool_path

    def progress_report(self, pct: int) -> None:
        """Report progress via async_query_job_service."""
        from mes_dashboard.services.async_query_job_service import update_job_progress
        update_job_progress(_JOB_PREFIX, self.job_id, pct=str(pct))

    def chunk_to_duckdb(self, batch: "pa.RecordBatch", job_duckdb_path: str) -> None:
        """Override base class to use explicit DDL for the raw table.

        The base class infers column types from the first batch via
        'CREATE TABLE AS SELECT ... WHERE 1=0'. When the first time-chunk
        returns no reject records, columns like REJECTCOMMENT arrive as
        pa.null() and DuckDB infers them as INT32, causing ConversionException
        when subsequent chunks carry real VARCHAR values.

        Fix: create raw with an explicit schema; insert by column name
        (INSERT BY NAME) to be resilient against column-order variance.
        """
        import duckdb

        with self._writer_lock:
            conn = duckdb.connect(job_duckdb_path)
            try:
                conn.register("_chunk_batch", batch)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS raw (
                        TXN_TIME VARCHAR,
                        TXN_DAY VARCHAR,
                        TXN_MONTH VARCHAR,
                        WORKCENTER_GROUP VARCHAR,
                        WORKCENTERSEQUENCE_GROUP VARCHAR,
                        WORKCENTERNAME VARCHAR,
                        SPECNAME VARCHAR,
                        EQUIPMENTNAME VARCHAR,
                        PRODUCTLINENAME VARCHAR,
                        SCRAP_OBJECTTYPE VARCHAR,
                        PJ_TYPE VARCHAR,
                        CONTAINERNAME VARCHAR,
                        PJ_WORKORDER VARCHAR,
                        PJ_FUNCTION VARCHAR,
                        PRODUCTNAME VARCHAR,
                        LOSSREASONNAME VARCHAR,
                        LOSSREASON_CODE VARCHAR,
                        REJECTCOMMENT VARCHAR,
                        AFFECTED_WORKORDER_COUNT BIGINT,
                        MOVEIN_QTY DOUBLE,
                        REJECT_QTY DOUBLE,
                        REJECT_TOTAL_QTY DOUBLE,
                        DEFECT_QTY DOUBLE,
                        STANDBY_QTY DOUBLE,
                        QTYTOPROCESS_QTY DOUBLE,
                        INPROCESS_QTY DOUBLE,
                        PROCESSED_QTY DOUBLE,
                        REJECT_RATE_PCT DOUBLE,
                        DEFECT_RATE_PCT DOUBLE,
                        REJECT_SHARE_PCT DOUBLE
                    )
                """)
                conn.execute("INSERT INTO raw BY NAME SELECT * FROM _chunk_batch")
                conn.unregister("_chunk_batch")
            finally:
                conn.close()


def _write_empty_reject_spool(spool_path: str) -> None:
    """Write an empty parquet file with the reject primary schema."""
    import pyarrow as pa
    import pyarrow.parquet as pq
    schema = pa.schema([
        pa.field("TXN_TIME", pa.string()),
        pa.field("TXN_DAY", pa.string()),
        pa.field("TXN_MONTH", pa.string()),
        pa.field("WORKCENTER_GROUP", pa.string()),
        pa.field("WORKCENTERSEQUENCE_GROUP", pa.string()),
        pa.field("WORKCENTERNAME", pa.string()),
        pa.field("SPECNAME", pa.string()),
        pa.field("EQUIPMENTNAME", pa.string()),
        pa.field("PRODUCTLINENAME", pa.string()),
        pa.field("SCRAP_OBJECTTYPE", pa.string()),
        pa.field("PJ_TYPE", pa.string()),
        pa.field("CONTAINERNAME", pa.string()),
        pa.field("PJ_WORKORDER", pa.string()),
        pa.field("PJ_FUNCTION", pa.string()),
        pa.field("PRODUCTNAME", pa.string()),
        pa.field("LOSSREASONNAME", pa.string()),
        pa.field("LOSSREASON_CODE", pa.string()),
        pa.field("REJECTCOMMENT", pa.string()),
        pa.field("AFFECTED_WORKORDER_COUNT", pa.int64()),
        pa.field("MOVEIN_QTY", pa.float64()),
        pa.field("REJECT_QTY", pa.float64()),
        pa.field("REJECT_TOTAL_QTY", pa.float64()),
        pa.field("DEFECT_QTY", pa.float64()),
        pa.field("STANDBY_QTY", pa.float64()),
        pa.field("QTYTOPROCESS_QTY", pa.float64()),
        pa.field("INPROCESS_QTY", pa.float64()),
        pa.field("PROCESSED_QTY", pa.float64()),
        pa.field("REJECT_RATE_PCT", pa.float64()),
        pa.field("DEFECT_RATE_PCT", pa.float64()),
        pa.field("REJECT_SHARE_PCT", pa.float64()),
    ])
    empty = pa.table({f: pa.array([], type=schema.field(f).type) for f in schema.names},
                     schema=schema)
    pq.write_table(empty, spool_path, compression="snappy")


def execute_reject_history_unified_job(
    job_id: str,
    params: dict,
) -> None:
    """RQ entry point for RejectHistoryJob (REJECT_HISTORY_USE_UNIFIED_JOB=on path).

    Called by RQ worker process. Creates RejectHistoryJob and runs the template method.
    """
    from mes_dashboard.rq_worker_preload import ensure_rq_logging
    ensure_rq_logging()

    from mes_dashboard.services.async_query_job_service import complete_job

    logger.info("execute_reject_history_unified_job: started job_id=%s", job_id)
    try:
        job = RejectHistoryJob(job_id=job_id, params=params)
        spool_path = job.run()
        complete_job(_JOB_PREFIX, job_id, query_id=job._spool_key)
        logger.info(
            "execute_reject_history_unified_job: completed job_id=%s spool_path=%s",
            job_id, spool_path,
        )
    except Exception as exc:
        logger.error(
            "execute_reject_history_unified_job: failed job_id=%s: %s",
            job_id, exc, exc_info=True,
        )
        complete_job(_JOB_PREFIX, job_id, error=str(exc))
        raise


# ── Central job registry ───────────────────────────────────────────────────────
from mes_dashboard.services.job_registry import JobTypeConfig, register_job_type  # noqa: E402

register_job_type(JobTypeConfig(
    job_type="reject_unified",
    queue_name=REJECT_QUERY_WORKER_QUEUE,
    worker_fn=execute_reject_history_unified_job,
    timeout_seconds=REJECT_HISTORY_JOB_TIMEOUT_SECONDS,
    ttl_seconds=REJECT_HISTORY_JOB_TTL_SECONDS,
    always_async=False,
))
