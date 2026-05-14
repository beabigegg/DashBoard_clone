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
import os
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
_HISTORICAL_TTL = int(os.getenv("RESOURCE_HISTORY_HISTORICAL_TTL", "86400"))
_CACHE_MAX_SIZE = 1
_RESOURCE_ENGINE_PARALLEL = max(1, int(os.getenv("RESOURCE_ENGINE_PARALLEL", "1")))
_REDIS_NAMESPACE = "resource_dataset"
_OEE_REDIS_NAMESPACE = "resource_oee"

_dataset_cache = ProcessLevelCache(ttl_seconds=_CACHE_TTL, max_size=_CACHE_MAX_SIZE)


def _get_cache_ttl(end_date: str) -> int:
    """Return 24h TTL for immutable historical queries (end_date < today-2d), 2h otherwise."""
    try:
        if date.fromisoformat(end_date) < date.today() - timedelta(days=2):
            return _HISTORICAL_TTL
    except (ValueError, TypeError):
        pass
    return _CACHE_TTL
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


def _store_df(query_id: str, df: pd.DataFrame, end_date: str = "") -> None:
    """Write to spool; L1 gets lightweight marker."""
    _dataset_cache.set(query_id, True)  # lightweight marker
    store_spooled_df(_REDIS_NAMESPACE, query_id, df, ttl_seconds=_get_cache_ttl(end_date))


def _has_cached_oee_df(query_id: str) -> bool:
    """Check if OEE spool exists for query_id."""
    return get_spool_file_path(_OEE_REDIS_NAMESPACE, query_id) is not None


def _store_oee_df(query_id: str, df: pd.DataFrame, end_date: str = "") -> None:
    """Write OEE data to separate spool."""
    store_spooled_df(_OEE_REDIS_NAMESPACE, query_id, df, ttl_seconds=_get_cache_ttl(end_date))


# ============================================================
# Resource cache integration (reuse existing service)
# ============================================================


def _get_resource_lookup() -> Dict[str, Dict[str, Any]]:
    """Thin wrapper: returns full resource lookup dict {historyid: info}.

    Delegates to resource_history_service to keep the canonical logic in one place.
    Imported by resource_history_sql_runtime and resource_history_routes.
    """
    from mes_dashboard.services.resource_history_service import (
        _get_filtered_resources,
        _build_resource_lookup,
    )
    resources = _get_filtered_resources()
    return _build_resource_lookup(resources)


def _get_workcenter_mapping() -> Optional[Dict[str, Dict[str, Any]]]:
    """Thin wrapper: returns workcenter mapping {workcentername: {group, sequence}}.

    Re-exports filter_cache.get_workcenter_mapping() so consumers can import
    from a single module.
    """
    from mes_dashboard.services.filter_cache import get_workcenter_mapping
    return get_workcenter_mapping()


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
    _oee_spool_available = _has_cached_oee_df(query_id)
    _partial_failure_meta: Dict[str, Any] = {}

    if _spool_available and _oee_spool_available:
        logger.info("Resource dataset cache hit for query_id=%s (base+oee)", query_id)
    else:
        logger.info(
            "Resource dataset cache miss for query_id=%s (base=%s oee=%s), querying Oracle",
            query_id, _spool_available, _oee_spool_available,
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

        # Try DuckDB cache for recent queries (end_date in [today-90d, yesterday])
        if not (_spool_available and _oee_spool_available):
            from mes_dashboard.services.resource_history_duckdb_cache import (
                should_use_duckdb,
                query_base_from_duckdb,
                query_oee_from_duckdb,
            )
            if should_use_duckdb(end_date, start_date):
                hist_ids = [r["RESOURCEID"] for r in resources if r.get("RESOURCEID")]
                if not _spool_available:
                    _base_from_duckdb = query_base_from_duckdb(hist_ids, start_date, end_date)
                    if not _base_from_duckdb.empty:
                        _store_df(query_id, _base_from_duckdb, end_date)
                        _spool_available = True
                if not _oee_spool_available:
                    _oee_from_duckdb = query_oee_from_duckdb(start_date, end_date)
                    if not _oee_from_duckdb.empty:
                        _store_oee_df(query_id, _oee_from_duckdb, end_date)
                        _oee_spool_available = True
                if _spool_available and _oee_spool_available:
                    logger.info(
                        "Resource dataset DuckDB cache served query_id=%s", query_id
                    )

        if not (_spool_available and _oee_spool_available):
            # --- Oracle query path (DuckDB miss or outside cache window) ---
            from mes_dashboard.services.batch_query_engine import (
                decompose_by_time_range,
                execute_plan,
                get_batch_progress,
                merge_chunks_to_spool,
                compute_query_hash,
                should_decompose_by_time,
            )
            from concurrent.futures import ThreadPoolExecutor

            base_sql = _load_sql("base_facts")
            base_sql = base_sql.replace("{{ HISTORYID_FILTER }}", historyid_filter)

            oee_sql = _load_sql("oee_facts")

            # Compute reject date window (±30 days)
            _reject_start = (
                date.fromisoformat(start_date) - timedelta(days=30)
            ).isoformat()
            _reject_end = (
                date.fromisoformat(end_date) + timedelta(days=30)
            ).isoformat()

            def _query_base_direct():
                params = {"start_date": start_date, "end_date": end_date}
                df = read_sql_df(
                    base_sql, params,
                    caller="resource_dataset_cache:execute_primary_query_direct",
                )
                return df if df is not None else pd.DataFrame()

            def _query_oee_direct():
                params = {
                    "start_date": start_date,
                    "end_date": end_date,
                    "reject_start": _reject_start,
                    "reject_end": _reject_end,
                }
                df = read_sql_df(
                    oee_sql, params,
                    caller="resource_dataset_cache:execute_primary_query_oee_direct",
                )
                return df if df is not None else pd.DataFrame()

            if should_decompose_by_time(start_date, end_date):
                # --- Engine path for long date ranges ---
                engine_chunks = decompose_by_time_range(start_date, end_date)
                engine_hash = compute_query_hash(query_id_input)

                def _run_base_chunk(chunk, max_rows_per_chunk=None):
                    params = {
                        "start_date": chunk["chunk_start"],
                        "end_date": chunk["chunk_end"],
                    }
                    result = read_sql_df(
                        base_sql, params,
                        caller="resource_dataset_cache:execute_primary_query_chunk",
                    )
                    return result if result is not None else pd.DataFrame()

                def _run_oee_chunk(chunk, max_rows_per_chunk=None):
                    chunk_reject_start = (
                        date.fromisoformat(chunk["chunk_start"]) - timedelta(days=30)
                    ).isoformat()
                    chunk_reject_end = (
                        date.fromisoformat(chunk["chunk_end"]) + timedelta(days=30)
                    ).isoformat()
                    params = {
                        "start_date": chunk["chunk_start"],
                        "end_date": chunk["chunk_end"],
                        "reject_start": chunk_reject_start,
                        "reject_end": chunk_reject_end,
                    }
                    result = read_sql_df(
                        oee_sql, params,
                        caller="resource_dataset_cache:execute_primary_query_oee_chunk",
                    )
                    return result if result is not None else pd.DataFrame()

                logger.info(
                    "Engine activated for resource: %d chunks (query_id=%s)",
                    len(engine_chunks), query_id,
                )

                if not _spool_available:
                    execute_plan(
                        engine_chunks, _run_base_chunk,
                        parallel=_RESOURCE_ENGINE_PARALLEL,
                        query_hash=engine_hash,
                        cache_prefix="resource",
                        chunk_ttl=_get_cache_ttl(end_date),
                    )
                    _base_progress = get_batch_progress("resource", engine_hash) or {}
                    if _base_progress.get("has_partial_failure") in (True, "True", "true", "1", 1):
                        _base_failed = {
                            "has_partial_failure": True,
                            "failed_chunk_count": _base_progress.get("failed_chunk_count"),
                            "failed_ranges": _base_progress.get("failed_ranges"),
                            "source": "base",
                        }
                        _partial_failure_meta.update(_base_failed)
                        logger.warning(
                            "resource base partial failure (query_id=%s): failed_ranges=%s",
                            query_id, _base_progress.get("failed_ranges"),
                        )
                    spool_tmp_path, spool_row_count = merge_chunks_to_spool(
                        "resource", engine_hash, spool_dir=QUERY_SPOOL_DIR,
                    )
                    if spool_tmp_path is not None:
                        register_spool_file(
                            _REDIS_NAMESPACE, query_id,
                            spool_tmp_path, spool_row_count,
                            ttl_seconds=_get_cache_ttl(end_date),
                        )
                        _dataset_cache.set(query_id, True)
                        _spool_available = True

                if not _oee_spool_available:
                    oee_engine_hash = compute_query_hash({**query_id_input, "_oee": True})
                    execute_plan(
                        engine_chunks, _run_oee_chunk,
                        parallel=_RESOURCE_ENGINE_PARALLEL,
                        query_hash=oee_engine_hash,
                        cache_prefix="resource_oee",
                        chunk_ttl=_get_cache_ttl(end_date),
                    )
                    _oee_progress = get_batch_progress("resource_oee", oee_engine_hash) or {}
                    if _oee_progress.get("has_partial_failure") in (True, "True", "true", "1", 1):
                        _oee_failed = {
                            "has_partial_failure": True,
                            "failed_chunk_count": _oee_progress.get("failed_chunk_count"),
                            "failed_ranges": _oee_progress.get("failed_ranges"),
                            "source": "oee",
                        }
                        _partial_failure_meta.update(_oee_failed)
                        logger.warning(
                            "resource OEE partial failure (query_id=%s): failed_ranges=%s",
                            query_id, _oee_progress.get("failed_ranges"),
                        )
                    oee_spool_tmp_path, oee_spool_row_count = merge_chunks_to_spool(
                        "resource_oee", oee_engine_hash, spool_dir=QUERY_SPOOL_DIR,
                    )
                    if oee_spool_tmp_path is not None:
                        register_spool_file(
                            _OEE_REDIS_NAMESPACE, query_id,
                            oee_spool_tmp_path, oee_spool_row_count,
                            ttl_seconds=_get_cache_ttl(end_date),
                        )
                        _oee_spool_available = True
            else:
                # --- Direct path (short query) — run base + OEE in parallel ---
                futures = {}
                with ThreadPoolExecutor(max_workers=2) as executor:
                    if not _spool_available:
                        futures["base"] = executor.submit(_query_base_direct)
                    if not _oee_spool_available:
                        futures["oee"] = executor.submit(_query_oee_direct)

                if "base" in futures:
                    df = futures["base"].result()
                    if not df.empty:
                        _store_df(query_id, df, end_date)
                        _spool_available = True

                if "oee" in futures:
                    oee_df = futures["oee"].result()
                    if not oee_df.empty:
                        _store_oee_df(query_id, oee_df, end_date)
                        _oee_spool_available = True

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
    if _partial_failure_meta:
        result.setdefault("_meta", {})["partial_failure"] = _partial_failure_meta
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
        "oee_pct": 0,
        "yield_pct": 0,
        "trackout_qty": 0,
        "ng_qty": 0,
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


def make_canonical_oee_query_id(start_date: str, end_date: str, granularity: str = "day") -> str:
    """Return the canonical spool key for the OEE dataset.

    Same key strategy as base dataset — date_range + granularity only.
    """
    return _make_query_id({
        "canonical_schema_version": _CANONICAL_BASE_SCHEMA_VERSION,
        "start_date": start_date,
        "end_date": end_date,
        "granularity": granularity,
        "_oee": True,
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
