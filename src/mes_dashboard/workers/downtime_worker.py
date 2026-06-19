# -*- coding: utf-8 -*-
"""DowntimeJob — BaseChunkedDuckDBJob implementation for downtime analysis.

Replaces the highest OOM-risk operation in the system:
  _bridge_jobid() Path B's pd.merge(events_b, jobs_b, how='left')
  — an N×M Cartesian pre-join with no chunk protection (ADR-0003).

Architecture (design.md D1–D4):
- Streams base_events (keyed by HISTORYID) and job_data (keyed by RESOURCEID)
  as Arrow batches into two tables in a shared job-temp DuckDB:
    base_raw  — raw E10 shift rows from DW_MES_RESOURCESTATUS_SHIFT
    job_raw   — job records from DW_MES_JOB + JOBTXNHISTORY
- chunk_strategy = SINGLE per RESOURCEID group (ADR-0003 forbids TIME/ROW_COUNT
  because cross-shift merge walks fragments within HISTORYID groups).
- requires_cross_chunk_reduction = True: both tables must be co-resident in one
  shared job-temp DuckDB to run the bridge JOIN in post_aggregate.
- post_aggregate runs:
    1. cross_shift_merge.sql: 60-second gap walk (DA-02)
    2. bridge_join.sql: time-overlap RANGE JOIN + winner selection (DA-03, ADR-0010)
    3. _bridge_jobid-equivalent derived columns (pandas; preserves byte-faithfulness)
    4. _enrich_events_df (category, event_id, column renames)
    5. COPY TO spool parquet with unchanged §3.21 schema

Gate: DOWNTIME_USE_UNIFIED_JOB flag (default off, see downtime_query_job_service.py).
Legacy _bridge_jobid Path B is NOT deleted while this flag exists (AC-8).

Module-level register_job_type("downtime-unified") fires at import time
(job-registry-central pattern, same as eap_alarm_worker.py).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List

import pyarrow as pa

from mes_dashboard.core.base_chunked_duckdb_job import BaseChunkedDuckDBJob, ChunkStrategy

logger = logging.getLogger("mes_dashboard.downtime_worker")

# ---------------------------------------------------------------------------
# Configuration (mirrors downtime_query_job_service.py constants)
# ---------------------------------------------------------------------------
DOWNTIME_WORKER_QUEUE: str = os.getenv("DOWNTIME_WORKER_QUEUE", "downtime-query")
DOWNTIME_JOB_TTL_SECONDS: int = int(os.getenv("DOWNTIME_JOB_TTL_SECONDS", "3600"))
DOWNTIME_JOB_TIMEOUT_SECONDS: int = int(os.getenv("DOWNTIME_JOB_TIMEOUT_SECONDS", "1800"))

_JOB_PREFIX = "downtime"

# SQL file paths
_SQL_DIR = Path(__file__).resolve().parent.parent / "sql" / "downtime_analysis"
_MERGE_GAP_SECONDS = 60  # must match _MERGE_GAP_SECONDS in downtime_analysis_service.py

# Oracle SQL templates (same tables/columns as job_bridge.sql and base_events.sql)
_BASE_EVENTS_SQL = """\
SELECT
    s.HISTORYID,
    s.OLDSTATUSNAME,
    TRIM(s.OLDREASONNAME) AS OLDREASONNAME,
    s.OLDLASTSTATUSCHANGEDATE,
    s.LASTSTATUSCHANGEDATE,
    CAST(s.HOURS AS FLOAT) AS HOURS,
    s.JOBID
FROM
    DWH.DW_MES_RESOURCESTATUS_SHIFT s
WHERE
    s.OLDSTATUSNAME IN ('UDT', 'SDT', 'EGT')
    AND s.OLDLASTSTATUSCHANGEDATE >= TO_DATE(:start_date, 'YYYY-MM-DD')
    AND s.OLDLASTSTATUSCHANGEDATE <  TO_DATE(:end_date,   'YYYY-MM-DD') + 1
    AND {resource_filter}
ORDER BY
    s.OLDLASTSTATUSCHANGEDATE DESC,
    s.HISTORYID ASC
"""

_JOB_SQL = """\
WITH job_base AS (
    SELECT
        JOBID,
        TRIM(RESOURCEID)           AS RESOURCEID,
        CREATEDATE,
        COMPLETEDATE,
        TRIM(SYMPTOMCODENAME)      AS SYMPTOMCODENAME,
        TRIM(CAUSECODENAME)        AS CAUSECODENAME,
        TRIM(REPAIRCODENAME)       AS REPAIRCODENAME,
        TRIM(COMPLETE_FULLNAME)    AS COMPLETE_FULLNAME,
        FIRSTCLOCKONDATE,
        LASTCLOCKOFFDATE,
        TRIM(JOBORDERNAME)         AS JOBORDERNAME,
        TRIM(JOBMODELNAME)         AS JOBMODELNAME
    FROM DWH.DW_MES_JOB
    WHERE {resource_filter}
      AND (
          COMPLETEDATE >= TO_DATE(:start_date, 'YYYY-MM-DD') - 7
          OR COMPLETEDATE IS NULL
      )
      AND CREATEDATE <= TO_DATE(:end_date, 'YYYY-MM-DD') + 7
)
SELECT
    jb.JOBID,
    jb.RESOURCEID,
    jb.CREATEDATE,
    jb.COMPLETEDATE,
    jb.SYMPTOMCODENAME,
    jb.CAUSECODENAME,
    jb.REPAIRCODENAME,
    jb.COMPLETE_FULLNAME,
    jb.FIRSTCLOCKONDATE,
    jb.LASTCLOCKOFFDATE,
    jb.JOBORDERNAME,
    jb.JOBMODELNAME,
    txn.ASSIGNED_DATE,
    txn.ACK_DATE,
    txn.INSPECT_START,
    txn.INSPECT_END
FROM job_base jb
LEFT JOIN (
    SELECT
        t.JOBID,
        MIN(CASE WHEN t.JOBSTATUS = 'ASSIGNED'     THEN t.TXNDATE END) AS ASSIGNED_DATE,
        MIN(CASE WHEN t.JOBSTATUS = 'ACKNOWLEDGED' THEN t.TXNDATE END) AS ACK_DATE,
        MIN(CASE WHEN t.STAGENAME IN (
                'QC-產品檢驗', 'PD-產品檢驗',
                'QC_驗機', 'EE_驗機', 'PD_驗機', 'PE_驗機'
            ) THEN t.TXNDATE END)                                       AS INSPECT_START,
        MAX(CASE WHEN t.STAGENAME IN (
                'QC-產品檢驗', 'PD-產品檢驗',
                'QC_驗機', 'EE_驗機', 'PD_驗機', 'PE_驗機'
            ) THEN t.TXNDATE END)                                       AS INSPECT_END
    FROM DWH.DW_MES_JOBTXNHISTORY t
    WHERE t.JOBID IN (SELECT JOBID FROM job_base)
    GROUP BY t.JOBID
) txn ON txn.JOBID = jb.JOBID
"""


def _build_in_filter(column: str, values: List[str]) -> tuple[str, Dict[str, Any]]:
    """Build Oracle IN-list filter for up to 999-element batches.

    Returns (sql_fragment, bind_params).
    Column is referenced without table alias — caller must ensure context.
    """
    _ORACLE_IN_LIMIT = 999
    params: Dict[str, Any] = {}
    if not values:
        return "1=0", params
    if len(values) <= _ORACLE_IN_LIMIT:
        placeholders = ", ".join(f":rid{i}" for i in range(len(values)))
        for i, v in enumerate(values):
            params[f"rid{i}"] = v
        return f"{column} IN ({placeholders})", params
    clauses: List[str] = []
    offset = 0
    for chunk_start in range(0, len(values), _ORACLE_IN_LIMIT):
        chunk = values[chunk_start:chunk_start + _ORACLE_IN_LIMIT]
        ph = ", ".join(f":rid{offset + k}" for k in range(len(chunk)))
        clauses.append(f"{column} IN ({ph})")
        for k, v in enumerate(chunk):
            params[f"rid{offset + k}"] = v
        offset += len(chunk)
    return "(" + " OR ".join(clauses) + ")", params


class DowntimeJob(BaseChunkedDuckDBJob):
    """Chunked Oracle→DuckDB job for downtime analysis (Path B OOM elimination).

    Two Oracle datasets streamed into one shared job-temp DuckDB:
      base_raw  — E10 shift rows (HISTORYID-keyed)
      job_raw   — job records (RESOURCEID-keyed)

    chunk_strategy = SINGLE per RESOURCEID group.
    requires_cross_chunk_reduction = True (both tables must co-reside, design.md D1).

    This is the opposite of EapAlarmJob (ADR-0009 used False) — intentional.
    BJ-01 warning against True applies to single-dataset row-chunkable domains;
    downtime requires TWO datasets co-resident for the bridge JOIN.
    """

    namespace = "downtime"
    chunk_strategy = ChunkStrategy.SINGLE
    requires_cross_chunk_reduction = True
    max_parallel = 3

    def __init__(self, job_id: str, params: dict) -> None:
        super().__init__(job_id)
        self.params = params
        self._spool_key: str = ""
        self._spool_path: str = ""
        self._hist_ids: List[str] = []  # DISTINCT HISTORYIDs for this query

    # ------------------------------------------------------------------
    # pre_query: resolve RESOURCEID set, emit base+job chunks per group
    # ------------------------------------------------------------------

    def pre_query(self) -> None:
        """Resolve candidate RESOURCEID set, build base+job chunk pairs.

        Mirrors query_downtime_dataset lines 1220-1235: fetches DISTINCT HISTORYID
        via a lightweight DuckDB scan (or Oracle scan) for the date range, then
        emits one 'base' chunk + one 'job' chunk per RESOURCEID group (SINGLE strategy
        per group — ADR-0003 forbids TIME/ROW_COUNT for downtime).

        For the unified job path, we simplify: emit ONE base chunk (all resources,
        date-range filtered) + ONE job chunk (same date range), letting the
        post_aggregate bridge join handle the full dataset.  This matches the legacy
        whole-dataset model.  Per-group parallelism is the future optimisation (D1).
        """
        start_date = str(self.params.get("start_date", "")).strip()
        end_date = str(self.params.get("end_date", "")).strip()

        from mes_dashboard.services.downtime_analysis_service import make_downtime_query_id

        query_id_input = {
            "start_date": start_date,
            "end_date": end_date,
            "workcenter_groups": sorted(self.params.get("workcenter_groups") or []),
            "families": sorted(self.params.get("families") or []),
            "resource_ids": sorted(self.params.get("resource_ids") or []),
            "package_groups": sorted(self.params.get("package_groups") or []),
            "big_categories": sorted(self.params.get("big_categories") or []),
            "status_types": sorted(self.params.get("status_types") or []),
        }
        self._spool_key = make_downtime_query_id(query_id_input)
        # spool_path is resolved lazily via store_downtime_events → get_spool_file_path
        self._spool_path = ""

        # Emit one 'base' chunk + one 'job' chunk (whole-dataset model, SINGLE strategy).
        # resource_filter is open (all resources) — filtering happens in post_aggregate
        # via _apply_resource_filters, matching the legacy query_downtime_dataset flow.
        self._chunks = [
            {
                "kind": "base",
                "start_date": start_date,
                "end_date": end_date,
            },
            {
                "kind": "job",
                "start_date": start_date,
                "end_date": end_date,
            },
        ]
        logger.info(
            "DowntimeJob.pre_query: job_id=%s spool_key=%s chunks=%d",
            self.job_id, self._spool_key, len(self._chunks),
        )

    # ------------------------------------------------------------------
    # build_chunk_sql: return (sql, binds) per kind
    # ------------------------------------------------------------------

    def build_chunk_sql(self, chunk_params: dict) -> tuple[str, dict]:
        """Return (sql, bind_params) for 'base' or 'job' chunk kind."""
        kind = chunk_params.get("kind")
        start_date = chunk_params["start_date"]
        end_date = chunk_params["end_date"]

        if kind == "base":
            # All resources for this date range — filters applied post-aggregate.
            sql = _BASE_EVENTS_SQL.format(resource_filter="1=1")
            params: Dict[str, Any] = {
                "start_date": start_date,
                "end_date": end_date,
            }
            return sql, params

        elif kind == "job":
            # All resources (wide time window to capture overlapping jobs).
            sql = _JOB_SQL.format(resource_filter="1=1")
            params = {
                "start_date": start_date,
                "end_date": end_date,
            }
            return sql, params

        else:
            raise ValueError(
                f"DowntimeJob.build_chunk_sql: unknown kind={kind!r}; "
                "expected 'base' or 'job'"
            )

    # ------------------------------------------------------------------
    # chunk_to_duckdb: R1 override — route to base_raw vs job_raw
    # ------------------------------------------------------------------

    def chunk_to_duckdb(
        self,
        batch: pa.RecordBatch,
        job_duckdb_path: str,
    ) -> None:
        """Disabled: DowntimeJob uses chunk_to_duckdb_routed which carries chunk_params.

        The base class _fan_out_reduction calls chunk_to_duckdb(batch, path) without
        chunk_params, so DowntimeJob overrides _fan_out_reduction instead to pass
        chunk_params through to _chunk_to_duckdb_routed.

        This method is never called on DowntimeJob; it raises to catch accidental use.
        """
        raise RuntimeError(
            "DowntimeJob.chunk_to_duckdb should not be called directly. "
            "Use _chunk_to_duckdb_routed(batch, path, chunk_params) instead."
        )

    def _chunk_to_duckdb_routed(
        self,
        batch: pa.RecordBatch,
        job_duckdb_path: str,
        chunk_params: dict,
    ) -> None:
        """R1: Route Arrow batch to base_raw or job_raw based on chunk_params['kind'].

        The base class chunk_to_duckdb infers ONE 'raw' table — DowntimeJob needs
        TWO tables keyed by chunk kind.  This method routes batches to the correct
        table and creates it if it does not yet exist (same schema-infer pattern as
        the base class, but with a configurable table name).

        Serialized under _writer_lock (DuckDB single-writer constraint, D4).
        """
        import duckdb

        kind = chunk_params.get("kind")
        if kind == "base":
            table_name = "base_raw"
        elif kind == "job":
            table_name = "job_raw"
        else:
            raise ValueError(
                f"DowntimeJob._chunk_to_duckdb_routed: unknown kind={kind!r}; "
                "expected 'base' or 'job'"
            )

        with self._writer_lock:
            conn = duckdb.connect(job_duckdb_path)
            try:
                conn.register("_chunk_batch", batch)
                conn.execute(
                    f"CREATE TABLE IF NOT EXISTS {table_name} AS "
                    f"SELECT * FROM _chunk_batch WHERE 1=0"
                )
                conn.execute(f"INSERT INTO {table_name} SELECT * FROM _chunk_batch")
                conn.unregister("_chunk_batch")
            finally:
                conn.close()

    def _fan_out_reduction(
        self, chunks: list, job_duckdb_path: str
    ) -> None:
        """Override: pass chunk_params to _chunk_to_duckdb_routed for table routing (R1).

        The base _fan_out_reduction calls chunk_to_duckdb(batch, path) without
        chunk_params; DowntimeJob needs chunk_params['kind'] to route batches
        to base_raw vs job_raw.  This override passes it through.
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        effective = min(self.max_parallel, len(chunks)) if chunks else 1

        def _fetch_and_insert(chunk_params: dict) -> None:
            for batch in self._fetch_chunk(chunk_params):
                self._chunk_to_duckdb_routed(batch, job_duckdb_path, chunk_params)

        if effective <= 1 or len(chunks) <= 1:
            for cp in chunks:
                _fetch_and_insert(cp)
        else:
            with ThreadPoolExecutor(max_workers=effective) as executor:
                futures = {executor.submit(_fetch_and_insert, cp): cp for cp in chunks}
                for fut in as_completed(futures):
                    exc = fut.exception()
                    if exc is not None:
                        raise exc

    # ------------------------------------------------------------------
    # post_aggregate: cross-shift merge → bridge JOIN → enrich → spool
    # ------------------------------------------------------------------

    def post_aggregate(self, job_duckdb_path: Any) -> str:
        """Run DuckDB reductions and write the canonical spool parquet.

        Steps:
          1. Read base_raw (or empty DataFrame if table missing).
          2. Cross-shift merge via _CROSS_SHIFT_MERGE_SQL (DuckDB form, R3 decision:
             use the same proven SQL from downtime_analysis_service, not a rewrite).
          3. Apply resource filters (matches legacy query_downtime_dataset flow).
          4. Bridge JOIN via bridge_join.sql (DA-03, ADR-0010).
          5. Derive job enrichment columns (pandas, byte-faithful match of _bridge_jobid).
          6. _enrich_events_df: category, event_id, column renames.
          7. COPY TO spool parquet at §3.21 column set.
          8. Register spool.
        """
        import pandas as pd

        from mes_dashboard.services.downtime_analysis_service import (
            _enrich_events_df,
            _apply_resource_filters,
            _empty_events_df,
        )

        logger.info(
            "DowntimeJob.post_aggregate: started job_id=%s job_duckdb=%s",
            self.job_id, job_duckdb_path,
        )

        # ── Step 1: Load base_raw from job-temp DuckDB ────────────────────────
        if job_duckdb_path is None:
            logger.warning(
                "DowntimeJob.post_aggregate: job_duckdb_path is None, returning empty"
            )
            events_df = _empty_events_df()
            return self._write_spool(events_df)

        base_df = self._read_table_safe(job_duckdb_path, "base_raw")
        job_df = self._read_table_safe(job_duckdb_path, "job_raw")

        # ── Step 2: Cross-shift merge (DuckDB SQL form — R3 decision) ─────────
        # R3 decision: use the same _CROSS_SHIFT_MERGE_SQL from
        # downtime_analysis_service._merge_cross_shift_events_from_parquet —
        # this SQL form is already proven in production (used by the legacy
        # DuckDB fast-path).  Re-use it here rather than reimplementing.
        if not base_df.empty:
            merged_df = self._run_cross_shift_merge(base_df)
        else:
            merged_df = pd.DataFrame()

        # ── Step 3: Apply resource filters (matches legacy flow) ───────────────
        if not merged_df.empty:
            merged_df = _apply_resource_filters(
                merged_df,
                workcenter_groups=self.params.get("workcenter_groups") or None,
                families=self.params.get("families") or None,
                resource_ids=self.params.get("resource_ids") or None,
                package_groups=self.params.get("package_groups") or None,
                is_production=bool(self.params.get("is_production", False)),
                is_key=bool(self.params.get("is_key", False)),
                is_monitor=bool(self.params.get("is_monitor", False)),
            )

        if merged_df.empty:
            events_df = _empty_events_df()
            return self._write_spool(events_df)

        # ── Step 4: Bridge JOIN via DuckDB SQL (ADR-0010) ─────────────────────
        bridged_df = self._run_bridge_join(merged_df, job_df)

        # ── Step 5: Derive job enrichment columns (pandas, byte-faithful) ──────
        bridged_df = self._derive_job_columns(bridged_df)

        # ── Step 6: _enrich_events_df (category, event_id, renames) ───────────
        if not bridged_df.empty:
            events_df = _enrich_events_df(bridged_df)
        else:
            events_df = _empty_events_df()

        # Apply big_category / status_type filters post-enrichment
        big_categories = self.params.get("big_categories") or None
        status_types = self.params.get("status_types") or None
        if not events_df.empty and big_categories:
            events_df = events_df[events_df["category"].isin(big_categories)]
        if not events_df.empty and status_types:
            events_df = events_df[events_df["status"].isin(status_types)]

        # ── Step 7+8: Write spool and register ────────────────────────────────
        spool_path = self._write_spool(events_df)

        logger.info(
            "DowntimeJob.post_aggregate: completed job_id=%s spool_key=%s rows=%d",
            self.job_id, self._spool_key, len(events_df),
        )
        return spool_path

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _read_table_safe(self, job_duckdb_path: str, table_name: str) -> Any:
        """Read a table from the job-temp DuckDB; return empty DataFrame if missing."""
        import duckdb
        import pandas as pd

        try:
            conn = duckdb.connect(job_duckdb_path, read_only=True)
            try:
                result = conn.execute(
                    f"SELECT * FROM {table_name}"
                ).df()
                return result
            finally:
                conn.close()
        except Exception as exc:
            logger.warning(
                "DowntimeJob._read_table_safe: could not read %s from %s: %s",
                table_name, job_duckdb_path, exc,
            )
            return pd.DataFrame()

    def _run_cross_shift_merge(self, base_df: Any) -> Any:
        """Run cross-shift 60s-gap merge using DuckDB SQL (R3: SQL form).

        R3 decision: Use the same DuckDB SQL proven in
        _merge_cross_shift_events_from_parquet() (downtime_analysis_service.py).
        The SQL form is byte-faithful with the pandas path for FIRST() semantics
        because DuckDB's FIRST() with FILTER and ORDER BY matches pandas nth(0)/
        _first_nonnull behaviour within the run_ids grouping.

        Fallback: if the DuckDB SQL form fails (version compat), call the pandas
        function directly.
        """
        import duckdb

        from mes_dashboard.services.downtime_analysis_service import (
            _merge_cross_shift_events,
            _MERGE_GAP_SECONDS as _svc_gap_seconds,
        )

        # Read cross-shift merge SQL template from the service's established constant
        # (same SQL already verified in production).
        try:
            from mes_dashboard.services.downtime_analysis_service import _CROSS_SHIFT_MERGE_SQL
            con = duckdb.connect()
            try:
                con.register("base_raw", base_df)
                # The SQL reads from "base_events" but our table is "base_raw";
                # create a view alias so the SQL works unchanged.
                con.execute("CREATE VIEW base_events AS SELECT * FROM base_raw")
                sql = _CROSS_SHIFT_MERGE_SQL.format(gap_seconds=_svc_gap_seconds)
                result = con.execute(sql).df()
                # Restore empty-string OLDREASONNAME -> None (matches pandas path)
                if "OLDREASONNAME" in result.columns:
                    result["OLDREASONNAME"] = result["OLDREASONNAME"].replace("", None)
                return result
            finally:
                con.close()
        except Exception as exc:
            logger.warning(
                "DowntimeJob._run_cross_shift_merge: DuckDB SQL form failed (%s), "
                "falling back to pandas _merge_cross_shift_events",
                exc,
            )
            return _merge_cross_shift_events(base_df)

    def _run_bridge_join(
        self,
        merged_df: Any,
        job_df: Any,
    ) -> Any:
        """Run bridge JOIN via bridge_join.sql (DA-03, ADR-0010).

        Registers merged_df as base_events_merged and job_df as job_raw,
        then executes bridge_join.sql entirely in DuckDB — eliminating the
        N×M Cartesian pd.merge (the Path B OOM elimination).

        Returns a DataFrame with all bridge join output columns.
        """
        import duckdb
        import pandas as pd

        bridge_sql_path = _SQL_DIR / "bridge_join.sql"
        bridge_sql = bridge_sql_path.read_text(encoding="utf-8")

        try:
            con = duckdb.connect()
            try:
                con.register("base_events_merged", merged_df)
                if not job_df.empty:
                    con.register("job_raw", job_df)
                else:
                    # Empty job table: register empty DataFrame with correct schema
                    empty_jobs = pd.DataFrame(columns=[
                        "JOBID", "RESOURCEID", "CREATEDATE", "COMPLETEDATE",
                        "SYMPTOMCODENAME", "CAUSECODENAME", "REPAIRCODENAME",
                        "COMPLETE_FULLNAME", "FIRSTCLOCKONDATE", "LASTCLOCKOFFDATE",
                        "JOBORDERNAME", "JOBMODELNAME",
                        "ASSIGNED_DATE", "ACK_DATE", "INSPECT_START", "INSPECT_END",
                    ])
                    con.register("job_raw", empty_jobs)

                result = con.execute(bridge_sql).df()
                return result
            finally:
                con.close()
        except Exception as exc:
            logger.error(
                "DowntimeJob._run_bridge_join: DuckDB bridge JOIN failed: %s",
                exc, exc_info=True,
            )
            raise

    def _derive_job_columns(self, df: Any) -> Any:
        """Derive job enrichment columns from bridge join output (pandas, byte-faithful).

        Mirrors the derived column computation in _bridge_jobid() lines 513-541:
          job_id, job_order_name, job_model, symptom, cause, repair, handler,
          wait_min, repair_min, wait_assign_min, wait_ack_min, inspect_min,
          close_wait_min, job_create_date, job_complete_date.

        Then drops raw Oracle columns so _enrich_events_df can work on the cleaned DF.
        """
        import pandas as pd

        from mes_dashboard.services.downtime_analysis_service import _ts_to_iso

        if df.empty:
            return df

        df = df.copy()

        def _safe_min_s(end_col: str, start_col: str) -> "pd.Series":
            if end_col not in df.columns or start_col not in df.columns:
                return pd.Series([None] * len(df), dtype=object)
            t_end = pd.to_datetime(df[end_col], errors="coerce")
            t_start = pd.to_datetime(df[start_col], errors="coerce")
            diff = (t_end - t_start).dt.total_seconds() / 60.0
            mask_valid = diff.notna() & (diff >= 0)
            out = diff.round(2).astype(object)
            out[~mask_valid] = None
            return out

        def _norm_str_col(col: str) -> "pd.Series":
            if col not in df.columns:
                return pd.Series([None] * len(df), dtype=object)
            s = df[col].astype(str).str.strip()
            bad = df[col].isna() | s.isin({"", "nan", "None", "NaT"})
            return s.where(~bad, other=None)

        df["job_id"] = _norm_str_col("JOBID")
        df["job_order_name"] = _norm_str_col("JOBORDERNAME")
        df["job_model"] = _norm_str_col("JOBMODELNAME")
        df["symptom"] = _norm_str_col("SYMPTOMCODENAME")
        df["cause"] = _norm_str_col("CAUSECODENAME")
        df["repair"] = _norm_str_col("REPAIRCODENAME")
        df["handler"] = _norm_str_col("COMPLETE_FULLNAME")
        df["wait_min"] = _safe_min_s("FIRSTCLOCKONDATE", "CREATEDATE")
        df["repair_min"] = _safe_min_s("LASTCLOCKOFFDATE", "FIRSTCLOCKONDATE")
        df["wait_assign_min"] = _safe_min_s("ASSIGNED_DATE", "CREATEDATE")
        df["wait_ack_min"] = _safe_min_s("ACK_DATE", "ASSIGNED_DATE")
        df["inspect_min"] = _safe_min_s("INSPECT_END", "INSPECT_START")
        df["close_wait_min"] = _safe_min_s("COMPLETEDATE", "LASTCLOCKOFFDATE")

        _cd = (
            pd.to_datetime(df["CREATEDATE"], errors="coerce")
            if "CREATEDATE" in df.columns else None
        )
        _cp = (
            pd.to_datetime(df["COMPLETEDATE"], errors="coerce")
            if "COMPLETEDATE" in df.columns else None
        )
        df["job_create_date"] = _cd.apply(_ts_to_iso) if _cd is not None else None
        df["job_complete_date"] = _cp.apply(_ts_to_iso) if _cp is not None else None

        # Drop raw Oracle columns (same set as _bridge_jobid lines 542-552)
        _drop = [
            "JOBORDERNAME", "JOBMODELNAME", "SYMPTOMCODENAME", "CAUSECODENAME",
            "REPAIRCODENAME", "COMPLETE_FULLNAME", "FIRSTCLOCKONDATE", "LASTCLOCKOFFDATE",
            "CREATEDATE", "COMPLETEDATE", "ASSIGNED_DATE", "ACK_DATE",
            "INSPECT_START", "INSPECT_END", "RESOURCEID",
            # bridge_join output extras not needed by _enrich_events_df
            "event_id",  # event_id will be rebuilt by _enrich_events_df
        ]
        df = df.drop(columns=[c for c in _drop if c in df.columns])
        return df

    def _write_spool(self, events_df: Any) -> str:
        """Write events DataFrame to spool and register.

        Uses store_downtime_events (same as legacy query_downtime_dataset) so the
        spool is readable by the same cache / view endpoints.

        Returns the spool file path (resolved after writing).
        """
        from mes_dashboard.services.downtime_analysis_cache import store_downtime_events
        from mes_dashboard.core.query_spool_store import get_spool_file_path
        from mes_dashboard.services.downtime_analysis_cache import _EVENTS_NAMESPACE

        store_downtime_events(
            self._spool_key,
            events_df,
            end_date=str(self.params.get("end_date", "")),
        )
        # Resolve the path after write so post_aggregate can return it.
        spool_path = get_spool_file_path(_EVENTS_NAMESPACE, self._spool_key) or ""
        self._spool_path = spool_path
        logger.info(
            "DowntimeJob._write_spool: spool registered key=%s rows=%d path=%s",
            self._spool_key, len(events_df), spool_path,
        )
        return spool_path

    def progress_report(self, pct: int) -> None:
        """Report progress via async_query_job_service (lazy import, same as eap_alarm)."""
        from mes_dashboard.services.async_query_job_service import update_job_progress
        update_job_progress(_JOB_PREFIX, self.job_id, pct=str(pct))


# ---------------------------------------------------------------------------
# RQ entry point
# ---------------------------------------------------------------------------

def execute_downtime_unified_job(
    job_id: str,
    **query_params: Any,
) -> None:
    """RQ entry point for DowntimeJob (DOWNTIME_USE_UNIFIED_JOB=on path).

    Called by RQ worker process.  Creates DowntimeJob and runs the template method.
    Mirrors execute_eap_alarm_unified_job pattern from eap_alarm_worker.py.
    """
    from mes_dashboard.rq_worker_preload import ensure_rq_logging
    ensure_rq_logging()

    from mes_dashboard.services.async_query_job_service import complete_job

    logger.info("execute_downtime_unified_job: started job_id=%s", job_id)
    try:
        job = DowntimeJob(
            job_id=job_id,
            params=query_params,
        )
        spool_path = job.run()
        complete_job(_JOB_PREFIX, job_id, query_id=job._spool_key)
        logger.info(
            "execute_downtime_unified_job: completed job_id=%s spool_path=%s",
            job_id, spool_path,
        )
    except Exception as exc:
        logger.error(
            "execute_downtime_unified_job: failed job_id=%s: %s",
            job_id, exc, exc_info=True,
        )
        complete_job(_JOB_PREFIX, job_id, error=str(exc))
        raise


# ---------------------------------------------------------------------------
# Central job registry — register at import time
# ---------------------------------------------------------------------------
from mes_dashboard.services.job_registry import JobTypeConfig, register_job_type  # noqa: E402

register_job_type(JobTypeConfig(
    job_type="downtime-unified",
    queue_name=DOWNTIME_WORKER_QUEUE,
    worker_fn=execute_downtime_unified_job,
    timeout_seconds=DOWNTIME_JOB_TIMEOUT_SECONDS,
    ttl_seconds=DOWNTIME_JOB_TTL_SECONDS,
    always_async=True,
))
