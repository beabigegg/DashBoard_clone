# -*- coding: utf-8 -*-
"""DuckDB SQL runtime for Production History view computation.

Provides out-of-core view queries (detail page, matrix summary, CSV export,
filter options) by reading Parquet spool files directly via DuckDB.

Entry points:
  - compute_detail_page(spool_path, filter_params, page, per_page)
  - compute_matrix_view(spool_path, filter_params)
  - stream_export(spool_path, filter_params) -> generator[str]
  - compute_filter_options(spool_path) -> dict[str, list[str]]
"""

from __future__ import annotations

import csv
import io
import logging
import time
from typing import Any, Dict, Generator, List, Optional

from mes_dashboard.core.feature_flags import resolve_bool_flag

logger = logging.getLogger("mes_dashboard.production_history_sql_runtime")

_SQL_VIEW_ENABLED = resolve_bool_flag("PROD_HISTORY_SQL_VIEW_ENABLED", default=True)
_SPOOL_NAMESPACE = "production_history"


# ── DuckDB helpers ────────────────────────────────────────────────────────────

def _qid(name: str) -> str:
    """Quote a DuckDB identifier."""
    return '"' + str(name).replace('"', '""') + '"'


def _sql_str(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _get_duckdb_conn():
    import duckdb
    return duckdb.connect(database=":memory:")


def _attach_spool_view(conn: Any, parquet_path: str) -> None:
    sql = (
        "CREATE OR REPLACE TEMP VIEW ph_src AS "
        f"SELECT * FROM read_parquet({_sql_str(parquet_path)})"
    )
    conn.execute(sql)


def _fetch_dict_rows(conn: Any, sql: str, params: Optional[List[Any]] = None) -> List[Dict[str, Any]]:
    cursor = conn.execute(sql, params or [])
    columns = [desc[0] for desc in (cursor.description or [])]
    rows = cursor.fetchall()
    return [dict(zip(columns, row)) for row in rows]


# ── Filter WHERE clause builder ───────────────────────────────────────────────

def _build_wc_group_condition(
    group_name: str, workcenter_groups: Dict[str, Any],
) -> tuple[str, List[Any]]:
    """Build a single workcenter-group WHERE fragment (ILIKE patterns or exact match)."""
    if group_name in workcenter_groups:
        cfg = workcenter_groups[group_name]
        like_parts = [f"WORKCENTERNAME ILIKE ?" for _ in cfg["patterns"]]
        clause = "(" + " OR ".join(like_parts) + ")"
        p = [f"%{pat}%" for pat in cfg["patterns"]]
        for excl in cfg.get("exclude", []):
            clause += " AND WORKCENTERNAME NOT ILIKE ?"
            p.append(f"%{excl}%")
        return clause, p
    else:
        return "WORKCENTERNAME = ?", [group_name]


def _build_filter_where(filter_params: Dict[str, Any]) -> tuple[str, List[Any]]:
    """Build DuckDB WHERE clause for matrix/page/export filter.

    Accepted filter fields:
      - Matrix (singular): workcenter_group, spec, equipment_id, month
      - Supplementary (arrays): work_orders, lot_ids, packages, bop_codes,
        workcenter_groups, equipment_ids

    ``workcenter_group`` / ``workcenter_groups`` are canonical group names
    (e.g. '焊接_DB').  This function expands them to the underlying ILIKE
    patterns defined in ``workcenter_groups.py`` so the filter matches the
    raw WORKCENTERNAME values stored in the Parquet spool.
    """
    from mes_dashboard.config.workcenter_groups import WORKCENTER_GROUPS

    conditions: List[str] = []
    params: List[Any] = []

    # ── Matrix singular filters ──────────────────────────────────────────────
    wc_group = str(filter_params.get("workcenter_group") or "").strip()
    spec = str(filter_params.get("spec") or "").strip()
    equipment_id = str(filter_params.get("equipment_id") or "").strip()
    month = str(filter_params.get("month") or "").strip()

    if wc_group:
        clause, p = _build_wc_group_condition(wc_group, WORKCENTER_GROUPS)
        conditions.append(clause)
        params.extend(p)
    if spec:
        conditions.append("SPECNAME = ?")
        params.append(spec)
    if equipment_id:
        conditions.append("EQUIPMENTID = ?")
        params.append(equipment_id)
    if month:
        conditions.append("strftime(TRACKIN_TS::TIMESTAMP, '%Y-%m') = ?")
        params.append(month)

    # ── Supplementary multi-select filters (arrays) ──────────────────────────
    # Simple column-based IN filters
    _SUPP_COLUMNS = [
        ("work_orders", "WORK_ORDER"),
        ("lot_ids", "CONTAINERNAME"),
        ("packages", "PACKAGE_NAME"),
        ("bop_codes", "PJ_BOP"),
        ("equipment_ids", "EQUIPMENTNAME"),
    ]
    for key, col in _SUPP_COLUMNS:
        values = filter_params.get(key)
        if isinstance(values, list) and values:
            placeholders = ", ".join("?" for _ in values)
            conditions.append(f'"{col}" IN ({placeholders})')
            params.extend(values)

    # workcenter_groups (plural) — expand each group name to ILIKE patterns
    wc_groups = filter_params.get("workcenter_groups")
    if isinstance(wc_groups, list) and wc_groups:
        group_clauses: List[str] = []
        for gname in wc_groups:
            clause, p = _build_wc_group_condition(gname, WORKCENTER_GROUPS)
            group_clauses.append(f"({clause})")
            params.extend(p)
        conditions.append("(" + " OR ".join(group_clauses) + ")")

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    return where, params


# ── Detail page ───────────────────────────────────────────────────────────────

def compute_detail_page(
    spool_path: str,
    filter_params: Dict[str, Any],
    page: int = 1,
    per_page: int = 25,
) -> Dict[str, Any]:
    """Return a single page of detail rows from the Parquet spool.

    Args:
        spool_path: Absolute path to the Parquet file.
        filter_params: Optional filter dict {workcenter_group, spec, equipment_id}.
        page: 1-based page number.
        per_page: Rows per page (default 25).

    Returns:
        {rows: [...], pagination: {page, per_page, total_rows, total_pages}}
    """
    if not _SQL_VIEW_ENABLED:
        return _pandas_detail_page(spool_path, filter_params, page, per_page)

    page = max(1, int(page))
    per_page = max(1, min(int(per_page), 200))
    offset = (page - 1) * per_page

    where, params = _build_filter_where(filter_params)

    try:
        conn = _get_duckdb_conn()
        _attach_spool_view(conn, spool_path)

        count_sql = f"SELECT COUNT(*) AS total FROM ph_src {where}"
        count_row = conn.execute(count_sql, params).fetchone()
        total_rows = int(count_row[0]) if count_row else 0
        total_pages = max(1, (total_rows + per_page - 1) // per_page)

        page_sql = f"""
            SELECT
                CONTAINERNAME   AS lot_id,
                PJ_TYPE         AS pj_type,
                PJ_BOP          AS bop,
                WORK_ORDER      AS work_order,
                WAFER_LOT       AS wafer_lot,
                PACKAGE_NAME    AS package_name,
                WORKCENTERNAME  AS workcenter,
                SPECNAME        AS spec,
                EQUIPMENTID     AS equipment_id,
                EQUIPMENTNAME   AS equipment_name,
                strftime(TRACKIN_TS::TIMESTAMP, '%Y-%m-%d %H:%M:%S')   AS trackin_time,
                strftime(TRACKOUT_TS::TIMESTAMP, '%Y-%m-%d %H:%M:%S') AS trackout_time,
                TRACKIN_QTY     AS trackin_qty,
                TRACKOUT_QTY    AS trackout_qty
            FROM ph_src
            {where}
            ORDER BY TRACKIN_TS DESC NULLS LAST, CONTAINERNAME
            LIMIT ? OFFSET ?
        """
        rows = _fetch_dict_rows(conn, page_sql, params + [per_page, offset])
        conn.close()

        return {
            "rows": rows,
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total_rows": total_rows,
                "total_pages": total_pages,
            },
        }
    except MemoryError:
        raise
    except Exception as exc:
        logger.error("compute_detail_page failed: %s", exc, exc_info=True)
        return {
            "rows": [],
            "pagination": {"page": page, "per_page": per_page, "total_rows": 0, "total_pages": 0},
        }


def _pandas_detail_page(
    spool_path: str,
    filter_params: Dict[str, Any],
    page: int,
    per_page: int,
) -> Dict[str, Any]:
    """Fallback pandas path when DuckDB is disabled."""
    import pandas as pd

    df = pd.read_parquet(spool_path)
    df = _apply_pandas_filter(df, filter_params)
    total_rows = len(df)
    offset = (page - 1) * per_page
    page_df = df.iloc[offset: offset + per_page]
    rows = page_df.rename(columns={
        "CONTAINERNAME": "lot_id", "PJ_TYPE": "pj_type", "PJ_BOP": "bop",
        "WORK_ORDER": "work_order", "WAFER_LOT": "wafer_lot",
        "PACKAGE_NAME": "package_name",
        "WORKCENTERNAME": "workcenter", "SPECNAME": "spec",
        "EQUIPMENTID": "equipment_id", "EQUIPMENTNAME": "equipment_name",
        "TRACKIN_TS": "trackin_time", "TRACKOUT_TS": "trackout_time",
        "TRACKIN_QTY": "trackin_qty", "TRACKOUT_QTY": "trackout_qty",
    }).to_dict(orient="records")
    return {
        "rows": rows,
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total_rows": total_rows,
            "total_pages": max(1, (total_rows + per_page - 1) // per_page),
        },
    }


# ── Matrix summary ────────────────────────────────────────────────────────────

def compute_matrix_view(
    spool_path: str,
    filter_params: Dict[str, Any],
) -> Dict[str, Any]:
    """Compute three-level aggregation matrix (WC → Spec → Equipment × Month).

    Returns:
        {tree: [...], month_columns: [...]}
        tree node: {label, level, count, month_counts: {YYYY-MM: n}, children: [...]}
    """
    if not _SQL_VIEW_ENABLED:
        return _pandas_matrix_view(spool_path, filter_params)

    where, params = _build_filter_where(filter_params)

    try:
        conn = _get_duckdb_conn()
        _attach_spool_view(conn, spool_path)

        # Aggregate at equipment level with month buckets
        agg_sql = f"""
            SELECT
                WORKCENTERNAME                                    AS wc,
                SPECNAME                                          AS spec,
                EQUIPMENTID                                       AS eqp_id,
                EQUIPMENTNAME                                     AS eqp_name,
                strftime(TRACKIN_TS::TIMESTAMP, '%Y-%m')          AS month_bucket,
                COUNT(DISTINCT CONTAINERNAME)                     AS lot_count
            FROM ph_src
            {where}
            GROUP BY wc, spec, eqp_id, eqp_name, month_bucket
            ORDER BY wc, spec, eqp_id, month_bucket
        """
        rows = _fetch_dict_rows(conn, agg_sql, params)
        conn.close()

        return _build_matrix_tree(rows)
    except MemoryError:
        raise
    except Exception as exc:
        logger.error("compute_matrix_view failed: %s", exc, exc_info=True)
        return {"tree": [], "month_columns": []}


def _build_matrix_tree(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Build hierarchical tree from flat aggregation rows.

    Applies workcenter group mapping so that raw workcenter names are grouped
    under their canonical group name (e.g. '焊_DB_料' → '焊接_DB') and sorted
    by the configured group order.
    """
    from mes_dashboard.config.workcenter_groups import get_workcenter_group

    # Collect all months
    all_months: set[str] = set()
    for r in rows:
        m = str(r.get("month_bucket") or "")
        if m:
            all_months.add(m)
    month_columns = sorted(all_months)

    # Build tree: workcenter_group → spec → eqp
    # Map raw workcenter names to canonical group names
    wc_map: Dict[str, Any] = {}
    wc_order: Dict[str, int] = {}

    for r in rows:
        raw_wc = str(r.get("wc") or "")
        spec = str(r.get("spec") or "")
        eqp_id = str(r.get("eqp_id") or "")
        eqp_name = str(r.get("eqp_name") or "")
        month = str(r.get("month_bucket") or "")
        count = int(r.get("lot_count") or 0)

        # Resolve workcenter to its group
        group_name, order = get_workcenter_group(raw_wc)
        wc_label = group_name if group_name else raw_wc
        wc_order.setdefault(wc_label, order)

        if wc_label not in wc_map:
            wc_map[wc_label] = {"label": wc_label, "level": "workcenter", "count": 0,
                                "month_counts": {}, "children": {}}
        wc_node = wc_map[wc_label]

        spec_key = spec
        if spec_key not in wc_node["children"]:
            wc_node["children"][spec_key] = {"label": spec, "level": "spec", "count": 0,
                                              "month_counts": {}, "children": {}}
        spec_node = wc_node["children"][spec_key]

        eqp_key = eqp_id
        if eqp_key not in spec_node["children"]:
            spec_node["children"][eqp_key] = {
                "label": eqp_id,
                "equipment_name": eqp_name,
                "level": "equipment",
                "count": 0,
                "month_counts": {},
                "children": {},
            }
        eqp_node = spec_node["children"][eqp_key]

        if month:
            eqp_node["month_counts"][month] = eqp_node["month_counts"].get(month, 0) + count
            spec_node["month_counts"][month] = spec_node["month_counts"].get(month, 0) + count
            wc_node["month_counts"][month] = wc_node["month_counts"].get(month, 0) + count
        eqp_node["count"] += count
        spec_node["count"] += count
        wc_node["count"] += count

    def _flatten(node_map: Dict) -> List[Dict]:
        result = []
        for node in node_map.values():
            n = dict(node)
            n["children"] = _flatten(n.get("children", {}))
            result.append(n)
        return result

    tree = _flatten(wc_map)
    # Sort workcenter groups by configured order, then alphabetically
    tree.sort(key=lambda n: (wc_order.get(n["label"], 999), n["label"]))
    # Sort spec children alphabetically, equipment children alphabetically
    for wc_node in tree:
        wc_node["children"].sort(key=lambda n: n["label"])
        for spec_node in wc_node["children"]:
            spec_node["children"].sort(key=lambda n: n.get("equipment_name") or n["label"])

    return {"tree": tree, "month_columns": month_columns}


def _apply_pandas_wc_group_filter(df: "pd.DataFrame", group_name: str, workcenter_groups: Dict) -> "pd.DataFrame":
    """Filter DataFrame by a single workcenter group name."""
    import pandas as pd

    if group_name in workcenter_groups:
        cfg = workcenter_groups[group_name]
        wc_upper = df["WORKCENTERNAME"].str.upper()
        mask = pd.Series(False, index=df.index)
        for p in cfg["patterns"]:
            mask |= wc_upper.str.contains(p.upper(), na=False)
        for excl in cfg.get("exclude", []):
            mask &= ~wc_upper.str.contains(excl.upper(), na=False)
        return df[mask]
    else:
        return df[df["WORKCENTERNAME"] == group_name]


def _apply_pandas_filter(df: "pd.DataFrame", filter_params: Dict[str, Any]) -> "pd.DataFrame":
    import pandas as pd
    from mes_dashboard.config.workcenter_groups import WORKCENTER_GROUPS

    # ── Matrix singular filters ──────────────────────────────────────────────
    wc_group = str(filter_params.get("workcenter_group") or "").strip()
    spec = str(filter_params.get("spec") or "").strip()
    equipment_id = str(filter_params.get("equipment_id") or "").strip()
    month = str(filter_params.get("month") or "").strip()

    if wc_group:
        df = _apply_pandas_wc_group_filter(df, wc_group, WORKCENTER_GROUPS)
    if spec:
        df = df[df["SPECNAME"] == spec]
    if equipment_id:
        df = df[df["EQUIPMENTID"] == equipment_id]
    if month:
        df = df[pd.to_datetime(df["TRACKIN_TS"], errors="coerce").dt.strftime("%Y-%m") == month]

    # ── Supplementary multi-select filters (arrays) ──────────────────────────
    _SUPP_COLUMNS = [
        ("work_orders", "WORK_ORDER"),
        ("lot_ids", "CONTAINERNAME"),
        ("packages", "PACKAGE_NAME"),
        ("bop_codes", "PJ_BOP"),
        ("equipment_ids", "EQUIPMENTNAME"),
    ]
    for key, col in _SUPP_COLUMNS:
        values = filter_params.get(key)
        if isinstance(values, list) and values:
            df = df[df[col].isin(values)]

    # workcenter_groups (plural) — OR across multiple groups
    wc_groups = filter_params.get("workcenter_groups")
    if isinstance(wc_groups, list) and wc_groups:
        combined_mask = pd.Series(False, index=df.index)
        for gname in wc_groups:
            sub = _apply_pandas_wc_group_filter(df, gname, WORKCENTER_GROUPS)
            combined_mask |= df.index.isin(sub.index)
        df = df[combined_mask]

    return df


def _pandas_matrix_view(spool_path: str, filter_params: Dict[str, Any]) -> Dict[str, Any]:
    import pandas as pd

    df = pd.read_parquet(spool_path)
    df = _apply_pandas_filter(df, filter_params)
    if df.empty:
        return {"tree": [], "month_columns": []}

    df["month_bucket"] = pd.to_datetime(df["TRACKIN_TS"], errors="coerce").dt.strftime("%Y-%m")
    agg = (
        df.groupby(["WORKCENTERNAME", "SPECNAME", "EQUIPMENTID", "EQUIPMENTNAME", "month_bucket"])
        ["CONTAINERNAME"].nunique().reset_index()
    )
    agg.columns = ["wc", "spec", "eqp_id", "eqp_name", "month_bucket", "lot_count"]
    return _build_matrix_tree(agg.to_dict(orient="records"))


# ── Filter options ────────────────────────────────────────────────────────────

def compute_filter_options(spool_path: str) -> Dict[str, List[str]]:
    """Return distinct values for each filterable column in the spool.

    Runs six separate ``SELECT DISTINCT`` queries (one per column) to avoid
    DuckDB limitations with ``ARRAY_AGG ... ORDER BY`` in older builds.

    Args:
        spool_path: Absolute path to the Parquet spool file.

    Returns:
        {
          "work_orders":       [...],
          "lot_ids":           [...],
          "packages":          [...],
          "bop_codes":         [...],
          "workcenter_groups": [...],
          "equipment_ids":     [...],
        }
        All values are sorted strings.  Empty lists are returned on any
        non-MemoryError failure so the caller always gets a safe dict.
    """
    # Simple 1:1 column mappings (key → Parquet column)
    _SIMPLE_COLUMNS = [
        ("work_orders",  "WORK_ORDER"),
        ("lot_ids",      "CONTAINERNAME"),
        ("packages",     "PACKAGE_NAME"),
        ("bop_codes",    "PJ_BOP"),
    ]

    empty: Dict[str, List[str]] = {
        k: [] for k, _ in _SIMPLE_COLUMNS
    }
    empty["workcenter_groups"] = []
    empty["equipment_ids"] = []

    if not _SQL_VIEW_ENABLED:
        logger.debug("compute_filter_options: SQL view disabled, returning empty options")
        return empty

    try:
        from mes_dashboard.config.workcenter_groups import get_workcenter_group

        conn = _get_duckdb_conn()
        _attach_spool_view(conn, spool_path)

        result: Dict[str, List[str]] = {}

        # Simple columns — straight DISTINCT
        for key, col in _SIMPLE_COLUMNS:
            sql = (
                f"SELECT DISTINCT {_qid(col)} AS val "
                f"FROM ph_src "
                f"WHERE {_qid(col)} IS NOT NULL AND {_qid(col)} != '' "
                f"ORDER BY val"
            )
            rows = _fetch_dict_rows(conn, sql)
            result[key] = [str(r["val"]) for r in rows]

        # workcenter_groups — map raw names → canonical group names, sorted by order
        wc_sql = (
            "SELECT DISTINCT \"WORKCENTERNAME\" AS val "
            "FROM ph_src "
            "WHERE \"WORKCENTERNAME\" IS NOT NULL AND \"WORKCENTERNAME\" != '' "
        )
        wc_rows = _fetch_dict_rows(conn, wc_sql)
        group_set: Dict[str, int] = {}  # group_name → order
        for r in wc_rows:
            gname, order = get_workcenter_group(str(r["val"]))
            label = gname if gname else str(r["val"])
            group_set.setdefault(label, order)
        result["workcenter_groups"] = [
            name for name, _ in sorted(group_set.items(), key=lambda x: (x[1], x[0]))
        ]

        # equipment_ids — use EQUIPMENTNAME for display
        eqp_sql = (
            "SELECT DISTINCT \"EQUIPMENTNAME\" AS val "
            "FROM ph_src "
            "WHERE \"EQUIPMENTNAME\" IS NOT NULL AND \"EQUIPMENTNAME\" != '' "
            "ORDER BY val"
        )
        eqp_rows = _fetch_dict_rows(conn, eqp_sql)
        result["equipment_ids"] = [str(r["val"]) for r in eqp_rows]

        conn.close()
        return result
    except MemoryError:
        raise
    except Exception as exc:
        logger.error("compute_filter_options failed: %s", exc, exc_info=True)
        return empty


# ── CSV export ────────────────────────────────────────────────────────────────

def stream_export(
    spool_path: str,
    filter_params: Dict[str, Any],
) -> Generator[str, None, None]:
    """Stream CSV rows from spool.

    Yields:
        CSV row strings (header first, then data rows).
    """
    EXPORT_COLUMNS = [
        ("CONTAINERNAME", "LotID"),
        ("PJ_TYPE", "Type"),
        ("PACKAGE_NAME", "Package"),
        ("PJ_BOP", "BOP"),
        ("WORK_ORDER", "WorkOrder"),
        ("WAFER_LOT", "WaferLot"),
        ("WORKCENTERNAME", "WorkCenter"),
        ("SPECNAME", "Spec"),
        ("EQUIPMENTID", "EquipmentID"),
        ("EQUIPMENTNAME", "EquipmentName"),
        ("TRACKIN_TS", "TrackInTime"),
        ("TRACKOUT_TS", "TrackOutTime"),
        ("TRACKIN_QTY", "TrackInQty"),
        ("TRACKOUT_QTY", "TrackOutQty"),
    ]
    col_selects = ", ".join(
        f"{_qid(src)} AS {_qid(dst)}" for src, dst in EXPORT_COLUMNS
    )

    where, params = _build_filter_where(filter_params)

    buf = io.StringIO()
    writer = csv.writer(buf)

    # BOM + Header for Excel UTF-8 compatibility
    buf.write('\ufeff')
    writer.writerow([dst for _, dst in EXPORT_COLUMNS])
    yield buf.getvalue()
    buf.truncate(0)
    buf.seek(0)

    if not _SQL_VIEW_ENABLED:
        yield from _pandas_stream_export(spool_path, filter_params, EXPORT_COLUMNS)
        return

    BATCH_SIZE = 1000
    offset = 0
    try:
        conn = _get_duckdb_conn()
        _attach_spool_view(conn, spool_path)

        while True:
            sql = f"""
                SELECT {col_selects}
                FROM ph_src
                {where}
                ORDER BY TRACKIN_TS DESC NULLS LAST, CONTAINERNAME
                LIMIT {BATCH_SIZE} OFFSET {offset}
            """
            rows = _fetch_dict_rows(conn, sql, params)
            if not rows:
                break
            for row in rows:
                writer.writerow([row.get(dst, "") for _, dst in EXPORT_COLUMNS])
            yield buf.getvalue()
            buf.truncate(0)
            buf.seek(0)
            offset += BATCH_SIZE
            if len(rows) < BATCH_SIZE:
                break

        conn.close()
    except Exception as exc:
        logger.error("stream_export failed at offset %d: %s", offset, exc)
        raise


def _pandas_stream_export(
    spool_path: str,
    filter_params: Dict[str, Any],
    columns: List[tuple[str, str]],
) -> Generator[str, None, None]:
    import pandas as pd

    df = pd.read_parquet(spool_path)
    df = _apply_pandas_filter(df, filter_params)

    buf = io.StringIO()
    writer = csv.writer(buf)
    BATCH = 500

    for i in range(0, max(len(df), 1), BATCH):
        chunk = df.iloc[i: i + BATCH]
        for _, row in chunk.iterrows():
            writer.writerow([row.get(src, "") for src, _ in columns])
        yield buf.getvalue()
        buf.truncate(0)
        buf.seek(0)
