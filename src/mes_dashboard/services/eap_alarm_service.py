# -*- coding: utf-8 -*-
"""EAP ALARM service: validation, DuckDB view compute, filter-options.

All DuckDB views operate solely on the spool parquet (EA-02/EA-04).
No Oracle re-query after the spool is built.

Public API:
  validate_eap_alarm_params(date_from, date_to, eqp_types)  → raises ValueError
  get_filter_options(spool_path, filters) → dict
  get_summary(spool_path, filters) → dict
  get_pareto(spool_path, filters) → dict
  get_trend(spool_path, filters, granularity) → dict
  get_detail(spool_path, filters, page, per_page) → dict
"""

from __future__ import annotations

import json
import logging
import math
from typing import Any, Dict, List, Optional

from mes_dashboard.services.eap_alarm_cache import decode_alarm_category

logger = logging.getLogger("mes_dashboard.eap_alarm_service")

# ── EA-07: EQP type closed enum ───────────────────────────────────────────────
_VALID_EQP_TYPES: frozenset[str] = frozenset({
    "GDBA", "GCBA", "GWBA", "GWBK", "GPRA",
    "GTMH", "GWMT", "GDSD", "GWAC", "GPTA",
})

# Detail pagination cap (data-shape §3.17)
_DETAIL_PER_PAGE_MAX = 200


# ── Validation ────────────────────────────────────────────────────────────────

def validate_eap_alarm_params(
    date_from: Optional[str],
    date_to: Optional[str],
    eqp_types: Optional[list],
) -> None:
    """Validate coarse filter params for EAP ALARM.

    Raises:
        ValueError with descriptive message on any violation.

    Rules enforced:
      - EA-03: date_from and date_to are both required
      - EA-07: eqp_types must be non-empty and all values in the closed enum
    """
    if not date_from or not date_to:
        raise ValueError("LAST_UPDATE_TIME filter required (date_from and date_to must be provided)")

    if not eqp_types:
        raise ValueError("eqp_types must be non-empty")

    invalid = [t for t in eqp_types if t not in _VALID_EQP_TYPES]
    if invalid:
        raise ValueError(
            f"invalid eqp_types: {invalid!r}. "
            f"Allowed values: {sorted(_VALID_EQP_TYPES)}"
        )


# ── DuckDB helpers ────────────────────────────────────────────────────────────

def _get_duckdb_conn():
    """Create a DuckDB connection via the project's runtime helper."""
    from mes_dashboard.core.duckdb_runtime import create_heavy_query_connection
    return create_heavy_query_connection()


def _build_filter_where(filters: Optional[Dict[str, Any]], alias: str = "") -> tuple[str, dict]:
    """Build a WHERE clause fragment from fine filters.

    Supported filter keys:
      alarm_text (list[str])  — fuzzy ILIKE match (OR across values)
      alarm_category_code (list[int])  — exact match on ALARM_CATEGORY_CODE
      equipment_id (list[str])  — exact match on EQP_ID

    Returns (where_sql, params) where params is a flat dict for DuckDB's
    positional binding (DuckDB supports $1/$2 or Python bindings via execute).
    Uses string interpolation for simplicity with list values (trusted server-side only).
    """
    prefix = f"{alias}." if alias else ""
    clauses = []

    if filters is None:
        filters = {}

    # alarm_text: fuzzy ILIKE with OR across selected values
    alarm_texts = [str(t) for t in (filters.get("alarm_text") or []) if t is not None]
    if alarm_texts:
        like_parts = " OR ".join(
            f"{prefix}ALARM_TEXT ILIKE '%' || '{_escape_like(t)}' || '%'"
            for t in alarm_texts
        )
        clauses.append(f"({like_parts})")

    # alarm_category_code: exact int match
    alarm_codes = filters.get("alarm_category_code")
    if alarm_codes:
        try:
            codes = [int(c) for c in alarm_codes]
            code_list = ", ".join(str(c) for c in codes)
            clauses.append(f"{prefix}ALARM_CATEGORY_CODE IN ({code_list})")
        except (TypeError, ValueError):
            pass

    # equipment_id: exact string match
    eqp_ids = [str(e) for e in (filters.get("equipment_id") or []) if e is not None]
    if eqp_ids:
        quoted = ", ".join(f"'{_escape_sql(e)}'" for e in eqp_ids)
        clauses.append(f"{prefix}EQP_ID IN ({quoted})")

    if clauses:
        return "WHERE " + " AND ".join(clauses), {}
    return "", {}


def _escape_like(s: str) -> str:
    """Escape single-quotes and LIKE wildcards in alarm_text filter values."""
    return s.replace("'", "''")


def _escape_sql(s: str) -> str:
    """Escape single-quotes in SQL literal values."""
    return s.replace("'", "''")


# ── Filter options ────────────────────────────────────────────────────────────

def get_filter_options(spool_path: str, filters: Optional[Dict[str, Any]] = None) -> dict:
    """Derive distinct filter option lists from the DuckDB spool (EA-02).

    Returns:
        {
          alarm_text_options: list[str | null],
          alarm_category_options: list[{code: int, label: str}],
          equipment_id_options: list[str],
        }
    """
    conn = _get_duckdb_conn()
    try:
        where_sql, _ = _build_filter_where(filters)

        # alarm_text distinct (non-null only for options list)
        sql_text = f"""
            SELECT DISTINCT ALARM_TEXT
            FROM read_parquet('{spool_path}')
            {where_sql}
            ORDER BY ALARM_TEXT
        """
        alarm_texts: List[Optional[str]] = [
            row[0] for row in conn.execute(sql_text).fetchall()
            if row[0] is not None
        ]

        # alarm_category_code+label distinct pairs
        sql_cat = f"""
            SELECT DISTINCT ALARM_CATEGORY_CODE, ALARM_CATEGORY
            FROM read_parquet('{spool_path}')
            {where_sql}
            ORDER BY ALARM_CATEGORY_CODE NULLS LAST
        """
        alarm_categories = []
        for row in conn.execute(sql_cat).fetchall():
            code = row[0]
            label = row[1] if row[1] is not None else decode_alarm_category(code)
            alarm_categories.append({"code": code, "label": label})

        # equipment_id distinct
        sql_eqp = f"""
            SELECT DISTINCT EQP_ID
            FROM read_parquet('{spool_path}')
            {where_sql}
            ORDER BY EQP_ID
        """
        eqp_ids: List[str] = [
            row[0] for row in conn.execute(sql_eqp).fetchall()
            if row[0] is not None
        ]

        return {
            "alarm_text_options": alarm_texts,
            "alarm_category_options": alarm_categories,
            "equipment_id_options": eqp_ids,
        }
    finally:
        conn.close()


# ── Summary ───────────────────────────────────────────────────────────────────

def get_summary(spool_path: str, filters: Optional[Dict[str, Any]] = None) -> dict:
    """Compute summary stats from the DuckDB spool.

    Returns:
        {
          total_alarm_count: int,
          affected_equipment_count: int,
          affected_lot_count: int,
          top_equipment: {eqp_id: str, alarm_count: int} | null,
        }
    """
    conn = _get_duckdb_conn()
    try:
        where_sql, _ = _build_filter_where(filters)

        sql_agg = f"""
            SELECT
                COUNT(*) AS total_alarm_count,
                COUNT(DISTINCT EQP_ID) AS affected_equipment_count,
                COUNT(DISTINCT LOT_ID) AS affected_lot_count
            FROM read_parquet('{spool_path}')
            {where_sql}
        """
        row = conn.execute(sql_agg).fetchone()
        total_alarm_count = int(row[0] or 0)
        affected_equipment_count = int(row[1] or 0)
        affected_lot_count = int(row[2] or 0)

        # top_equipment: eqp with most alarms
        sql_top = f"""
            SELECT EQP_ID, COUNT(*) AS alarm_count
            FROM read_parquet('{spool_path}')
            {where_sql}
            GROUP BY EQP_ID
            ORDER BY alarm_count DESC
            LIMIT 1
        """
        top_row = conn.execute(sql_top).fetchone()
        top_equipment = None
        if top_row and top_row[0]:
            top_equipment = {"eqp_id": str(top_row[0]), "alarm_count": int(top_row[1])}

        return {
            "total_alarm_count": total_alarm_count,
            "affected_equipment_count": affected_equipment_count,
            "affected_lot_count": affected_lot_count,
            "top_equipment": top_equipment,
        }
    finally:
        conn.close()


# ── Pareto ────────────────────────────────────────────────────────────────────

def get_pareto(spool_path: str, filters: Optional[Dict[str, Any]] = None) -> dict:
    """Compute top-50 alarm_text Pareto from the DuckDB spool.

    Returns:
        {
          items: [{alarm_text: str, count: int, cumulative_pct: float}],
          total: int,
        }
    """
    conn = _get_duckdb_conn()
    try:
        where_sql, _ = _build_filter_where(filters)

        sql_total = f"""
            SELECT COUNT(*) FROM read_parquet('{spool_path}') {where_sql}
        """
        total_row = conn.execute(sql_total).fetchone()
        total = int(total_row[0] or 0)

        if total == 0:
            return {"items": [], "total": 0}

        sql_pareto = f"""
            SELECT
                COALESCE(ALARM_TEXT, '(無說明)') AS alarm_text,
                COUNT(*) AS cnt
            FROM read_parquet('{spool_path}')
            {where_sql}
            GROUP BY ALARM_TEXT
            ORDER BY cnt DESC
            LIMIT 50
        """
        rows = conn.execute(sql_pareto).fetchall()

        items = []
        cumulative = 0
        for row in rows:
            alarm_text = str(row[0])
            count = int(row[1])
            cumulative += count
            items.append({
                "alarm_text": alarm_text,
                "count": count,
                "cumulative_pct": round(cumulative / total * 100, 2) if total > 0 else 0.0,
            })

        return {"items": items, "total": total}
    finally:
        conn.close()


# ── Trend ─────────────────────────────────────────────────────────────────────

def get_trend(
    spool_path: str,
    filters: Optional[Dict[str, Any]] = None,
    granularity: str = "day",
) -> dict:
    """Compute stacked trend (by eqp_type) from the DuckDB spool.

    Args:
        granularity: "day" (ISO date) or "hour" (ISO datetime YYYY-MM-DD HH:00)

    Returns:
        {
          labels: list[str],
          series: [{eqp_type: str, data: list[int]}],
        }
    """
    conn = _get_duckdb_conn()
    try:
        where_sql, _ = _build_filter_where(filters)

        if granularity == "hour":
            ts_expr = "strftime(ALARM_TIME, '%Y-%m-%d %H:00')"
        else:
            ts_expr = "strftime(ALARM_TIME, '%Y-%m-%d')"

        sql_trend = f"""
            SELECT
                {ts_expr} AS label,
                EQP_TYPE,
                COUNT(*) AS cnt
            FROM read_parquet('{spool_path}')
            {where_sql}
            GROUP BY label, EQP_TYPE
            ORDER BY label, EQP_TYPE
        """
        rows = conn.execute(sql_trend).fetchall()

        if not rows:
            return {"labels": [], "series": []}

        # Build label list and series map
        label_set: dict[str, int] = {}
        eqp_type_counts: dict[str, dict[str, int]] = {}

        for row in rows:
            label = str(row[0])
            eqp_type = str(row[1]) if row[1] is not None else "UNKNOWN"
            cnt = int(row[2])

            if label not in label_set:
                label_set[label] = len(label_set)
            if eqp_type not in eqp_type_counts:
                eqp_type_counts[eqp_type] = {}
            eqp_type_counts[eqp_type][label] = cnt

        labels = sorted(label_set.keys())
        series = []
        for eqp_type in sorted(eqp_type_counts.keys()):
            data = [eqp_type_counts[eqp_type].get(label, 0) for label in labels]
            series.append({"eqp_type": eqp_type, "data": data})

        return {"labels": labels, "series": series}
    finally:
        conn.close()


# ── Detail ────────────────────────────────────────────────────────────────────

def get_detail(
    spool_path: str,
    filters: Optional[Dict[str, Any]] = None,
    page: int = 1,
    per_page: int = 50,
) -> dict:
    """Return paginated detail rows from the DuckDB spool (EA-04).

    Returns:
        {
          rows: [{event_id, eqp_id, eqp_type, lot_id, alarm_text,
                  alarm_category, alarm_time, detail_params}],
          meta: {page, per_page, total_count, total_pages},
        }

    per_page capped at 200 per data-shape §3.17.
    """
    per_page = min(max(1, int(per_page)), _DETAIL_PER_PAGE_MAX)
    page = max(1, int(page))
    offset = (page - 1) * per_page

    conn = _get_duckdb_conn()
    try:
        where_sql, _ = _build_filter_where(filters)

        sql_count = f"""
            SELECT COUNT(*) FROM read_parquet('{spool_path}') {where_sql}
        """
        total_count = int(conn.execute(sql_count).fetchone()[0] or 0)
        total_pages = max(1, math.ceil(total_count / per_page)) if total_count > 0 else 1

        sql_rows = f"""
            SELECT
                EVENT_ID,
                EQP_ID,
                EQP_TYPE,
                LOT_ID,
                ALARM_TEXT,
                ALARM_CATEGORY,
                ALARM_TIME,
                DETAIL_PARAMS
            FROM read_parquet('{spool_path}')
            {where_sql}
            ORDER BY ALARM_TIME DESC, EVENT_ID
            LIMIT {per_page} OFFSET {offset}
        """
        raw_rows = conn.execute(sql_rows).fetchall()

        rows = []
        for r in raw_rows:
            event_id = str(r[0]) if r[0] is not None else None
            eqp_id = str(r[1]) if r[1] is not None else None
            eqp_type = str(r[2]) if r[2] is not None else None
            lot_id = str(r[3]) if r[3] is not None else None
            alarm_text = str(r[4]) if r[4] is not None else None
            alarm_category = str(r[5]) if r[5] is not None else decode_alarm_category(None)
            # ALARM_TIME: DuckDB returns as datetime; format to ISO 8601
            alarm_time_raw = r[6]
            if alarm_time_raw is None:
                alarm_time = None
            elif hasattr(alarm_time_raw, "isoformat"):
                alarm_time = alarm_time_raw.isoformat()
            else:
                alarm_time = str(alarm_time_raw)

            # DETAIL_PARAMS: stored as JSON string; parse to object or leave null
            detail_params_raw = r[7]
            if detail_params_raw is None:
                detail_params = None
            else:
                try:
                    detail_params = json.loads(str(detail_params_raw))
                except (json.JSONDecodeError, TypeError):
                    detail_params = {"_raw": str(detail_params_raw)}

            rows.append({
                "event_id": event_id,
                "eqp_id": eqp_id,
                "eqp_type": eqp_type,
                "lot_id": lot_id,
                "alarm_text": alarm_text,
                "alarm_category": alarm_category,
                "alarm_time": alarm_time,
                "detail_params": detail_params,
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
