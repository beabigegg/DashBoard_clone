# -*- coding: utf-8 -*-
"""Production History RQ worker (BaseChunkedDuckDBJob unified path, P2 migration).

Entry point: execute_production_history_unified_job(job_id, params)

Design:
  - Subclasses BaseChunkedDuckDBJob (ADR-0009 P2 pattern).
  - ChunkStrategy.TIME: one Oracle query per ENGINE_GRAIN_DAYS window.
  - requires_cross_chunk_reduction=False: row-level detail appended across chunks.
  - post_aggregate merges chunk parquets into a single canonical parquet spool.
  - Uses make_canonical_spool_id for deterministic query_id (spool-hit L0 compatibility).
  - always_async=False: sync fallback permitted; sync_fallback_allowed=True at route.
  - Feature flag: PRODUCTION_HISTORY_USE_UNIFIED_JOB=on activates this path.
    Flag off → legacy query_production_history pandas BQE path.

Module-level register_job_type() fires at import time (job-registry-central).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

from mes_dashboard.core.base_chunked_duckdb_job import BaseChunkedDuckDBJob, ChunkStrategy

logger = logging.getLogger("mes_dashboard.production_history_worker")

PRODUCTION_HISTORY_WORKER_QUEUE: str = os.getenv(
    "PRODUCTION_HISTORY_WORKER_QUEUE", "production-history-query"
)
PRODUCTION_HISTORY_JOB_TIMEOUT_SECONDS: int = max(
    60, int(os.getenv("PRODUCTION_HISTORY_JOB_TIMEOUT_SECONDS", "1800"))
)
PRODUCTION_HISTORY_JOB_TTL_SECONDS: int = max(
    3600, int(os.getenv("PRODUCTION_HISTORY_JOB_TTL_SECONDS", "3600"))
)

_JOB_PREFIX = "production_history_unified"  # matches enqueue_job_dynamic prefix (job_type=production_history_unified)

# Grain size for time-chunking (days per Oracle query).
_ENGINE_GRAIN_DAYS: int = max(1, int(os.getenv("PROD_HISTORY_ENGINE_GRAIN_DAYS", "31")))


class ProductionHistoryJob(BaseChunkedDuckDBJob):
    """Unified chunked Oracle→DuckDB job for Production History (P2 migration).

    ChunkStrategy: TIME (one Oracle query per ENGINE_GRAIN_DAYS window).
    requires_cross_chunk_reduction=False: raw row-level detail appended across
    chunks into separate parquets; post_aggregate merges them into one canonical
    parquet spool using DuckDB COPY TO (no pandas in the hot path).
    """

    namespace = "production_history"
    chunk_strategy = ChunkStrategy.TIME
    requires_cross_chunk_reduction = False

    def __init__(self, job_id: str, params: dict) -> None:
        super().__init__(job_id)
        self.params = params
        self._spool_key: str = ""
        self._spool_path: str = ""
        self._chunks: List[Dict[str, Any]] = []

    def pre_query(self) -> None:
        """Parse params, compute canonical spool key, build time chunks."""
        from mes_dashboard.services.production_history_service import (
            make_canonical_spool_id,
            validate_query_params,
            _build_extra_filters,
            ENGINE_GRAIN_DAYS,
        )
        from mes_dashboard.core.query_spool_store import QUERY_SPOOL_DIR

        validated = validate_query_params(self.params)
        self._spool_key = make_canonical_spool_id(validated)

        spool_dir = QUERY_SPOOL_DIR / "production_history"
        self._spool_path = str(spool_dir / f"{self._spool_key}.parquet")

        extra_sql, extra_params = _build_extra_filters(validated)
        self._extra_sql = extra_sql
        self._extra_params = extra_params

        start_date = validated["start_date"]
        end_date = validated["end_date"]

        # Build time chunks (one per ENGINE_GRAIN_DAYS window)
        grain = ENGINE_GRAIN_DAYS
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        chunks: List[Dict[str, Any]] = []
        current = start_dt
        while current <= end_dt:
            chunk_end_dt = min(current + timedelta(days=grain - 1), end_dt)
            chunk_end_excl_dt = chunk_end_dt + timedelta(days=1)
            chunks.append({
                "chunk_start": current.strftime("%Y-%m-%d"),
                "chunk_end_excl": chunk_end_excl_dt.strftime("%Y-%m-%d"),
                "extra_sql": extra_sql,
                "extra_params": extra_params,
            })
            current = chunk_end_dt + timedelta(days=1)
        self._chunks = chunks

    def build_chunk_sql(self, chunk_params: dict) -> tuple[str, dict]:
        """Return (sql, binds) for a single time chunk."""
        from mes_dashboard.sql import SQLLoader
        base_sql = SQLLoader.load("production_history/main_query")
        sql = base_sql.replace("{{ EXTRA_FILTERS }}", chunk_params["extra_sql"])
        bind_params: Dict[str, Any] = {
            "chunk_start": chunk_params["chunk_start"],
            "chunk_end_excl": chunk_params["chunk_end_excl"],
        }
        bind_params.update(chunk_params["extra_params"])
        return sql, bind_params

    def post_aggregate(self, job_duckdb_path: "str | None") -> str:
        """Merge all chunk parquets into canonical spool via DuckDB COPY TO."""
        import duckdb

        chunk_dir = self._make_chunk_parquet_dir(self.job_id)
        all_parquets = sorted(chunk_dir.glob("chunk-*.parquet"))

        spool_path = self._spool_path
        os.makedirs(os.path.dirname(spool_path), exist_ok=True)

        if not all_parquets:
            # No rows — write an empty parquet with the correct schema.
            _schema_cols = [
                "CONTAINERNAME", "PJ_TYPE", "PJ_BOP", "PJ_FUNCTION", "MFGORDERNAME",
                "FIRSTNAME", "PRODUCTLINENAME", "WORKCENTERNAME", "SPECNAME",
                "EQUIPMENTID", "EQUIPMENTNAME", "TRACKINTIMESTAMP", "TRACKOUTTIMESTAMP",
                "TRACKINQTY", "TRACKOUTQTY",
            ]
            import pyarrow as pa
            import pyarrow.parquet as pq
            schema = pa.schema([
                pa.field("CONTAINERNAME", pa.string()),
                pa.field("PJ_TYPE", pa.string()),
                pa.field("PJ_BOP", pa.string()),
                pa.field("PJ_FUNCTION", pa.string()),
                pa.field("MFGORDERNAME", pa.string()),
                pa.field("FIRSTNAME", pa.string()),
                pa.field("PRODUCTLINENAME", pa.string()),
                pa.field("WORKCENTERNAME", pa.string()),
                pa.field("SPECNAME", pa.string()),
                pa.field("EQUIPMENTID", pa.string()),
                pa.field("EQUIPMENTNAME", pa.string()),
                pa.field("TRACKINTIMESTAMP", pa.string()),
                pa.field("TRACKOUTTIMESTAMP", pa.string()),
                pa.field("TRACKINQTY", pa.int64()),
                pa.field("TRACKOUTQTY", pa.int64()),
            ])
            pq.write_table(pa.table({f: pa.array([], type=schema.field(f).type) for f in schema.names},
                                    schema=schema), spool_path, compression="snappy")
            row_count = 0
        else:
            # Use DuckDB to merge all chunk parquets into one canonical spool
            con = duckdb.connect()
            try:
                # register each as a parquet scan
                parquet_glob = str(chunk_dir / "chunk-*.parquet")
                con.execute(
                    f"COPY (SELECT * FROM read_parquet('{parquet_glob}')) "
                    f"TO '{spool_path}' (FORMAT PARQUET, CODEC 'SNAPPY')"
                )
                row_count = con.execute(
                    f"SELECT COUNT(*) FROM read_parquet('{spool_path}')"
                ).fetchone()[0]
            finally:
                con.close()

        logger.info(
            "ProductionHistoryJob.post_aggregate: parquet written path=%s rows=%d job_id=%s",
            spool_path, row_count, self.job_id,
        )

        try:
            from mes_dashboard.core.query_spool_store import register_spool_file, QUERY_SPOOL_TTL_SECONDS
            register_spool_file(
                "production_history", self._spool_key, Path(spool_path),
                row_count, ttl_seconds=QUERY_SPOOL_TTL_SECONDS,
            )
        except Exception as reg_exc:
            logger.warning(
                "ProductionHistoryJob.post_aggregate: spool registration failed: %s", reg_exc
            )

        return spool_path

    def progress_report(self, pct: int) -> None:
        """Report progress via async_query_job_service (lazy import to avoid circular)."""
        from mes_dashboard.services.async_query_job_service import update_job_progress
        update_job_progress(_JOB_PREFIX, self.job_id, pct=str(pct))


def execute_production_history_unified_job(
    job_id: str,
    params: dict,
) -> None:
    """RQ entry point for ProductionHistoryJob (PRODUCTION_HISTORY_USE_UNIFIED_JOB=on path).

    Called by RQ worker process. Creates ProductionHistoryJob and runs the template method.
    """
    from mes_dashboard.rq_worker_preload import ensure_rq_logging
    ensure_rq_logging()

    from mes_dashboard.services.async_query_job_service import complete_job

    logger.info("execute_production_history_unified_job: started job_id=%s", job_id)
    try:
        job = ProductionHistoryJob(job_id=job_id, params=params)
        spool_path = job.run()
        complete_job(_JOB_PREFIX, job_id, query_id=job._spool_key)
        logger.info(
            "execute_production_history_unified_job: completed job_id=%s spool_path=%s",
            job_id, spool_path,
        )
    except Exception as exc:
        logger.error(
            "execute_production_history_unified_job: failed job_id=%s: %s",
            job_id, exc, exc_info=True,
        )
        complete_job(_JOB_PREFIX, job_id, error=str(exc))
        raise


# ── Central job registry ───────────────────────────────────────────────────────
from mes_dashboard.services.job_registry import JobTypeConfig, register_job_type  # noqa: E402

register_job_type(JobTypeConfig(
    job_type="production_history_unified",
    queue_name=PRODUCTION_HISTORY_WORKER_QUEUE,
    worker_fn=execute_production_history_unified_job,
    timeout_seconds=PRODUCTION_HISTORY_JOB_TIMEOUT_SECONDS,
    ttl_seconds=PRODUCTION_HISTORY_JOB_TTL_SECONDS,
    always_async=False,
))
