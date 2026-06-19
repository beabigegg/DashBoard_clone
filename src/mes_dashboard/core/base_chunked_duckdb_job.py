# -*- coding: utf-8 -*-
"""BaseChunkedDuckDBJob — template-method base class for chunked Oracle→DuckDB jobs.

Implements the canonical pipeline:
    Oracle parallel chunk → pyarrow RecordBatch → DuckDB (on-disk spill)
    → post_aggregate → canonical parquet spool

Design decisions:
    D1 — ChunkStrategy enum {TIME, ID_LIST, ROW_COUNT, SINGLE}
    D2 — Two reduction paths via requires_cross_chunk_reduction:
         False → each chunk writes its own parquet (multi-parquet append)
         True  → all chunks INSERT INTO a shared job-temp DuckDB, then
                 post_aggregate GROUP BY/JOIN → canonical parquet
    D7 — Job-temp DuckDB lifecycle: create at job start, delete in finally.

Progress brackets (Type B coarse, per cache-spool-patterns.md):
    5 → pre_query done
    15 → all chunks fetched / first reduction pass done
    90 → post_aggregate done
    100 → spool registered and job complete

No domain logic lives here.  Subclasses implement pre_query, build_chunk_sql,
and post_aggregate; chunk_to_duckdb and progress_report have sensible defaults.
"""
from __future__ import annotations

import logging
import os
import shutil
import threading
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from enum import Enum
from pathlib import Path
from typing import Iterator

import pyarrow as pa
import pyarrow.parquet as pq

from mes_dashboard.core.oracle_arrow_reader import OracleArrowReader

logger = logging.getLogger("mes_dashboard.base_chunked_duckdb_job")

# ---------------------------------------------------------------------------
# Job-temp DuckDB directory
# DUCKDB_JOB_DIR defaults to {QUERY_SPOOL_DIR}/../duckdb_jobs (D4).
# QUERY_SPOOL_DIR defaults to tmp/query_spool (from query_spool_store.py).
# ---------------------------------------------------------------------------
_QUERY_SPOOL_DIR_DEFAULT = "tmp/query_spool"
_DUCKDB_JOB_DIR_DEFAULT = str(
    Path(os.environ.get("QUERY_SPOOL_DIR", _QUERY_SPOOL_DIR_DEFAULT)).parent
    / "duckdb_jobs"
)
DUCKDB_JOB_DIR: str = os.environ.get("DUCKDB_JOB_DIR", _DUCKDB_JOB_DIR_DEFAULT)


class ChunkStrategy(Enum):
    """Design-time chunking taxonomy (ADR-0003).

    TIME      — decompose by date/time range (row-level, parallelisable).
    ID_LIST   — decompose by ID batches (Oracle IN-list ≤ 1000, parallelisable).
    ROW_COUNT — decompose by row-count window via ROW_NUMBER() (parallelisable).
    SINGLE    — no chunking; fetch entire result set as one query (used when
                cross-row aggregation cannot be split safely, e.g. downtime).
    """

    TIME = "time"
    ID_LIST = "id_list"
    ROW_COUNT = "row_count"
    SINGLE = "single"


class BaseChunkedDuckDBJob(ABC):
    """Abstract base for all chunked Oracle→DuckDB→parquet spool jobs.

    Subclasses MUST set class attributes:
        namespace (str)      — spool namespace, e.g. "eap_alarm"
        chunk_strategy (ChunkStrategy)

    Subclasses MUST implement abstract methods:
        pre_query(self) -> None
        build_chunk_sql(self, chunk_params: dict) -> tuple[str, dict]
        post_aggregate(self, job_duckdb_path: str | None) -> str

    Subclasses MAY override:
        chunk_to_duckdb(self, batch, job_duckdb_path)
        progress_report(self, pct)
    """

    # Subclass must set:
    namespace: str = ""
    chunk_strategy: ChunkStrategy = ChunkStrategy.SINGLE

    # Subclass may override:
    requires_cross_chunk_reduction: bool = False
    max_parallel: int = 3

    # Class-level writer lock: serializes DuckDB writes across threads.
    _writer_lock: threading.Lock = threading.Lock()

    def __init__(self, job_id: str) -> None:
        self.job_id = job_id
        self._chunks: list[dict] = []
        self._reader = OracleArrowReader()

    # ------------------------------------------------------------------
    # Abstract hooks (subclass MUST implement)
    # ------------------------------------------------------------------

    @abstractmethod
    def pre_query(self) -> None:
        """Parse filters, compute chunk boundaries, resolve spool key, etc.

        Called before any Oracle access.  Must populate self._chunks with
        a list of chunk_params dicts suitable for build_chunk_sql().
        """
        ...

    @abstractmethod
    def build_chunk_sql(self, chunk_params: dict) -> tuple[str, dict]:
        """Return (sql_string, bind_params) for a single chunk.

        Args:
            chunk_params: One element from the list populated by pre_query().

        Returns:
            (sql, params) — passed directly to OracleArrowReader.chunk_iter().
        """
        ...

    @abstractmethod
    def post_aggregate(self, job_duckdb_path: str | None) -> str:
        """Run final aggregation and write the canonical parquet spool.

        For requires_cross_chunk_reduction=True:
            job_duckdb_path is the path to the job-temp DuckDB containing
            the "raw" table.  Execute GROUP BY/JOIN SQL and COPY TO spool.

        For requires_cross_chunk_reduction=False:
            job_duckdb_path is None.  The multi-parquet files are already
            written; merge or register as appropriate.

        Returns:
            Absolute path to the canonical parquet spool file.
        """
        ...

    # ------------------------------------------------------------------
    # Default hooks (subclass MAY override)
    # ------------------------------------------------------------------

    def chunk_to_duckdb(
        self, batch: pa.RecordBatch, job_duckdb_path: str
    ) -> None:
        """Insert an Arrow RecordBatch into the job-temp DuckDB raw table.

        Serialized under _writer_lock (DuckDB single-writer constraint).
        """
        import duckdb

        with self._writer_lock:
            conn = duckdb.connect(job_duckdb_path)
            try:
                # Register the batch as an in-process Arrow object, then INSERT.
                conn.register("_chunk_batch", batch)
                # CREATE TABLE IF NOT EXISTS with schema inferred from first batch.
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS raw AS SELECT * FROM _chunk_batch WHERE 1=0"
                )
                conn.execute("INSERT INTO raw SELECT * FROM _chunk_batch")
                conn.unregister("_chunk_batch")
            finally:
                conn.close()

    def progress_report(self, pct: int) -> None:
        """Report job progress percentage (0–100).

        Default implementation logs at DEBUG.  Subclasses should override to
        update RQ job metadata or a Redis progress key.
        """
        logger.debug(
            "job=%s namespace=%s progress=%d%%",
            self.job_id,
            self.namespace,
            pct,
        )

    # ------------------------------------------------------------------
    # Template method (do NOT override in subclasses)
    # ------------------------------------------------------------------

    def run(self) -> str:
        """Execute the full pipeline; return canonical spool path.

        Progress brackets: 5 → 15 → 90 → 100
        Job-temp DuckDB is always deleted in the finally block (D7).
        """
        job_duckdb_path: str | None = None

        try:
            # Step 1 — pre_query + bracket 5
            self.pre_query()
            self.progress_report(5)

            chunks = list(self._chunks)  # snapshot after pre_query

            # Step 2 — Decide reduction path
            if self.requires_cross_chunk_reduction:
                job_duckdb_path = self._make_job_duckdb_path()
                self._fan_out_reduction(chunks, job_duckdb_path)
            else:
                self._fan_out_append(chunks)

            # Step 3 — bracket 15 (all chunks fetched)
            self.progress_report(15)

            # Step 4 — post_aggregate + bracket 90
            spool_path = self.post_aggregate(job_duckdb_path)
            self.progress_report(90)

            # Step 5 — bracket 100
            self.progress_report(100)

            return spool_path

        finally:
            # D7: delete job-temp DuckDB on completion or error
            if job_duckdb_path is not None:
                self._cleanup_job_duckdb(job_duckdb_path)
            # Append path: clean up per-chunk parquet dir
            if not self.requires_cross_chunk_reduction:
                self._cleanup_chunk_parquet_dir(self.job_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _make_job_duckdb_path(self) -> str:
        """Build the job-temp DuckDB path under DUCKDB_JOB_DIR."""
        base = Path(os.environ.get("DUCKDB_JOB_DIR", DUCKDB_JOB_DIR))
        ns_dir = base / self.namespace
        ns_dir.mkdir(parents=True, exist_ok=True)
        return str(ns_dir / f"{self.job_id}.duckdb")

    def _cleanup_job_duckdb(self, path: str) -> None:
        """Delete the job-temp DuckDB file if it exists."""
        try:
            p = Path(path)
            if p.exists():
                p.unlink()
                logger.debug("Deleted job-temp DuckDB: %s", path)
        except Exception as exc:
            logger.warning("Failed to delete job-temp DuckDB %s: %s", path, exc)

    def _make_chunk_parquet_dir(self, job_id: str) -> Path:
        """Return (and create) the per-job chunk parquet dir.

        Path: {DUCKDB_JOB_DIR}/{namespace}/{job_id}/
        Mirror of _make_job_duckdb_path style.
        """
        base = Path(os.environ.get("DUCKDB_JOB_DIR", DUCKDB_JOB_DIR))
        chunk_dir = base / self.namespace / job_id
        chunk_dir.mkdir(parents=True, exist_ok=True)
        return chunk_dir

    def _cleanup_chunk_parquet_dir(self, job_id: str) -> None:
        """Remove the per-job chunk parquet directory tree if it exists."""
        try:
            base = Path(os.environ.get("DUCKDB_JOB_DIR", DUCKDB_JOB_DIR))
            chunk_dir = base / self.namespace / job_id
            if chunk_dir.exists():
                shutil.rmtree(chunk_dir, ignore_errors=True)
                logger.debug("Deleted chunk parquet dir: %s", chunk_dir)
        except Exception as exc:
            logger.warning("Failed to delete chunk parquet dir for job %s: %s", job_id, exc)

    def _fetch_chunk(
        self, chunk_params: dict
    ) -> Iterator[pa.RecordBatch]:
        """Fetch one chunk from Oracle; yields RecordBatch objects."""
        sql, params = self.build_chunk_sql(chunk_params)
        yield from self._reader.chunk_iter(sql, params)

    def _fan_out_reduction(
        self, chunks: list[dict], job_duckdb_path: str
    ) -> None:
        """Fan-out: fetch chunks in parallel, INSERT into shared job-temp DuckDB."""
        effective = min(self.max_parallel, len(chunks)) if chunks else 1

        def _fetch_and_insert(chunk_params: dict) -> None:
            for batch in self._fetch_chunk(chunk_params):
                self.chunk_to_duckdb(batch, job_duckdb_path)

        if effective <= 1 or len(chunks) <= 1:
            for cp in chunks:
                _fetch_and_insert(cp)
        else:
            with ThreadPoolExecutor(max_workers=effective) as executor:
                futures = {executor.submit(_fetch_and_insert, cp): cp for cp in chunks}
                for fut in as_completed(futures):
                    exc = fut.exception()
                    if exc is not None:
                        raise exc

    def _fan_out_append(self, chunks: list[dict]) -> None:
        """Fan-out: fetch chunks in parallel; write each batch to per-chunk parquet files.

        For requires_cross_chunk_reduction=False domains. Each chunk thread writes its own
        {chunk_dir}/chunk-{chunk_idx:04d}-{batch_idx:04d}.parquet files (no _writer_lock
        needed — each thread writes to distinct paths).
        post_aggregate receives job_duckdb_path=None and globs chunk_dir for parquets.

        Empty-chunk / zero-batch case: chunk_dir is created and left present so
        post_aggregate can safely glob to an empty list without error.
        """
        chunk_dir = self._make_chunk_parquet_dir(self.job_id)
        effective = min(self.max_parallel, len(chunks)) if chunks else 1

        def _fetch_and_write(chunk_idx: int, chunk_params: dict) -> None:
            for batch_idx, batch in enumerate(self._fetch_chunk(chunk_params)):
                path = chunk_dir / f"chunk-{chunk_idx:04d}-{batch_idx:04d}.parquet"
                pq.write_table(pa.Table.from_batches([batch]), path)

        if effective <= 1 or len(chunks) <= 1:
            for chunk_idx, cp in enumerate(chunks):
                _fetch_and_write(chunk_idx, cp)
        else:
            with ThreadPoolExecutor(max_workers=effective) as executor:
                futures = {
                    executor.submit(_fetch_and_write, chunk_idx, cp): cp
                    for chunk_idx, cp in enumerate(chunks)
                }
                for fut in as_completed(futures):
                    exc = fut.exception()
                    if exc is not None:
                        raise exc
