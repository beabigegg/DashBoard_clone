# -*- coding: utf-8 -*-
"""Resource History Base-Facts RQ worker (BaseChunkedDuckDBJob unified path, P3 migration).

Entry point: execute_resource_history_base_job(job_id, params)

Design:
  - Subclasses BaseChunkedDuckDBJob (ADR-0009 P3 pattern).
  - ChunkStrategy.TIME: one Oracle query per whole-day boundary.
  - requires_cross_chunk_reduction=False: each day's shift-status rows belong to
    exactly one calendar day (GROUP BY HISTORYID, TRUNC(TXNDATE)), so no row
    spans a chunk seam.  _fan_out_append + multi-parquet merge is safe.
  - post_aggregate merges chunk parquets into canonical resource_dataset spool.
  - always_async=True (mirror EapAlarm): resource-history base queries can take
    >30s for long date ranges; no safe synchronous timeout bound.
  - Feature flag: RESOURCE_HISTORY_USE_UNIFIED_JOB=on activates this path.
    Flag off → legacy execute_primary_query pandas BQE path.

Module-level register_job_type() fires at import time (job-registry-central).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

from mes_dashboard.core.base_chunked_duckdb_job import BaseChunkedDuckDBJob, ChunkStrategy

logger = logging.getLogger("mes_dashboard.resource_history_base_worker")

RESOURCE_WORKER_QUEUE: str = os.getenv("RESOURCE_WORKER_QUEUE", "resource-history-query")
RESOURCE_BASE_JOB_TIMEOUT_SECONDS: int = max(
    60, int(os.getenv("RESOURCE_BASE_JOB_TIMEOUT_SECONDS", "1800"))
)
RESOURCE_BASE_JOB_TTL_SECONDS: int = max(
    3600, int(os.getenv("RESOURCE_BASE_JOB_TTL_SECONDS", "72000"))
)

_JOB_PREFIX = "resource-history-base"


class ResourceHistoryBaseJob(BaseChunkedDuckDBJob):
    """Unified chunked Oracle→DuckDB job for Resource History base facts (P3 migration).

    ChunkStrategy: TIME (one Oracle query per whole-day boundary).
    requires_cross_chunk_reduction=False: base_facts.sql is GROUP BY HISTORYID, TRUNC(TXNDATE).
    Each shift row belongs to exactly one calendar day; whole-day chunk boundaries guarantee
    no (HISTORYID, day) group spans a seam (ADR-0003 safe).  Per-chunk parquets are
    independently correct; post_aggregate merges them into the resource_dataset spool.

    Output namespace: resource_dataset (matches legacy _REDIS_NAMESPACE).
    """

    namespace = "resource_dataset"
    chunk_strategy = ChunkStrategy.TIME
    requires_cross_chunk_reduction = False
    max_parallel = 3

    def __init__(self, job_id: str, params: dict) -> None:
        super().__init__(job_id)
        self.params = params
        self._spool_key: str = ""
        self._spool_path: str = ""
        self._historyid_filter: str = ""

    def pre_query(self) -> None:
        """Parse params, compute spool key, build daily time chunks."""
        from mes_dashboard.services.resource_dataset_cache import make_canonical_base_query_id
        from mes_dashboard.core.query_spool_store import QUERY_SPOOL_DIR
        from mes_dashboard.services.resource_history_service import (
            _get_filtered_resources,
            _build_historyid_filter,
        )

        start_date = str(self.params.get("start_date", "")).strip()
        end_date = str(self.params.get("end_date", "")).strip()

        self._spool_key = make_canonical_base_query_id(start_date, end_date)
        spool_dir = QUERY_SPOOL_DIR / "resource_dataset"
        self._spool_path = str(spool_dir / f"{self._spool_key}.parquet")

        # Build HISTORYID filter from resource cache (all resources — canonical superset)
        resources = _get_filtered_resources()
        self._historyid_filter = _build_historyid_filter(resources)
        if not self._historyid_filter:
            self._historyid_filter = "1=1"

        # Build whole-day time chunks
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        chunks: List[Dict[str, Any]] = []
        current = start_dt
        while current <= end_dt:
            chunks.append({
                "start_date": current.strftime("%Y-%m-%d"),
                "end_date": current.strftime("%Y-%m-%d"),
            })
            current += timedelta(days=1)
        self._chunks = chunks

    def build_chunk_sql(self, chunk_params: dict) -> tuple[str, dict]:
        """Return (sql, binds) for a single day chunk of base_facts.sql."""
        from mes_dashboard.sql import SQLLoader

        sql = SQLLoader.load("resource_history/base_facts")
        sql = sql.replace("{{ HISTORYID_FILTER }}", self._historyid_filter)
        bind_params: Dict[str, Any] = {
            "start_date": chunk_params["start_date"],
            "end_date": chunk_params["end_date"],
        }
        return sql, bind_params

    def post_aggregate(self, job_duckdb_path: "str | None") -> str:
        """Merge all chunk parquets into canonical resource_dataset spool via DuckDB COPY TO."""
        import duckdb

        chunk_dir = self._make_chunk_parquet_dir(self.job_id)
        all_parquets = sorted(chunk_dir.glob("chunk-*.parquet"))

        spool_path = self._spool_path
        os.makedirs(os.path.dirname(spool_path), exist_ok=True)

        if not all_parquets:
            # No rows — write empty parquet with correct legacy schema
            import pyarrow as pa
            import pyarrow.parquet as pq

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
                spool_path,
                compression="snappy",
            )
            row_count = 0
        else:
            parquet_glob = str(chunk_dir / "chunk-*.parquet")
            con = duckdb.connect()
            try:
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
            "ResourceHistoryBaseJob.post_aggregate: parquet written path=%s rows=%d job_id=%s",
            spool_path, row_count, self.job_id,
        )

        try:
            from mes_dashboard.core.query_spool_store import register_spool_file
            from mes_dashboard.services.resource_dataset_cache import _get_cache_ttl
            ttl = _get_cache_ttl(str(self.params.get("end_date", "")))
            register_spool_file(
                "resource_dataset", self._spool_key, Path(spool_path),
                row_count, ttl_seconds=ttl,
            )
        except Exception as reg_exc:
            logger.warning(
                "ResourceHistoryBaseJob.post_aggregate: spool registration failed: %s", reg_exc
            )

        return spool_path

    def progress_report(self, pct: int) -> None:
        """Report progress via async_query_job_service (lazy import to avoid circular)."""
        from mes_dashboard.services.async_query_job_service import update_job_progress
        update_job_progress(_JOB_PREFIX, self.job_id, pct=str(pct))


def execute_resource_history_base_job(
    job_id: str,
    params: dict,
) -> None:
    """RQ entry point for ResourceHistoryBaseJob (RESOURCE_HISTORY_USE_UNIFIED_JOB=on path).

    Called by RQ worker process.  Creates ResourceHistoryBaseJob and runs the template method.
    """
    from mes_dashboard.rq_worker_preload import ensure_rq_logging
    ensure_rq_logging()

    from mes_dashboard.services.async_query_job_service import complete_job

    logger.info("execute_resource_history_base_job: started job_id=%s", job_id)
    try:
        job = ResourceHistoryBaseJob(job_id=job_id, params=params)
        spool_path = job.run()
        complete_job(_JOB_PREFIX, job_id, query_id=job._spool_key)
        logger.info(
            "execute_resource_history_base_job: completed job_id=%s spool_path=%s",
            job_id, spool_path,
        )
    except Exception as exc:
        logger.error(
            "execute_resource_history_base_job: failed job_id=%s: %s",
            job_id, exc, exc_info=True,
        )
        complete_job(_JOB_PREFIX, job_id, error=str(exc))
        raise


# ── Central job registry ───────────────────────────────────────────────────────
from mes_dashboard.services.job_registry import JobTypeConfig, register_job_type  # noqa: E402

register_job_type(JobTypeConfig(
    job_type="resource-history-base",
    queue_name=RESOURCE_WORKER_QUEUE,
    worker_fn=execute_resource_history_base_job,
    timeout_seconds=RESOURCE_BASE_JOB_TIMEOUT_SECONDS,
    ttl_seconds=RESOURCE_BASE_JOB_TTL_SECONDS,
    always_async=True,
))
