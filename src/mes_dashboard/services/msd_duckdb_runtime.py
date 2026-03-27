# -*- coding: utf-8 -*-
"""DuckDB runtime for MSD (mid-section defect) staged trace aggregation.

Reads stage spool parquet files produced by the RQ lineage/events pipeline
and computes KPIs, charts, daily-trend, and detail rows using DuckDB so that
no large pandas frames need to be assembled in the gunicorn worker.

Spool layout expected:
  {SPOOL_NAMESPACE}/{trace_query_id}_events.parquet
  {SPOOL_NAMESPACE}/{trace_query_id}_lineage.parquet   (optional, for attribution)

Usage::

    from mes_dashboard.services.msd_duckdb_runtime import MsdDuckdbRuntime

    rt = MsdDuckdbRuntime(trace_query_id="msd-abc12345")
    if rt.is_available():
        summary = rt.get_summary()
        detail = rt.get_detail(page=1, per_page=20, sort_by="defect_rate", order="desc")
        # streaming CSV:
        for chunk in rt.export_csv():
            yield chunk
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

logger = logging.getLogger("mes_dashboard.msd_duckdb_runtime")

SPOOL_NAMESPACE = "msd-events"
_STAGE_EVENTS = "events"
_STAGE_LINEAGE = "lineage"


class MsdDuckdbRuntime:
    """DuckDB-backed runtime for MSD aggregation over spool parquet files."""

    def __init__(self, trace_query_id: str) -> None:
        self.trace_query_id = trace_query_id
        self._events_path: Optional[str] = None
        self._lineage_path: Optional[str] = None
        self._resolved = False

    def _resolve_paths(self) -> None:
        if self._resolved:
            return
        from mes_dashboard.core.query_spool_store import (
            get_stage_spool_path,
            get_spool_file_path,
        )
        self._events_path = (
            get_stage_spool_path(SPOOL_NAMESPACE, self.trace_query_id, _STAGE_EVENTS)
            or get_spool_file_path(SPOOL_NAMESPACE, self.trace_query_id)
        )
        self._lineage_path = get_stage_spool_path(
            SPOOL_NAMESPACE, self.trace_query_id, _STAGE_LINEAGE
        )
        self._resolved = True

    def is_available(self) -> bool:
        """Return True if at least the events spool file is present."""
        self._resolve_paths()
        return bool(self._events_path and Path(self._events_path).exists())

    # ------------------------------------------------------------------
    # Summary / KPI
    # ------------------------------------------------------------------

    def get_summary(self) -> Optional[Dict[str, Any]]:
        """Compute summary KPIs and charts from spool via DuckDB."""
        self._resolve_paths()
        if not self._events_path:
            return None

        try:
            import duckdb

            conn = duckdb.connect(database=":memory:", read_only=False)
            conn.execute(f"CREATE VIEW events AS SELECT * FROM read_parquet('{self._events_path}')")

            kpi = self._compute_kpi(conn)
            charts = self._compute_charts(conn)
            daily_trend = self._compute_daily_trend(conn)

            if self._lineage_path and Path(self._lineage_path).exists():
                conn.execute(
                    f"CREATE VIEW lineage AS SELECT * FROM read_parquet('{self._lineage_path}')"
                )
                attribution = self._compute_attribution(conn)
            else:
                attribution = []

            conn.close()
            return {
                "kpi": kpi,
                "charts": charts,
                "daily_trend": daily_trend,
                "attribution": attribution,
                "trace_query_id": self.trace_query_id,
            }
        except Exception as exc:
            logger.warning("MsdDuckdbRuntime.get_summary failed (trace_query_id=%s): %s", self.trace_query_id, exc)
            return None

    def _compute_kpi(self, conn) -> Dict[str, Any]:
        """Compute total defect count, lot count, and defect rate from events view."""
        try:
            row = conn.execute(
                """
                SELECT
                    COUNT(DISTINCT CONTAINER_ID) AS lot_count,
                    SUM(DEFECT_QTY) AS defect_qty,
                    SUM(INPUT_QTY) AS input_qty
                FROM events
                """
            ).fetchone()
            if row:
                lot_count, defect_qty, input_qty = row
                defect_rate = (
                    round(float(defect_qty) / float(input_qty) * 100, 2)
                    if input_qty and input_qty > 0
                    else 0.0
                )
                return {
                    "lot_count": int(lot_count or 0),
                    "defect_qty": int(defect_qty or 0),
                    "input_qty": int(input_qty or 0),
                    "defect_rate": defect_rate,
                }
        except Exception as exc:
            logger.debug("_compute_kpi failed: %s", exc)
        return {"lot_count": 0, "defect_qty": 0, "input_qty": 0, "defect_rate": 0.0}

    def _compute_charts(self, conn) -> List[Dict[str, Any]]:
        """Compute top-N station defect rate chart from events view."""
        try:
            rows = conn.execute(
                """
                SELECT
                    STATION_NAME,
                    SUM(DEFECT_QTY) AS defect_qty,
                    SUM(INPUT_QTY) AS input_qty
                FROM events
                GROUP BY STATION_NAME
                ORDER BY defect_qty DESC
                LIMIT 20
                """
            ).fetchall()
            return [
                {
                    "station": r[0],
                    "defect_qty": int(r[1] or 0),
                    "input_qty": int(r[2] or 0),
                    "defect_rate": round(float(r[1] or 0) / float(r[2]) * 100, 2) if r[2] else 0.0,
                }
                for r in rows
            ]
        except Exception as exc:
            logger.debug("_compute_charts failed: %s", exc)
            return []

    def _compute_daily_trend(self, conn) -> List[Dict[str, Any]]:
        """Compute daily defect trend from events view."""
        try:
            rows = conn.execute(
                """
                SELECT
                    CAST(TXNDATE AS DATE) AS txn_day,
                    SUM(DEFECT_QTY) AS defect_qty,
                    SUM(INPUT_QTY) AS input_qty
                FROM events
                GROUP BY CAST(TXNDATE AS DATE)
                ORDER BY txn_day
                """
            ).fetchall()
            return [
                {
                    "date": str(r[0]),
                    "defect_qty": int(r[1] or 0),
                    "input_qty": int(r[2] or 0),
                }
                for r in rows
            ]
        except Exception as exc:
            logger.debug("_compute_daily_trend failed: %s", exc)
            return []

    def _compute_attribution(self, conn) -> List[Dict[str, Any]]:
        """Compute upstream attribution by joining events + lineage views."""
        try:
            rows = conn.execute(
                """
                SELECT
                    l.ANCESTOR_NAME,
                    COUNT(DISTINCT e.CONTAINER_ID) AS lot_count,
                    SUM(e.DEFECT_QTY) AS defect_qty
                FROM events e
                JOIN lineage l ON e.CONTAINER_ID = l.DESCENDANT_ID
                GROUP BY l.ANCESTOR_NAME
                ORDER BY defect_qty DESC
                LIMIT 20
                """
            ).fetchall()
            return [
                {
                    "ancestor": r[0],
                    "lot_count": int(r[1] or 0),
                    "defect_qty": int(r[2] or 0),
                }
                for r in rows
            ]
        except Exception as exc:
            logger.debug("_compute_attribution failed (may be schema difference): %s", exc)
            return []

    # ------------------------------------------------------------------
    # Detail (paginated)
    # ------------------------------------------------------------------

    def get_detail(
        self,
        page: int = 1,
        per_page: int = 20,
        sort_by: str = "defect_rate",
        order: str = "desc",
    ) -> Optional[Dict[str, Any]]:
        """Return paginated detail rows from events spool via DuckDB."""
        self._resolve_paths()
        if not self._events_path:
            return None

        safe_order = "DESC" if order.lower() == "desc" else "ASC"
        # defect_rate is a derived column (computed via CTE); others are raw columns.
        _derived = {"defect_rate"}
        _raw_allowed = {"defect_qty", "input_qty", "station_name", "txndate"}
        sort_lower = sort_by.lower()
        if sort_lower not in _derived and sort_lower not in _raw_allowed:
            sort_lower = "defect_qty"
        offset = max(0, (page - 1) * per_page)

        try:
            import duckdb

            conn = duckdb.connect(database=":memory:", read_only=False)
            conn.execute(f"CREATE VIEW events AS SELECT * FROM read_parquet('{self._events_path}')")

            total_row = conn.execute("SELECT COUNT(*) FROM events").fetchone()
            total = int(total_row[0]) if total_row else 0

            rows = conn.execute(
                f"""
                WITH with_rate AS (
                    SELECT *,
                        CASE WHEN INPUT_QTY > 0
                             THEN DEFECT_QTY * 1.0 / INPUT_QTY * 100
                             ELSE 0.0 END AS defect_rate
                    FROM events
                )
                SELECT * FROM with_rate
                ORDER BY {sort_lower} {safe_order}
                LIMIT {per_page} OFFSET {offset}
                """
            ).df()
            conn.close()

            return {
                "items": rows.to_dict(orient="records"),
                "pagination": {
                    "page": page,
                    "per_page": per_page,
                    "total": total,
                    "total_pages": max(1, (total + per_page - 1) // per_page),
                },
                "trace_query_id": self.trace_query_id,
            }
        except Exception as exc:
            logger.warning("MsdDuckdbRuntime.get_detail failed: %s", exc)
            return None

    def get_all_detail(
        self,
        sort_by: str = "defect_rate",
        order: str = "desc",
    ) -> Optional[List[Dict[str, Any]]]:
        """Return all detail rows from events spool via DuckDB."""
        self._resolve_paths()
        if not self._events_path:
            return None

        safe_order = "DESC" if order.lower() == "desc" else "ASC"
        derived = {"defect_rate"}
        raw_allowed = {"defect_qty", "input_qty", "station_name", "txndate"}
        sort_lower = sort_by.lower()
        if sort_lower not in derived and sort_lower not in raw_allowed:
            sort_lower = "defect_qty"

        try:
            import duckdb

            conn = duckdb.connect(database=":memory:", read_only=False)
            conn.execute(f"CREATE VIEW events AS SELECT * FROM read_parquet('{self._events_path}')")
            rows = conn.execute(
                f"""
                WITH with_rate AS (
                    SELECT *,
                        CASE WHEN INPUT_QTY > 0
                             THEN DEFECT_QTY * 1.0 / INPUT_QTY * 100
                             ELSE 0.0 END AS defect_rate
                    FROM events
                )
                SELECT * FROM with_rate
                ORDER BY {sort_lower} {safe_order}
                """
            ).df()
            conn.close()
            return rows.to_dict(orient="records")
        except Exception as exc:
            logger.warning("MsdDuckdbRuntime.get_all_detail failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Export (streaming CSV)
    # ------------------------------------------------------------------

    def export_csv(self, chunk_size: int = 5000) -> Generator[bytes, None, None]:
        """Stream CSV rows from events spool via DuckDB in chunks."""
        self._resolve_paths()
        if not self._events_path:
            return

        try:
            import duckdb
            import io
            import csv

            conn = duckdb.connect(database=":memory:", read_only=False)
            conn.execute(f"CREATE VIEW events AS SELECT * FROM read_parquet('{self._events_path}')")

            # Get column names
            cols_result = conn.execute("DESCRIBE events").fetchall()
            columns = [r[0] for r in cols_result]

            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow(columns)
            yield buf.getvalue().encode("utf-8-sig")

            offset = 0
            while True:
                rows = conn.execute(
                    f"SELECT * FROM events LIMIT {chunk_size} OFFSET {offset}"
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
            logger.warning("MsdDuckdbRuntime.export_csv failed: %s", exc)
