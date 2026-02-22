# -*- coding: utf-8 -*-
"""Service layer for reject-history page APIs."""

from __future__ import annotations

import csv
import io
import logging
from datetime import date, datetime
from typing import Any, Dict, Generator, Iterable, Optional

import pandas as pd

from mes_dashboard.core.database import read_sql_df
from mes_dashboard.services.filter_cache import get_workcenter_groups
from mes_dashboard.services.scrap_reason_exclusion_cache import get_excluded_reasons
from mes_dashboard.sql import QueryBuilder, SQLLoader

logger = logging.getLogger("mes_dashboard.reject_history_service")

MAX_QUERY_DAYS = 730
VALID_GRANULARITY = {"day", "week", "month"}
VALID_METRIC_MODE = {"reject_total", "defect"}
MATERIAL_REASON_OPTION = "原物料報廢"


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _validate_range(start_date: str, end_date: str) -> None:
    start = _parse_date(start_date)
    end = _parse_date(end_date)
    if end < start:
        raise ValueError("end_date 不可早於 start_date")
    if (end - start).days > MAX_QUERY_DAYS:
        raise ValueError(f"日期範圍不可超過 {MAX_QUERY_DAYS} 天")


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _as_int(value: Any) -> int:
    if value is None:
        return 0
    try:
        if pd.isna(value):
            return 0
    except Exception:
        pass
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _as_float(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        if pd.isna(value):
            return 0.0
    except Exception:
        pass
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _to_date_str(value: Any) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime().strftime("%Y-%m-%d")
    text = _normalize_text(value)
    if not text:
        return ""
    try:
        return pd.to_datetime(text).strftime("%Y-%m-%d")
    except Exception:
        return text


def _date_bucket_expr(granularity: str) -> str:
    if granularity == "week":
        return "TRUNC(b.TXN_DAY, 'IW')"
    if granularity == "month":
        return "TRUNC(b.TXN_DAY, 'MM')"
    return "TRUNC(b.TXN_DAY)"


def _metric_column(metric_mode: str) -> str:
    if metric_mode == "defect":
        return "b.DEFECT_QTY"
    return "b.REJECT_TOTAL_QTY"


def _load_sql(name: str) -> str:
    return SQLLoader.load(f"reject_history/{name}")


def _base_query_sql(variant: str = "") -> str:
    sql_name = "performance_daily_lot" if variant == "lot" else "performance_daily"
    sql = _load_sql(sql_name).strip().rstrip(";")
    # Strip leading comment/blank lines so WITH parsing can detect the first SQL token.
    lines = sql.splitlines()
    first_sql_line = 0
    for index, line in enumerate(lines):
        token = line.strip()
        if not token or token.startswith("--"):
            continue
        first_sql_line = index
        break
    return "\n".join(lines[first_sql_line:]).strip()


def _split_with_query(sql: str) -> tuple[str, str] | None:
    """Split a top-level WITH query into (cte_segment, final_select)."""
    text = (sql or "").strip()
    if not text.lower().startswith("with "):
        return None

    depth = 0
    in_string = False
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "'":
            if in_string and i + 1 < len(text) and text[i + 1] == "'":
                i += 2
                continue
            in_string = not in_string
            i += 1
            continue
        if in_string:
            i += 1
            continue

        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(depth - 1, 0)
        elif depth == 0:
            head = text[i : i + 6]
            if head.lower() == "select":
                prev_ok = i == 0 or not (text[i - 1].isalnum() or text[i - 1] == "_")
                next_idx = i + 6
                next_ok = next_idx >= len(text) or not (
                    text[next_idx].isalnum() or text[next_idx] == "_"
                )
                if prev_ok and next_ok:
                    cte_segment = text[5:i].strip().rstrip(",")
                    final_select = text[i:].strip()
                    if cte_segment and final_select:
                        return cte_segment, final_select
                    return None
        i += 1
    return None


def _base_with_cte_sql(alias: str = "base", variant: str = "") -> str:
    base_sql = _base_query_sql(variant)
    split = _split_with_query(base_sql)
    if split is None:
        return f"WITH {alias} AS (\n{base_sql}\n)"
    cte_segment, final_select = split
    return f"WITH {cte_segment},\n{alias} AS (\n{final_select}\n)"


def _build_where_clause(
    *,
    workcenter_groups: Optional[list[str]] = None,
    packages: Optional[list[str]] = None,
    reasons: Optional[list[str]] = None,
    categories: Optional[list[str]] = None,
    include_excluded_scrap: bool = False,
    exclude_material_scrap: bool = True,
    exclude_pb_diode: bool = True,
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    builder = QueryBuilder()

    normalized_wc_groups = sorted({_normalize_text(v) for v in (workcenter_groups or []) if _normalize_text(v)})
    normalized_packages = sorted({_normalize_text(v) for v in (packages or []) if _normalize_text(v)})
    normalized_reasons = sorted({_normalize_text(v) for v in (reasons or []) if _normalize_text(v)})
    material_reason_selected = MATERIAL_REASON_OPTION in normalized_reasons
    reason_name_filters = [value for value in normalized_reasons if value != MATERIAL_REASON_OPTION]
    normalized_categories = sorted({_normalize_text(v) for v in (categories or []) if _normalize_text(v)})

    if normalized_wc_groups:
        builder.add_in_condition("b.WORKCENTER_GROUP", normalized_wc_groups)
    if normalized_packages:
        builder.add_in_condition("b.PRODUCTLINENAME", normalized_packages)
    if reason_name_filters:
        builder.add_in_condition("b.LOSSREASONNAME", reason_name_filters)
    if material_reason_selected:
        builder.add_condition("UPPER(NVL(TRIM(b.SCRAP_OBJECTTYPE), '-')) = 'MATERIAL'")
    material_exclusion_applied = False
    if exclude_material_scrap and not material_reason_selected:
        builder.add_condition("UPPER(NVL(TRIM(b.SCRAP_OBJECTTYPE), '-')) <> 'MATERIAL'")
        material_exclusion_applied = True
    pb_diode_exclusion_applied = False
    if exclude_pb_diode and "PB_Diode" not in normalized_packages:
        builder.add_condition("b.PRODUCTLINENAME <> 'PB_Diode'")
        pb_diode_exclusion_applied = True
    if normalized_categories:
        builder.add_in_condition("b.REJECTCATEGORYNAME", normalized_categories)

    exclusions_applied = False
    excluded_reason_codes = []
    reason_name_prefix_policy_applied = False
    if not include_excluded_scrap:
        excluded_reason_codes = sorted(get_excluded_reasons())
        reason_name_prefix_policy_applied = True
        if excluded_reason_codes:
            exclusions_applied = True
            # Support exclusion matching by both normalized reason code and full reason text.
            builder.add_not_in_condition(
                "UPPER(NVL(TRIM(b.LOSSREASON_CODE), '-'))",
                excluded_reason_codes,
            )
            builder.add_not_in_condition(
                "UPPER(NVL(TRIM(b.LOSSREASONNAME), '-'))",
                excluded_reason_codes,
            )
        # Exclude reason labels that are not "NNN_*", and always exclude XXX_/ZZZ_ prefixes.
        builder.add_condition(
            "REGEXP_LIKE(UPPER(NVL(TRIM(b.LOSSREASONNAME), '')), '^[0-9]{3}_')"
        )
        builder.add_condition(
            "NOT REGEXP_LIKE(UPPER(NVL(TRIM(b.LOSSREASONNAME), '')), '^(XXX|ZZZ)_')"
        )
        exclusions_applied = True

    where_clause, params = builder.build_where_only()
    meta = {
        "include_excluded_scrap": bool(include_excluded_scrap),
        "exclusion_applied": exclusions_applied,
        "reason_name_prefix_policy_applied": reason_name_prefix_policy_applied,
        "exclude_material_scrap": bool(exclude_material_scrap),
        "material_exclusion_applied": material_exclusion_applied,
        "excluded_reason_count": len(excluded_reason_codes),
        "workcenter_group_count": len(normalized_wc_groups),
        "package_filter_count": len(normalized_packages),
        "reason_filter_count": len(reason_name_filters),
        "material_reason_selected": material_reason_selected,
        "exclude_pb_diode": bool(exclude_pb_diode),
        "pb_diode_exclusion_applied": pb_diode_exclusion_applied,
    }
    return where_clause, params, meta


def _prepare_sql(
    name: str,
    *,
    where_clause: str = "",
    bucket_expr: str = "",
    metric_column: str = "",
    base_variant: str = "",
) -> str:
    sql = _load_sql(name)
    sql = sql.replace("{{ BASE_QUERY }}", _base_query_sql(base_variant))
    sql = sql.replace("{{ BASE_WITH_CTE }}", _base_with_cte_sql("base", base_variant))
    sql = sql.replace("{{ WHERE_CLAUSE }}", where_clause or "")
    sql = sql.replace("{{ BUCKET_EXPR }}", bucket_expr or "TRUNC(b.TXN_DAY)")
    sql = sql.replace("{{ METRIC_COLUMN }}", metric_column or "b.REJECT_TOTAL_QTY")
    return sql


def _common_params(start_date: str, end_date: str, extra: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    params = {"start_date": start_date, "end_date": end_date}
    if extra:
        params.update(extra)
    return params


def _list_to_csv(
    rows: Iterable[dict[str, Any]],
    headers: list[str],
) -> Generator[str, None, None]:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=headers)
    writer.writeheader()
    yield buffer.getvalue()
    buffer.seek(0)
    buffer.truncate(0)

    for row in rows:
        writer.writerow(row)
        yield buffer.getvalue()
        buffer.seek(0)
        buffer.truncate(0)


def get_filter_options(
    *,
    start_date: str,
    end_date: str,
    include_excluded_scrap: bool = False,
    exclude_material_scrap: bool = True,
    exclude_pb_diode: bool = True,
) -> dict[str, Any]:
    """Return workcenter-group / package / reason options (single DB query)."""
    _validate_range(start_date, end_date)

    where_clause, params, meta = _build_where_clause(
        include_excluded_scrap=include_excluded_scrap,
        exclude_material_scrap=exclude_material_scrap,
        exclude_pb_diode=exclude_pb_diode,
    )
    sql = _prepare_sql("filter_options", where_clause=where_clause)
    df = read_sql_df(sql, _common_params(start_date, end_date, params))

    reasons: list[str] = []
    packages: list[str] = []
    has_material_option = False

    if df is not None and not df.empty:
        reasons = sorted({
            _normalize_text(v)
            for v in df["REASON"].dropna()
            if _normalize_text(v)
        })
        packages = sorted({
            _normalize_text(v)
            for v in df["PACKAGE"].dropna()
            if _normalize_text(v)
        })
        if "SCRAP_OBJECTTYPE" in df.columns:
            has_material_option = (
                df["SCRAP_OBJECTTYPE"]
                .apply(lambda v: str(v or "").strip().upper())
                .eq("MATERIAL")
                .any()
            )

    groups_raw = get_workcenter_groups() or []
    workcenter_groups = []
    for item in groups_raw:
        name = _normalize_text(item.get("name"))
        if not name:
            continue
        workcenter_groups.append(
            {
                "name": name,
                "sequence": _as_int(item.get("sequence")),
            }
        )

    reason_options = sorted(set(reasons))
    if has_material_option and MATERIAL_REASON_OPTION not in reason_options:
        reason_options.append(MATERIAL_REASON_OPTION)
    return {
        "workcenter_groups": workcenter_groups,
        "packages": sorted(set(packages)),
        "reasons": reason_options,
        "meta": meta,
    }


def query_summary(
    *,
    start_date: str,
    end_date: str,
    workcenter_groups: Optional[list[str]] = None,
    packages: Optional[list[str]] = None,
    reasons: Optional[list[str]] = None,
    categories: Optional[list[str]] = None,
    include_excluded_scrap: bool = False,
    exclude_material_scrap: bool = True,
    exclude_pb_diode: bool = True,
) -> dict[str, Any]:
    _validate_range(start_date, end_date)
    where_clause, params, meta = _build_where_clause(
        workcenter_groups=workcenter_groups,
        packages=packages,
        reasons=reasons,
        categories=categories,
        include_excluded_scrap=include_excluded_scrap,
        exclude_material_scrap=exclude_material_scrap,
        exclude_pb_diode=exclude_pb_diode,
    )
    sql = _prepare_sql("summary", where_clause=where_clause)
    df = read_sql_df(sql, _common_params(start_date, end_date, params))
    row = (df.iloc[0] if df is not None and not df.empty else {})

    return {
        "MOVEIN_QTY": _as_int(row.get("MOVEIN_QTY")),
        "REJECT_TOTAL_QTY": _as_int(row.get("REJECT_TOTAL_QTY")),
        "DEFECT_QTY": _as_int(row.get("DEFECT_QTY")),
        "REJECT_RATE_PCT": round(_as_float(row.get("REJECT_RATE_PCT")), 4),
        "DEFECT_RATE_PCT": round(_as_float(row.get("DEFECT_RATE_PCT")), 4),
        "REJECT_SHARE_PCT": round(_as_float(row.get("REJECT_SHARE_PCT")), 4),
        "AFFECTED_LOT_COUNT": _as_int(row.get("AFFECTED_LOT_COUNT")),
        "AFFECTED_WORKORDER_COUNT": _as_int(row.get("AFFECTED_WORKORDER_COUNT")),
        "meta": meta,
    }


def query_trend(
    *,
    start_date: str,
    end_date: str,
    granularity: str = "day",
    workcenter_groups: Optional[list[str]] = None,
    packages: Optional[list[str]] = None,
    reasons: Optional[list[str]] = None,
    categories: Optional[list[str]] = None,
    include_excluded_scrap: bool = False,
    exclude_material_scrap: bool = True,
    exclude_pb_diode: bool = True,
) -> dict[str, Any]:
    _validate_range(start_date, end_date)
    normalized_granularity = _normalize_text(granularity).lower() or "day"
    if normalized_granularity not in VALID_GRANULARITY:
        raise ValueError("Invalid granularity. Use day, week, or month")

    where_clause, params, meta = _build_where_clause(
        workcenter_groups=workcenter_groups,
        packages=packages,
        reasons=reasons,
        categories=categories,
        include_excluded_scrap=include_excluded_scrap,
        exclude_material_scrap=exclude_material_scrap,
        exclude_pb_diode=exclude_pb_diode,
    )
    sql = _prepare_sql(
        "trend",
        where_clause=where_clause,
        bucket_expr=_date_bucket_expr(normalized_granularity),
    )
    df = read_sql_df(sql, _common_params(start_date, end_date, params))
    items = []
    if df is not None and not df.empty:
        for _, row in df.iterrows():
            items.append(
                {
                    "bucket_date": _to_date_str(row.get("BUCKET_DATE")),
                    "MOVEIN_QTY": _as_int(row.get("MOVEIN_QTY")),
                    "REJECT_TOTAL_QTY": _as_int(row.get("REJECT_TOTAL_QTY")),
                    "DEFECT_QTY": _as_int(row.get("DEFECT_QTY")),
                    "REJECT_RATE_PCT": round(_as_float(row.get("REJECT_RATE_PCT")), 4),
                    "DEFECT_RATE_PCT": round(_as_float(row.get("DEFECT_RATE_PCT")), 4),
                }
            )

    return {
        "items": items,
        "granularity": normalized_granularity,
        "meta": meta,
    }


def query_reason_pareto(
    *,
    start_date: str,
    end_date: str,
    metric_mode: str = "reject_total",
    pareto_scope: str = "top80",
    workcenter_groups: Optional[list[str]] = None,
    packages: Optional[list[str]] = None,
    reasons: Optional[list[str]] = None,
    categories: Optional[list[str]] = None,
    include_excluded_scrap: bool = False,
    exclude_material_scrap: bool = True,
    exclude_pb_diode: bool = True,
) -> dict[str, Any]:
    _validate_range(start_date, end_date)
    normalized_metric = _normalize_text(metric_mode).lower() or "reject_total"
    if normalized_metric not in VALID_METRIC_MODE:
        raise ValueError("Invalid metric_mode. Use reject_total or defect")

    normalized_scope = _normalize_text(pareto_scope).lower() or "top80"
    if normalized_scope not in {"top80", "all"}:
        raise ValueError("Invalid pareto_scope. Use top80 or all")

    where_clause, params, meta = _build_where_clause(
        workcenter_groups=workcenter_groups,
        packages=packages,
        reasons=reasons,
        categories=categories,
        include_excluded_scrap=include_excluded_scrap,
        exclude_material_scrap=exclude_material_scrap,
        exclude_pb_diode=exclude_pb_diode,
    )
    sql = _prepare_sql(
        "reason_pareto",
        where_clause=where_clause,
        metric_column=_metric_column(normalized_metric),
    )
    df = read_sql_df(sql, _common_params(start_date, end_date, params))
    all_items = []
    if df is not None and not df.empty:
        for _, row in df.iterrows():
            all_items.append(
                {
                    "reason": _normalize_text(row.get("REASON")) or "(未填寫)",
                    "metric_value": _as_float(row.get("METRIC_VALUE")),
                    "MOVEIN_QTY": _as_int(row.get("MOVEIN_QTY")),
                    "REJECT_TOTAL_QTY": _as_int(row.get("REJECT_TOTAL_QTY")),
                    "DEFECT_QTY": _as_int(row.get("DEFECT_QTY")),
                    "count": _as_int(row.get("AFFECTED_LOT_COUNT")),
                    "pct": round(_as_float(row.get("PCT")), 4),
                    "cumPct": round(_as_float(row.get("CUM_PCT")), 4),
                }
            )

    items = list(all_items)
    if normalized_scope == "top80" and items:
        top_items = [item for item in items if _as_float(item.get("cumPct")) <= 80.0]
        # Keep strict top-80% behavior, but still return one row when first item already exceeds 80%.
        if not top_items:
            top_items = [items[0]]
        items = top_items

    return {
        "items": items,
        "metric_mode": normalized_metric,
        "pareto_scope": normalized_scope,
        "meta": {
            **meta,
            "total_items_after_filter": len(all_items),
            "displayed_items": len(items),
        },
    }


def query_list(
    *,
    start_date: str,
    end_date: str,
    page: int = 1,
    per_page: int = 50,
    workcenter_groups: Optional[list[str]] = None,
    packages: Optional[list[str]] = None,
    reasons: Optional[list[str]] = None,
    categories: Optional[list[str]] = None,
    include_excluded_scrap: bool = False,
    exclude_material_scrap: bool = True,
    exclude_pb_diode: bool = True,
) -> dict[str, Any]:
    _validate_range(start_date, end_date)

    page = max(int(page or 1), 1)
    per_page = min(max(int(per_page or 50), 1), 200)
    offset = (page - 1) * per_page

    where_clause, params, meta = _build_where_clause(
        workcenter_groups=workcenter_groups,
        packages=packages,
        reasons=reasons,
        categories=categories,
        include_excluded_scrap=include_excluded_scrap,
        exclude_material_scrap=exclude_material_scrap,
        exclude_pb_diode=exclude_pb_diode,
    )
    sql = _prepare_sql("list", where_clause=where_clause, base_variant="lot")
    query_params = _common_params(
        start_date,
        end_date,
        {
            **params,
            "offset": offset,
            "limit": per_page,
        },
    )
    df = read_sql_df(sql, query_params)

    items = []
    total = 0
    if df is not None and not df.empty:
        total = _as_int(df.iloc[0].get("TOTAL_COUNT"))
        for _, row in df.iterrows():
            items.append(
                {
                    "TXN_DAY": _to_date_str(row.get("TXN_DAY")),
                    "TXN_MONTH": _normalize_text(row.get("TXN_MONTH")),
                    "WORKCENTER_GROUP": _normalize_text(row.get("WORKCENTER_GROUP")),
                    "WORKCENTERNAME": _normalize_text(row.get("WORKCENTERNAME")),
                    "SPECNAME": _normalize_text(row.get("SPECNAME")),
                    "PRODUCTLINENAME": _normalize_text(row.get("PRODUCTLINENAME")),
                    "PJ_TYPE": _normalize_text(row.get("PJ_TYPE")),
                    "CONTAINERNAME": _normalize_text(row.get("CONTAINERNAME")),
                    "PJ_FUNCTION": _normalize_text(row.get("PJ_FUNCTION")),
                    "PRODUCTNAME": _normalize_text(row.get("PRODUCTNAME")),
                    "LOSSREASONNAME": _normalize_text(row.get("LOSSREASONNAME")),
                    "LOSSREASON_CODE": _normalize_text(row.get("LOSSREASON_CODE")),
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
            )

    total_pages = max((total + per_page - 1) // per_page, 1) if total else 1
    return {
        "items": items,
        "pagination": {
            "page": page,
            "perPage": per_page,
            "total": total,
            "totalPages": total_pages,
        },
        "meta": meta,
    }


def export_csv(
    *,
    start_date: str,
    end_date: str,
    workcenter_groups: Optional[list[str]] = None,
    packages: Optional[list[str]] = None,
    reasons: Optional[list[str]] = None,
    categories: Optional[list[str]] = None,
    include_excluded_scrap: bool = False,
    exclude_material_scrap: bool = True,
    exclude_pb_diode: bool = True,
) -> Generator[str, None, None]:
    _validate_range(start_date, end_date)

    where_clause, params, _meta = _build_where_clause(
        workcenter_groups=workcenter_groups,
        packages=packages,
        reasons=reasons,
        categories=categories,
        include_excluded_scrap=include_excluded_scrap,
        exclude_material_scrap=exclude_material_scrap,
        exclude_pb_diode=exclude_pb_diode,
    )
    sql = _prepare_sql("export", where_clause=where_clause)
    df = read_sql_df(sql, _common_params(start_date, end_date, params))

    rows = []
    if df is not None and not df.empty:
        for _, row in df.iterrows():
            rows.append(
                {
                    "TXN_DAY": _to_date_str(row.get("TXN_DAY")),
                    "TXN_MONTH": _normalize_text(row.get("TXN_MONTH")),
                    "WORKCENTER_GROUP": _normalize_text(row.get("WORKCENTER_GROUP")),
                    "WORKCENTERNAME": _normalize_text(row.get("WORKCENTERNAME")),
                    "SPECNAME": _normalize_text(row.get("SPECNAME")),
                    "PRODUCTLINENAME": _normalize_text(row.get("PRODUCTLINENAME")),
                    "PJ_TYPE": _normalize_text(row.get("PJ_TYPE")),
                    "LOSSREASONNAME": _normalize_text(row.get("LOSSREASONNAME")),
                    "LOSSREASON_CODE": _normalize_text(row.get("LOSSREASON_CODE")),
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
                    "AFFECTED_LOT_COUNT": _as_int(row.get("AFFECTED_LOT_COUNT")),
                    "AFFECTED_WORKORDER_COUNT": _as_int(row.get("AFFECTED_WORKORDER_COUNT")),
                }
            )

    headers = [
        "TXN_DAY",
        "TXN_MONTH",
        "WORKCENTER_GROUP",
        "WORKCENTERNAME",
        "SPECNAME",
        "PRODUCTLINENAME",
        "PJ_TYPE",
        "LOSSREASONNAME",
        "LOSSREASON_CODE",
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
        "AFFECTED_LOT_COUNT",
        "AFFECTED_WORKORDER_COUNT",
    ]
    return _list_to_csv(rows, headers=headers)


def _derive_summary(df: pd.DataFrame) -> dict[str, Any]:
    """Aggregate analytics rows into a single summary dict."""
    if df is None or df.empty:
        return {
            "MOVEIN_QTY": 0,
            "REJECT_TOTAL_QTY": 0,
            "DEFECT_QTY": 0,
            "REJECT_RATE_PCT": 0,
            "DEFECT_RATE_PCT": 0,
            "REJECT_SHARE_PCT": 0,
            "AFFECTED_LOT_COUNT": 0,
            "AFFECTED_WORKORDER_COUNT": 0,
        }

    movein = _as_int(df["MOVEIN_QTY"].sum())
    reject_total = _as_int(df["REJECT_TOTAL_QTY"].sum())
    defect = _as_int(df["DEFECT_QTY"].sum())
    affected_lot = _as_int(df["AFFECTED_LOT_COUNT"].sum())
    affected_wo = _as_int(df["AFFECTED_WORKORDER_COUNT"].sum())

    total_scrap = reject_total + defect
    reject_rate = round((reject_total / movein * 100) if movein else 0, 4)
    defect_rate = round((defect / movein * 100) if movein else 0, 4)
    reject_share = round((reject_total / total_scrap * 100) if total_scrap else 0, 4)

    return {
        "MOVEIN_QTY": movein,
        "REJECT_TOTAL_QTY": reject_total,
        "DEFECT_QTY": defect,
        "REJECT_RATE_PCT": reject_rate,
        "DEFECT_RATE_PCT": defect_rate,
        "REJECT_SHARE_PCT": reject_share,
        "AFFECTED_LOT_COUNT": affected_lot,
        "AFFECTED_WORKORDER_COUNT": affected_wo,
    }


def _derive_trend(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Group analytics rows by BUCKET_DATE into daily trend items."""
    if df is None or df.empty:
        return []

    grouped = df.groupby("BUCKET_DATE", sort=True).agg(
        MOVEIN_QTY=("MOVEIN_QTY", "sum"),
        REJECT_TOTAL_QTY=("REJECT_TOTAL_QTY", "sum"),
        DEFECT_QTY=("DEFECT_QTY", "sum"),
    ).reset_index()

    items = []
    for _, row in grouped.iterrows():
        movein = _as_int(row["MOVEIN_QTY"])
        reject_total = _as_int(row["REJECT_TOTAL_QTY"])
        defect = _as_int(row["DEFECT_QTY"])
        items.append({
            "bucket_date": _to_date_str(row["BUCKET_DATE"]),
            "MOVEIN_QTY": movein,
            "REJECT_TOTAL_QTY": reject_total,
            "DEFECT_QTY": defect,
            "REJECT_RATE_PCT": round((reject_total / movein * 100) if movein else 0, 4),
            "DEFECT_RATE_PCT": round((defect / movein * 100) if movein else 0, 4),
        })
    return items


def _derive_pareto(df: pd.DataFrame, metric_mode: str = "reject_total") -> list[dict[str, Any]]:
    """Group analytics rows by REASON into pareto items with PCT/CUM_PCT."""
    if df is None or df.empty:
        return []

    metric_col = "REJECT_TOTAL_QTY" if metric_mode == "reject_total" else "DEFECT_QTY"

    grouped = df.groupby("REASON", sort=False).agg(
        MOVEIN_QTY=("MOVEIN_QTY", "sum"),
        REJECT_TOTAL_QTY=("REJECT_TOTAL_QTY", "sum"),
        DEFECT_QTY=("DEFECT_QTY", "sum"),
        AFFECTED_LOT_COUNT=("AFFECTED_LOT_COUNT", "sum"),
    ).reset_index()

    grouped = grouped.sort_values(metric_col, ascending=False).reset_index(drop=True)
    total_metric = _as_float(grouped[metric_col].sum())

    items = []
    cum = 0.0
    for _, row in grouped.iterrows():
        metric_value = _as_float(row[metric_col])
        pct = round((metric_value / total_metric * 100) if total_metric else 0, 4)
        cum += pct
        reason_text = _normalize_text(row["REASON"]) or "(未填寫)"
        items.append({
            "reason": reason_text,
            "metric_value": metric_value,
            "MOVEIN_QTY": _as_int(row["MOVEIN_QTY"]),
            "REJECT_TOTAL_QTY": _as_int(row["REJECT_TOTAL_QTY"]),
            "DEFECT_QTY": _as_int(row["DEFECT_QTY"]),
            "count": _as_int(row["AFFECTED_LOT_COUNT"]),
            "pct": pct,
            "cumPct": round(cum, 4),
        })
    return items


def _derive_raw_items(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Return per-(date, reason) rows for client-side re-derivation."""
    if df is None or df.empty:
        return []
    items = []
    for _, row in df.iterrows():
        items.append({
            "bucket_date": _to_date_str(row["BUCKET_DATE"]),
            "reason": _normalize_text(row["REASON"]) or "(未填寫)",
            "MOVEIN_QTY": _as_int(row["MOVEIN_QTY"]),
            "REJECT_TOTAL_QTY": _as_int(row["REJECT_TOTAL_QTY"]),
            "DEFECT_QTY": _as_int(row["DEFECT_QTY"]),
            "AFFECTED_LOT_COUNT": _as_int(row["AFFECTED_LOT_COUNT"]),
            "AFFECTED_WORKORDER_COUNT": _as_int(row["AFFECTED_WORKORDER_COUNT"]),
        })
    return items


def query_analytics(
    *,
    start_date: str,
    end_date: str,
    metric_mode: str = "reject_total",
    workcenter_groups: Optional[list[str]] = None,
    packages: Optional[list[str]] = None,
    reasons: Optional[list[str]] = None,
    categories: Optional[list[str]] = None,
    include_excluded_scrap: bool = False,
    exclude_material_scrap: bool = True,
    exclude_pb_diode: bool = True,
) -> dict[str, Any]:
    """Single DB query → summary + trend + pareto (replaces 3 separate queries)."""
    _validate_range(start_date, end_date)
    normalized_metric = _normalize_text(metric_mode).lower() or "reject_total"
    if normalized_metric not in VALID_METRIC_MODE:
        raise ValueError("Invalid metric_mode. Use reject_total or defect")

    where_clause, params, meta = _build_where_clause(
        workcenter_groups=workcenter_groups,
        packages=packages,
        reasons=reasons,
        categories=categories,
        include_excluded_scrap=include_excluded_scrap,
        exclude_material_scrap=exclude_material_scrap,
        exclude_pb_diode=exclude_pb_diode,
    )
    sql = _prepare_sql("analytics", where_clause=where_clause)
    df = read_sql_df(sql, _common_params(start_date, end_date, params))

    return {
        "summary": _derive_summary(df),
        "trend": {
            "items": _derive_trend(df),
            "granularity": "day",
        },
        "pareto": {
            "items": _derive_pareto(df, normalized_metric),
            "metric_mode": normalized_metric,
        },
        "raw_items": _derive_raw_items(df),
        "meta": meta,
    }
