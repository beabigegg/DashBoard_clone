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

def _build_filter_where(filter_params: Dict[str, Any]) -> tuple[str, List[Any]]:
    """Build DuckDB WHERE clause for matrix/page/export filter.

    Accepted filter fields: workcenter_group, spec, equipment_id, month
    Returns (where_clause, positional_params)

    ``workcenter_group`` is a canonical group name (e.g. '焊接_DB').  This
    function expands it to the underlying ILIKE patterns defined in
    ``workcenter_groups.py`` so the filter matches the raw WORKCENTERNAME
    values stored in the Parquet spool.
    """
    from mes_dashboard.config.workcenter_groups import WORKCENTER_GROUPS

    conditions: List[str] = []
    params: List[Any] = []

    wc_group = str(filter_params.get("workcenter_group") or "").strip()
    spec = str(filter_params.get("spec") or "").strip()
    equipment_id = str(filter_params.get("equipment_id") or "").strip()
    month = str(filter_params.get("month") or "").strip()

    if wc_group:
        if wc_group in WORKCENTER_GROUPS:
            cfg = WORKCENTER_GROUPS[wc_group]
            # Include patterns (OR)
            like_parts = [f"WORKCENTERNAME ILIKE ?" for _ in cfg["patterns"]]
            conditions.append("(" + " OR ".join(like_parts) + ")")
            params.extend(f"%{p}%" for p in cfg["patterns"])
            # Exclude patterns (AND NOT each)
            for excl in cfg.get("exclude", []):
                conditions.append("WORKCENTERNAME NOT ILIKE ?")
                params.append(f"%{excl}%")
        else:
            # Unmatched group — label equals the raw workcenter name
            conditions.append("WORKCENTERNAME = ?")
            params.append(wc_group)
    if spec:
        conditions.append("SPECNAME = ?")
        params.append(spec)
    if equipment_id:
        conditions.append("EQUIPMENTID = ?")
        params.append(equipment_id)
    if month:
        conditions.append("strftime(TRACKIN_TS::TIMESTAMP, '%Y-%m') = ?")
        params.append(month)

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
                WORKCENTERNAME  AS workcenter,
                SPECNAME        AS spec,
                EQUIPMENTID     AS equipment_id,
                EQUIPMENTNAME   AS equipment_name,
                TRACKIN_TS      AS trackin_time,
                TRACKOUT_TS     AS trackout_time,
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


def _apply_pandas_filter(df: "pd.DataFrame", filter_params: Dict[str, Any]) -> "pd.DataFrame":
    import pandas as pd
    from mes_dashboard.config.workcenter_groups import WORKCENTER_GROUPS

    wc_group = str(filter_params.get("workcenter_group") or "").strip()
    spec = str(filter_params.get("spec") or "").strip()
    equipment_id = str(filter_params.get("equipment_id") or "").strip()
    month = str(filter_params.get("month") or "").strip()

    if wc_group:
        if wc_group in WORKCENTER_GROUPS:
            cfg = WORKCENTER_GROUPS[wc_group]
            wc_upper = df["WORKCENTERNAME"].str.upper()
            mask = pd.Series(False, index=df.index)
            for p in cfg["patterns"]:
                mask |= wc_upper.str.contains(p.upper(), na=False)
            for excl in cfg.get("exclude", []):
                mask &= ~wc_upper.str.contains(excl.upper(), na=False)
            df = df[mask]
        else:
            df = df[df["WORKCENTERNAME"] == wc_group]
    if spec:
        df = df[df["SPECNAME"] == spec]
    if equipment_id:
        df = df[df["EQUIPMENTID"] == equipment_id]
    if month:
        df = df[pd.to_datetime(df["TRACKIN_TS"], errors="coerce").dt.strftime("%Y-%m") == month]
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
    _COLUMNS = [
        ("work_orders",       "WORK_ORDER"),
        ("lot_ids",           "CONTAINERNAME"),
        ("packages",          "PJ_TYPE"),
        ("bop_codes",         "PJ_BOP"),
        ("workcenter_groups", "WORKCENTERNAME"),
        ("equipment_ids",     "EQUIPMENTID"),
    ]

    empty: Dict[str, List[str]] = {key: [] for key, _ in _COLUMNS}

    if not _SQL_VIEW_ENABLED:
        logger.debug("compute_filter_options: SQL view disabled, returning empty options")
        return empty

    try:
        conn = _get_duckdb_conn()
        _attach_spool_view(conn, spool_path)

        result: Dict[str, List[str]] = {}
        for key, col in _COLUMNS:
            sql = (
                f"SELECT DISTINCT {_qid(col)} AS val "
                f"FROM ph_src "
                f"WHERE {_qid(col)} IS NOT NULL AND {_qid(col)} != '' "
                f"ORDER BY val"
            )
            rows = _fetch_dict_rows(conn, sql)
            result[key] = [str(r["val"]) for r in rows]

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

    # Header
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
