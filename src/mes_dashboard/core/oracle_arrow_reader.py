# -*- coding: utf-8 -*-
"""Oracle → pyarrow RecordBatch streaming reader.

Provides a lazy per-worker session pool (ADR-0004 fork-safety) and a
``chunk_iter()`` generator that streams Oracle query results as Arrow
RecordBatch objects without touching pandas or loading the full result set
into Python heap.

Design decisions:
    D3 — Pool is created lazily post-fork; never at module import.
    D6 — One connection per chunk_iter() call; returned via finally:.
    No pandas in this module.

Usage::

    reader = OracleArrowReader()
    for batch in reader.chunk_iter(sql, params, chunk_size=10000):
        # batch is a pyarrow.RecordBatch
        ...
"""
from __future__ import annotations

import logging
import os
import re
from typing import TYPE_CHECKING, Any, Dict, Iterator

import pyarrow as pa

if TYPE_CHECKING:
    import oracledb

logger = logging.getLogger("mes_dashboard.oracle_arrow_reader")

# ---------------------------------------------------------------------------
# Oracle DATE column: pattern to detect midnight-UTC (no time component).
# We inspect H:M:S before converting to avoid ±8h TZ shift.
# Regex matches strings that end in " 00:00:00" (Oracle DATE default repr).
# ---------------------------------------------------------------------------
_DATE_MIDNIGHT_RE = re.compile(r"\s00:00:00$")


def _strip_char(value: Any) -> Any:
    """Strip padding from Oracle CHAR columns. No-op for non-str types."""
    if isinstance(value, str):
        return value.strip()
    return value


def _coerce_row(row: tuple, col_names: list[str]) -> dict:
    """Convert a raw Oracle row tuple to a dict, applying CHAR strip."""
    return {col_names[i]: _strip_char(val) for i, val in enumerate(row)}


class OracleArrowReader:
    """Oracle → pyarrow.RecordBatch streaming reader.

    Class-level pool (``_pool``) is ``None`` at module import and created
    lazily on the first ``chunk_iter()`` call inside the worker process.
    This prevents pre-fork pool creation under gunicorn ``preload_app=True``
    (ADR-0004).

    Pool sizing: min=2, max=15 (3 jobs × 3 parallel chunks + headroom,
    per §4.2 of query-dataflow-unification.md).
    """

    _pool: "oracledb.SessionPool | None" = None  # class-level, per-worker

    @classmethod
    def _init_pool(cls) -> None:
        """Create the Oracle session pool (called once per worker post-fork)."""
        if cls._pool is not None:
            return

        import oracledb  # deferred import: must not run at module import

        host = os.environ.get("DB_HOST", "")
        port = os.environ.get("DB_PORT", "1521")
        service = os.environ.get("DB_SERVICE", "")
        user = os.environ.get("DB_USER", "")
        password = os.environ.get("DB_PASSWORD", "")
        dsn = f"{host}:{port}/{service}"

        logger.info(
            "OracleArrowReader: initializing pool (min=2, max=15) for DSN=%s user=%s",
            f"{host}:{port}/<service>",
            user,
        )
        cls._pool = oracledb.create_pool(
            user=user,
            password=password,
            dsn=dsn,
            min=2,
            max=15,
            increment=1,
        )

    def chunk_iter(
        self,
        sql: str,
        params: Dict[str, Any],
        chunk_size: int = 10000,
    ) -> Iterator[pa.RecordBatch]:
        """Yield pyarrow.RecordBatch objects for each chunk of Oracle results.

        Acquires exactly one connection from the pool; returns it via
        ``finally`` regardless of success or exception.

        Args:
            sql:        Oracle SQL string with named bind parameters.
            params:     Dictionary of bind parameters.
            chunk_size: Number of rows to fetch per batch.

        Yields:
            pyarrow.RecordBatch — one per fetched chunk; empty result → zero yields.
        """
        self._init_pool()

        conn = self._pool.acquire()  # type: ignore[union-attr]
        try:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            col_names: list[str] = [desc[0] for desc in cursor.description or []]

            while True:
                rows = cursor.fetchmany(chunk_size)
                if not rows:
                    break
                # Build column-oriented dict; apply CHAR strip per column.
                col_data: dict[str, list[Any]] = {name: [] for name in col_names}
                for row in rows:
                    for i, val in enumerate(row):
                        col_data[col_names[i]].append(_strip_char(val))

                # Infer schema from data; null-safe via pa.array auto-inference.
                arrays = [pa.array(col_data[name]) for name in col_names]
                batch = pa.RecordBatch.from_arrays(arrays, names=col_names)
                yield batch
        finally:
            conn.close()  # ALWAYS returns connection to pool
