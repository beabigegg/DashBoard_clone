# -*- coding: utf-8 -*-
"""Service layer for Production History query APIs.

Two-layer query architecture:
  1. Primary: Oracle chunked query → Parquet spool (via batch_query_engine)
  2. View:    DuckDB over Parquet spool for page / matrix / export

Entry points:
  - query_production_history(...)  -> {dataset_id, detail, matrix, meta}
  - compute_detail_page(...)       -> {rows, pagination}
  - compute_matrix_view(...)       -> {tree, month_columns}
  - stream_export(...)             -> generator of CSV rows
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import pandas as pd

from mes_dashboard.core.database import read_sql_df_slow
from mes_dashboard.core.feature_flags import resolve_bool_flag
from mes_dashboard.core.global_concurrency import (
    acquire_heavy_query_slot,
    release_heavy_query_slot,
)
from mes_dashboard.core.query_spool_store import (
    QUERY_SPOOL_DIR,
    QUERY_SPOOL_TTL_SECONDS,
    get_spool_file_path,
    get_spool_metadata,
    register_spool_file,
)
from mes_dashboard.services.batch_query_engine import (
    compute_query_hash,
    decompose_by_time_range,
    execute_plan,
    merge_chunks_to_spool,
)
from mes_dashboard.sql import QueryBuilder, SQLLoader

logger = logging.getLogger("mes_dashboard.production_history_service")

# ── Feature flags ─────────────────────────────────────────────────────────────

_SQL_VIEW_ENABLED = resolve_bool_flag("PROD_HISTORY_SQL_VIEW_ENABLED", default=True)
_ASYNC_ENABLED = resolve_bool_flag("PROD_HISTORY_ASYNC_ENABLED", default=False)  # Phase 2 placeholder

# ── Configuration ─────────────────────────────────────────────────────────────

MAX_DATE_RANGE_DAYS = max(1, int(os.getenv("PROD_HISTORY_MAX_DATE_RANGE_DAYS", "730")))
ENGINE_GRAIN_DAYS = max(1, int(os.getenv("PROD_HISTORY_ENGINE_GRAIN_DAYS", "31")))
MAX_ROWS_PER_CHUNK = max(1, int(os.getenv("PROD_HISTORY_MAX_ROWS_PER_CHUNK", "50000")))
MAX_PARENT_TRACE_DEPTH = max(1, int(os.getenv("PROD_HISTORY_MAX_TRACE_DEPTH", "8")))
DEFAULT_PAGE_SIZE = 25
_SPOOL_NAMESPACE = "production_history"
_CACHE_PREFIX = "prod_hist"


# ── Date helpers ──────────────────────────────────────────────────────────────

def _parse_date(value: str) -> date:
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").date()
    except (ValueError, AttributeError):
        raise ValueError(f"日期格式錯誤（需 YYYY-MM-DD）: {value!r}")


def _end_date_exclusive(end_date: date) -> str:
    """Return end_date + 1 day as YYYY-MM-DD (exclusive upper bound)."""
    return (end_date + timedelta(days=1)).strftime("%Y-%m-%d")


# ── Input validation ──────────────────────────────────────────────────────────

def validate_query_params(params: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and normalize incoming query parameters.

    Raises:
        ValueError: on any validation failure (caller should return 400).
    """
    pj_types: List[str] = [str(t).strip() for t in (params.get("pj_types") or []) if str(t).strip()]
    if not pj_types:
        raise ValueError("必要參數: pj_types（至少一個）")

    start_raw = str(params.get("start_date") or "").strip()
    end_raw = str(params.get("end_date") or "").strip()
    if not start_raw or not end_raw:
        raise ValueError("必要參數: start_date, end_date")

    start_dt = _parse_date(start_raw)
    end_dt = _parse_date(end_raw)

    if start_dt > end_dt:
        raise ValueError("start_date 不可晚於 end_date")

    span = (end_dt - start_dt).days + 1
    if span > MAX_DATE_RANGE_DAYS:
        raise ValueError(
            f"日期區間超過上限 {MAX_DATE_RANGE_DAYS} 天（實際 {span} 天）"
        )

    # Optional filters — lists of strings
    def _str_list(key: str) -> List[str]:
        raw = params.get(key) or []
        if isinstance(raw, str):
            raw = [raw]
        return [str(v).strip() for v in raw if str(v).strip()]

    lot_ids = _str_list("lot_ids")
    work_orders = _str_list("work_orders")
    packages = _str_list("packages")
    bop_codes = _str_list("bop_codes")
    workcenter_groups = _str_list("workcenter_groups")
    workcenter_names = _str_list("workcenter_names")
    equipment_ids = _str_list("equipment_ids")

    return {
        "pj_types": pj_types,
        "start_date": start_dt.strftime("%Y-%m-%d"),
        "end_date": end_dt.strftime("%Y-%m-%d"),
        "end_date_exclusive": _end_date_exclusive(end_dt),
        "lot_ids": lot_ids,
        "work_orders": work_orders,
        "packages": packages,
        "bop_codes": bop_codes,
        "workcenter_groups": workcenter_groups,
        "workcenter_names": workcenter_names,
        "equipment_ids": equipment_ids,
    }


# ── SQL builder ───────────────────────────────────────────────────────────────

def _build_extra_filters(params: Dict[str, Any]) -> tuple[str, Dict[str, Any]]:
    """Build EXTRA_FILTERS SQL fragment + bind params from validated params.

    Returns:
        (extra_sql, bind_params) — extra_sql is prefixed with AND if non-empty.
    """
    qb = QueryBuilder()

    pj_types = params.get("pj_types") or []
    if pj_types:
        qb.add_in_condition("c.PJ_TYPE", pj_types)

    lot_ids = params.get("lot_ids") or []
    if lot_ids:
        qb.add_in_condition("c.CONTAINERNAME", lot_ids)

    work_orders = params.get("work_orders") or []
    if work_orders:
        qb.add_in_condition("c.MFGORDERNAME", work_orders)

    packages = params.get("packages") or []
    if packages:
        qb.add_in_condition("c.PRODUCTLINENAME", packages)

    bop_codes = params.get("bop_codes") or []
    if bop_codes:
        qb.add_in_condition("c.PJ_BOP", bop_codes)

    # Workcenter names take priority over groups
    wc_names = params.get("workcenter_names") or []
    wc_groups = params.get("workcenter_groups") or []
    if wc_names:
        qb.add_in_condition("h.WORKCENTERNAME", wc_names)
    elif wc_groups:
        # Resolve groups to workcenter names if possible
        try:
            from mes_dashboard.config.workcenter_groups import get_workcenter_group
            wcs = []
            for grp in wc_groups:
                members = get_workcenter_group(grp)
                wcs.extend(members or [])
            if wcs:
                qb.add_in_condition("h.WORKCENTERNAME", list(set(wcs)))
        except Exception:
            pass

    equipment_ids = params.get("equipment_ids") or []
    if equipment_ids:
        qb.add_in_condition("h.EQUIPMENTNAME", equipment_ids)

    conditions_sql = qb.get_conditions_sql()
    extra_sql = f"AND {conditions_sql}" if conditions_sql else ""
    return extra_sql, qb.params


# ── Oracle chunk query function ───────────────────────────────────────────────

def _make_chunk_query_fn(params: Dict[str, Any]):
    """Return a chunk query function closure over the given filter params."""
    extra_sql, extra_params = _build_extra_filters(params)
    base_sql = SQLLoader.load("production_history/main_query")
    sql = base_sql.replace("{{ EXTRA_FILTERS }}", extra_sql)

    def _run_history_chunk(
        chunk: Dict[str, str],
        max_rows_per_chunk: Optional[int] = None,
    ) -> pd.DataFrame:
        bind_params: Dict[str, Any] = {
            "chunk_start": chunk["chunk_start"],
            "chunk_end_excl": params["end_date_exclusive"]
            if chunk["chunk_end"] == params["end_date"]
            else _end_date_exclusive(_parse_date(chunk["chunk_end"])),
        }
        bind_params.update(extra_params)

        df = read_sql_df_slow(
            sql,
            params=bind_params,
            caller="production_history.chunk",
        )

        if max_rows_per_chunk and len(df) > max_rows_per_chunk:
            logger.warning(
                "production_history chunk row limit hit: %d > %d (chunk=%s–%s)",
                len(df),
                max_rows_per_chunk,
                chunk["chunk_start"],
                chunk["chunk_end"],
            )
            df = df.head(max_rows_per_chunk)

        return df

    return _run_history_chunk


# ── LOT split-chain trace ─────────────────────────────────────────────────────

def _resolve_lot_ids_with_trace(
    lot_ids: List[str],
) -> List[str]:
    """Trace parent LOTs along split chain for each input lot ID.

    Adds ancestor CONTAINERNAME values that are not already in lot_ids.
    Bounded by MAX_PARENT_TRACE_DEPTH and cycle-safe via visited set.

    Returns:
        Deduplicated list of lot IDs including traced parents.

    Raises:
        ValueError: if trace depth is exceeded or cycle detected.
    """
    if not lot_ids:
        return lot_ids

    try:
        from mes_dashboard.services.lineage_engine import LineageEngine
    except ImportError:
        logger.warning("LineageEngine not available; skipping LOT parent trace")
        return lot_ids

    all_names: set[str] = set(lot_ids)
    # Resolve input names → CIDs
    name_to_cid = _resolve_container_ids_by_names(lot_ids)
    if not name_to_cid:
        return lot_ids

    pending_cids: set[str] = set(name_to_cid.values())
    visited_cids: set[str] = set(pending_cids)
    cid_to_name: Dict[str, str] = {v: k for k, v in name_to_cid.items()}

    for depth in range(MAX_PARENT_TRACE_DEPTH):
        if not pending_cids:
            break

        split_result = LineageEngine.resolve_split_ancestors(list(pending_cids))
        child_to_parent: Dict[str, str] = split_result.get("child_to_parent", {})
        cid_to_name.update(split_result.get("cid_to_name", {}))

        if not child_to_parent:
            break

        next_pending: set[str] = set()
        for cid in list(pending_cids):
            parent_cid = child_to_parent.get(cid)
            if not parent_cid or parent_cid == cid:
                continue
            if parent_cid in visited_cids:
                raise ValueError(
                    f"LOT split chain 偵測到循環（depth={depth}，cid={cid}）"
                )
            if depth + 1 >= MAX_PARENT_TRACE_DEPTH:
                raise ValueError(
                    f"LOT split chain 超過追溯深度上限 {MAX_PARENT_TRACE_DEPTH}"
                )
            visited_cids.add(parent_cid)
            next_pending.add(parent_cid)
            parent_name = cid_to_name.get(parent_cid)
            if parent_name:
                all_names.add(parent_name)

        pending_cids = next_pending

    return list(all_names)


def _resolve_container_ids_by_names(names: List[str]) -> Dict[str, str]:
    """Resolve CONTAINERNAME list → {CONTAINERNAME: CONTAINERID} map."""
    from mes_dashboard.core.database import read_sql_df
    from mes_dashboard.sql import QueryBuilder, SQLLoader

    if not names:
        return {}

    qb = QueryBuilder()
    qb.add_in_condition("CONTAINERNAME", [n.upper() for n in names])
    conditions = qb.get_conditions_sql()

    sql = f"SELECT CONTAINERNAME, CONTAINERID FROM DWH.DW_MES_CONTAINER WHERE {conditions}"
    try:
        df = read_sql_df(sql, params=qb.params)
        if df is None or df.empty:
            return {}
        return {
            str(r["CONTAINERNAME"]).strip(): str(r["CONTAINERID"]).strip()
            for _, r in df.iterrows()
            if r.get("CONTAINERNAME") and r.get("CONTAINERID")
        }
    except Exception as exc:
        logger.warning("_resolve_container_ids_by_names failed: %s", exc)
        return {}


# ── Type options (from DWH history) ───────────────────────────────────────────

_TYPE_OPTIONS_CACHE_KEY = "production_history:type_options"
_TYPE_OPTIONS_TTL = 86400  # 24 hours


def get_type_options() -> List[str]:
    """Return DISTINCT PJ_TYPE values from container_filter_cache.

    Delegates to container_filter_cache.get_pj_types() which is loaded at
    startup and refreshed every 24 hours. No Oracle query is executed here.
    """
    from mes_dashboard.services.container_filter_cache import get_pj_types
    return get_pj_types()


# ── Primary query entry point ─────────────────────────────────────────────────

def query_production_history(raw_params: Dict[str, Any]) -> Dict[str, Any]:
    """Execute the full primary query: Oracle → spool → first-page + matrix.

    Flow:
      1. Validate params
      2. Optionally resolve LOT IDs with split-chain trace
      3. acquire_heavy_query_slot
      4. decompose_by_time_range → execute_plan (each chunk via _run_history_chunk)
      5. merge_chunks_to_spool → register_spool_file
      6. DuckDB first-page result + matrix summary
      7. release_heavy_query_slot

    Returns:
        {dataset_id, detail: {rows, pagination}, matrix: {tree, month_columns},
         filter_options, meta: {ttl_seconds, expires_at, ...}}

    Raises:
        ValueError: on validation failure (→ 400)
        MemoryError: on memory guard rejection (→ 503)
        RuntimeError: on heavy-query slot rejection (→ 503)
    """
    from mes_dashboard.services.production_history_sql_runtime import (
        compute_detail_page,
        compute_matrix_view,
    )

    params = validate_query_params(raw_params)

    # Optional: expand LOT IDs via split-chain trace
    if params["lot_ids"]:
        params["lot_ids"] = _resolve_lot_ids_with_trace(params["lot_ids"])

    dataset_id = _make_dataset_id(params)
    slot_owner = f"prod_hist:{dataset_id}"

    # ── Heavy-query slot acquisition ──────────────────────────────────────────
    acquired = acquire_heavy_query_slot(slot_owner)
    if not acquired:
        raise RuntimeError("heavy_query_overloaded")

    t_start = time.monotonic()
    try:
        _run_oracle_to_spool(params, dataset_id)
    finally:
        release_heavy_query_slot(slot_owner)

    elapsed = time.monotonic() - t_start
    try:
        from mes_dashboard.core.metrics import record_query_latency
        record_query_latency(elapsed)
    except Exception:
        pass

    # ── DuckDB view computation ───────────────────────────────────────────────
    spool_path = get_spool_file_path(_SPOOL_NAMESPACE, dataset_id)
    if spool_path is None:
        raise ValueError("查詢無結果，請確認篩選條件後重試")

    meta = get_spool_metadata(_SPOOL_NAMESPACE, dataset_id) or {}
    ttl_seconds = int(meta.get("expires_at", 0)) - int(time.time())
    ttl_seconds = max(ttl_seconds, 0)

    detail = compute_detail_page(spool_path, filter_params={}, page=1, per_page=DEFAULT_PAGE_SIZE)
    matrix = compute_matrix_view(spool_path, filter_params={})

    return {
        "dataset_id": dataset_id,
        "detail": detail,
        "matrix": matrix,
        "filter_options": {
            "pj_types": params["pj_types"],
        },
        "meta": {
            "ttl_seconds": ttl_seconds,
            "expires_at": int(meta.get("expires_at", 0)),
            "row_count": int(meta.get("row_count", 0)),
            "query_seconds": round(elapsed, 2),
        },
    }


def _make_dataset_id(params: Dict[str, Any]) -> str:
    """Compute stable dataset_id from query params (hash-based)."""
    hash_key = {
        "pj_types": sorted(params["pj_types"]),
        "start_date": params["start_date"],
        "end_date": params["end_date"],
        "lot_ids": sorted(params["lot_ids"]),
        "work_orders": sorted(params["work_orders"]),
        "packages": sorted(params["packages"]),
        "bop_codes": sorted(params["bop_codes"]),
        "workcenter_groups": sorted(params["workcenter_groups"]),
        "workcenter_names": sorted(params["workcenter_names"]),
        "equipment_ids": sorted(params["equipment_ids"]),
    }
    return f"ph-{compute_query_hash(hash_key)}"


def _run_oracle_to_spool(params: Dict[str, Any], dataset_id: str) -> None:
    """Execute Oracle chunked query and write results to Parquet spool."""
    chunks = decompose_by_time_range(
        params["start_date"],
        params["end_date"],
        grain_days=ENGINE_GRAIN_DAYS,
    )

    query_fn = _make_chunk_query_fn(params)
    query_hash = compute_query_hash({
        "dataset_id": dataset_id,
        "chunks": [c["chunk_start"] for c in chunks],
    })

    execute_plan(
        chunks,
        query_fn,
        parallel=1,
        query_hash=query_hash,
        cache_prefix=_CACHE_PREFIX,
        max_rows_per_chunk=MAX_ROWS_PER_CHUNK,
    )

    spool_dir = QUERY_SPOOL_DIR / _SPOOL_NAMESPACE
    tmp_path, total_rows = merge_chunks_to_spool(
        _CACHE_PREFIX,
        query_hash,
        spool_dir=spool_dir,
        max_total_rows=None,
        overflow_mode="truncate",
    )

    if tmp_path is not None and total_rows > 0:
        register_spool_file(
            _SPOOL_NAMESPACE,
            dataset_id,
            src_path=tmp_path,
            row_count=total_rows,
            ttl_seconds=QUERY_SPOOL_TTL_SECONDS,
        )


# ---------------------------------------------------------------------------
# Canonical spool identity (task 2.3)
# ---------------------------------------------------------------------------
# production-history is on-demand only; it is NOT enrolled in the warmup
# scheduler.  The canonical spool identity includes pj_types + date range +
# all user-supplied filters so that any repeat query with the same params can
# reuse the spool without re-querying Oracle.
#
# Do NOT add production-history to spool_warmup_scheduler._WARMUP_JOBS.


def make_canonical_spool_id(params: Dict[str, Any]) -> str:
    """Return the canonical on-demand spool id for a production-history query.

    Delegates to the internal ``_make_dataset_id`` which already includes
    pj_types, date range, and all user-supplied filter params.

    This function is the stable public entry point for external callers
    (routes, tests) that need to look up or reuse an existing spool.
    """
    return _make_dataset_id(params)
