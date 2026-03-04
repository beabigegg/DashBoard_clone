# -*- coding: utf-8 -*-
"""Material trace service — bidirectional LOT/material query."""

from __future__ import annotations

import io
import logging
import os
from typing import Any, Dict, List, Optional

import pandas as pd

from mes_dashboard.core.database import read_sql_df, read_sql_df_slow
from mes_dashboard.core.interactive_memory_guard import (
    enforce_dataset_memory_guard,
    maybe_gc_collect,
)
from mes_dashboard.core.redis_df_store import redis_load_df, redis_store_df
from mes_dashboard.services.batch_query_engine import compute_query_hash
from mes_dashboard.services.container_resolution_policy import (
    validate_resolution_request,
)
from mes_dashboard.services.filter_cache import (
    get_workcenter_mapping,
    get_workcenters_for_groups,
)
from mes_dashboard.sql import QueryBuilder, SQLLoader

logger = logging.getLogger("mes_dashboard.material_trace")

_REVERSE_MAX_ROWS = 10_000
_FORWARD_MAX_ROWS = 50_000
_EXPORT_MAX_ROWS = 50_000

# Safeguard: max DataFrame memory (MB) before aborting — same pattern as batch_query_engine
_MAX_RESULT_MB = int(os.getenv("MATERIAL_TRACE_MAX_RESULT_MB", "256"))

# Safeguard: IN-clause batch size — Oracle has practical limits on large IN lists
_IN_BATCH_SIZE = 1000

# Redis result cache TTL (seconds)
_CACHE_TTL = 300

_CSV_COLUMNS = {
    "CONTAINERNAME": "LOT ID",
    "PJ_WORKORDER": "工單",
    "WORKCENTER_GROUP": "站群組",
    "WORKCENTERNAME": "站點",
    "MATERIALPARTNAME": "料號",
    "MATERIALLOTNAME": "物料批號",
    "VENDORLOTNUMBER": "供應商批號",
    "QTYREQUIRED": "應領量",
    "QTYCONSUMED": "實際消耗",
    "EQUIPMENTNAME": "機台",
    "TXNDATE": "交易日期",
    "PRIMARY_CATEGORY": "主分類",
    "SECONDARY_CATEGORY": "副分類",
}


# ============================================================
# Wildcard helpers (same pattern as query_tool_service)
# ============================================================


def _normalize_wildcard_token(value: str) -> str:
    """Normalize user wildcard syntax: * → %."""
    return str(value or "").replace("*", "%")


def _is_pattern_token(value: str) -> bool:
    token = _normalize_wildcard_token(value)
    return "%" in token or "_" in token


def _add_exact_or_pattern_condition(
    builder: QueryBuilder,
    column: str,
    values: List[str],
) -> None:
    """Add IN + LIKE mixed condition supporting exact and wildcard tokens.

    Replicates the proven pattern from query_tool_service.
    """
    if not values:
        return

    col_expr = f"NVL({column}, '')"
    conditions: List[str] = []

    exact_tokens = [v for v in values if not _is_pattern_token(v)]
    pattern_tokens = [v for v in values if _is_pattern_token(v)]

    if exact_tokens:
        placeholders: List[str] = []
        for token in exact_tokens:
            param = builder._next_param()
            placeholders.append(f":{param}")
            builder.params[param] = token
        conditions.append(f"{col_expr} IN ({', '.join(placeholders)})")

    for token in pattern_tokens:
        param = builder._next_param()
        builder.params[param] = _normalize_wildcard_token(token)
        conditions.append(f"{col_expr} LIKE :{param} ESCAPE '\\'")

    if conditions:
        builder.add_condition(f"({' OR '.join(conditions)})")


# ============================================================
# Shared helpers
# ============================================================


def _enrich_workcenter_group(df: pd.DataFrame) -> pd.DataFrame:
    """Add WORKCENTER_GROUP column based on filter_cache mapping."""
    df = df.copy()
    mapping = get_workcenter_mapping()
    if mapping and "WORKCENTERNAME" in df.columns:
        df["WORKCENTER_GROUP"] = df["WORKCENTERNAME"].map(
            lambda wc: (mapping.get(wc) or {}).get("group", "")
        )
    else:
        df["WORKCENTER_GROUP"] = ""
    return df


def _resolve_workcenter_names(workcenter_groups: Optional[List[str]]) -> Optional[List[str]]:
    """Resolve group names to a flat list of WORKCENTERNAME values."""
    if not workcenter_groups:
        return None
    names = get_workcenters_for_groups(workcenter_groups)
    return names or None


def _resolve_container_ids(
    lot_names: List[str],
) -> tuple[List[str], Dict[str, str], List[str]]:
    """Batch-resolve CONTAINERNAME → CONTAINERID (supports wildcards).

    Returns:
        (container_ids, name_to_id_map, unresolved_names)
        Note: wildcard tokens are never reported as "unresolved".
    """
    builder = QueryBuilder(base_sql=SQLLoader.load("material_trace/resolve_container_ids"))
    _add_exact_or_pattern_condition(builder, "c.CONTAINERNAME", lot_names)
    sql, params = builder.build()

    df = read_sql_df(sql, params)
    if df is None or df.empty:
        # Only exact tokens can be "unresolved"
        exact_unresolved = [n for n in lot_names if not _is_pattern_token(n)]
        return [], {}, exact_unresolved

    name_to_id: Dict[str, str] = {}
    for _, row in df.iterrows():
        name_to_id[str(row["CONTAINERNAME"])] = str(row["CONTAINERID"])

    resolved_ids = list(name_to_id.values())
    # Only report unresolved for exact tokens (wildcards can match 0 rows legitimately)
    unresolved = [n for n in lot_names if not _is_pattern_token(n) and n not in name_to_id]
    return resolved_ids, name_to_id, unresolved


def _check_memory_guard(df: pd.DataFrame, *, query_id: str = "") -> None:
    """Raise if DataFrame exceeds memory / RSS thresholds.

    Delegates to the shared interactive_memory_guard for two-fence protection.
    Kept as a thin wrapper so existing call-sites remain unchanged.
    """
    enforce_dataset_memory_guard(
        df,
        operation="物料追溯查詢",
        query_id=query_id,
        max_input_mb=float(_MAX_RESULT_MB),
        max_projected_rss_mb=1100.0,
        working_set_factor=1.8,
    )


def _execute_batched_query(
    sql_name: str,
    column: str,
    values: List[str],
    wc_names: Optional[List[str]] = None,
    *,
    allow_patterns: bool = True,
) -> pd.DataFrame:
    """Execute query in batches, using slow-query channel.

    When allow_patterns=True, values containing * or % are sent as LIKE clauses.
    When allow_patterns=False (e.g. resolved CONTAINERIDs), all values are treated
    as exact IN matches regardless of content.
    """
    base_sql = SQLLoader.load(sql_name)
    chunks: list[pd.DataFrame] = []

    if allow_patterns:
        exact_tokens = [v for v in values if not _is_pattern_token(v)]
        pattern_tokens = [v for v in values if _is_pattern_token(v)]
    else:
        exact_tokens = list(values)
        pattern_tokens = []

    # Batch exact tokens; include pattern tokens once in the first batch
    for i in range(0, max(len(exact_tokens), 1), _IN_BATCH_SIZE):
        batch = exact_tokens[i : i + _IN_BATCH_SIZE]
        combined = batch + (pattern_tokens if i == 0 else [])
        if not combined:
            continue

        builder = QueryBuilder(base_sql=base_sql)
        _add_exact_or_pattern_condition(builder, column, combined)
        if wc_names:
            builder.add_in_condition("m.WORKCENTERNAME", wc_names)

        sql, params = builder.build()
        df = read_sql_df_slow(sql, params)
        if df is not None and not df.empty:
            chunks.append(df)

    if not chunks:
        return pd.DataFrame()

    result = pd.concat(chunks, ignore_index=True) if len(chunks) > 1 else chunks[0]
    # Deduplicate — wildcards across batches may produce overlapping rows
    if len(chunks) > 1 and "CONTAINERID" in result.columns:
        result = result.drop_duplicates(subset=["CONTAINERID", "MATERIALLOTNAME", "WORKCENTERNAME", "TXNDATE"], ignore_index=True)
    _check_memory_guard(result)
    return result


def _paginate(df: pd.DataFrame, page: int, per_page: int) -> Dict[str, Any]:
    """Apply pagination to a DataFrame and return paginated dict."""
    total = len(df)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = min(page, total_pages)
    start = (page - 1) * per_page
    end = start + per_page
    page_df = df.iloc[start:end]

    # Replace NaN/NaT with None so JSON serialization produces null (not NaN).
    # Must convert to object dtype first — float64 columns coerce None back to NaN.
    page_df = page_df.astype(object).where(page_df.notna(), None)

    return {
        "rows": page_df.to_dict("records"),
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": total_pages,
        },
    }


# ============================================================
# Redis result cache helpers
# ============================================================


def _compute_cache_key(
    mode: str,
    values: List[str],
    workcenter_groups: Optional[List[str]] = None,
) -> str:
    """Compute a deterministic Redis cache key for a query."""
    cache_hash = compute_query_hash({
        "mode": mode,
        "values": sorted(values),
        "workcenter_groups": sorted(workcenter_groups) if workcenter_groups else [],
    })
    return f"mt:result:{cache_hash}"


def _try_load_cached_df(cache_key: str) -> Optional[pd.DataFrame]:
    """Attempt to load a cached DataFrame from Redis."""
    try:
        return redis_load_df(cache_key)
    except Exception as exc:
        logger.debug("Redis cache load failed (%s): %s", cache_key, exc)
        return None


def _try_store_cached_df(cache_key: str, df: pd.DataFrame) -> None:
    """Attempt to store a DataFrame in Redis cache."""
    try:
        redis_store_df(cache_key, df, ttl=_CACHE_TTL)
    except Exception as exc:
        logger.debug("Redis cache store failed (%s): %s", cache_key, exc)


# ============================================================
# Forward query (LOT ID / Work Order → Materials)
# ============================================================


def forward_query(
    mode: str,
    values: List[str],
    workcenter_groups: Optional[List[str]] = None,
    page: int = 1,
    per_page: int = 50,
) -> Dict[str, Any]:
    """Execute forward material trace query."""
    meta: Dict[str, Any] = {}
    cache_key = _compute_cache_key(mode, values, workcenter_groups)

    # Try Redis cache first (pagination and re-queries skip Oracle)
    cached_df = _try_load_cached_df(cache_key)
    if cached_df is not None:
        logger.debug("Forward query cache hit: %s", cache_key)
        result = _paginate(cached_df, page, per_page)
        result["meta"] = meta
        return result

    wc_names = _resolve_workcenter_names(workcenter_groups)

    if mode == "lot":
        container_ids, _name_map, unresolved = _resolve_container_ids(values)
        if unresolved:
            meta["unresolved"] = unresolved
        if not container_ids:
            return {"rows": [], "pagination": {"page": 1, "per_page": per_page, "total": 0, "total_pages": 0}, "meta": meta}

        df = _execute_batched_query("material_trace/forward_by_lot", "m.CONTAINERID", container_ids, wc_names, allow_patterns=False)

    else:  # workorder
        df = _execute_batched_query("material_trace/forward_by_workorder", "m.PJ_WORKORDER", values, wc_names)

    maybe_gc_collect()

    if df.empty:
        return {"rows": [], "pagination": {"page": 1, "per_page": per_page, "total": 0, "total_pages": 0}, "meta": meta}

    # Forward truncation — SQL fetches 50001 rows to detect overflow
    if len(df) > _FORWARD_MAX_ROWS:
        df = df.iloc[:_FORWARD_MAX_ROWS]
        meta["truncated"] = True
        meta["max_rows"] = _FORWARD_MAX_ROWS

    df = _enrich_workcenter_group(df)

    # Store enriched result in Redis for subsequent pagination / export
    _try_store_cached_df(cache_key, df)

    result = _paginate(df, page, per_page)
    result["meta"] = meta
    return result


# ============================================================
# Reverse query (Material Lot → LOTs)
# ============================================================


def reverse_query(
    values: List[str],
    workcenter_groups: Optional[List[str]] = None,
    page: int = 1,
    per_page: int = 50,
) -> Dict[str, Any]:
    """Execute reverse material trace query."""
    meta: Dict[str, Any] = {}
    cache_key = _compute_cache_key("material_lot", values, workcenter_groups)

    # Try Redis cache first
    cached_df = _try_load_cached_df(cache_key)
    if cached_df is not None:
        logger.debug("Reverse query cache hit: %s", cache_key)
        result = _paginate(cached_df, page, per_page)
        result["meta"] = meta
        return result

    wc_names = _resolve_workcenter_names(workcenter_groups)

    df = _execute_batched_query("material_trace/reverse_by_material_lot", "m.MATERIALLOTNAME", values, wc_names)

    maybe_gc_collect()

    if df.empty:
        return {"rows": [], "pagination": {"page": 1, "per_page": per_page, "total": 0, "total_pages": 0}, "meta": meta}

    # Check truncation (SQL fetches 10001 rows to detect overflow)
    if len(df) > _REVERSE_MAX_ROWS:
        df = df.iloc[:_REVERSE_MAX_ROWS]
        meta["truncated"] = True
        meta["max_rows"] = _REVERSE_MAX_ROWS

    df = _enrich_workcenter_group(df)

    # Store enriched result in Redis for subsequent pagination / export
    _try_store_cached_df(cache_key, df)

    result = _paginate(df, page, per_page)
    result["meta"] = meta
    return result


# ============================================================
# CSV Export
# ============================================================


def export_csv(
    mode: str,
    values: List[str],
    workcenter_groups: Optional[List[str]] = None,
) -> tuple[bytes, Dict[str, Any]]:
    """Export query results as UTF-8 BOM CSV."""
    meta: Dict[str, Any] = {}

    # Try Redis cache first — avoids re-querying Oracle for export
    cache_key = _compute_cache_key(mode, values, workcenter_groups)
    df = _try_load_cached_df(cache_key)

    if df is None:
        # Cache miss — execute query
        wc_names = _resolve_workcenter_names(workcenter_groups)

        if mode == "lot":
            container_ids, _name_map, unresolved = _resolve_container_ids(values)
            if unresolved:
                meta["unresolved"] = unresolved
            if not container_ids:
                return _empty_csv(), meta

            df = _execute_batched_query("material_trace/forward_by_lot", "m.CONTAINERID", container_ids, wc_names, allow_patterns=False)

        elif mode == "workorder":
            df = _execute_batched_query("material_trace/forward_by_workorder", "m.PJ_WORKORDER", values, wc_names)

        else:  # material_lot
            df = _execute_batched_query("material_trace/reverse_by_material_lot", "m.MATERIALLOTNAME", values, wc_names)

        if df.empty:
            return _empty_csv(), meta

        df = _enrich_workcenter_group(df)

        # Store in cache for potential subsequent requests
        _try_store_cached_df(cache_key, df)

    if df.empty:
        return _empty_csv(), meta

    # Truncate if over export limit
    if len(df) > _EXPORT_MAX_ROWS:
        df = df.iloc[:_EXPORT_MAX_ROWS]
        meta["truncated"] = True
        meta["export_max_rows"] = _EXPORT_MAX_ROWS

    # Select and rename columns for CSV
    available_cols = [c for c in _CSV_COLUMNS if c in df.columns]
    export_df = df[available_cols].rename(columns=_CSV_COLUMNS)

    buf = io.BytesIO()
    buf.write(b"\xef\xbb\xbf")  # UTF-8 BOM
    buf.write(export_df.fillna("").to_csv(index=False).encode("utf-8"))
    return buf.getvalue(), meta


def _empty_csv() -> bytes:
    """Return an empty CSV with headers only."""
    buf = io.BytesIO()
    buf.write(b"\xef\xbb\xbf")
    headers = ",".join(_CSV_COLUMNS.values()) + "\n"
    buf.write(headers.encode("utf-8"))
    return buf.getvalue()
