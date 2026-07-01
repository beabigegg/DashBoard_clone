# -*- coding: utf-8 -*-
"""EAP ALARM service: validation, DuckDB view compute, filter-options.

All DuckDB views operate solely on the spool parquet (EA-02/EA-04).
No Oracle re-query after the spool is built.

Spool schema (v2): one row = one alarm occurrence (SET event + optional CLEAR).
  ALARM_ID, EQP_ID, EQP_TYPE, LOT_ID, ALARM_TEXT, ALARM_CATEGORY_CODE,
  ALARM_START, ALARM_END (nullable), DURATION_SECONDS (nullable),
  DETAIL_PARAMS, eqp_types_filter

Public API:
  validate_eap_alarm_params(date_from, date_to, machines)  → raises ValueError
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

from mes_dashboard.services.eap_alarm_cache import decode_alarm_category  # noqa: F401

logger = logging.getLogger("mes_dashboard.eap_alarm_service")

_DETAIL_PER_PAGE_MAX = 200


# ── Validation ────────────────────────────────────────────────────────────────

_LOT_IDS_MAX = 200


def validate_eap_alarm_params(
    date_from: Optional[str],
    date_to: Optional[str],
    eqp_types: Optional[list] = None,
    lot_ids: Optional[list] = None,
    pj_types: Optional[list] = None,
    product_lines: Optional[list] = None,
    pj_bops: Optional[list] = None,
) -> None:
    """Validate EAP ALARM coarse filter params (EA-03, EA-07, EA-08, EA-09).

    Raises:
        ValueError: on missing dates, non-string/blank eqp_type entries (EA-07),
                    all-empty filter axes (EA-08), or lot_ids overflow (EA-09).
    """
    if not date_from or not date_to:
        raise ValueError("LAST_UPDATE_TIME filter required (date_from and date_to must be provided)")

    # Normalize eqp_types — validated like lot_ids: reject non-string/blank entries,
    # keep every non-empty stripped value, no closed-enum membership check (EA-07,
    # D-7). NOTE: despite the field name, values are full EQUIPMENT_ID strings
    # (e.g. "GWBK-0241"), not 4-char type codes.
    cleaned_eqp = []
    if eqp_types:
        invalid = [m for m in eqp_types if not isinstance(m, str) or not m.strip()]
        if invalid:
            raise ValueError(f"invalid machine values: {invalid!r}")
        cleaned_eqp = [m for m in eqp_types if m.strip()]

    # Normalize lot_ids — strip whitespace, drop empties, dedup
    cleaned_lots: list[str] = []
    if lot_ids:
        seen: set[str] = set()
        for raw in lot_ids:
            v = str(raw).strip() if raw is not None else ""
            if v and v not in seen:
                seen.add(v)
                cleaned_lots.append(v)
    if len(cleaned_lots) > _LOT_IDS_MAX:
        raise ValueError(
            f"lot_ids exceeds max {_LOT_IDS_MAX} entries (EA-09): got {len(cleaned_lots)}"
        )

    # Check product_dims presence (any of pj_types / product_lines / pj_bops non-empty)
    has_product_dims = bool(pj_types) or bool(product_lines) or bool(pj_bops)

    # EA-08: at least one of {eqp_types, lot_ids, product_dims} required
    if not cleaned_eqp and not cleaned_lots and not has_product_dims:
        raise ValueError(
            "at least one of {eqp_types, lot_ids, product_dims} must be provided (EA-08)"
        )


# ── DuckDB helpers ────────────────────────────────────────────────────────────

def _get_duckdb_conn():
    from mes_dashboard.core.duckdb_runtime import create_heavy_query_connection
    return create_heavy_query_connection()


def _escape_like(s: str) -> str:
    return s.replace("'", "''")


def _escape_sql(s: str) -> str:
    return s.replace("'", "''")


def _build_filter_where(filters: Optional[Dict[str, Any]], alias: str = "") -> tuple[str, dict]:
    """Build WHERE clause from fine filters.

    Supported keys:
      alarm_text (list[str])   — ILIKE match on ALARM_TEXT
      equipment_id (list[str]) — exact match on EQP_ID
    """
    prefix = f"{alias}." if alias else ""
    clauses = []

    if filters is None:
        filters = {}

    alarm_texts = [str(t) for t in (filters.get("alarm_text") or []) if t is not None]
    if alarm_texts:
        like_parts = " OR ".join(
            f"{prefix}ALARM_TEXT ILIKE '%' || '{_escape_like(t)}' || '%'"
            for t in alarm_texts
        )
        clauses.append(f"({like_parts})")

    eqp_ids = [str(e) for e in (filters.get("equipment_id") or []) if e is not None]
    if eqp_ids:
        quoted = ", ".join(f"'{_escape_sql(e)}'" for e in eqp_ids)
        clauses.append(f"{prefix}EQP_ID IN ({quoted})")

    if clauses:
        return "WHERE " + " AND ".join(clauses), {}
    return "", {}


# ── Filter options ────────────────────────────────────────────────────────────

def get_filter_options(spool_path: str, filters: Optional[Dict[str, Any]] = None) -> dict:
    """Distinct filter options from spool.

    Returns:
        {
          alarm_text_options: list[str],
          equipment_id_options: list[str],
        }
    """
    conn = _get_duckdb_conn()
    try:
        where_sql, _ = _build_filter_where(filters)

        alarm_texts: List[str] = [
            row[0]
            for row in conn.execute(f"""
                SELECT DISTINCT ALARM_TEXT
                FROM read_parquet('{spool_path}')
                {where_sql}
                ORDER BY ALARM_TEXT
            """).fetchall()
            if row[0] is not None
        ]

        eqp_ids: List[str] = [
            row[0]
            for row in conn.execute(f"""
                SELECT DISTINCT EQP_ID
                FROM read_parquet('{spool_path}')
                {where_sql}
                ORDER BY EQP_ID
            """).fetchall()
            if row[0] is not None
        ]

        return {
            "alarm_text_options": alarm_texts,
            "equipment_id_options": eqp_ids,
        }
    finally:
        conn.close()


# ── Summary ───────────────────────────────────────────────────────────────────

def get_summary(spool_path: str, filters: Optional[Dict[str, Any]] = None) -> dict:
    """Compute summary stats from the DuckDB spool.

    Returns:
        {
          total_alarm_count: int,        — total alarm occurrences
          affected_equipment_count: int,
          unresolved_count: int,         — alarms without a CLEAR in the window
          avg_duration_minutes: float | null,  — avg resolution time (resolved only)
        }
    """
    conn = _get_duckdb_conn()
    try:
        where_sql, _ = _build_filter_where(filters)

        row = conn.execute(f"""
            SELECT
                COUNT(*) AS total_alarm_count,
                COUNT(DISTINCT EQP_ID) AS affected_equipment_count,
                SUM(CASE WHEN ALARM_END IS NULL THEN 1 ELSE 0 END) AS unresolved_count,
                AVG(DURATION_SECONDS) AS avg_duration_seconds
            FROM read_parquet('{spool_path}')
            {where_sql}
        """).fetchone()

        total_alarm_count = int(row[0] or 0)
        affected_equipment_count = int(row[1] or 0)
        unresolved_count = int(row[2] or 0)
        avg_dur_sec = row[3]
        avg_duration_minutes = (
            round(float(avg_dur_sec) / 60, 1) if avg_dur_sec is not None else None
        )

        return {
            "total_alarm_count": total_alarm_count,
            "affected_equipment_count": affected_equipment_count,
            "unresolved_count": unresolved_count,
            "avg_duration_minutes": avg_duration_minutes,
        }
    finally:
        conn.close()


# ── Pareto ────────────────────────────────────────────────────────────────────

def get_pareto(spool_path: str, filters: Optional[Dict[str, Any]] = None) -> dict:
    """Top-50 alarm_text Pareto (count of occurrences).

    Returns:
        {
          items: [{alarm_text, count, cumulative_pct}],
          total: int,
        }
    """
    conn = _get_duckdb_conn()
    try:
        where_sql, _ = _build_filter_where(filters)

        total = int(conn.execute(
            f"SELECT COUNT(*) FROM read_parquet('{spool_path}') {where_sql}"
        ).fetchone()[0] or 0)

        if total == 0:
            return {"items": [], "total": 0}

        rows = conn.execute(f"""
            SELECT
                COALESCE(ALARM_TEXT, '(無說明)') AS alarm_text,
                COUNT(*) AS cnt
            FROM read_parquet('{spool_path}')
            {where_sql}
            GROUP BY ALARM_TEXT
            ORDER BY cnt DESC
            LIMIT 50
        """).fetchall()

        items = []
        cumulative = 0
        for row in rows:
            count = int(row[1])
            cumulative += count
            items.append({
                "alarm_text": str(row[0]),
                "count": count,
                "cumulative_pct": round(cumulative / total * 100, 2),
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
    """Stacked trend by ALARM_TEXT (top 10), bucketed by ALARM_START.

    Returns:
        {
          labels: list[str],
          series: [{alarm_text, data: list[int]}],
        }
    """
    conn = _get_duckdb_conn()
    try:
        where_sql, _ = _build_filter_where(filters)

        if granularity == "hour":
            ts_expr = "strftime(ALARM_START, '%Y-%m-%d %H:00')"
        else:
            ts_expr = "strftime(ALARM_START, '%Y-%m-%d')"

        # Limit to top-10 alarm texts to keep chart readable
        top_texts = [
            row[0]
            for row in conn.execute(f"""
                SELECT COALESCE(ALARM_TEXT, '(無說明)') AS alarm_text
                FROM read_parquet('{spool_path}')
                {where_sql}
                GROUP BY alarm_text
                ORDER BY COUNT(*) DESC
                LIMIT 10
            """).fetchall()
        ]

        if not top_texts:
            return {"labels": [], "series": []}

        quoted = ", ".join(f"'{_escape_sql(t)}'" for t in top_texts)
        rows = conn.execute(f"""
            SELECT
                {ts_expr} AS label,
                COALESCE(ALARM_TEXT, '(無說明)') AS alarm_text,
                COUNT(*) AS cnt
            FROM read_parquet('{spool_path}')
            {where_sql}
            {"AND" if where_sql else "WHERE"} COALESCE(ALARM_TEXT, '(無說明)') IN ({quoted})
            GROUP BY label, alarm_text
            ORDER BY label, alarm_text
        """).fetchall()

        if not rows:
            return {"labels": [], "series": []}

        label_set: dict[str, int] = {}
        text_counts: dict[str, dict[str, int]] = {}

        for row in rows:
            label = str(row[0])
            alarm_text = str(row[1])
            cnt = int(row[2])
            if label not in label_set:
                label_set[label] = len(label_set)
            if alarm_text not in text_counts:
                text_counts[alarm_text] = {}
            text_counts[alarm_text][label] = cnt

        labels = sorted(label_set.keys())
        series = [
            {"alarm_text": at, "data": [text_counts[at].get(lbl, 0) for lbl in labels]}
            for at in top_texts
            if at in text_counts
        ]

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
    """Paginated alarm occurrences from the DuckDB spool.

    Returns:
        {
          rows: [{alarm_id, eqp_id, eqp_type, lot_id, alarm_text,
                  alarm_category_code, alarm_start, alarm_end,
                  duration_seconds, detail_params}],
          meta: {page, per_page, total_count, total_pages},
        }
    """
    per_page = min(max(1, int(per_page)), _DETAIL_PER_PAGE_MAX)
    page = max(1, int(page))
    offset = (page - 1) * per_page

    conn = _get_duckdb_conn()
    try:
        where_sql, _ = _build_filter_where(filters)

        total_count = int(conn.execute(
            f"SELECT COUNT(*) FROM read_parquet('{spool_path}') {where_sql}"
        ).fetchone()[0] or 0)
        total_pages = max(1, math.ceil(total_count / per_page)) if total_count > 0 else 1

        raw_rows = conn.execute(f"""
            SELECT
                ALARM_ID,
                EQP_ID,
                EQP_TYPE,
                LOT_ID,
                ALARM_TEXT,
                ALARM_CATEGORY_CODE,
                ALARM_START,
                ALARM_END,
                DURATION_SECONDS,
                DETAIL_PARAMS
            FROM read_parquet('{spool_path}')
            {where_sql}
            ORDER BY ALARM_START DESC, ALARM_ID
            LIMIT {per_page} OFFSET {offset}
        """).fetchall()

        def _fmt_ts(v) -> Optional[str]:
            if v is None:
                return None
            if hasattr(v, "isoformat"):
                return v.isoformat()
            s = str(v)
            m = s if len(s) >= 19 else None
            return m or s

        rows = []
        for r in raw_rows:
            detail_params_raw = r[9]
            if detail_params_raw is None:
                detail_params = None
            else:
                try:
                    detail_params = json.loads(str(detail_params_raw))
                except (json.JSONDecodeError, TypeError):
                    detail_params = {"_raw": str(detail_params_raw)}

            duration = r[8]
            rows.append({
                "alarm_id":           str(r[0]) if r[0] is not None else None,
                "eqp_id":             str(r[1]) if r[1] is not None else None,
                "eqp_type":           str(r[2]) if r[2] is not None else None,
                "lot_id":             str(r[3]) if r[3] is not None else None,
                "alarm_text":         str(r[4]) if r[4] is not None else None,
                "alarm_category_code":int(r[5]) if r[5] is not None else None,
                "alarm_start":        _fmt_ts(r[6]),
                "alarm_end":          _fmt_ts(r[7]),
                "duration_seconds":   round(float(duration), 1) if duration is not None else None,
                "detail_params":      detail_params,
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
