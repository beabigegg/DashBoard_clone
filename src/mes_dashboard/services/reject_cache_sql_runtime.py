# -*- coding: utf-8 -*-
"""SQL runtime for reject-history cached derivations (DuckDB-backed).

Current scope:
- batch-pareto SQL-first computation
- view SQL-first derivation (summary/trend/detail)
- export SQL-first streaming rows

If SQL runtime is unavailable, callers deterministically follow fallback policy.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Generator, Iterable, List, Optional, Sequence, Tuple

from mes_dashboard.core.feature_flags import resolve_bool_flag
from mes_dashboard.core.query_spool_store import get_spool_file_path
from mes_dashboard.services.filter_cache import get_specs_for_groups
from mes_dashboard.services.reject_history_service import _as_float, _as_int, _normalize_text

logger = logging.getLogger("mes_dashboard.reject_cache_sql_runtime")

SQL_FALLBACK_DISABLED = "cache_sql_disabled"
SQL_FALLBACK_DEP_MISSING = "cache_sql_dependency_missing"
SQL_FALLBACK_SPOOL_MISS = "cache_sql_spool_miss"
SQL_FALLBACK_RUNTIME_ERROR = "cache_sql_runtime_error"

_CACHE_SQL_ENABLED = resolve_bool_flag("REJECT_CACHE_SQL_ENABLED", default=True)
_CACHE_SQL_BATCH_ENABLED = resolve_bool_flag(
    "REJECT_CACHE_SQL_BATCH_PARETO_ENABLED", default=True
)
_CACHE_SQL_VIEW_ENABLED = resolve_bool_flag("REJECT_CACHE_SQL_VIEW_ENABLED", default=True)
_CACHE_SQL_EXPORT_ENABLED = resolve_bool_flag("REJECT_CACHE_SQL_EXPORT_ENABLED", default=True)


def _qid(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def _sql_str_literal(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _attach_spool_source_view(conn, parquet_path: str) -> None:
    sql = (
        "CREATE OR REPLACE TEMP VIEW reject_src AS "
        f"SELECT * FROM read_parquet({_sql_str_literal(parquet_path)})"
    )
    conn.execute(sql)


def _norm_value_expr(column: str) -> str:
    q_col = _qid(column)
    return f"CASE WHEN TRIM(COALESCE(CAST({q_col} AS VARCHAR), '')) = '' THEN '(未知)' ELSE TRIM(CAST({q_col} AS VARCHAR)) END"


def _append_in_condition(
    conditions: List[str],
    params: List[Any],
    *,
    expr: str,
    values: Sequence[str],
) -> None:
    normalized_values = [_normalize_text(v) for v in values if _normalize_text(v)]
    if not normalized_values:
        return
    placeholders = ", ".join("?" for _ in normalized_values)
    conditions.append(f"{expr} IN ({placeholders})")
    params.extend(normalized_values)


def _available_columns(conn) -> set[str]:
    rows = conn.execute("PRAGMA table_info('reject_src')").fetchall()
    # [cid, name, type, notnull, dflt_value, pk]
    return {str(row[1]) for row in rows if len(row) > 1}


def _build_base_filters(
    *,
    cols: set[str],
    include_excluded_scrap: bool,
    exclude_material_scrap: bool,
    exclude_pb_diode: bool,
    packages: Optional[List[str]],
    workcenter_groups: Optional[List[str]],
    reasons: Optional[List[str]],
    trend_dates: Optional[List[str]],
    metric_filter: str = "all",
) -> Tuple[List[str], List[Any]]:
    conditions: List[str] = []
    params: List[Any] = []

    if exclude_material_scrap and "SCRAP_OBJECTTYPE" in cols:
        conditions.append(
            "UPPER(TRIM(COALESCE(CAST(\"SCRAP_OBJECTTYPE\" AS VARCHAR), ''))) <> 'MATERIAL'"
        )

    if exclude_pb_diode and "PRODUCTLINENAME" in cols:
        conditions.append(
            "NOT regexp_matches(UPPER(TRIM(COALESCE(CAST(\"PRODUCTLINENAME\" AS VARCHAR), ''))), '^PB_')"
        )

    if not include_excluded_scrap:
        from mes_dashboard.services.scrap_reason_exclusion_cache import (
            get_excluded_reasons,
        )

        excluded = get_excluded_reasons() or []
        if excluded and "LOSSREASON_CODE" in cols:
            placeholders = ", ".join("?" for _ in excluded)
            conditions.append(
                f"UPPER(TRIM(COALESCE(CAST(\"LOSSREASON_CODE\" AS VARCHAR), ''))) NOT IN ({placeholders})"
            )
            params.extend([_normalize_text(v).upper() for v in excluded])
        if excluded and "LOSSREASONNAME" in cols:
            placeholders = ", ".join("?" for _ in excluded)
            conditions.append(
                f"UPPER(TRIM(COALESCE(CAST(\"LOSSREASONNAME\" AS VARCHAR), ''))) NOT IN ({placeholders})"
            )
            params.extend([_normalize_text(v).upper() for v in excluded])
        if "LOSSREASONNAME" in cols:
            name_expr = "UPPER(TRIM(COALESCE(CAST(\"LOSSREASONNAME\" AS VARCHAR), '')))"
            conditions.append(f"regexp_matches({name_expr}, '^[0-9]{{3}}_')")
            conditions.append(f"NOT regexp_matches({name_expr}, '^(XXX|ZZZ)_')")

    if packages and "PRODUCTLINENAME" in cols:
        _append_in_condition(
            conditions,
            params,
            expr=_norm_value_expr("PRODUCTLINENAME"),
            values=packages,
        )

    wc_groups = [_normalize_text(g) for g in (workcenter_groups or []) if _normalize_text(g)]
    if wc_groups:
        specs = get_specs_for_groups(wc_groups)
        if specs and "SPECNAME" in cols:
            normalized_specs = [_normalize_text(s).upper() for s in specs if _normalize_text(s)]
            if normalized_specs:
                placeholders = ", ".join("?" for _ in normalized_specs)
                conditions.append(
                    f"UPPER(TRIM(COALESCE(CAST(\"SPECNAME\" AS VARCHAR), ''))) IN ({placeholders})"
                )
                params.extend(normalized_specs)
        elif "WORKCENTER_GROUP" in cols:
            _append_in_condition(
                conditions,
                params,
                expr=_norm_value_expr("WORKCENTER_GROUP"),
                values=wc_groups,
            )

    if reasons and "LOSSREASONNAME" in cols:
        _append_in_condition(
            conditions,
            params,
            expr=_norm_value_expr("LOSSREASONNAME"),
            values=reasons,
        )

    if trend_dates and "TXN_DAY" in cols:
        trend_values = [_normalize_text(v) for v in trend_dates if _normalize_text(v)]
        if trend_values:
            placeholders = ", ".join("?" for _ in trend_values)
            conditions.append(f"strftime(CAST(\"TXN_DAY\" AS DATE), '%Y-%m-%d') IN ({placeholders})")
            params.extend(trend_values)

    normalized_metric_filter = _normalize_text(metric_filter).lower()
    if normalized_metric_filter == "reject" and "REJECT_TOTAL_QTY" in cols:
        conditions.append("COALESCE(\"REJECT_TOTAL_QTY\", 0) > 0")
    elif normalized_metric_filter == "defect" and "DEFECT_QTY" in cols:
        conditions.append("COALESCE(\"DEFECT_QTY\", 0) > 0")

    return conditions, params


def _normalize_pareto_selections(
    selections: Optional[Dict[str, List[str]]],
    *,
    dimensions: Iterable[str],
) -> Dict[str, List[str]]:
    allowed = set(dimensions)
    normalized: Dict[str, List[str]] = {}
    for dim, values in (selections or {}).items():
        dim_key = _normalize_text(dim).lower()
        if dim_key not in allowed:
            continue
        cleaned = [_normalize_text(v) for v in (values or []) if _normalize_text(v)]
        if cleaned:
            normalized[dim_key] = cleaned
    return normalized


def _apply_pareto_scope(items: List[Dict[str, Any]], pareto_scope: str) -> List[Dict[str, Any]]:
    if pareto_scope != "top80" or not items:
        return items
    top_items = [item for item in items if _as_float(item.get("cumPct")) <= 80.0]
    return top_items or [items[0]]


def _build_dimension_items(
    rows: Sequence[Sequence[Any]],
) -> List[Dict[str, Any]]:
    total_metric = sum(_as_float(row[5]) for row in rows)
    if total_metric <= 0:
        return []

    items: List[Dict[str, Any]] = []
    cumulative = 0.0
    for row in rows:
        reason = _normalize_text(row[0]) or "(未知)"
        metric_value = _as_float(row[5])
        pct = round((metric_value / total_metric) * 100, 4)
        cumulative = round(cumulative + pct, 4)
        items.append(
            {
                "reason": reason,
                "metric_value": metric_value,
                "MOVEIN_QTY": _as_int(row[1]),
                "REJECT_TOTAL_QTY": _as_int(row[2]),
                "DEFECT_QTY": _as_int(row[3]),
                "count": _as_int(row[4]),
                "pct": pct,
                "cumPct": cumulative,
            }
        )
    return items


def _fetch_dict_rows(conn, sql: str, params: Optional[Sequence[Any]] = None) -> List[Dict[str, Any]]:
    cursor = conn.execute(sql, params or [])
    columns = [desc[0] for desc in (cursor.description or [])]
    rows = cursor.fetchall()
    return [dict(zip(columns, row)) for row in rows]


def _normalize_pareto_values(values: Optional[List[str]]) -> List[str]:
    normalized: List[str] = []
    seen = set()
    for value in values or []:
        item = _normalize_text(value)
        if not item or item in seen:
            continue
        seen.add(item)
        normalized.append(item)
    return normalized


def _apply_detail_pareto_conditions(
    conditions: List[str],
    params: List[Any],
    *,
    cols: set[str],
    dim_to_column: Dict[str, str],
    pareto_dimension: Optional[str],
    pareto_values: Optional[List[str]],
    pareto_selections: Optional[Dict[str, List[str]]],
) -> None:
    normalized_selections = _normalize_pareto_selections(
        pareto_selections,
        dimensions=dim_to_column.keys(),
    )
    if normalized_selections:
        for dim, selected_values in normalized_selections.items():
            if not selected_values:
                continue
            dim_col = dim_to_column.get(dim)
            if not dim_col:
                raise ValueError(f"不支援的 pareto_dimension: {dim}")
            if dim_col not in cols:
                conditions.append("1=0")
                return
            _append_in_condition(
                conditions,
                params,
                expr=_norm_value_expr(dim_col),
                values=selected_values,
            )
        return

    normalized_values = _normalize_pareto_values(pareto_values)
    if not normalized_values:
        return

    dimension = _normalize_text(pareto_dimension).lower() or "reason"
    dim_col = dim_to_column.get(dimension)
    if not dim_col:
        raise ValueError(f"不支援的 pareto_dimension: {pareto_dimension}")
    if dim_col not in cols:
        conditions.append("1=0")
        return
    _append_in_condition(
        conditions,
        params,
        expr=_norm_value_expr(dim_col),
        values=normalized_values,
    )


def _build_summary_from_analytics(analytics_raw: List[Dict[str, Any]]) -> Dict[str, Any]:
    movein = sum(_as_int(r.get("MOVEIN_QTY")) for r in analytics_raw)
    reject_total = sum(_as_int(r.get("REJECT_TOTAL_QTY")) for r in analytics_raw)
    defect = sum(_as_int(r.get("DEFECT_QTY")) for r in analytics_raw)
    affected_lot = sum(_as_int(r.get("AFFECTED_LOT_COUNT")) for r in analytics_raw)
    affected_wo = sum(_as_int(r.get("AFFECTED_WORKORDER_COUNT")) for r in analytics_raw)
    total_scrap = reject_total + defect
    return {
        "MOVEIN_QTY": movein,
        "REJECT_TOTAL_QTY": reject_total,
        "DEFECT_QTY": defect,
        "REJECT_RATE_PCT": round((reject_total / movein * 100) if movein else 0, 4),
        "DEFECT_RATE_PCT": round((defect / movein * 100) if movein else 0, 4),
        "REJECT_SHARE_PCT": round((reject_total / total_scrap * 100) if total_scrap else 0, 4),
        "AFFECTED_LOT_COUNT": affected_lot,
        "AFFECTED_WORKORDER_COUNT": affected_wo,
    }


def _detail_sort_clause(cols: set[str]) -> str:
    order_specs = [
        ("TXN_DAY", "DESC"),
        ("WORKCENTERSEQUENCE_GROUP", "ASC"),
        ("WORKCENTERNAME", "ASC"),
        ("REJECT_TOTAL_QTY", "DESC"),
        ("CONTAINERNAME", "ASC"),
    ]
    usable = [f'{_qid(col)} {direction}' for col, direction in order_specs if col in cols]
    if not usable:
        return ""
    return "ORDER BY " + ", ".join(usable)


def _detail_item_from_row(row: Dict[str, Any]) -> Dict[str, Any]:
    from mes_dashboard.services.reject_history_service import _to_date_str, _to_datetime_str

    return {
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
        "REJECT_RATE_PCT": round(_as_float(row.get("REJECT_RATE_PCT")), 4),
        "DEFECT_RATE_PCT": round(_as_float(row.get("DEFECT_RATE_PCT")), 4),
        "REJECT_SHARE_PCT": round(_as_float(row.get("REJECT_SHARE_PCT")), 4),
        "AFFECTED_WORKORDER_COUNT": _as_int(row.get("AFFECTED_WORKORDER_COUNT")),
    }


def _export_row_from_row(row: Dict[str, Any]) -> Dict[str, Any]:
    from mes_dashboard.services.reject_history_service import _to_date_str, _to_datetime_str

    return {
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


def try_compute_batch_pareto_from_spool(
    *,
    query_id: str,
    namespace: str,
    metric_mode: str,
    pareto_scope: str,
    pareto_display_scope: str,
    pareto_selections: Optional[Dict[str, List[str]]],
    include_excluded_scrap: bool,
    exclude_material_scrap: bool,
    exclude_pb_diode: bool,
    packages: Optional[List[str]],
    workcenter_groups: Optional[List[str]],
    reasons: Optional[List[str]],
    trend_dates: Optional[List[str]],
    dim_to_column: Dict[str, str],
    top20_dimensions: Iterable[str],
) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
    """Try batch-pareto via DuckDB over spool parquet.

    Returns (result, meta). When result is None, caller should fallback.
    """
    if not _CACHE_SQL_ENABLED or not _CACHE_SQL_BATCH_ENABLED:
        return None, {
            "pareto_source": "legacy",
            "pareto_sql_fallback_reason": SQL_FALLBACK_DISABLED,
        }

    try:
        import duckdb  # type: ignore
    except Exception:
        return None, {
            "pareto_source": "legacy",
            "pareto_sql_fallback_reason": SQL_FALLBACK_DEP_MISSING,
        }

    parquet_path = get_spool_file_path(namespace, query_id)
    if not parquet_path:
        return None, {
            "pareto_source": "legacy",
            "pareto_sql_fallback_reason": SQL_FALLBACK_SPOOL_MISS,
        }

    started_at = time.time()
    conn = None
    try:
        conn = duckdb.connect(database=":memory:")
        _attach_spool_source_view(conn, parquet_path)
        cols = _available_columns(conn)
        if not cols:
            return None, {
                "pareto_source": "legacy",
                "pareto_sql_fallback_reason": SQL_FALLBACK_RUNTIME_ERROR,
            }

        metric_col = "DEFECT_QTY" if metric_mode == "defect" else "REJECT_TOTAL_QTY"
        if metric_col not in cols:
            dimensions = {
                dim: {"items": [], "dimension": dim, "metric_mode": metric_mode}
                for dim in dim_to_column
            }
            return {
                "dimensions": dimensions,
                "metric_mode": metric_mode,
                "pareto_scope": pareto_scope,
                "pareto_display_scope": pareto_display_scope,
            }, {
                "pareto_source": "cache_sql",
                "pareto_runtime": "duckdb",
                "pareto_runtime_path": "spool",
                "pareto_sql_latency_s": round(time.time() - started_at, 3),
            }

        base_conditions, base_params = _build_base_filters(
            cols=cols,
            include_excluded_scrap=include_excluded_scrap,
            exclude_material_scrap=exclude_material_scrap,
            exclude_pb_diode=exclude_pb_diode,
            packages=packages,
            workcenter_groups=workcenter_groups,
            reasons=reasons,
            trend_dates=trend_dates,
            metric_filter="all",
        )

        normalized_selections = _normalize_pareto_selections(
            pareto_selections, dimensions=dim_to_column.keys()
        )

        movein_expr = (
            "COALESCE(\"MOVEIN_QTY\", 0)" if "MOVEIN_QTY" in cols else "0"
        )
        reject_expr = (
            "COALESCE(\"REJECT_TOTAL_QTY\", 0)" if "REJECT_TOTAL_QTY" in cols else "0"
        )
        defect_expr = "COALESCE(\"DEFECT_QTY\", 0)" if "DEFECT_QTY" in cols else "0"
        lot_expr = (
            'COUNT(DISTINCT "CONTAINERID")' if "CONTAINERID" in cols else "0"
        )
        metric_expr = f"COALESCE({_qid(metric_col)}, 0)"

        dimensions: Dict[str, Dict[str, Any]] = {}
        top20_set = set(top20_dimensions)
        for dimension, dim_col in dim_to_column.items():
            if dim_col not in cols:
                dimensions[dimension] = {
                    "items": [],
                    "dimension": dimension,
                    "metric_mode": metric_mode,
                }
                continue

            conditions = list(base_conditions)
            params = list(base_params)
            for other_dim, selected_values in normalized_selections.items():
                if not selected_values or other_dim == dimension:
                    continue
                other_col = dim_to_column.get(other_dim)
                if not other_col or other_col not in cols:
                    conditions.append("1=0")
                    continue
                _append_in_condition(
                    conditions,
                    params,
                    expr=_norm_value_expr(other_col),
                    values=selected_values,
                )

            where_clause = ""
            if conditions:
                where_clause = "WHERE " + " AND ".join(conditions)
            dim_expr = _norm_value_expr(dim_col)
            sql = f"""
                SELECT
                    {dim_expr} AS dim_value,
                    SUM({movein_expr}) AS movein_qty,
                    SUM({reject_expr}) AS reject_total_qty,
                    SUM({defect_expr}) AS defect_qty,
                    {lot_expr} AS lot_count,
                    SUM({metric_expr}) AS metric_value
                FROM reject_src
                {where_clause}
                GROUP BY 1
                HAVING SUM({metric_expr}) > 0
                ORDER BY metric_value DESC
            """
            rows = conn.execute(sql, params).fetchall()
            items = _build_dimension_items(rows)
            items = _apply_pareto_scope(items, pareto_scope)
            if pareto_display_scope == "top20" and dimension in top20_set:
                items = items[:20]
            dimensions[dimension] = {
                "items": items,
                "dimension": dimension,
                "metric_mode": metric_mode,
            }

        result = {
            "dimensions": dimensions,
            "metric_mode": metric_mode,
            "pareto_scope": pareto_scope,
            "pareto_display_scope": pareto_display_scope,
        }
        meta = {
            "pareto_source": "cache_sql",
            "pareto_runtime": "duckdb",
            "pareto_runtime_path": "spool",
            "pareto_sql_latency_s": round(time.time() - started_at, 3),
        }
        return result, meta
    except Exception as exc:
        logger.warning("cache-sql batch-pareto failed (query_id=%s): %s", query_id, exc)
        return None, {
            "pareto_source": "legacy",
            "pareto_sql_fallback_reason": SQL_FALLBACK_RUNTIME_ERROR,
        }
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def try_compute_view_from_spool(
    *,
    query_id: str,
    namespace: str,
    packages: Optional[List[str]],
    workcenter_groups: Optional[List[str]],
    reasons: Optional[List[str]],
    metric_filter: str,
    trend_dates: Optional[List[str]],
    detail_reason: Optional[str],
    pareto_dimension: Optional[str],
    pareto_values: Optional[List[str]],
    pareto_selections: Optional[Dict[str, List[str]]],
    page: int,
    per_page: int,
    include_excluded_scrap: bool,
    exclude_material_scrap: bool,
    exclude_pb_diode: bool,
    dim_to_column: Dict[str, str],
) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
    if not _CACHE_SQL_ENABLED or not _CACHE_SQL_VIEW_ENABLED:
        return None, {"view_sql_fallback_reason": SQL_FALLBACK_DISABLED}
    try:
        import duckdb  # type: ignore
    except Exception:
        return None, {"view_sql_fallback_reason": SQL_FALLBACK_DEP_MISSING}

    parquet_path = get_spool_file_path(namespace, query_id)
    if not parquet_path:
        return None, {"view_sql_fallback_reason": SQL_FALLBACK_SPOOL_MISS}

    started_at = time.time()
    conn = None
    try:
        conn = duckdb.connect(database=":memory:")
        _attach_spool_source_view(conn, parquet_path)
        cols = _available_columns(conn)
        if not cols:
            return None, {"view_sql_fallback_reason": SQL_FALLBACK_RUNTIME_ERROR}

        base_conditions, base_params = _build_base_filters(
            cols=cols,
            include_excluded_scrap=include_excluded_scrap,
            exclude_material_scrap=exclude_material_scrap,
            exclude_pb_diode=exclude_pb_diode,
            packages=packages,
            workcenter_groups=workcenter_groups,
            reasons=reasons,
            trend_dates=None,
            metric_filter=metric_filter,
        )

        where_clause = "WHERE " + " AND ".join(base_conditions) if base_conditions else ""
        movein_expr = 'SUM(COALESCE("MOVEIN_QTY", 0))'
        reject_expr = 'SUM(COALESCE("REJECT_TOTAL_QTY", 0))'
        defect_expr = 'SUM(COALESCE("DEFECT_QTY", 0))'
        lot_expr = 'COUNT(DISTINCT "CONTAINERID")' if "CONTAINERID" in cols else "0"
        wo_expr = 'SUM(COALESCE("AFFECTED_WORKORDER_COUNT", 0))' if "AFFECTED_WORKORDER_COUNT" in cols else "0"
        reason_expr = _norm_value_expr("LOSSREASONNAME") if "LOSSREASONNAME" in cols else "'(未填寫)'"
        day_expr = (
            'strftime(CAST("TXN_DAY" AS DATE), \'%Y-%m-%d\')'
            if "TXN_DAY" in cols
            else "''"
        )
        analytics_sql = f"""
            SELECT
                {day_expr} AS bucket_date,
                {reason_expr} AS reason,
                {movein_expr} AS MOVEIN_QTY,
                {reject_expr} AS REJECT_TOTAL_QTY,
                {defect_expr} AS DEFECT_QTY,
                {lot_expr} AS AFFECTED_LOT_COUNT,
                {wo_expr} AS AFFECTED_WORKORDER_COUNT
            FROM reject_src
            {where_clause}
            GROUP BY 1, 2
            ORDER BY 1, 2
        """
        analytics_rows = _fetch_dict_rows(conn, analytics_sql, base_params)
        analytics_raw = [
            {
                "bucket_date": _normalize_text(row.get("bucket_date")),
                "reason": _normalize_text(row.get("reason")) or "(未填寫)",
                "MOVEIN_QTY": _as_int(row.get("MOVEIN_QTY")),
                "REJECT_TOTAL_QTY": _as_int(row.get("REJECT_TOTAL_QTY")),
                "DEFECT_QTY": _as_int(row.get("DEFECT_QTY")),
                "AFFECTED_LOT_COUNT": _as_int(row.get("AFFECTED_LOT_COUNT")),
                "AFFECTED_WORKORDER_COUNT": _as_int(row.get("AFFECTED_WORKORDER_COUNT")),
            }
            for row in analytics_rows
        ]
        summary = _build_summary_from_analytics(analytics_raw)

        detail_conditions = list(base_conditions)
        detail_params = list(base_params)
        if trend_dates and "TXN_DAY" in cols:
            trend_values = [_normalize_text(v) for v in trend_dates if _normalize_text(v)]
            if trend_values:
                placeholders = ", ".join("?" for _ in trend_values)
                detail_conditions.append(
                    f"strftime(CAST(\"TXN_DAY\" AS DATE), '%Y-%m-%d') IN ({placeholders})"
                )
                detail_params.extend(trend_values)
        if detail_reason and "LOSSREASONNAME" in cols:
            detail_conditions.append(f"{_norm_value_expr('LOSSREASONNAME')} = ?")
            detail_params.append(_normalize_text(detail_reason))
        _apply_detail_pareto_conditions(
            detail_conditions,
            detail_params,
            cols=cols,
            dim_to_column=dim_to_column,
            pareto_dimension=pareto_dimension,
            pareto_values=pareto_values,
            pareto_selections=pareto_selections,
        )

        detail_where = "WHERE " + " AND ".join(detail_conditions) if detail_conditions else ""
        count_sql = f"SELECT COUNT(*) AS total FROM reject_src {detail_where}"
        total_rows = _fetch_dict_rows(conn, count_sql, detail_params)
        total = _as_int(total_rows[0].get("total")) if total_rows else 0

        page = max(int(page or 1), 1)
        per_page = min(max(int(per_page or 50), 1), 200)
        total_pages = max((total + per_page - 1) // per_page, 1)
        offset = (page - 1) * per_page

        detail_columns = [
            "TXN_TIME",
            "TXN_DAY",
            "TXN_MONTH",
            "WORKCENTER_GROUP",
            "WORKCENTERNAME",
            "SPECNAME",
            "WORKFLOWNAME",
            "EQUIPMENTNAME",
            "PRODUCTLINENAME",
            "PJ_TYPE",
            "CONTAINERNAME",
            "PJ_FUNCTION",
            "PRODUCTNAME",
            "LOSSREASONNAME",
            "LOSSREASON_CODE",
            "REJECTCOMMENT",
            "MOVEIN_QTY",
            "REJECT_QTY",
            "STANDBY_QTY",
            "QTYTOPROCESS_QTY",
            "INPROCESS_QTY",
            "PROCESSED_QTY",
            "REJECT_TOTAL_QTY",
            "DEFECT_QTY",
            "REJECT_RATE_PCT",
            "DEFECT_RATE_PCT",
            "REJECT_SHARE_PCT",
            "AFFECTED_WORKORDER_COUNT",
        ]
        select_expr = ", ".join(
            f'{_qid(col)} AS {_qid(col)}' if col in cols else f"NULL AS {_qid(col)}"
            for col in detail_columns
        )
        sort_clause = _detail_sort_clause(cols)
        detail_sql = f"""
            SELECT {select_expr}
            FROM reject_src
            {detail_where}
            {sort_clause}
            LIMIT ? OFFSET ?
        """
        detail_rows = _fetch_dict_rows(conn, detail_sql, [*detail_params, per_page, offset])
        detail_items = [_detail_item_from_row(row) for row in detail_rows]

        return {
            "analytics_raw": analytics_raw,
            "summary": summary,
            "detail": {
                "items": detail_items,
                "pagination": {
                    "page": 1 if total == 0 else page,
                    "perPage": per_page,
                    "total": total,
                    "totalPages": total_pages,
                },
            },
        }, {
            "view_source": "cache_sql",
            "view_runtime": "duckdb",
            "view_runtime_path": "spool",
            "view_sql_analytics_rows": len(analytics_raw),
            "view_sql_detail_total": total,
            "view_sql_latency_s": round(time.time() - started_at, 3),
        }
    except Exception as exc:
        logger.warning("cache-sql view failed (query_id=%s): %s", query_id, exc)
        return None, {"view_sql_fallback_reason": SQL_FALLBACK_RUNTIME_ERROR}
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def try_iter_export_rows_from_spool(
    *,
    query_id: str,
    namespace: str,
    packages: Optional[List[str]],
    workcenter_groups: Optional[List[str]],
    reasons: Optional[List[str]],
    metric_filter: str,
    trend_dates: Optional[List[str]],
    detail_reason: Optional[str],
    pareto_dimension: Optional[str],
    pareto_values: Optional[List[str]],
    pareto_selections: Optional[Dict[str, List[str]]],
    include_excluded_scrap: bool,
    exclude_material_scrap: bool,
    exclude_pb_diode: bool,
    dim_to_column: Dict[str, str],
    chunk_size: int = 2000,
) -> Tuple[Optional[Generator[Dict[str, Any], None, None]], Dict[str, Any]]:
    if not _CACHE_SQL_ENABLED or not _CACHE_SQL_EXPORT_ENABLED:
        return None, {"export_sql_fallback_reason": SQL_FALLBACK_DISABLED}
    try:
        import duckdb  # type: ignore
    except Exception:
        return None, {"export_sql_fallback_reason": SQL_FALLBACK_DEP_MISSING}

    parquet_path = get_spool_file_path(namespace, query_id)
    if not parquet_path:
        return None, {"export_sql_fallback_reason": SQL_FALLBACK_SPOOL_MISS}

    started_at = time.time()
    conn = None
    try:
        conn = duckdb.connect(database=":memory:")
        _attach_spool_source_view(conn, parquet_path)
        cols = _available_columns(conn)
        if not cols:
            return None, {"export_sql_fallback_reason": SQL_FALLBACK_RUNTIME_ERROR}

        conditions, params = _build_base_filters(
            cols=cols,
            include_excluded_scrap=include_excluded_scrap,
            exclude_material_scrap=exclude_material_scrap,
            exclude_pb_diode=exclude_pb_diode,
            packages=packages,
            workcenter_groups=workcenter_groups,
            reasons=reasons,
            trend_dates=None,
            metric_filter=metric_filter,
        )
        if trend_dates and "TXN_DAY" in cols:
            trend_values = [_normalize_text(v) for v in trend_dates if _normalize_text(v)]
            if trend_values:
                placeholders = ", ".join("?" for _ in trend_values)
                conditions.append(
                    f"strftime(CAST(\"TXN_DAY\" AS DATE), '%Y-%m-%d') IN ({placeholders})"
                )
                params.extend(trend_values)
        if detail_reason and "LOSSREASONNAME" in cols:
            conditions.append(f"{_norm_value_expr('LOSSREASONNAME')} = ?")
            params.append(_normalize_text(detail_reason))
        _apply_detail_pareto_conditions(
            conditions,
            params,
            cols=cols,
            dim_to_column=dim_to_column,
            pareto_dimension=pareto_dimension,
            pareto_values=pareto_values,
            pareto_selections=pareto_selections,
        )

        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
        detail_columns = [
            "TXN_TIME",
            "TXN_DAY",
            "WORKCENTER_GROUP",
            "WORKCENTERNAME",
            "SPECNAME",
            "WORKFLOWNAME",
            "EQUIPMENTNAME",
            "PRODUCTLINENAME",
            "PJ_TYPE",
            "CONTAINERNAME",
            "PJ_FUNCTION",
            "PRODUCTNAME",
            "LOSSREASONNAME",
            "REJECTCOMMENT",
            "MOVEIN_QTY",
            "REJECT_QTY",
            "STANDBY_QTY",
            "QTYTOPROCESS_QTY",
            "INPROCESS_QTY",
            "PROCESSED_QTY",
            "REJECT_TOTAL_QTY",
            "DEFECT_QTY",
        ]
        select_expr = ", ".join(
            f'{_qid(col)} AS {_qid(col)}' if col in cols else f"NULL AS {_qid(col)}"
            for col in detail_columns
        )
        sort_clause = _detail_sort_clause(cols)
        sql = f"""
            SELECT {select_expr}
            FROM reject_src
            {where_clause}
            {sort_clause}
        """
        cursor = conn.execute(sql, params)
        query_latency_s = round(time.time() - started_at, 3)
        columns = [desc[0] for desc in (cursor.description or [])]

        def _row_iter() -> Generator[Dict[str, Any], None, None]:
            emitted_rows = 0
            try:
                while True:
                    batch = cursor.fetchmany(max(int(chunk_size), 1))
                    if not batch:
                        break
                    for raw in batch:
                        row = dict(zip(columns, raw))
                        emitted_rows += 1
                        yield _export_row_from_row(row)
            finally:
                total_latency_s = round(time.time() - started_at, 3)
                logger.info(
                    "cache-sql export stream finished (query_id=%s, rows=%d, query_latency_s=%.3f, total_latency_s=%.3f)",
                    query_id,
                    emitted_rows,
                    query_latency_s,
                    total_latency_s,
                )
                try:
                    conn.close()
                except Exception:
                    pass

        return _row_iter(), {
            "export_source": "cache_sql",
            "export_runtime": "duckdb",
            "export_runtime_path": "spool",
            "export_sql_query_latency_s": query_latency_s,
        }
    except Exception as exc:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
        logger.warning("cache-sql export failed (query_id=%s): %s", query_id, exc)
        return None, {"export_sql_fallback_reason": SQL_FALLBACK_RUNTIME_ERROR}
