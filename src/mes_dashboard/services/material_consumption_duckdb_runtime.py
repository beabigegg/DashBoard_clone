# -*- coding: utf-8 -*-
"""DuckDB-backed runtime for material consumption spool files.

Provides:
- Summary regroup by granularity (week/month/quarter) from summary spool.
- Summary KPI aggregation from spool.
- Summary type_breakdown aggregation.
- Detail pagination from detail spool via DuckDB.
- Chunked CSV export from detail spool without full memory load.

All operations read from Parquet spool files directly; no Oracle re-query.
Granularity bucket expressions implement MC-01 from business-rules.md.
"""

from __future__ import annotations

import csv
import io
import logging
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

from mes_dashboard.core.query_spool_store import get_spool_file_path

logger = logging.getLogger("mes_dashboard.material_consumption_duckdb_runtime")

_SUMMARY_SPOOL_NAMESPACE = "material_consumption_summary"
_DETAIL_SPOOL_NAMESPACE = "material_consumption_detail"

# CSV export columns for detail spool (must match parquet column names — all uppercase from Oracle)
_EXPORT_COLS = [
    "CONTAINERID", "CONTAINERNAME", "PJ_WORKORDER", "WORKCENTERNAME",
    "MATERIALPARTNAME", "MATERIALLOTNAME", "VENDORLOTNUMBER",
    "QTYREQUIRED", "QTYCONSUMED", "EQUIPMENTNAME", "TXNDATE",
    "PRIMARY_CATEGORY", "SECONDARY_CATEGORY", "PJ_TYPE", "PRODUCTLINENAME",
]
_EXPORT_HEADERS = {
    "CONTAINERID": "容器ID",
    "CONTAINERNAME": "LOT ID",
    "PJ_WORKORDER": "工單",
    "WORKCENTERNAME": "站點",
    "MATERIALPARTNAME": "料號",
    "MATERIALLOTNAME": "物料批號",
    "VENDORLOTNUMBER": "供應商批號",
    "QTYREQUIRED": "應領量",
    "QTYCONSUMED": "實際消耗",
    "EQUIPMENTNAME": "機台",
    "TXNDATE": "交易日期",
    "PRIMARY_CATEGORY": "主分類",
    "SECONDARY_CATEGORY": "副分類",
    "PJ_TYPE": "產品類型",
    "PRODUCTLINENAME": "PRODUCTLINENAME",
}

# Column rename map: Oracle uppercase → frontend snake_case API keys
_DETAIL_COL_RENAME = {
    "MATERIALPARTNAME": "material_part",
    "QTYREQUIRED": "qty_required",
    "QTYCONSUMED": "qty_consumed",
    "TXNDATE": "txn_date",
}


def _normalize_detail_df(df: Any) -> Any:
    """Rename and lowercase detail spool columns to match the frontend API contract."""
    df.columns = [_DETAIL_COL_RENAME.get(c, c.lower()) for c in df.columns]
    # Trim Oracle CHAR-padded PRODUCTLINENAME values (AC-6)
    if "productlinename" in df.columns:
        df["productlinename"] = (
            df["productlinename"]
            .apply(lambda v: v.strip() if isinstance(v, str) else v)
        )
    return df


# ---------------------------------------------------------------------------
# Granularity bucket expression (MC-01)
# ---------------------------------------------------------------------------


def _granularity_bucket_expr(granularity: str, col: str = "txn_date") -> str:
    """DuckDB SQL expression for date bucketing by granularity (MC-01).

    day:     YYYY-MM-DD string (explicit)
    week:    ISO week start date as string (date_trunc)
    month:   YYYY-MM string
    quarter: YYYY-QN string
    """
    qcol = f'CAST("{col}" AS DATE)'
    if granularity == "day":
        return f"strftime({qcol}, '%Y-%m-%d')"
    if granularity == "week":
        return f"strftime(date_trunc('week', {qcol}), '%Y-%m-%d')"
    if granularity == "month":
        return f"strftime({qcol}, '%Y-%m')"
    if granularity == "quarter":
        # year + '-Q' + quarter number
        return (
            f"CAST(YEAR({qcol}) AS VARCHAR) || '-Q' || "
            f"CAST(QUARTER({qcol}) AS VARCHAR)"
        )
    # default: day fallback
    return f"strftime({qcol}, '%Y-%m-%d')"


def _sql_str_literal(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _type_where(types: Optional[List[str]]) -> str:
    """Build a DuckDB WHERE clause for pj_type filtering.

    Returns an empty string when types is None or empty (no filter).
    """
    if not types:
        return ""
    literals = ", ".join(_sql_str_literal(t) for t in types)
    return f'WHERE "pj_type" IN ({literals})'


def _fetch_dict_rows(conn: Any, sql: str) -> List[Dict[str, Any]]:
    cursor = conn.execute(sql)
    # DuckDB returns cursor.description column names from parquet in UPPERCASE (e.g. MATERIAL_PART).
    # Normalize to lowercase so r.get("material_part") / r.get("pj_type") resolve correctly.
    columns = [desc[0].lower() for desc in (cursor.description or [])]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


# ---------------------------------------------------------------------------
# Summary spool operations
# ---------------------------------------------------------------------------


def regroup_summary(
    spool_path: str,
    *,
    granularity: str = "month",
    types: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Regroup summary spool by granularity and return {kpi, trend, type_breakdown}.

    No Oracle re-query — reads directly from the Parquet spool file.
    Implements MC-01 granularity bucket expressions.
    Optionally filter rows by pj_type via the `types` parameter.
    """
    try:
        from mes_dashboard.core.duckdb_runtime import create_heavy_query_connection

        conn = create_heavy_query_connection()
        path_lit = _sql_str_literal(spool_path)
        conn.execute(
            f"CREATE OR REPLACE TEMP VIEW summary_src AS "
            f"SELECT * FROM read_parquet({path_lit})"
        )

        kpi = _query_kpi(conn, types=types)
        trend = _query_trend(conn, granularity=granularity, types=types)
        type_breakdown = _query_type_breakdown(conn, granularity=granularity, types=types)
        conn.close()

        return {
            "kpi": kpi,
            "trend": trend,
            "type_breakdown": type_breakdown,
        }
    except Exception as exc:
        logger.warning("regroup_summary failed (path=%s, gran=%s): %s", spool_path, granularity, exc)
        raise


def _query_kpi(conn: Any, *, types: Optional[List[str]] = None) -> Dict[str, Any]:
    """Aggregate KPI totals from summary_src."""
    where = _type_where(types)
    sql = f"""
        SELECT
            COALESCE(SUM("total_consumed"), 0.0) AS total_consumed,
            COALESCE(SUM("total_required"), 0.0) AS total_required,
            COALESCE(SUM("lot_count"), 0)         AS lot_count,
            COALESCE(SUM("workorder_count"), 0)   AS workorder_count
        FROM summary_src
        {where}
    """
    rows = _fetch_dict_rows(conn, sql)
    if not rows:
        return _empty_kpi()
    r = rows[0]
    consumed = float(r.get("total_consumed") or 0.0)
    required = float(r.get("total_required") or 0.0)
    efficiency_pct = round(consumed / required * 100, 1) if required > 0 else 0.0
    return {
        "total_consumed": round(consumed, 2),
        "total_required": round(required, 2),
        "efficiency_pct": efficiency_pct,
        "lot_count": int(r.get("lot_count") or 0),
        "workorder_count": int(r.get("workorder_count") or 0),
    }


def _empty_kpi() -> Dict[str, Any]:
    return {
        "total_consumed": 0.0,
        "total_required": 0.0,
        "efficiency_pct": 0.0,
        "lot_count": 0,
        "workorder_count": 0,
    }


def _query_trend(
    conn: Any,
    *,
    granularity: str,
    types: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Trend: GROUP BY period + material_part."""
    bucket_expr = _granularity_bucket_expr(granularity)
    # Combine txn_date IS NOT NULL guard with optional pj_type filter
    base_where = '"txn_date" IS NOT NULL AND "material_part" IS NOT NULL'
    type_clause = _type_where(types)
    if type_clause:
        # _type_where returns "WHERE ..." — strip to just the condition
        type_cond = type_clause[len("WHERE "):].strip()
        where = f"WHERE {base_where} AND {type_cond}"
    else:
        where = f"WHERE {base_where}"
    sql = f"""
        SELECT
            {bucket_expr} AS period,
            "material_part",
            SUM("total_consumed")   AS total_consumed,
            SUM("total_required")   AS total_required,
            SUM("lot_count")        AS lot_count,
            SUM("workorder_count")  AS workorder_count
        FROM summary_src
        {where}
        GROUP BY {bucket_expr}, "material_part"
        ORDER BY period, "material_part"
    """
    rows = _fetch_dict_rows(conn, sql)
    return [
        {
            "period": r.get("period"),
            "material_part": r.get("material_part"),
            "total_consumed": float(r.get("total_consumed") or 0.0),
            "total_required": float(r.get("total_required") or 0.0),
            "lot_count": int(r.get("lot_count") or 0),
            "workorder_count": int(r.get("workorder_count") or 0),
        }
        for r in rows
    ]


def _query_type_breakdown(
    conn: Any,
    *,
    granularity: str,
    types: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Type breakdown: GROUP BY period + material_part + pj_type."""
    bucket_expr = _granularity_bucket_expr(granularity)
    base_where = '"txn_date" IS NOT NULL AND "material_part" IS NOT NULL'
    type_clause = _type_where(types)
    if type_clause:
        type_cond = type_clause[len("WHERE "):].strip()
        where = f"WHERE {base_where} AND {type_cond}"
    else:
        where = f"WHERE {base_where}"
    sql = f"""
        SELECT
            {bucket_expr} AS period,
            "material_part",
            "pj_type",
            SUM("total_consumed")   AS total_consumed,
            SUM("total_required")   AS total_required,
            SUM("lot_count")        AS lot_count
        FROM summary_src
        {where}
        GROUP BY {bucket_expr}, "material_part", "pj_type"
        ORDER BY period, "material_part", "pj_type"
    """
    rows = _fetch_dict_rows(conn, sql)
    return [
        {
            "period": r.get("period"),
            "material_part": r.get("material_part"),
            "pj_type": r.get("pj_type"),
            "total_consumed": float(r.get("total_consumed") or 0.0),
            "total_required": float(r.get("total_required") or 0.0),
            "lot_count": int(r.get("lot_count") or 0),
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Detail spool operations
# ---------------------------------------------------------------------------


class MaterialConsumptionDetailRuntime:
    """DuckDB-backed pagination and CSV export for material consumption detail spool."""

    def __init__(self, query_id: str) -> None:
        self.query_id = query_id
        self._spool_path: Optional[str] = None
        self._resolved = False

    def _resolve_path(self) -> None:
        if self._resolved:
            return
        self._spool_path = get_spool_file_path(_DETAIL_SPOOL_NAMESPACE, self.query_id)
        self._resolved = True

    def is_available(self) -> bool:
        self._resolve_path()
        return bool(self._spool_path and Path(self._spool_path).exists())

    def get_page(
        self,
        page: int = 1,
        per_page: int = 20,
        *,
        pj_types: Optional[List[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Return paginated rows from detail spool via DuckDB.

        Applies optional pj_types filter inline at DuckDB level.
        Returns None if spool is unavailable.
        """
        self._resolve_path()
        if not self._spool_path:
            return None

        safe_page = max(1, int(page))
        safe_per_page = max(1, min(int(per_page), 500))

        try:
            from mes_dashboard.core.duckdb_runtime import create_heavy_query_connection

            conn = create_heavy_query_connection()
            path_lit = _sql_str_literal(self._spool_path)
            conn.execute(
                f"CREATE TEMP VIEW detail_src AS SELECT * FROM read_parquet({path_lit})"
            )

            # Optional pj_types filter
            where_clause = ""
            if pj_types:
                pj_list = ", ".join(_sql_str_literal(p) for p in pj_types)
                where_clause = f"WHERE \"pj_type\" IN ({pj_list})"

            total_row = conn.execute(f"SELECT COUNT(*) FROM detail_src {where_clause}").fetchone()
            total = int(total_row[0]) if total_row else 0
            total_pages = max(1, (total + safe_per_page - 1) // safe_per_page)
            safe_page = min(safe_page, total_pages)
            offset = (safe_page - 1) * safe_per_page

            rows_df = conn.execute(
                f"SELECT * FROM detail_src {where_clause} "
                f"LIMIT {safe_per_page} OFFSET {offset}"
            ).df()
            conn.close()

            rows_df = _normalize_detail_df(rows_df)
            rows_df = rows_df.astype(object).where(rows_df.notna(), None)
            return {
                "rows": rows_df.to_dict("records"),
                "pagination": {
                    "page": safe_page,
                    "per_page": safe_per_page,
                    "total_rows": total,
                    "total_pages": total_pages,
                },
            }
        except Exception as exc:
            logger.warning(
                "MaterialConsumptionDetailRuntime.get_page failed (query_id=%s): %s",
                self.query_id, exc,
            )
            return None

    def export_csv(self, chunk_size: int = 5000) -> Generator[bytes, None, None]:
        """Stream CSV rows from detail spool via DuckDB in chunks.

        Yields UTF-8-sig encoded bytes. First chunk is the header row.
        Subsequent chunks are row data (UTF-8). No full DataFrame load.
        """
        self._resolve_path()
        if not self._spool_path:
            return

        try:
            from mes_dashboard.core.duckdb_runtime import create_heavy_query_connection

            conn = create_heavy_query_connection()
            path_lit = _sql_str_literal(self._spool_path)
            conn.execute(
                f"CREATE TEMP VIEW detail_src AS SELECT * FROM read_parquet({path_lit})"
            )

            available = {r[0] for r in conn.execute("DESCRIBE detail_src").fetchall()}
            cols = [c for c in _EXPORT_COLS if c in available]
            col_select = ", ".join(f'"{c}"' for c in cols)
            headers = [_EXPORT_HEADERS.get(c, c) for c in cols]

            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow(headers)
            yield buf.getvalue().encode("utf-8-sig")

            offset = 0
            while True:
                rows = conn.execute(
                    f"SELECT {col_select} FROM detail_src LIMIT {chunk_size} OFFSET {offset}"
                ).fetchall()
                if not rows:
                    break
                buf = io.StringIO()
                writer = csv.writer(buf)
                writer.writerows(rows)
                yield buf.getvalue().encode("utf-8")
                offset += chunk_size

            conn.close()
        except Exception as exc:
            logger.warning(
                "MaterialConsumptionDetailRuntime.export_csv failed (query_id=%s): %s",
                self.query_id, exc,
            )
