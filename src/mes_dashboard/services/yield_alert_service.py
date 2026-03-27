# -*- coding: utf-8 -*-
"""Service layer for Yield Alert Center APIs."""

from __future__ import annotations

import logging
import math
import os
import re
import time
from datetime import date, datetime
from urllib.parse import urlencode

from mes_dashboard.config.workcenter_groups import get_workcenter_group
from mes_dashboard.core.database import read_sql_df_slow
from mes_dashboard.services.batch_query_engine import compute_query_hash
from mes_dashboard.services.filter_cache import get_workcenter_groups
from mes_dashboard.services.scrap_reason_exclusion_cache import get_excluded_reasons
from mes_dashboard.sql import QueryBuilder, SQLLoader

logger = logging.getLogger("mes_dashboard.yield_alert_service")

MAX_QUERY_DAYS = max(1, int(os.getenv("YIELD_ALERT_MAX_QUERY_DAYS", "730")))
DEFAULT_PAGE_SIZE = max(1, int(os.getenv("YIELD_ALERT_DEFAULT_PER_PAGE", "50")))
MAX_PAGE_SIZE = max(DEFAULT_PAGE_SIZE, int(os.getenv("YIELD_ALERT_MAX_PER_PAGE", "200")))
ALERT_CACHE_TTL_SECONDS = max(30, int(os.getenv("YIELD_ALERT_CACHE_TTL_SECONDS", "300")))
LINKAGE_WARN_UNMATCHED_RATIO = float(os.getenv("YIELD_ALERT_LINKAGE_WARN_RATIO", "0.25"))
_ORACLE_IN_MAX_EXPRESSIONS = max(
    1,
    min(int(os.getenv("YIELD_ALERT_ORACLE_IN_MAX_EXPRESSIONS", "900")), 1000),
)

VALID_GRANULARITY = {"day", "week", "month"}
VALID_SORT_FIELDS = {
    "date_bucket": "date_bucket",
    "workorder": "workorder",
    "reason_code": "reason_code",
    "package": "package",
    "type": "type",
    "scrap_qty": "scrap_qty",
    "yield_pct": "yield_pct",
    "risk_score": "risk_score",
}

_DETAIL_FILTER_COLUMNS = {
    "departments": "NVL(TRIM(d.DEPARTMENT_NAME), '(NA)')",
    "lines": "NVL(TRIM(d.LINE), '(NA)')",
    "packages": "NVL(TRIM(d.PACKAGE), '(NA)')",
    "types": "NVL(TRIM(d.TYPE), '(NA)')",
    "functions": "NVL(TRIM(d.FUNCTION), '(NA)')",
    "operations": "TO_CHAR(NVL(d.OPERATION_SEQ_NUM, -1))",
}

_SUMMARY_FILTER_COLUMNS = {
    "departments": "NVL(TRIM(m.DEPARTMENT_NAME), '(NA)')",
}

_SUMMARY_DETAIL_FILTER_COLUMNS = {
    "departments": "NVL(TRIM(d.DEPARTMENT_NAME), '(NA)')",
}

_REASON_ALIAS_MAP = {
    "NG品": "NG品",
    "NG": "NG品",
    "N/A": "UNMAPPED_REASON",
    "NA": "UNMAPPED_REASON",
    "-": "UNMAPPED_REASON",
    "(UNMAPPED)": "UNMAPPED_REASON",
    "UNMAPPED": "UNMAPPED_REASON",
}
_UNMAPPED_REASON_CODE = "UNMAPPED_REASON"
_YIELD_WORKCENTER_GROUP_ORDER = [
    "切割",
    "焊接_DB",
    "焊接_WB",
    "成型",
    "去膠",
    "水吹砂",
    "電鍍",
    "移印",
    "切彎腳",
    "TMTT",
    "品檢",
    "FQC",
]

_WAFER_SORT_DEPT_GROUPS = frozenset(["切割"])
_ASSEMBLY_DEPT_GROUPS = frozenset([
    "焊接_DB", "焊接_WB",
    "成型", "去膠", "水吹砂", "電鍍", "移印", "切彎腳",
    "TMTT", "FQC", "品檢",
])


def _normalize_process_category(dept_group: str) -> str:
    if dept_group in _WAFER_SORT_DEPT_GROUPS:
        return "WAFER_SORT"
    if dept_group in _ASSEMBLY_DEPT_GROUPS:
        return "ASSEMBLY"
    return "OTHER"


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def validate_date_range(start_date: str, end_date: str) -> tuple[date, date]:
    start = _parse_date(start_date)
    end = _parse_date(end_date)
    if end < start:
        raise ValueError("結束日期必須大於起始日期")
    if (end - start).days + 1 > MAX_QUERY_DAYS:
        raise ValueError(f"查詢範圍不可超過 {MAX_QUERY_DAYS} 天")
    return start, end


def normalize_reason_code(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return "UNMAPPED_REASON"

    mapped = _REASON_ALIAS_MAP.get(text)
    if mapped:
        return mapped

    token = text.upper().replace("：", ":")
    token = re.sub(r"\s+", "", token)
    mapped_token = _REASON_ALIAS_MAP.get(token)
    if mapped_token:
        return mapped_token

    m = re.match(r"^([A-Z0-9]{1,10})[_\-:.].*$", token)
    if m:
        return m.group(1)

    m_num = re.match(r"^([0-9]{1,4}).*$", token)
    if m_num:
        return m_num.group(1)

    # Keep localized textual reasons as-is (e.g. NG品), otherwise fallback.
    if re.search(r"[\u4e00-\u9fffA-Z0-9]", token):
        return token[:30]
    return "UNMAPPED_REASON"


def build_canonical_key(date_bucket: str, workorder: str, reason_code: str) -> str:
    bucket = str(date_bucket or "").strip()[:10]
    wo = str(workorder or "").strip().upper() or "(NA)"
    reason = normalize_reason_code(reason_code)
    return f"{bucket}|{wo}|{reason}"


def _normalize_yield_department_group(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return "(NA)"

    upper = text.upper()
    if "切割" in text or "DIE SAW" in upper or "DICING" in upper:
        return "切割"
    if "FQC" in upper:
        return "FQC"
    if "品檢" in text or "IPQC" in upper or "OQC" in upper or "IQC" in upper:
        return "品檢"
    if "TMTT" in upper:
        return "TMTT"

    group_name, _ = get_workcenter_group(text)
    if group_name == "焊接_DW":
        return "焊接_WB"
    if group_name == "測試":
        return "TMTT"
    if group_name:
        return group_name
    return text


def expand_workcenter_groups_to_departments(workcenter_groups: list[str] | None) -> list[str]:
    if not workcenter_groups:
        return []

    expanded: list[str] = []
    seen: set[str] = set()
    for raw in workcenter_groups:
        group = str(raw or "").strip()
        if not group:
            continue
        candidates = [group]
        if group == "焊接_WB":
            candidates.append("焊接_DW")
        elif group == "TMTT":
            candidates.append("測試")
        elif group == "品檢":
            candidates.extend(["IPQC", "OQC", "IQC"])

        for candidate in candidates:
            token = str(candidate or "").strip()
            if not token or token in seen:
                continue
            seen.add(token)
            expanded.append(token)
    return expanded


def get_yield_workcenter_group_options() -> list[str]:
    options: list[str] = []
    seen: set[str] = set()
    cache_groups = get_workcenter_groups() or []
    for item in cache_groups:
        if isinstance(item, dict):
            raw_name = item.get("name")
        else:
            raw_name = item
        name = str(raw_name or "").strip()
        if not name:
            continue
        group = _normalize_yield_department_group(name)
        if group not in seen:
            seen.add(group)
            options.append(group)

    for fixed in _YIELD_WORKCENTER_GROUP_ORDER:
        if fixed not in seen:
            options.append(fixed)
            seen.add(fixed)

    return sorted(
        options,
        key=lambda group: (
            _YIELD_WORKCENTER_GROUP_ORDER.index(group)
            if group in _YIELD_WORKCENTER_GROUP_ORDER
            else 999,
            group,
        ),
    )


def _normalize_tokens(values: list[str] | None) -> list[str]:
    if not values:
        return []
    seen: set[str] = set()
    normalized: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        if text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    return normalized


def normalize_query_key_payload(payload: dict) -> dict:
    """Return deterministic payload used to compute query hash/cache key."""

    normalized: dict = {}
    for key in sorted(payload.keys()):
        value = payload[key]
        if isinstance(value, list):
            normalized[key] = sorted(_normalize_tokens([str(v) for v in value]))
        elif isinstance(value, dict):
            normalized[key] = normalize_query_key_payload(value)
        elif value is None:
            continue
        else:
            normalized[key] = value
    return normalized


def build_query_cache_key(namespace: str, payload: dict) -> str:
    canonical = normalize_query_key_payload(payload)
    return f"yield_alert:{namespace}:{compute_query_hash(canonical)}"


def _load_sql(name: str) -> str:
    return SQLLoader.load(f"yield_alert/{name}")


def _bucket_expr(granularity: str, alias: str = "m") -> str:
    if granularity == "week":
        return f"TRUNC({alias}.TXN_DATE, 'IW')"
    if granularity == "month":
        return f"TRUNC({alias}.TXN_DATE, 'MM')"
    return f"TRUNC({alias}.TXN_DATE)"


def _build_optional_where(
    filters: dict,
    *,
    column_map: dict[str, str],
) -> tuple[str, dict]:
    builder = QueryBuilder()
    for key, column_expr in column_map.items():
        values = _normalize_tokens(filters.get(key) or [])
        if values:
            builder.add_in_condition(column_expr, values)
    return builder.get_conditions_sql(), builder.params.copy()


def _load_excluded_reason_tokens() -> set[str]:
    tokens: set[str] = set()
    for value in get_excluded_reasons():
        token = str(value or "").strip().upper()
        if token:
            tokens.add(token)
    return tokens


def _build_normalized_exclusion_tokens(excluded_reason_tokens: set[str]) -> set[str]:
    normalized: set[str] = set()
    for token in excluded_reason_tokens:
        normalized_token = normalize_reason_code(token)
        if normalized_token:
            normalized.add(normalized_token)
    return normalized


def _build_reason_exclusion_clause(*, alias: str, excluded_reason_tokens: set[str]) -> tuple[str, dict]:
    builder = QueryBuilder()
    if excluded_reason_tokens:
        sorted_tokens = sorted(excluded_reason_tokens)
        builder.add_not_in_condition(f"UPPER(NVL(TRIM({alias}.REASON_CODE), '-'))", sorted_tokens)
        builder.add_not_in_condition(f"UPPER(NVL(TRIM({alias}.REASON_NAME), '-'))", sorted_tokens)

    builder.add_condition(
        f"UPPER(NVL(TRIM({alias}.REASON_CODE), NVL(TRIM({alias}.REASON_NAME), '(UNMAPPED)'))) "
        "NOT IN ('(UNMAPPED)', 'N/A', 'NA', '-')"
    )

    where_sql, params = builder.build_where_only()
    where_tail = f" AND {where_sql[6:]}" if where_sql.startswith("WHERE ") else ""
    return where_tail, params


def _namespace_bind_params(sql: str, params: dict, *, prefix: str) -> tuple[str, dict]:
    if not params:
        return sql, {}

    rewritten_sql = sql
    rewritten_params: dict = {}
    for key in sorted(params.keys(), key=len, reverse=True):
        namespaced = f"{prefix}{key}"
        rewritten_sql = rewritten_sql.replace(f":{key}", f":{namespaced}")
        rewritten_params[namespaced] = params[key]
    return rewritten_sql, rewritten_params


def _bucket_to_text(value: object) -> str:
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d")
    return str(value)[:10]


def _query_filtered_scrap_total(
    *,
    start_date: str,
    end_date: str,
    filters: dict,
    excluded_reason_tokens: set[str],
) -> float:
    where_sql, params = _build_optional_where(filters, column_map=_SUMMARY_DETAIL_FILTER_COLUMNS)
    exclusion_sql, exclusion_params = _build_reason_exclusion_clause(
        alias="d",
        excluded_reason_tokens=excluded_reason_tokens,
    )
    exclusion_sql, exclusion_params = _namespace_bind_params(exclusion_sql, exclusion_params, prefix="x_")
    sql = f"""
        SELECT
            SUM(NVL(d.SCRAP_QUANTITY, 0)) AS SCRAP_QTY
        FROM DWH.ERP_WIP_MOVETXN_DETAIL d
        WHERE d.TXN_DATE >= TO_DATE(:start_date, 'YYYY-MM-DD')
          AND d.TXN_DATE < TO_DATE(:end_date, 'YYYY-MM-DD') + 1
          AND UPPER(NVL(TRIM(d.WIP_ENTITY_NAME), '-')) LIKE 'GA%'
          AND d.PACKAGE IS NOT NULL
          AND TRIM(d.PACKAGE) NOT IN ('N/A', 'NA', '(NA)', '(N/A)', 'NULL')
        {"AND " + where_sql if where_sql else ""}
        {exclusion_sql}
    """
    query_params = {"start_date": start_date, "end_date": end_date}
    query_params.update(params)
    query_params.update(exclusion_params)
    df = read_sql_df_slow(sql, query_params)
    if df.empty:
        return 0.0
    row = df.iloc[0]
    return _safe_float(row.get("SCRAP_QTY") if hasattr(row, "get") else 0)


def _query_filtered_scrap_trend(
    *,
    start_date: str,
    end_date: str,
    granularity: str,
    filters: dict,
    excluded_reason_tokens: set[str],
) -> dict[str, float]:
    bucket_expr = _bucket_expr(granularity, alias="d")
    where_sql, params = _build_optional_where(filters, column_map=_SUMMARY_DETAIL_FILTER_COLUMNS)
    exclusion_sql, exclusion_params = _build_reason_exclusion_clause(
        alias="d",
        excluded_reason_tokens=excluded_reason_tokens,
    )
    exclusion_sql, exclusion_params = _namespace_bind_params(exclusion_sql, exclusion_params, prefix="x_")
    sql = f"""
        SELECT
            {bucket_expr} AS DATE_BUCKET,
            SUM(NVL(d.SCRAP_QUANTITY, 0)) AS SCRAP_QTY
        FROM DWH.ERP_WIP_MOVETXN_DETAIL d
        WHERE d.TXN_DATE >= TO_DATE(:start_date, 'YYYY-MM-DD')
          AND d.TXN_DATE < TO_DATE(:end_date, 'YYYY-MM-DD') + 1
          AND UPPER(NVL(TRIM(d.WIP_ENTITY_NAME), '-')) LIKE 'GA%'
          AND d.PACKAGE IS NOT NULL
          AND TRIM(d.PACKAGE) NOT IN ('N/A', 'NA', '(NA)', '(N/A)', 'NULL')
        {"AND " + where_sql if where_sql else ""}
        {exclusion_sql}
        GROUP BY {bucket_expr}
    """
    query_params = {"start_date": start_date, "end_date": end_date}
    query_params.update(params)
    query_params.update(exclusion_params)
    df = read_sql_df_slow(sql, query_params)
    result: dict[str, float] = {}
    for _, row in df.iterrows():
        bucket_text = _bucket_to_text(row.get("DATE_BUCKET"))
        result[bucket_text] = _safe_float(row.get("SCRAP_QTY"))
    return result


def _safe_float(value: object) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _chunked(items: list[str], size: int) -> list[list[str]]:
    if size <= 0:
        return [items]
    return [items[i : i + size] for i in range(0, len(items), size)]


def query_yield_summary(
    *,
    start_date: str,
    end_date: str,
    filters: dict | None = None,
) -> dict:
    validate_date_range(start_date, end_date)
    sql = _load_sql("summary")

    where_sql, params = _build_optional_where(filters or {}, column_map=_SUMMARY_FILTER_COLUMNS)
    sql = sql.replace("{{ WHERE_CLAUSE }}", f" AND {where_sql}" if where_sql else "")

    query_params = {"start_date": start_date, "end_date": end_date}
    query_params.update(params)

    started = time.perf_counter()
    df = read_sql_df_slow(sql, query_params)
    excluded_reason_tokens = _load_excluded_reason_tokens()
    filtered_scrap_qty = _query_filtered_scrap_total(
        start_date=start_date,
        end_date=end_date,
        filters=filters or {},
        excluded_reason_tokens=excluded_reason_tokens,
    )
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)

    row = df.iloc[0] if not df.empty else {}
    transaction_qty = _safe_float(row.get("TRANSACTION_QTY") if hasattr(row, "get") else 0)
    yield_pct = 100.0
    if transaction_qty > 0:
        yield_pct = round((1 - (filtered_scrap_qty / transaction_qty)) * 100, 4)
    summary = {
        "transaction_qty": transaction_qty,
        "scrap_qty": filtered_scrap_qty,
        "yield_pct": yield_pct,
    }
    return {
        "summary": summary,
        "meta": {
            "query_latency_ms": elapsed_ms,
            "max_query_days": MAX_QUERY_DAYS,
            "reason_exclusion_applied": True,
            "excluded_reason_count": len(excluded_reason_tokens),
        },
    }


def query_yield_trend(
    *,
    start_date: str,
    end_date: str,
    granularity: str,
    filters: dict | None = None,
) -> dict:
    validate_date_range(start_date, end_date)
    if granularity not in VALID_GRANULARITY:
        raise ValueError("granularity 僅支援 day/week/month")

    sql = _load_sql("trend")
    sql = sql.replace("{{ BUCKET_EXPR }}", _bucket_expr(granularity, alias="m"))
    where_sql, params = _build_optional_where(filters or {}, column_map=_SUMMARY_FILTER_COLUMNS)
    sql = sql.replace("{{ WHERE_CLAUSE }}", f" AND {where_sql}" if where_sql else "")

    query_params = {"start_date": start_date, "end_date": end_date}
    query_params.update(params)

    started = time.perf_counter()
    df = read_sql_df_slow(sql, query_params)
    excluded_reason_tokens = _load_excluded_reason_tokens()
    scrap_by_bucket = _query_filtered_scrap_trend(
        start_date=start_date,
        end_date=end_date,
        granularity=granularity,
        filters=filters or {},
        excluded_reason_tokens=excluded_reason_tokens,
    )
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)

    items: list[dict] = []
    seen_buckets: set[str] = set()
    for _, row in df.iterrows():
        date_bucket = _bucket_to_text(row.get("DATE_BUCKET"))
        transaction_qty = _safe_float(row.get("TRANSACTION_QTY"))
        scrap_qty = _safe_float(scrap_by_bucket.get(date_bucket, 0.0))
        yield_pct = 100.0
        if transaction_qty > 0:
            yield_pct = round((1 - (scrap_qty / transaction_qty)) * 100, 4)
        items.append(
            {
                "date_bucket": date_bucket,
                "transaction_qty": transaction_qty,
                "scrap_qty": scrap_qty,
                "yield_pct": yield_pct,
            }
        )
        seen_buckets.add(date_bucket)

    for date_bucket in sorted(k for k in scrap_by_bucket.keys() if k not in seen_buckets):
        scrap_qty = _safe_float(scrap_by_bucket.get(date_bucket, 0.0))
        items.append(
            {
                "date_bucket": date_bucket,
                "transaction_qty": 0.0,
                "scrap_qty": scrap_qty,
                "yield_pct": 100.0,
            }
        )

    return {
        "items": items,
        "granularity": granularity,
        "meta": {
            "query_latency_ms": elapsed_ms,
            "max_query_days": MAX_QUERY_DAYS,
            "reason_exclusion_applied": True,
            "excluded_reason_count": len(excluded_reason_tokens),
        },
    }


def _risk_level(yield_pct: float, scrap_qty: float, threshold: float) -> tuple[str, float]:
    scrap_weight = min(max(scrap_qty, 0.0), 200.0) / 20.0
    risk_score = round(max(0.0, (threshold - yield_pct)) + scrap_weight, 4)
    if yield_pct < threshold - 2.0 or scrap_qty >= 100:
        return "high", risk_score
    if yield_pct < threshold or scrap_qty >= 20:
        return "medium", risk_score
    return "low", risk_score


def _compute_reject_linkage(
    *,
    start_date: str,
    end_date: str,
    workorders: list[str],
) -> dict[str, float]:
    if not workorders:
        return {}

    normalized_workorders: list[str] = []
    seen_workorders: set[str] = set()
    for workorder in workorders:
        token = str(workorder or "").strip().upper()
        if not token or token in seen_workorders:
            continue
        seen_workorders.add(token)
        normalized_workorders.append(token)
    if not normalized_workorders:
        return {}

    sql_template = """
        SELECT
            TRUNC(r.TXNDATE) AS DATE_BUCKET,
            UPPER(NVL(TRIM(r.PJ_WORKORDER), '(NA)')) AS WORKORDER,
            NVL(TRIM(r.LOSSREASONNAME), '(未填寫)') AS REASON_NAME,
            SUM(
                NVL(r.REJECTQTY, 0)
                + NVL(r.STANDBYQTY, 0)
                + NVL(r.QTYTOPROCESS, 0)
                + NVL(r.INPROCESSQTY, 0)
                + NVL(r.PROCESSEDQTY, 0)
            ) AS REJECT_TOTAL_QTY
        FROM DWH.DW_MES_LOTREJECTHISTORY r
        WHERE r.TXNDATE >= TO_DATE(:start_date, 'YYYY-MM-DD')
          AND r.TXNDATE < TO_DATE(:end_date, 'YYYY-MM-DD') + 1
        {{ WHERE_TAIL }}
        GROUP BY
            TRUNC(r.TXNDATE),
            UPPER(NVL(TRIM(r.PJ_WORKORDER), '(NA)')),
            NVL(TRIM(r.LOSSREASONNAME), '(未填寫)')
    """

    linked: dict[str, float] = {}
    workorder_batches = _chunked(normalized_workorders, _ORACLE_IN_MAX_EXPRESSIONS)
    if len(workorder_batches) > 1:
        logger.info(
            "Yield alert linkage batching enabled: workorders=%s batches=%s batch_size=%s",
            len(normalized_workorders),
            len(workorder_batches),
            _ORACLE_IN_MAX_EXPRESSIONS,
        )

    for batch in workorder_batches:
        builder = QueryBuilder()
        builder.add_in_condition("UPPER(NVL(TRIM(r.PJ_WORKORDER), '-'))", batch)
        where_sql, params = builder.build_where_only()
        where_tail = f" AND {where_sql[6:]}" if where_sql.startswith("WHERE ") else ""
        sql = sql_template.replace("{{ WHERE_TAIL }}", where_tail)

        query_params = {"start_date": start_date, "end_date": end_date}
        query_params.update(params)
        df = read_sql_df_slow(sql, query_params)

        for _, row in df.iterrows():
            bucket = row.get("DATE_BUCKET")
            if hasattr(bucket, "strftime"):
                bucket_text = bucket.strftime("%Y-%m-%d")
            else:
                bucket_text = str(bucket)[:10]

            key = build_canonical_key(
                bucket_text,
                str(row.get("WORKORDER") or ""),
                str(row.get("REASON_NAME") or ""),
            )
            linked[key] = linked.get(key, 0.0) + _safe_float(row.get("REJECT_TOTAL_QTY"))
    return linked


def query_alert_candidates(
    *,
    start_date: str,
    end_date: str,
    filters: dict | None = None,
    page: int = 1,
    per_page: int = DEFAULT_PAGE_SIZE,
    sort_by: str = "date_bucket",
    sort_dir: str = "desc",
    risk_threshold: float = 98.0,
    min_scrap_qty: float = 1.0,
) -> dict:
    validate_date_range(start_date, end_date)

    normalized_page = max(1, int(page or 1))
    normalized_per_page = min(max(1, int(per_page or DEFAULT_PAGE_SIZE)), MAX_PAGE_SIZE)
    normalized_sort_by = sort_by if sort_by in VALID_SORT_FIELDS else "date_bucket"
    normalized_sort_dir = "asc" if str(sort_dir).lower() == "asc" else "desc"

    sql = _load_sql("alerts")
    excluded_reason_tokens = _load_excluded_reason_tokens()
    normalized_excluded_reason_tokens = _build_normalized_exclusion_tokens(excluded_reason_tokens)
    exclusion_sql, exclusion_params = _build_reason_exclusion_clause(
        alias="d",
        excluded_reason_tokens=excluded_reason_tokens,
    )
    exclusion_sql, exclusion_params = _namespace_bind_params(exclusion_sql, exclusion_params, prefix="x_")
    where_sql, params = _build_optional_where(filters or {}, column_map=_DETAIL_FILTER_COLUMNS)
    sql = sql.replace("{{ WHERE_CLAUSE }}", f" AND {where_sql}" if where_sql else "")
    sql = sql.replace("{{ EXCLUSION_CLAUSE }}", exclusion_sql)

    query_params = {"start_date": start_date, "end_date": end_date}
    query_params.update(params)
    query_params.update(exclusion_params)

    # Query TRANSACTION_QTY from ALL rows (including move-only) at non-reason level
    tx_sql = _load_sql("alerts_tx_lookup")
    tx_where_sql, tx_params = _build_optional_where(filters or {}, column_map=_DETAIL_FILTER_COLUMNS)
    tx_sql = tx_sql.replace("{{ WHERE_CLAUSE }}", f" AND {tx_where_sql}" if tx_where_sql else "")
    tx_query_params = {"start_date": start_date, "end_date": end_date}
    tx_query_params.update(tx_params)

    started = time.perf_counter()
    df = read_sql_df_slow(sql, query_params)
    tx_df = read_sql_df_slow(tx_sql, tx_query_params)

    # Build tx_lookup: (date, workorder, department_group, line, package, type, function, operation) -> tx_qty
    tx_lookup: dict[tuple, float] = {}
    for _, trow in tx_df.iterrows():
        tx_key = (
            _bucket_to_text(trow.get("DATE_BUCKET")),
            str(trow.get("WIP_ENTITY_NAME") or "").strip(),
            _normalize_yield_department_group(trow.get("DEPARTMENT_NAME")),
            str(trow.get("LINE_NAME") or "").strip(),
            str(trow.get("PACKAGE_NAME") or "").strip(),
            str(trow.get("TYPE_NAME") or "").strip(),
            str(trow.get("FUNCTION_NAME") or "").strip(),
            str(trow.get("OPERATION_SEQ_NUM") or "").strip(),
        )
        tx_lookup[tx_key] = tx_lookup.get(tx_key, 0.0) + _safe_float(trow.get("TRANSACTION_QTY"))

    aggregated_rows: dict[tuple, dict] = {}
    for _, row in df.iterrows():
        scrap_qty = _safe_float(row.get("SCRAP_QTY"))
        date_bucket = _bucket_to_text(row.get("DATE_BUCKET"))

        reason_raw = str(row.get("REASON_RAW") or "").strip()
        reason_code = normalize_reason_code(reason_raw)
        if (
            reason_code == _UNMAPPED_REASON_CODE
            or reason_code in normalized_excluded_reason_tokens
            or reason_raw.upper() in excluded_reason_tokens
        ):
            continue

        workorder = str(row.get("WIP_ENTITY_NAME") or "").strip()
        reason_name = str(row.get("REASON_NAME") or "").strip()
        department_group = _normalize_yield_department_group(row.get("DEPARTMENT_NAME"))
        line_name = str(row.get("LINE_NAME") or "").strip()
        package_name = str(row.get("PACKAGE_NAME") or "").strip()
        type_name = str(row.get("TYPE_NAME") or "").strip()
        function_name = str(row.get("FUNCTION_NAME") or "").strip()
        operation_name = str(row.get("OPERATION_SEQ_NUM") or "").strip()
        row_key = (
            date_bucket,
            workorder,
            reason_code,
            reason_name,
            department_group,
            line_name,
            package_name,
            type_name,
            function_name,
            operation_name,
        )
        if row_key not in aggregated_rows:
            aggregated_rows[row_key] = {
                "date_bucket": date_bucket,
                "workorder": workorder,
                "reason_code": reason_code,
                "reason_name": reason_name,
                "department": department_group,
                "line": line_name,
                "package": package_name,
                "type": type_name,
                "function": function_name,
                "operation": operation_name,
                "scrap_qty": 0.0,
            }
        aggregated_rows[row_key]["scrap_qty"] += scrap_qty

    rows: list[dict] = []
    for aggregated in aggregated_rows.values():
        # Look up TRANSACTION_QTY from the non-reason-level tx_lookup
        tx_key = (
            aggregated["date_bucket"],
            aggregated["workorder"],
            aggregated["department"],
            aggregated["line"],
            aggregated["package"],
            aggregated["type"],
            aggregated["function"],
            aggregated["operation"],
        )
        transaction_qty = _safe_float(tx_lookup.get(tx_key, 0.0))
        scrap_qty = _safe_float(aggregated.get("scrap_qty"))
        yield_pct = 100.0
        if transaction_qty > 0:
            yield_pct = round((1 - (scrap_qty / transaction_qty)) * 100, 4)
        if yield_pct >= float(risk_threshold) and scrap_qty < float(min_scrap_qty):
            continue
        scrap_rate_pct = 0.0
        if transaction_qty > 0:
            scrap_rate_pct = round((scrap_qty / transaction_qty) * 100, 4)
        risk_level, risk_score = _risk_level(yield_pct, scrap_qty, float(risk_threshold))

        rows.append(
            {
                **aggregated,
                "transaction_qty": round(transaction_qty, 4),
                "scrap_qty": round(scrap_qty, 4),
                "yield_pct": yield_pct,
                "scrap_rate_pct": scrap_rate_pct,
                "risk_level": risk_level,
                "risk_score": risk_score,
                "match_status": "none",
                "fallback_reason": None,
                "reject_total_qty": 0.0,
            }
        )

    workorders = sorted({str(item["workorder"] or "").upper() for item in rows if item.get("workorder")})
    linked = _compute_reject_linkage(start_date=start_date, end_date=end_date, workorders=workorders)

    matched = 0
    partial = 0
    unmatched = 0
    matched_qty = 0.0
    partial_qty = 0.0
    unmatched_qty = 0.0

    for item in rows:
        key = build_canonical_key(item["date_bucket"], item["workorder"], item["reason_code"])
        exact_qty = linked.get(key, 0.0)
        if exact_qty > 0:
            item["match_status"] = "exact"
            item["reject_total_qty"] = round(exact_qty, 4)
            matched += 1
            matched_qty += item["scrap_qty"]
            continue

        partial_key_prefix = f"{item['date_bucket']}|{str(item['workorder'] or '').strip().upper()}|"
        partial_hits = [qty for k, qty in linked.items() if k.startswith(partial_key_prefix)]
        if partial_hits:
            item["match_status"] = "partial"
            item["fallback_reason"] = "reason_code_not_exact"
            item["reject_total_qty"] = round(sum(partial_hits), 4)
            partial += 1
            partial_qty += item["scrap_qty"]
        else:
            item["match_status"] = "none"
            item["fallback_reason"] = "workorder_or_date_not_found"
            unmatched += 1
            unmatched_qty += item["scrap_qty"]

    reverse = normalized_sort_dir == "desc"
    rows.sort(key=lambda item: item.get(normalized_sort_by), reverse=reverse)

    total = len(rows)
    total_pages = max(1, int(math.ceil(total / normalized_per_page)))
    normalized_page = min(normalized_page, total_pages)
    start_idx = (normalized_page - 1) * normalized_per_page
    end_idx = start_idx + normalized_per_page
    page_rows = rows[start_idx:end_idx]

    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    total_scrap = matched_qty + partial_qty + unmatched_qty
    unmatched_ratio = 0.0 if total_scrap <= 0 else round(unmatched_qty / total_scrap, 4)
    logger.info(
        (
            "Yield alert linkage quality: rows=%s matched=%s partial=%s unmatched=%s "
            "unmatched_ratio=%.4f query_latency_ms=%.2f"
        ),
        len(rows),
        matched,
        partial,
        unmatched,
        unmatched_ratio,
        elapsed_ms,
    )

    return {
        "items": page_rows,
        "pagination": {
            "page": normalized_page,
            "per_page": normalized_per_page,
            "total": total,
            "total_pages": total_pages,
        },
        "quality": {
            "matched": matched,
            "partially_matched": partial,
            "unmatched": unmatched,
            "matched_scrap_qty": round(matched_qty, 4),
            "partially_matched_scrap_qty": round(partial_qty, 4),
            "unmatched_scrap_qty": round(unmatched_qty, 4),
            "total_scrap_qty": round(total_scrap, 4),
            "unmatched_ratio": unmatched_ratio,
            "warning": unmatched_ratio >= LINKAGE_WARN_UNMATCHED_RATIO,
            "warning_code": "high_unmatched_ratio" if unmatched_ratio >= LINKAGE_WARN_UNMATCHED_RATIO else None,
        },
        "sort": {
            "sort_by": normalized_sort_by,
            "sort_dir": normalized_sort_dir,
        },
        "meta": {
            "query_latency_ms": elapsed_ms,
            "max_query_days": MAX_QUERY_DAYS,
            "max_per_page": MAX_PAGE_SIZE,
            "reason_exclusion_applied": True,
            "excluded_reason_count": len(excluded_reason_tokens),
        },
    }


def query_reason_detail(*, workorder: str, date_bucket: str, reason_code: str = "", department: str = "") -> list[dict]:
    if not workorder or not date_bucket:
        return []

    sql = SQLLoader.load("yield_alert/reason_detail")
    params: dict = {
        "workorder": workorder,
        "date_bucket": date_bucket,
        "reason_code": reason_code.strip().upper() if reason_code and reason_code.strip() else None,
        "department": department.strip() if department and department.strip() else None,
    }
    df = read_sql_df_slow(sql, params)

    items: list[dict] = []
    for _, row in df.iterrows():
        txn_time = row.get("TXN_TIME")
        if hasattr(txn_time, "strftime"):
            txn_time_str = txn_time.strftime("%Y-%m-%d %H:%M:%S")
        else:
            txn_time_str = str(txn_time or "")[:19]
        items.append({
            "txn_time": txn_time_str,
            "containername": str(row.get("CONTAINERNAME") or ""),
            "workcentername": str(row.get("WORKCENTERNAME") or ""),
            "workcenter_group": str(row.get("WORKCENTER_GROUP") or ""),
            "specname": str(row.get("SPECNAME") or ""),
            "equipmentname": str(row.get("EQUIPMENTNAME") or ""),
            "productname": str(row.get("PRODUCTNAME") or ""),
            "pj_function": str(row.get("PJ_FUNCTION") or ""),
            "pj_type": str(row.get("PJ_TYPE") or ""),
            "package_name": str(row.get("PACKAGE_NAME") or ""),
            "lossreasonname": str(row.get("LOSSREASONNAME") or ""),
            "lossreason_code": str(row.get("LOSSREASON_CODE") or ""),
            "rejectcomment": str(row.get("REJECTCOMMENT") or ""),
            "scrap_objecttype": str(row.get("SCRAP_OBJECTTYPE") or ""),
            "reject_qty": _safe_float(row.get("REJECT_QTY")),
            "standby_qty": _safe_float(row.get("STANDBY_QTY")),
            "qtytoprocess_qty": _safe_float(row.get("QTYTOPROCESS_QTY")),
            "inprocess_qty": _safe_float(row.get("INPROCESS_QTY")),
            "processed_qty": _safe_float(row.get("PROCESSED_QTY")),
            "reject_total_qty": _safe_float(row.get("REJECT_TOTAL_QTY")),
            "defect_qty": _safe_float(row.get("DEFECT_QTY")),
        })
    return items


def build_drilldown_payload(
    *,
    date_bucket: str,
    workorder: str,
    reason_code: str,
) -> dict:
    normalized_reason = normalize_reason_code(reason_code)
    canonical = build_canonical_key(date_bucket, workorder, normalized_reason)

    params = [
        ("mode", "date_range"),
        ("start_date", date_bucket),
        ("end_date", date_bucket),
        ("reasons", normalized_reason),
        ("yield_workorder", str(workorder or "").strip()),
        ("yield_reason_code", normalized_reason),
    ]
    launch_href = f"/reject-history?{urlencode(params, doseq=True)}"

    match_status = "exact" if normalized_reason != "UNMAPPED_REASON" else "partial"
    fallback_reason = None if match_status == "exact" else "reason_unmapped"

    return {
        "match_status": match_status,
        "fallback_reason": fallback_reason,
        "launch_href": launch_href,
        "filters": {
            "start_date": date_bucket,
            "end_date": date_bucket,
            "workorder": str(workorder or "").strip(),
            "reason_code": normalized_reason,
        },
        "linkage": {
            "canonical_key": canonical,
            "normalized_reason_code": normalized_reason,
        },
    }
