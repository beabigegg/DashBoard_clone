# -*- coding: utf-8 -*-
"""DuckDB SQL runtime for Yield Alert Center view computation.

Provides out-of-core view aggregation (summary / trend / heatmap /
station_summary / package_summary / alerts / filter_options) by querying
parquet spool files directly via DuckDB, avoiding full DataFrame loads into
pandas.

Entry point: ``try_compute_view_from_spool``
"""

from __future__ import annotations

import logging
import math
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from mes_dashboard.core.feature_flags import resolve_bool_flag
from mes_dashboard.core.query_spool_store import get_spool_file_path

logger = logging.getLogger("mes_dashboard.yield_alert_sql_runtime")

# ── Feature flag ──────────────────────────────────────────────────────────────
_SQL_VIEW_ENABLED = resolve_bool_flag("YIELD_ALERT_SQL_VIEW_ENABLED", default=True)

SQL_FALLBACK_DISABLED = "yield_alert_sql_disabled"
SQL_FALLBACK_DEP_MISSING = "yield_alert_sql_dependency_missing"
SQL_FALLBACK_SPOOL_MISS = "yield_alert_sql_spool_miss"
SQL_FALLBACK_RUNTIME_ERROR = "yield_alert_sql_runtime_error"

_SPOOL_NAMESPACE = "yield_alert_dataset"

# Columns used for TRANSACTION_QTY deduplication (mirrors _TX_DEDUP_COLUMNS)
_TX_DEDUP_COLS = [
    "DATE_BUCKET", "WORKORDER",
    "DEPARTMENT_NAME", "DEPARTMENT_GROUP", "PROCESS_CATEGORY",
    "LINE_NAME", "PACKAGE_NAME", "TYPE_NAME", "FUNCTION_NAME", "OPERATION_TEXT",
]

# Mapping from API sort_by field to SQL column/alias
_ALERTS_SQL_SORT_COL: Dict[str, str] = {
    "date_bucket": "DATE_BUCKET",
    "workorder": "WORKORDER",
    "reason_code": "REASON_CODE",
    "package": "PACKAGE_NAME",
    "type": "TYPE_NAME",
    "scrap_qty": "scrap_qty",
    "yield_pct": "yield_pct",
    "risk_score": "risk_score",
}

# Station ordering (mirrors _DEPT_SEQ_MAP)
_YIELD_WORKCENTER_GROUP_ORDER = [
    "切割", "焊接_DB", "焊接_WB", "成型", "去膠", "水吹砂",
    "電鍍", "移印", "切彎腳", "TMTT", "品檢", "FQC",
]
_DEPT_SEQ_MAP: Dict[str, int] = {g: i for i, g in enumerate(_YIELD_WORKCENTER_GROUP_ORDER)}


# ── SQL helpers ───────────────────────────────────────────────────────────────

def _qid(name: str) -> str:
    """Quote a DuckDB identifier."""
    return '"' + str(name).replace('"', '""') + '"'


def _sql_str_literal(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _attach_spool_view(conn: Any, parquet_path: str) -> None:
    sql = (
        "CREATE OR REPLACE TEMP VIEW yield_alert_src AS "
        f"SELECT * FROM read_parquet({_sql_str_literal(parquet_path)})"
    )
    conn.execute(sql)


def _fetch_dict_rows(
    conn: Any,
    sql: str,
    params: Optional[List[Any]] = None,
) -> List[Dict[str, Any]]:
    cursor = conn.execute(sql, params or [])
    columns = [desc[0] for desc in (cursor.description or [])]
    rows = cursor.fetchall()
    return [dict(zip(columns, row)) for row in rows]


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value) if value is not None else default
    except (TypeError, ValueError):
        return default


# ── Task 4.2: Reason exclusion SQL condition ──────────────────────────────────

def _build_reason_exclusion_sql(
    excluded_reason_tokens: Set[str],
) -> Tuple[str, List[Any]]:
    """Return a SQL condition (and params) implementing the reason exclusion policy.

    Equivalent to ``_apply_reason_policy`` in ``yield_alert_dataset_cache``:
      - Always exclude UNMAPPED_REASON rows from scrap aggregation
      - Exclude rows matching excluded normalized codes / raw / name tokens
      - Always INCLUDE reversal rows (SCRAP_QTY < 0)
    """
    params: List[Any] = []
    exclusion_parts: List[str] = []

    # Exclude UNMAPPED_REASON
    exclusion_parts.append("\"REASON_CODE\" <> 'UNMAPPED_REASON'")

    if excluded_reason_tokens:
        from mes_dashboard.services.yield_alert_service import _build_normalized_exclusion_tokens
        normalized = _build_normalized_exclusion_tokens(excluded_reason_tokens)

        if normalized:
            sorted_norm = sorted(normalized)
            placeholders = ", ".join("?" for _ in sorted_norm)
            exclusion_parts.append(f"\"REASON_CODE\" NOT IN ({placeholders})")
            params.extend(sorted_norm)

        sorted_tokens = sorted(excluded_reason_tokens)
        placeholders = ", ".join("?" for _ in sorted_tokens)
        exclusion_parts.append(f"\"REASON_RAW_UPPER\" NOT IN ({placeholders})")
        exclusion_parts.append(f"\"REASON_NAME_UPPER\" NOT IN ({placeholders})")
        params.extend(sorted_tokens)
        params.extend(sorted_tokens)

    exclusion_sql = " AND ".join(exclusion_parts)
    # Reversals (SCRAP_QTY < 0) are always included
    full_condition = f"(({exclusion_sql}) OR \"SCRAP_QTY\" < 0)"
    return full_condition, params


# ── Dimension filter helpers ──────────────────────────────────────────────────

def _build_dimension_filter_sql(
    filters: Dict[str, List[str]],
    *,
    dept_proc_only: bool = False,
) -> Tuple[str, List[Any]]:
    """Build WHERE conditions for dimension filters.

    When ``dept_proc_only=True``, only DEPARTMENT_GROUP and PROCESS_CATEGORY
    are applied (for summary/trend/heatmap/station_summary/package_summary).
    For alerts, use ``dept_proc_only=False`` to include all 6 dimensions.
    """
    conditions: List[str] = []
    params: List[Any] = []

    col_map: Dict[str, str] = {
        "departments": "DEPARTMENT_GROUP",
        "process_category": "PROCESS_CATEGORY",
    }
    if not dept_proc_only:
        col_map.update({
            "lines": "LINE_NAME",
            "packages": "PACKAGE_NAME",
            "types": "TYPE_NAME",
            "functions": "FUNCTION_NAME",
        })

    for filter_key, col in col_map.items():
        values = [str(v) for v in (filters.get(filter_key) or []) if str(v).strip()]
        if not values:
            continue
        placeholders = ", ".join("?" for _ in values)
        conditions.append(f"{_qid(col)} IN ({placeholders})")
        params.extend(values)

    where_sql = " AND ".join(conditions) if conditions else ""
    return where_sql, params


# ── Date bucket expression ────────────────────────────────────────────────────

def _granularity_bucket_expr(granularity: str, col: str = "DATE_BUCKET") -> str:
    """DuckDB SQL expression for date bucketing."""
    qcol = _qid(col)
    if granularity == "week":
        return f"strftime(date_trunc('week', CAST({qcol} AS DATE)), '%Y-%m-%d')"
    if granularity == "month":
        return f"strftime(CAST({qcol} AS DATE), '%Y-%m')"
    if granularity == "year":
        return f"strftime(CAST({qcol} AS DATE), '%Y')"
    # day
    return f"CAST({qcol} AS VARCHAR)"


# ── Task 4.3: Summary SQL ─────────────────────────────────────────────────────

def _query_summary(
    conn: Any,
    *,
    dept_proc_where: str,
    dept_proc_params: List[Any],
    reason_excl_sql: str,
    reason_excl_params: List[Any],
) -> Dict[str, float]:
    """Compute overall transaction_qty, scrap_qty, yield_pct."""
    tx_dedup_cols = ", ".join(_qid(c) for c in _TX_DEDUP_COLS)
    dept_where_clause = f"WHERE {dept_proc_where}" if dept_proc_where else ""
    scrap_where_clause = (
        f"WHERE {dept_proc_where} AND {reason_excl_sql}"
        if dept_proc_where
        else f"WHERE {reason_excl_sql}"
    )

    sql = f"""
        SELECT
            (SELECT COALESCE(SUM(TRANSACTION_QTY), 0)
             FROM (
                 SELECT SUM("TRANSACTION_QTY") AS TRANSACTION_QTY
                 FROM yield_alert_src
                 {dept_where_clause}
                 GROUP BY {tx_dedup_cols}
             )
            ) AS transaction_qty,
            (SELECT COALESCE(SUM("SCRAP_QTY"), 0)
             FROM yield_alert_src
             {scrap_where_clause}
            ) AS scrap_qty
    """
    combined_params = (dept_proc_params + dept_proc_params + reason_excl_params)
    row = _fetch_dict_rows(conn, sql, combined_params)
    if not row:
        return {"transaction_qty": 0.0, "scrap_qty": 0.0, "yield_pct": 100.0}

    tx = _safe_float(row[0].get("transaction_qty"))
    sc = _safe_float(row[0].get("scrap_qty"))
    yield_pct = 100.0 if tx <= 0 else round((1 - sc / tx) * 100, 4)
    return {
        "transaction_qty": round(tx, 4),
        "scrap_qty": round(sc, 4),
        "yield_pct": yield_pct,
    }


# ── Task 4.4: Trend SQL ───────────────────────────────────────────────────────

def _query_trend(
    conn: Any,
    *,
    granularity: str,
    dept_proc_where: str,
    dept_proc_params: List[Any],
    reason_excl_sql: str,
    reason_excl_params: List[Any],
) -> List[Dict[str, Any]]:
    """Compute date-bucketed trend."""
    tx_dedup_cols = ", ".join(_qid(c) for c in _TX_DEDUP_COLS)
    bucket_expr = _granularity_bucket_expr(granularity)
    dept_where_clause = f"WHERE {dept_proc_where}" if dept_proc_where else ""
    scrap_where_clause = (
        f"WHERE {dept_proc_where} AND {reason_excl_sql}"
        if dept_proc_where
        else f"WHERE {reason_excl_sql}"
    )

    tx_sql = f"""
        SELECT "DATE_BUCKET" AS bucket, SUM(TRANSACTION_QTY) AS tx_qty
        FROM (
            SELECT {bucket_expr} AS DATE_BUCKET,
                   SUM("TRANSACTION_QTY") AS TRANSACTION_QTY
            FROM yield_alert_src
            {dept_where_clause}
            GROUP BY {tx_dedup_cols}
        )
        GROUP BY 1
    """
    sc_sql = f"""
        SELECT {bucket_expr} AS bucket, SUM("SCRAP_QTY") AS sc_qty
        FROM yield_alert_src
        {scrap_where_clause}
        GROUP BY 1
    """
    tx_rows = _fetch_dict_rows(conn, tx_sql, dept_proc_params)
    sc_rows = _fetch_dict_rows(conn, sc_sql, dept_proc_params + reason_excl_params)

    tx_by_bucket: Dict[str, float] = {
        str(r["bucket"]): _safe_float(r.get("tx_qty")) for r in tx_rows if r.get("bucket")
    }
    sc_by_bucket: Dict[str, float] = {
        str(r["bucket"]): _safe_float(r.get("sc_qty")) for r in sc_rows if r.get("bucket")
    }

    trend: List[Dict[str, Any]] = []
    for bucket in sorted(set(tx_by_bucket) | set(sc_by_bucket)):
        tx = tx_by_bucket.get(bucket, 0.0)
        sc = sc_by_bucket.get(bucket, 0.0)
        day_yield = 100.0 if tx <= 0 else round((1 - sc / tx) * 100, 4)
        trend.append({
            "date_bucket": bucket,
            "transaction_qty": round(tx, 4),
            "scrap_qty": round(sc, 4),
            "yield_pct": day_yield,
        })
    return trend


# ── Task 4.5: Heatmap SQL ─────────────────────────────────────────────────────

def _query_heatmap(
    conn: Any,
    *,
    granularity: str,
    dept_proc_where: str,
    dept_proc_params: List[Any],
    reason_excl_sql: str,
    reason_excl_params: List[Any],
) -> List[Dict[str, Any]]:
    """Compute station × date yield matrix."""
    tx_dedup_cols = ", ".join(_qid(c) for c in _TX_DEDUP_COLS)
    bucket_expr = _granularity_bucket_expr(granularity)
    dept_where_clause = f"WHERE {dept_proc_where}" if dept_proc_where else ""
    scrap_where_clause = (
        f"WHERE {dept_proc_where} AND {reason_excl_sql}"
        if dept_proc_where
        else f"WHERE {reason_excl_sql}"
    )

    tx_sql = f"""
        SELECT "DATE_BUCKET" AS bucket, "DEPARTMENT_GROUP", SUM(TRANSACTION_QTY) AS tx_qty
        FROM (
            SELECT {bucket_expr} AS DATE_BUCKET, "DEPARTMENT_GROUP",
                   SUM("TRANSACTION_QTY") AS TRANSACTION_QTY
            FROM yield_alert_src
            {dept_where_clause}
            GROUP BY {tx_dedup_cols}
        )
        GROUP BY 1, 2
    """
    sc_sql = f"""
        SELECT {bucket_expr} AS bucket, "DEPARTMENT_GROUP", SUM("SCRAP_QTY") AS sc_qty
        FROM yield_alert_src
        {scrap_where_clause}
        GROUP BY 1, 2
    """
    tx_rows = _fetch_dict_rows(conn, tx_sql, dept_proc_params)
    sc_rows = _fetch_dict_rows(conn, sc_sql, dept_proc_params + reason_excl_params)

    # Build dicts keyed by (bucket, dept)
    tx_map: Dict[Tuple[str, str], float] = {}
    for r in tx_rows:
        key = (str(r.get("bucket") or ""), str(r.get("DEPARTMENT_GROUP") or ""))
        tx_map[key] = _safe_float(r.get("tx_qty"))

    sc_map: Dict[Tuple[str, str], float] = {}
    for r in sc_rows:
        key = (str(r.get("bucket") or ""), str(r.get("DEPARTMENT_GROUP") or ""))
        sc_map[key] = _safe_float(r.get("sc_qty"))

    all_keys = set(tx_map) | set(sc_map)
    result: List[Dict[str, Any]] = []
    for bucket, dept in all_keys:
        tx = tx_map.get((bucket, dept), 0.0)
        sc = sc_map.get((bucket, dept), 0.0)
        result.append({
            "station": dept,
            "station_seq": _DEPT_SEQ_MAP.get(dept, 999),
            "date": bucket,
            "transaction_qty": round(tx, 4),
            "scrap_qty": round(sc, 4),
            "yield_pct": 100.0 if tx <= 0 else round((1 - sc / tx) * 100, 4),
        })
    result.sort(key=lambda x: (_DEPT_SEQ_MAP.get(x["station"], 999), x["date"]))
    return result


# ── Task 4.6: Station and package summary SQL ─────────────────────────────────

def _query_station_summary(
    conn: Any,
    *,
    dept_proc_where: str,
    dept_proc_params: List[Any],
    reason_excl_sql: str,
    reason_excl_params: List[Any],
) -> List[Dict[str, Any]]:
    """Per-station yield summary sorted by yield_pct ascending."""
    tx_dedup_cols = ", ".join(_qid(c) for c in _TX_DEDUP_COLS)
    dept_where_clause = f"WHERE {dept_proc_where}" if dept_proc_where else ""
    scrap_where_clause = (
        f"WHERE {dept_proc_where} AND {reason_excl_sql}"
        if dept_proc_where
        else f"WHERE {reason_excl_sql}"
    )

    tx_sql = f"""
        SELECT "DEPARTMENT_GROUP", SUM(TRANSACTION_QTY) AS tx_qty
        FROM (
            SELECT "DEPARTMENT_GROUP", SUM("TRANSACTION_QTY") AS TRANSACTION_QTY
            FROM yield_alert_src
            {dept_where_clause}
            GROUP BY {tx_dedup_cols}
        )
        GROUP BY 1
    """
    sc_sql = f"""
        SELECT "DEPARTMENT_GROUP", SUM("SCRAP_QTY") AS sc_qty
        FROM yield_alert_src
        {scrap_where_clause}
        GROUP BY 1
    """
    tx_map = {
        str(r.get("DEPARTMENT_GROUP") or ""): _safe_float(r.get("tx_qty"))
        for r in _fetch_dict_rows(conn, tx_sql, dept_proc_params)
    }
    sc_map = {
        str(r.get("DEPARTMENT_GROUP") or ""): _safe_float(r.get("sc_qty"))
        for r in _fetch_dict_rows(conn, sc_sql, dept_proc_params + reason_excl_params)
    }

    result: List[Dict[str, Any]] = []
    for dept in set(tx_map) | set(sc_map):
        tx = tx_map.get(dept, 0.0)
        sc = sc_map.get(dept, 0.0)
        result.append({
            "station": dept,
            "station_seq": _DEPT_SEQ_MAP.get(dept, 999),
            "transaction_qty": round(tx, 4),
            "scrap_qty": round(sc, 4),
            "yield_pct": 100.0 if tx <= 0 else round((1 - sc / tx) * 100, 4),
        })
    result.sort(key=lambda x: (x["yield_pct"], _DEPT_SEQ_MAP.get(x["station"], 999)))
    return result


def _query_package_summary(
    conn: Any,
    *,
    dept_proc_where: str,
    dept_proc_params: List[Any],
    reason_excl_sql: str,
    reason_excl_params: List[Any],
) -> List[Dict[str, Any]]:
    """Per-package yield summary sorted by scrap_qty descending."""
    tx_dedup_cols = ", ".join(_qid(c) for c in _TX_DEDUP_COLS)
    dept_where_clause = f"WHERE {dept_proc_where}" if dept_proc_where else ""
    scrap_where_clause = (
        f"WHERE {dept_proc_where} AND {reason_excl_sql}"
        if dept_proc_where
        else f"WHERE {reason_excl_sql}"
    )

    tx_sql = f"""
        SELECT "PACKAGE_NAME", SUM(TRANSACTION_QTY) AS tx_qty
        FROM (
            SELECT "PACKAGE_NAME", SUM("TRANSACTION_QTY") AS TRANSACTION_QTY
            FROM yield_alert_src
            {dept_where_clause}
            GROUP BY {tx_dedup_cols}
        )
        GROUP BY 1
    """
    sc_sql = f"""
        SELECT "PACKAGE_NAME", SUM("SCRAP_QTY") AS sc_qty
        FROM yield_alert_src
        {scrap_where_clause}
        GROUP BY 1
    """
    tx_map = {
        str(r.get("PACKAGE_NAME") or ""): _safe_float(r.get("tx_qty"))
        for r in _fetch_dict_rows(conn, tx_sql, dept_proc_params)
    }
    sc_map = {
        str(r.get("PACKAGE_NAME") or ""): _safe_float(r.get("sc_qty"))
        for r in _fetch_dict_rows(conn, sc_sql, dept_proc_params + reason_excl_params)
    }

    result: List[Dict[str, Any]] = []
    for pkg in set(tx_map) | set(sc_map):
        tx = tx_map.get(pkg, 0.0)
        sc = sc_map.get(pkg, 0.0)
        result.append({
            "package": pkg,
            "transaction_qty": round(tx, 4),
            "scrap_qty": round(sc, 4),
            "yield_pct": 100.0 if tx <= 0 else round((1 - sc / tx) * 100, 4),
        })
    result.sort(key=lambda x: (-x["scrap_qty"], x["yield_pct"]))
    return result


# ── Task 4.7: Alerts SQL ──────────────────────────────────────────────────────

def _query_alerts(
    conn: Any,
    *,
    full_where: str,
    full_params: List[Any],
    reason_excl_sql: str,
    reason_excl_params: List[Any],
    granularity: str,
    risk_threshold: float,
    min_scrap_qty: float,
    sort_by: str,
    sort_dir: str,
    page: int,
    per_page: int,
) -> Dict[str, Any]:
    """Compute alert groups with SQL-level filtering, sorting, and pagination.

    Applies the same time-granularity bucketing as trend/heatmap so that
    the alerts table rows match the selected granularity (day/week/month/year).
    TX dedup uses a two-level approach (inner: dedup per raw daily date;
    outer: sum bucketed totals) to avoid double-counting.
    """
    bucket_expr = _granularity_bucket_expr(granularity)

    combined_where = (
        f"WHERE {full_where} AND {reason_excl_sql} AND \"SCRAP_QTY\" <> 0"
        if full_where
        else f"WHERE {reason_excl_sql} AND \"SCRAP_QTY\" <> 0"
    )
    combined_params = full_params + reason_excl_params

    safe_threshold = float(risk_threshold)
    safe_min_scrap = float(min_scrap_qty)

    tx_where = f"WHERE {full_where}" if full_where else ""

    # Non-date columns used in alert grouping
    alert_extra_cols = [
        "WORKORDER", "REASON_CODE", "REASON_NAME",
        "DEPARTMENT_GROUP", "PROCESS_CATEGORY",
        "LINE_NAME", "PACKAGE_NAME", "TYPE_NAME", "FUNCTION_NAME", "OPERATION_TEXT",
    ]
    # Non-date columns used in TX dedup (no REASON_* columns)
    tx_extra_cols = [
        "WORKORDER",
        "DEPARTMENT_GROUP", "PROCESS_CATEGORY",
        "LINE_NAME", "PACKAGE_NAME", "TYPE_NAME", "FUNCTION_NAME", "OPERATION_TEXT",
    ]

    alert_extra_sql = ", ".join(_qid(c) for c in alert_extra_cols)
    tx_extra_sql    = ", ".join(_qid(c) for c in tx_extra_cols)

    tx_join_on = (
        'ag."DATE_BUCKET" IS NOT DISTINCT FROM tx."DATE_BUCKET" AND '
        + " AND ".join(
            f'ag.{_qid(c)} IS NOT DISTINCT FROM tx.{_qid(c)}'
            for c in tx_extra_cols
        )
    )

    # Two-level TX dedup:
    #   _tx_daily  – groups by raw DATE_BUCKET → one TX value per (raw_date, workorder, …)
    #   tx_lookup  – groups by bucketed DATE_BUCKET → sums daily TX into the bucket period
    base_sql = f"""
        WITH _tx_daily AS (
            SELECT
                {bucket_expr} AS bucketed_date,
                {tx_extra_sql},
                SUM("TRANSACTION_QTY") AS tx_raw
            FROM yield_alert_src
            {tx_where}
            GROUP BY "DATE_BUCKET", {tx_extra_sql}
        ),
        tx_lookup AS (
            SELECT bucketed_date AS "DATE_BUCKET", {tx_extra_sql}, SUM(tx_raw) AS transaction_qty
            FROM _tx_daily
            GROUP BY bucketed_date, {tx_extra_sql}
        ),
        alert_groups AS (
            SELECT
                {bucket_expr} AS "DATE_BUCKET",
                {alert_extra_sql},
                SUM("SCRAP_QTY") AS scrap_qty
            FROM yield_alert_src
            {combined_where}
            GROUP BY {bucket_expr}, {alert_extra_sql}
        ),
        alert_with_tx AS (
            SELECT ag.*, COALESCE(tx.transaction_qty, 0) AS transaction_qty
            FROM alert_groups ag
            LEFT JOIN tx_lookup tx ON {tx_join_on}
        ),
        alerts_computed AS (
            SELECT *,
                CASE WHEN transaction_qty <= 0 THEN 100.0
                     ELSE ROUND((1 - scrap_qty / transaction_qty) * 100, 4)
                END AS yield_pct,
                CASE WHEN transaction_qty <= 0 THEN 0.0
                     ELSE ROUND((scrap_qty / transaction_qty) * 100, 4)
                END AS scrap_rate_pct,
                ROUND(
                    GREATEST(0.0,
                        ? - CASE WHEN transaction_qty <= 0 THEN 100.0
                                 ELSE ROUND((1 - scrap_qty / transaction_qty) * 100, 4)
                            END
                    )
                    + LEAST(GREATEST(scrap_qty, 0), 200) / 20.0,
                    4
                ) AS risk_score
            FROM alert_with_tx
        ),
        alerts_filtered AS (
            SELECT *,
                CASE
                    WHEN yield_pct < ? - 2.0 OR scrap_qty >= 100 THEN 'high'
                    WHEN yield_pct < ? OR scrap_qty >= 20 THEN 'medium'
                    ELSE 'low'
                END AS risk_level
            FROM alerts_computed
            WHERE NOT (yield_pct >= ? AND scrap_qty < ?)
        )
    """
    threshold_params = [safe_threshold, safe_threshold, safe_threshold, safe_threshold, safe_min_scrap]

    # tx_lookup uses full_params (dimension filters only);
    # alert_groups uses combined_params (dimension + reason exclusion + scrap filter)
    all_cte_params = full_params + combined_params

    # Count total
    count_sql = base_sql + "SELECT COUNT(*) AS total FROM alerts_filtered"
    count_rows = _fetch_dict_rows(
        conn, count_sql, all_cte_params + threshold_params
    )
    total = int(count_rows[0].get("total") or 0) if count_rows else 0

    if total == 0:
        return {
            "items": [],
            "pagination": {"page": 1, "per_page": per_page, "total": 0, "total_pages": 1},
            "quality": None,
            "sort": {"sort_by": sort_by, "sort_dir": sort_dir},
        }

    total_pages = max(1, math.ceil(total / per_page))
    normalized_page = min(max(1, page), total_pages)
    offset = (normalized_page - 1) * per_page

    sort_col = _ALERTS_SQL_SORT_COL.get(sort_by, "DATE_BUCKET")
    sort_direction = "ASC" if sort_dir == "asc" else "DESC"

    page_sql = (
        base_sql
        + f"""
        SELECT
            "DATE_BUCKET" AS date_bucket,
            "WORKORDER" AS workorder,
            "REASON_CODE" AS reason_code,
            "REASON_NAME" AS reason_name,
            "DEPARTMENT_GROUP" AS department,
            "PROCESS_CATEGORY" AS process_category,
            "LINE_NAME" AS line,
            "PACKAGE_NAME" AS package,
            "TYPE_NAME" AS type,
            "FUNCTION_NAME" AS function,
            "OPERATION_TEXT" AS operation,
            ROUND(CAST(transaction_qty AS DOUBLE), 4) AS transaction_qty,
            ROUND(CAST(scrap_qty AS DOUBLE), 4) AS scrap_qty,
            yield_pct,
            scrap_rate_pct,
            risk_level,
            risk_score
        FROM alerts_filtered
        ORDER BY {_qid(sort_col)} {sort_direction}
        LIMIT ? OFFSET ?
        """
    )
    page_rows = _fetch_dict_rows(
        conn, page_sql,
        all_cte_params + threshold_params + [per_page, offset]
    )

    items: List[Dict[str, Any]] = []
    for r in page_rows:
        items.append({
            "date_bucket": str(r.get("date_bucket") or ""),
            "workorder": str(r.get("workorder") or "").strip(),
            "reason_code": str(r.get("reason_code") or "").strip(),
            "reason_name": str(r.get("reason_name") or "").strip(),
            "department": str(r.get("department") or "(NA)"),
            "process_category": str(r.get("process_category") or "OTHER"),
            "line": str(r.get("line") or "(NA)"),
            "package": str(r.get("package") or "(NA)"),
            "type": str(r.get("type") or "(NA)"),
            "function": str(r.get("function") or "(NA)"),
            "operation": str(r.get("operation") or "-1"),
            "transaction_qty": _safe_float(r.get("transaction_qty")),
            "scrap_qty": _safe_float(r.get("scrap_qty")),
            "yield_pct": _safe_float(r.get("yield_pct")),
            "scrap_rate_pct": _safe_float(r.get("scrap_rate_pct")),
            "risk_level": str(r.get("risk_level") or "low"),
            "risk_score": _safe_float(r.get("risk_score")),
            # Linkage fields populated by caller (apply_view)
            "match_status": "none",
            "fallback_reason": None,
            "reject_total_qty": 0.0,
        })

    # Fetch all canonical keys for full-population quality metrics
    # (lightweight: only key columns + scrap_qty, not full row data)
    keys_sql = (
        base_sql
        + """
        SELECT
            CAST("DATE_BUCKET" AS VARCHAR)[:10] AS date_bucket,
            UPPER(TRIM(COALESCE(CAST("WORKORDER" AS VARCHAR), '(NA)'))) AS workorder,
            TRIM(COALESCE(CAST("REASON_CODE" AS VARCHAR), 'UNMAPPED_REASON')) AS reason_code,
            ROUND(CAST(scrap_qty AS DOUBLE), 4) AS scrap_qty
        FROM alerts_filtered
        """
    )
    all_quality_keys = _fetch_dict_rows(
        conn, keys_sql, all_cte_params + threshold_params
    )

    return {
        "items": items,
        "pagination": {
            "page": normalized_page,
            "per_page": per_page,
            "total": total,
            "total_pages": total_pages,
        },
        "quality": None,  # populated by _enrich_alerts_with_linkage in apply_view
        "_quality_keys": all_quality_keys,
        "sort": {"sort_by": sort_by, "sort_dir": sort_dir},
    }


# ── Task 4.8: Filter options SQL ──────────────────────────────────────────────

def _query_filter_options(conn: Any) -> Dict[str, List[str]]:
    """Extract distinct filter option values from the spool."""
    options: Dict[str, List[str]] = {}
    col_key_map = [
        ("lines", "LINE_NAME"),
        ("packages", "PACKAGE_NAME"),
        ("types", "TYPE_NAME"),
        ("functions", "FUNCTION_NAME"),
        # workcenter_groups: raw DEPARTMENT_NAME (NOT the normalized DEPARTMENT_GROUP
        # column used elsewhere for the `departments` filter-apply key) — YA-10.
        ("workcenter_groups", "DEPARTMENT_NAME"),
    ]
    exclude_values = {"(NA)", "-1", ""}

    for key, col in col_key_map:
        sql = (
            f"SELECT DISTINCT CAST({_qid(col)} AS VARCHAR) AS v "
            f"FROM yield_alert_src "
            f"WHERE {_qid(col)} IS NOT NULL "
            f"ORDER BY 1"
        )
        rows = _fetch_dict_rows(conn, sql)
        options[key] = sorted(
            str(r["v"]) for r in rows
            if r.get("v") is not None and str(r["v"]).strip() not in exclude_values
        )

    # process_categories
    sql = (
        "SELECT DISTINCT CAST(\"PROCESS_CATEGORY\" AS VARCHAR) AS v "
        "FROM yield_alert_src "
        "WHERE \"PROCESS_CATEGORY\" IS NOT NULL "
        "ORDER BY 1"
    )
    rows = _fetch_dict_rows(conn, sql)
    options["process_categories"] = sorted(
        str(r["v"]) for r in rows
        if r.get("v") is not None and str(r["v"]).strip() not in {"OTHER", ""}
    )

    return options


# ── Cross-filter options ──────────────────────────────────────────────────────

def compute_cross_filter_options(
    *,
    query_id: str,
    filters: Dict[str, List[str]],
) -> Optional[Dict[str, List[str]]]:
    """Compute available dropdown options for each dimension filtered by all OTHER
    currently-selected dimensions.  Enables cross-filter UX without re-querying Oracle.

    Returns a dict with keys ``lines``, ``packages``, ``types``, ``functions``.
    Returns ``None`` when the spool is missing (cache expired or DuckDB unavailable).
    """
    try:
        from mes_dashboard.core.duckdb_runtime import create_heavy_query_connection
    except Exception:
        return None

    parquet_path = get_spool_file_path(_SPOOL_NAMESPACE, query_id)
    if not parquet_path:
        return None

    # (col_name, option_key, other_filter_keys_to_apply)
    # NOTE: "workcenter_groups" (raw DEPARTMENT_NAME) is a NET-NEW dimension, additive
    # alongside the pre-existing "departments" (normalized DEPARTMENT_GROUP) filter-apply
    # key — it is not a rename/repurpose of "departments". See YA-10 / implementation-plan
    # Pitfall #1 and #2.
    dim_specs = [
        ("LINE_NAME",       "lines",             ["departments", "packages", "types", "functions", "workcenter_groups"]),
        ("PACKAGE_NAME",    "packages",          ["departments", "lines",    "types", "functions", "workcenter_groups"]),
        ("TYPE_NAME",       "types",             ["departments", "lines",    "packages", "functions", "workcenter_groups"]),
        ("FUNCTION_NAME",   "functions",         ["departments", "lines",    "packages", "types", "workcenter_groups"]),
        ("DEPARTMENT_NAME", "workcenter_groups", ["departments", "lines",    "packages", "types", "functions"]),
    ]
    exclude_values: Set[str] = {"(NA)", "-1", ""}

    conn = None
    try:
        conn = create_heavy_query_connection()
        _attach_spool_view(conn, parquet_path)

        result: Dict[str, List[str]] = {}
        for col, opt_key, other_keys in dim_specs:
            other_filters = {k: v for k, v in filters.items() if k in other_keys}
            where_sql, where_params = _build_dimension_filter_sql(other_filters, dept_proc_only=False)
            not_null_cond = f"{_qid(col)} IS NOT NULL"
            where_clause = f"WHERE {where_sql} AND {not_null_cond}" if where_sql else f"WHERE {not_null_cond}"

            sql = (
                f"SELECT DISTINCT CAST({_qid(col)} AS VARCHAR) AS v "
                f"FROM yield_alert_src "
                f"{where_clause} "
                f"ORDER BY 1"
            )
            rows = _fetch_dict_rows(conn, sql, where_params)
            result[opt_key] = [
                str(r["v"]) for r in rows
                if r.get("v") is not None and str(r["v"]).strip() not in exclude_values
            ]

        return result

    except Exception as exc:
        logger.warning(
            "yield_alert_sql_runtime: cross_filter_options failed (query_id=%s): %s",
            query_id, exc,
        )
        return None
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


# ── Task 4.9: Entry point ─────────────────────────────────────────────────────

def try_compute_view_from_spool(
    *,
    query_id: str,
    filters: Dict[str, List[str]],
    granularity: str,
    page: int,
    per_page: int,
    sort_by: str,
    sort_dir: str,
    risk_threshold: float,
    min_scrap_qty: float,
    excluded_reason_tokens: Set[str],
) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
    """Try to compute the full view result via DuckDB over the parquet spool.

    Returns ``(result_dict, meta)`` on success, or ``(None, meta)`` on failure.
    The ``result_dict["alerts"]["quality"]`` is set to ``None`` and must be
    populated by the caller (``_enrich_alerts_with_linkage``).
    """
    if not _SQL_VIEW_ENABLED:
        return None, {"view_sql_fallback_reason": SQL_FALLBACK_DISABLED}

    try:
        from mes_dashboard.core.duckdb_runtime import create_heavy_query_connection
    except Exception:
        return None, {"view_sql_fallback_reason": SQL_FALLBACK_DEP_MISSING}

    parquet_path = get_spool_file_path(_SPOOL_NAMESPACE, query_id)
    if not parquet_path:
        from mes_dashboard.core.heavy_query_telemetry import record_spool_miss
        record_spool_miss("yield_alert", query_id)
        return None, {"view_sql_fallback_reason": SQL_FALLBACK_SPOOL_MISS}

    from mes_dashboard.core.heavy_query_telemetry import record_spool_hit
    record_spool_hit("yield_alert", query_id)

    started_at = time.time()
    conn = None
    try:
        conn = create_heavy_query_connection()
        _attach_spool_view(conn, parquet_path)

        reason_excl_sql, reason_excl_params = _build_reason_exclusion_sql(excluded_reason_tokens)

        # Apply ALL dimension filters to every section (summary/trend/heatmap/station/package/alerts)
        full_where, full_params = _build_dimension_filter_sql(
            filters, dept_proc_only=False
        )

        summary = _query_summary(
            conn,
            dept_proc_where=full_where,
            dept_proc_params=full_params,
            reason_excl_sql=reason_excl_sql,
            reason_excl_params=reason_excl_params,
        )
        trend_items = _query_trend(
            conn,
            granularity=granularity,
            dept_proc_where=full_where,
            dept_proc_params=full_params,
            reason_excl_sql=reason_excl_sql,
            reason_excl_params=reason_excl_params,
        )
        heatmap_items = _query_heatmap(
            conn,
            granularity=granularity,
            dept_proc_where=full_where,
            dept_proc_params=full_params,
            reason_excl_sql=reason_excl_sql,
            reason_excl_params=reason_excl_params,
        )
        station_summary_items = _query_station_summary(
            conn,
            dept_proc_where=full_where,
            dept_proc_params=full_params,
            reason_excl_sql=reason_excl_sql,
            reason_excl_params=reason_excl_params,
        )
        package_summary_items = _query_package_summary(
            conn,
            dept_proc_where=full_where,
            dept_proc_params=full_params,
            reason_excl_sql=reason_excl_sql,
            reason_excl_params=reason_excl_params,
        )
        alerts = _query_alerts(
            conn,
            full_where=full_where,
            full_params=full_params,
            reason_excl_sql=reason_excl_sql,
            reason_excl_params=reason_excl_params,
            granularity=granularity,
            risk_threshold=risk_threshold,
            min_scrap_qty=min_scrap_qty,
            sort_by=sort_by,
            sort_dir=sort_dir,
            page=page,
            per_page=per_page,
        )
        filter_options = _query_filter_options(conn)

        latency_s = round(time.time() - started_at, 3)
        logger.info(
            "yield_alert_sql_runtime: view computed via DuckDB (query_id=%s latency_s=%.3f)",
            query_id, latency_s,
        )

        result = {
            "summary": summary,
            "trend": {"items": trend_items, "granularity": granularity},
            "heatmap": {"items": heatmap_items, "granularity": granularity},
            "station_summary": {"items": station_summary_items},
            "package_summary": {"items": package_summary_items},
            "alerts": alerts,
            "filter_options": filter_options,
        }
        meta = {
            "view_sql_latency_s": latency_s,
            "view_sql_alert_total": alerts["pagination"].get("total", 0),
        }
        return result, meta

    except Exception as exc:
        logger.warning(
            "yield_alert_sql_runtime: DuckDB view failed (query_id=%s): %s",
            query_id, exc,
        )
        from mes_dashboard.core.heavy_query_telemetry import record_lifecycle_failure
        record_lifecycle_failure("yield_alert", reason="runtime_error")
        return None, {"view_sql_fallback_reason": SQL_FALLBACK_RUNTIME_ERROR}
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
