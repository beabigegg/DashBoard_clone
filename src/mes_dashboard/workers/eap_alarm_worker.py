# -*- coding: utf-8 -*-
"""EAP ALARM RQ worker.

Entry point: run_eap_alarm_query_job(job_id, date_from, date_to, machines)

Design:
  - Oracle connections POST-FORK (ADR-0004).
  - Fetches all EQP_SECS_ALARM events (SET + CLEAR) via read_sql_df_slow.
  - Registers Oracle results in DuckDB in-memory; all transformation
    (EAV pivot, SET/CLEAR pairing, DURATION) done in SQL — no pandas ops.
  - Writes parquet with DuckDB COPY TO.
  - SECS/GEM ALCD signed-byte convention:
      AlarmCode < 0  → bit7=1 → Alarm SET (start)
      AlarmCode >= 0 → bit7=0 → Alarm CLEAR (end)
    Pairing key: (EQP_ID, ALARM_ID); each output row = one alarm occurrence.
    Unpaired SET → ALARM_END=NULL, DURATION_SECONDS=NULL.
    CLEAR with no preceding SET in window → dropped.
    Events with no AlarmCode in detail → treated as SET.

Module-level register_job_type() fires at import time (job-registry-central).
"""

from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

from mes_dashboard.core.base_chunked_duckdb_job import BaseChunkedDuckDBJob, ChunkStrategy

logger = logging.getLogger("mes_dashboard.eap_alarm_worker")

EAP_ALARM_JOB_TIMEOUT_SECONDS: int = max(
    60, int(os.getenv("EAP_ALARM_JOB_TIMEOUT_SECONDS", "1800"))
)
EAP_ALARM_WORKER_QUEUE: str = os.getenv("EAP_ALARM_WORKER_QUEUE", "eap-alarm-query")
EAP_ALARM_JOB_TTL_SECONDS: int = max(
    3600, int(os.getenv("EAP_ALARM_SPOOL_TTL", "72000"))
)

_JOB_PREFIX = "eap-alarm"

# ── Oracle SQL templates ───────────────────────────────────────────────────────

_EAP_EVENT_SQL_TEMPLATE = """\
SELECT
    TO_CHAR(e.SEQ_ID)              AS EVENT_ID,
    e.EQUIPMENT_ID                 AS EQP_ID,
    SUBSTR(e.EQUIPMENT_ID, 1, 4)   AS EQP_TYPE,
    e.LOT_ID,
    e.EVENT_NAME                   AS ALARM_ID,
    e.LAST_UPDATE_TIME             AS ALARM_TIME
FROM DWH.EAP_EVENT e
WHERE e.LAST_UPDATE_TIME BETWEEN TO_DATE(:date_from, 'YYYY-MM-DD')
                              AND TO_DATE(:date_to,   'YYYY-MM-DD') + 1
  AND {equipment_filter}
  AND e.EVENT_TYPE = 'EQP_SECS_ALARM'
"""

_DETAIL_SQL_TEMPLATE = """\
SELECT TO_CHAR(e.SEQ_ID) AS EVENT_ID,
       d.PARAMETER_NAME,
       d.PARAMETER_VALUE
FROM DWH.EAP_EVENT e
JOIN DWH.EAP_EVENT_DETAIL d ON d.SEQ_ID = e.SEQ_ID
WHERE e.LAST_UPDATE_TIME BETWEEN TO_DATE(:date_from, 'YYYY-MM-DD')
                              AND TO_DATE(:date_to,   'YYYY-MM-DD') + 1
  AND {equipment_filter}
  AND e.EVENT_TYPE = 'EQP_SECS_ALARM'
"""

# ── DuckDB pairing query ───────────────────────────────────────────────────────
# Registers two tables:
#   events_raw   — from Oracle main query (EVENT_ID, EQP_ID, ...)
#   detail_pivot — pre-pivoted in Python (EVENT_ID, ALARM_CODE_STR,
#                  ALARM_TEXT_DETAIL, DETAIL_PARAMS)
# Produces one row per alarm occurrence (SET + optional CLEAR pair).
_PAIR_SQL = """\
WITH events AS (
    SELECT
        e.EVENT_ID,
        e.EQP_ID,
        e.EQP_TYPE,
        e.LOT_ID,
        e.ALARM_ID,
        COALESCE(d.ALARM_TEXT_DETAIL, e.ALARM_ID)       AS ALARM_TEXT,
        TRY_CAST(d.ALARM_CODE_STR AS INTEGER)            AS ALARM_CODE,
        CASE WHEN d.ALARM_CODE_STR IS NULL
                  OR TRY_CAST(d.ALARM_CODE_STR AS INTEGER) < 0
             THEN TRUE ELSE FALSE END                    AS IS_SET,
        CASE WHEN d.ALARM_CODE_STR IS NOT NULL
             THEN ABS(TRY_CAST(d.ALARM_CODE_STR AS INTEGER)) & 127 END AS ALARM_CATEGORY_CODE,
        d.DETAIL_PARAMS,
        e.ALARM_TIME
    FROM events_raw e
    LEFT JOIN detail_pivot d ON d.EVENT_ID = e.EVENT_ID
),
set_events AS (
    SELECT * FROM events WHERE IS_SET
),
clear_events AS (
    SELECT EQP_ID, ALARM_ID, ALARM_TIME AS CLEAR_TIME
    FROM events WHERE NOT IS_SET
),
paired AS (
    SELECT
        s.ALARM_ID,
        s.EQP_ID,
        s.EQP_TYPE,
        s.LOT_ID,
        s.ALARM_TEXT,
        s.ALARM_CATEGORY_CODE,
        s.ALARM_TIME                AS ALARM_START,
        MIN(c.CLEAR_TIME)           AS ALARM_END,
        s.DETAIL_PARAMS,
        s.EVENT_ID
    FROM set_events s
    LEFT JOIN clear_events c
           ON c.EQP_ID    = s.EQP_ID
          AND c.ALARM_ID  = s.ALARM_ID
          AND c.CLEAR_TIME > s.ALARM_TIME
    GROUP BY
        s.EVENT_ID, s.ALARM_ID, s.EQP_ID, s.EQP_TYPE, s.LOT_ID,
        s.ALARM_TEXT, s.ALARM_CATEGORY_CODE, s.ALARM_TIME, s.DETAIL_PARAMS
)
SELECT
    ALARM_ID,
    EQP_ID,
    EQP_TYPE,
    LOT_ID,
    ALARM_TEXT,
    ALARM_CATEGORY_CODE,
    ALARM_START,
    ALARM_END,
    CASE WHEN ALARM_END IS NOT NULL
         THEN epoch(CAST(ALARM_END AS TIMESTAMP)) - epoch(CAST(ALARM_START AS TIMESTAMP))
    END                             AS DURATION_SECONDS,
    DETAIL_PARAMS,
    '{machines_hash}'               AS eqp_types_filter
FROM paired
ORDER BY ALARM_START DESC
"""


def _build_equipment_filter(machines: List[str]) -> tuple[str, Dict[str, Any]]:
    _ORACLE_IN_LIMIT = 999
    eqp_params: Dict[str, Any] = {}
    if len(machines) <= _ORACLE_IN_LIMIT:
        placeholders = ", ".join(f":r{i}" for i in range(len(machines)))
        return f"e.EQUIPMENT_ID IN ({placeholders})", {f"r{i}": m for i, m in enumerate(machines)}
    clauses: List[str] = []
    offset = 0
    for chunk_start in range(0, len(machines), _ORACLE_IN_LIMIT):
        chunk = machines[chunk_start:chunk_start + _ORACLE_IN_LIMIT]
        ph = ", ".join(f":r{offset + k}" for k in range(len(chunk)))
        clauses.append(f"e.EQUIPMENT_ID IN ({ph})")
        for k, m in enumerate(chunk):
            eqp_params[f"r{offset + k}"] = m
        offset += len(chunk)
    return "(" + " OR ".join(clauses) + ")", eqp_params


def run_eap_alarm_query_job(
    job_id: str,
    date_from: str,
    date_to: str,
    machines: List[str],
) -> None:
    """RQ worker: Oracle fetch → DuckDB in-memory pairing → parquet write."""
    import hashlib
    import duckdb

    from mes_dashboard.rq_worker_preload import ensure_rq_logging
    ensure_rq_logging()

    from mes_dashboard.services.async_query_job_service import complete_job, update_job_progress
    from mes_dashboard.services.eap_alarm_cache import (
        make_eap_alarm_spool_key,
        get_eap_alarm_spool_path,
        EAP_ALARM_SPOOL_TTL,
    )

    logger.info("eap_alarm_worker: job started job_id=%s", job_id)
    update_job_progress(_JOB_PREFIX, job_id, status="started", progress="initializing", pct="5")

    try:
        spool_key = make_eap_alarm_spool_key(date_from, date_to, machines)
        spool_path = get_eap_alarm_spool_path(spool_key)
        os.makedirs(os.path.dirname(spool_path), exist_ok=True)

        machines_hash = hashlib.sha256(
            ",".join(sorted(machines)).encode("utf-8")
        ).hexdigest()[:8]

        equipment_filter, eqp_params = _build_equipment_filter(machines)
        base_params: Dict[str, Any] = {"date_from": date_from, "date_to": date_to, **eqp_params}

        update_job_progress(_JOB_PREFIX, job_id, status="running", progress="querying Oracle", pct="15")

        from mes_dashboard.core.database import read_sql_df_slow

        events_df = read_sql_df_slow(
            _EAP_EVENT_SQL_TEMPLATE.format(equipment_filter=equipment_filter),
            params=base_params,
            timeout_seconds=EAP_ALARM_JOB_TIMEOUT_SECONDS,
            caller="eap_alarm_worker",
        )
        logger.info("eap_alarm_worker: Oracle returned %d events job_id=%s", len(events_df), job_id)

        update_job_progress(_JOB_PREFIX, job_id, status="running", progress="fetching detail", pct="30")

        try:
            detail_df = read_sql_df_slow(
                _DETAIL_SQL_TEMPLATE.format(equipment_filter=equipment_filter),
                params=base_params,
                timeout_seconds=EAP_ALARM_JOB_TIMEOUT_SECONDS,
                caller="eap_alarm_worker_detail",
            )
        except Exception as det_exc:
            logger.warning("eap_alarm_worker: detail fetch failed, proceeding without detail job_id=%s: %s", job_id, det_exc)
            import pandas as pd
            detail_df = pd.DataFrame(columns=["EVENT_ID", "PARAMETER_NAME", "PARAMETER_VALUE"])

        update_job_progress(_JOB_PREFIX, job_id, status="running", progress="pairing SET/CLEAR", pct="50")

        # ── Pre-pivot detail EAV in Python (avoids DuckDB version-specific agg) ──
        import json
        import pandas as pd

        if not detail_df.empty:
            records = []
            for eid, grp in detail_df.groupby("EVENT_ID"):
                d = dict(zip(grp["PARAMETER_NAME"], grp["PARAMETER_VALUE"]))
                records.append({
                    "EVENT_ID":          str(eid),
                    "ALARM_CODE_STR":    d.get("AlarmCode"),
                    "ALARM_TEXT_DETAIL": d.get("AlarmText"),
                    "DETAIL_PARAMS":     json.dumps(d, ensure_ascii=False),
                })
            detail_pivot_df = pd.DataFrame(records)
        else:
            detail_pivot_df = pd.DataFrame(
                columns=["EVENT_ID", "ALARM_CODE_STR", "ALARM_TEXT_DETAIL", "DETAIL_PARAMS"]
            )

        # ── DuckDB in-memory: register Oracle results, do all transformations ──
        con = duckdb.connect()
        try:
            con.register("events_raw", events_df)
            con.register("detail_pivot", detail_pivot_df)

            # Re-create directory immediately before write: the spool cleanup daemon
            # calls rmdir() on empty directories every ~5 min, so the directory
            # created at job-start can disappear during the long Oracle query phase.
            os.makedirs(os.path.dirname(spool_path), exist_ok=True)

            if events_df.empty:
                row_count = 0
                con.execute(f"COPY (SELECT * FROM ({_PAIR_SQL.format(machines_hash=machines_hash)}) t WHERE FALSE) TO '{spool_path}' (FORMAT PARQUET, CODEC 'SNAPPY')")
            else:
                pair_sql = _PAIR_SQL.format(machines_hash=machines_hash)
                update_job_progress(_JOB_PREFIX, job_id, status="running", progress="writing parquet", pct="90")
                con.execute(f"COPY ({pair_sql}) TO '{spool_path}' (FORMAT PARQUET, CODEC 'SNAPPY')")
                row_count = con.execute(f"SELECT COUNT(*) FROM read_parquet('{spool_path}')").fetchone()[0]
        finally:
            con.close()

        logger.info("eap_alarm_worker: parquet written path=%s rows=%d job_id=%s", spool_path, row_count, job_id)

        try:
            from mes_dashboard.core.query_spool_store import register_spool_file
            from pathlib import Path
            register_spool_file("eap_alarm", spool_key, Path(spool_path), row_count, ttl_seconds=EAP_ALARM_SPOOL_TTL)
        except Exception as reg_exc:
            logger.warning("eap_alarm_worker: spool registration failed: %s", reg_exc)

        update_job_progress(_JOB_PREFIX, job_id, status="running", progress="done", pct="100")
        complete_job(_JOB_PREFIX, job_id, query_id=spool_key)
        logger.info("eap_alarm_worker: job completed job_id=%s spool_key=%s", job_id, spool_key)

    except Exception as exc:
        logger.error("eap_alarm_worker: job failed job_id=%s: %s", job_id, exc, exc_info=True)
        complete_job(_JOB_PREFIX, job_id, error=str(exc))
        raise


class EapAlarmJob(BaseChunkedDuckDBJob):
    """Unified chunked Oracle→DuckDB job for EAP ALARM (BaseChunkedDuckDBJob template method).

    ChunkStrategy: TIME (one pair of Oracle queries per day: events + detail).
    requires_cross_chunk_reduction=False: SET/CLEAR pairing is deferred to post_aggregate
    which reads ALL chunk parquets together (ADR-0009, cross-seam safe).
    """

    namespace = "eap_alarm"
    chunk_strategy = ChunkStrategy.TIME
    requires_cross_chunk_reduction = False
    max_parallel = 3

    def __init__(self, job_id: str, params: dict) -> None:
        super().__init__(job_id)
        self.params = params
        self._spool_key: str = ""
        self._spool_path: str = ""
        self._machines_hash: str = ""
        self._equipment_filter: str = ""
        self._eqp_params: dict = {}
        self._machines: List[str] = []
        self._date_from: str = ""
        self._date_to: str = ""

    def pre_query(self) -> None:
        """Parse params, compute spool key, build daily chunk pairs."""
        date_from = str(self.params.get("date_from", "")).strip()
        date_to = str(self.params.get("date_to", "")).strip()
        machines = list(self.params.get("machines", []))

        self._date_from = date_from
        self._date_to = date_to
        self._machines = machines

        self._machines_hash = hashlib.sha256(
            ",".join(sorted(machines)).encode("utf-8")
        ).hexdigest()[:8]

        self._equipment_filter, self._eqp_params = _build_equipment_filter(machines)

        from mes_dashboard.services.eap_alarm_cache import make_eap_alarm_spool_key, get_eap_alarm_spool_path
        self._spool_key = make_eap_alarm_spool_key(date_from, date_to, machines)
        self._spool_path = get_eap_alarm_spool_path(self._spool_key)

        # Build daily chunk pairs: one "events" chunk + one "detail" chunk per day
        start = datetime.strptime(date_from, "%Y-%m-%d")
        end = datetime.strptime(date_to, "%Y-%m-%d")
        chunks = []
        current = start
        while current <= end:
            day_str = current.strftime("%Y-%m-%d")
            next_day_str = (current + timedelta(days=1)).strftime("%Y-%m-%d")
            base_params: Dict[str, Any] = {
                "date_from": day_str,
                "date_to": next_day_str,
                **self._eqp_params,
            }
            chunks.append({
                "kind": "events",
                "date_from": day_str,
                "date_to": next_day_str,
                "base_params": base_params,
            })
            chunks.append({
                "kind": "detail",
                "date_from": day_str,
                "date_to": next_day_str,
                "base_params": base_params,
            })
            current += timedelta(days=1)
        self._chunks = chunks

    def build_chunk_sql(self, chunk_params: dict) -> tuple[str, dict]:
        """Return (sql, binds) for the given chunk kind."""
        if chunk_params["kind"] == "events":
            return (
                _EAP_EVENT_SQL_TEMPLATE.format(equipment_filter=self._equipment_filter),
                chunk_params["base_params"],
            )
        else:
            return (
                _DETAIL_SQL_TEMPLATE.format(equipment_filter=self._equipment_filter),
                chunk_params["base_params"],
            )

    def post_aggregate(self, job_duckdb_path: "str | None") -> str:
        """Read all chunk parquets, run EAV pivot + SET/CLEAR pairing, write spool."""
        import json
        import duckdb
        import pandas as pd
        import pyarrow as pa
        import pyarrow.parquet as pq

        chunk_dir = self._make_chunk_parquet_dir(self.job_id)
        all_parquets = sorted(chunk_dir.glob("chunk-*.parquet"))

        # Separate events vs detail parquets by chunk index parity
        # _chunks layout: [events_day0, detail_day0, events_day1, detail_day1, ...]
        # chunk-{chunk_idx:04d}-{batch_idx:04d}.parquet
        events_parquets = []
        detail_parquets = []
        for p in all_parquets:
            name = p.name  # e.g. chunk-0000-0000.parquet
            parts = name.split("-")
            # parts: ['chunk', '0000', '0000.parquet']
            chunk_idx = int(parts[1])
            kind = self._chunks[chunk_idx]["kind"]
            if kind == "events":
                events_parquets.append(p)
            else:
                detail_parquets.append(p)

        # Read events
        if events_parquets:
            events_tables = [pq.read_table(str(p)) for p in events_parquets]
            events_combined = pa.concat_tables(events_tables)
            events_df = events_combined.to_pandas()
        else:
            events_df = pd.DataFrame(
                columns=["EVENT_ID", "EQP_ID", "EQP_TYPE", "LOT_ID", "ALARM_ID", "ALARM_TIME"]
            )

        # Read detail
        if detail_parquets:
            detail_tables = [pq.read_table(str(p)) for p in detail_parquets]
            detail_combined = pa.concat_tables(detail_tables)
            detail_raw_df = detail_combined.to_pandas()
        else:
            detail_raw_df = pd.DataFrame(
                columns=["EVENT_ID", "PARAMETER_NAME", "PARAMETER_VALUE"]
            )

        # EAV pivot in Python (same logic as run_eap_alarm_query_job)
        if not detail_raw_df.empty:
            records = []
            for eid, grp in detail_raw_df.groupby("EVENT_ID"):
                d = dict(zip(grp["PARAMETER_NAME"], grp["PARAMETER_VALUE"]))
                records.append({
                    "EVENT_ID":          str(eid),
                    "ALARM_CODE_STR":    d.get("AlarmCode"),
                    "ALARM_TEXT_DETAIL": d.get("AlarmText"),
                    "DETAIL_PARAMS":     json.dumps(d, ensure_ascii=False),
                })
            detail_pivot_df = pd.DataFrame(records)
        else:
            detail_pivot_df = pd.DataFrame(
                columns=["EVENT_ID", "ALARM_CODE_STR", "ALARM_TEXT_DETAIL", "DETAIL_PARAMS"]
            )

        os.makedirs(os.path.dirname(self._spool_path), exist_ok=True)

        con = duckdb.connect()
        try:
            con.register("events_raw", events_df)
            con.register("detail_pivot", detail_pivot_df)

            pair_sql = _PAIR_SQL.format(machines_hash=self._machines_hash)

            if events_df.empty:
                con.execute(
                    f"COPY (SELECT * FROM ({pair_sql}) t WHERE FALSE) TO '{self._spool_path}'"
                    " (FORMAT PARQUET, CODEC 'SNAPPY')"
                )
                row_count = 0
            else:
                con.execute(
                    f"COPY ({pair_sql}) TO '{self._spool_path}' (FORMAT PARQUET, CODEC 'SNAPPY')"
                )
                row_count = con.execute(
                    f"SELECT COUNT(*) FROM read_parquet('{self._spool_path}')"
                ).fetchone()[0]
        finally:
            con.close()

        logger.info(
            "EapAlarmJob.post_aggregate: parquet written path=%s rows=%d job_id=%s",
            self._spool_path, row_count, self.job_id,
        )

        try:
            from mes_dashboard.core.query_spool_store import register_spool_file
            from mes_dashboard.services.eap_alarm_cache import EAP_ALARM_SPOOL_TTL
            register_spool_file(
                "eap_alarm", self._spool_key, Path(self._spool_path),
                row_count, ttl_seconds=EAP_ALARM_SPOOL_TTL,
            )
        except Exception as reg_exc:
            logger.warning("EapAlarmJob.post_aggregate: spool registration failed: %s", reg_exc)

        return self._spool_path

    def progress_report(self, pct: int) -> None:
        """Report progress via async_query_job_service (lazy import to avoid circular)."""
        from mes_dashboard.services.async_query_job_service import update_job_progress
        update_job_progress("eap-alarm", self.job_id, pct=str(pct))


def execute_eap_alarm_unified_job(
    job_id: str,
    date_from: str,
    date_to: str,
    machines: list,
) -> None:
    """RQ entry point for EapAlarmJob (EAP_ALARM_USE_UNIFIED_JOB=on path).

    Called by RQ worker process. Creates EapAlarmJob and runs the template method.
    """
    from mes_dashboard.rq_worker_preload import ensure_rq_logging
    ensure_rq_logging()

    from mes_dashboard.services.async_query_job_service import complete_job

    logger.info("execute_eap_alarm_unified_job: started job_id=%s", job_id)
    try:
        job = EapAlarmJob(
            job_id=job_id,
            params={"date_from": date_from, "date_to": date_to, "machines": machines},
        )
        spool_path = job.run()
        complete_job("eap-alarm", job_id, query_id=job._spool_key)
        logger.info(
            "execute_eap_alarm_unified_job: completed job_id=%s spool_path=%s",
            job_id, spool_path,
        )
    except Exception as exc:
        logger.error(
            "execute_eap_alarm_unified_job: failed job_id=%s: %s", job_id, exc, exc_info=True
        )
        complete_job("eap-alarm", job_id, error=str(exc))
        raise


# ── Central job registry ───────────────────────────────────────────────────────
from mes_dashboard.services.job_registry import JobTypeConfig, register_job_type  # noqa: E402

register_job_type(JobTypeConfig(
    job_type="eap-alarm",
    queue_name=EAP_ALARM_WORKER_QUEUE,
    worker_fn=execute_eap_alarm_unified_job,
    timeout_seconds=EAP_ALARM_JOB_TIMEOUT_SECONDS,
    ttl_seconds=EAP_ALARM_JOB_TTL_SECONDS,
    always_async=True,
))
