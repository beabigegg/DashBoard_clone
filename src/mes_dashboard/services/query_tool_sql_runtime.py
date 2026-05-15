# -*- coding: utf-8 -*-
"""DuckDB SQL runtime for Query Tool batch detail pagination on spool files.

This module provides a lightweight degraded path: when a Query Tool batch
dataset has already been written to parquet spool, pages can be served from
DuckDB without rebuilding large in-memory DataFrames.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence, Tuple

from mes_dashboard.core.feature_flags import resolve_bool_flag
from mes_dashboard.core.query_spool_store import get_spool_file_path

logger = logging.getLogger("mes_dashboard.query_tool_sql_runtime")

_SQL_ENABLED = resolve_bool_flag("QUERY_TOOL_SQL_BATCH_ENABLED", default=True)

# ── Partial-trackout aggregation constants (QT-05 / QT-06) ────────────────────

# 4-tuple key for lot_history and equipment_lots
_PARTIAL_KEY_COLS_4 = ["CONTAINERID", "EQUIPMENTID", "SPECNAME", "TRACKINTIMESTAMP"]

# 3-tuple key for adjacent_lots (SPECNAME is a non-key column there)
_PARTIAL_KEY_COLS_3 = ["CONTAINERID", "EQUIPMENTID", "TRACKINTIMESTAMP"]

_PARTIAL_NONKEY_COLS_LOT = [
    "WORKCENTERNAME", "EQUIPMENTNAME", "FINISHEDRUNCARD", "PJ_WORKORDER",
    "CONTAINERNAME", "PJ_TYPE", "PJ_BOP", "WAFER_LOT_ID",
]

# adjacent_lots has SPECNAME as non-key (it's not in the 3-tuple key)
_PARTIAL_NONKEY_COLS_ADJACENT = [
    "EQUIPMENTNAME", "SPECNAME", "FINISHEDRUNCARD", "PJ_WORKORDER",
    "CONTAINERNAME", "PJ_TYPE", "PJ_BOP", "WAFER_LOT_ID",
]


def aggregate_partial_trackouts(
    df: Any,
    key_cols: List[str],
    nonkey_cols: List[str],
    *,
    query_id: Optional[str] = None,
) -> Any:
    """Apply partial-trackout aggregation with strict guard (QT-05 / QT-06).

    Consistent groups (all non-key columns identical within the key-tuple group)
    collapse to one row: TRACKINQTY=MAX, TRACKOUTTIMESTAMP=MAX, TRACKOUTQTY=SUM,
    partial_count=COUNT(*).
    Divergent groups (strict guard, QT-06) emit their original raw rows each
    with partial_count=1.  Emits one INFO log when divergent groups exist.

    Columns listed in key_cols or nonkey_cols that are absent from df are
    silently skipped so callers need not pre-filter for optional columns.

    Returns a DataFrame sorted by TRACKINTIMESTAMP ASC (NULLS LAST), CONTAINERID.
    """
    import pandas as pd

    if df.empty:
        result = df.copy()
        result["partial_count"] = pd.array([], dtype="Int64")
        return result

    active_key_cols = [c for c in key_cols if c in df.columns]
    active_nonkey_cols = [c for c in nonkey_cols if c in df.columns]

    # If the full key tuple is not present (any required key col absent), we cannot
    # perform meaningful partial-trackout aggregation.  Return as-is with partial_count=1.
    if len(active_key_cols) < len(key_cols):
        result = df.copy()
        result["partial_count"] = 1
        return result

    grouped = df.groupby(active_key_cols, sort=False)

    agg_rows: List[Dict[str, Any]] = []
    raw_rows: List[Any] = []
    divergent_count = 0
    total_groups = grouped.ngroups

    for _, grp in grouped:
        # Check strict guard: all non-key columns must be identical within group
        is_consistent = all(
            grp[col].nunique(dropna=False) == 1
            for col in active_nonkey_cols
        )
        if is_consistent:
            # Aggregate: TRACKINQTY=MAX (original load), TRACKOUTTIMESTAMP=MAX,
            # TRACKOUTQTY=SUM (sum of all partial outs), partial_count=COUNT(*).
            row = grp.iloc[0].to_dict()
            if "TRACKINQTY" in grp.columns:
                row["TRACKINQTY"] = grp["TRACKINQTY"].max()
            if "TRACKOUTTIMESTAMP" in grp.columns:
                row["TRACKOUTTIMESTAMP"] = grp["TRACKOUTTIMESTAMP"].max()
            if "TRACKOUTQTY" in grp.columns:
                row["TRACKOUTQTY"] = grp["TRACKOUTQTY"].sum()
            row["partial_count"] = len(grp)
            agg_rows.append(row)
        else:
            # Strict guard fallback: emit raw rows with partial_count=1
            divergent_count += 1
            for _, raw_row in grp.iterrows():
                d = raw_row.to_dict()
                d["partial_count"] = 1
                raw_rows.append(d)

    # Emit summary INFO log when divergent groups exist (QT-06)
    if divergent_count > 0:
        logger.info(
            "query-tool partial-trackout strict-guard: %d divergent groups fell back to raw rows "
            "(query_id=%s, total_groups=%d)",
            divergent_count,
            query_id,
            total_groups,
        )

    parts: List[Any] = []
    if agg_rows:
        parts.append(pd.DataFrame(agg_rows))
    if raw_rows:
        parts.append(pd.DataFrame(raw_rows))

    if not parts:
        result = df.iloc[0:0].copy()
        result["partial_count"] = pd.array([], dtype="Int64")
        return result

    result = pd.concat(parts, ignore_index=True)

    # Sort: TRACKINTIMESTAMP ASC (NaT/None last), then CONTAINERID
    sort_cols = [c for c in ["TRACKINTIMESTAMP", "CONTAINERID"] if c in result.columns]
    if sort_cols:
        result = result.sort_values(
            by=sort_cols,
            ascending=[True] * len(sort_cols),
            na_position="last",
        ).reset_index(drop=True)

    # Ensure partial_count is int (not float from concat)
    result["partial_count"] = result["partial_count"].astype(int)

    return result

SQL_FALLBACK_DISABLED = "query_tool_sql_disabled"
SQL_FALLBACK_DEP_MISSING = "query_tool_sql_dependency_missing"
SQL_FALLBACK_SPOOL_MISS = "query_tool_sql_spool_miss"
SQL_FALLBACK_RUNTIME_ERROR = "query_tool_sql_runtime_error"


def _qid(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def _sql_str_literal(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _fetch_dict_rows(conn: Any, sql: str, params: Optional[List[Any]] = None) -> List[Dict[str, Any]]:
    cursor = conn.execute(sql, params or [])
    columns = [desc[0] for desc in (cursor.description or [])]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _serialize_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, Decimal):
        return float(value)
    return value


def _serialize_rows(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    serialized: List[Dict[str, Any]] = []
    for row in rows:
        serialized.append({k: _serialize_value(v) for k, v in row.items()})
    return serialized


def _normalize_tokens(values: Optional[Sequence[str]]) -> List[str]:
    seen = set()
    normalized: List[str] = []
    for raw in values or []:
        token = str(raw or "").strip()
        if not token or token in seen:
            continue
        seen.add(token)
        normalized.append(token)
    return normalized


def _available_columns(conn: Any) -> set[str]:
    rows = conn.execute("PRAGMA table_info('qt_src')").fetchall()
    return {str(row[1]) for row in rows if len(row) > 1}


def _best_order_clause(columns: set[str]) -> str:
    for col in ("TRACKINTIMESTAMP", "TXNDATE", "TXN_TIME", "TRACKOUTTIMESTAMP"):
        if col in columns:
            return f" ORDER BY {_qid(col)}"
    return ""


def _append_reject_policy_conditions(
    *,
    columns: set[str],
    conditions: List[str],
    condition_params: List[Any],
    include_excluded_scrap: bool,
    exclude_material_scrap: bool,
    exclude_pb_diode: bool,
) -> None:
    if exclude_material_scrap and "SCRAP_OBJECTTYPE" in columns:
        conditions.append(
            "UPPER(TRIM(COALESCE(CAST("
            + _qid("SCRAP_OBJECTTYPE")
            + " AS VARCHAR), ''))) <> 'MATERIAL'"
        )

    if exclude_pb_diode and "PRODUCTLINENAME" in columns:
        conditions.append(
            "NOT regexp_matches(UPPER(TRIM(COALESCE(CAST("
            + _qid("PRODUCTLINENAME")
            + " AS VARCHAR), ''))), '^PB_')"
        )

    if include_excluded_scrap:
        return

    excluded: List[str] = []
    try:
        from mes_dashboard.services.scrap_reason_exclusion_cache import (
            get_excluded_reasons,
        )

        excluded = sorted(
            {
                str(v or "").strip().upper()
                for v in (get_excluded_reasons() or set())
                if str(v or "").strip()
            }
        )
    except Exception:
        excluded = []

    if excluded and "LOSSREASON_CODE" in columns:
        placeholders = ", ".join("?" for _ in excluded)
        conditions.append(
            "UPPER(TRIM(COALESCE(CAST("
            + _qid("LOSSREASON_CODE")
            + f" AS VARCHAR), ''))) NOT IN ({placeholders})"
        )
        condition_params.extend(excluded)
    if excluded and "LOSSREASONNAME" in columns:
        placeholders = ", ".join("?" for _ in excluded)
        conditions.append(
            "UPPER(TRIM(COALESCE(CAST("
            + _qid("LOSSREASONNAME")
            + f" AS VARCHAR), ''))) NOT IN ({placeholders})"
        )
        condition_params.extend(excluded)

    if "LOSSREASONNAME" in columns:
        reason_expr = (
            "UPPER(TRIM(COALESCE(CAST("
            + _qid("LOSSREASONNAME")
            + " AS VARCHAR), '')))"
        )
        conditions.append(f"regexp_matches({reason_expr}, '^[0-9]{{3}}_')")
        conditions.append(f"NOT regexp_matches({reason_expr}, '^(XXX|ZZZ)_')")


def try_compute_page_from_spool(
    *,
    namespace: str,
    query_id: str,
    page: int = 1,
    per_page: int = 0,
    workcenter_names: Optional[Sequence[str]] = None,
    reject_policy: Optional[Dict[str, bool]] = None,
) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
    """Try loading one page from a Query Tool batch spool via DuckDB.

    Returns:
        (result, meta) on success
        (None, meta) on fallback/error
    """
    if not _SQL_ENABLED:
        return None, {"view_sql_fallback_reason": SQL_FALLBACK_DISABLED}

    try:
        from mes_dashboard.core.duckdb_runtime import create_heavy_query_connection
    except Exception:
        return None, {"view_sql_fallback_reason": SQL_FALLBACK_DEP_MISSING}

    parquet_path = get_spool_file_path(namespace, query_id)
    if not parquet_path:
        from mes_dashboard.core.heavy_query_telemetry import record_spool_miss
        record_spool_miss("query_tool", query_id)
        return None, {"view_sql_fallback_reason": SQL_FALLBACK_SPOOL_MISS}

    from mes_dashboard.core.heavy_query_telemetry import record_spool_hit
    record_spool_hit("query_tool", query_id)

    conn = None
    try:
        conn = create_heavy_query_connection()
        conn.execute(
            "CREATE OR REPLACE TEMP VIEW qt_src AS "
            f"SELECT * FROM read_parquet({_sql_str_literal(parquet_path)})"
        )
        columns = _available_columns(conn)

        conditions: List[str] = []
        condition_params: List[Any] = []
        wc_names = _normalize_tokens(workcenter_names)
        if wc_names and "WORKCENTERNAME" in columns:
            placeholders = ", ".join("?" for _ in wc_names)
            conditions.append(f"TRIM(COALESCE(CAST({_qid('WORKCENTERNAME')} AS VARCHAR), '')) IN ({placeholders})")
            condition_params.extend(wc_names)
        if reject_policy:
            _append_reject_policy_conditions(
                columns=columns,
                conditions=conditions,
                condition_params=condition_params,
                include_excluded_scrap=bool(reject_policy.get("include_excluded_scrap", False)),
                exclude_material_scrap=bool(reject_policy.get("exclude_material_scrap", True)),
                exclude_pb_diode=bool(reject_policy.get("exclude_pb_diode", True)),
            )

        where_sql = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        total_sql = f"SELECT COUNT(*) AS total FROM qt_src{where_sql}"
        total_rows = _fetch_dict_rows(conn, total_sql, condition_params)
        total = int((total_rows[0].get("total") if total_rows else 0) or 0)

        normalized_page = max(int(page or 1), 1)
        normalized_per_page = int(per_page or 0)
        if normalized_per_page > 0:
            total_pages = max(1, (total + normalized_per_page - 1) // normalized_per_page)
            current_page = max(1, min(normalized_page, total_pages))
            offset = (current_page - 1) * normalized_per_page
            limit_clause = " LIMIT ? OFFSET ?"
            page_params = [*condition_params, normalized_per_page, offset]
            effective_per_page = normalized_per_page
        else:
            total_pages = 1
            current_page = 1
            limit_clause = ""
            page_params = condition_params
            effective_per_page = total

        order_clause = _best_order_clause(columns)
        data_sql = f"SELECT * FROM qt_src{where_sql}{order_clause}{limit_clause}"
        rows = _fetch_dict_rows(conn, data_sql, page_params)
        data = _serialize_rows(rows)

        result = {
            "data": data,
            "total": total,
            "pagination": {
                "page": current_page,
                "per_page": effective_per_page,
                "total": total,
                "total_pages": total_pages,
            },
        }
        meta = {
            "view_runtime": "duckdb",
            "view_runtime_path": "spool",
            "view_reject_policy_applied": bool(reject_policy),
        }
        return result, meta
    except Exception as exc:
        logger.warning(
            "query_tool_sql_runtime: failed loading page from spool "
            "(namespace=%s query_id=%s): %s",
            namespace,
            query_id,
            exc,
        )
        from mes_dashboard.core.heavy_query_telemetry import record_lifecycle_failure
        record_lifecycle_failure("query_tool", reason="runtime_error")
        return None, {"view_sql_fallback_reason": SQL_FALLBACK_RUNTIME_ERROR}
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
