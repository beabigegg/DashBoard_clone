# -*- coding: utf-8 -*-
"""Hold-history dataset cache.

Primary query (POST /query) → Oracle → spool to Parquet → call DuckDB apply_view() → return result.
Supplementary view (GET /view) → read spool → DuckDB apply_view() → return result.

Cache layers:
  L1: ProcessLevelCache (in-process, per-worker)
  L2: spool file + Redis metadata pointer (< 1 KB)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd

from mes_dashboard.core.cache import ProcessLevelCache, register_process_cache
from mes_dashboard.core.database import read_sql_df_slow as read_sql_df
from mes_dashboard.core.query_spool_store import (
    QUERY_SPOOL_DIR,
    get_spool_file_path,
    register_spool_file,
    store_spooled_df,
)
from mes_dashboard.core.redis_client import get_key, get_redis_client
from mes_dashboard.sql.filters import CommonFilters

logger = logging.getLogger("mes_dashboard.hold_dataset_cache")

from mes_dashboard.config.constants import CACHE_TTL_DATASET
_CACHE_TTL = CACHE_TTL_DATASET
_CACHE_MAX_SIZE = 1
_REDIS_NAMESPACE = "hold_dataset"
_HOLD_ENGINE_PARALLEL = max(1, int(os.getenv("HOLD_ENGINE_PARALLEL", "1")))
_DEFAULT_DETAIL_PER_PAGE = 20

_dataset_cache = ProcessLevelCache(ttl_seconds=_CACHE_TTL, max_size=_CACHE_MAX_SIZE)
register_process_cache("hold_dataset", _dataset_cache, "Hold Dataset (L1, 15min)")

_SQL_DIR = Path(__file__).resolve().parent.parent / "sql" / "hold_history"


# ============================================================
# SQL loading
# ============================================================


@lru_cache(maxsize=4)
def _load_sql(name: str) -> str:
    path = _SQL_DIR / f"{name}.sql"
    sql = path.read_text(encoding="utf-8")
    if "{{ NON_QUALITY_REASONS }}" in sql:
        sql = sql.replace(
            "{{ NON_QUALITY_REASONS }}",
            CommonFilters.get_non_quality_reasons_sql(),
        )
    return sql


# ============================================================
# Query ID
# ============================================================


# Bump when the spool's row semantics change so pre-existing cached spools are
# orphaned (the redis spool pointer + parquet file outlive a gunicorn restart, so a
# version token is the self-healing alternative to a manual post-deploy parquet purge).
# v2: whole-range single-chunk query removed cross-chunk duplication of open holds.
_QUERY_ID_SCHEMA = 2


def _make_query_id(params: dict) -> str:
    """Deterministic hash from primary query params."""
    canonical = json.dumps(
        {**params, "_schema": _QUERY_ID_SCHEMA},
        sort_keys=True, ensure_ascii=False, default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


# ============================================================
# Cache existence check and write
# ============================================================


def _has_cached_df(query_id: str) -> bool:
    """Check if query_id has cached data (L1 marker or spool exists)."""
    if _dataset_cache.get(query_id) is not None:
        return True
    return get_spool_file_path(_REDIS_NAMESPACE, query_id) is not None


def _store_query_dates(query_id: str, start_date: str, end_date: str) -> None:
    """Persist query date range in Redis for record_type='new' boundary computation."""
    client = get_redis_client()
    if client is None:
        return
    try:
        client.setex(
            get_key(f"{_REDIS_NAMESPACE}:{query_id}:dates"),
            _CACHE_TTL,
            json.dumps({"start": start_date, "end": end_date}),
        )
    except Exception:
        pass


def _get_query_dates(query_id: str) -> Optional[Dict[str, str]]:
    """Retrieve stored query date range from Redis."""
    client = get_redis_client()
    if client is None:
        return None
    try:
        raw = client.get(get_key(f"{_REDIS_NAMESPACE}:{query_id}:dates"))
        if raw:
            return json.loads(raw)
    except Exception:
        pass
    return None


def _store_df(query_id: str, df: pd.DataFrame) -> None:
    """Write to spool; L1 gets lightweight marker."""
    _dataset_cache.set(query_id, True)  # lightweight marker
    store_spooled_df(_REDIS_NAMESPACE, query_id, df, ttl_seconds=_CACHE_TTL)


# ============================================================
# Primary query
# ============================================================


def execute_primary_query(
    *,
    start_date: str,
    end_date: str,
    hold_type: str = "quality",
    record_type: str = "new",
) -> Dict[str, Any]:
    """Execute Oracle query -> spool to Parquet -> return DuckDB-computed result."""

    query_id = _make_query_id({"start_date": start_date, "end_date": end_date})

    _spool_available = _has_cached_df(query_id)
    _hold_partial_failure: Dict[str, Any] = {}

    if _spool_available:
        logger.info("Hold dataset cache hit for query_id=%s", query_id)
    else:
        logger.info(
            "Hold dataset cache miss for query_id=%s, querying Oracle", query_id
        )

        from mes_dashboard.services.batch_query_engine import (
            _USE_ROW_COUNT_CHUNKING,
            decompose_by_row_count,
            execute_plan,
            get_batch_progress,
            merge_chunks_to_spool,
            compute_query_hash,
            should_decompose_by_time,
        )

        if should_decompose_by_time(start_date, end_date):
            # --- Engine path for long date ranges → stream to Parquet spool ---
            if _USE_ROW_COUNT_CHUNKING:
                # --- Row-count chunking path (USE_ROW_COUNT_CHUNKING=true) ---
                count_sql = _load_sql("count_query")
                count_params = {"start_date": start_date, "end_date": end_date}
                _count_df = read_sql_df(
                    count_sql, count_params,
                    caller="hold_dataset_cache:count_query",
                )
                total_rows = int(_count_df.iloc[0].get("ROW_COUNT") or 0) if (
                    _count_df is not None and not _count_df.empty
                ) else 0
                engine_chunks = decompose_by_row_count(total_rows)
                engine_hash = compute_query_hash({
                    "start_date": start_date, "end_date": end_date,
                    "mode": "row_count", "total_rows": total_rows,
                })
                paged_sql = _load_sql("list_paged")

                def _run_hold_chunk(chunk, max_rows_per_chunk=None):
                    params = {
                        "start_date": start_date,
                        "end_date": end_date,
                        "start_row": chunk["start_row"],
                        "end_row": chunk["end_row"],
                    }
                    result = read_sql_df(
                        paged_sql, params,
                        caller="hold_dataset_cache:execute_paged_chunk",
                    )
                    return result if result is not None else pd.DataFrame()

                logger.info(
                    "Engine (row-count) activated for hold: total=%d chunks=%d (query_id=%s)",
                    total_rows, len(engine_chunks), query_id,
                )
            else:
                # --- Whole-range single-chunk path (ADR-0003 style) ---
                # base_facts.sql carries an `OR h.RELEASETXNDATE IS NULL` escape in
                # BOTH AND-groups of its WHERE, so it returns ALL currently-open holds
                # regardless of the date window. Splitting the range into N time-chunks
                # would re-fetch those open holds in EVERY chunk, and merge_chunks_to_spool
                # concatenates without dedup → the on_hold view counts them N times and
                # the on-hold number balloons ~Nx once the range exceeds one 31-day grain.
                # We therefore run base_facts ONCE over the full range (a single chunk).
                # This keeps the open-hold "standing inventory" semantics intact while
                # making the merged spool free of cross-chunk duplicates.
                # Empirically cheap: ~1.9 s / ~52k rows for a 2-year range (hold/release
                # events are sparse), so a single query stays well under the slow-pool
                # call timeout. The frontend caps the selectable range as a guardrail.
                engine_chunks = [{"chunk_start": start_date, "chunk_end": end_date}]
                engine_hash = compute_query_hash(
                    {"start_date": start_date, "end_date": end_date}
                )
                base_sql = _load_sql("base_facts")

                def _run_hold_chunk(chunk, max_rows_per_chunk=None):
                    params = {
                        "start_date": chunk["chunk_start"],
                        "end_date": chunk["chunk_end"],
                    }
                    result = read_sql_df(
                        base_sql,
                        params,
                        caller="hold_dataset_cache:execute_primary_query_chunk",
                    )
                    return result if result is not None else pd.DataFrame()

                logger.info(
                    "Engine activated for hold: %d chunk(s), whole-range (query_id=%s)",
                    len(engine_chunks), query_id,
                )

            execute_plan(
                engine_chunks, _run_hold_chunk,
                parallel=_HOLD_ENGINE_PARALLEL,
                query_hash=engine_hash,
                cache_prefix="hold",
                chunk_ttl=_CACHE_TTL,
            )
            _hold_progress = get_batch_progress("hold", engine_hash) or {}
            if _hold_progress.get("has_partial_failure") in (True, "True", "true", "1", 1):
                _hold_partial_failure = {
                    "has_partial_failure": True,
                    "failed_chunk_count": _hold_progress.get("failed_chunk_count"),
                    "failed_ranges": _hold_progress.get("failed_ranges"),
                }
                logger.warning(
                    "hold partial failure (query_id=%s): failed_ranges=%s",
                    query_id, _hold_progress.get("failed_ranges"),
                )
            spool_tmp_path, spool_row_count = merge_chunks_to_spool(
                "hold",
                engine_hash,
                spool_dir=QUERY_SPOOL_DIR,
            )
            if spool_tmp_path is not None:
                register_spool_file(
                    _REDIS_NAMESPACE,
                    query_id,
                    spool_tmp_path,
                    spool_row_count,
                    ttl_seconds=_CACHE_TTL,
                )
                _dataset_cache.set(query_id, True)  # L1 marker
                _store_query_dates(query_id, start_date, end_date)
                _spool_available = True
        else:
            # --- Direct path (short query) ---
            sql = _load_sql("base_facts")
            params = {"start_date": start_date, "end_date": end_date}
            df = read_sql_df(
                sql,
                params,
                caller="hold_dataset_cache:execute_primary_query_direct",
            )
            if df is None:
                df = pd.DataFrame()
            if not df.empty:
                _store_df(query_id, df)
                _store_query_dates(query_id, start_date, end_date)
                _spool_available = True

    result = apply_view(
        query_id=query_id,
        hold_type=hold_type,
        record_type=record_type,
        page=1,
        per_page=_DEFAULT_DETAIL_PER_PAGE,
        _start_date=start_date,
        _end_date=end_date,
    )
    if result is None:
        if _spool_available:
            raise RuntimeError(
                f"bootstrap render failure: apply_view returned None for query_id={query_id}"
            )
        return {"query_id": query_id, **_empty_views()}
    if _hold_partial_failure:
        result.setdefault("_meta", {})["partial_failure"] = _hold_partial_failure
    return {"query_id": query_id, **result}


# ============================================================
# View (supplementary filtering on cache)
# ============================================================


def apply_view(
    *,
    query_id: str,
    hold_type: str = "quality",
    reason: Optional[str] = None,
    record_type: str = "new",
    duration_range: Optional[str] = None,
    page: int = 1,
    per_page: int = 50,
    _start_date: Optional[str] = None,
    _end_date: Optional[str] = None,
    export_mode: bool = False,
    sort_col: str = "holdDate",
    sort_dir: str = "desc",
    day_filter: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Read cache -> apply filters -> return derived data. Returns None if expired (→ route returns 410).

    DuckDB SQL runtime is the sole compute path. Spool miss or runtime error
    returns None (cache_expired).
    ``_start_date``/``_end_date`` are passed through to the SQL runtime for
    record_type='new' boundary computation.
    """
    resolved_start_date = _start_date
    resolved_end_date = _end_date
    if not resolved_start_date or not resolved_end_date:
        query_dates = _get_query_dates(query_id) or {}
        if not resolved_start_date:
            start = str(query_dates.get("start") or "").strip()
            resolved_start_date = start or None
        if not resolved_end_date:
            end = str(query_dates.get("end") or "").strip()
            resolved_end_date = end or None

    # ── Task 4.6: Try DuckDB SQL runtime path ─────────────────────────────
    try:
        from mes_dashboard.services.hold_history_sql_runtime import (
            try_compute_view_from_spool,
        )
        sql_result, sql_meta = try_compute_view_from_spool(
            query_id=query_id,
            hold_type=hold_type,
            reason=reason,
            record_type=record_type,
            duration_range=duration_range,
            page=page,
            per_page=per_page,
            start_date=resolved_start_date,
            end_date=resolved_end_date,
            export_mode=export_mode,
            sort_col=sort_col,
            sort_dir=sort_dir,
            day_filter=day_filter,
        )
        if sql_result is not None:
            return {**sql_result, "_meta": sql_meta}
        fallback_reason = sql_meta.get("view_sql_fallback_reason", "unknown")
        logger.debug(
            "hold apply_view: SQL runtime fallback (reason=%s query_id=%s)",
            fallback_reason, query_id,
        )
    except Exception as exc:
        logger.warning("hold apply_view: SQL runtime error: %s", exc)
    return None


def _empty_views() -> Dict[str, Any]:
    return {
        "trend": {"days": []},
        "reason_pareto": {"items": []},
        "duration": {"items": []},
        "list": {
            "items": [],
            "pagination": {
                "page": 1,
                "perPage": _DEFAULT_DETAIL_PER_PAGE,
                "total": 0,
                "totalPages": 1,
            },
        },
    }




# ---------------------------------------------------------------------------
# Canonical warmup identity (task 2.1)
# ---------------------------------------------------------------------------
# hold-overview canonical spool key is determined by (start_date, end_date).
# Warmup uses the rolling last-90-days window so the key is date-stable.
_WARMUP_DAYS = 90


def make_canonical_warmup_query_id(start_date: str, end_date: str) -> str:
    """Return the canonical spool key for the given date range."""
    return _make_query_id({"start_date": start_date, "end_date": end_date})


def ensure_canonical_spool(start_date: str, end_date: str) -> Dict[str, Any]:
    """Ensure the hold spool exists for an arbitrary date range.

    Called by the RQ worker after completing a user-triggered async query so
    that subsequent queries for the same date range are served from the spool
    synchronously (no Oracle hit, no new job dispatch).

    Unlike resource-history, hold-history has a single spool key space keyed on
    {start_date, end_date} only — hold_type/record_type are view-level filters.
    So the spool created here IS the canonical; no separate canonical key exists.

    If the spool already exists (common case — worker just created it), this is
    a cheap Redis check and returns immediately.
    """
    query_id = _make_query_id({"start_date": start_date, "end_date": end_date})
    if _has_cached_df(query_id):
        return {"query_id": query_id, "cache_hit": True}
    result = execute_primary_query(start_date=start_date, end_date=end_date)
    return {"query_id": result.get("query_id", query_id), "cache_hit": False}


def ensure_dataset_loaded() -> Dict[str, Any]:
    """Ensure the default hold dataset exists in cache (used by warmup scheduler)."""
    end_dt = date.today()
    start_dt = end_dt - timedelta(days=_WARMUP_DAYS - 1)
    start_date = start_dt.strftime("%Y-%m-%d")
    end_date = end_dt.strftime("%Y-%m-%d")

    query_id = make_canonical_warmup_query_id(start_date, end_date)
    if _has_cached_df(query_id):
        return {"query_id": query_id, "cache_hit": True, "start_date": start_date, "end_date": end_date}

    result = execute_primary_query(start_date=start_date, end_date=end_date)
    return {
        "query_id": result.get("query_id", query_id),
        "cache_hit": False,
        "start_date": start_date,
        "end_date": end_date,
    }
