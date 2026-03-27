# -*- coding: utf-8 -*-
"""DuckDB SQL runtime for resource-history view computation.

Provides out-of-core view aggregation (kpi / trend / heatmap /
workcenter_comparison / detail) by querying Parquet spool files directly via
DuckDB, avoiding full DataFrame loads into pandas.

Entry point: ``try_compute_view_from_spool``
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from mes_dashboard.core.feature_flags import resolve_bool_flag
from mes_dashboard.core.query_spool_store import get_spool_file_path

logger = logging.getLogger("mes_dashboard.resource_history_sql_runtime")

# ── Feature flag ──────────────────────────────────────────────────────────────
_SQL_VIEW_ENABLED = resolve_bool_flag("RESOURCE_HISTORY_SQL_VIEW_ENABLED", default=True)

SQL_FALLBACK_DISABLED = "resource_history_sql_disabled"
SQL_FALLBACK_DEP_MISSING = "resource_history_sql_dependency_missing"
SQL_FALLBACK_SPOOL_MISS = "resource_history_sql_spool_miss"
SQL_FALLBACK_RUNTIME_ERROR = "resource_history_sql_runtime_error"

_SPOOL_NAMESPACE = "resource_dataset"


# ── SQL helpers ───────────────────────────────────────────────────────────────

def _qid(name: str) -> str:
    """Quote a DuckDB identifier."""
    return '"' + str(name).replace('"', '""') + '"'


def _sql_str_literal(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _attach_spool_view(conn: Any, parquet_path: str) -> None:
    conn.execute(
        "CREATE OR REPLACE TEMP VIEW resource_src AS "
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


def _calc_ou_pct(prd: float, sby: float, udt: float, sdt: float, egt: float) -> float:
    denom = prd + sby + udt + sdt + egt
    return round(prd / denom * 100, 1) if denom > 0 else 0.0


def _calc_avail_pct(prd: float, sby: float, udt: float, sdt: float, egt: float, nst: float) -> float:
    num = prd + sby + egt
    denom = prd + sby + egt + sdt + udt + nst
    return round(num / denom * 100, 1) if denom > 0 else 0.0


def _status_pct(val: float, total: float) -> float:
    return round(val / total * 100, 1) if total > 0 else 0.0


# ── Date bucket expression ────────────────────────────────────────────────────

def _granularity_bucket_expr(granularity: str, col: str = "DATA_DATE") -> str:
    """DuckDB SQL expression for date bucketing from DATA_DATE."""
    qcol = _qid(col)
    if granularity == "year":
        return f"strftime(CAST({qcol} AS DATE), '%Y')"
    if granularity == "month":
        return f"strftime(CAST({qcol} AS DATE), '%Y-%m')"
    if granularity == "week":
        return f"strftime(date_trunc('week', CAST({qcol} AS DATE)), '%Y-%m-%d')"
    # day (default)
    return f"strftime(CAST({qcol} AS DATE), '%Y-%m-%d')"


# ── Resource lookup table ─────────────────────────────────────────────────────

def _build_resource_lookup_table(
    conn: Any,
    resource_lookup: Dict[str, Dict[str, Any]],
    wc_mapping: Dict[str, Dict[str, Any]],
) -> None:
    """Register resource dimension data as a DuckDB temp table.

    Columns: HISTORYID, WC_GROUP, WC_SEQ, FAMILY, RESOURCE
    """
    rows = []
    for historyid, info in resource_lookup.items():
        wc_name = str(info.get("WORKCENTERNAME") or "")
        wc_info = wc_mapping.get(wc_name, {})
        wc_group = str(wc_info.get("group") or wc_name)
        wc_seq = int(wc_info.get("sequence") or 999)
        family = str(info.get("RESOURCEFAMILYNAME") or "")
        resource = str(info.get("RESOURCENAME") or "")
        rows.append((str(historyid), wc_group, wc_seq, family, resource))

    if not rows:
        conn.execute(
            "CREATE OR REPLACE TEMP TABLE resource_dim AS "
            "SELECT '' AS HISTORYID, '' AS WC_GROUP, 999 AS WC_SEQ, "
            "'' AS FAMILY, '' AS RESOURCE LIMIT 0"
        )
        return

    import pyarrow as pa  # type: ignore
    table = pa.table({
        "HISTORYID": pa.array([r[0] for r in rows], type=pa.large_utf8()),
        "WC_GROUP": pa.array([r[1] for r in rows], type=pa.large_utf8()),
        "WC_SEQ": pa.array([r[2] for r in rows], type=pa.int64()),
        "FAMILY": pa.array([r[3] for r in rows], type=pa.large_utf8()),
        "RESOURCE": pa.array([r[4] for r in rows], type=pa.large_utf8()),
    })
    conn.register("_resource_dim_arrow", table)
    conn.execute(
        "CREATE OR REPLACE TEMP TABLE resource_dim AS "
        "SELECT CAST(HISTORYID AS VARCHAR) AS HISTORYID, "
        "CAST(WC_GROUP AS VARCHAR) AS WC_GROUP, "
        "WC_SEQ, "
        "CAST(FAMILY AS VARCHAR) AS FAMILY, "
        "CAST(RESOURCE AS VARCHAR) AS RESOURCE "
        "FROM _resource_dim_arrow"
    )


# ── Task 3.2: KPI summary SQL ─────────────────────────────────────────────────

def _query_kpi(conn: Any) -> Dict[str, Any]:
    """Compute overall KPI metrics via DuckDB aggregation."""
    sql = """
        SELECT
            COALESCE(SUM("PRD_HOURS"), 0) AS prd,
            COALESCE(SUM("SBY_HOURS"), 0) AS sby,
            COALESCE(SUM("UDT_HOURS"), 0) AS udt,
            COALESCE(SUM("SDT_HOURS"), 0) AS sdt,
            COALESCE(SUM("EGT_HOURS"), 0) AS egt,
            COALESCE(SUM("NST_HOURS"), 0) AS nst,
            COALESCE(SUM("TOTAL_HOURS"), 0) AS total,
            COUNT(DISTINCT CAST("HISTORYID" AS VARCHAR)) AS machine_count
        FROM resource_src
    """
    rows = _fetch_dict_rows(conn, sql)
    if not rows:
        return _empty_kpi()

    r = rows[0]
    prd = _sf(r.get("prd"))
    sby = _sf(r.get("sby"))
    udt = _sf(r.get("udt"))
    sdt = _sf(r.get("sdt"))
    egt = _sf(r.get("egt"))
    nst = _sf(r.get("nst"))
    total = _sf(r.get("total"))
    machine_count = int(r.get("machine_count") or 0)

    return {
        "ou_pct": _calc_ou_pct(prd, sby, udt, sdt, egt),
        "availability_pct": _calc_avail_pct(prd, sby, udt, sdt, egt, nst),
        "prd_hours": round(prd, 1),
        "prd_pct": _status_pct(prd, total),
        "sby_hours": round(sby, 1),
        "sby_pct": _status_pct(sby, total),
        "udt_hours": round(udt, 1),
        "udt_pct": _status_pct(udt, total),
        "sdt_hours": round(sdt, 1),
        "sdt_pct": _status_pct(sdt, total),
        "egt_hours": round(egt, 1),
        "egt_pct": _status_pct(egt, total),
        "nst_hours": round(nst, 1),
        "nst_pct": _status_pct(nst, total),
        "machine_count": machine_count,
    }


# ── Task 3.3: Trend SQL ───────────────────────────────────────────────────────

def _query_trend(conn: Any, *, granularity: str) -> List[Dict[str, Any]]:
    """Compute date-bucketed trend via DuckDB GROUP BY."""
    bucket_expr = _granularity_bucket_expr(granularity)
    sql = f"""
        SELECT
            {bucket_expr} AS period,
            COALESCE(SUM("PRD_HOURS"), 0) AS prd,
            COALESCE(SUM("SBY_HOURS"), 0) AS sby,
            COALESCE(SUM("UDT_HOURS"), 0) AS udt,
            COALESCE(SUM("SDT_HOURS"), 0) AS sdt,
            COALESCE(SUM("EGT_HOURS"), 0) AS egt,
            COALESCE(SUM("NST_HOURS"), 0) AS nst
        FROM resource_src
        GROUP BY 1
        ORDER BY 1
    """
    rows = _fetch_dict_rows(conn, sql)
    items: List[Dict[str, Any]] = []
    for r in rows:
        prd = _sf(r.get("prd"))
        sby = _sf(r.get("sby"))
        udt = _sf(r.get("udt"))
        sdt = _sf(r.get("sdt"))
        egt = _sf(r.get("egt"))
        nst = _sf(r.get("nst"))
        items.append({
            "date": str(r.get("period") or ""),
            "ou_pct": _calc_ou_pct(prd, sby, udt, sdt, egt),
            "availability_pct": _calc_avail_pct(prd, sby, udt, sdt, egt, nst),
            "prd_hours": round(prd, 1),
            "sby_hours": round(sby, 1),
            "udt_hours": round(udt, 1),
            "sdt_hours": round(sdt, 1),
            "egt_hours": round(egt, 1),
            "nst_hours": round(nst, 1),
        })
    return items


# ── Task 3.4: Heatmap SQL ─────────────────────────────────────────────────────

def _query_heatmap(conn: Any, *, granularity: str) -> List[Dict[str, Any]]:
    """Compute workcenter × date OU% matrix via DuckDB JOIN + GROUP BY."""
    bucket_expr = _granularity_bucket_expr(granularity)
    sql = f"""
        SELECT
            d.WC_GROUP AS workcenter,
            MIN(d.WC_SEQ) AS workcenter_seq,
            {bucket_expr.replace('"DATA_DATE"', 's."DATA_DATE"')} AS date,
            COALESCE(SUM(s."PRD_HOURS"), 0) AS prd,
            COALESCE(SUM(s."SBY_HOURS"), 0) AS sby,
            COALESCE(SUM(s."UDT_HOURS"), 0) AS udt,
            COALESCE(SUM(s."SDT_HOURS"), 0) AS sdt,
            COALESCE(SUM(s."EGT_HOURS"), 0) AS egt
        FROM resource_src s
        JOIN resource_dim d ON CAST(s."HISTORYID" AS VARCHAR) = d.HISTORYID
        WHERE d.WC_GROUP <> ''
        GROUP BY d.WC_GROUP, {bucket_expr.replace('"DATA_DATE"', 's."DATA_DATE"')}
        ORDER BY MIN(d.WC_SEQ), date
    """
    rows = _fetch_dict_rows(conn, sql)
    items: List[Dict[str, Any]] = []
    for r in rows:
        prd = _sf(r.get("prd"))
        sby = _sf(r.get("sby"))
        udt = _sf(r.get("udt"))
        sdt = _sf(r.get("sdt"))
        egt = _sf(r.get("egt"))
        items.append({
            "workcenter": str(r.get("workcenter") or ""),
            "workcenter_seq": int(r.get("workcenter_seq") or 999),
            "date": str(r.get("date") or ""),
            "ou_pct": _calc_ou_pct(prd, sby, udt, sdt, egt),
        })
    return items


# ── Task 3.5: Workcenter comparison SQL ───────────────────────────────────────

def _query_workcenter_comparison(conn: Any) -> List[Dict[str, Any]]:
    """Compute per-workcenter aggregated metrics, sorted by OU% DESC, LIMIT 15."""
    sql = """
        SELECT
            d.WC_GROUP AS workcenter,
            COALESCE(SUM(s."PRD_HOURS"), 0) AS prd,
            COALESCE(SUM(s."SBY_HOURS"), 0) AS sby,
            COALESCE(SUM(s."UDT_HOURS"), 0) AS udt,
            COALESCE(SUM(s."SDT_HOURS"), 0) AS sdt,
            COALESCE(SUM(s."EGT_HOURS"), 0) AS egt,
            COUNT(DISTINCT CAST(s."HISTORYID" AS VARCHAR)) AS machine_count
        FROM resource_src s
        JOIN resource_dim d ON CAST(s."HISTORYID" AS VARCHAR) = d.HISTORYID
        WHERE d.WC_GROUP <> ''
        GROUP BY d.WC_GROUP
        ORDER BY prd / NULLIF(prd + sby + udt + sdt + egt, 0) DESC NULLS LAST
        LIMIT 15
    """
    rows = _fetch_dict_rows(conn, sql)
    items: List[Dict[str, Any]] = []
    for r in rows:
        prd = _sf(r.get("prd"))
        sby = _sf(r.get("sby"))
        udt = _sf(r.get("udt"))
        sdt = _sf(r.get("sdt"))
        egt = _sf(r.get("egt"))
        items.append({
            "workcenter": str(r.get("workcenter") or ""),
            "ou_pct": _calc_ou_pct(prd, sby, udt, sdt, egt),
            "prd_hours": round(prd, 1),
            "machine_count": int(r.get("machine_count") or 0),
        })
    return items


# ── Task 3.6: Detail SQL ──────────────────────────────────────────────────────

def _query_detail(conn: Any) -> Dict[str, Any]:
    """Compute per-resource metrics via DuckDB JOIN, sorted by workcenter/family/resource."""
    sql = """
        SELECT
            CAST(s."HISTORYID" AS VARCHAR) AS historyid,
            d.WC_GROUP AS workcenter,
            d.WC_SEQ AS workcenter_seq,
            d.FAMILY AS family,
            d.RESOURCE AS resource,
            COALESCE(SUM(s."PRD_HOURS"), 0) AS prd,
            COALESCE(SUM(s."SBY_HOURS"), 0) AS sby,
            COALESCE(SUM(s."UDT_HOURS"), 0) AS udt,
            COALESCE(SUM(s."SDT_HOURS"), 0) AS sdt,
            COALESCE(SUM(s."EGT_HOURS"), 0) AS egt,
            COALESCE(SUM(s."NST_HOURS"), 0) AS nst,
            COALESCE(SUM(s."TOTAL_HOURS"), 0) AS total
        FROM resource_src s
        JOIN resource_dim d ON CAST(s."HISTORYID" AS VARCHAR) = d.HISTORYID
        GROUP BY CAST(s."HISTORYID" AS VARCHAR), d.WC_GROUP, d.WC_SEQ, d.FAMILY, d.RESOURCE
        ORDER BY d.WC_SEQ, d.FAMILY, d.RESOURCE
    """
    rows = _fetch_dict_rows(conn, sql)
    data: List[Dict[str, Any]] = []
    for r in rows:
        prd = _sf(r.get("prd"))
        sby = _sf(r.get("sby"))
        udt = _sf(r.get("udt"))
        sdt = _sf(r.get("sdt"))
        egt = _sf(r.get("egt"))
        nst = _sf(r.get("nst"))
        total = _sf(r.get("total"))
        data.append({
            "workcenter": str(r.get("workcenter") or ""),
            "workcenter_seq": int(r.get("workcenter_seq") or 999),
            "family": str(r.get("family") or ""),
            "resource": str(r.get("resource") or ""),
            "ou_pct": _calc_ou_pct(prd, sby, udt, sdt, egt),
            "availability_pct": _calc_avail_pct(prd, sby, udt, sdt, egt, nst),
            "prd_hours": round(prd, 1),
            "prd_pct": _status_pct(prd, total),
            "sby_hours": round(sby, 1),
            "sby_pct": _status_pct(sby, total),
            "udt_hours": round(udt, 1),
            "udt_pct": _status_pct(udt, total),
            "sdt_hours": round(sdt, 1),
            "sdt_pct": _status_pct(sdt, total),
            "egt_hours": round(egt, 1),
            "egt_pct": _status_pct(egt, total),
            "nst_hours": round(nst, 1),
            "nst_pct": _status_pct(nst, total),
            "machine_count": 1,
        })
    return {
        "data": data,
        "total": len(data),
        "truncated": False,
        "max_records": None,
    }


# ── Empty fallbacks ───────────────────────────────────────────────────────────

def _empty_kpi() -> Dict[str, Any]:
    return {
        "ou_pct": 0, "availability_pct": 0,
        "prd_hours": 0, "prd_pct": 0,
        "sby_hours": 0, "sby_pct": 0,
        "udt_hours": 0, "udt_pct": 0,
        "sdt_hours": 0, "sdt_pct": 0,
        "egt_hours": 0, "egt_pct": 0,
        "nst_hours": 0, "nst_pct": 0,
        "machine_count": 0,
    }


# ── Task 3.1 + 3.7: Entry point ───────────────────────────────────────────────

def try_compute_view_from_spool(
    *,
    query_id: str,
    granularity: str = "day",
) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
    """Try to compute the full view result via DuckDB over the Parquet spool.

    Returns ``(result_dict, meta)`` on success, or ``(None, meta)`` on failure.
    On failure the caller should fall back to Pandas-based derivation.
    ``meta["view_sql_fallback_reason"]`` is set when returning None.
    """
    if not _SQL_VIEW_ENABLED:
        return None, {"view_sql_fallback_reason": SQL_FALLBACK_DISABLED}

    try:
        import duckdb  # type: ignore
    except Exception:
        return None, {"view_sql_fallback_reason": SQL_FALLBACK_DEP_MISSING}

    parquet_path = get_spool_file_path(_SPOOL_NAMESPACE, query_id)
    if not parquet_path:
        return None, {"view_sql_fallback_reason": SQL_FALLBACK_SPOOL_MISS}

    # Load resource dimension data (needed for heatmap / comparison / detail)
    try:
        from mes_dashboard.services.resource_dataset_cache import (
            _get_resource_lookup,
            _get_workcenter_mapping,
        )
        resource_lookup = _get_resource_lookup()
        wc_mapping = _get_workcenter_mapping()
    except Exception as exc:
        logger.warning("resource_history_sql_runtime: failed to load dimension data: %s", exc)
        return None, {"view_sql_fallback_reason": SQL_FALLBACK_RUNTIME_ERROR}

    started_at = time.time()
    conn = None
    try:
        conn = duckdb.connect(database=":memory:")
        _attach_spool_view(conn, parquet_path)
        _build_resource_lookup_table(conn, resource_lookup, wc_mapping)

        kpi = _query_kpi(conn)
        trend_items = _query_trend(conn, granularity=granularity)
        heatmap_items = _query_heatmap(conn, granularity=granularity)
        comparison_items = _query_workcenter_comparison(conn)
        detail = _query_detail(conn)

        latency_s = round(time.time() - started_at, 3)
        logger.info(
            "resource_history_sql_runtime: view computed via DuckDB "
            "(query_id=%s latency_s=%.3f)",
            query_id, latency_s,
        )

        result = {
            "summary": {
                "kpi": kpi,
                "trend": trend_items,
                "heatmap": heatmap_items,
                "workcenter_comparison": comparison_items,
            },
            "detail": detail,
        }
        meta = {"view_sql_latency_s": latency_s}
        return result, meta

    except Exception as exc:
        logger.warning(
            "resource_history_sql_runtime: DuckDB view failed (query_id=%s): %s",
            query_id, exc,
        )
        return None, {"view_sql_fallback_reason": SQL_FALLBACK_RUNTIME_ERROR}
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


# ── Task 7.2: Canonical base spool query with view-time filter predicates ─────

def try_compute_query_from_canonical_spool(
    *,
    start_date: str,
    end_date: str,
    granularity: str = "day",
    workcenter_groups=None,
    families=None,
    resource_ids=None,
    is_production: bool = False,
    is_key: bool = False,
    is_monitor: bool = False,
) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
    """Check canonical base spool and compute query result with filter predicates in DuckDB.

    The canonical base spool (no filter, date-range only) is checked first.
    If found, filter dimensions (workcenter_groups / families / resource_ids / flags)
    are applied via an INNER JOIN against resource_dim so that kpi / trend /
    heatmap / comparison / detail all see only the filtered subset.

    Route contract remains unchanged — same params and response shape as
    ``execute_primary_query``.  Returns ``(result_dict, meta)`` with
    ``result["query_id"]`` set to the canonical query_id, or ``(None, meta)``
    when the canonical spool is not yet available (cache miss → fall through to
    Oracle path).
    """
    if not _SQL_VIEW_ENABLED:
        return None, {"canonical_fallback_reason": SQL_FALLBACK_DISABLED}

    try:
        import duckdb  # type: ignore
    except Exception:
        return None, {"canonical_fallback_reason": SQL_FALLBACK_DEP_MISSING}

    from mes_dashboard.services.resource_dataset_cache import make_canonical_base_query_id
    canonical_query_id = make_canonical_base_query_id(start_date, end_date, granularity)
    parquet_path = get_spool_file_path(_SPOOL_NAMESPACE, canonical_query_id)
    if not parquet_path:
        return None, {"canonical_fallback_reason": SQL_FALLBACK_SPOOL_MISS}

    try:
        from mes_dashboard.services.resource_history_service import (
            _get_filtered_resources,
            _build_resource_lookup,
        )
        from mes_dashboard.services.resource_dataset_cache import _get_workcenter_mapping
        resources = _get_filtered_resources(
            workcenter_groups=workcenter_groups,
            families=families,
            resource_ids=resource_ids,
            is_production=is_production,
            is_key=is_key,
            is_monitor=is_monitor,
        )
        resource_lookup = _build_resource_lookup(resources)
        wc_mapping = _get_workcenter_mapping()
    except Exception as exc:
        logger.warning(
            "try_compute_query_from_canonical_spool: dimension load failed: %s", exc
        )
        return None, {"canonical_fallback_reason": SQL_FALLBACK_RUNTIME_ERROR}

    started_at = time.time()
    conn = None
    try:
        conn = duckdb.connect(database=":memory:")
        # Load all spool rows into resource_all, then build filter-specific
        # resource_dim, then create resource_src as the filtered join view so
        # all existing query functions (_query_kpi, _query_trend, etc.) see
        # only the filtered subset without any code changes.
        conn.execute(
            "CREATE TEMP VIEW resource_all AS "
            f"SELECT * FROM read_parquet({_sql_str_literal(parquet_path)})"
        )
        _build_resource_lookup_table(conn, resource_lookup, wc_mapping)
        conn.execute(
            "CREATE TEMP VIEW resource_src AS "
            "SELECT s.* FROM resource_all s "
            "INNER JOIN resource_dim d "
            "ON CAST(s.\"HISTORYID\" AS VARCHAR) = d.HISTORYID"
        )

        kpi = _query_kpi(conn)
        trend_items = _query_trend(conn, granularity=granularity)
        heatmap_items = _query_heatmap(conn, granularity=granularity)
        comparison_items = _query_workcenter_comparison(conn)
        detail = _query_detail(conn)

        latency_s = round(time.time() - started_at, 3)
        logger.info(
            "try_compute_query_from_canonical_spool: hit "
            "(canonical_query_id=%s latency_s=%.3f)",
            canonical_query_id, latency_s,
        )
        result = {
            "query_id": canonical_query_id,
            "summary": {
                "kpi": kpi,
                "trend": trend_items,
                "heatmap": heatmap_items,
                "workcenter_comparison": comparison_items,
            },
            "detail": detail,
        }
        return result, {"canonical_spool_latency_s": latency_s}

    except Exception as exc:
        logger.warning(
            "try_compute_query_from_canonical_spool failed "
            "(canonical_query_id=%s): %s",
            canonical_query_id, exc,
        )
        return None, {"canonical_fallback_reason": SQL_FALLBACK_RUNTIME_ERROR}
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
