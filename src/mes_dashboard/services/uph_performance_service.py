# -*- coding: utf-8 -*-
"""UPH Performance service: validation, DuckDB view compute, filter-options.

All DuckDB views operate solely on the spool parquet (data-shape §3.29). No
Oracle re-query after the spool is built -- mirrors eap_alarm_service.py's
view-derivation pattern (docs/architecture/service-patterns.md).

Spool schema (v1) columns (data-shape §3.29):
  LOT_ID, EQUIPMENT_ID, EQUIPMENT_FAMILY, EVENT_TIME, PARAMETER_NAME,
  UPH_VALUE (nullable), WORKCENTERNAME (nullable), DB_WB_LABEL (nullable),
  PACKAGE (nullable), PJ_TYPE (nullable), PJ_BOP (nullable),
  PJ_FUNCTION (nullable), coarse_filter_hash

Public API:
  validate_uph_performance_params(date_from, date_to, families, equipment_ids) -> raises ValueError
  get_filter_options(spool_path, filters) -> dict
  get_trend(spool_path, filters, group_by) -> dict
  get_ranking(spool_path, pj_types) -> dict
  get_detail(spool_path, filters, page, per_page) -> dict
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Dict, List, Optional

# SYS-04: 730-day query-range cap (mirrors production_achievement_service.MAX_QUERY_DAYS).
MAX_QUERY_DAYS = 730

_EQUIPMENT_IDS_MAX = 200
_DETAIL_PER_PAGE_MAX = 200

_VALID_FAMILIES = {"GDBA", "GWBA"}


# ── Validation (UPH-01, UPH-02, SYS-04) ───────────────────────────────────────

def validate_uph_performance_params(
    date_from: Optional[str],
    date_to: Optional[str],
    families: Optional[list] = None,
    equipment_ids: Optional[list] = None,
) -> None:
    """Validate UPH Performance coarse filter params.

    Raises:
        ValueError: on missing/invalid dates, range > MAX_QUERY_DAYS (SYS-04),
                    a families[] value outside {GDBA, GWBA} (UPH-02), or
                    equipment_ids overflow (max 200, api-contract.md).
    """
    if not date_from or not date_to:
        raise ValueError("date_from 和 date_to 為必填參數 (LAST_UPDATE_TIME filter required)")

    try:
        start_dt = datetime.strptime(date_from, "%Y-%m-%d")
        end_dt = datetime.strptime(date_to, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError("date_from/date_to 格式錯誤，須為 YYYY-MM-DD") from exc

    if end_dt < start_dt:
        raise ValueError("date_to 不可早於 date_from")
    if (end_dt - start_dt).days > MAX_QUERY_DAYS:
        raise ValueError(f"查詢範圍不可超過 {MAX_QUERY_DAYS} 天")

    if families:
        invalid = [f for f in families if str(f).strip().upper() not in _VALID_FAMILIES]
        if invalid:
            raise ValueError(
                f"families 僅支援 GDBA/GWBA (UPH-02): {invalid!r}"
            )

    if equipment_ids and len(equipment_ids) > _EQUIPMENT_IDS_MAX:
        raise ValueError(f"equipment_ids 不可超過 {_EQUIPMENT_IDS_MAX} 筆")


# ── DuckDB helpers ────────────────────────────────────────────────────────────

def _get_duckdb_conn():
    from mes_dashboard.core.duckdb_runtime import create_heavy_query_connection
    return create_heavy_query_connection()


# Exact-match fine-filter axes shared by filter-options / trend / detail
# (data-shape §3.29 "Fine-filter axes"): request key -> spool column.
_EXACT_FILTER_COLUMNS: Dict[str, str] = {
    "equipment_id": "EQUIPMENT_ID",
    "workcenter_name": "WORKCENTERNAME",
    "package": "PACKAGE",
    "pj_type": "PJ_TYPE",
}


def _build_filter_where(filters: Optional[Dict[str, Any]] = None) -> tuple[str, list]:
    """Build a WHERE clause from fine filters (never inlines user values)."""
    clauses: List[str] = []
    params: List[Any] = []

    if filters is None:
        filters = {}

    for key, column in _EXACT_FILTER_COLUMNS.items():
        values = [str(v) for v in (filters.get(key) or []) if v is not None]
        if values:
            placeholders = ", ".join("?" for _ in values)
            clauses.append(f"{column} IN ({placeholders})")
            params.extend(values)

    if clauses:
        return "WHERE " + " AND ".join(clauses), params
    return "", params


# ── Filter options ────────────────────────────────────────────────────────────

def get_filter_options(spool_path: str, filters: Optional[Dict[str, Any]] = None) -> dict:
    """Distinct fine-filter options derived from the DuckDB spool (data-shape §3.29).

    NULL column values are excluded from option lists.
    """
    conn = _get_duckdb_conn()
    try:
        where_sql, where_params = _build_filter_where(filters)

        def _distinct(column: str) -> List[str]:
            return [
                row[0]
                for row in conn.execute(f"""
                    SELECT DISTINCT {column}
                    FROM read_parquet(?)
                    {where_sql}
                    ORDER BY {column}
                """, [spool_path, *where_params]).fetchall()
                if row[0] is not None
            ]

        return {
            "equipment_id_options": _distinct("EQUIPMENT_ID"),
            "workcenter_name_options": _distinct("WORKCENTERNAME"),
            "package_options": _distinct("PACKAGE"),
            "pj_type_options": _distinct("PJ_TYPE"),
        }
    finally:
        conn.close()


# ── Trend ─────────────────────────────────────────────────────────────────────

# Groupable dimensions for trend (data-shape §3.29): request value -> spool column.
# Closed enum -- routes validate against these keys before calling the service.
GROUP_DIMENSIONS: Dict[str, str] = {
    "equipment_id": "EQUIPMENT_ID",
    "family": "EQUIPMENT_FAMILY",
    "model": "MODEL",
    "package": "PACKAGE",
}


def get_trend(
    spool_path: str,
    filters: Optional[Dict[str, Any]] = None,
    group_by: str = "family",
) -> dict:
    """Hourly (native M[60]) avg-UPH trend, stacked by *group_by* dimension.

    Returns:
        {labels: [...], series: [{name, data: [number|null, ...]}], group_by}

    A group's missing hour bucket is ``null`` in ``data[]``, never ``0`` -- a
    gap must not visually imply zero output (data-shape §3.29 Trend).
    """
    if group_by not in GROUP_DIMENSIONS:
        raise ValueError(f"invalid trend group_by: {group_by!r}")

    conn = _get_duckdb_conn()
    try:
        where_sql, where_params = _build_filter_where(filters)
        grp_col = GROUP_DIMENSIONS[group_by]
        ts_expr = "strftime(EVENT_TIME, '%Y-%m-%d %H:00')"
        null_guard = f"{grp_col} IS NOT NULL"

        rows = conn.execute(f"""
            SELECT
                {ts_expr} AS label,
                {grp_col} AS grp,
                AVG(UPH_VALUE) AS avg_uph
            FROM read_parquet(?)
            {where_sql}
            {"AND" if where_sql else "WHERE"} {null_guard}
            GROUP BY label, grp
            ORDER BY label, grp
        """, [spool_path, *where_params]).fetchall()

        if not rows:
            return {"labels": [], "series": [], "group_by": group_by}

        labels = sorted({str(r[0]) for r in rows})
        groups = sorted({str(r[1]) for r in rows})

        data_map: Dict[str, Dict[str, Optional[float]]] = {g: {} for g in groups}
        for label, grp, avg_uph in rows:
            value = None if avg_uph is None else round(float(avg_uph), 2)
            data_map[str(grp)][str(label)] = value

        series = [
            {"name": g, "data": [data_map[g].get(lbl) for lbl in labels]}
            for g in groups
        ]

        return {"labels": labels, "series": series, "group_by": group_by}
    finally:
        conn.close()


# ── Ranking ───────────────────────────────────────────────────────────────────

def get_ranking(spool_path: str, pj_types: Optional[List[str]] = None) -> dict:
    """Per-equipment (further groupable by pj_type client-side) avg-UPH ranking.

    ``pj_types`` is this endpoint's OWN fine-filter axis, independent of the
    page's global filters (data-shape §3.29 Ranking) -- it is NOT part of the
    spool key and does not read/write the global pj_type filter.

    Sorted ascending by avg_uph (lowest-UPH equipment first -- the point is
    finding underperformers). ``avg_uph`` is ``null`` (never a divide-by-zero
    ``0``) for an equipment/pj_type combination with zero rows carrying a
    non-null UPH_VALUE.
    """
    conn = _get_duckdb_conn()
    try:
        where_sql = ""
        where_params: List[Any] = []
        cleaned_pj_types = [str(v) for v in (pj_types or []) if v is not None and str(v).strip()]
        if cleaned_pj_types:
            placeholders = ", ".join("?" for _ in cleaned_pj_types)
            where_sql = f"WHERE PJ_TYPE IN ({placeholders})"
            where_params = list(cleaned_pj_types)

        rows = conn.execute(f"""
            SELECT
                EQUIPMENT_ID,
                MAX(WORKCENTERNAME) AS workcenter_name,
                MAX(DB_WB_LABEL) AS db_wb_label,
                PJ_TYPE,
                AVG(UPH_VALUE) AS avg_uph,
                COUNT(UPH_VALUE) AS sample_count
            FROM read_parquet(?)
            {where_sql}
            GROUP BY EQUIPMENT_ID, PJ_TYPE
            ORDER BY avg_uph ASC NULLS LAST, EQUIPMENT_ID
        """, [spool_path, *where_params]).fetchall()

        items = []
        for r in rows:
            items.append({
                "equipment_id": str(r[0]) if r[0] is not None else None,
                "workcenter_name": str(r[1]) if r[1] is not None else None,
                "db_wb_label": str(r[2]) if r[2] is not None else None,
                "pj_type": str(r[3]) if r[3] is not None else None,
                "avg_uph": round(float(r[4]), 2) if r[4] is not None else None,
                "sample_count": int(r[5] or 0),
            })

        pj_type_rows = conn.execute(f"""
            SELECT DISTINCT PJ_TYPE FROM read_parquet(?) {where_sql} ORDER BY PJ_TYPE
        """, [spool_path, *where_params]).fetchall()
        pj_type_list = [str(r[0]) for r in pj_type_rows if r[0] is not None]

        return {"items": items, "pj_types": pj_type_list}
    finally:
        conn.close()


# ── Detail ────────────────────────────────────────────────────────────────────

def get_detail(
    spool_path: str,
    filters: Optional[Dict[str, Any]] = None,
    page: int = 1,
    per_page: int = 50,
) -> dict:
    """Paginated per-event UPH detail rows from the DuckDB spool.

    Returns:
        {rows: [{lot_id, equipment_id, event_time, uph_value, package, pj_type}],
         meta: {page, per_page, total_count, total_pages}}

    Pagination: per_page max 200 (mirrors EA-04 detail pagination).
    """
    per_page = min(max(1, int(per_page)), _DETAIL_PER_PAGE_MAX)
    page = max(1, int(page))
    offset = (page - 1) * per_page

    conn = _get_duckdb_conn()
    try:
        where_sql, where_params = _build_filter_where(filters)

        total_count = int(conn.execute(
            f"SELECT COUNT(*) FROM read_parquet(?) {where_sql}",
            [spool_path, *where_params],
        ).fetchone()[0] or 0)
        total_pages = max(1, math.ceil(total_count / per_page)) if total_count > 0 else 1

        raw_rows = conn.execute(f"""
            SELECT LOT_ID, EQUIPMENT_ID, MODEL, EVENT_TIME, UPH_VALUE, PACKAGE, PJ_TYPE
            FROM read_parquet(?)
            {where_sql}
            ORDER BY EVENT_TIME DESC, LOT_ID
            LIMIT ? OFFSET ?
        """, [spool_path, *where_params, per_page, offset]).fetchall()

        def _fmt_ts(v) -> Optional[str]:
            if v is None:
                return None
            if hasattr(v, "isoformat"):
                return v.isoformat()
            return str(v)

        rows = []
        for r in raw_rows:
            rows.append({
                "lot_id": str(r[0]) if r[0] is not None else None,
                "equipment_id": str(r[1]) if r[1] is not None else None,
                "model": str(r[2]) if r[2] is not None else None,
                "event_time": _fmt_ts(r[3]),
                "uph_value": round(float(r[4]), 2) if r[4] is not None else None,
                "package": str(r[5]) if r[5] is not None else None,
                "pj_type": str(r[6]) if r[6] is not None else None,
            })

        return {
            "rows": rows,
            "meta": {
                "page": page,
                "per_page": per_page,
                "total_count": total_count,
                "total_pages": total_pages,
            },
        }
    finally:
        conn.close()
