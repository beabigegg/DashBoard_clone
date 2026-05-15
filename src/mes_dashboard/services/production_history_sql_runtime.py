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
    from mes_dashboard.core.duckdb_runtime import create_heavy_query_connection
    return create_heavy_query_connection()


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
        like_parts = ["WORKCENTERNAME ILIKE ?" for _ in cfg["patterns"]]
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
        conditions.append("strftime(TRACKINTIMESTAMP::TIMESTAMP, '%Y-%m') = ?")
        params.append(month)

    # ── Supplementary multi-select filters (arrays) ──────────────────────────
    # Simple column-based IN filters
    _SUPP_COLUMNS = [
        ("work_orders", "MFGORDERNAME"),
        ("lot_ids", "CONTAINERNAME"),
        ("packages", "PRODUCTLINENAME"),
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
    # Build an AND-prefixed filter fragment for the raw branch inside the CTE.
    # The raw branch already has `WHERE (key-tuple) IN (...)`, so the user
    # filter must continue that WHERE with AND, not start a second WHERE.
    where_for_raw = (" AND " + where[len("WHERE "):]) if where else ""

    try:
        conn = _get_duckdb_conn()
        _attach_spool_view(conn, spool_path)

        # ── Partial-trackout aggregation SQL (PH-06 / PH-07) ─────────────────
        # The CTE groups by the 4-tuple key (lot, spec, equipment, trackin_time);
        # TRACKINQTY is intentionally NOT a key because this MES records the qty
        # remaining at each partial's start, so successive partials of the same
        # upload have different TRACKINQTY values.  TRACKINQTY=MAX(...) is emitted
        # = original load before any partial trackouts.  A/B lot interleaving is
        # preserved by TRACKINTIMESTAMP (A's re-upload has a different timestamp).
        #
        # The grouped CTE splits into:
        #   agg  — groups where all 8 non-key columns are identical (collapse)
        #   raw  — groups where any non-key column diverges (strict guard fallback)
        agg_cte_sql = f"""
            WITH grouped AS (
                SELECT
                    CONTAINERNAME, SPECNAME, EQUIPMENTID, TRACKINTIMESTAMP,
                    COUNT(*) AS partial_count,
                    MAX(TRACKINQTY)        AS TRACKINQTY,
                    MAX(TRACKOUTTIMESTAMP) AS TRACKOUTTIMESTAMP,
                    SUM(TRACKOUTQTY)       AS TRACKOUTQTY,
                    COUNT(DISTINCT MFGORDERNAME)    AS dc_work_order,
                    COUNT(DISTINCT FIRSTNAME)        AS dc_wafer_lot,
                    COUNT(DISTINCT PJ_TYPE)          AS dc_pj_type,
                    COUNT(DISTINCT PJ_BOP)           AS dc_pj_bop,
                    COUNT(DISTINCT PJ_FUNCTION)      AS dc_pj_function,
                    COUNT(DISTINCT PRODUCTLINENAME)  AS dc_package,
                    COUNT(DISTINCT WORKCENTERNAME)   AS dc_wc,
                    COUNT(DISTINCT EQUIPMENTNAME)    AS dc_eq_name,
                    ANY_VALUE(MFGORDERNAME)    AS MFGORDERNAME,
                    ANY_VALUE(FIRSTNAME)       AS FIRSTNAME,
                    ANY_VALUE(PJ_TYPE)         AS PJ_TYPE,
                    ANY_VALUE(PJ_BOP)          AS PJ_BOP,
                    ANY_VALUE(PJ_FUNCTION)     AS PJ_FUNCTION,
                    ANY_VALUE(PRODUCTLINENAME) AS PRODUCTLINENAME,
                    ANY_VALUE(WORKCENTERNAME)  AS WORKCENTERNAME,
                    ANY_VALUE(EQUIPMENTNAME)   AS EQUIPMENTNAME
                FROM ph_src
                {where}
                GROUP BY CONTAINERNAME, SPECNAME, EQUIPMENTID, TRACKINTIMESTAMP
            ),
            agg AS (
                SELECT * FROM grouped
                WHERE dc_work_order=1 AND dc_wafer_lot=1 AND dc_pj_type=1 AND dc_pj_bop=1
                  AND dc_pj_function=1 AND dc_package=1 AND dc_wc=1 AND dc_eq_name=1
            ),
            raw AS (
                SELECT
                    p.CONTAINERNAME, p.SPECNAME, p.EQUIPMENTID,
                    p.TRACKINTIMESTAMP,
                    1 AS partial_count,
                    p.TRACKINQTY,
                    p.TRACKOUTTIMESTAMP, p.TRACKOUTQTY,
                    0 AS dc_work_order, 0 AS dc_wafer_lot, 0 AS dc_pj_type, 0 AS dc_pj_bop,
                    0 AS dc_pj_function, 0 AS dc_package, 0 AS dc_wc, 0 AS dc_eq_name,
                    p.MFGORDERNAME, p.FIRSTNAME, p.PJ_TYPE, p.PJ_BOP,
                    p.PJ_FUNCTION, p.PRODUCTLINENAME, p.WORKCENTERNAME, p.EQUIPMENTNAME
                FROM ph_src p
                WHERE (p.CONTAINERNAME, p.SPECNAME, p.EQUIPMENTID,
                       p.TRACKINTIMESTAMP) IN (
                    SELECT CONTAINERNAME, SPECNAME, EQUIPMENTID, TRACKINTIMESTAMP
                    FROM grouped
                    WHERE dc_work_order>1 OR dc_wafer_lot>1 OR dc_pj_type>1 OR dc_pj_bop>1
                       OR dc_pj_function>1 OR dc_package>1 OR dc_wc>1 OR dc_eq_name>1
                )
                {where_for_raw}
            ),
            combined AS (
                SELECT * FROM agg UNION ALL SELECT * FROM raw
            )
        """

        # Post-aggregation count for total_rows (AC-4) and summary log
        count_sql = f"""
            {agg_cte_sql}
            SELECT
                COUNT(*) AS total_rows,
                COUNT(*) FILTER (
                    WHERE dc_work_order>1 OR dc_wafer_lot>1 OR dc_pj_type>1 OR dc_pj_bop>1
                       OR dc_pj_function>1 OR dc_package>1 OR dc_wc>1 OR dc_eq_name>1
                ) AS divergent_groups_raw_rows,
                (SELECT COUNT(DISTINCT (CONTAINERNAME, SPECNAME, EQUIPMENTID,
                                        TRACKINTIMESTAMP)) FROM grouped
                 WHERE dc_work_order>1 OR dc_wafer_lot>1 OR dc_pj_type>1 OR dc_pj_bop>1
                    OR dc_pj_function>1 OR dc_package>1 OR dc_wc>1 OR dc_eq_name>1
                ) AS divergent_groups,
                (SELECT COUNT(*) FROM grouped) AS total_groups
            FROM combined
        """
        count_row = conn.execute(count_sql, params + params).fetchone()
        if count_row:
            total_rows = int(count_row[0])
            divergent_groups = int(count_row[2]) if count_row[2] is not None else 0
            total_groups = int(count_row[3]) if count_row[3] is not None else 0
        else:
            total_rows = 0
            divergent_groups = 0
            total_groups = 0

        total_pages = max(1, (total_rows + per_page - 1) // per_page)

        # Emit summary INFO log when strict-guard fallback occurs (PH-07)
        if divergent_groups > 0:
            query_id = filter_params.get("query_id")
            logger.info(
                "partial-trackout strict-guard: %d divergent groups fell back to raw rows "
                "(query_id=%s, total_groups=%d)",
                divergent_groups,
                query_id,
                total_groups,
            )

        page_sql = f"""
            {agg_cte_sql}
            SELECT
                CONTAINERNAME    AS lot_id,
                PJ_TYPE          AS pj_type,
                PJ_BOP           AS bop,
                PJ_FUNCTION      AS pj_function,
                MFGORDERNAME     AS work_order,
                FIRSTNAME        AS wafer_lot,
                PRODUCTLINENAME  AS package_name,
                WORKCENTERNAME   AS workcenter,
                SPECNAME         AS spec,
                EQUIPMENTID      AS equipment_id,
                EQUIPMENTNAME    AS equipment_name,
                strftime(TRACKINTIMESTAMP::TIMESTAMP,  '%Y-%m-%d %H:%M:%S') AS trackin_time,
                strftime(TRACKOUTTIMESTAMP::TIMESTAMP, '%Y-%m-%d %H:%M:%S') AS trackout_time,
                TRACKINQTY       AS trackin_qty,
                TRACKOUTQTY      AS trackout_qty,
                partial_count
            FROM combined
            ORDER BY TRACKINTIMESTAMP ASC NULLS LAST, CONTAINERNAME
            LIMIT ? OFFSET ?
        """
        rows = _fetch_dict_rows(conn, page_sql, params + params + [per_page, offset])
        # Ensure partial_count is int (DuckDB may return it as a different numeric type)
        for row in rows:
            if "partial_count" in row:
                row["partial_count"] = int(row["partial_count"])
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
    """Fallback pandas path when DuckDB is disabled.

    Applies the same 4-tuple partial-trackout aggregation as compute_detail_page
    (PH-06 / PH-07).  Groups sharing all non-key columns are collapsed into one
    row with TRACKOUTTIMESTAMP=MAX, TRACKOUTQTY=SUM, partial_count=COUNT(*).
    Groups where any non-key column diverges emit raw rows with partial_count=1.
    """
    import pandas as pd

    df = pd.read_parquet(spool_path)
    df = _apply_pandas_filter(df, filter_params)

    agg_df = _pandas_aggregate_partial_trackouts(df, query_id=None)

    total_rows = len(agg_df)
    offset = (page - 1) * per_page
    page_df = agg_df.iloc[offset: offset + per_page]
    rows = page_df.rename(columns={
        "CONTAINERNAME": "lot_id", "PJ_TYPE": "pj_type", "PJ_BOP": "bop",
        "PJ_FUNCTION": "pj_function",
        "MFGORDERNAME": "work_order", "FIRSTNAME": "wafer_lot",
        "PRODUCTLINENAME": "package_name",
        "WORKCENTERNAME": "workcenter", "SPECNAME": "spec",
        "EQUIPMENTID": "equipment_id", "EQUIPMENTNAME": "equipment_name",
        "TRACKINTIMESTAMP": "trackin_time", "TRACKOUTTIMESTAMP": "trackout_time",
        "TRACKINQTY": "trackin_qty", "TRACKOUTQTY": "trackout_qty",
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


# ── Partial-trackout aggregation constants ─────────────────────────────────────

# 4-tuple key that defines one partial-trackout upload session (PH-06).
# TRACKINQTY is intentionally NOT a key — in this MES, TRACKINQTY records the
# qty AT EACH PARTIAL's start (i.e. remaining on the equipment), so successive
# partials of the same upload have DIFFERENT TRACKINQTY values.  Aggregation
# emits TRACKINQTY=MAX(...) (= the original load before any partial trackouts).
# A/B lot interleaving (A out → B in/out → A back in) is preserved because
# A's second upload has a DIFFERENT TRACKINTIMESTAMP from the first.
_PARTIAL_KEY_COLS = [
    "CONTAINERNAME", "SPECNAME", "EQUIPMENTID", "TRACKINTIMESTAMP",
]

# Non-key columns that must be identical within a group for aggregation (PH-07)
_PARTIAL_NONKEY_COLS = [
    "MFGORDERNAME", "FIRSTNAME", "PJ_TYPE", "PJ_BOP", "PJ_FUNCTION",
    "PRODUCTLINENAME", "WORKCENTERNAME", "EQUIPMENTNAME",
]


def _pandas_aggregate_partial_trackouts(
    df: Any,
    query_id: Optional[str] = None,
) -> Any:
    """Apply 4-tuple partial-trackout aggregation to a pandas DataFrame.

    Consistent groups (all non-key columns identical within the 4-tuple group)
    collapse to one row: TRACKOUTTIMESTAMP=MAX, TRACKOUTQTY=SUM, TRACKINQTY=MAX
    (= original load qty before any partial trackouts), partial_count=COUNT(*).
    Divergent groups (strict guard, PH-07) emit their original raw rows each
    with partial_count=1.  Emits one INFO log when divergent groups exist.

    Returns a DataFrame sorted by TRACKINTIMESTAMP ASC NULLS LAST, CONTAINERNAME.
    """
    import pandas as pd

    if df.empty:
        result = df.copy()
        result["partial_count"] = pd.array([], dtype="Int64")
        return result

    key_cols = [c for c in _PARTIAL_KEY_COLS if c in df.columns]
    nonkey_cols = [c for c in _PARTIAL_NONKEY_COLS if c in df.columns]

    grouped = df.groupby(key_cols, sort=False)

    agg_rows: List[Dict[str, Any]] = []
    raw_rows: List[Any] = []
    divergent_count = 0
    total_groups = grouped.ngroups

    for _, grp in grouped:
        # Check strict guard: all non-key columns must be identical
        is_consistent = all(
            grp[col].nunique(dropna=False) == 1
            for col in nonkey_cols
        )
        if is_consistent:
            # Aggregate: TRACKINQTY=MAX (original load), TRACKOUTTIMESTAMP=MAX,
            # TRACKOUTQTY=SUM (sum of all partial outs), partial_count=COUNT(*).
            row = grp.iloc[0].to_dict()
            if "TRACKINQTY" in grp.columns:
                row["TRACKINQTY"] = grp["TRACKINQTY"].max()
            if "TRACKOUTTIMESTAMP" in grp.columns:
                row["TRACKOUTTIMESTAMP"] = grp["TRACKOUTTIMESTAMP"].max()
            if "TRACKOUTQTY" in grp.columns:
                row["TRACKOUTQTY"] = grp["TRACKOUTQTY"].sum()
            row["partial_count"] = len(grp)
            agg_rows.append(row)
        else:
            # Strict guard fallback: emit raw rows with partial_count=1
            divergent_count += 1
            for _, raw_row in grp.iterrows():
                d = raw_row.to_dict()
                d["partial_count"] = 1
                raw_rows.append(d)

    # Emit summary INFO log when divergent groups exist (PH-07)
    if divergent_count > 0:
        logger.info(
            "partial-trackout strict-guard: %d divergent groups fell back to raw rows "
            "(query_id=%s, total_groups=%d)",
            divergent_count,
            query_id,
            total_groups,
        )

    parts: List[Any] = []
    if agg_rows:
        parts.append(pd.DataFrame(agg_rows))
    if raw_rows:
        parts.append(pd.DataFrame(raw_rows))

    if not parts:
        result = df.iloc[0:0].copy()
        result["partial_count"] = pd.array([], dtype="Int64")
        return result

    result = pd.concat(parts, ignore_index=True)

    # Sort: TRACKINTIMESTAMP ASC (NaT/None last), then CONTAINERNAME
    result = result.sort_values(
        by=["TRACKINTIMESTAMP", "CONTAINERNAME"],
        ascending=[True, True],
        na_position="last",
    ).reset_index(drop=True)

    # Ensure partial_count is int (not float from concat)
    result["partial_count"] = result["partial_count"].astype(int)

    return result


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

        # Emit raw distinct (wc, spec, eqp, month, container) tuples — NOT
        # pre-counted rows.  Distinct counts are non-additive across the
        # display hierarchy (PH-05), so all counting happens once in
        # _build_matrix_tree via Python sets, where the canonical
        # workcenter-group dedup also lives.  Row source is raw
        # LOTWIPHISTORY partial rows; SELECT DISTINCT collapses the
        # partial-row fan-out per (cell, container).
        agg_sql = f"""
            SELECT DISTINCT
                WORKCENTERNAME                                       AS wc,
                SPECNAME                                             AS spec,
                EQUIPMENTID                                          AS eqp_id,
                EQUIPMENTNAME                                        AS eqp_name,
                strftime(TRACKINTIMESTAMP::TIMESTAMP, '%Y-%m')       AS month_bucket,
                CONTAINERNAME                                        AS container
            FROM ph_src
            {where}
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
    """Build hierarchical tree from raw distinct-tuple rows.

    Each input row is a distinct ``(wc, spec, eqp_id, eqp_name, month_bucket,
    container)`` tuple.  Every node accumulates a Python ``set`` of container
    ids (and a per-month set); ``count`` / ``month_counts`` are derived via
    ``len()`` after the walk.  This is the single counting site — distinct
    counts are non-additive across the hierarchy (PH-05), so they must be
    re-evaluated independently per grain rather than summed from children.

    The canonical workcenter-group dedup happens here naturally: containers
    from several raw ``WORKCENTERNAME`` values that map to the same group
    (e.g. '焊_DB_料' → '焊接_DB') land in the same group node's set, so a
    container spanning two raw workcenters of one group is counted once.
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

    def _new_node(label: str, level: str, **extra: Any) -> Dict[str, Any]:
        node = {
            "label": label,
            "level": level,
            "_containers": set(),
            "_month_containers": {},
            "children": {},
        }
        node.update(extra)
        return node

    def _accumulate(node: Dict[str, Any], month: str, container: str) -> None:
        node["_containers"].add(container)
        if month:
            node["_month_containers"].setdefault(month, set()).add(container)

    for r in rows:
        raw_wc = str(r.get("wc") or "")
        spec = str(r.get("spec") or "")
        eqp_id = str(r.get("eqp_id") or "")
        eqp_name = str(r.get("eqp_name") or "")
        month = str(r.get("month_bucket") or "")
        container = str(r.get("container") or "")

        # Resolve workcenter to its group
        group_name, order = get_workcenter_group(raw_wc)
        wc_label = group_name if group_name else raw_wc
        wc_order.setdefault(wc_label, order)

        if wc_label not in wc_map:
            wc_map[wc_label] = _new_node(wc_label, "workcenter")
        wc_node = wc_map[wc_label]

        spec_key = spec
        if spec_key not in wc_node["children"]:
            wc_node["children"][spec_key] = _new_node(spec, "spec")
        spec_node = wc_node["children"][spec_key]

        eqp_key = eqp_id
        if eqp_key not in spec_node["children"]:
            spec_node["children"][eqp_key] = _new_node(
                eqp_id, "equipment", equipment_name=eqp_name,
            )
        eqp_node = spec_node["children"][eqp_key]

        _accumulate(eqp_node, month, container)
        _accumulate(spec_node, month, container)
        _accumulate(wc_node, month, container)

    def _flatten(node_map: Dict) -> List[Dict]:
        result = []
        for node in node_map.values():
            n = dict(node)
            # Convert transient container sets → distinct counts, then drop
            # the transient keys so the node shape stays
            # {label, level, count, month_counts, children}.
            containers = n.pop("_containers")
            month_containers = n.pop("_month_containers")
            n["count"] = len(containers)
            n["month_counts"] = {m: len(s) for m, s in month_containers.items()}
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


def _apply_pandas_wc_group_filter(df: "pd.DataFrame", group_name: str, workcenter_groups: Dict) -> "pd.DataFrame":  # noqa: F821
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


def _apply_pandas_filter(df: "pd.DataFrame", filter_params: Dict[str, Any]) -> "pd.DataFrame":  # noqa: F821
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
        df = df[pd.to_datetime(df["TRACKINTIMESTAMP"], errors="coerce").dt.strftime("%Y-%m") == month]

    # ── Supplementary multi-select filters (arrays) ──────────────────────────
    _SUPP_COLUMNS = [
        ("work_orders", "MFGORDERNAME"),
        ("lot_ids", "CONTAINERNAME"),
        ("packages", "PRODUCTLINENAME"),
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

    df["month_bucket"] = pd.to_datetime(df["TRACKINTIMESTAMP"], errors="coerce").dt.strftime("%Y-%m")
    # Emit raw distinct (wc, spec, eqp, month, container) tuples — identical
    # row contract to compute_matrix_view's SELECT DISTINCT.  All distinct
    # counting (incl. canonical-group dedup) happens in _build_matrix_tree.
    distinct = (
        df[["WORKCENTERNAME", "SPECNAME", "EQUIPMENTID", "EQUIPMENTNAME",
            "month_bucket", "CONTAINERNAME"]]
        .drop_duplicates()
    )
    distinct.columns = ["wc", "spec", "eqp_id", "eqp_name", "month_bucket", "container"]
    return _build_matrix_tree(distinct.to_dict(orient="records"))


# ── Filter options ────────────────────────────────────────────────────────────

def compute_filter_options(
    spool_path: str,
    filter_params: Optional[Dict[str, Any]] = None,
) -> Dict[str, List[str]]:
    """Return distinct values for each filterable column in the spool.

    Supports cross-filtering (exclude-self pattern): when filter_params contains
    staged selections, each field's options are narrowed by all OTHER fields'
    selections so incompatible combinations cannot be built.

    Args:
        spool_path: Absolute path to the Parquet spool file.
        filter_params: Optional staged filter dict.  For each returned field the
            filter is applied with that field's own key excluded, so the user
            can still see all valid values for the field they are currently
            configuring.

    Returns:
        {work_orders, lot_ids, packages, bop_codes, workcenter_groups, equipment_ids}
        All values are sorted strings.  Empty lists are returned on any
        non-MemoryError failure so the caller always gets a safe dict.
    """
    filter_params = filter_params or {}

    _SIMPLE_COLUMNS = [
        ("work_orders",  "MFGORDERNAME"),
        ("lot_ids",      "CONTAINERNAME"),
        ("packages",     "PRODUCTLINENAME"),
        ("bop_codes",    "PJ_BOP"),
    ]

    empty: Dict[str, List[str]] = {k: [] for k, _ in _SIMPLE_COLUMNS}
    empty["workcenter_groups"] = []
    empty["equipment_ids"] = []

    if not _SQL_VIEW_ENABLED:
        logger.debug("compute_filter_options: SQL view disabled, returning empty options")
        return empty

    def _col_where(col: str, exclude_key: str, params: Dict[str, Any]) -> tuple[str, List[Any]]:
        """Build WHERE for a single-column DISTINCT query with cross-filter applied."""
        cross = {k: v for k, v in params.items() if k != exclude_key}
        base_where, bind = _build_filter_where(cross)
        not_null = f"{_qid(col)} IS NOT NULL AND {_qid(col)} != ''"
        if base_where:
            return f"{base_where} AND {not_null}", bind
        return f"WHERE {not_null}", bind

    try:
        from mes_dashboard.config.workcenter_groups import get_workcenter_group

        conn = _get_duckdb_conn()
        _attach_spool_view(conn, spool_path)

        result: Dict[str, List[str]] = {}

        # Simple columns — cross-filtered (exclude self)
        for key, col in _SIMPLE_COLUMNS:
            where, bind = _col_where(col, key, filter_params)
            sql = f"SELECT DISTINCT {_qid(col)} AS val FROM ph_src {where} ORDER BY val"
            rows = _fetch_dict_rows(conn, sql, bind)
            result[key] = [str(r["val"]) for r in rows]

        # workcenter_groups — map raw WORKCENTERNAME → canonical group, cross-filtered
        wc_where, wc_bind = _col_where("WORKCENTERNAME", "workcenter_groups", filter_params)
        wc_sql = f'SELECT DISTINCT "WORKCENTERNAME" AS val FROM ph_src {wc_where}'
        wc_rows = _fetch_dict_rows(conn, wc_sql, wc_bind)
        group_set: Dict[str, int] = {}
        for r in wc_rows:
            gname, order = get_workcenter_group(str(r["val"]))
            label = gname if gname else str(r["val"])
            group_set.setdefault(label, order)
        result["workcenter_groups"] = [
            name for name, _ in sorted(group_set.items(), key=lambda x: (x[1], x[0]))
        ]

        # equipment_ids — use EQUIPMENTNAME, cross-filtered
        eqp_where, eqp_bind = _col_where("EQUIPMENTNAME", "equipment_ids", filter_params)
        eqp_sql = f'SELECT DISTINCT "EQUIPMENTNAME" AS val FROM ph_src {eqp_where} ORDER BY val'
        eqp_rows = _fetch_dict_rows(conn, eqp_sql, eqp_bind)
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
    """Stream CSV rows from spool applying partial-trackout aggregation (PH-06/PH-07).

    Yields:
        CSV row strings (header first, then data rows).
        Column 16 (final) is PartialCount \u2014 additive per api-contract.md \u00a710.
    """
    EXPORT_COLUMNS = [
        ("CONTAINERNAME", "LotID"),
        ("PJ_TYPE", "Type"),
        ("PRODUCTLINENAME", "Package"),
        ("PJ_BOP", "BOP"),
        ("PJ_FUNCTION", "Function"),
        ("MFGORDERNAME", "WorkOrder"),
        ("FIRSTNAME", "WaferLot"),
        ("WORKCENTERNAME", "WorkCenter"),
        ("SPECNAME", "Spec"),
        ("EQUIPMENTID", "EquipmentID"),
        ("EQUIPMENTNAME", "EquipmentName"),
        ("TRACKINTIMESTAMP", "TrackInTime"),
        ("TRACKOUTTIMESTAMP", "TrackOutTime"),
        ("TRACKINQTY", "TrackInQty"),
        ("TRACKOUTQTY", "TrackOutQty"),
        ("partial_count", "PartialCount"),  # column 16 \u2014 additive per api-contract \u00a710
    ]

    where, params = _build_filter_where(filter_params)
    # See compute_detail_page for why the raw branch needs AND, not WHERE.
    where_for_raw = (" AND " + where[len("WHERE "):]) if where else ""

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

        # Build same aggregation CTE as compute_detail_page (PH-06/PH-07) — 4-tuple key
        agg_cte_sql = f"""
            WITH grouped AS (
                SELECT
                    CONTAINERNAME, SPECNAME, EQUIPMENTID, TRACKINTIMESTAMP,
                    COUNT(*) AS partial_count,
                    MAX(TRACKINQTY)        AS TRACKINQTY,
                    MAX(TRACKOUTTIMESTAMP) AS TRACKOUTTIMESTAMP,
                    SUM(TRACKOUTQTY)       AS TRACKOUTQTY,
                    COUNT(DISTINCT MFGORDERNAME)    AS dc_work_order,
                    COUNT(DISTINCT FIRSTNAME)        AS dc_wafer_lot,
                    COUNT(DISTINCT PJ_TYPE)          AS dc_pj_type,
                    COUNT(DISTINCT PJ_BOP)           AS dc_pj_bop,
                    COUNT(DISTINCT PJ_FUNCTION)      AS dc_pj_function,
                    COUNT(DISTINCT PRODUCTLINENAME)  AS dc_package,
                    COUNT(DISTINCT WORKCENTERNAME)   AS dc_wc,
                    COUNT(DISTINCT EQUIPMENTNAME)    AS dc_eq_name,
                    ANY_VALUE(MFGORDERNAME)    AS MFGORDERNAME,
                    ANY_VALUE(FIRSTNAME)       AS FIRSTNAME,
                    ANY_VALUE(PJ_TYPE)         AS PJ_TYPE,
                    ANY_VALUE(PJ_BOP)          AS PJ_BOP,
                    ANY_VALUE(PJ_FUNCTION)     AS PJ_FUNCTION,
                    ANY_VALUE(PRODUCTLINENAME) AS PRODUCTLINENAME,
                    ANY_VALUE(WORKCENTERNAME)  AS WORKCENTERNAME,
                    ANY_VALUE(EQUIPMENTNAME)   AS EQUIPMENTNAME
                FROM ph_src
                {where}
                GROUP BY CONTAINERNAME, SPECNAME, EQUIPMENTID, TRACKINTIMESTAMP
            ),
            agg AS (
                SELECT * FROM grouped
                WHERE dc_work_order=1 AND dc_wafer_lot=1 AND dc_pj_type=1 AND dc_pj_bop=1
                  AND dc_pj_function=1 AND dc_package=1 AND dc_wc=1 AND dc_eq_name=1
            ),
            raw AS (
                SELECT
                    p.CONTAINERNAME, p.SPECNAME, p.EQUIPMENTID,
                    p.TRACKINTIMESTAMP,
                    1 AS partial_count,
                    p.TRACKINQTY,
                    p.TRACKOUTTIMESTAMP, p.TRACKOUTQTY,
                    0 AS dc_work_order, 0 AS dc_wafer_lot, 0 AS dc_pj_type, 0 AS dc_pj_bop,
                    0 AS dc_pj_function, 0 AS dc_package, 0 AS dc_wc, 0 AS dc_eq_name,
                    p.MFGORDERNAME, p.FIRSTNAME, p.PJ_TYPE, p.PJ_BOP,
                    p.PJ_FUNCTION, p.PRODUCTLINENAME, p.WORKCENTERNAME, p.EQUIPMENTNAME
                FROM ph_src p
                WHERE (p.CONTAINERNAME, p.SPECNAME, p.EQUIPMENTID,
                       p.TRACKINTIMESTAMP) IN (
                    SELECT CONTAINERNAME, SPECNAME, EQUIPMENTID, TRACKINTIMESTAMP
                    FROM grouped
                    WHERE dc_work_order>1 OR dc_wafer_lot>1 OR dc_pj_type>1 OR dc_pj_bop>1
                       OR dc_pj_function>1 OR dc_package>1 OR dc_wc>1 OR dc_eq_name>1
                )
                {where_for_raw}
            ),
            combined AS (
                SELECT * FROM agg UNION ALL SELECT * FROM raw
            )
        """

        # Compute divergent-group count for summary INFO log
        log_sql = f"""
            {agg_cte_sql}
            SELECT
                (SELECT COUNT(DISTINCT (CONTAINERNAME, SPECNAME, EQUIPMENTID,
                                        TRACKINTIMESTAMP)) FROM grouped
                 WHERE dc_work_order>1 OR dc_wafer_lot>1 OR dc_pj_type>1 OR dc_pj_bop>1
                    OR dc_pj_function>1 OR dc_package>1 OR dc_wc>1 OR dc_eq_name>1
                ) AS divergent_groups,
                (SELECT COUNT(*) FROM grouped) AS total_groups
        """
        log_row = conn.execute(log_sql, params + params).fetchone()
        if log_row:
            divergent_groups = int(log_row[0]) if log_row[0] is not None else 0
            total_groups = int(log_row[1]) if log_row[1] is not None else 0
            if divergent_groups > 0:
                query_id = filter_params.get("query_id")
                logger.info(
                    "partial-trackout strict-guard: %d divergent groups fell back to raw rows "
                    "(query_id=%s, total_groups=%d)",
                    divergent_groups,
                    query_id,
                    total_groups,
                )

        # Stream aggregated rows in batches
        # Build column select from EXPORT_COLUMNS (excluding partial_count which is already in CTE)
        _NON_PARTIAL_EXPORT = [(s, d) for s, d in EXPORT_COLUMNS if s != "partial_count"]
        col_selects = ", ".join(
            f"{_qid(src)} AS {_qid(dst)}" for src, dst in _NON_PARTIAL_EXPORT
        ) + ', "partial_count" AS "PartialCount"'

        while True:
            sql = f"""
                {agg_cte_sql}
                SELECT {col_selects}
                FROM combined
                ORDER BY TRACKINTIMESTAMP ASC NULLS LAST, CONTAINERNAME
                LIMIT {BATCH_SIZE} OFFSET {offset}
            """
            rows = _fetch_dict_rows(conn, sql, params + params)
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
    """Pandas fallback for stream_export \u2014 applies the same partial-trackout aggregation."""
    import pandas as pd

    df = pd.read_parquet(spool_path)
    df = _apply_pandas_filter(df, filter_params)

    # Apply same 4-tuple aggregation as DuckDB path (PH-06/PH-07)
    df = _pandas_aggregate_partial_trackouts(df, query_id=filter_params.get("query_id"))

    buf = io.StringIO()
    writer = csv.writer(buf)
    BATCH = 500

    # Build a mapping from column name \u2192 CSV header for the aggregated DataFrame
    # EXPORT_COLUMNS uses raw Oracle column names for non-partial_count columns
    # but the aggregated df retains original column names, so we read by src name.
    # For partial_count column we use the column name directly.
    _RENAME_BACK = {
        "LotID": "CONTAINERNAME", "Type": "PJ_TYPE", "Package": "PRODUCTLINENAME",
        "BOP": "PJ_BOP", "Function": "PJ_FUNCTION", "WorkOrder": "MFGORDERNAME",
        "WaferLot": "FIRSTNAME", "WorkCenter": "WORKCENTERNAME", "Spec": "SPECNAME",
        "EquipmentID": "EQUIPMENTID", "EquipmentName": "EQUIPMENTNAME",
        "TrackInTime": "TRACKINTIMESTAMP", "TrackOutTime": "TRACKOUTTIMESTAMP",
        "TrackInQty": "TRACKINQTY", "TrackOutQty": "TRACKOUTQTY",
        "PartialCount": "partial_count",
    }

    for i in range(0, max(len(df), 1), BATCH):
        chunk = df.iloc[i: i + BATCH]
        for _, row in chunk.iterrows():
            csv_row = []
            for src, dst in columns:
                # src is the Oracle column name (or 'partial_count'); dst is CSV header
                col_name = src if src != "partial_count" else "partial_count"
                csv_row.append(row.get(col_name, ""))
            writer.writerow(csv_row)
        yield buf.getvalue()
        buf.truncate(0)
        buf.seek(0)
