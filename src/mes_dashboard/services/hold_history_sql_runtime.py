# -*- coding: utf-8 -*-
"""DuckDB SQL runtime for hold-history view computation.

Provides out-of-core view aggregation (trend / reason_pareto / duration / list)
by querying Parquet spool files directly via DuckDB, avoiding full DataFrame
loads into pandas.

Entry point: ``try_compute_view_from_spool``
"""

from __future__ import annotations

import logging
import math
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from mes_dashboard.core.feature_flags import resolve_bool_flag
from mes_dashboard.core.query_spool_store import get_spool_file_path

logger = logging.getLogger("mes_dashboard.hold_history_sql_runtime")

# ── Feature flag ──────────────────────────────────────────────────────────────
_SQL_VIEW_ENABLED = resolve_bool_flag("HOLD_HISTORY_SQL_VIEW_ENABLED", default=True)

SQL_FALLBACK_DISABLED = "hold_history_sql_disabled"
SQL_FALLBACK_DEP_MISSING = "hold_history_sql_dependency_missing"
SQL_FALLBACK_SPOOL_MISS = "hold_history_sql_spool_miss"
SQL_FALLBACK_RUNTIME_ERROR = "hold_history_sql_runtime_error"

_SPOOL_NAMESPACE = "hold_dataset"


# ── SQL helpers ───────────────────────────────────────────────────────────────

def _qid(name: str) -> str:
    """Quote a DuckDB identifier."""
    return '"' + str(name).replace('"', '""') + '"'


def _sql_str_literal(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _attach_spool_view(conn: Any, parquet_path: str) -> None:
    conn.execute(
        "CREATE OR REPLACE TEMP VIEW hold_src AS "
        f"SELECT * FROM read_parquet({_sql_str_literal(parquet_path)})"
    )


def _fetch_dict_rows(conn: Any, sql: str, params: Optional[List[Any]] = None) -> List[Dict[str, Any]]:
    cursor = conn.execute(sql, params or [])
    columns = [desc[0] for desc in (cursor.description or [])]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _sf(value: Any, default: float = 0.0) -> float:
    try:
        return float(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def _si(value: Any, default: int = 0) -> int:
    try:
        return int(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def _sstr(value: Any, default: str = "") -> str:
    if value is None:
        return default
    s = str(value).strip()
    return s if s else default


def _is_iso_date(value: Optional[str]) -> bool:
    text = _sstr(value, "")
    if not text:
        return False
    try:
        datetime.strptime(text, "%Y-%m-%d")
        return True
    except (TypeError, ValueError):
        return False


def _resolve_view_date_range(
    conn: Any,
    *,
    start_date: Optional[str],
    end_date: Optional[str],
) -> Tuple[Optional[str], Optional[str]]:
    """Resolve safe YYYY-MM-DD bounds for trend/new-record computation.

    Priority:
    1) Caller-provided valid ISO dates.
    2) Derive from spool data min/max(hold_day) when any bound is missing.
    """
    start = _sstr(start_date, "") if _is_iso_date(start_date) else ""
    end = _sstr(end_date, "") if _is_iso_date(end_date) else ""

    if start and end:
        if end < start:
            return end, start
        return start, end

    bounds_sql = """
        SELECT
            MIN(CAST("hold_day" AS DATE)) AS min_day,
            MAX(CAST("hold_day" AS DATE)) AS max_day
        FROM hold_src
    """
    rows = _fetch_dict_rows(conn, bounds_sql)
    if rows:
        row = rows[0] or {}
        if not start:
            min_day = row.get("min_day")
            start = str(min_day)[:10] if min_day is not None else ""
        if not end:
            max_day = row.get("max_day")
            end = str(max_day)[:10] if max_day is not None else ""

    if start and end and end < start:
        start, end = end, start

    return (start or None), (end or None)


# ── Task 4.2: Trend SQL ───────────────────────────────────────────────────────

def _query_trend(
    conn: Any,
    *,
    start_date: str,
    end_date: str,
) -> Dict[str, Any]:
    """Compute daily hold trend with quality / non_quality / all variants.

    The 07:30 shift boundary is already baked into the ``hold_day`` and
    ``release_day`` columns by the Oracle base_facts SQL.

    Optimized: replaced N×3×4 individual queries with 4 batched queries
    that compute all dates × hold_types in single passes via GROUP BY.
    """
    # Generate date series from start_date to end_date
    dates_sql = """
        SELECT CAST(generate_series AS DATE) AS d
        FROM generate_series(
            CAST(? AS DATE),
            CAST(? AS DATE),
            INTERVAL 1 DAY
        )
    """
    date_rows = _fetch_dict_rows(conn, dates_sql, [start_date, end_date])
    dates = [str(r["d"])[:10] for r in date_rows]

    # Pre-build empty structure
    day_map: Dict[str, Dict[str, Dict[str, int]]] = {}
    for d in dates:
        day_map[d] = {
            k: {"holdQty": 0, "newHoldQty": 0, "releaseQty": 0, "futureHoldQty": 0, "repeatQualityHoldQty": 0}
            for k in ("quality", "non_quality", "all")
        }

    _HOLD_TYPE_KEY = {"quality": "quality", "non-quality": "non_quality"}

    # ── Batch 1: holdQty (on-hold as of each day) ──
    # Cross join dates × hold_src, group by date + hold_type
    hold_sql = """
        SELECT
            CAST(cal.d AS VARCHAR) AS day_str,
            "HOLD_TYPE" AS ht,
            COALESCE(SUM("QTY"), 0) AS v
        FROM generate_series(CAST(? AS DATE), CAST(? AS DATE), INTERVAL 1 DAY) cal(d)
        JOIN hold_src h
          ON CAST(h."hold_day" AS DATE) <= cal.d
          AND (h."release_day" IS NULL OR CAST(h."release_day" AS DATE) > cal.d)
        GROUP BY cal.d, "HOLD_TYPE"
    """
    for r in _fetch_dict_rows(conn, hold_sql, [start_date, end_date]):
        d = str(r["day_str"])[:10]
        if d not in day_map:
            continue
        qty = _si(r["v"])
        ht_key = _HOLD_TYPE_KEY.get(str(r["ht"]), None)
        if ht_key:
            day_map[d][ht_key]["holdQty"] = qty
        day_map[d]["all"]["holdQty"] = day_map[d]["all"]["holdQty"] + qty

    # ── Batch 2: newHoldQty (new holds arriving on each day) ──
    new_sql = """
        SELECT
            CAST("hold_day" AS VARCHAR) AS day_str,
            "HOLD_TYPE" AS ht,
            COALESCE(SUM("QTY"), 0) AS v
        FROM hold_src
        WHERE CAST("hold_day" AS DATE) BETWEEN CAST(? AS DATE) AND CAST(? AS DATE)
          AND "RN_HOLD_DAY" = 1
        GROUP BY "hold_day", "HOLD_TYPE"
    """
    for r in _fetch_dict_rows(conn, new_sql, [start_date, end_date]):
        d = str(r["day_str"])[:10]
        if d not in day_map:
            continue
        qty = _si(r["v"])
        ht_key = _HOLD_TYPE_KEY.get(str(r["ht"]), None)
        if ht_key:
            day_map[d][ht_key]["newHoldQty"] = qty
        day_map[d]["all"]["newHoldQty"] = day_map[d]["all"]["newHoldQty"] + qty

    # ── Batch 3: releaseQty (released on each day) ──
    release_sql = """
        SELECT
            CAST("release_day" AS VARCHAR) AS day_str,
            "HOLD_TYPE" AS ht,
            COALESCE(SUM("QTY"), 0) AS v
        FROM hold_src
        WHERE CAST("release_day" AS DATE) BETWEEN CAST(? AS DATE) AND CAST(? AS DATE)
        GROUP BY "release_day", "HOLD_TYPE"
    """
    for r in _fetch_dict_rows(conn, release_sql, [start_date, end_date]):
        d = str(r["day_str"])[:10]
        if d not in day_map:
            continue
        qty = _si(r["v"])
        ht_key = _HOLD_TYPE_KEY.get(str(r["ht"]), None)
        if ht_key:
            day_map[d][ht_key]["releaseQty"] = qty
        day_map[d]["all"]["releaseQty"] = day_map[d]["all"]["releaseQty"] + qty

    # ── Batch 4: futureHoldQty (future holds on each day) ──
    future_sql = """
        SELECT
            CAST("hold_day" AS VARCHAR) AS day_str,
            "HOLD_TYPE" AS ht,
            COALESCE(SUM("QTY"), 0) AS v
        FROM hold_src
        WHERE CAST("hold_day" AS DATE) BETWEEN CAST(? AS DATE) AND CAST(? AS DATE)
          AND "IS_FUTURE_HOLD" = 1
          AND "FUTURE_HOLD_FLAG" = 1
        GROUP BY "hold_day", "HOLD_TYPE"
    """
    for r in _fetch_dict_rows(conn, future_sql, [start_date, end_date]):
        d = str(r["day_str"])[:10]
        if d not in day_map:
            continue
        qty = _si(r["v"])
        ht_key = _HOLD_TYPE_KEY.get(str(r["ht"]), None)
        if ht_key:
            day_map[d][ht_key]["futureHoldQty"] = qty
        day_map[d]["all"]["futureHoldQty"] = day_map[d]["all"]["futureHoldQty"] + qty

    # ── Batch 5: repeatQualityHoldQty (quality repeat holds: rn_future_reason > 1) ──
    repeat_sql = """
        SELECT
            CAST("hold_day" AS VARCHAR) AS day_str,
            COALESCE(SUM("QTY"), 0) AS v
        FROM hold_src
        WHERE CAST("hold_day" AS DATE) BETWEEN CAST(? AS DATE) AND CAST(? AS DATE)
          AND "RN_FUTURE_REASON" > 1
          AND "HOLD_TYPE" = 'quality'
        GROUP BY "hold_day"
    """
    for r in _fetch_dict_rows(conn, repeat_sql, [start_date, end_date]):
        d = str(r["day_str"])[:10]
        if d not in day_map:
            continue
        qty = _si(r["v"])
        day_map[d]["quality"]["repeatQualityHoldQty"] = qty
        day_map[d]["all"]["repeatQualityHoldQty"] = qty

    # Assemble result in date order
    days: List[Dict[str, Any]] = []
    for d in dates:
        days.append({"date": d, **day_map[d]})

    return {"days": days}


# ── Task 4.3: Reason Pareto SQL ───────────────────────────────────────────────

def _query_reason_pareto(
    conn: Any,
    *,
    hold_type: str = "quality",
    record_type: str = "new",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    duration_range: Optional[str] = None,
) -> Dict[str, Any]:
    """Compute reason Pareto: GROUP BY HOLDREASONNAME, DESC by count."""
    type_clause = _build_hold_type_clause(hold_type)
    record_clause = _build_record_type_clause(record_type, start_date, end_date)
    duration_clause = _build_duration_clause(duration_range)

    where_parts = []
    if type_clause:
        where_parts.append(type_clause)
    if record_clause:
        where_parts.append(record_clause)
    if duration_clause:
        where_parts.append(duration_clause)
    where_sql = "WHERE " + " AND ".join(where_parts) if where_parts else ""

    sql = f"""
        SELECT
            COALESCE(CAST("HOLDREASONNAME" AS VARCHAR), '') AS reason,
            COUNT(*) AS cnt,
            COALESCE(SUM("QTY"), 0) AS qty
        FROM hold_src
        {where_sql}
        GROUP BY COALESCE(CAST("HOLDREASONNAME" AS VARCHAR), '')
        ORDER BY qty DESC
    """
    rows = _fetch_dict_rows(conn, sql)
    total_qty = sum(_si(r.get("qty")) for r in rows)

    items: List[Dict[str, Any]] = []
    cumulative = 0.0
    for r in rows:
        qty = _si(r.get("qty"))
        pct = round((qty / total_qty * 100) if total_qty > 0 else 0, 2)
        cumulative += pct
        reason = _sstr(r.get("reason")) or "(未填寫)"
        items.append({
            "reason": reason,
            "count": _si(r.get("cnt")),
            "qty": qty,
            "pct": pct,
            "cumPct": round(cumulative, 2),
        })

    return {"items": items}


# ── Task 4.4: Duration SQL ────────────────────────────────────────────────────

def _query_duration(
    conn: Any,
    *,
    hold_type: str = "quality",
    record_type: str = "new",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    reason: Optional[str] = None,
) -> Dict[str, Any]:
    """Compute hold duration distribution via CASE buckets in DuckDB.

    Bucket computation uses released-only rows (RELEASETXNDATE IS NOT NULL).
    AVG/MAX metrics are computed for released and on-hold rows separately.
    """
    type_clause = _build_hold_type_clause(hold_type)
    record_clause = _build_record_type_clause(record_type, start_date, end_date)

    base_parts: List[str] = []
    if type_clause:
        base_parts.append(type_clause)
    if record_clause:
        base_parts.append(record_clause)
    if reason:
        base_parts.append(f'TRIM("HOLDREASONNAME") = {_sql_str_literal(reason.strip())}')

    bucket_parts = ['"RELEASETXNDATE" IS NOT NULL'] + base_parts
    bucket_where = "WHERE " + " AND ".join(bucket_parts)

    bucket_sql = f"""
        SELECT
            CASE
                WHEN "HOLD_HOURS" < 4      THEN '<4h'
                WHEN "HOLD_HOURS" < 24     THEN '4-24h'
                WHEN "HOLD_HOURS" < 72     THEN '1-3d'
                ELSE '>3d'
            END AS bucket,
            COUNT(*) AS cnt,
            COALESCE(SUM("QTY"), 0) AS qty
        FROM hold_src
        {bucket_where}
        GROUP BY 1
    """

    released_parts = ['"RELEASETXNDATE" IS NOT NULL'] + base_parts
    released_where = "WHERE " + " AND ".join(released_parts)
    released_sql = f"""
        SELECT
            ROUND(AVG("HOLD_HOURS"), 2) AS avg_released_hours,
            ROUND(MAX("HOLD_HOURS"), 2) AS max_released_hours
        FROM hold_src
        {released_where}
    """

    on_hold_parts = ['"RELEASETXNDATE" IS NULL'] + base_parts
    on_hold_where = "WHERE " + " AND ".join(on_hold_parts)
    on_hold_sql = f"""
        SELECT
            ROUND(AVG("HOLD_HOURS"), 2) AS avg_on_hold_hours,
            ROUND(MAX("HOLD_HOURS"), 2) AS max_on_hold_hours
        FROM hold_src
        {on_hold_where}
    """

    rows = _fetch_dict_rows(conn, bucket_sql)
    released_rows = _fetch_dict_rows(conn, released_sql)
    on_hold_rows = _fetch_dict_rows(conn, on_hold_sql)

    bucket_map = {r["bucket"]: {"count": _si(r["cnt"]), "qty": _si(r["qty"])} for r in rows}
    total_qty = sum(v["qty"] for v in bucket_map.values())

    items: List[Dict[str, Any]] = []
    for label in ("<4h", "4-24h", "1-3d", ">3d"):
        entry = bucket_map.get(label, {"count": 0, "qty": 0})
        qty = entry["qty"]
        items.append({
            "range": label,
            "count": entry["count"],
            "qty": qty,
            "pct": round((qty / total_qty * 100) if total_qty > 0 else 0, 2),
        })

    rel = released_rows[0] if released_rows else {}
    oh = on_hold_rows[0] if on_hold_rows else {}

    return {
        "items": items,
        "avgReleasedHours": round(_sf(rel.get("avg_released_hours")), 2),
        "avgOnHoldHours": round(_sf(oh.get("avg_on_hold_hours")), 2),
        "maxReleasedHours": round(_sf(rel.get("max_released_hours")), 2),
        "maxOnHoldHours": round(_sf(oh.get("max_on_hold_hours")), 2),
    }


# ── Task 4.5: List SQL ────────────────────────────────────────────────────────

def _query_list(
    conn: Any,
    *,
    hold_type: str = "quality",
    reason: Optional[str] = None,
    record_type: str = "new",
    duration_range: Optional[str] = None,
    page: int = 1,
    per_page: int = 50,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Dict[str, Any]:
    """Paginated hold list: filter by hold_type + reason, sorted by HOLDTXNDATE DESC.

    When per_page <= 0 (export mode), all matching rows are returned without
    LIMIT/OFFSET and pagination metadata reflects a single page of all rows.
    """
    export_mode = per_page <= 0
    if not export_mode:
        page = max(int(page), 1)
        per_page = min(max(int(per_page), 1), 200)

    type_clause = _build_hold_type_clause(hold_type)
    record_clause = _build_record_type_clause(record_type, start_date, end_date)
    duration_clause = _build_duration_clause(duration_range)

    where_parts = []
    params: List[Any] = []
    if type_clause:
        where_parts.append(type_clause)
    if record_clause:
        where_parts.append(record_clause)
    if reason:
        where_parts.append("TRIM(CAST(\"HOLDREASONNAME\" AS VARCHAR)) = ?")
        params.append(reason.strip())
    if duration_clause:
        where_parts.append(duration_clause)

    where_sql = "WHERE " + " AND ".join(where_parts) if where_parts else ""

    count_sql = f"SELECT COUNT(*) AS total FROM hold_src {where_sql}"
    count_rows = _fetch_dict_rows(conn, count_sql, params)
    total = _si(count_rows[0]["total"]) if count_rows else 0

    # Detect whether the spool parquet has the 'package' column (additive field).
    # Older spool files written before the schema change will not have it.
    _available_cols = {
        r[0].lower()
        for r in conn.execute("DESCRIBE hold_src").fetchall()
        if len(r) > 0
    }
    _package_col = (
        'CAST(hold_src."PACKAGE" AS VARCHAR) AS package'
        if "package" in _available_cols
        else "NULL AS package"
    )

    if export_mode:
        page_sql = f"""
            SELECT
                CAST("CONTAINERID" AS VARCHAR)   AS CONTAINERID,
                CAST("LOT_ID" AS VARCHAR)        AS LOT_ID,
                CAST("PJ_WORKORDER" AS VARCHAR)  AS PJ_WORKORDER,
                CAST("PRODUCTNAME" AS VARCHAR)   AS PRODUCTNAME,
                CAST("WORKCENTERNAME" AS VARCHAR) AS WORKCENTERNAME,
                CAST("HOLDREASONNAME" AS VARCHAR) AS HOLDREASONNAME,
                "QTY",
                "HOLDTXNDATE",
                CAST("HOLDEMP" AS VARCHAR)       AS HOLDEMP,
                CAST("HOLDCOMMENTS" AS VARCHAR)  AS HOLDCOMMENTS,
                "RELEASETXNDATE",
                CAST("RELEASEEMP" AS VARCHAR)    AS RELEASEEMP,
                CAST("RELEASECOMMENTS" AS VARCHAR) AS RELEASECOMMENTS,
                "HOLD_HOURS",
                CAST("NCRID" AS VARCHAR)         AS NCRID,
                CAST("FUTUREHOLDCOMMENTS" AS VARCHAR) AS FUTUREHOLDCOMMENTS,
                {_package_col}
            FROM hold_src
            {where_sql}
            ORDER BY "HOLDTXNDATE" DESC NULLS LAST
        """
        page_rows = _fetch_dict_rows(conn, page_sql, params)
        page = 1
        per_page = total
        total_pages = 1
    else:
        total_pages = max(1, math.ceil(total / per_page))
        page = min(page, total_pages)
        offset = (page - 1) * per_page

        page_sql = f"""
            SELECT
                CAST("CONTAINERID" AS VARCHAR)   AS CONTAINERID,
                CAST("LOT_ID" AS VARCHAR)        AS LOT_ID,
                CAST("PJ_WORKORDER" AS VARCHAR)  AS PJ_WORKORDER,
                CAST("PRODUCTNAME" AS VARCHAR)   AS PRODUCTNAME,
                CAST("WORKCENTERNAME" AS VARCHAR) AS WORKCENTERNAME,
                CAST("HOLDREASONNAME" AS VARCHAR) AS HOLDREASONNAME,
                "QTY",
                "HOLDTXNDATE",
                CAST("HOLDEMP" AS VARCHAR)       AS HOLDEMP,
                CAST("HOLDCOMMENTS" AS VARCHAR)  AS HOLDCOMMENTS,
                "RELEASETXNDATE",
                CAST("RELEASEEMP" AS VARCHAR)    AS RELEASEEMP,
                CAST("RELEASECOMMENTS" AS VARCHAR) AS RELEASECOMMENTS,
                "HOLD_HOURS",
                CAST("NCRID" AS VARCHAR)         AS NCRID,
                CAST("FUTUREHOLDCOMMENTS" AS VARCHAR) AS FUTUREHOLDCOMMENTS,
                {_package_col}
            FROM hold_src
            {where_sql}
            ORDER BY "HOLDTXNDATE" DESC NULLS LAST
            LIMIT ? OFFSET ?
        """
        page_rows = _fetch_dict_rows(conn, page_sql, params + [per_page, offset])

    # Lazy import to avoid circular dependency
    try:
        from mes_dashboard.services.hold_history_service import (
            _clean_text, _format_datetime, _safe_float,
        )
        from mes_dashboard.services.filter_cache import get_workcenter_group as _get_wc_group
    except Exception:
        def _clean_text(v):  # type: ignore[misc]
            return str(v).strip() if v is not None else None
        def _format_datetime(v):  # type: ignore[misc]
            return str(v) if v is not None else None
        def _safe_float(v, d=0.0):  # type: ignore[misc]
            try:
                return float(v) if v is not None else d
            except Exception:
                return d
        def _get_wc_group(v):  # type: ignore[misc]
            return v

    items: List[Dict[str, Any]] = []
    for r in page_rows:
        wc_name = _clean_text(r.get("WORKCENTERNAME"))
        wc_group = _get_wc_group(wc_name) if wc_name else None
        items.append({
            "lotId": _clean_text(r.get("LOT_ID")),
            "workorder": _clean_text(r.get("PJ_WORKORDER")),
            "product": _clean_text(r.get("PRODUCTNAME")),
            "workcenter": wc_group or wc_name,
            "holdReason": _clean_text(r.get("HOLDREASONNAME")),
            "qty": _si(r.get("QTY")),
            "holdDate": _format_datetime(r.get("HOLDTXNDATE")),
            "holdEmp": _clean_text(r.get("HOLDEMP")),
            "holdComment": _clean_text(r.get("HOLDCOMMENTS")),
            "releaseDate": _format_datetime(r.get("RELEASETXNDATE")),
            "releaseEmp": _clean_text(r.get("RELEASEEMP")),
            "releaseComment": _clean_text(r.get("RELEASECOMMENTS")),
            "holdHours": round(_safe_float(r.get("HOLD_HOURS")), 2),
            "ncr": _clean_text(r.get("NCRID")),
            "futureHoldComment": _clean_text(r.get("FUTUREHOLDCOMMENTS")),
            "package": _clean_text(r.get("package")),
        })

    return {
        "items": items,
        "pagination": {
            "page": page,
            "perPage": per_page,
            "total": total,
            "totalPages": total_pages,
        },
    }


# ── Filter clause helpers ─────────────────────────────────────────────────────

def _build_hold_type_clause(hold_type: str) -> str:
    if hold_type == "all":
        return ""
    ht_value = "non-quality" if hold_type == "non-quality" else "quality"
    return f"\"HOLD_TYPE\" = {_sql_str_literal(ht_value)}"


def _build_record_type_clause(
    record_type: str,
    start_date: Optional[str],
    end_date: Optional[str],
) -> str:
    """Build SQL WHERE clause for record_type filter.

    Mirrors _apply_record_type_filter in hold_dataset_cache.
    """
    types = {t.strip().lower() for t in str(record_type or "new").split(",")}
    if types >= {"new", "on_hold", "released"}:
        return ""

    parts: List[str] = []
    if "new" in types and start_date and end_date:
        parts.append(
            f"(CAST(\"hold_day\" AS DATE) >= CAST({_sql_str_literal(start_date)} AS DATE) "
            f"AND CAST(\"hold_day\" AS DATE) <= CAST({_sql_str_literal(end_date)} AS DATE))"
        )
    if "on_hold" in types:
        parts.append("\"RELEASETXNDATE\" IS NULL")
    if "released" in types:
        parts.append("\"RELEASETXNDATE\" IS NOT NULL")

    return "(" + " OR ".join(parts) + ")" if parts else ""


def _build_duration_clause(duration_range: Optional[str]) -> str:
    if not duration_range:
        return ""
    if duration_range == "<4h":
        return "\"HOLD_HOURS\" < 4"
    if duration_range == "4-24h":
        return "\"HOLD_HOURS\" >= 4 AND \"HOLD_HOURS\" < 24"
    if duration_range == "1-3d":
        return "\"HOLD_HOURS\" >= 24 AND \"HOLD_HOURS\" < 72"
    if duration_range == ">3d":
        return "\"HOLD_HOURS\" >= 72"
    return ""


# ── Task 4.1 + 4.6: Entry point ───────────────────────────────────────────────

def try_compute_view_from_spool(
    *,
    query_id: str,
    hold_type: str = "quality",
    reason: Optional[str] = None,
    record_type: str = "new",
    duration_range: Optional[str] = None,
    page: int = 1,
    per_page: int = 50,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    export_mode: bool = False,
) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
    """Try to compute the full view result via DuckDB over the Parquet spool.

    Returns ``(result_dict, meta)`` on success, or ``(None, meta)`` on failure.
    ``meta["view_sql_fallback_reason"]`` is set when returning None.
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
        record_spool_miss("hold_history", query_id)
        return None, {"view_sql_fallback_reason": SQL_FALLBACK_SPOOL_MISS}

    from mes_dashboard.core.heavy_query_telemetry import record_spool_hit
    record_spool_hit("hold_history", query_id)

    started_at = time.time()
    conn = None
    try:
        conn = create_heavy_query_connection()
        _attach_spool_view(conn, parquet_path)

        resolved_start, resolved_end = _resolve_view_date_range(
            conn,
            start_date=start_date,
            end_date=end_date,
        )

        if resolved_start and resolved_end:
            trend = _query_trend(
                conn,
                start_date=resolved_start,
                end_date=resolved_end,
            )
        else:
            trend = {"days": []}
        reason_pareto = _query_reason_pareto(
            conn,
            hold_type=hold_type,
            record_type=record_type,
            start_date=resolved_start,
            end_date=resolved_end,
            duration_range=duration_range,
        )
        duration = _query_duration(
            conn,
            hold_type=hold_type,
            record_type=record_type,
            start_date=resolved_start,
            end_date=resolved_end,
            reason=reason,
        )
        list_result = _query_list(
            conn,
            hold_type=hold_type,
            reason=reason,
            record_type=record_type,
            duration_range=duration_range,
            page=page,
            per_page=0 if export_mode else per_page,
            start_date=resolved_start,
            end_date=resolved_end,
        )

        latency_s = round(time.time() - started_at, 3)
        logger.info(
            "hold_history_sql_runtime: view computed via DuckDB "
            "(query_id=%s latency_s=%.3f)",
            query_id, latency_s,
        )

        result = {
            "trend": trend,
            "reason_pareto": reason_pareto,
            "duration": duration,
            "list": list_result,
        }
        meta = {"view_sql_latency_s": latency_s}
        return result, meta

    except Exception as exc:
        logger.warning(
            "hold_history_sql_runtime: DuckDB view failed (query_id=%s): %s",
            query_id, exc,
        )
        from mes_dashboard.core.heavy_query_telemetry import record_lifecycle_failure
        record_lifecycle_failure("hold_history", reason="runtime_error")
        return None, {"view_sql_fallback_reason": SQL_FALLBACK_RUNTIME_ERROR}
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
