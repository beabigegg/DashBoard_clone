# -*- coding: utf-8 -*-
"""Material Consumption service — 料號用量報表.

Provides Oracle aggregate + Parquet spool + DuckDB regroup pipeline for
the /material-consumption report page.

Business rules implemented here:
  MC-01 — Consumption data source and grouping (DuckDB granularity)
  MC-02 — material_parts input cap (20), wildcard translation, meta-char rejection
  MC-03 — Summary spool cache key EXCLUDES granularity (ADR-0001)
  MC-04 — Detail async threshold via SYNC_ROW_LIMIT env var
  MC-05 — Parts list Redis cache warmed at startup via start_parts_cache_warmup()
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, Generator, List, Optional

import pandas as pd

from mes_dashboard.core.database import read_sql_df
from mes_dashboard.core.query_spool_store import (
    get_spool_file_path,
    store_spooled_df,
)
from mes_dashboard.core.redis_client import REDIS_ENABLED, get_redis_client
from mes_dashboard.services.batch_query_engine import compute_query_hash
from mes_dashboard.sql import QueryBuilder, SQLLoader

logger = logging.getLogger("mes_dashboard.material_consumption")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MATERIAL_CONSUMPTION_QUEUE = os.getenv(
    "MATERIAL_CONSUMPTION_WORKER_QUEUE", "material-consumption"
)
_SYNC_ROW_LIMIT = int(os.getenv("SYNC_ROW_LIMIT", "30000"))
_MAX_PARTS = 20
_SUMMARY_NAMESPACE = "material_consumption_summary"
_DETAIL_NAMESPACE = "material_consumption_detail"

# Redis cache for DISTINCT MATERIALPARTNAME list
_PARTS_CACHE_KEY = "mc:parts_list_v2"
_PARTS_CACHE_TTL = 86400  # 24 hours

# SQL meta-char pattern (MC-02)
_META_CHAR_RE = re.compile(r"['\;]|--|/\*|\*/|[\x00-\x1f]")


# ---------------------------------------------------------------------------
# Redis-cached parts list
# ---------------------------------------------------------------------------


def _get_parts_list() -> List[Dict[str, Optional[str]]]:
    """Return cached DISTINCT MATERIALPARTNAME + DESCRIPTION list. Redis TTL 24h."""
    import json as _json

    try:
        if REDIS_ENABLED:
            rc = get_redis_client()
            cached = rc.get(_PARTS_CACHE_KEY)
            if cached:
                return _json.loads(cached)

        # Cache miss — query Oracle
        df = read_sql_df(
            "SELECT DISTINCT TRIM(MATERIALPARTNAME) AS part, "
            "DESCRIPTION AS description "
            "FROM DWH.DW_MES_LOTMATERIALSHISTORY "
            "WHERE MATERIALPARTNAME IS NOT NULL ORDER BY 1",
            {},
        )
        if df is None or df.empty:
            return []

        # Resolve column names case-insensitively
        col_map = {c.lower(): c for c in df.columns}
        name_col = col_map.get("part")
        desc_col = col_map.get("description")
        if name_col is None:
            return []

        parts: List[Dict[str, Optional[str]]] = []
        seen: set = set()
        for _, row in df.iterrows():
            name_val = row[name_col]
            if name_val is None:
                continue
            name_str = str(name_val)
            if name_str in seen:
                continue
            seen.add(name_str)
            desc_val: Optional[str] = None
            if desc_col is not None:
                raw = row[desc_col]
                if raw is not None and not (isinstance(raw, float) and pd.isna(raw)):
                    desc_val = str(raw)
            parts.append({"name": name_str, "description": desc_val})

        parts.sort(key=lambda d: d["name"])  # type: ignore[arg-type]

        if REDIS_ENABLED:
            rc = get_redis_client()
            rc.set(_PARTS_CACHE_KEY, _json.dumps(parts), ex=_PARTS_CACHE_TTL)

        return parts
    except Exception as exc:
        logger.warning("_get_parts_list failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Typed exceptions
# ---------------------------------------------------------------------------


class ValidationError(ValueError):
    """Raised when input validation fails (MC-02). Maps to 400 VALIDATION_ERROR."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class CacheExpiredError(LookupError):
    """Raised when spool is missing/expired (MC-03). Maps to 410 CACHE_EXPIRED."""

    def __init__(self, message: str = "查詢已過期，請重新查詢") -> None:
        super().__init__(message)
        self.message = message


# ---------------------------------------------------------------------------
# Input validation helpers (MC-02)
# ---------------------------------------------------------------------------


def validate_material_parts(parts: Any) -> List[Dict[str, str]]:
    """Validate material_parts list and return parsed token list.

    Each token dict has: {kind: 'exact'|'pattern', bound_value: str}
    Raises ValidationError on cap violation (>20) or SQL meta-char presence.
    Translates '*' → '%' for pattern tokens, escaping '%' and '_'.
    """
    if not isinstance(parts, list):
        raise ValidationError("material_parts 必須為陣列")

    # Flatten any nested lists and stringify
    flat: List[str] = []
    for item in parts:
        if isinstance(item, str):
            flat.append(item.strip())
        else:
            flat.append(str(item).strip())

    # Drop empties
    flat = [t for t in flat if t]

    if not flat:
        raise ValidationError("material_parts 不可為空")

    # Cap (MC-02)
    if len(flat) > _MAX_PARTS:
        raise ValidationError(
            f"material_parts 上限 {_MAX_PARTS} 筆，收到 {len(flat)} 筆"
        )

    tokens: List[Dict[str, str]] = []
    for tok in flat:
        # Meta-char check (MC-02) — BEFORE any substitution
        if _META_CHAR_RE.search(tok):
            raise ValidationError(
                f"material_parts 含有不允許的字元: {tok!r}"
            )

        star_count = tok.count("*")
        if star_count > 1:
            raise ValidationError(
                f"material_parts 萬用字元 * 每筆最多一個: {tok!r}"
            )

        if star_count == 0:
            tokens.append({"kind": "exact", "bound_value": tok})
        else:
            # Escape % and _ in the literal portion, then translate * → %
            literal = tok.replace("%", r"\%").replace("_", r"\_")
            bound = literal.replace("*", "%")
            tokens.append({"kind": "pattern", "bound_value": bound})

    return tokens


def _add_parts_condition(builder: QueryBuilder, tokens: List[Dict[str, str]], column: str = "m.MATERIALPARTNAME") -> None:
    """Add IN + LIKE mixed condition for validated material_parts tokens."""
    if not tokens:
        return

    exact_values = [t["bound_value"] for t in tokens if t["kind"] == "exact"]
    pattern_values = [t["bound_value"] for t in tokens if t["kind"] == "pattern"]

    conditions: List[str] = []

    if exact_values:
        builder_params: List[str] = []
        for val in exact_values:
            p = builder._next_param()
            builder_params.append(f":{p}")
            builder.params[p] = val
        conditions.append(f"{column} IN ({', '.join(builder_params)})")

    for val in pattern_values:
        p = builder._next_param()
        builder.params[p] = val
        conditions.append(f"{column} LIKE :{p} ESCAPE '\\'")

    if conditions:
        builder.add_condition(f"({' OR '.join(conditions)})")


# ---------------------------------------------------------------------------
# Cache key computation (MC-03 — EXCLUDES granularity)
# ---------------------------------------------------------------------------


def _compute_summary_cache_key(
    material_parts: List[str],
    start_date: str,
    end_date: str,
) -> str:
    """Compute cache key for summary spool.

    EXCLUDES granularity per ADR-0001 / MC-03: one spool serves all
    granularity views (day/week/month/quarter).
    Also excludes workcenter_groups, primary_categories, pj_types — all
    post-Oracle filtering is now done in DuckDB apply_view().
    """
    key_params = {
        "material_parts": sorted(material_parts),
        "start_date": start_date,
        "end_date": end_date,
    }
    return compute_query_hash(key_params)


def _compute_detail_cache_key(
    material_parts: List[str],
    start_date: str,
    end_date: str,
) -> str:
    key_params = {
        "detail": True,
        "material_parts": sorted(material_parts),
        "start_date": start_date,
        "end_date": end_date,
    }
    return compute_query_hash(key_params)


# ---------------------------------------------------------------------------
# Oracle query helpers
# ---------------------------------------------------------------------------


def _build_summary_sql(
    tokens: List[Dict[str, str]],
    start_date: str,
    end_date: str,
) -> tuple[str, Dict[str, Any]]:
    """Build parameterized summary_by_day SQL.

    Only applies date range and material_parts filters at Oracle level.
    pj_type filtering is deferred to DuckDB apply_view().
    """
    base_sql = SQLLoader.load("material_consumption/summary_by_day")
    builder = QueryBuilder(base_sql=base_sql)

    # Date range
    p_start = builder._next_param()
    p_end = builder._next_param()
    builder.params[p_start] = start_date
    builder.params[p_end] = end_date
    builder.add_condition(f"m.TXNDATE >= TO_DATE(:{p_start}, 'YYYY-MM-DD')")
    builder.add_condition(f"m.TXNDATE < TO_DATE(:{p_end}, 'YYYY-MM-DD') + 1")

    # material_parts (MC-02)
    _add_parts_condition(builder, tokens)

    return builder.build()


def _build_detail_sql(
    tokens: List[Dict[str, str]],
    start_date: str,
    end_date: str,
) -> tuple[str, Dict[str, Any]]:
    """Build parameterized detail_rows SQL.

    Only applies date range and material_parts filters at Oracle level.
    """
    base_sql = SQLLoader.load("material_consumption/detail_rows")
    builder = QueryBuilder(base_sql=base_sql)

    p_start = builder._next_param()
    p_end = builder._next_param()
    builder.params[p_start] = start_date
    builder.params[p_end] = end_date
    builder.add_condition(f"m.TXNDATE >= TO_DATE(:{p_start}, 'YYYY-MM-DD')")
    builder.add_condition(f"m.TXNDATE < TO_DATE(:{p_end}, 'YYYY-MM-DD') + 1")

    _add_parts_condition(builder, tokens)

    return builder.build()


# ---------------------------------------------------------------------------
# Internal: compute summary from spool file
# ---------------------------------------------------------------------------


def _compute_summary_from_spool(
    spool_path: str,
    *,
    granularity: str,
    types: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Regroup summary spool by granularity using DuckDB (no Oracle).

    Optionally filter by pj_type via the `types` parameter.
    """
    from mes_dashboard.services.material_consumption_duckdb_runtime import regroup_summary
    return regroup_summary(spool_path, granularity=granularity, types=types)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_filter_options() -> Dict[str, Any]:
    """Return distinct filter values for UI dropdowns.

    Returns: {parts, pj_types}
    - parts: Redis-cached list of {name, description} dicts (24h TTL).
    - pj_types: from shared container_filter_cache.
    Falls back to empty lists on failure.
    """
    from mes_dashboard.services.container_filter_cache import get_pj_types

    return {
        "parts": _get_parts_list(),
        "pj_types": get_pj_types(),
    }


def get_summary(
    material_parts: List[str],
    start_date: str,
    end_date: str,
    granularity: str = "month",
) -> Dict[str, Any]:
    """Run summary query and return {query_id, kpi, trend, type_breakdown}.

    MC-02: validates material_parts (cap + meta-char + wildcard).
    MC-03: cache key EXCLUDES granularity; one spool serves all views.
    Idempotent: if spool already exists, skips Oracle and regroups from spool.
    Always synchronous. pj_type filtering is deferred to apply_view().
    """
    # MC-02 validation
    tokens = validate_material_parts(material_parts)

    # Raw bound values for cache key
    raw_parts = [t["bound_value"] for t in tokens]

    # Build cache key (MC-03: granularity excluded; no filter_kwargs)
    query_id = _compute_summary_cache_key(raw_parts, start_date, end_date)

    # Idempotency check (MC-05 / spool pattern)
    spool_path = get_spool_file_path(_SUMMARY_NAMESPACE, query_id)
    if spool_path and __import__("pathlib").Path(spool_path).exists():
        # Spool hit — regroup without Oracle
        view_result = _compute_summary_from_spool(spool_path, granularity=granularity)
        return {
            "query_id": query_id,
            **view_result,
        }

    # Spool miss — query Oracle
    sql, params = _build_summary_sql(tokens, start_date, end_date)
    df = read_sql_df(sql, params)

    if df is None:
        df = pd.DataFrame(columns=[
            "txn_date", "material_part", "pj_type",
            "total_consumed", "total_required", "lot_count", "workorder_count",
        ])

    # Normalize types per data-shape-contract.md §3.9.1
    if not df.empty:
        for float_col in ("total_consumed", "total_required"):
            if float_col in df.columns:
                df[float_col] = df[float_col].astype(float)
        for int_col in ("lot_count", "workorder_count"):
            if int_col in df.columns:
                df[int_col] = df[int_col].astype(int)

    # Write spool
    store_spooled_df(_SUMMARY_NAMESPACE, query_id, df)

    # Regroup (even empty df returns empty KPI/trend/breakdown)
    spool_path_new = get_spool_file_path(_SUMMARY_NAMESPACE, query_id)
    if spool_path_new and __import__("pathlib").Path(spool_path_new).exists():
        view_result = _compute_summary_from_spool(spool_path_new, granularity=granularity)
    else:
        # Fallback: compute from df in-memory via temp spool
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp:
            df.to_parquet(tmp.name, engine="pyarrow", index=False)
            view_result = _compute_summary_from_spool(tmp.name, granularity=granularity)

    return {
        "query_id": query_id,
        **view_result,
    }


def apply_view(
    query_id: str,
    granularity: str = "month",
    *,
    types: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Regroup existing summary spool by granularity — no Oracle query (MC-03).

    Optionally filter rows by pj_type via the `types` parameter (DuckDB WHERE clause).
    Raises CacheExpiredError if spool is missing or expired → 410.
    """
    import pathlib

    spool_path = get_spool_file_path(_SUMMARY_NAMESPACE, query_id)
    if not spool_path or not pathlib.Path(spool_path).exists():
        raise CacheExpiredError(f"查詢 {query_id} 已過期，請重新查詢")

    return _compute_summary_from_spool(spool_path, granularity=granularity, types=types)


def get_detail_summary(
    material_parts: List[str],
    start_date: str,
    end_date: str,
    *,
    per_page: int = 20,
) -> Dict[str, Any]:
    """Run detail query. Sync if rows <= SYNC_ROW_LIMIT; async otherwise (MC-04).

    Sync (200): returns {async: False, query_id, rows, pagination}
    Async (202): returns {async: True, job_id, query_id}
    pj_type filtering on the detail spool is applied at the /detail/page level.
    """
    sync_limit = int(os.getenv("SYNC_ROW_LIMIT", str(_SYNC_ROW_LIMIT)))

    tokens = validate_material_parts(material_parts)
    raw_parts = [t["bound_value"] for t in tokens]
    query_id = _compute_detail_cache_key(raw_parts, start_date, end_date)

    # Idempotency check
    spool_path = get_spool_file_path(_DETAIL_NAMESPACE, query_id)
    if spool_path and __import__("pathlib").Path(spool_path).exists():
        # Already have spool — return first page
        result = get_detail_page(query_id, page=1, per_page=per_page)
        if result:
            return {"async": False, "query_id": query_id, **result}

    # Build and execute Oracle query
    sql, params = _build_detail_sql(tokens, start_date, end_date)
    df = read_sql_df(sql, params)
    if df is None:
        df = pd.DataFrame()

    row_count = len(df)

    if row_count > sync_limit:
        # Async path (MC-04) — enqueue RQ job
        import uuid as _uuid
        allocated_job_id = f"{MATERIAL_CONSUMPTION_QUEUE}-{_uuid.uuid4().hex[:12]}"
        job_kwargs = {
            "job_id": allocated_job_id,
            "query_id": query_id,
            "material_parts": raw_parts,
            "start_date": start_date,
            "end_date": end_date,
        }
        job_id, err = enqueue_job(
            queue_name=MATERIAL_CONSUMPTION_QUEUE,
            worker_fn=rq_material_consumption_job,
            owner="material-consumption",
            job_id=allocated_job_id,
            kwargs=job_kwargs,
        )
        if err:
            logger.error("Failed to enqueue material-consumption job: %s", err)
            raise RuntimeError(f"非同步佇列失敗: {err}")

        return {
            "async": True,
            "job_id": job_id,
            "query_id": query_id,
        }

    # Sync path — write spool and return first page
    store_spooled_df(_DETAIL_NAMESPACE, query_id, df)

    safe_per_page = max(1, min(per_page, 500))
    total = len(df)
    total_pages = max(1, (total + safe_per_page - 1) // safe_per_page)
    page_df = df.iloc[:safe_per_page].copy()
    from mes_dashboard.services.material_consumption_duckdb_runtime import _normalize_detail_df
    page_df = _normalize_detail_df(page_df)
    page_df = page_df.astype(object).where(page_df.notna(), None)

    return {
        "async": False,
        "query_id": query_id,
        "rows": page_df.to_dict("records"),
        "pagination": {
            "page": 1,
            "per_page": safe_per_page,
            "total_rows": total,
            "total_pages": total_pages,
        },
    }


def get_detail_page(
    query_id: str,
    page: int = 1,
    per_page: int = 20,
    *,
    pj_types: Optional[List[str]] = None,
) -> Optional[Dict[str, Any]]:
    """Return paginated rows from detail spool via DuckDB.

    Returns None if spool is unavailable.
    """
    from mes_dashboard.services.material_consumption_duckdb_runtime import (
        MaterialConsumptionDetailRuntime,
    )

    runtime = MaterialConsumptionDetailRuntime(query_id)
    return runtime.get_page(page=page, per_page=per_page, pj_types=pj_types)


_MC_JOB_PREFIX = "async"


def get_job_status(job_id: str) -> Dict[str, Any]:
    """Return RQ job status dict: {status, query_id?}."""
    from mes_dashboard.services.async_query_job_service import get_job_status as _get_job_status
    return _get_job_status(_MC_JOB_PREFIX, job_id)


def export_csv_stream(query_id: str) -> Generator[bytes, None, None]:
    """Stream detail spool as chunked CSV bytes (no full memory load)."""
    from mes_dashboard.services.material_consumption_duckdb_runtime import (
        MaterialConsumptionDetailRuntime,
    )

    runtime = MaterialConsumptionDetailRuntime(query_id)
    yield from runtime.export_csv()


# ---------------------------------------------------------------------------
# RQ job entry point (MC-04 async path)
# ---------------------------------------------------------------------------


def rq_material_consumption_job(
    job_id: str,
    query_id: str,
    material_parts: List[str],
    start_date: str,
    end_date: str,
    **_ignored: Any,
) -> None:
    """RQ worker: execute detail Oracle query and write spool.

    Calls complete_job() on both success and failure paths so the Redis
    metadata key transitions to a terminal status and the frontend poll
    composable does not hang.
    """
    from mes_dashboard.services.async_query_job_service import complete_job as _complete_job

    logger.info("rq_material_consumption_job start job_id=%s query_id=%s", job_id, query_id)

    # Check idempotency — skip if spool already written
    spool_path = get_spool_file_path(_DETAIL_NAMESPACE, query_id)
    if spool_path and __import__("pathlib").Path(spool_path).exists():
        logger.info("rq_material_consumption_job: spool exists, skip query_id=%s", query_id)
        _complete_job(_MC_JOB_PREFIX, job_id, query_id=query_id)
        return

    # Re-validate (tokens already validated at submit time, but worker re-validates for safety)
    try:
        tokens = validate_material_parts(material_parts)
    except ValidationError as exc:
        logger.error("rq_material_consumption_job: validation failed: %s", exc)
        _complete_job(_MC_JOB_PREFIX, job_id, error=str(exc))
        raise

    try:
        sql, params = _build_detail_sql(tokens, start_date, end_date)
        df = read_sql_df(sql, params)
        if df is None:
            df = pd.DataFrame()

        store_spooled_df(_DETAIL_NAMESPACE, query_id, df)
        logger.info(
            "rq_material_consumption_job done job_id=%s query_id=%s rows=%d",
            job_id, query_id, len(df),
        )
        _complete_job(_MC_JOB_PREFIX, job_id, query_id=query_id)
    except Exception as exc:
        logger.error(
            "rq_material_consumption_job failed job_id=%s query_id=%s: %s",
            job_id, query_id, exc, exc_info=True,
        )
        _complete_job(_MC_JOB_PREFIX, job_id, error=str(exc))
        raise


# ---------------------------------------------------------------------------
# Deferred import to avoid circular dependency at module load
# ---------------------------------------------------------------------------


def enqueue_job(*args: Any, **kwargs: Any):
    from mes_dashboard.services.async_query_job_service import enqueue_job as _enqueue
    return _enqueue(*args, **kwargs)


def start_parts_cache_warmup() -> None:
    """Warm the parts list Redis cache at startup in a background daemon thread.

    Calls _get_parts_list() after a 10s delay — that function handles the full
    Redis check → Oracle query → cache write pipeline. Skipped when Redis is off.
    Safe for multi-worker gunicorn: concurrent writes to the same Redis key are
    idempotent (last write wins, data is identical).
    """
    import threading
    import time

    try:
        if not REDIS_ENABLED:
            logger.info("material_consumption parts warmup skipped (Redis disabled)")
            return
    except Exception:
        return

    def _run() -> None:
        time.sleep(10)
        try:
            _get_parts_list()
            logger.info("material_consumption parts list cache warmup complete")
        except Exception as exc:
            logger.warning("material_consumption parts list cache warmup failed: %s", exc)

    threading.Thread(
        target=_run,
        daemon=True,
        name="material-consumption-parts-warmup",
    ).start()
    logger.info("material_consumption parts list cache warmup thread started")
