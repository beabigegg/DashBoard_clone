# -*- coding: utf-8 -*-
"""Resource History OEE-Facts RQ worker (BaseChunkedDuckDBJob unified path, P3 migration).

Entry point: execute_resource_history_oee_job(job_id, params)

Design:
  - Subclasses BaseChunkedDuckDBJob (ADR-0009 P3 pattern).
  - ChunkStrategy.TIME: one Oracle query per whole-day boundary.
  - requires_cross_chunk_reduction=True: OEE Availability and Yield are ratio-of-SUMs
    per EQUIPMENTID across ALL shift dates.  Per-chunk pre-aggregation followed by naive
    concat would under/double-count at seams (ADR-0003 failure mode).  Chunks INSERT INTO
    the shared job-temp DuckDB raw table; post_aggregate runs the final GROUP BY EQUIPMENTID
    ratio-of-SUMs there and COPYs to the resource_oee spool.
  - OEE ±30d reject window: each chunk's build_chunk_sql extends :reject_start/:reject_end
    ±30d around the chunk's production dates to avoid boundary NG loss (highest-risk item).
  - always_async=True (mirror EapAlarm / base worker).
  - Feature flag: RESOURCE_HISTORY_USE_UNIFIED_JOB=on activates this path.
    Flag off → legacy execute_primary_query OEE ThreadPoolExecutor path.

Output namespace: resource_oee (matches legacy _OEE_REDIS_NAMESPACE).
Note: resource_oee is NOT in spool_routes._ALLOWED_NAMESPACES (OEE spool is consumed
internally via get_spool_file_path, never exposed over /api/spool HTTP).

Module-level register_job_type() fires at import time (job-registry-central).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

from mes_dashboard.core.base_chunked_duckdb_job import BaseChunkedDuckDBJob, ChunkStrategy

logger = logging.getLogger("mes_dashboard.resource_history_oee_worker")

RESOURCE_WORKER_QUEUE: str = os.getenv("RESOURCE_WORKER_QUEUE", "resource-history-query")
RESOURCE_OEE_JOB_TIMEOUT_SECONDS: int = max(
    60, int(os.getenv("RESOURCE_OEE_JOB_TIMEOUT_SECONDS", "1800"))
)
RESOURCE_OEE_JOB_TTL_SECONDS: int = max(
    3600, int(os.getenv("RESOURCE_OEE_JOB_TTL_SECONDS", "72000"))
)

_JOB_PREFIX = "resource-history-oee"

# Reject window radius (days) — matches legacy oee_facts.sql intent
_REJECT_WINDOW_DAYS = 30


class ResourceHistoryOeeJob(BaseChunkedDuckDBJob):
    """Unified chunked Oracle→DuckDB job for Resource History OEE facts (P3 migration).

    ChunkStrategy: TIME (one Oracle query per whole-day boundary).
    requires_cross_chunk_reduction=True: Yield = ΣTRACKOUT / (ΣTRACKOUT + ΣNG) and
    Availability = (ΣPRD+ΣSBY+ΣEGT)/(ΣPRD+ΣSBY+ΣEGT+ΣSDT+ΣUDT+ΣNST) per EQUIPMENTID
    across the whole date range.  Cross-date sums span chunk boundaries; NG side carries
    a ±30d reject window whose matches can land in a different chunk than the producing
    trackout.  All chunks INSERT INTO the shared job-temp DuckDB raw table; post_aggregate
    runs the final GROUP BY EQUIPMENTID + ratio-of-SUMs and COPYs to resource_oee spool.

    OEE ±30d reject window: each chunk's build_chunk_sql widens :reject_start/:reject_end
    ±30d around its own production chunk dates.  This is the single highest-risk correctness
    item; data-boundary tests assert seam parity ≤1e-6.

    Output namespace: resource_oee (matches legacy _OEE_REDIS_NAMESPACE).
    """

    namespace = "resource_oee"
    chunk_strategy = ChunkStrategy.TIME
    requires_cross_chunk_reduction = True
    max_parallel = 3

    def __init__(self, job_id: str, params: dict) -> None:
        super().__init__(job_id)
        self.params = params
        self._spool_key: str = ""
        self._spool_path: str = ""

    def pre_query(self) -> None:
        """Parse params, compute spool key, build daily time chunks."""
        from mes_dashboard.services.resource_dataset_cache import make_canonical_oee_query_id
        from mes_dashboard.core.query_spool_store import QUERY_SPOOL_DIR

        start_date = str(self.params.get("start_date", "")).strip()
        end_date = str(self.params.get("end_date", "")).strip()

        self._spool_key = make_canonical_oee_query_id(start_date, end_date)
        spool_dir = QUERY_SPOOL_DIR / "resource_oee"
        self._spool_path = str(spool_dir / f"{self._spool_key}.parquet")

        # Build whole-day time chunks (production window only;
        # reject window is widened per-chunk in build_chunk_sql)
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
        """Return (sql, binds) for a single day chunk of oee_facts.sql.

        Each chunk's :reject_start/:reject_end is widened ±30d around the chunk's
        production dates to capture NG events that fall outside the chunk boundary
        but match trackout events within it (highest-risk seam item).
        """
        from mes_dashboard.sql import SQLLoader

        sql = SQLLoader.load("resource_history/oee_facts")

        chunk_start = chunk_params["start_date"]
        chunk_end = chunk_params["end_date"]

        chunk_start_dt = datetime.strptime(chunk_start, "%Y-%m-%d")
        chunk_end_dt = datetime.strptime(chunk_end, "%Y-%m-%d")

        reject_start = (chunk_start_dt - timedelta(days=_REJECT_WINDOW_DAYS)).strftime("%Y-%m-%d")
        reject_end = (chunk_end_dt + timedelta(days=_REJECT_WINDOW_DAYS)).strftime("%Y-%m-%d")

        bind_params: Dict[str, Any] = {
            "start_date": chunk_start,
            "end_date": chunk_end,
            "reject_start": reject_start,
            "reject_end": reject_end,
        }
        return sql, bind_params

    def post_aggregate(self, job_duckdb_path: "str | None") -> str:
        """Run GROUP BY EQUIPMENTID ratio-of-SUMs in job-temp DuckDB; COPY to resource_oee spool.

        The raw table in job_duckdb_path contains all chunk rows
        (EQUIPMENTID, SHIFT_DATE, TRACKOUT_QTY, NG_QTY).
        Final aggregation mirrors legacy export_csv iterrows formulas:
          yield_pct = ΣTRACKOUT / (ΣTRACKOUT + ΣNG)  (ratio-of-SUMs, not avg-of-ratios)
        The base job's availability formula (PRD+SBY+EGT / total) is computed at CSV stitch
        time in the route; the OEE spool stores the raw SUM columns for the join.
        """
        import duckdb

        spool_path = self._spool_path
        os.makedirs(os.path.dirname(spool_path), exist_ok=True)

        # Aggregate raw table: SUM per EQUIPMENTID across all chunks
        _AGG_SQL = """
SELECT
    EQUIPMENTID,
    SUM(TRACKOUT_QTY)  AS TRACKOUT_QTY,
    SUM(NG_QTY)        AS NG_QTY
FROM raw
GROUP BY EQUIPMENTID
ORDER BY EQUIPMENTID
"""
        if job_duckdb_path is None:
            raise RuntimeError(
                "ResourceHistoryOeeJob.post_aggregate: job_duckdb_path is None "
                "(requires_cross_chunk_reduction=True must provide a DuckDB path)"
            )

        con = duckdb.connect(job_duckdb_path)
        try:
            # Check if raw table exists and has rows
            try:
                row_check = con.execute("SELECT COUNT(*) FROM raw").fetchone()
                raw_count = row_check[0] if row_check else 0
            except Exception:
                raw_count = 0

            if raw_count == 0:
                # Write empty parquet with correct legacy schema
                con.execute(
                    f"COPY (SELECT CAST(NULL AS VARCHAR) AS EQUIPMENTID, "
                    f"CAST(NULL AS DOUBLE) AS TRACKOUT_QTY, "
                    f"CAST(NULL AS DOUBLE) AS NG_QTY "
                    f"WHERE FALSE) "
                    f"TO '{spool_path}' (FORMAT PARQUET, CODEC 'SNAPPY')"
                )
                row_count = 0
            else:
                con.execute(
                    f"COPY ({_AGG_SQL}) TO '{spool_path}' (FORMAT PARQUET, CODEC 'SNAPPY')"
                )
                row_count = con.execute(
                    f"SELECT COUNT(*) FROM read_parquet('{spool_path}')"
                ).fetchone()[0]
        finally:
            con.close()

        logger.info(
            "ResourceHistoryOeeJob.post_aggregate: parquet written path=%s rows=%d job_id=%s",
            spool_path, row_count, self.job_id,
        )

        try:
            from mes_dashboard.core.query_spool_store import register_spool_file
            from mes_dashboard.services.resource_dataset_cache import _get_cache_ttl
            ttl = _get_cache_ttl(str(self.params.get("end_date", "")))
            register_spool_file(
                "resource_oee", self._spool_key, Path(spool_path),
                row_count, ttl_seconds=ttl,
            )
        except Exception as reg_exc:
            logger.warning(
                "ResourceHistoryOeeJob.post_aggregate: spool registration failed: %s", reg_exc
            )

        return spool_path

    def progress_report(self, pct: int) -> None:
        """Report progress via async_query_job_service (lazy import to avoid circular)."""
        from mes_dashboard.services.async_query_job_service import update_job_progress
        update_job_progress(_JOB_PREFIX, self.job_id, pct=str(pct))


def execute_resource_history_oee_job(
    job_id: str,
    params: dict,
) -> None:
    """RQ entry point for ResourceHistoryOeeJob (RESOURCE_HISTORY_USE_UNIFIED_JOB=on path).

    Called by RQ worker process.  Creates ResourceHistoryOeeJob and runs the template method.
    """
    from mes_dashboard.rq_worker_preload import ensure_rq_logging
    ensure_rq_logging()

    from mes_dashboard.services.async_query_job_service import complete_job

    logger.info("execute_resource_history_oee_job: started job_id=%s", job_id)
    try:
        job = ResourceHistoryOeeJob(job_id=job_id, params=params)
        spool_path = job.run()
        complete_job(_JOB_PREFIX, job_id, query_id=job._spool_key)
        logger.info(
            "execute_resource_history_oee_job: completed job_id=%s spool_path=%s",
            job_id, spool_path,
        )
    except Exception as exc:
        logger.error(
            "execute_resource_history_oee_job: failed job_id=%s: %s",
            job_id, exc, exc_info=True,
        )
        complete_job(_JOB_PREFIX, job_id, error=str(exc))
        raise


# ── Central job registry ───────────────────────────────────────────────────────
from mes_dashboard.services.job_registry import JobTypeConfig, register_job_type  # noqa: E402

register_job_type(JobTypeConfig(
    job_type="resource-history-oee",
    queue_name=RESOURCE_WORKER_QUEUE,
    worker_fn=execute_resource_history_oee_job,
    timeout_seconds=RESOURCE_OEE_JOB_TIMEOUT_SECONDS,
    ttl_seconds=RESOURCE_OEE_JOB_TTL_SECONDS,
    always_async=True,
))
