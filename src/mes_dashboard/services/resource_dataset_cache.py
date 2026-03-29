# -*- coding: utf-8 -*-
"""Resource-history dataset cache.

Primary query (POST /query) → Oracle → spool to Parquet → call DuckDB apply_view() → return result.
Supplementary view (GET /view) → read spool → DuckDB apply_view() → return result.

Cache layers:
  L1: ProcessLevelCache (in-process, per-worker)
  L2: spool file + Redis metadata pointer (< 1 KB)
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from mes_dashboard.core.cache import ProcessLevelCache, register_process_cache
from mes_dashboard.core.database import read_sql_df_slow as read_sql_df
from mes_dashboard.core.query_spool_store import (
    QUERY_SPOOL_DIR,
    get_spool_file_path,
    register_spool_file,
    store_spooled_df,
)

logger = logging.getLogger("mes_dashboard.resource_dataset_cache")

from mes_dashboard.config.constants import CACHE_TTL_DATASET
_CACHE_TTL = CACHE_TTL_DATASET
_CACHE_MAX_SIZE = 1
_REDIS_NAMESPACE = "resource_dataset"

_dataset_cache = ProcessLevelCache(ttl_seconds=_CACHE_TTL, max_size=_CACHE_MAX_SIZE)
register_process_cache(
    "resource_dataset", _dataset_cache, "Resource Dataset (L1, 15min)"
)

_SQL_DIR = Path(__file__).resolve().parent.parent / "sql" / "resource_history"


# ============================================================
# SQL loading
# ============================================================


@lru_cache(maxsize=4)
def _load_sql(name: str) -> str:
    path = _SQL_DIR / f"{name}.sql"
    return path.read_text(encoding="utf-8")


# ============================================================
# Query ID
# ============================================================


def _make_query_id(params: dict) -> str:
    """Deterministic hash from primary query params."""
    canonical = json.dumps(params, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


# ============================================================
# Cache existence check and write
# ============================================================


def _has_cached_df(query_id: str) -> bool:
    """Check if query_id has cached data (L1 marker or spool exists)."""
    if _dataset_cache.get(query_id) is not None:
        return True
    return get_spool_file_path(_REDIS_NAMESPACE, query_id) is not None


def _store_df(query_id: str, df: pd.DataFrame) -> None:
    """Write to spool; L1 gets lightweight marker."""
    _dataset_cache.set(query_id, True)  # lightweight marker
    store_spooled_df(_REDIS_NAMESPACE, query_id, df, ttl_seconds=_CACHE_TTL)


# ============================================================
# Resource cache integration (reuse existing service)
# ============================================================


def _get_filtered_resources_and_lookup(
    *,
    workcenter_groups: Optional[List[str]] = None,
    families: Optional[List[str]] = None,
    resource_ids: Optional[List[str]] = None,
    is_production: bool = False,
    is_key: bool = False,
    is_monitor: bool = False,
) -> tuple:
    """Returns (resources_list, resource_lookup_dict, historyid_filter_sql)."""
    from mes_dashboard.services.resource_history_service import (
        _get_filtered_resources,
        _build_resource_lookup,
        _build_historyid_filter,
    )

    resources = _get_filtered_resources(
        workcenter_groups=workcenter_groups,
        families=families,
        resource_ids=resource_ids,
        is_production=is_production,
        is_key=is_key,
        is_monitor=is_monitor,
    )
    lookup = _build_resource_lookup(resources)
    historyid_filter = _build_historyid_filter(resources)
    return resources, lookup, historyid_filter


# ============================================================
# Primary query
# ============================================================


def execute_primary_query(
    *,
    start_date: str,
    end_date: str,
    granularity: str = "day",
    workcenter_groups: Optional[List[str]] = None,
    families: Optional[List[str]] = None,
    resource_ids: Optional[List[str]] = None,
    is_production: bool = False,
    is_key: bool = False,
    is_monitor: bool = False,
) -> Dict[str, Any]:
    """Execute Oracle query -> spool to Parquet -> return DuckDB-computed result."""

    query_id_input = {
        "start_date": start_date,
        "end_date": end_date,
        "workcenter_groups": sorted(workcenter_groups or []),
        "families": sorted(families or []),
        "resource_ids": sorted(resource_ids or []),
        "is_production": is_production,
        "is_key": is_key,
        "is_monitor": is_monitor,
    }
    query_id = _make_query_id(query_id_input)

    _spool_available = _has_cached_df(query_id)

    if _spool_available:
        logger.info("Resource dataset cache hit for query_id=%s", query_id)
    else:
        logger.info(
            "Resource dataset cache miss for query_id=%s, querying Oracle", query_id
        )

        resources, _, historyid_filter = _get_filtered_resources_and_lookup(
            workcenter_groups=workcenter_groups,
            families=families,
            resource_ids=resource_ids,
            is_production=is_production,
            is_key=is_key,
            is_monitor=is_monitor,
        )

        if not resources:
            return {
                "query_id": query_id,
                "summary": _empty_summary(),
                "detail": _empty_detail(),
            }

        from mes_dashboard.services.batch_query_engine import (
            decompose_by_time_range,
            execute_plan,
            merge_chunks_to_spool,
            compute_query_hash,
            should_decompose_by_time,
        )

        base_sql = _load_sql("base_facts")
        base_sql = base_sql.replace("{{ HISTORYID_FILTER }}", historyid_filter)

        if should_decompose_by_time(start_date, end_date):
            # --- Engine path for long date ranges → stream to Parquet spool ---
            engine_chunks = decompose_by_time_range(start_date, end_date)
            engine_hash = compute_query_hash(query_id_input)

            def _run_resource_chunk(chunk, max_rows_per_chunk=None):
                params = {
                    "start_date": chunk["chunk_start"],
                    "end_date": chunk["chunk_end"],
                }
                result = read_sql_df(
                    base_sql,
                    params,
                    caller="resource_dataset_cache:execute_primary_query_chunk",
                )
                return result if result is not None else pd.DataFrame()

            logger.info(
                "Engine activated for resource: %d chunks (query_id=%s)",
                len(engine_chunks), query_id,
            )
            execute_plan(
                engine_chunks, _run_resource_chunk,
                query_hash=engine_hash,
                cache_prefix="resource",
                chunk_ttl=_CACHE_TTL,
            )
            spool_tmp_path, spool_row_count = merge_chunks_to_spool(
                "resource",
                engine_hash,
                spool_dir=QUERY_SPOOL_DIR,
            )
            if spool_tmp_path is not None:
                register_spool_file(
                    _REDIS_NAMESPACE,
                    query_id,
                    spool_tmp_path,
                    spool_row_count,
                    ttl_seconds=_CACHE_TTL,
                )
                _dataset_cache.set(query_id, True)  # L1 marker
                _spool_available = True
        else:
            # --- Direct path (short query) ---
            params = {"start_date": start_date, "end_date": end_date}
            df = read_sql_df(
                base_sql,
                params,
                caller="resource_dataset_cache:execute_primary_query_direct",
            )
            if df is None:
                df = pd.DataFrame()
            if not df.empty:
                _store_df(query_id, df)
                _spool_available = True

    result = apply_view(query_id=query_id, granularity=granularity)
    if result is None:
        if _spool_available:
            raise RuntimeError(
                f"bootstrap render failure: apply_view returned None for query_id={query_id}"
            )
        return {
            "query_id": query_id,
            "summary": _empty_summary(),
            "detail": _empty_detail(),
        }
    return {"query_id": query_id, **result}


# ============================================================
# View (supplementary — cache only)
# ============================================================


def apply_view(
    *,
    query_id: str,
    granularity: str = "day",
) -> Optional[Dict[str, Any]]:
    """Read cache -> derive views. Returns None if expired (→ route returns 410).

    DuckDB SQL runtime is the sole compute path. Spool miss or runtime error
    returns None (cache_expired).
    """
    try:
        from mes_dashboard.services.resource_history_sql_runtime import (
            try_compute_view_from_spool,
        )
        sql_result, sql_meta = try_compute_view_from_spool(
            query_id=query_id,
            granularity=granularity,
        )
        if sql_result is not None:
            return {**sql_result, "_meta": sql_meta}
        fallback_reason = sql_meta.get("view_sql_fallback_reason", "unknown")
        logger.debug(
            "resource apply_view: SQL runtime no result (reason=%s query_id=%s)",
            fallback_reason, query_id,
        )
    except Exception as exc:
        logger.warning("resource apply_view: SQL runtime error: %s", exc)
    return None


def _empty_summary() -> Dict[str, Any]:
    return {
        "kpi": _empty_kpi(),
        "trend": [],
        "heatmap": [],
        "workcenter_comparison": [],
    }


def _empty_detail() -> Dict[str, Any]:
    return {"data": [], "total": 0, "truncated": False, "max_records": None}


def _empty_kpi() -> Dict[str, Any]:
    return {
        "ou_pct": 0,
        "availability_pct": 0,
        "prd_hours": 0,
        "prd_pct": 0,
        "sby_hours": 0,
        "sby_pct": 0,
        "udt_hours": 0,
        "udt_pct": 0,
        "sdt_hours": 0,
        "sdt_pct": 0,
        "egt_hours": 0,
        "egt_pct": 0,
        "nst_hours": 0,
        "nst_pct": 0,
        "machine_count": 0,
    }



# ---------------------------------------------------------------------------
# Canonical base dataset identity (task 2.2)
# ---------------------------------------------------------------------------
# resource-history canonical base dataset: date-range only, no filter params.
# Filters (workcenter / family / resource / flags) are applied at DuckDB /
# view-time, not baked into the spool key.  The route contract remains
# unchanged — POST /api/resource/history/query still accepts the same params.
#
# This function is the stable key used for warmup and spool reuse.
# Full spool pipeline migration is completed in task 7.2.
_CANONICAL_BASE_SCHEMA_VERSION = 1


def make_canonical_base_query_id(start_date: str, end_date: str, granularity: str = "day") -> str:
    """Return the canonical spool key for the resource base dataset.

    Uses only the date range and granularity — filter dimensions are resolved
    at view time by the DuckDB / SQL runtime, not baked into the spool key.
    """
    return _make_query_id({
        "canonical_schema_version": _CANONICAL_BASE_SCHEMA_VERSION,
        "start_date": start_date,
        "end_date": end_date,
        "granularity": granularity,
    })


def ensure_dataset_loaded() -> Dict[str, Any]:
    """Ensure the canonical resource base dataset exists in cache.

    Called by the warmup scheduler (task 3.3) after canonical base dataset
    design is complete.  Uses the last 90 days as the default warmup window.
    """
    end_dt = date.today()
    start_dt = end_dt - timedelta(days=89)
    start_date = start_dt.strftime("%Y-%m-%d")
    end_date = end_dt.strftime("%Y-%m-%d")

    base_query_id = make_canonical_base_query_id(start_date, end_date)
    if _has_cached_df(base_query_id):
        return {"query_id": base_query_id, "cache_hit": True, "start_date": start_date, "end_date": end_date}

    # Full base dataset: no filter restrictions, all resources
    result = execute_primary_query(start_date=start_date, end_date=end_date)
    return {
        "query_id": result.get("query_id", base_query_id),
        "cache_hit": False,
        "start_date": start_date,
        "end_date": end_date,
    }
