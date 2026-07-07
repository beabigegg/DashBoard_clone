# -*- coding: utf-8 -*-
"""EAP ALARM service: validation, DuckDB view compute, filter-options.

All DuckDB views operate solely on the spool parquet (EA-02/EA-04).
No Oracle re-query after the spool is built.

Spool schema (v5): one row = one alarm occurrence (SET event + optional CLEAR).
  ALARM_ID, EQP_ID, EQP_TYPE, LOT_ID, ALARM_TEXT, ALARM_CATEGORY_CODE,
  ALARM_START, ALARM_END (nullable), DURATION_SECONDS (nullable),
  DETAIL_PARAMS, PJ_TYPE (nullable), PRODUCT_LINE (nullable),
  PJ_BOP (nullable), ALARM_SOURCE (v5: raw EVENT_TYPE — 'EQP_SECS_ALARM'
  Shape A / 'EQP_SECS_EVENT' Shape B alarm-alias, EA-EVT), eqp_types_filter

Public API:
  validate_eap_alarm_params(date_from, date_to, machines)  → raises ValueError
  get_filter_options(spool_path, filters) → dict
  get_summary(spool_path, filters) → dict
  get_pareto(spool_path, filters, dim) → dict
  get_trend(spool_path, filters, granularity, group_by) → dict
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


def _escape_sql(s: str) -> str:
    return s.replace("'", "''")


# Exact-match fine-filter axes: request key → spool column (all IN-list semantics)
_EXACT_FILTER_COLUMNS: Dict[str, str] = {
    "equipment_id": "EQP_ID",
    "lot_id": "LOT_ID",
    "pj_type": "PJ_TYPE",
    "product_line": "PRODUCT_LINE",
    "pj_bop": "PJ_BOP",
}


def _build_filter_where(filters: Optional[Dict[str, Any]], alias: str = "") -> tuple[str, list]:
    """Build WHERE clause from fine filters.

    User-supplied values are NEVER inlined — the clause carries ``?``
    placeholders and the values are returned as a bind-params list, in
    placeholder order, for DuckDB prepared execution.

    Supported keys:
      alarm_text (list[str])    — ILIKE match on ALARM_TEXT
      equipment_id (list[str])  — exact match on EQP_ID
      lot_id (list[str])        — exact match on LOT_ID
      pj_type (list[str])       — exact match on PJ_TYPE (product dim)
      product_line (list[str])  — exact match on PRODUCT_LINE (product dim)
      pj_bop (list[str])        — exact match on PJ_BOP (product dim)
    """
    prefix = f"{alias}." if alias else ""
    clauses: List[str] = []
    params: List[Any] = []

    if filters is None:
        filters = {}

    alarm_texts = [str(t) for t in (filters.get("alarm_text") or []) if t is not None]
    if alarm_texts:
        like_parts = " OR ".join(
            f"{prefix}ALARM_TEXT ILIKE '%' || ? || '%'" for _ in alarm_texts
        )
        clauses.append(f"({like_parts})")
        params.extend(alarm_texts)

    for key, column in _EXACT_FILTER_COLUMNS.items():
        values = [str(v) for v in (filters.get(key) or []) if v is not None]
        if values:
            placeholders = ", ".join("?" for _ in values)
            clauses.append(f"{prefix}{column} IN ({placeholders})")
            params.extend(values)

    if clauses:
        return "WHERE " + " AND ".join(clauses), params
    return "", params


# ── Filter options ────────────────────────────────────────────────────────────

def get_filter_options(spool_path: str, filters: Optional[Dict[str, Any]] = None) -> dict:
    """Distinct filter options from spool.

    Returns:
        {
          alarm_text_options: list[str],
          equipment_id_options: list[str],
          lot_id_options: list[str],
          pj_type_options: list[str],
          product_line_options: list[str],
          pj_bop_options: list[str],
        }
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
            "alarm_text_options": _distinct("ALARM_TEXT"),
            "equipment_id_options": _distinct("EQP_ID"),
            "lot_id_options": _distinct("LOT_ID"),
            "pj_type_options": _distinct("PJ_TYPE"),
            "product_line_options": _distinct("PRODUCT_LINE"),
            "pj_bop_options": _distinct("PJ_BOP"),
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
          affected_lot_count: int,       — distinct LOT_ID (NULL lot excluded)
          affected_product_line_count: int,  — distinct PRODUCT_LINE (NULL excluded)
          unresolved_count: int,         — alarms without a CLEAR in the window
          avg_duration_minutes: float | null,  — avg resolution time (resolved only)
        }
    """
    conn = _get_duckdb_conn()
    try:
        where_sql, where_params = _build_filter_where(filters)

        row = conn.execute(f"""
            SELECT
                COUNT(*) AS total_alarm_count,
                COUNT(DISTINCT EQP_ID) AS affected_equipment_count,
                COUNT(DISTINCT LOT_ID) AS affected_lot_count,
                COUNT(DISTINCT PRODUCT_LINE) AS affected_product_line_count,
                SUM(CASE WHEN ALARM_END IS NULL THEN 1 ELSE 0 END) AS unresolved_count,
                AVG(DURATION_SECONDS) AS avg_duration_seconds
            FROM read_parquet(?)
            {where_sql}
        """, [spool_path, *where_params]).fetchone()

        total_alarm_count = int(row[0] or 0)
        affected_equipment_count = int(row[1] or 0)
        affected_lot_count = int(row[2] or 0)
        affected_product_line_count = int(row[3] or 0)
        unresolved_count = int(row[4] or 0)
        avg_dur_sec = row[5]
        avg_duration_minutes = (
            round(float(avg_dur_sec) / 60, 1) if avg_dur_sec is not None else None
        )

        return {
            "total_alarm_count": total_alarm_count,
            "affected_equipment_count": affected_equipment_count,
            "affected_lot_count": affected_lot_count,
            "affected_product_line_count": affected_product_line_count,
            "unresolved_count": unresolved_count,
            "avg_duration_minutes": avg_duration_minutes,
        }
    finally:
        conn.close()


# ── Pareto ────────────────────────────────────────────────────────────────────

# Groupable dimensions for pareto/trend: request value → (column, NULL label).
# Closed enum — routes validate against these keys before calling the service.
GROUP_DIMENSIONS: Dict[str, tuple[str, str]] = {
    "alarm_text": ("ALARM_TEXT", "(無說明)"),
    "eqp_id": ("EQP_ID", "(未知)"),
    "eqp_type": ("EQP_TYPE", "(未知)"),
    "lot_id": ("LOT_ID", "(無批號)"),
    "pj_type": ("PJ_TYPE", "(NA)"),
    "product_line": ("PRODUCT_LINE", "(NA)"),
    "pj_bop": ("PJ_BOP", "(NA)"),
}


def _group_expr(dim: str) -> str:
    """COALESCE'd group expression for a GROUP_DIMENSIONS key."""
    column, null_label = GROUP_DIMENSIONS[dim]
    return f"COALESCE({column}, '{_escape_sql(null_label)}')"


def get_pareto(
    spool_path: str,
    filters: Optional[Dict[str, Any]] = None,
    dim: str = "alarm_text",
) -> dict:
    """Top-50 Pareto over the requested dimension (count of occurrences).

    dim: one of GROUP_DIMENSIONS keys (default "alarm_text").

    Returns:
        {
          items: [{name, alarm_text, count, cumulative_pct}],
          dim: str,
          total: int,
        }
        `alarm_text` mirrors `name` for backward compatibility with pre-dim
        consumers; new consumers should read `name`.
    """
    if dim not in GROUP_DIMENSIONS:
        raise ValueError(f"invalid pareto dim: {dim!r}")

    conn = _get_duckdb_conn()
    try:
        where_sql, where_params = _build_filter_where(filters)

        total = int(conn.execute(
            f"SELECT COUNT(*) FROM read_parquet(?) {where_sql}",
            [spool_path, *where_params],
        ).fetchone()[0] or 0)

        if total == 0:
            return {"items": [], "dim": dim, "total": 0}

        rows = conn.execute(f"""
            SELECT
                {_group_expr(dim)} AS grp,
                COUNT(*) AS cnt
            FROM read_parquet(?)
            {where_sql}
            GROUP BY grp
            ORDER BY cnt DESC
            LIMIT 50
        """, [spool_path, *where_params]).fetchall()

        items = []
        cumulative = 0
        for row in rows:
            count = int(row[1])
            cumulative += count
            items.append({
                "name": str(row[0]),
                "alarm_text": str(row[0]),
                "count": count,
                "cumulative_pct": round(cumulative / total * 100, 2),
            })

        return {"items": items, "dim": dim, "total": total}
    finally:
        conn.close()


# ── Trend ─────────────────────────────────────────────────────────────────────

def get_trend(
    spool_path: str,
    filters: Optional[Dict[str, Any]] = None,
    granularity: str = "day",
    group_by: str = "alarm_text",
) -> dict:
    """Stacked trend by the requested dimension (top 10), bucketed by ALARM_START.

    group_by: one of GROUP_DIMENSIONS keys (default "alarm_text").

    Returns:
        {
          labels: list[str],
          series: [{name, alarm_text, data: list[int]}],
          group_by: str,
        }
        `alarm_text` mirrors `name` for backward compatibility with pre-dim
        consumers; new consumers should read `name`.
    """
    if group_by not in GROUP_DIMENSIONS:
        raise ValueError(f"invalid trend group_by: {group_by!r}")

    conn = _get_duckdb_conn()
    try:
        where_sql, where_params = _build_filter_where(filters)
        grp_expr = _group_expr(group_by)

        if granularity == "hour":
            ts_expr = "strftime(ALARM_START, '%Y-%m-%d %H:00')"
        else:
            ts_expr = "strftime(ALARM_START, '%Y-%m-%d')"

        # Limit to top-10 group values to keep chart readable
        top_groups = [
            row[0]
            for row in conn.execute(f"""
                SELECT {grp_expr} AS grp
                FROM read_parquet(?)
                {where_sql}
                GROUP BY grp
                ORDER BY COUNT(*) DESC
                LIMIT 10
            """, [spool_path, *where_params]).fetchall()
        ]

        if not top_groups:
            return {"labels": [], "series": [], "group_by": group_by}

        group_placeholders = ", ".join("?" for _ in top_groups)
        rows = conn.execute(f"""
            SELECT
                {ts_expr} AS label,
                {grp_expr} AS grp,
                COUNT(*) AS cnt
            FROM read_parquet(?)
            {where_sql}
            {"AND" if where_sql else "WHERE"} {grp_expr} IN ({group_placeholders})
            GROUP BY label, grp
            ORDER BY label, grp
        """, [spool_path, *where_params, *top_groups]).fetchall()

        if not rows:
            return {"labels": [], "series": [], "group_by": group_by}

        label_set: dict[str, int] = {}
        group_counts: dict[str, dict[str, int]] = {}

        for row in rows:
            label = str(row[0])
            grp = str(row[1])
            cnt = int(row[2])
            if label not in label_set:
                label_set[label] = len(label_set)
            if grp not in group_counts:
                group_counts[grp] = {}
            group_counts[grp][label] = cnt

        labels = sorted(label_set.keys())
        series = [
            {
                "name": grp,
                "alarm_text": grp,
                "data": [group_counts[grp].get(lbl, 0) for lbl in labels],
            }
            for grp in top_groups
            if grp in group_counts
        ]

        return {"labels": labels, "series": series, "group_by": group_by}
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
          rows: [{alarm_id, eqp_id, eqp_type, lot_id, pj_type, product_line,
                  pj_bop, alarm_text, alarm_category_code, alarm_start,
                  alarm_end, duration_seconds, detail_params, alarm_source}],
          meta: {page, per_page, total_count, total_pages},
        }
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

        # ALARM_SOURCE exists from spool schema v5 (EA-EVT). In-flight query_ids
        # minted before a deploy can still point at v4 parquet — DESCRIBE-detect
        # the column instead of letting the binder fail on old files.
        spool_cols = {
            row[0]
            for row in conn.execute(
                "DESCRIBE SELECT * FROM read_parquet(?)", [spool_path]
            ).fetchall()
        }
        alarm_source_col = (
            "ALARM_SOURCE" if "ALARM_SOURCE" in spool_cols else "NULL AS ALARM_SOURCE"
        )

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
                DETAIL_PARAMS,
                PJ_TYPE,
                PRODUCT_LINE,
                PJ_BOP,
                {alarm_source_col}
            FROM read_parquet(?)
            {where_sql}
            ORDER BY ALARM_START DESC, ALARM_ID
            LIMIT ? OFFSET ?
        """, [spool_path, *where_params, per_page, offset]).fetchall()

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
                "pj_type":            str(r[10]) if r[10] is not None else None,
                "product_line":       str(r[11]) if r[11] is not None else None,
                "pj_bop":             str(r[12]) if r[12] is not None else None,
                "alarm_source":       str(r[13]) if r[13] is not None else None,
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
