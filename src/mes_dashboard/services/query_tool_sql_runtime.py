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
        import duckdb  # type: ignore
    except Exception:
        return None, {"view_sql_fallback_reason": SQL_FALLBACK_DEP_MISSING}

    parquet_path = get_spool_file_path(namespace, query_id)
    if not parquet_path:
        return None, {"view_sql_fallback_reason": SQL_FALLBACK_SPOOL_MISS}

    conn = None
    try:
        conn = duckdb.connect(database=":memory:")
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
        return None, {"view_sql_fallback_reason": SQL_FALLBACK_RUNTIME_ERROR}
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
