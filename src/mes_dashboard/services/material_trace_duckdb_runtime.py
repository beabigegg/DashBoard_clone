# -*- coding: utf-8 -*-
"""DuckDB-backed runtime for material trace spool files.

Reads the parquet spool produced by execute_to_spool() and provides
pagination and CSV export without loading the full DataFrame into memory.
"""

from __future__ import annotations

import csv
import io
import logging
from pathlib import Path
from typing import Any, Dict, Generator, Optional

logger = logging.getLogger("mes_dashboard.material_trace_duckdb_runtime")

_SPOOL_NAMESPACE = "material_trace"

# Columns to include in CSV export (same order as legacy _CSV_COLUMNS)
_EXPORT_COLS = [
    "CONTAINERNAME", "PJ_WORKORDER", "WORKCENTER_GROUP", "WORKCENTERNAME",
    "MATERIALPARTNAME", "MATERIALLOTNAME", "VENDORLOTNUMBER",
    "QTYREQUIRED", "QTYCONSUMED", "EQUIPMENTNAME", "TXNDATE",
    "PRIMARY_CATEGORY", "SECONDARY_CATEGORY",
]
_EXPORT_HEADERS = {
    "CONTAINERNAME": "LOT ID",
    "PJ_WORKORDER": "工單",
    "WORKCENTER_GROUP": "站群組",
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
}


class MaterialTraceDuckdbRuntime:
    """DuckDB-backed pagination and export for material trace spool files."""

    def __init__(self, query_hash: str) -> None:
        self.query_hash = query_hash
        self._spool_path: Optional[str] = None
        self._resolved = False

    def _resolve_path(self) -> None:
        if self._resolved:
            return
        from mes_dashboard.core.query_spool_store import get_spool_file_path
        self._spool_path = get_spool_file_path(_SPOOL_NAMESPACE, self.query_hash)
        self._resolved = True

    def is_available(self) -> bool:
        """Return True if the spool parquet file exists on disk."""
        self._resolve_path()
        available = bool(self._spool_path and Path(self._spool_path).exists())
        from mes_dashboard.core.heavy_query_telemetry import record_spool_hit, record_spool_miss
        if available:
            record_spool_hit("material_trace", self.query_hash)
        else:
            record_spool_miss("material_trace", self.query_hash)
        return available

    def get_page(
        self,
        page: int = 1,
        per_page: int = 50,
    ) -> Optional[Dict[str, Any]]:
        """Return paginated rows dict from spool via DuckDB.

        Returns None if spool is unavailable. Pagination dict uses the same
        shape as the legacy paginate helper: {rows, pagination: {page, per_page,
        total, total_pages}}.
        """
        self._resolve_path()
        if not self._spool_path:
            return None

        safe_page = max(1, int(page))
        safe_per_page = max(1, min(int(per_page), 500))
        offset = (safe_page - 1) * safe_per_page

        try:
            from mes_dashboard.core.duckdb_runtime import create_heavy_query_connection

            conn = create_heavy_query_connection()
            path_lit = "'" + self._spool_path.replace("'", "''") + "'"
            conn.execute(f"CREATE TEMP VIEW src AS SELECT * FROM read_parquet({path_lit})")

            total_row = conn.execute("SELECT COUNT(*) FROM src").fetchone()
            total = int(total_row[0]) if total_row else 0
            total_pages = max(1, (total + safe_per_page - 1) // safe_per_page)
            safe_page = min(safe_page, total_pages)
            offset = (safe_page - 1) * safe_per_page

            rows_df = conn.execute(
                f"SELECT * FROM src LIMIT {safe_per_page} OFFSET {offset}"
            ).df()
            conn.close()

            rows_df = rows_df.astype(object).where(rows_df.notna(), None)
            return {
                "rows": rows_df.to_dict("records"),
                "pagination": {
                    "page": safe_page,
                    "per_page": safe_per_page,
                    "total": total,
                    "total_pages": total_pages,
                },
                "query_hash": self.query_hash,
            }
        except Exception as exc:
            logger.warning(
                "MaterialTraceDuckdbRuntime.get_page failed (query_hash=%s): %s",
                self.query_hash, exc,
            )
            from mes_dashboard.core.heavy_query_telemetry import record_lifecycle_failure
            record_lifecycle_failure("material_trace", reason="runtime_error")
            return None

    def export_csv(self, chunk_size: int = 5000) -> Generator[bytes, None, None]:
        """Stream CSV rows from spool via DuckDB in chunks.

        Yields UTF-8-sig encoded bytes. First chunk is the header row.
        Columns follow _EXPORT_COLS order (only present columns included).
        """
        self._resolve_path()
        if not self._spool_path:
            return

        try:
            from mes_dashboard.core.duckdb_runtime import create_heavy_query_connection

            conn = create_heavy_query_connection()
            path_lit = "'" + self._spool_path.replace("'", "''") + "'"
            conn.execute(f"CREATE TEMP VIEW src AS SELECT * FROM read_parquet({path_lit})")

            # Determine which export columns are present
            available = {r[0] for r in conn.execute("DESCRIBE src").fetchall()}
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
                    f"SELECT {col_select} FROM src LIMIT {chunk_size} OFFSET {offset}"
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
                "MaterialTraceDuckdbRuntime.export_csv failed (query_hash=%s): %s",
                self.query_hash, exc,
            )
            from mes_dashboard.core.heavy_query_telemetry import record_lifecycle_failure
            record_lifecycle_failure("material_trace", reason="export_runtime_error")
