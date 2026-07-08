# -*- coding: utf-8 -*-
"""Production Achievement Rate RQ worker (BaseChunkedDuckDBJob unified path,
production-achievement-async-spool, ADR-0016).

Entry point: execute_production_achievement_unified_job(job_id, params)

Design:
  - Subclasses BaseChunkedDuckDBJob (mirrors resource_history_base_worker.py).
  - ChunkStrategy.TIME: one Oracle query per whole-day TRACKOUTTIMESTAMP
    boundary of sql/production_achievement.sql (PA-05 predicate reused
    verbatim; change-request §Non-goals).
  - requires_cross_chunk_reduction=False: sql/production_achievement.sql
    already GROUP BYs server-side per chunk, so per-chunk parquets are each
    independently correct for THEIR OWN chunk window -- BUT PA-03/PA-04's
    previous-day "N"/"C" shift-tail attribution rule means a single
    (output_date, shift_code, SPECNAME) group can draw TRACKOUTTIMESTAMP rows
    from BOTH sides of a calendar-midnight chunk seam (the tail's
    TRACKOUTTIMESTAMP falls in the NEXT calendar day's chunk even though its
    output_date attributes to the PREVIOUS day). post_aggregate therefore
    MUST re-aggregate (GROUP BY output_date, shift_code, SPECNAME
    SUM(actual_output_qty)) across ALL chunk parquets rather than a plain
    concat, or the spool would contain duplicate keys for seam-straddling
    groups (design.md "Chunk-seam correctness (RESOLVED)", ADR-0016).
  - always_async=True: no synchronous fallback (pre-launch clean replacement;
    env-contract.md PRODUCTION_ACHIEVEMENT_USE_UNIFIED_JOB is a pure kill
    switch, not a dual-path selector).
  - Canonical spool key: date-range only
    (services.production_achievement_service.make_canonical_pa_spool_id) --
    shift_code/workcenter_group narrowing happens client-side and never
    re-triggers an Oracle fetch (data-shape-contract.md §3.28).
  - Heavy-query slot is INHERITED from BaseChunkedDuckDBJob.run() -- this
    module never re-acquires the semaphore a second time.

Module-level register_job_type() fires at import time (job-registry-central).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

from mes_dashboard.core.base_chunked_duckdb_job import BaseChunkedDuckDBJob, ChunkStrategy

logger = logging.getLogger("mes_dashboard.production_achievement_worker")

PRODUCTION_ACHIEVEMENT_WORKER_QUEUE: str = os.getenv(
    "PRODUCTION_ACHIEVEMENT_WORKER_QUEUE", "production-achievement-query"
)
PRODUCTION_ACHIEVEMENT_JOB_TIMEOUT_SECONDS: int = max(
    60, int(os.getenv("PRODUCTION_ACHIEVEMENT_JOB_TIMEOUT_SECONDS", "1800"))
)
# No dedicated PRODUCTION_ACHIEVEMENT_JOB_TTL_SECONDS env var (env-contract.md
# documents only the 3 vars above) -- JobTypeConfig.ttl_seconds default
# (3600s) is used below.

# job_type / status_url prefix (hyphen) -- distinct from the spool namespace
# / _ALLOWED_NAMESPACES / spool-path segment (underscore). Do not conflate.
_JOB_PREFIX = "production-achievement"
_NAMESPACE = "production_achievement"


class ProductionAchievementJob(BaseChunkedDuckDBJob):
    """Unified chunked Oracle→DuckDB job for Production Achievement Rate.

    ChunkStrategy: TIME (one Oracle query per whole-day TRACKOUTTIMESTAMP
    boundary). requires_cross_chunk_reduction=False, but post_aggregate
    re-aggregates (GROUP BY output_date, shift_code, SPECNAME
    SUM(actual_output_qty)) across chunk parquets -- see module docstring
    "Chunk-seam correctness". This is this worker's differentiator from the
    plain-concat resource_history_base_worker.py post_aggregate.

    Output namespace: production_achievement (data-shape-contract.md §3.28).
    """

    namespace = _NAMESPACE
    chunk_strategy = ChunkStrategy.TIME
    requires_cross_chunk_reduction = False
    max_parallel = 3

    def __init__(self, job_id: str, params: dict) -> None:
        super().__init__(job_id)
        self.params = params
        self._spool_key: str = ""
        self._spool_path: str = ""

    def pre_query(self) -> None:
        """Parse start_date/end_date, compute the canonical spool key, and
        build daily TIME chunks (mirrors resource_history_base_worker.py)."""
        from mes_dashboard.services.production_achievement_service import (
            make_canonical_pa_spool_id,
        )
        from mes_dashboard.core.query_spool_store import QUERY_SPOOL_DIR

        start_date = str(self.params.get("start_date", "")).strip()
        end_date = str(self.params.get("end_date", "")).strip()

        self._spool_key = make_canonical_pa_spool_id(start_date, end_date)
        spool_dir = QUERY_SPOOL_DIR / _NAMESPACE
        self._spool_path = str(spool_dir / f"{self._spool_key}.parquet")

        # Build whole-day TIME chunks: TRACKOUTTIMESTAMP in [start_date, chunk_end_excl).
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        chunks: List[Dict[str, Any]] = []
        current = start_dt
        while current <= end_dt:
            chunk_end_excl_dt = current + timedelta(days=1)
            chunks.append({
                "start_date": current.strftime("%Y-%m-%d"),
                "chunk_end_excl": chunk_end_excl_dt.strftime("%Y-%m-%d"),
            })
            current += timedelta(days=1)
        self._chunks = chunks

    def build_chunk_sql(self, chunk_params: dict) -> tuple[str, dict]:
        """Return (sql, binds) for a single day chunk of production_achievement.sql.

        PA-05 predicate is reused verbatim (change-request §Non-goals);
        CONTAINERNAME_FILTER is not used on this async path (always "").
        """
        from mes_dashboard.sql import SQLLoader

        sql = SQLLoader.load_with_params(
            "production_achievement", CONTAINERNAME_FILTER=""
        )
        bind_params: Dict[str, Any] = {
            "start_date": chunk_params["start_date"],
            "chunk_end_excl": chunk_params["chunk_end_excl"],
        }
        return sql, bind_params

    def post_aggregate(self, job_duckdb_path: "str | None") -> str:
        """Re-aggregate all chunk parquets into the canonical SPECNAME-grain
        spool via ``GROUP BY output_date, shift_code, SPECNAME
        SUM(actual_output_qty)`` -- seam-safe merge (ADR-0016; NOT a plain
        concat, see module docstring "Chunk-seam correctness").

        Empty/no-parquet (or all-unmapped) window still writes a VALID empty
        parquet with the exact data-shape-contract.md §3.28.1 schema.
        """
        import duckdb

        chunk_dir = self._make_chunk_parquet_dir(self.job_id)
        all_parquets = sorted(chunk_dir.glob("chunk-*.parquet"))

        spool_path = self._spool_path
        os.makedirs(os.path.dirname(spool_path), exist_ok=True)

        if not all_parquets:
            # No qualifying rows in any chunk -- write empty parquet with the
            # canonical §3.28.1 schema (empty-result invariant).
            import pyarrow as pa
            import pyarrow.parquet as pq

            schema = pa.schema([
                pa.field("output_date", pa.date32()),
                pa.field("shift_code", pa.string()),
                pa.field("SPECNAME", pa.string()),
                pa.field("actual_output_qty", pa.int64()),
            ])
            pq.write_table(
                pa.table(
                    {f: pa.array([], type=schema.field(f).type) for f in schema.names},
                    schema=schema,
                ),
                spool_path,
                compression="snappy",
            )
            row_count = 0
        else:
            parquet_glob = str(chunk_dir / "chunk-*.parquet")
            con = duckdb.connect()
            try:
                # Re-aggregate across ALL chunk parquets -- collapses any
                # (output_date, shift_code, SPECNAME) group that straddled a
                # calendar-midnight chunk seam into a single SUMmed row
                # (chunk-seam correctness -- design.md, ADR-0016).
                con.execute(
                    "COPY ("
                    "  SELECT"
                    "    CAST(OUTPUT_DATE AS DATE) AS output_date,"
                    "    SHIFT_CODE AS shift_code,"
                    "    SPECNAME,"
                    "    SUM(ACTUAL_OUTPUT_QTY) AS actual_output_qty"
                    f"  FROM read_parquet('{parquet_glob}')"
                    "  GROUP BY OUTPUT_DATE, SHIFT_CODE, SPECNAME"
                    f") TO '{spool_path}' (FORMAT PARQUET, CODEC 'SNAPPY')"
                )
                row_count = con.execute(
                    f"SELECT COUNT(*) FROM read_parquet('{spool_path}')"
                ).fetchone()[0]
            finally:
                con.close()

        logger.info(
            "ProductionAchievementJob.post_aggregate: parquet written path=%s rows=%d job_id=%s",
            spool_path, row_count, self.job_id,
        )

        try:
            from mes_dashboard.core.query_spool_store import (
                register_spool_file,
                QUERY_SPOOL_TTL_SECONDS,
            )
            register_spool_file(
                _NAMESPACE, self._spool_key, Path(spool_path),
                row_count, ttl_seconds=QUERY_SPOOL_TTL_SECONDS,
            )
        except Exception as reg_exc:
            logger.warning(
                "ProductionAchievementJob.post_aggregate: spool registration failed: %s",
                reg_exc,
            )

        return spool_path

    def progress_report(self, pct: int) -> None:
        """Report progress via async_query_job_service (lazy import to avoid circular)."""
        from mes_dashboard.services.async_query_job_service import update_job_progress
        update_job_progress(_JOB_PREFIX, self.job_id, pct=str(pct))


def execute_production_achievement_unified_job(
    job_id: str,
    params: dict,
) -> None:
    """RQ entry point for ProductionAchievementJob (PRODUCTION_ACHIEVEMENT_USE_UNIFIED_JOB=on path).

    Called by the RQ worker process. Creates ProductionAchievementJob and
    runs the template method. Heavy-query slot is acquired automatically
    inside BaseChunkedDuckDBJob.run() -- do NOT acquire it here again.
    """
    from mes_dashboard.rq_worker_preload import ensure_rq_logging
    ensure_rq_logging()

    from mes_dashboard.services.async_query_job_service import complete_job

    logger.info("execute_production_achievement_unified_job: started job_id=%s", job_id)
    try:
        job = ProductionAchievementJob(job_id=job_id, params=params)
        spool_path = job.run()
        complete_job(_JOB_PREFIX, job_id, query_id=job._spool_key)
        logger.info(
            "execute_production_achievement_unified_job: completed job_id=%s spool_path=%s",
            job_id, spool_path,
        )
    except Exception as exc:
        logger.error(
            "execute_production_achievement_unified_job: failed job_id=%s: %s",
            job_id, exc, exc_info=True,
        )
        complete_job(_JOB_PREFIX, job_id, error=str(exc))
        raise


# ── Central job registry ───────────────────────────────────────────────────────
from mes_dashboard.services.job_registry import JobTypeConfig, register_job_type  # noqa: E402

register_job_type(JobTypeConfig(
    job_type=_JOB_PREFIX,
    queue_name=PRODUCTION_ACHIEVEMENT_WORKER_QUEUE,
    worker_fn=execute_production_achievement_unified_job,
    timeout_seconds=PRODUCTION_ACHIEVEMENT_JOB_TIMEOUT_SECONDS,
    always_async=True,
))
