# -*- coding: utf-8 -*-
"""UPH Performance RQ worker (add-uph-performance-page).

Entry point: execute_uph_performance_unified_job(job_id, params)

Design (design.md Key Decisions; ADR-0017):
  - Single shared sql/uph_performance.sql template, one JOIN'd chunk query
    per <=6h TIME window (UPH-01) -- family-conditional CASE detail JOIN
    (ADR-0017 Decision-1), never a blanket PARAMETER_NAME IN-list.
  - UphPerformanceJob(BaseChunkedDuckDBJob): chunk_strategy=TIME,
    requires_cross_chunk_reduction=False (append path, like EapAlarmJob --
    each event row is independent, no seam-straddling aggregation;
    ADR-0017 Decision-2). post_aggregate is a plain concat of chunk
    parquets plus two enrichment bridges (ADR-0017 Decision-3):
      LOT_ID       -> DW_MES_CONTAINER  (Package/Type/PJ_BOP/PJ_FUNCTION)
      EQUIPMENT_ID -> DW_MES_RESOURCE   (WORKCENTERNAME, OBJECTCATEGORY='ASSEMBLY')
    Both bridges mirror eap_alarm_worker.py's _safe_lot_product_df pattern
    (chunked IN-list lookups over distinct keys, best-effort degrade to
    empty/NULL on failure -- never fails the job).
  - DB/WB label (UPH-05) is computed in Python via
    config.workcenter_groups.get_workcenter_group(WORKCENTERNAME) -- NOT
    Oracle SQL, NOT EQUIPMENT_ID prefix enumeration (retired precedent,
    business-rules.md EA-07). Kept only when the result is 焊接_DB/焊接_WB,
    else NULL.
  - UPH_VALUE (UPH-04): raw PARAMETER_VALUE cast via a plain TRY_CAST(...AS
    DOUBLE) in DuckDB -- NO scale conversion (x100 / /100) at any layer.
  - Heavy-query slot is INHERITED from BaseChunkedDuckDBJob.run() -- this
    module never re-acquires the semaphore a second time (design.md Open Risks).

Module-level register_job_type() fires at import time (job-registry-central).
"""

from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from mes_dashboard.core.base_chunked_duckdb_job import BaseChunkedDuckDBJob, ChunkStrategy

logger = logging.getLogger("mes_dashboard.uph_performance_worker")

UPH_PERFORMANCE_JOB_TIMEOUT_SECONDS: int = max(
    60, int(os.getenv("UPH_PERFORMANCE_JOB_TIMEOUT_SECONDS", "1800"))
)
UPH_PERFORMANCE_WORKER_QUEUE: str = os.getenv(
    "UPH_PERFORMANCE_WORKER_QUEUE", "uph-performance-query"
)

_JOB_PREFIX = "uph-performance"
_NAMESPACE = "uph_performance"

# UPH-03: family-conditional PARAMETER_NAME mapping. FIXED -- do not swap.
# Both parameter names were reconfigured on the equipment side and confirmed
# correct by the requesting engineer (2026-07); they intentionally do not
# match the earlier investigation's `UPHBonded` (business-rules.md UPH-03).
# This dict documents the mapping already hardcoded (as a literal Oracle CASE
# expression, per ADR-0017 Decision-1) in sql/uph_performance.sql -- kept here
# only so tests/tooling can assert the two stay in sync.
FAMILY_PARAMETER_MAP: Dict[str, str] = {
    "GDBA": "BondUPH",
    "GWBA": "fHCM_UPH",
}

# UPH-05: DB/WB labels kept from workcenter_groups.get_workcenter_group() --
# any other group (or None/unmapped) collapses to a NULL label.
_DB_WB_LABELS = {"焊接_DB", "焊接_WB"}

_CHUNK_HOURS = 6

_MAX_ORACLE_IN_LIST = 999


# ── Coarse filter builders (data-shape §3.29 Oracle coarse-filter mapping) ────

def _build_family_filter(families: Optional[List[str]]) -> str:
    """Build the mandatory GDBA/GWBA family-scope predicate (UPH-02).

    Empty/absent families -> both families (never any other prefix).
    """
    cleaned = {str(f).strip().upper() for f in (families or []) if str(f).strip()}
    cleaned &= {"GDBA", "GWBA"}
    if not cleaned or cleaned == {"GDBA", "GWBA"}:
        return "(e.EQUIPMENT_ID LIKE 'GDBA%' OR e.EQUIPMENT_ID LIKE 'GWBA%')"
    if cleaned == {"GDBA"}:
        return "e.EQUIPMENT_ID LIKE 'GDBA%'"
    return "e.EQUIPMENT_ID LIKE 'GWBA%'"


def _build_equipment_ids_filter(equipment_ids: Optional[List[str]]) -> tuple[str, Dict[str, Any]]:
    """Build "AND e.EQUIPMENT_ID IN (...)" -- empty ("", {}) when absent.

    Deliberately no leading/embedded newline in the returned fragment:
    `SQLLoader.load_with_params` substitutes `{{ EXTRA_FILTERS }}` via a
    plain global string replace, which also matches the placeholder's own
    mention inside this template's doc-comment header. An embedded `\n`
    would split that single `--` comment line in two, leaving the second
    half uncommented -- Oracle then rejects the resulting statement with
    ORA-00900. A space-separated clause is syntactically identical for
    Oracle and immune to this failure mode regardless of where the
    placeholder text lands.
    """
    cleaned = [str(v).strip() for v in (equipment_ids or []) if str(v).strip()]
    if not cleaned:
        return "", {}
    placeholders = ", ".join(f":eqid_{i}" for i in range(len(cleaned)))
    params = {f"eqid_{i}": v for i, v in enumerate(cleaned)}
    return f"AND e.EQUIPMENT_ID IN ({placeholders})", params


def _build_container_exists_filter(
    values: Optional[List[str]], column: str, prefix: str
) -> tuple[str, Dict[str, Any]]:
    """EXISTS semi-join on DW_MES_CONTAINER for pj_types/packages (mirrors EA-10).

    No embedded newline in the returned fragment -- see
    `_build_equipment_ids_filter`'s docstring for why.
    """
    cleaned = [str(v).strip() for v in (values or []) if str(v).strip()]
    if not cleaned:
        return "", {}
    placeholders = ", ".join(f":{prefix}_{i}" for i in range(len(cleaned)))
    clause = (
        "AND EXISTS (SELECT 1 FROM DWH.DW_MES_CONTAINER c"
        " WHERE c.CONTAINERNAME = e.LOT_ID"
        f" AND NVL(TRIM(c.{column}), '(NA)') IN ({placeholders}))"
    )
    params = {f"{prefix}_{i}": v for i, v in enumerate(cleaned)}
    return clause, params


def _build_workcenter_names_exists_filter(
    workcenter_names: Optional[List[str]],
) -> tuple[str, Dict[str, Any]]:
    """EXISTS semi-join on DW_MES_RESOURCE (OBJECTCATEGORY='ASSEMBLY') for workcenter_names.

    No embedded newline in the returned fragment -- see
    `_build_equipment_ids_filter`'s docstring for why.
    """
    cleaned = [str(v).strip() for v in (workcenter_names or []) if str(v).strip()]
    if not cleaned:
        return "", {}
    placeholders = ", ".join(f":wc_{i}" for i in range(len(cleaned)))
    clause = (
        "AND EXISTS (SELECT 1 FROM DWH.DW_MES_RESOURCE r"
        " WHERE r.RESOURCENAME = e.EQUIPMENT_ID"
        " AND r.OBJECTCATEGORY = 'ASSEMBLY'"
        f" AND NVL(TRIM(r.WORKCENTERNAME), '(NA)') IN ({placeholders}))"
    )
    params = {f"wc_{i}": v for i, v in enumerate(cleaned)}
    return clause, params


def _build_models_exists_filter(
    models: Optional[List[str]],
) -> tuple[str, Dict[str, Any]]:
    """EXISTS semi-join on DW_MES_RESOURCE.RESOURCEFAMILYNAME for the 機型 filter.

    RESOURCEFAMILYNAME is the real machine model (e.g. DBA_AD832UR, WBA_iHawk) --
    the coarse 機型 axis that replaces the old GDBA/GWBA-only selector. Mirrors
    `_build_workcenter_names_exists_filter` (same DW_MES_RESOURCE bridge,
    RESOURCENAME = EQUIPMENT_ID). No embedded newline -- see
    `_build_equipment_ids_filter`'s docstring for why.
    """
    cleaned = [str(v).strip() for v in (models or []) if str(v).strip()]
    if not cleaned:
        return "", {}
    placeholders = ", ".join(f":mdl_{i}" for i in range(len(cleaned)))
    clause = (
        "AND EXISTS (SELECT 1 FROM DWH.DW_MES_RESOURCE r"
        " WHERE r.RESOURCENAME = e.EQUIPMENT_ID"
        " AND r.OBJECTCATEGORY = 'ASSEMBLY'"
        f" AND NVL(TRIM(r.RESOURCEFAMILYNAME), '(NA)') IN ({placeholders}))"
    )
    params = {f"mdl_{i}": v for i, v in enumerate(cleaned)}
    return clause, params


def _build_time_chunks(date_from: str, date_to: str) -> List[Dict[str, str]]:
    """Build <=6h [chunk_start, chunk_end) windows spanning [date_from, date_to] inclusive.

    UPH-01: every chunk window is <=6h -- the detail JOIN over this table has
    previously timed out at >180s over a 24h window; a single unchunked
    full-range query is forbidden.
    """
    start_dt = datetime.strptime(date_from, "%Y-%m-%d")
    end_dt_excl = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)

    chunks: List[Dict[str, str]] = []
    current = start_dt
    while current < end_dt_excl:
        chunk_end = min(current + timedelta(hours=_CHUNK_HOURS), end_dt_excl)
        chunks.append({
            "chunk_start": current.strftime("%Y-%m-%d %H:%M:%S"),
            "chunk_end": chunk_end.strftime("%Y-%m-%d %H:%M:%S"),
        })
        current = chunk_end
    return chunks


# ── Enrichment bridges (post_aggregate, ADR-0017 Decision-3) ─────────────────

_LOT_PRODUCT_SQL_TEMPLATE = """\
SELECT
    TRIM(c.CONTAINERNAME)   AS LOT_ID,
    TRIM(c.PRODUCTLINENAME) AS PACKAGE,
    TRIM(c.PJ_TYPE)         AS PJ_TYPE,
    TRIM(c.PJ_BOP)          AS PJ_BOP,
    TRIM(c.PJ_FUNCTION)     AS PJ_FUNCTION
FROM DWH.DW_MES_CONTAINER c
WHERE c.CONTAINERNAME IN ({placeholders})
"""
_LOT_PRODUCT_COLUMNS = ["LOT_ID", "PACKAGE", "PJ_TYPE", "PJ_BOP", "PJ_FUNCTION"]

_RESOURCE_WORKCENTER_SQL_TEMPLATE = """\
SELECT
    TRIM(r.RESOURCENAME)        AS EQUIPMENT_ID,
    TRIM(r.WORKCENTERNAME)      AS WORKCENTERNAME,
    TRIM(r.RESOURCEFAMILYNAME)  AS MODEL
FROM DWH.DW_MES_RESOURCE r
WHERE r.OBJECTCATEGORY = 'ASSEMBLY'
  AND r.RESOURCENAME IN ({placeholders})
"""
# MODEL (RESOURCEFAMILYNAME, e.g. DBA_AD832UR) is carried into the spool so the
# real 機型 is a first-class visible dimension (trend grouping + detail column),
# not just a coarse filter -- same DW_MES_RESOURCE bridge, no extra query.
_RESOURCE_WORKCENTER_COLUMNS = ["EQUIPMENT_ID", "WORKCENTERNAME", "MODEL"]


def _empty_df(columns: List[str]):
    import pandas as pd
    return pd.DataFrame(columns=columns)


def _fetch_dim_df(keys: List[str], sql_template: str, columns: List[str], timeout_seconds: int):
    """Chunked ``IN (...)`` lookup (<=999 binds/chunk, Oracle IN-list limit).

    Deduped on the first column (the join key). Preserves real NULLs in the
    other columns (no NVL('(NA)') coalescing -- data-shape §3.29 requires
    actual NULL on no-match, unlike the coarse EXISTS-filter convention).
    """
    import pandas as pd

    cleaned = sorted({str(v).strip() for v in keys if v is not None and str(v).strip()})
    if not cleaned:
        return _empty_df(columns)

    from mes_dashboard.core.database import read_sql_df_slow

    frames = []
    for start in range(0, len(cleaned), _MAX_ORACLE_IN_LIST):
        chunk = cleaned[start:start + _MAX_ORACLE_IN_LIST]
        placeholders = ", ".join(f":k{i}" for i in range(len(chunk)))
        params = {f"k{i}": v for i, v in enumerate(chunk)}
        frames.append(read_sql_df_slow(
            sql_template.format(placeholders=placeholders),
            params=params,
            timeout_seconds=timeout_seconds,
            caller="uph_performance_worker_dim_lookup",
        ))

    combined = pd.concat(frames, ignore_index=True) if frames else _empty_df(columns)
    if not set(columns).issubset(set(combined.columns)):
        logger.warning(
            "uph_performance_worker: dim lookup returned unexpected columns %s",
            list(combined.columns),
        )
        return _empty_df(columns)
    combined = combined[columns].dropna(subset=[columns[0]])
    combined[columns[0]] = combined[columns[0]].astype(str).str.strip()
    return combined.drop_duplicates(subset=[columns[0]], keep="first")


def _safe_lot_product_df(events_df, timeout_seconds: int):
    """Best-effort LOT_ID -> Package/Type/PJ_BOP/PJ_FUNCTION lookup frame."""
    try:
        if events_df is None or events_df.empty or "LOT_ID" not in events_df.columns:
            return _empty_df(_LOT_PRODUCT_COLUMNS)
        return _fetch_dim_df(
            events_df["LOT_ID"].dropna().unique().tolist(),
            _LOT_PRODUCT_SQL_TEMPLATE, _LOT_PRODUCT_COLUMNS, timeout_seconds,
        )
    except Exception as exc:
        logger.warning(
            "uph_performance_worker: lot_product lookup failed, proceeding without "
            "product dims: %s", exc,
        )
        return _empty_df(_LOT_PRODUCT_COLUMNS)


def _safe_workcenter_df(events_df, timeout_seconds: int):
    """Best-effort EQUIPMENT_ID -> WORKCENTERNAME lookup frame, with DB_WB_LABEL added."""
    try:
        if events_df is None or events_df.empty or "EQUIPMENT_ID" not in events_df.columns:
            df = _empty_df(_RESOURCE_WORKCENTER_COLUMNS)
        else:
            df = _fetch_dim_df(
                events_df["EQUIPMENT_ID"].dropna().unique().tolist(),
                _RESOURCE_WORKCENTER_SQL_TEMPLATE, _RESOURCE_WORKCENTER_COLUMNS, timeout_seconds,
            )
    except Exception as exc:
        logger.warning(
            "uph_performance_worker: workcenter lookup failed, proceeding without "
            "workcenter dims: %s", exc,
        )
        df = _empty_df(_RESOURCE_WORKCENTER_COLUMNS)

    df = df.copy()
    df["DB_WB_LABEL"] = df["WORKCENTERNAME"].map(_compute_db_wb_label)
    return df


def _compute_db_wb_label(workcenter_name: Optional[str]) -> Optional[str]:
    """Map WORKCENTERNAME -> 焊接_DB/焊接_WB via workcenter_groups (UPH-05).

    MUST use config.workcenter_groups.get_workcenter_group() -- MUST NOT
    derive the label from a closed equipment-id-prefix enumeration (the
    equivalent approach for EAP ALARM was retired in production because the
    closed enum never matched real equipment-id data; business-rules.md
    EA-07). Unmapped or NULL WORKCENTERNAME -> NULL label (not an error, not
    a default guess).
    """
    from mes_dashboard.config.workcenter_groups import get_workcenter_group

    if not workcenter_name:
        return None
    group_name, _order = get_workcenter_group(workcenter_name)
    return group_name if group_name in _DB_WB_LABELS else None


def _build_final_select_sql(coarse_filter_hash: str) -> str:
    """Build the post_aggregate final SELECT (concat + enrichment bridges).

    UPH_VALUE is a plain TRY_CAST of the raw Oracle PARAMETER_VALUE -- NO
    scale conversion (UPH-04; no `* 100` / `/ 100` anywhere in this string).
    """
    return f"""
        SELECT
            e.LOT_ID,
            e.EQUIPMENT_ID,
            e.EQUIPMENT_FAMILY,
            CAST(e.EVENT_TIME AS TIMESTAMP)     AS EVENT_TIME,
            e.PARAMETER_NAME,
            TRY_CAST(e.UPH_VALUE_RAW AS DOUBLE) AS UPH_VALUE,
            w.WORKCENTERNAME,
            w.MODEL,
            w.DB_WB_LABEL,
            lp.PACKAGE,
            lp.PJ_TYPE,
            lp.PJ_BOP,
            lp.PJ_FUNCTION,
            '{coarse_filter_hash}'              AS coarse_filter_hash
        FROM events_raw e
        LEFT JOIN lot_product lp   ON lp.LOT_ID = TRIM(e.LOT_ID)
        LEFT JOIN workcenter_info w ON w.EQUIPMENT_ID = TRIM(e.EQUIPMENT_ID)
    """


class UphPerformanceJob(BaseChunkedDuckDBJob):
    """Unified chunked Oracle->DuckDB job for UPH Performance (ADR-0017).

    ChunkStrategy: TIME (<=6h windows). requires_cross_chunk_reduction=False:
    each event row is independent -- no seam-straddling aggregation (unlike
    ProductionAchievementJob's SPECNAME re-aggregation, ADR-0016). post_aggregate
    is a plain concat of chunk parquets plus the two enrichment bridges.
    """

    namespace = _NAMESPACE
    chunk_strategy = ChunkStrategy.TIME
    requires_cross_chunk_reduction = False

    def __init__(self, job_id: str, params: dict) -> None:
        super().__init__(job_id)
        self.params = params
        self._spool_key: str = ""
        self._spool_path: str = ""
        self._coarse_filter_hash: str = ""
        self._family_filter: str = ""
        self._extra_filters: str = ""
        self._extra_params: Dict[str, Any] = {}

    def pre_query(self) -> None:
        """Parse params, compute spool key, build <=6h TIME chunks."""
        date_from = str(self.params.get("date_from", "")).strip()
        date_to = str(self.params.get("date_to", "")).strip()
        families = list(self.params.get("families", []))
        models = list(self.params.get("models", []))
        workcenter_names = list(self.params.get("workcenter_names", []))
        packages = list(self.params.get("packages", []))
        pj_types = list(self.params.get("pj_types", []))
        equipment_ids = list(self.params.get("equipment_ids", []))

        self._family_filter = _build_family_filter(families)

        eq_clause, eq_params = _build_equipment_ids_filter(equipment_ids)
        mdl_clause, mdl_params = _build_models_exists_filter(models)
        pjt_clause, pjt_params = _build_container_exists_filter(pj_types, "PJ_TYPE", "pjt")
        pkg_clause, pkg_params = _build_container_exists_filter(packages, "PRODUCTLINENAME", "pkg")
        wc_clause, wc_params = _build_workcenter_names_exists_filter(workcenter_names)

        self._extra_filters = "".join(
            f"\n  {clause}" for clause in (eq_clause, mdl_clause, pjt_clause, pkg_clause, wc_clause) if clause
        )
        self._extra_params = {**eq_params, **mdl_params, **pjt_params, **pkg_params, **wc_params}

        from mes_dashboard.services.uph_performance_cache import (
            make_uph_performance_spool_key,
            get_uph_performance_spool_path,
        )
        self._spool_key = make_uph_performance_spool_key(
            date_from, date_to, families, workcenter_names, packages, pj_types, equipment_ids,
            models=models,
        )
        self._spool_path = get_uph_performance_spool_path(self._spool_key)
        self._coarse_filter_hash = hashlib.sha256(self._spool_key.encode("utf-8")).hexdigest()[:8]

        self._chunks = _build_time_chunks(date_from, date_to)

    def build_chunk_sql(self, chunk_params: dict) -> tuple[str, dict]:
        from mes_dashboard.sql import SQLLoader

        sql = SQLLoader.load_with_params(
            "uph_performance",
            FAMILY_FILTER=self._family_filter,
            EXTRA_FILTERS=self._extra_filters,
        )
        binds: Dict[str, Any] = {
            "chunk_start": chunk_params["chunk_start"],
            "chunk_end": chunk_params["chunk_end"],
            **self._extra_params,
        }
        return sql, binds

    def post_aggregate(self, job_duckdb_path: "str | None") -> str:
        """Concat all chunk parquets, bridge product/workcenter dims, write spool."""
        import duckdb
        import pandas as pd
        import pyarrow as pa
        import pyarrow.parquet as pq

        chunk_dir = self._make_chunk_parquet_dir(self.job_id)
        all_parquets = sorted(chunk_dir.glob("chunk-*.parquet"))

        if all_parquets:
            tables = [pq.read_table(str(p)) for p in all_parquets]
            events_df = pa.concat_tables(tables).to_pandas()
        else:
            events_df = pd.DataFrame(columns=[
                "LOT_ID", "EQUIPMENT_ID", "EQUIPMENT_FAMILY", "EVENT_TIME",
                "PARAMETER_NAME", "UPH_VALUE_RAW",
            ])

        lot_product_df = _safe_lot_product_df(events_df, UPH_PERFORMANCE_JOB_TIMEOUT_SECONDS)
        workcenter_df = _safe_workcenter_df(events_df, UPH_PERFORMANCE_JOB_TIMEOUT_SECONDS)

        os.makedirs(os.path.dirname(self._spool_path), exist_ok=True)

        con = duckdb.connect()
        try:
            con.register("events_raw", events_df)
            con.register("lot_product", lot_product_df)
            con.register("workcenter_info", workcenter_df)

            final_sql = _build_final_select_sql(self._coarse_filter_hash)

            if events_df.empty:
                con.execute(
                    f"COPY (SELECT * FROM ({final_sql}) t WHERE FALSE) TO '{self._spool_path}'"
                    " (FORMAT PARQUET, CODEC 'SNAPPY')"
                )
                row_count = 0
            else:
                con.execute(
                    f"COPY ({final_sql}) TO '{self._spool_path}' (FORMAT PARQUET, CODEC 'SNAPPY')"
                )
                row_count = con.execute(
                    f"SELECT COUNT(*) FROM read_parquet('{self._spool_path}')"
                ).fetchone()[0]
        finally:
            con.close()

        logger.info(
            "UphPerformanceJob.post_aggregate: parquet written path=%s rows=%d job_id=%s",
            self._spool_path, row_count, self.job_id,
        )

        try:
            from mes_dashboard.core.query_spool_store import (
                register_spool_file,
                QUERY_SPOOL_TTL_SECONDS,
            )
            register_spool_file(
                _NAMESPACE, self._spool_key, Path(self._spool_path),
                row_count, ttl_seconds=QUERY_SPOOL_TTL_SECONDS,
            )
        except Exception as exc:
            logger.warning("UphPerformanceJob.post_aggregate: spool registration failed: %s", exc)

        return self._spool_path

    def progress_report(self, pct: int) -> None:
        """Report progress via async_query_job_service (lazy import to avoid circular)."""
        from mes_dashboard.services.async_query_job_service import update_job_progress
        update_job_progress(_JOB_PREFIX, self.job_id, pct=str(pct))


def execute_uph_performance_unified_job(job_id: str, **params: Any) -> None:
    """RQ entry point for UphPerformanceJob (UPH_PERFORMANCE_USE_UNIFIED_JOB=on path).

    Called by the RQ worker process. Creates UphPerformanceJob and runs the
    template method. Heavy-query slot is acquired automatically inside
    BaseChunkedDuckDBJob.run() -- do NOT acquire it here again.
    """
    from mes_dashboard.rq_worker_preload import ensure_rq_logging
    ensure_rq_logging()

    from mes_dashboard.services.async_query_job_service import complete_job

    logger.info("execute_uph_performance_unified_job: started job_id=%s", job_id)
    try:
        job = UphPerformanceJob(job_id=job_id, params=params)
        spool_path = job.run()
        complete_job(_JOB_PREFIX, job_id, query_id=job._spool_key)
        logger.info(
            "execute_uph_performance_unified_job: completed job_id=%s spool_path=%s",
            job_id, spool_path,
        )
    except Exception as exc:
        logger.error(
            "execute_uph_performance_unified_job: failed job_id=%s: %s", job_id, exc, exc_info=True,
        )
        complete_job(_JOB_PREFIX, job_id, error=str(exc))
        raise


# ── Central job registry ───────────────────────────────────────────────────────
from mes_dashboard.services.job_registry import JobTypeConfig, register_job_type  # noqa: E402

register_job_type(JobTypeConfig(
    job_type="uph-performance",
    queue_name=UPH_PERFORMANCE_WORKER_QUEUE,
    worker_fn=execute_uph_performance_unified_job,
    timeout_seconds=UPH_PERFORMANCE_JOB_TIMEOUT_SECONDS,
    always_async=True,
))
