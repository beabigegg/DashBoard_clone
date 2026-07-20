# -*- coding: utf-8 -*-
"""Production Achievement Rate -- MOVE-OUT (轉出) source RQ worker
(BaseChunkedDuckDBJob unified path, production-achievement-moveout, PA-18).

Entry point: execute_production_achievement_moveout_unified_job(job_id, params)

The 轉出 counterpart to production_achievement_worker.py. Structurally
identical (TIME chunks + one D6 closing chunk + seam-safe post_aggregate
re-aggregation); only the SQL template, the spool namespace, the spool grain
(raw_workcenter_group instead of SPECNAME), and the job_type differ.

  - Subclasses BaseChunkedDuckDBJob (same as ProductionAchievementJob).
  - ChunkStrategy.TIME: one Oracle query per whole-day TXNDATE boundary of
    sql/production_achievement_moveout.sql.
  - post_aggregate re-aggregates (GROUP BY output_date, shift_code,
    raw_workcenter_group, PACKAGE_LF SUM(actual_output_qty)) across chunk
    parquets -- required because PA-03's overnight-tail attribution and the D6
    closing chunk both let a single (output_date, shift_code,
    raw_workcenter_group, PACKAGE_LF) group draw TXNDATE rows from both sides
    of a calendar-midnight chunk seam.
  - always_async=True: no synchronous fallback.
  - Canonical spool key: date-range + source='moveout'
    (services.production_achievement_service.make_canonical_pa_spool_id).
  - SAME RQ queue as the 產出 worker (production-achievement-query): the RQ
    worker process dequeues by QUEUE name, not job_type, so a second job_type
    on the same queue needs NO new deploy/*.service and NO start_server.sh
    change (that requirement is only triggered by opening a NEW queue).

Module-level register_job_type() fires at import time (job-registry-central).
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

from mes_dashboard.core.base_chunked_duckdb_job import BaseChunkedDuckDBJob, ChunkStrategy

logger = logging.getLogger("mes_dashboard.production_achievement_moveout_worker")

# Same queue as the 產出 worker on purpose (see module docstring).
PRODUCTION_ACHIEVEMENT_WORKER_QUEUE: str = os.getenv(
    "PRODUCTION_ACHIEVEMENT_WORKER_QUEUE", "production-achievement-query"
)
PRODUCTION_ACHIEVEMENT_JOB_TIMEOUT_SECONDS: int = max(
    60, int(os.getenv("PRODUCTION_ACHIEVEMENT_JOB_TIMEOUT_SECONDS", "1800"))
)

# job_type / status_url prefix (hyphen) -- distinct from the spool namespace
# (underscore). Do not conflate.
_JOB_PREFIX = "production-achievement-moveout"
_SOURCE = "moveout"

from mes_dashboard.services.production_achievement_service import (  # noqa: E402
    PRODUCTION_ACHIEVEMENT_MOVEOUT_SPOOL_NAMESPACE as _NAMESPACE,
)


class ProductionAchievementMoveoutJob(BaseChunkedDuckDBJob):
    """Unified chunked Oracle->DuckDB job for the 轉出 (move-out) source.

    ChunkStrategy: TIME (one Oracle query per whole-day TXNDATE boundary).
    requires_cross_chunk_reduction=False, but post_aggregate re-aggregates
    across chunk parquets -- see module docstring "chunk-seam correctness".

    Output namespace: production_achievement_moveout (data-shape-contract.md
    §3.28, moveout variant -- grain raw_workcenter_group, not SPECNAME).
    """

    namespace = _NAMESPACE
    chunk_strategy = ChunkStrategy.TIME
    requires_cross_chunk_reduction = False

    def __init__(self, job_id: str, params: dict) -> None:
        super().__init__(job_id)
        self.params = params
        self._spool_key: str = ""
        self._spool_path: str = ""
        self._query_started_at: "float | None" = None

    def pre_query(self) -> None:
        """Parse start_date/end_date, compute the canonical spool key, and
        build daily TIME chunks plus one D6 closing chunk (PA-15).

        D6/PA-15 fetch-completeness fix: same rationale as the 產出 worker --
        a date-only ``chunk_end_excl`` bind (implicit midnight) never fetched
        the overnight N-shift tail ``[end_date+1 00:00:00, end_date+1
        07:30:00)`` that PA-03 attributes back to ``end_date``. Every chunk's
        ``chunk_end_excl`` is formatted as a full datetime to match the widened
        Oracle format mask; ``start_date`` stays date-only (always midnight).
        """
        from mes_dashboard.services.production_achievement_service import (
            make_canonical_pa_spool_id,
        )
        from mes_dashboard.core.query_spool_store import QUERY_SPOOL_DIR, set_inflight_state

        start_date = str(self.params.get("start_date", "")).strip()
        end_date = str(self.params.get("end_date", "")).strip()

        self._spool_key = make_canonical_pa_spool_id(start_date, end_date, source=_SOURCE)
        spool_dir = QUERY_SPOOL_DIR / _NAMESPACE
        self._spool_path = str(spool_dir / f"{self._spool_key}.parquet")

        # Race-condition fix (query_spool_store's CAS write, see
        # post_aggregate below): record the wall-clock time THIS job started
        # querying Oracle for this spool key, and publish inflight state so
        # the warmup scheduler (production_achievement_daily_cache.py) can
        # avoid enqueuing a duplicate concurrent job for the same key.
        self._query_started_at = time.time()
        set_inflight_state(
            _NAMESPACE, self._spool_key,
            {"started_at": self._query_started_at, "job_id": self.job_id},
        )

        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        chunks: List[Dict[str, Any]] = []
        current = start_dt
        while current <= end_dt:
            chunk_end_excl_dt = current + timedelta(days=1)
            chunks.append({
                "start_date": current.strftime("%Y-%m-%d"),
                "chunk_end_excl": chunk_end_excl_dt.strftime("%Y-%m-%d %H:%M:%S"),
            })
            current += timedelta(days=1)

        # D6/PA-15: one narrow closing chunk for end_date's overnight N-shift
        # tail. Non-overlapping with the last regular chunk; post_aggregate's
        # GROUP BY folds both into the same (end_date, 'N', ...) group.
        closing_start_dt = end_dt + timedelta(days=1)
        closing_end_excl_dt = closing_start_dt + timedelta(hours=7, minutes=30)
        chunks.append({
            "start_date": closing_start_dt.strftime("%Y-%m-%d"),
            "chunk_end_excl": closing_end_excl_dt.strftime("%Y-%m-%d %H:%M:%S"),
        })

        self._chunks = chunks

    def build_chunk_sql(self, chunk_params: dict) -> tuple[str, dict]:
        """Return (sql, binds) for a single day chunk of
        production_achievement_moveout.sql (no structural placeholders)."""
        from mes_dashboard.sql import SQLLoader

        sql = SQLLoader.load("production_achievement_moveout")
        bind_params: Dict[str, Any] = {
            "start_date": chunk_params["start_date"],
            "chunk_end_excl": chunk_params["chunk_end_excl"],
        }
        return sql, bind_params

    def post_aggregate(self, job_duckdb_path: "str | None") -> str:
        """Re-aggregate all chunk parquets into the canonical
        raw_workcenter_group+PACKAGE_LF-grain spool via ``GROUP BY output_date,
        shift_code, raw_workcenter_group, PACKAGE_LF SUM(actual_output_qty)`` --
        seam-safe merge (mirrors ProductionAchievementJob.post_aggregate, but
        the grain column is raw_workcenter_group (FROMWORKCENTER) not SPECNAME).

        Empty/no-parquet window still writes a VALID empty parquet with the
        canonical 5-column schema.
        """
        import duckdb

        chunk_dir = self._make_chunk_parquet_dir(self.job_id)
        all_parquets = sorted(chunk_dir.glob("chunk-*.parquet"))

        spool_path = self._spool_path
        os.makedirs(os.path.dirname(spool_path), exist_ok=True)

        if not all_parquets:
            import pyarrow as pa
            import pyarrow.parquet as pq

            schema = pa.schema([
                pa.field("output_date", pa.date32()),
                pa.field("shift_code", pa.string()),
                pa.field("raw_workcenter_group", pa.string()),
                pa.field("PACKAGE_LF", pa.string()),
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
            latest_data_ts = None
        else:
            parquet_glob = str(chunk_dir / "chunk-*.parquet")
            con = duckdb.connect()
            try:
                con.execute(
                    "COPY ("
                    "  SELECT"
                    "    CAST(OUTPUT_DATE AS DATE) AS output_date,"
                    "    SHIFT_CODE AS shift_code,"
                    "    RAW_WORKCENTER_GROUP AS raw_workcenter_group,"
                    "    PACKAGE_LF,"
                    "    SUM(ACTUAL_OUTPUT_QTY) AS actual_output_qty"
                    f"  FROM read_parquet('{parquet_glob}')"
                    "  GROUP BY OUTPUT_DATE, SHIFT_CODE, RAW_WORKCENTER_GROUP, PACKAGE_LF"
                    f") TO '{spool_path}' (FORMAT PARQUET, CODEC 'SNAPPY')"
                )
                row_count = con.execute(
                    f"SELECT COUNT(*) FROM read_parquet('{spool_path}')"
                ).fetchone()[0]
                # Data-freshness indicator (UI "資料最新一筆時間") -- global max
                # across ALL chunk parquets for this job, NOT part of the
                # canonical 5-column spool schema itself (data-shape-contract
                # lock); carried out-of-band via register_spool_file's
                # extra_metadata below.
                max_ts_row = con.execute(
                    f"SELECT MAX(MAX_TXN_TS) FROM read_parquet('{parquet_glob}')"
                ).fetchone()
                max_ts = max_ts_row[0] if max_ts_row else None
                latest_data_ts = max_ts.strftime("%Y-%m-%d %H:%M:%S") if max_ts is not None else None
            finally:
                con.close()

        logger.info(
            "ProductionAchievementMoveoutJob.post_aggregate: parquet written path=%s rows=%d job_id=%s",
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
                extra_metadata={
                    "latest_data_ts": latest_data_ts,
                    "query_started_at": self._query_started_at,
                },
                cas_field="query_started_at",
                cas_value=self._query_started_at,
            )
        except Exception as reg_exc:
            logger.warning(
                "ProductionAchievementMoveoutJob.post_aggregate: spool registration failed: %s",
                reg_exc,
            )

        # Job is done regardless of whether register_spool_file's write won
        # or lost the CAS race -- always clear inflight state so the warmup
        # scheduler's duplicate-job guard (production_achievement_daily_cache.py)
        # never wedges on a stale "still running" marker. No try/finally
        # around the above: on an unhandled exception this simply never
        # runs, and inflight state's own TTL (_INFLIGHT_KEY_TTL_SECONDS)
        # self-expires within 5 minutes -- an accepted tradeoff, not a leak.
        from mes_dashboard.core.query_spool_store import clear_inflight_state
        clear_inflight_state(_NAMESPACE, self._spool_key)

        return spool_path

    def progress_report(self, pct: int) -> None:
        """Report progress via async_query_job_service (lazy import)."""
        from mes_dashboard.services.async_query_job_service import update_job_progress
        update_job_progress(_JOB_PREFIX, self.job_id, pct=str(pct))


def execute_production_achievement_moveout_unified_job(
    job_id: str,
    params: dict,
) -> None:
    """RQ entry point for ProductionAchievementMoveoutJob.

    Heavy-query slot is acquired automatically inside BaseChunkedDuckDBJob.run()
    -- do NOT acquire it here again.
    """
    from mes_dashboard.rq_worker_preload import ensure_rq_logging
    ensure_rq_logging()

    from mes_dashboard.services.async_query_job_service import complete_job

    logger.info("execute_production_achievement_moveout_unified_job: started job_id=%s", job_id)
    try:
        job = ProductionAchievementMoveoutJob(job_id=job_id, params=params)
        spool_path = job.run()
        complete_job(_JOB_PREFIX, job_id, query_id=job._spool_key)
        logger.info(
            "execute_production_achievement_moveout_unified_job: completed job_id=%s spool_path=%s",
            job_id, spool_path,
        )
    except Exception as exc:
        logger.error(
            "execute_production_achievement_moveout_unified_job: failed job_id=%s: %s",
            job_id, exc, exc_info=True,
        )
        complete_job(_JOB_PREFIX, job_id, error=str(exc))
        raise


# ── Central job registry ───────────────────────────────────────────────────────
from mes_dashboard.services.job_registry import JobTypeConfig, register_job_type  # noqa: E402

register_job_type(JobTypeConfig(
    job_type=_JOB_PREFIX,
    queue_name=PRODUCTION_ACHIEVEMENT_WORKER_QUEUE,
    worker_fn=execute_production_achievement_moveout_unified_job,
    timeout_seconds=PRODUCTION_ACHIEVEMENT_JOB_TIMEOUT_SECONDS,
    always_async=True,
))
