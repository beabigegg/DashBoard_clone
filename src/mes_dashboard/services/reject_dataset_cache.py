# -*- coding: utf-8 -*-
"""Two-phase reject-history dataset cache.

Primary query (POST /query) → Oracle → cache full LOT-level DataFrame.
Supplementary view (GET /view) → read cache → pandas filter/derive.

Cache layers:
  L1: ProcessLevelCache (in-process, per-worker)
  L2: Redis (cross-worker, parquet bytes encoded as base64 string)
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import logging
from typing import Any, Dict, List, Optional

import pandas as pd

from mes_dashboard.core.cache import ProcessLevelCache, register_process_cache
from mes_dashboard.core.database import read_sql_df
from mes_dashboard.core.redis_client import (
    REDIS_ENABLED,
    get_key,
    get_redis_client,
)
from mes_dashboard.services.filter_cache import get_specs_for_groups
from mes_dashboard.services.reject_history_service import (
    _as_float,
    _as_int,
    _build_where_clause,
    _derive_summary,
    _extract_distinct_text_values,
    _extract_workcenter_group_options,
    _normalize_text,
    _prepare_sql,
    _to_date_str,
    _to_datetime_str,
    _validate_range,
)
from mes_dashboard.services.query_tool_service import (
    _resolve_by_lot_id,
    _resolve_by_wafer_lot,
    _resolve_by_work_order,
)
from mes_dashboard.sql import QueryBuilder

logger = logging.getLogger("mes_dashboard.reject_dataset_cache")

_CACHE_TTL = 900  # 15 minutes
_CACHE_MAX_SIZE = 8
_REDIS_NAMESPACE = "reject_dataset"

_dataset_cache = ProcessLevelCache(ttl_seconds=_CACHE_TTL, max_size=_CACHE_MAX_SIZE)
register_process_cache("reject_dataset", _dataset_cache, "Reject Dataset (L1, 15min)")


# ============================================================
# Query ID
# ============================================================


def _make_query_id(params: dict) -> str:
    """Deterministic hash from primary query params + policy toggles."""
    canonical = json.dumps(params, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


# ============================================================
# Redis L2 helpers (parquet ↔ base64 string)
# ============================================================


def _redis_key(query_id: str) -> str:
    return get_key(f"{_REDIS_NAMESPACE}:{query_id}")


def _redis_store_df(query_id: str, df: pd.DataFrame) -> None:
    if not REDIS_ENABLED:
        return
    client = get_redis_client()
    if client is None:
        return
    try:
        buf = io.BytesIO()
        df.to_parquet(buf, engine="pyarrow", index=False)
        encoded = base64.b64encode(buf.getvalue()).decode("ascii")
        client.setex(_redis_key(query_id), _CACHE_TTL, encoded)
    except Exception as exc:
        logger.warning("Failed to store DataFrame in Redis: %s", exc)


def _redis_load_df(query_id: str) -> Optional[pd.DataFrame]:
    if not REDIS_ENABLED:
        return None
    client = get_redis_client()
    if client is None:
        return None
    try:
        encoded = client.get(_redis_key(query_id))
        if encoded is None:
            return None
        raw = base64.b64decode(encoded)
        return pd.read_parquet(io.BytesIO(raw), engine="pyarrow")
    except Exception as exc:
        logger.warning("Failed to load DataFrame from Redis: %s", exc)
        return None


# ============================================================
# Cache read (L1 → L2 → None)
# ============================================================


def _get_cached_df(query_id: str) -> Optional[pd.DataFrame]:
    """Read cache: L1 hit → return, L1 miss → L2 → write L1 → return."""
    df = _dataset_cache.get(query_id)
    if df is not None:
        return df
    df = _redis_load_df(query_id)
    if df is not None:
        _dataset_cache.set(query_id, df)
    return df


def _store_df(query_id: str, df: pd.DataFrame) -> None:
    """Write to L1 and L2."""
    _dataset_cache.set(query_id, df)
    _redis_store_df(query_id, df)


# ============================================================
# Container resolution (reuse query_tool_service resolvers)
# ============================================================


_RESOLVERS = {
    "lot": _resolve_by_lot_id,
    "work_order": _resolve_by_work_order,
    "wafer_lot": _resolve_by_wafer_lot,
}


def resolve_containers(
    input_type: str, values: List[str]
) -> Dict[str, Any]:
    """Dispatch to existing resolver → return container IDs + resolution info."""
    resolver = _RESOLVERS.get(input_type)
    if resolver is None:
        raise ValueError(f"不支援的輸入類型: {input_type}")

    result = resolver(values)
    if "error" in result:
        raise ValueError(result["error"])

    container_ids = []
    for row in result.get("data", []):
        cid = row.get("container_id")
        if cid:
            container_ids.append(cid)

    return {
        "container_ids": container_ids,
        "resolution_info": {
            "input_count": result.get("input_count", len(values)),
            "resolved_count": len(container_ids),
            "not_found": result.get("not_found", []),
        },
    }


# ============================================================
# Primary query
# ============================================================


def execute_primary_query(
    *,
    mode: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    container_input_type: Optional[str] = None,
    container_values: Optional[List[str]] = None,
    include_excluded_scrap: bool = False,
    exclude_material_scrap: bool = True,
    exclude_pb_diode: bool = True,
) -> Dict[str, Any]:
    """Execute Oracle query → cache DataFrame → return structured result."""

    # ---- Build base_where + params for the primary filter ----
    base_where_parts: List[str] = []
    base_params: Dict[str, Any] = {}
    resolution_info: Optional[Dict[str, Any]] = None

    if mode == "date_range":
        if not start_date or not end_date:
            raise ValueError("date_range mode 需要 start_date 和 end_date")
        _validate_range(start_date, end_date)
        base_where_parts.append(
            "r.TXNDATE >= TO_DATE(:start_date, 'YYYY-MM-DD')"
            " AND r.TXNDATE < TO_DATE(:end_date, 'YYYY-MM-DD') + 1"
        )
        base_params["start_date"] = start_date
        base_params["end_date"] = end_date

    elif mode == "container":
        if not container_values:
            raise ValueError("container mode 需要至少一個容器值")
        resolved = resolve_containers(
            container_input_type or "lot", container_values
        )
        resolution_info = resolved["resolution_info"]
        container_ids = resolved["container_ids"]
        if not container_ids:
            raise ValueError("未找到任何對應的容器")

        builder = QueryBuilder()
        builder.add_in_condition("r.CONTAINERID", container_ids)
        cid_where, cid_params = builder.build_where_only()
        # build_where_only returns "WHERE ..." — strip "WHERE " prefix
        cid_condition = cid_where.strip()
        if cid_condition.upper().startswith("WHERE "):
            cid_condition = cid_condition[6:].strip()
        base_where_parts.append(cid_condition)
        base_params.update(cid_params)

    else:
        raise ValueError(f"不支援的查詢模式: {mode}")

    base_where = " AND ".join(base_where_parts)

    # ---- Build policy WHERE (only toggles, no supplementary filters) ----
    policy_where, policy_params, meta = _build_where_clause(
        include_excluded_scrap=include_excluded_scrap,
        exclude_material_scrap=exclude_material_scrap,
        exclude_pb_diode=exclude_pb_diode,
    )

    # ---- Compute query_id from all primary params ----
    query_id_input = {
        "mode": mode,
        "start_date": start_date,
        "end_date": end_date,
        "container_input_type": container_input_type,
        "container_values": sorted(container_values or []),
        "include_excluded_scrap": include_excluded_scrap,
        "exclude_material_scrap": exclude_material_scrap,
        "exclude_pb_diode": exclude_pb_diode,
    }
    query_id = _make_query_id(query_id_input)

    # ---- Check cache first ----
    cached_df = _get_cached_df(query_id)
    if cached_df is not None:
        logger.info("Dataset cache hit for query_id=%s", query_id)
        return _build_primary_response(
            query_id, cached_df, meta, resolution_info
        )

    # ---- Execute Oracle query ----
    logger.info("Dataset cache miss for query_id=%s, querying Oracle", query_id)
    sql = _prepare_sql(
        "list",
        where_clause=policy_where,
        base_variant="lot",
        base_where=base_where,
    )
    all_params = {**base_params, **policy_params, "offset": 0, "limit": 999999999}
    df = read_sql_df(sql, all_params)
    if df is None:
        df = pd.DataFrame()

    # ---- Cache and return ----
    if not df.empty:
        _store_df(query_id, df)

    return _build_primary_response(query_id, df, meta, resolution_info)


def _build_primary_response(
    query_id: str,
    df: pd.DataFrame,
    meta: Dict[str, Any],
    resolution_info: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Build the full response from a LOT-level DataFrame."""
    analytics_raw = _derive_analytics_raw(df)
    summary = _derive_summary_from_analytics(analytics_raw)
    trend_items = _derive_trend_from_analytics(analytics_raw)
    first_page = _paginate_detail(df, page=1, per_page=50)
    available = _extract_available_filters(df)

    result: Dict[str, Any] = {
        "query_id": query_id,
        "analytics_raw": analytics_raw,
        "summary": summary,
        "trend": {"items": trend_items, "granularity": "day"},
        "detail": first_page,
        "available_filters": available,
        "meta": meta,
    }
    if resolution_info is not None:
        result["resolution_info"] = resolution_info
    return result


# ============================================================
# View (supplementary + interactive filtering on cache)
# ============================================================


def apply_view(
    *,
    query_id: str,
    packages: Optional[List[str]] = None,
    workcenter_groups: Optional[List[str]] = None,
    reason: Optional[str] = None,
    metric_filter: str = "all",
    trend_dates: Optional[List[str]] = None,
    detail_reason: Optional[str] = None,
    page: int = 1,
    per_page: int = 50,
) -> Optional[Dict[str, Any]]:
    """Read cache → apply filters → return derived data. Returns None if expired."""
    df = _get_cached_df(query_id)
    if df is None:
        return None

    filtered = _apply_supplementary_filters(
        df,
        packages=packages,
        workcenter_groups=workcenter_groups,
        reason=reason,
        metric_filter=metric_filter,
    )

    # Analytics always uses full date range (supplementary-filtered only).
    # The frontend derives trend from analytics_raw and filters Pareto by
    # selectedTrendDates client-side.
    analytics_raw = _derive_analytics_raw(filtered)
    summary = _derive_summary_from_analytics(analytics_raw)

    # Detail list: additionally filter by detail_reason and trend_dates
    detail_df = filtered
    if trend_dates:
        date_set = set(trend_dates)
        detail_df = detail_df[
            detail_df["TXN_DAY"].apply(lambda d: _to_date_str(d) in date_set)
        ]
    if detail_reason:
        detail_df = detail_df[
            detail_df["LOSSREASONNAME"].str.strip() == detail_reason.strip()
        ]

    detail_page = _paginate_detail(detail_df, page=page, per_page=per_page)

    return {
        "analytics_raw": analytics_raw,
        "summary": summary,
        "detail": detail_page,
    }


def _apply_supplementary_filters(
    df: pd.DataFrame,
    *,
    packages: Optional[List[str]] = None,
    workcenter_groups: Optional[List[str]] = None,
    reason: Optional[str] = None,
    metric_filter: str = "all",
) -> pd.DataFrame:
    """Apply supplementary filters via pandas boolean indexing."""
    if df is None or df.empty:
        return df

    mask = pd.Series(True, index=df.index)

    if packages:
        pkg_set = {p.strip() for p in packages if p.strip()}
        if pkg_set and "PRODUCTLINENAME" in df.columns:
            mask &= df["PRODUCTLINENAME"].isin(pkg_set)

    if workcenter_groups:
        wc_groups = [g.strip() for g in workcenter_groups if g.strip()]
        if wc_groups:
            specs = get_specs_for_groups(wc_groups)
            if specs and "SPECNAME" in df.columns:
                spec_set = {s.upper() for s in specs}
                mask &= df["SPECNAME"].str.strip().str.upper().isin(spec_set)
            elif "WORKCENTER_GROUP" in df.columns:
                mask &= df["WORKCENTER_GROUP"].isin(wc_groups)

    if reason and "LOSSREASONNAME" in df.columns:
        mask &= df["LOSSREASONNAME"].str.strip() == reason.strip()

    if metric_filter == "reject" and "REJECT_TOTAL_QTY" in df.columns:
        mask &= df["REJECT_TOTAL_QTY"] > 0
    elif metric_filter == "defect" and "DEFECT_QTY" in df.columns:
        mask &= df["DEFECT_QTY"] > 0

    return df[mask]


# ============================================================
# Derivation helpers
# ============================================================


def _derive_analytics_raw(df: pd.DataFrame) -> list:
    """GROUP BY (TXN_DAY, LOSSREASONNAME) → per date×reason rows."""
    if df is None or df.empty:
        return []

    agg_cols = {
        "MOVEIN_QTY": ("MOVEIN_QTY", "sum"),
        "REJECT_TOTAL_QTY": ("REJECT_TOTAL_QTY", "sum"),
        "DEFECT_QTY": ("DEFECT_QTY", "sum"),
    }
    # Add optional columns if present
    if "AFFECTED_WORKORDER_COUNT" in df.columns:
        agg_cols["AFFECTED_WORKORDER_COUNT"] = ("AFFECTED_WORKORDER_COUNT", "sum")

    grouped = (
        df.groupby(["TXN_DAY", "LOSSREASONNAME"], sort=True)
        .agg(**agg_cols)
        .reset_index()
    )

    # Count distinct CONTAINERIDs per group for AFFECTED_LOT_COUNT
    if "CONTAINERID" in df.columns:
        lot_counts = (
            df.groupby(["TXN_DAY", "LOSSREASONNAME"])["CONTAINERID"]
            .nunique()
            .reset_index()
            .rename(columns={"CONTAINERID": "AFFECTED_LOT_COUNT"})
        )
        grouped = grouped.merge(
            lot_counts, on=["TXN_DAY", "LOSSREASONNAME"], how="left"
        )
    else:
        grouped["AFFECTED_LOT_COUNT"] = 0

    items = []
    for _, row in grouped.iterrows():
        items.append(
            {
                "bucket_date": _to_date_str(row["TXN_DAY"]),
                "reason": _normalize_text(row["LOSSREASONNAME"]) or "(未填寫)",
                "MOVEIN_QTY": _as_int(row.get("MOVEIN_QTY")),
                "REJECT_TOTAL_QTY": _as_int(row.get("REJECT_TOTAL_QTY")),
                "DEFECT_QTY": _as_int(row.get("DEFECT_QTY")),
                "AFFECTED_LOT_COUNT": _as_int(row.get("AFFECTED_LOT_COUNT")),
                "AFFECTED_WORKORDER_COUNT": _as_int(
                    row.get("AFFECTED_WORKORDER_COUNT")
                ),
            }
        )
    return items


def _derive_summary_from_analytics(analytics_raw: list) -> dict:
    """Aggregate analytics_raw into a single summary dict."""
    movein = sum(r.get("MOVEIN_QTY", 0) for r in analytics_raw)
    reject_total = sum(r.get("REJECT_TOTAL_QTY", 0) for r in analytics_raw)
    defect = sum(r.get("DEFECT_QTY", 0) for r in analytics_raw)
    affected_lot = sum(r.get("AFFECTED_LOT_COUNT", 0) for r in analytics_raw)
    affected_wo = sum(r.get("AFFECTED_WORKORDER_COUNT", 0) for r in analytics_raw)

    total_scrap = reject_total + defect
    return {
        "MOVEIN_QTY": movein,
        "REJECT_TOTAL_QTY": reject_total,
        "DEFECT_QTY": defect,
        "REJECT_RATE_PCT": round((reject_total / movein * 100) if movein else 0, 4),
        "DEFECT_RATE_PCT": round((defect / movein * 100) if movein else 0, 4),
        "REJECT_SHARE_PCT": round(
            (reject_total / total_scrap * 100) if total_scrap else 0, 4
        ),
        "AFFECTED_LOT_COUNT": affected_lot,
        "AFFECTED_WORKORDER_COUNT": affected_wo,
    }


def _derive_trend_from_analytics(analytics_raw: list) -> list:
    """Group analytics_raw by date into trend items."""
    by_date: Dict[str, Dict[str, int]] = {}
    for row in analytics_raw:
        d = row.get("bucket_date", "")
        if d not in by_date:
            by_date[d] = {"MOVEIN_QTY": 0, "REJECT_TOTAL_QTY": 0, "DEFECT_QTY": 0}
        by_date[d]["MOVEIN_QTY"] += row.get("MOVEIN_QTY", 0)
        by_date[d]["REJECT_TOTAL_QTY"] += row.get("REJECT_TOTAL_QTY", 0)
        by_date[d]["DEFECT_QTY"] += row.get("DEFECT_QTY", 0)

    items = []
    for date_str in sorted(by_date.keys()):
        vals = by_date[date_str]
        movein = vals["MOVEIN_QTY"]
        reject = vals["REJECT_TOTAL_QTY"]
        defect = vals["DEFECT_QTY"]
        items.append(
            {
                "bucket_date": date_str,
                "MOVEIN_QTY": movein,
                "REJECT_TOTAL_QTY": reject,
                "DEFECT_QTY": defect,
                "REJECT_RATE_PCT": round(
                    (reject / movein * 100) if movein else 0, 4
                ),
                "DEFECT_RATE_PCT": round(
                    (defect / movein * 100) if movein else 0, 4
                ),
            }
        )
    return items


def _paginate_detail(
    df: pd.DataFrame, *, page: int = 1, per_page: int = 50
) -> dict:
    """Sort + paginate LOT-level rows."""
    if df is None or df.empty:
        return {
            "items": [],
            "pagination": {
                "page": 1,
                "perPage": per_page,
                "total": 0,
                "totalPages": 1,
            },
        }

    page = max(int(page), 1)
    per_page = min(max(int(per_page), 1), 200)

    # Sort
    sort_cols = []
    sort_asc = []
    for col, asc in [
        ("TXN_DAY", False),
        ("WORKCENTERSEQUENCE_GROUP", True),
        ("WORKCENTERNAME", True),
        ("REJECT_TOTAL_QTY", False),
        ("CONTAINERNAME", True),
    ]:
        if col in df.columns:
            sort_cols.append(col)
            sort_asc.append(asc)

    if sort_cols:
        sorted_df = df.sort_values(sort_cols, ascending=sort_asc)
    else:
        sorted_df = df

    total = len(sorted_df)
    total_pages = max((total + per_page - 1) // per_page, 1)
    offset = (page - 1) * per_page
    page_df = sorted_df.iloc[offset : offset + per_page]

    items = []
    for _, row in page_df.iterrows():
        items.append(
            {
                "TXN_TIME": _to_datetime_str(row.get("TXN_TIME")),
                "TXN_DAY": _to_date_str(row.get("TXN_DAY")),
                "TXN_MONTH": _normalize_text(row.get("TXN_MONTH")),
                "WORKCENTER_GROUP": _normalize_text(row.get("WORKCENTER_GROUP")),
                "WORKCENTERNAME": _normalize_text(row.get("WORKCENTERNAME")),
                "SPECNAME": _normalize_text(row.get("SPECNAME")),
                "WORKFLOWNAME": _normalize_text(row.get("WORKFLOWNAME")),
                "EQUIPMENTNAME": _normalize_text(row.get("EQUIPMENTNAME")),
                "PRODUCTLINENAME": _normalize_text(row.get("PRODUCTLINENAME")),
                "PJ_TYPE": _normalize_text(row.get("PJ_TYPE")),
                "CONTAINERNAME": _normalize_text(row.get("CONTAINERNAME")),
                "PJ_FUNCTION": _normalize_text(row.get("PJ_FUNCTION")),
                "PRODUCTNAME": _normalize_text(row.get("PRODUCTNAME")),
                "LOSSREASONNAME": _normalize_text(row.get("LOSSREASONNAME")),
                "LOSSREASON_CODE": _normalize_text(row.get("LOSSREASON_CODE")),
                "REJECTCOMMENT": _normalize_text(row.get("REJECTCOMMENT")),
                "MOVEIN_QTY": _as_int(row.get("MOVEIN_QTY")),
                "REJECT_QTY": _as_int(row.get("REJECT_QTY")),
                "STANDBY_QTY": _as_int(row.get("STANDBY_QTY")),
                "QTYTOPROCESS_QTY": _as_int(row.get("QTYTOPROCESS_QTY")),
                "INPROCESS_QTY": _as_int(row.get("INPROCESS_QTY")),
                "PROCESSED_QTY": _as_int(row.get("PROCESSED_QTY")),
                "REJECT_TOTAL_QTY": _as_int(row.get("REJECT_TOTAL_QTY")),
                "DEFECT_QTY": _as_int(row.get("DEFECT_QTY")),
                "REJECT_RATE_PCT": round(
                    _as_float(row.get("REJECT_RATE_PCT")), 4
                ),
                "DEFECT_RATE_PCT": round(
                    _as_float(row.get("DEFECT_RATE_PCT")), 4
                ),
                "REJECT_SHARE_PCT": round(
                    _as_float(row.get("REJECT_SHARE_PCT")), 4
                ),
                "AFFECTED_WORKORDER_COUNT": _as_int(
                    row.get("AFFECTED_WORKORDER_COUNT")
                ),
            }
        )

    return {
        "items": items,
        "pagination": {
            "page": page,
            "perPage": per_page,
            "total": total,
            "totalPages": total_pages,
        },
    }


def _extract_available_filters(df: pd.DataFrame) -> dict:
    """Extract distinct packages/reasons/WC groups from the full cache DF."""
    return {
        "workcenter_groups": _extract_workcenter_group_options(df),
        "packages": _extract_distinct_text_values(df, "PRODUCTLINENAME"),
        "reasons": _extract_distinct_text_values(df, "LOSSREASONNAME"),
    }


# ============================================================
# Dimension Pareto from cache
# ============================================================

# Dimension → DF column mapping (matches _DIMENSION_COLUMN_MAP in reject_history_service)
_DIM_TO_DF_COLUMN = {
    "reason": "LOSSREASONNAME",
    "package": "PRODUCTLINENAME",
    "type": "PJ_TYPE",
    "workflow": "WORKFLOWNAME",
    "workcenter": "WORKCENTER_GROUP",
    "equipment": "PRIMARY_EQUIPMENTNAME",
}


def compute_dimension_pareto(
    *,
    query_id: str,
    dimension: str = "reason",
    metric_mode: str = "reject_total",
    pareto_scope: str = "top80",
    packages: Optional[List[str]] = None,
    workcenter_groups: Optional[List[str]] = None,
    reason: Optional[str] = None,
    trend_dates: Optional[List[str]] = None,
) -> Optional[Dict[str, Any]]:
    """Compute dimension pareto from cached DataFrame (no Oracle query)."""
    df = _get_cached_df(query_id)
    if df is None:
        return None

    dim_col = _DIM_TO_DF_COLUMN.get(dimension, "LOSSREASONNAME")
    if dim_col not in df.columns:
        return {"items": [], "dimension": dimension, "metric_mode": metric_mode}

    # Apply supplementary filters
    filtered = _apply_supplementary_filters(
        df,
        packages=packages,
        workcenter_groups=workcenter_groups,
        reason=reason,
    )
    if filtered is None or filtered.empty:
        return {"items": [], "dimension": dimension, "metric_mode": metric_mode}

    # Apply trend date filter
    if trend_dates and "TXN_DAY" in filtered.columns:
        date_set = set(trend_dates)
        filtered = filtered[
            filtered["TXN_DAY"].apply(lambda d: _to_date_str(d) in date_set)
        ]
        if filtered.empty:
            return {"items": [], "dimension": dimension, "metric_mode": metric_mode}

    # Determine metric column
    if metric_mode == "defect":
        metric_col = "DEFECT_QTY"
    else:
        metric_col = "REJECT_TOTAL_QTY"

    if metric_col not in filtered.columns:
        return {"items": [], "dimension": dimension, "metric_mode": metric_mode}

    # Group by dimension
    agg_dict = {}
    for col in ["MOVEIN_QTY", "REJECT_TOTAL_QTY", "DEFECT_QTY"]:
        if col in filtered.columns:
            agg_dict[col] = (col, "sum")

    grouped = filtered.groupby(dim_col, sort=False).agg(**agg_dict).reset_index()

    # Count distinct lots
    if "CONTAINERID" in filtered.columns:
        lot_counts = (
            filtered.groupby(dim_col)["CONTAINERID"]
            .nunique()
            .reset_index()
            .rename(columns={"CONTAINERID": "AFFECTED_LOT_COUNT"})
        )
        grouped = grouped.merge(lot_counts, on=dim_col, how="left")
    else:
        grouped["AFFECTED_LOT_COUNT"] = 0

    # Compute metric and sort
    grouped["METRIC_VALUE"] = grouped[metric_col].fillna(0)
    grouped = grouped[grouped["METRIC_VALUE"] > 0].sort_values(
        "METRIC_VALUE", ascending=False
    )
    if grouped.empty:
        return {"items": [], "dimension": dimension, "metric_mode": metric_mode}

    total_metric = grouped["METRIC_VALUE"].sum()
    grouped["PCT"] = (grouped["METRIC_VALUE"] / total_metric * 100).round(4)
    grouped["CUM_PCT"] = grouped["PCT"].cumsum().round(4)

    all_items = []
    for _, row in grouped.iterrows():
        all_items.append({
            "reason": _normalize_text(row.get(dim_col)) or "(未知)",
            "metric_value": _as_float(row.get("METRIC_VALUE")),
            "MOVEIN_QTY": _as_int(row.get("MOVEIN_QTY")),
            "REJECT_TOTAL_QTY": _as_int(row.get("REJECT_TOTAL_QTY")),
            "DEFECT_QTY": _as_int(row.get("DEFECT_QTY")),
            "count": _as_int(row.get("AFFECTED_LOT_COUNT")),
            "pct": round(_as_float(row.get("PCT")), 4),
            "cumPct": round(_as_float(row.get("CUM_PCT")), 4),
        })

    items = list(all_items)
    if pareto_scope == "top80" and items:
        top_items = [item for item in items if _as_float(item.get("cumPct")) <= 80.0]
        if not top_items:
            top_items = [items[0]]
        items = top_items

    return {
        "items": items,
        "dimension": dimension,
        "metric_mode": metric_mode,
    }


# ============================================================
# CSV export from cache
# ============================================================


def export_csv_from_cache(
    *,
    query_id: str,
    packages: Optional[List[str]] = None,
    workcenter_groups: Optional[List[str]] = None,
    reason: Optional[str] = None,
    metric_filter: str = "all",
    trend_dates: Optional[List[str]] = None,
    detail_reason: Optional[str] = None,
) -> Optional[list]:
    """Read cache → apply filters → return list of dicts for CSV export."""
    df = _get_cached_df(query_id)
    if df is None:
        return None

    filtered = _apply_supplementary_filters(
        df,
        packages=packages,
        workcenter_groups=workcenter_groups,
        reason=reason,
        metric_filter=metric_filter,
    )

    if trend_dates:
        date_set = set(trend_dates)
        filtered = filtered[
            filtered["TXN_DAY"].apply(lambda d: _to_date_str(d) in date_set)
        ]
    if detail_reason and "LOSSREASONNAME" in filtered.columns:
        filtered = filtered[
            filtered["LOSSREASONNAME"].str.strip() == detail_reason.strip()
        ]

    rows = []
    for _, row in filtered.iterrows():
        rows.append(
            {
                "LOT": _normalize_text(row.get("CONTAINERNAME")),
                "WORKCENTER": _normalize_text(row.get("WORKCENTERNAME")),
                "WORKCENTER_GROUP": _normalize_text(row.get("WORKCENTER_GROUP")),
                "Package": _normalize_text(row.get("PRODUCTLINENAME")),
                "FUNCTION": _normalize_text(row.get("PJ_FUNCTION")),
                "TYPE": _normalize_text(row.get("PJ_TYPE")),
                "WORKFLOW": _normalize_text(row.get("WORKFLOWNAME")),
                "PRODUCT": _normalize_text(row.get("PRODUCTNAME")),
                "原因": _normalize_text(row.get("LOSSREASONNAME")),
                "EQUIPMENT": _normalize_text(row.get("EQUIPMENTNAME")),
                "COMMENT": _normalize_text(row.get("REJECTCOMMENT")),
                "SPEC": _normalize_text(row.get("SPECNAME")),
                "REJECT_QTY": _as_int(row.get("REJECT_QTY")),
                "STANDBY_QTY": _as_int(row.get("STANDBY_QTY")),
                "QTYTOPROCESS_QTY": _as_int(row.get("QTYTOPROCESS_QTY")),
                "INPROCESS_QTY": _as_int(row.get("INPROCESS_QTY")),
                "PROCESSED_QTY": _as_int(row.get("PROCESSED_QTY")),
                "扣帳報廢量": _as_int(row.get("REJECT_TOTAL_QTY")),
                "不扣帳報廢量": _as_int(row.get("DEFECT_QTY")),
                "MOVEIN_QTY": _as_int(row.get("MOVEIN_QTY")),
                "報廢時間": _to_datetime_str(row.get("TXN_TIME")),
                "日期": _to_date_str(row.get("TXN_DAY")),
            }
        )
    return rows
