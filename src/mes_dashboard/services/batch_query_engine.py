# -*- coding: utf-8 -*-
"""BatchQueryEngine — reusable batch query orchestration.

Provides time-range decomposition, ID-batch decomposition,
memory guards, controlled parallelism, Redis chunk caching
with partial cache hits, and progress tracking.

Any service that plugs into this module automatically gains:
  - Oracle timeout protection (via read_sql_df_slow, 300s)
  - OOM protection (per-chunk memory guard)
  - Partial cache reuse (extend date range → reuse old chunks)
  - Progress tracking via Redis HSET

Usage::

    from mes_dashboard.services.batch_query_engine import (
        decompose_by_time_range,
        decompose_by_ids,
        execute_plan,
        merge_chunks,
        compute_query_hash,
    )

    chunks = decompose_by_time_range("2025-01-01", "2025-12-31")
    qh = compute_query_hash({"mode": "date_range", ...})
    execute_plan(chunks, my_query_fn, query_hash=qh, cache_prefix="reject")
    df = merge_chunks("reject", qh)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Generator, List, Optional

import pandas as pd

from mes_dashboard.core.partial_failure_contract import (
    build_partial_failure_meta,
    serialize_partial_failure_meta,
)
from mes_dashboard.core.redis_client import get_key, get_redis_client
from mes_dashboard.core.redis_df_store import (
    redis_chunk_exists,
    redis_load_chunk,
    redis_store_chunk,
)

logger = logging.getLogger("mes_dashboard.batch_query_engine")


_RETRYABLE_PATTERNS = (
    "dpy-4024",
    "ora-01013",
    "ora-03113",
    "ora-03135",
    "ora-12514",
    "ora-12541",
    "timeout",
    "timed out",
)

# ============================================================
# Configuration (env-overridable)
# ============================================================

BATCH_CHUNK_MAX_MEMORY_MB: int = int(
    os.getenv("BATCH_CHUNK_MAX_MEMORY_MB", "192")
)

BATCH_QUERY_TIME_THRESHOLD_DAYS: int = int(
    os.getenv("BATCH_QUERY_TIME_THRESHOLD_DAYS", "10")
)

BATCH_QUERY_ID_THRESHOLD: int = int(
    os.getenv("BATCH_QUERY_ID_THRESHOLD", "1000")
)


# ============================================================
# 1. Time-range decomposition
# ============================================================


def decompose_by_time_range(
    start_date: str,
    end_date: str,
    grain_days: int = 31,
) -> List[Dict[str, str]]:
    """Split ``[start_date, end_date]`` into monthly-ish chunks.

    Boundary semantics (closed interval):
      - Each chunk uses ``[chunk_start, chunk_end]``.
      - The next chunk starts at ``previous_chunk_end + 1 day``.
      - The final chunk may contain fewer than *grain_days* days.

    Args:
        start_date: ISO date string ``YYYY-MM-DD``.
        end_date:   ISO date string ``YYYY-MM-DD``.
        grain_days: Maximum days per chunk (default 31).

    Returns:
        List of dicts with ``chunk_start`` and ``chunk_end`` keys.
    """
    dt_start = datetime.strptime(start_date, "%Y-%m-%d")
    dt_end = datetime.strptime(end_date, "%Y-%m-%d")

    if dt_start > dt_end:
        raise ValueError(
            f"start_date ({start_date}) must be <= end_date ({end_date})"
        )

    chunks: List[Dict[str, str]] = []
    cursor = dt_start
    while cursor <= dt_end:
        chunk_end = min(cursor + timedelta(days=grain_days - 1), dt_end)
        chunks.append(
            {
                "chunk_start": cursor.strftime("%Y-%m-%d"),
                "chunk_end": chunk_end.strftime("%Y-%m-%d"),
            }
        )
        cursor = chunk_end + timedelta(days=1)

    return chunks


# ============================================================
# 2. ID-batch decomposition
# ============================================================


def decompose_by_ids(
    ids: List[Any],
    batch_size: int = 1000,
) -> List[List[Any]]:
    """Split *ids* into batches of at most *batch_size*.

    Args:
        ids: List of IDs (container IDs, lot IDs, etc.).
        batch_size: Maximum items per batch (default 1000,
            matching Oracle IN-clause limit).

    Returns:
        List of ID sub-lists.
    """
    if batch_size < 1:
        raise ValueError("batch_size must be >= 1")
    return [ids[i : i + batch_size] for i in range(0, len(ids), batch_size)]


# ============================================================
# 3. Deterministic query_hash
# ============================================================


def compute_query_hash(params: Dict[str, Any]) -> str:
    """Compute a stable 16-char hex hash for *params*.

    Canonicalization:
      - ``json.dumps`` with ``sort_keys=True`` and ``default=str``.
      - Lists are sorted before serialisation.
      - SHA-256, truncated to first 16 hex chars.

    Only dataset-affecting parameters should be included;
    presentation-only parameters (page, per_page, …) must be
    excluded by the caller.
    """
    canonical = _canonicalize(params)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def _canonicalize(obj: Any) -> str:
    """Recursively sort lists and produce deterministic JSON."""

    def _sort_value(v: Any) -> Any:
        if isinstance(v, list):
            try:
                return sorted(_sort_value(i) for i in v)
            except TypeError:
                return [_sort_value(i) for i in v]
        if isinstance(v, dict):
            return {k: _sort_value(v[k]) for k in sorted(v.keys())}
        return v

    return json.dumps(_sort_value(obj), sort_keys=True, ensure_ascii=False, default=str)


# ============================================================
# 4. Progress tracking via Redis HSET
# ============================================================


def _update_progress(
    cache_prefix: str,
    query_hash: str,
    *,
    total: int,
    completed: int,
    failed: int,
    status: str = "running",
    has_partial_failure: bool = False,
    failed_ranges: Optional[List[Dict[str, str]]] = None,
    ttl: int = 900,
) -> None:
    """Write/update batch progress metadata to Redis."""
    client = get_redis_client()
    if client is None:
        return
    key = get_key(f"batch:{cache_prefix}:{query_hash}:meta")
    pct = round(completed / total * 100, 1) if total else 0
    partial_meta = build_partial_failure_meta(
        failed_count=failed,
        failed_ranges=failed_ranges if has_partial_failure else [],
    )
    if has_partial_failure:
        partial_meta["has_partial_failure"] = True

    mapping = {
        "total": str(total),
        "completed": str(completed),
        "failed": str(failed),
        "pct": str(pct),
        "status": status,
    }
    mapping.update(serialize_partial_failure_meta(partial_meta))
    try:
        client.hset(key, mapping=mapping)
        client.expire(key, ttl)
    except Exception as exc:
        logger.warning("Failed to update batch progress: %s", exc)


def get_batch_progress(
    cache_prefix: str,
    query_hash: str,
) -> Optional[Dict[str, str]]:
    """Read batch progress metadata from Redis."""
    client = get_redis_client()
    if client is None:
        return None
    key = get_key(f"batch:{cache_prefix}:{query_hash}:meta")
    try:
        data = client.hgetall(key)
        return data if data else None
    except Exception:
        return None


# ============================================================
# 5. Execute plan
# ============================================================

# Type alias for the function each chunk calls.
# Signature: query_fn(chunk, max_rows_per_chunk) -> pd.DataFrame
QueryFn = Callable[..., pd.DataFrame]


def execute_plan(
    chunks: List[Dict[str, Any]],
    query_fn: QueryFn,
    *,
    parallel: int = 1,
    query_hash: Optional[str] = None,
    skip_cached: bool = True,
    cache_prefix: str = "",
    chunk_ttl: int = 900,
    max_rows_per_chunk: Optional[int] = None,
) -> str:
    """Execute *chunks* through *query_fn* with caching + guards.

    Args:
        chunks: List of chunk descriptors (dicts from decompose_*).
        query_fn: ``fn(chunk_dict, max_rows_per_chunk=…) -> DataFrame``.
            Must use ``read_sql_df_slow`` internally.
        parallel: Max concurrent chunks (default 1 = sequential).
        query_hash: Precomputed hash; auto-generated if None.
        skip_cached: Skip chunks already in Redis (default True).
        cache_prefix: Service prefix for Redis keys (e.g. "reject").
        chunk_ttl: TTL in seconds for each chunk key (default 900).
        max_rows_per_chunk: Passed to *query_fn* for SQL-level
            ``FETCH FIRST N ROWS ONLY``.

    Returns:
        The ``query_hash`` identifying this batch.
    """
    if query_hash is None:
        query_hash = compute_query_hash({"chunks": chunks})

    total = len(chunks)
    completed = 0
    failed = 0
    has_partial_failure = False
    failed_range_list: Optional[List[Dict[str, str]]] = None

    _update_progress(
        cache_prefix, query_hash,
        total=total, completed=0, failed=0, status="running", ttl=chunk_ttl,
    )

    effective_parallel = _effective_parallelism(parallel)

    if effective_parallel <= 1:
        # --- Sequential path ---
        for idx, chunk in enumerate(chunks):
            if skip_cached and redis_chunk_exists(cache_prefix, query_hash, idx):
                completed += 1
                logger.debug("chunk %d/%d cached, skipping", idx, total)
                _update_progress(
                    cache_prefix, query_hash,
                    total=total, completed=completed, failed=failed,
                    has_partial_failure=has_partial_failure,
                    failed_ranges=failed_range_list,
                    ttl=chunk_ttl,
                )
                continue
            ok = _execute_single_chunk(
                idx, chunk, query_fn, cache_prefix, query_hash,
                chunk_ttl, max_rows_per_chunk,
            )
            if ok:
                completed += 1
            else:
                failed += 1
                has_partial_failure = True
                if failed_range_list is None:
                    failed_range_list = []
                chunk_start = chunk.get("chunk_start")
                chunk_end = chunk.get("chunk_end")
                if chunk_start and chunk_end:
                    failed_range_list.append(
                        {"start": str(chunk_start), "end": str(chunk_end)}
                    )
            _update_progress(
                cache_prefix, query_hash,
                total=total, completed=completed, failed=failed,
                has_partial_failure=has_partial_failure,
                failed_ranges=failed_range_list,
                ttl=chunk_ttl,
            )
    else:
        # --- Parallel path ---
        completed, failed, has_partial_failure, failed_range_list = _execute_parallel(
            chunks, query_fn, cache_prefix, query_hash,
            chunk_ttl, max_rows_per_chunk, skip_cached,
            effective_parallel,
        )

    final_status = "completed" if failed == 0 else ("failed" if completed == 0 else "partial")
    _update_progress(
        cache_prefix, query_hash,
        total=total, completed=completed, failed=failed,
        status=final_status,
        has_partial_failure=has_partial_failure,
        failed_ranges=failed_range_list,
        ttl=chunk_ttl,
    )

    return query_hash


def _effective_parallelism(requested: int) -> int:
    """Cap parallelism at ``min(requested, semaphore_available - 1)``.

    If semaphore is fully occupied, degrade to sequential (1).
    """
    if requested <= 1:
        return 1
    try:
        from mes_dashboard.core.database import _get_slow_query_semaphore
        sem = _get_slow_query_semaphore()
        # threading.Semaphore doesn't expose available count directly;
        # use a non-blocking acquire/release to estimate.
        acquired = sem.acquire(blocking=False)
        if not acquired:
            logger.info("Semaphore fully occupied; degrading to sequential")
            return 1
        sem.release()
        # We got one permit, so at least 1 is available.
        # Conservative cap: min(requested, available - 1) where available >= 1.
        # Since we can't know exact available, just cap at requested.
        return min(requested, 3)  # hard ceiling to be safe
    except Exception:
        return 1


def _execute_single_chunk(
    idx: int,
    chunk: Dict[str, Any],
    query_fn: QueryFn,
    cache_prefix: str,
    query_hash: str,
    chunk_ttl: int,
    max_rows_per_chunk: Optional[int],
    max_retries: int = 1,
) -> bool:
    """Run one chunk through *query_fn*, apply guards, store result.

    Returns True on success, False on failure.
    """
    attempts = max(0, int(max_retries)) + 1
    for attempt in range(attempts):
        try:
            df = query_fn(chunk, max_rows_per_chunk=max_rows_per_chunk)
            if df is None:
                df = pd.DataFrame()

            # ---- Memory guard ----
            mem_bytes = df.memory_usage(deep=True).sum()
            mem_mb = mem_bytes / (1024 * 1024)
            if mem_mb > BATCH_CHUNK_MAX_MEMORY_MB:
                logger.warning(
                    "Chunk %d memory %.1f MB exceeds limit %d MB — discarded",
                    idx, mem_mb, BATCH_CHUNK_MAX_MEMORY_MB,
                )
                return False

            # ---- Store to Redis ----
            stored = redis_store_chunk(cache_prefix, query_hash, idx, df, ttl=chunk_ttl)
            if not stored:
                logger.warning(
                    "Chunk %d failed to persist into Redis, marking as failed", idx
                )
                return False

            logger.debug(
                "Chunk %d completed: %d rows, %.1f MB",
                idx, len(df), mem_mb,
            )
            return True

        except Exception as exc:
            should_retry = attempt < attempts - 1 and _is_retryable_error(exc)
            if should_retry:
                logger.warning(
                    "Chunk %d transient failure on attempt %d/%d: %s; retrying",
                    idx,
                    attempt + 1,
                    attempts,
                    exc,
                )
                continue
            logger.error(
                "Chunk %d failed: %s", idx, exc, exc_info=True,
            )
            return False
    return False


def _execute_parallel(
    chunks: List[Dict[str, Any]],
    query_fn: QueryFn,
    cache_prefix: str,
    query_hash: str,
    chunk_ttl: int,
    max_rows_per_chunk: Optional[int],
    skip_cached: bool,
    max_workers: int,
) -> tuple:
    """Execute chunks in parallel via ThreadPoolExecutor.

    Returns (completed, failed, has_partial_failure, failed_ranges).
    """
    total = len(chunks)
    completed = 0
    failed = 0
    has_partial_failure = False
    failed_range_list: Optional[List[Dict[str, str]]] = None

    futures = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for idx, chunk in enumerate(chunks):
            if skip_cached and redis_chunk_exists(cache_prefix, query_hash, idx):
                completed += 1
                continue
            future = executor.submit(
                _execute_single_chunk,
                idx, chunk, query_fn,
                cache_prefix, query_hash, chunk_ttl, max_rows_per_chunk,
            )
            futures[future] = (idx, chunk)

        for future in as_completed(futures):
            idx, chunk = futures[future]
            try:
                ok = future.result()
                if ok:
                    completed += 1
                else:
                    failed += 1
                    has_partial_failure = True
                    if failed_range_list is None:
                        failed_range_list = []
                    chunk_start = chunk.get("chunk_start")
                    chunk_end = chunk.get("chunk_end")
                    if chunk_start and chunk_end:
                        failed_range_list.append(
                            {"start": str(chunk_start), "end": str(chunk_end)}
                        )
            except Exception as exc:
                logger.error("Chunk %d future error: %s", idx, exc)
                failed += 1
                has_partial_failure = True
                if failed_range_list is None:
                    failed_range_list = []
                chunk_start = chunk.get("chunk_start")
                chunk_end = chunk.get("chunk_end")
                if chunk_start and chunk_end:
                    failed_range_list.append(
                        {"start": str(chunk_start), "end": str(chunk_end)}
                    )

            _update_progress(
                cache_prefix, query_hash,
                total=total, completed=completed, failed=failed,
                has_partial_failure=has_partial_failure,
                failed_ranges=failed_range_list,
                ttl=chunk_ttl,
            )

    return completed, failed, has_partial_failure, failed_range_list


def _is_retryable_error(exc: Exception) -> bool:
    """Return True for transient Oracle/network timeout errors."""
    if isinstance(exc, (TimeoutError, ConnectionError, OSError)):
        return True
    text = str(exc).strip().lower()
    if not text:
        return False
    return any(pattern in text for pattern in _RETRYABLE_PATTERNS)


# ============================================================
# 6. Merge / iterate chunks
# ============================================================


class MergeChunksMaxRowsExceeded(RuntimeError):
    """Raised when merge_chunks exceeds max_total_rows in strict mode."""

    def __init__(self, *, max_total_rows: int, observed_rows: int, chunk_index: int):
        super().__init__(
            "merge_chunks max_total_rows exceeded "
            f"(max_total_rows={max_total_rows}, observed_rows={observed_rows}, chunk_index={chunk_index})"
        )
        self.max_total_rows = int(max_total_rows)
        self.observed_rows = int(observed_rows)
        self.chunk_index = int(chunk_index)


def merge_chunks(
    cache_prefix: str,
    query_hash: str,
    total: Optional[int] = None,
    max_total_rows: Optional[int] = None,
    overflow_mode: str = "truncate",
) -> pd.DataFrame:
    """Load all chunks from Redis and concatenate into one DataFrame.

    If *total* is not given, reads it from the progress metadata.
    Missing chunks are skipped (``has_partial_failure`` semantics).
    """
    if total is None:
        progress = get_batch_progress(cache_prefix, query_hash)
        if progress:
            total = int(progress.get("total", 0))
        else:
            total = 0

    dfs: List[pd.DataFrame] = []
    total_rows = 0
    if overflow_mode not in {"truncate", "error"}:
        raise ValueError("overflow_mode must be either 'truncate' or 'error'")

    for idx in range(total):
        df = redis_load_chunk(cache_prefix, query_hash, idx)
        if df is not None and not df.empty:
            if max_total_rows is not None and total_rows >= max_total_rows:
                if overflow_mode == "error":
                    observed_rows = total_rows + len(df)
                    logger.warning(
                        "merge_chunks overflow in strict mode after cap reached: max_total_rows=%d, observed_rows=%d, chunk=%d",
                        max_total_rows,
                        observed_rows,
                        idx,
                    )
                    raise MergeChunksMaxRowsExceeded(
                        max_total_rows=max_total_rows,
                        observed_rows=observed_rows,
                        chunk_index=idx,
                    )
                logger.warning(
                    "merge_chunks reached max_total_rows=%d (prefix=%s, query_hash=%s)",
                    max_total_rows,
                    cache_prefix,
                    query_hash,
                )
                break
            if max_total_rows is not None:
                remaining = max_total_rows - total_rows
                if remaining <= 0:
                    break
                if len(df) > remaining:
                    if overflow_mode == "error":
                        observed_rows = total_rows + len(df)
                        logger.warning(
                            "merge_chunks overflow in strict mode: max_total_rows=%d, observed_rows=%d, chunk=%d",
                            max_total_rows,
                            observed_rows,
                            idx,
                        )
                        raise MergeChunksMaxRowsExceeded(
                            max_total_rows=max_total_rows,
                            observed_rows=observed_rows,
                            chunk_index=idx,
                        )
                    df = df.head(remaining).copy()
                    logger.warning(
                        "merge_chunks truncated chunk %d to %d rows (max_total_rows=%d)",
                        idx,
                        remaining,
                        max_total_rows,
                    )
            dfs.append(df)
            total_rows += len(df)

    if not dfs:
        return pd.DataFrame()

    return pd.concat(dfs, ignore_index=True)


def iterate_chunks(
    cache_prefix: str,
    query_hash: str,
    total: Optional[int] = None,
) -> Generator[pd.DataFrame, None, None]:
    """Yield chunk DataFrames one at a time (memory-friendly).

    Skips missing chunks.
    """
    if total is None:
        progress = get_batch_progress(cache_prefix, query_hash)
        if progress:
            total = int(progress.get("total", 0))
        else:
            total = 0

    for idx in range(total):
        df = redis_load_chunk(cache_prefix, query_hash, idx)
        if df is not None:
            yield df


# ============================================================
# 7. Streaming merge to spool (memory-efficient path)
# ============================================================


def merge_chunks_to_spool(
    cache_prefix: str,
    query_hash: str,
    spool_dir,
    max_total_rows: Optional[int] = None,
    overflow_mode: str = "error",
):
    """Stream-merge Redis chunks into a single parquet spool file.

    Iterates chunks one-by-one via :func:`iterate_chunks` and appends each
    to a ``pyarrow.parquet.ParquetWriter``.  Peak memory is proportional to a
    single chunk rather than the full result set.

    Args:
        cache_prefix: Redis cache namespace (e.g. ``"reject"``).
        query_hash:   Hash key identifying the batch job.
        spool_dir:    Directory in which to write the temp parquet file.
        max_total_rows: Hard row cap. Behaviour on breach is controlled by
            *overflow_mode*.
        overflow_mode: ``"error"`` raises :exc:`MergeChunksMaxRowsExceeded`;
            ``"truncate"`` stops writing and returns partial results.

    Returns:
        ``(Path, total_rows)`` on success, or ``(None, 0)`` for empty results.

    Raises:
        :exc:`MergeChunksMaxRowsExceeded`: when ``overflow_mode="error"`` and
            the row cap is exceeded.
    """
    import pyarrow as pa
    import pyarrow.parquet as pq
    from pathlib import Path as _Path

    if overflow_mode not in {"truncate", "error"}:
        raise ValueError("overflow_mode must be either 'truncate' or 'error'")

    spool_dir = _Path(spool_dir)
    spool_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = spool_dir / f"{cache_prefix}_{query_hash}_streaming.tmp.parquet"

    writer: Optional[pq.ParquetWriter] = None
    schema: Optional[pa.Schema] = None
    total_rows = 0
    chunk_index = 0

    try:
        for df_chunk in iterate_chunks(cache_prefix, query_hash):
            if df_chunk.empty:
                chunk_index += 1
                continue

            if max_total_rows is not None and total_rows >= max_total_rows:
                if overflow_mode == "error":
                    raise MergeChunksMaxRowsExceeded(
                        max_total_rows=max_total_rows,
                        observed_rows=total_rows + len(df_chunk),
                        chunk_index=chunk_index,
                    )
                logger.warning(
                    "merge_chunks_to_spool reached max_total_rows=%d (prefix=%s)",
                    max_total_rows,
                    cache_prefix,
                )
                break

            # Clip last chunk when needed
            if max_total_rows is not None:
                remaining = max_total_rows - total_rows
                if len(df_chunk) > remaining:
                    if overflow_mode == "error":
                        raise MergeChunksMaxRowsExceeded(
                            max_total_rows=max_total_rows,
                            observed_rows=total_rows + len(df_chunk),
                            chunk_index=chunk_index,
                        )
                    df_chunk = df_chunk.head(remaining).copy()

            table = pa.Table.from_pandas(df_chunk, preserve_index=False)

            if writer is None:
                schema = table.schema
                writer = pq.ParquetWriter(str(tmp_path), schema)

            # Align schema for subsequent chunks (drop unexpected columns, fill missing)
            if table.schema != schema:
                try:
                    table = table.cast(schema)
                except Exception:
                    # Best-effort: select only columns in schema
                    common_cols = [f.name for f in schema if f.name in table.schema.names]
                    if not common_cols:
                        chunk_index += 1
                        continue
                    table = table.select(common_cols).cast(
                        pa.schema([schema.field(c) for c in common_cols])
                    )

            writer.write_table(table)
            total_rows += len(df_chunk)
            chunk_index += 1

    except Exception:
        if writer is not None:
            try:
                writer.close()
            except Exception:
                pass
            writer = None
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except Exception:
                pass
        raise
    finally:
        if writer is not None:
            writer.close()

    if total_rows == 0 or not tmp_path.exists():
        if tmp_path.exists():
            tmp_path.unlink()
        return None, 0

    logger.info(
        "merge_chunks_to_spool complete (prefix=%s, rows=%d, path=%s)",
        cache_prefix,
        total_rows,
        tmp_path,
    )
    return tmp_path, total_rows


# ============================================================
# 8. Convenience: should_use_engine?
# ============================================================


def should_decompose_by_time(start_date: str, end_date: str) -> bool:
    """Return True if the date range exceeds the threshold for engine use."""
    try:
        dt_start = datetime.strptime(start_date, "%Y-%m-%d")
        dt_end = datetime.strptime(end_date, "%Y-%m-%d")
        return (dt_end - dt_start).days > BATCH_QUERY_TIME_THRESHOLD_DAYS
    except (ValueError, TypeError):
        return False


def should_decompose_by_ids(ids: List[Any]) -> bool:
    """Return True if the ID list exceeds the threshold for engine use."""
    return len(ids) > BATCH_QUERY_ID_THRESHOLD
