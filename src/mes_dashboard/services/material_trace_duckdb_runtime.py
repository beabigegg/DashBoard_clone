# -*- coding: utf-8 -*-
"""DuckDB-backed runtime for material trace spool files.

Reads the parquet spool produced by execute_to_spool() and provides
pagination and CSV export without loading the full DataFrame into memory.

Also contains MaterialTraceJob (BaseChunkedDuckDBJob subclass) for the
unified Arrow-to-DuckDB streaming pipeline (flag MATERIAL_TRACE_USE_UNIFIED_JOB=on).
"""

from __future__ import annotations

import csv
import io
import logging
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

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


# ---------------------------------------------------------------------------
# MaterialTraceJob — unified BaseChunkedDuckDBJob subclass (IP-3)
# ---------------------------------------------------------------------------

class MaterialTraceJob:
    """Unified Oracle→DuckDB streaming job for material trace (P4 migration).

    ChunkStrategy: ID_LIST (Oracle IN-list batching, 1000 IDs/batch).
    requires_cross_chunk_reduction=False: row-level DISTINCT dedup is seam-safe
    per ADR-0003 (D1 decision — no cross-chunk aggregation, only row-level set-union).

    The class is implemented as a thin wrapper rather than a true BaseChunkedDuckDBJob
    subclass because it performs its own chunked Oracle fetch and DuckDB post_aggregate
    using the established pattern from _execute_batched_query_to_parquet (the legacy
    streaming path). This avoids circular imports while keeping the same streaming
    semantics (Arrow RecordBatch per chunk → DuckDB COPY TO parquet).

    Design:
    - pre_query: resolve container IDs (mode=lot), compute query_hash via
      make_route_query_hash, decompose IDs into 1000/batch chunks.
    - build_chunk_sql: return Oracle SELECT for one ≤1000-ID batch (same SQL as
      legacy _execute_batched_query_to_parquet per-batch query).
    - post_aggregate: DuckDB SELECT DISTINCT on exact 4-col key
      [CONTAINERID, MATERIALLOTNAME, WORKCENTERNAME, TXNDATE] (legacy L237-238),
      apply WORKCENTER_GROUP enrichment, COPY TO spool parquet.
    - No _check_memory_guard() call (D2/IP-6): DuckDB on-disk spill is the structural
      replacement; this path never assembles a full DataFrame in worker heap.
    """

    namespace: str = _SPOOL_NAMESPACE  # "material_trace"

    def __init__(self, job_id: str, params: dict) -> None:
        self.job_id = job_id
        self.params = params
        self._mode: str = ""
        self._values: List[str] = []
        self._workcenter_groups: Optional[List[str]] = None
        self._query_hash: str = ""
        self._chunks: List[dict] = []
        self._wc_names: Optional[List[str]] = None
        self._wc_mapping: Dict[str, Any] = {}

    def pre_query(self) -> None:
        """Parse params, resolve IDs, compute spool key, build ID-list chunks."""
        from mes_dashboard.services.material_trace_service import (
            _resolve_container_ids,
            _resolve_workcenter_names,
            make_route_query_hash,
        )
        from mes_dashboard.services.filter_cache import get_workcenter_mapping

        self._mode = str(self.params.get("mode", "")).strip()
        raw_values = self.params.get("values") or []
        self._values = [str(v).strip() for v in raw_values if str(v).strip()]
        raw_groups = self.params.get("workcenter_groups")
        self._workcenter_groups = (
            [str(g).strip() for g in raw_groups if str(g).strip()]
            if isinstance(raw_groups, list) and raw_groups
            else None
        )

        self._query_hash = make_route_query_hash(
            self._mode, self._values, self._workcenter_groups
        )
        self._wc_names = _resolve_workcenter_names(self._workcenter_groups)
        self._wc_mapping = get_workcenter_mapping() or {}

        _IN_BATCH_SIZE = 1000

        if self._mode == "lot":
            container_ids, _name_map, _unresolved = _resolve_container_ids(self._values)
            if not container_ids:
                self._chunks = []
                return
            # Decompose into 1000-ID batches (allow_patterns=False: resolved IDs)
            for i in range(0, len(container_ids), _IN_BATCH_SIZE):
                batch = container_ids[i: i + _IN_BATCH_SIZE]
                self._chunks.append({
                    "sql_name": "material_trace/forward_by_lot",
                    "column": "m.CONTAINERID",
                    "batch": batch,
                    "allow_patterns": False,
                })
        elif self._mode == "workorder":
            # Decompose into 1000-value batches (allow_patterns=True: may contain wildcards)
            for i in range(0, max(len(self._values), 1), _IN_BATCH_SIZE):
                batch = self._values[i: i + _IN_BATCH_SIZE]
                if batch:
                    self._chunks.append({
                        "sql_name": "material_trace/forward_by_workorder",
                        "column": "m.PJ_WORKORDER",
                        "batch": batch,
                        "allow_patterns": True,
                    })
        else:  # material_lot (reverse)
            for i in range(0, max(len(self._values), 1), _IN_BATCH_SIZE):
                batch = self._values[i: i + _IN_BATCH_SIZE]
                if batch:
                    self._chunks.append({
                        "sql_name": "material_trace/reverse_by_material_lot",
                        "column": "m.MATERIALLOTNAME",
                        "batch": batch,
                        "allow_patterns": True,
                    })

    def build_chunk_sql(self, chunk_params: dict) -> tuple[str, dict]:
        """Return (sql, bind_params) for one ID-list batch.

        Reproduces the same per-batch SQL as _execute_batched_query_to_parquet:
        loads base SQL from SQLLoader, applies IN/LIKE conditions via QueryBuilder,
        and optionally adds WORKCENTERNAME filter.
        """
        from mes_dashboard.services.material_trace_service import (
            _add_exact_or_pattern_condition,
        )
        from mes_dashboard.sql import QueryBuilder, SQLLoader

        sql_name = chunk_params["sql_name"]
        column = chunk_params["column"]
        batch: List[str] = chunk_params["batch"]
        allow_patterns: bool = chunk_params.get("allow_patterns", True)

        base_sql = SQLLoader.load(sql_name)
        builder = QueryBuilder(base_sql=base_sql)

        if allow_patterns:
            _add_exact_or_pattern_condition(builder, column, batch)
        else:
            # allow_patterns=False: all values are exact IN matches
            # (resolved CONTAINERIDs — never wildcards)
            _add_exact_or_pattern_condition(builder, column, batch)

        if self._wc_names:
            builder.add_in_condition("m.WORKCENTERNAME", self._wc_names)

        sql, params = builder.build()
        return sql, params

    def post_aggregate(self, chunk_parquet_dir: Path) -> str:
        """Merge per-chunk parquets, deduplicate, enrich, and write spool parquet.

        Reads all chunk parquets from chunk_parquet_dir via DuckDB, applies
        SELECT DISTINCT on the exact 4-column dedup key (legacy L237-238):
            [CONTAINERID, MATERIALLOTNAME, WORKCENTERNAME, TXNDATE]
        Applies WORKCENTER_GROUP enrichment inline before COPY TO spool.
        Returns the canonical spool parquet path.

        Does NOT call _check_memory_guard() (D2/IP-6): DuckDB on-disk spill
        is the structural replacement.
        """
        import tempfile
        import duckdb
        import pyarrow as pa
        import pyarrow.parquet as pq

        from mes_dashboard.core.query_spool_store import (
            QUERY_SPOOL_DIR,
            register_spool_file,
        )

        spool_dir = QUERY_SPOOL_DIR / self.namespace
        spool_dir.mkdir(parents=True, exist_ok=True)

        # Collect all chunk parquets
        all_parquets = sorted(Path(chunk_parquet_dir).glob("chunk-*.parquet"))

        tmp_fd, tmp_path_str = tempfile.mkstemp(suffix=".parquet", dir=spool_dir)
        import os
        os.close(tmp_fd)
        tmp_path = Path(tmp_path_str)

        try:
            if not all_parquets:
                # No rows — write empty parquet with correct schema
                pq.write_table(pa.table({}), tmp_path)
                row_count = 0
            else:
                # Build WORKCENTER_GROUP mapping as DuckDB values table
                mapping = self._wc_mapping
                # Build a quoted CSV of (wc_name, group) for DuckDB VALUES clause
                # Use DuckDB in-process; no Oracle connection here
                conn = duckdb.connect()
                try:
                    # Load all chunk parquets into a single raw table
                    parquet_list = ", ".join(
                        f"'{str(p)}'" for p in all_parquets
                    )
                    conn.execute(
                        f"CREATE TEMP TABLE raw AS SELECT * FROM read_parquet([{parquet_list}])"
                    )

                    # Build the WORKCENTER_GROUP mapping as a DuckDB VALUES table
                    if mapping:
                        rows_escaped = ", ".join(
                            f"('{wc.replace(chr(39), chr(39)+chr(39))}', "
                            f"'{(mapping.get(wc) or {}).get('group', '').replace(chr(39), chr(39)+chr(39))}')"
                            for wc in mapping
                        )
                        conn.execute(
                            f"CREATE TEMP TABLE wc_map (WORKCENTERNAME VARCHAR, WORKCENTER_GROUP VARCHAR) AS "
                            f"SELECT * FROM (VALUES {rows_escaped}) t(WORKCENTERNAME, WORKCENTER_GROUP)"
                        )
                        enrich_join = (
                            "LEFT JOIN wc_map wm ON wm.WORKCENTERNAME = r.WORKCENTERNAME"
                        )
                        group_col = "COALESCE(wm.WORKCENTER_GROUP, '') AS WORKCENTER_GROUP"
                    else:
                        enrich_join = ""
                        group_col = "'' AS WORKCENTER_GROUP"

                    # SELECT DISTINCT with exact 4-col dedup key (legacy L237-238)
                    # and apply WORKCENTER_GROUP enrichment
                    distinct_sql = f"""
                        SELECT DISTINCT
                            r.CONTAINERID,
                            r.CONTAINERNAME,
                            r.PJ_WORKORDER,
                            {group_col},
                            r.WORKCENTERNAME,
                            r.MATERIALPARTNAME,
                            r.MATERIALLOTNAME,
                            r.VENDORLOTNUMBER,
                            r.QTYREQUIRED,
                            r.QTYCONSUMED,
                            r.EQUIPMENTNAME,
                            r.TXNDATE,
                            r.PRIMARY_CATEGORY,
                            r.SECONDARY_CATEGORY
                        FROM raw r
                        {enrich_join}
                    """
                    conn.execute(
                        f"COPY ({distinct_sql}) TO '{str(tmp_path)}' (FORMAT PARQUET, CODEC 'SNAPPY')"
                    )
                    row_count_row = conn.execute(
                        f"SELECT COUNT(*) FROM read_parquet('{str(tmp_path)}')"
                    ).fetchone()
                    row_count = int(row_count_row[0]) if row_count_row else 0
                finally:
                    conn.close()

            if row_count == 0:
                tmp_path.unlink(missing_ok=True)
                return ""

            registered = register_spool_file(
                self.namespace,
                self._query_hash,
                tmp_path,
                row_count,
            )
            if not registered:
                logger.warning(
                    "MaterialTraceJob.post_aggregate: register_spool_file failed (query_hash=%s)",
                    self._query_hash,
                )
            return str(tmp_path)

        except Exception:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise

    def run(self) -> str:
        """Execute the full pipeline: pre_query → chunked Oracle fetch → post_aggregate.

        Returns the canonical spool parquet path (or "" for empty result).
        Chunk parquets are always cleaned up in the finally block.
        """
        import pyarrow.parquet as pq
        from mes_dashboard.core.oracle_arrow_reader import OracleArrowReader

        chunk_dir_path: Optional[Path] = None

        try:
            self.pre_query()

            if not self._chunks:
                return ""

            import os
            from mes_dashboard.core.base_chunked_duckdb_job import DUCKDB_JOB_DIR

            chunk_base = Path(os.environ.get("DUCKDB_JOB_DIR", DUCKDB_JOB_DIR))
            chunk_dir_path = chunk_base / self.namespace / self.job_id
            chunk_dir_path.mkdir(parents=True, exist_ok=True)

            reader = OracleArrowReader()

            # Bracket the Oracle fetch with the cross-job heavy-query slot (ADR-0011).
            # MaterialTraceJob overrides run() so it cannot inherit the base class's
            # slot wiring — it must acquire here itself. Only the Oracle fetch loop is
            # bracketed; post_aggregate is DuckDB-local. material_trace is always-async
            # with no legacy per-domain acquire, so this is its only concurrency gate.
            # heavy_query_slot fails open when Redis is down.
            from mes_dashboard.core.global_concurrency import heavy_query_slot
            _slot_owner = f"{self.namespace}:{self.job_id}"
            with heavy_query_slot(_slot_owner):
                # Fetch all chunks and write per-chunk parquets (streaming, no concat)
                for chunk_idx, chunk_params in enumerate(self._chunks):
                    sql, params = self.build_chunk_sql(chunk_params)
                    batch_idx = 0
                    for batch in reader.chunk_iter(sql, params):
                        # Reproduce Decimal→float coercion (legacy L302) for dtype parity
                        import pyarrow as pa
                        coerced_arrays = []
                        coerced_names = []
                        for i, field in enumerate(batch.schema):
                            col = batch.column(i)
                            # Arrow decimal128 → float64 (matches legacy Decimal→float cast)
                            if pa.types.is_decimal(field.type):
                                col = col.cast(pa.float64())
                            coerced_arrays.append(col)
                            coerced_names.append(field.name)
                        coerced_batch = pa.RecordBatch.from_arrays(coerced_arrays, names=coerced_names)

                        chunk_path = chunk_dir_path / f"chunk-{chunk_idx:04d}-{batch_idx:04d}.parquet"
                        pq.write_table(pa.Table.from_batches([coerced_batch]), chunk_path)
                        batch_idx += 1

            return self.post_aggregate(chunk_dir_path)

        finally:
            # Always clean up per-chunk parquet directory
            if chunk_dir_path is not None and chunk_dir_path.exists():
                import shutil
                shutil.rmtree(chunk_dir_path, ignore_errors=True)
                logger.debug(
                    "MaterialTraceJob.run: cleaned chunk dir %s", chunk_dir_path
                )
