# -*- coding: utf-8 -*-
"""Two-phase reject-history dataset cache.

Primary query (POST /query) → Oracle → cache full LOT-level DataFrame.
Supplementary view (GET /view) → read cache → pandas filter/derive.

Cache layers:
  L1: ProcessLevelCache (in-process, per-worker)
  L2: spool file + Redis metadata pointer (< 1 KB) [Phase 2]; Redis parquet bytes [Phase 1 fallback]
"""

from __future__ import annotations

import gc
import hashlib
import json
import logging
import os
import time
import uuid
from datetime import date, timedelta
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd

from mes_dashboard.core.cache import ProcessLevelCache, register_process_cache
from mes_dashboard.core.database import read_sql_df_slow as read_sql_df
from mes_dashboard.core.query_spool_store import (
    get_spool_file_path,
    load_spooled_df,
    store_spooled_df,
)
from mes_dashboard.core.global_concurrency import (
    acquire_heavy_query_slot,
    release_heavy_query_slot,
)
from mes_dashboard.core.redis_client import get_key, get_redis_client
from mes_dashboard.core.redis_df_store import (
    redis_clear_batch,
)
from mes_dashboard.core.partial_failure_contract import (
    build_partial_failure_meta,
    parse_partial_failure_meta,
    serialize_partial_failure_meta,
)
from mes_dashboard.services.filter_cache import get_specs_for_groups
from mes_dashboard.services.container_resolution_policy import (
    assess_resolution_result,
    extract_container_ids,
    normalize_input_values,
    validate_resolution_request,
    validate_resolution_result,
)
from mes_dashboard.services.reject_history_service import (
    _as_float,
    _as_int,
    _build_where_clause,
    _derive_summary,
    _extract_distinct_text_values,
    _extract_workcenter_group_options,
    _normalize_text,
    _prepare_sql,
    _to_date_str,
    _to_datetime_str,
    _validate_range,
)
from mes_dashboard.services.query_tool_service import (
    _resolve_by_lot_id,
    _resolve_by_wafer_lot,
    _resolve_by_work_order,
)
from mes_dashboard.sql import QueryBuilder

logger = logging.getLogger("mes_dashboard.reject_dataset_cache")

from mes_dashboard.config.constants import CACHE_TTL_DATASET
_CACHE_TTL = CACHE_TTL_DATASET
_CACHE_MAX_SIZE = 1
_REDIS_NAMESPACE = "reject_dataset"
_CACHE_SCHEMA_VERSION = 4
_REJECT_PRIMARY_SQL_TEMPLATE = "primary"
_REJECT_ENGINE_GRAIN_DAYS = max(1, int(os.getenv("REJECT_ENGINE_GRAIN_DAYS", "10")))
_REJECT_ENGINE_PARALLEL = max(1, int(os.getenv("REJECT_ENGINE_PARALLEL", "1")))
_REJECT_ENGINE_MAX_ROWS_PER_CHUNK = max(
    1, int(os.getenv("REJECT_ENGINE_MAX_ROWS_PER_CHUNK", "50000"))
)
_REJECT_ENGINE_MAX_TOTAL_ROWS = max(
    1, int(os.getenv("REJECT_ENGINE_MAX_TOTAL_ROWS", "200000"))
)
_REJECT_ENGINE_SPILL_ENABLED = os.getenv("REJECT_ENGINE_SPILL_ENABLED", "true").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
_REJECT_ENGINE_MAX_RESULT_MB = max(
    1, int(os.getenv("REJECT_ENGINE_MAX_RESULT_MB", "48"))
)
_REJECT_ENGINE_SPOOL_TTL_SECONDS = max(
    300, int(os.getenv("REJECT_ENGINE_SPOOL_TTL_SECONDS", "21600"))
)
_REJECT_ENGINE_QUERY_LOCK_TTL_SECONDS = max(
    60, int(os.getenv("REJECT_ENGINE_QUERY_LOCK_TTL_SECONDS", "1200"))
)
_REJECT_ENGINE_QUERY_WAIT_SECONDS = max(
    1, int(os.getenv("REJECT_ENGINE_QUERY_WAIT_SECONDS", "90"))
)
_REJECT_ENGINE_QUERY_WAIT_POLL_SECONDS = max(
    0.1, float(os.getenv("REJECT_ENGINE_QUERY_WAIT_POLL_SECONDS", "1.0"))
)
_REJECT_DERIVE_MAX_INPUT_MB = max(
    16, int(os.getenv("REJECT_DERIVE_MAX_INPUT_MB", "96"))
)
_REJECT_DERIVE_MAX_PROJECTED_RSS_MB = max(
    _REJECT_DERIVE_MAX_INPUT_MB + 64,
    int(os.getenv("REJECT_DERIVE_MAX_PROJECTED_RSS_MB", "1100")),
)
_REJECT_DERIVE_WORKING_SET_FACTOR = max(
    1.0, float(os.getenv("REJECT_DERIVE_WORKING_SET_FACTOR", "1.8"))
)
_REJECT_DERIVE_FORCE_GC = os.getenv("REJECT_DERIVE_FORCE_GC", "true").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

_dataset_cache = ProcessLevelCache(ttl_seconds=_CACHE_TTL, max_size=_CACHE_MAX_SIZE)
register_process_cache("reject_dataset", _dataset_cache, "Reject Dataset (L1, 15min)")

_WARMUP_DAYS = max(1, int(os.getenv("REJECT_DATASET_WARMUP_DAYS", "30")))
_GROUPBY_OPTIMIZED_COLUMNS = (
    "TXN_DAY",
    "LOSSREASONNAME",
    "PRODUCTLINENAME",
    "PJ_TYPE",
    "WORKCENTER_GROUP",
)


class RejectPrimaryQueryOverloadError(RuntimeError):
    """Operational overload guardrail for reject primary query."""

    def __init__(self, message: str, *, code: str, retry_after: int = 30):
        super().__init__(message)
        self.code = str(code)
        self.retry_after = max(1, int(retry_after))



# ============================================================
# Query ID
# ============================================================


def _make_query_id(params: dict) -> str:
    """Deterministic hash from primary query params + policy toggles."""
    canonical = json.dumps(params, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


# ============================================================
# Redis L2 helpers (delegated to shared redis_df_store)
# ============================================================





def _redis_delete_df(query_id: str) -> None:
    client = get_redis_client()
    if client is None:
        return
    try:
        client.delete(get_key(f"{_REDIS_NAMESPACE}:{query_id}"))
    except Exception:
        return


def _partial_failure_key(query_id: str) -> str:
    return f"{_REDIS_NAMESPACE}:{query_id}:partial_failure"


def _store_partial_failure_flag(
    query_id: str,
    failed_count: int,
    failed_ranges: Optional[List[Dict[str, str]]],
    ttl: int,
) -> None:
    """Persist partial-failure metadata for cache-hit responses."""
    client = get_redis_client()
    if client is None:
        return
    key = get_key(_partial_failure_key(query_id))
    mapping = serialize_partial_failure_meta(
        build_partial_failure_meta(
            failed_count=failed_count,
            failed_ranges=failed_ranges or [],
        )
    )
    try:
        client.hset(key, mapping=mapping)
        client.expire(key, max(int(ttl), 1))
    except Exception as exc:
        logger.warning("Failed to store partial failure flag (query_id=%s): %s", query_id, exc)


def _load_partial_failure_flag(query_id: str) -> Dict[str, Any]:
    """Load persisted partial-failure metadata for cache-hit responses."""
    client = get_redis_client()
    if client is None:
        return {}
    key = get_key(_partial_failure_key(query_id))
    try:
        raw = client.hgetall(key)
    except Exception:
        return {}
    return parse_partial_failure_meta(raw)


def _clear_partial_failure_flag(query_id: str) -> None:
    client = get_redis_client()
    if client is None:
        return
    try:
        client.delete(get_key(_partial_failure_key(query_id)))
    except Exception:
        return


def _query_lock_key(query_id: str) -> str:
    return f"{_REDIS_NAMESPACE}:{query_id}:inflight"


def _acquire_query_lock(query_id: str, owner: str) -> bool:
    """Acquire cross-worker single-flight lock; fail-open when Redis is unavailable."""
    client = get_redis_client()
    if client is None:
        return True
    key = get_key(_query_lock_key(query_id))
    try:
        acquired = client.set(
            key,
            owner,
            nx=True,
            ex=_REJECT_ENGINE_QUERY_LOCK_TTL_SECONDS,
        )
        return bool(acquired)
    except Exception as exc:
        logger.warning("Query lock acquisition failed (query_id=%s): %s", query_id, exc)
        return True


def _release_query_lock(query_id: str, owner: str) -> None:
    client = get_redis_client()
    if client is None:
        return
    key = get_key(_query_lock_key(query_id))
    try:
        current = client.get(key)
        if current is None:
            return
        if isinstance(current, bytes):
            current = current.decode("utf-8", errors="ignore")
        if str(current) == str(owner):
            client.delete(key)
    except Exception as exc:
        logger.warning("Query lock release failed (query_id=%s): %s", query_id, exc)


def _is_query_lock_active(query_id: str) -> bool:
    client = get_redis_client()
    if client is None:
        return False
    key = get_key(_query_lock_key(query_id))
    try:
        return bool(client.exists(key))
    except Exception:
        return False


def _wait_for_inflight_query_result(query_id: str) -> bool:
    """Wait for in-flight owner to finish and publish cache. Returns True when ready."""
    deadline = time.monotonic() + float(_REJECT_ENGINE_QUERY_WAIT_SECONDS)
    poll = float(_REJECT_ENGINE_QUERY_WAIT_POLL_SECONDS)
    while time.monotonic() < deadline:
        if _has_cached_df(query_id):
            return True
        if not _is_query_lock_active(query_id):
            return False
        time.sleep(poll)

    raise RejectPrimaryQueryOverloadError(
        "同條件查詢仍在執行中，請稍後重試",
        code="SERVICE_UNAVAILABLE",
        retry_after=max(3, int(round(poll))),
    )


# ============================================================
# Cache read (L1 → L2 → None)
# ============================================================



def _has_cached_df(query_id: str) -> bool:
    """Check if query_id has cached data (L1 marker or spool exists)."""
    if _dataset_cache.get(query_id) is not None:
        return True
    spool_path = get_spool_file_path(_REDIS_NAMESPACE, query_id)
    return spool_path is not None


def _store_df(query_id: str, df: pd.DataFrame) -> None:
    """Write to spool; L1 gets lightweight marker."""
    df = _optimize_groupby_dtypes(df)
    _dataset_cache.set(query_id, True)  # lightweight marker
    store_spooled_df(_REDIS_NAMESPACE, query_id, df, ttl_seconds=_CACHE_TTL)


def _optimize_groupby_dtypes(df: pd.DataFrame) -> pd.DataFrame:
    """Convert high-cardinality groupby dimensions to categorical dtype."""
    if df is None or df.empty:
        return df

    optimized = df.copy()
    for col in _GROUPBY_OPTIMIZED_COLUMNS:
        if col not in optimized.columns:
            continue
        series = optimized[col]
        if str(series.dtype) == "category":
            continue
        if col == "TXN_DAY":
            optimized[col] = series.astype("category")
            continue
        if pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series):
            optimized[col] = series.astype("category")
    return optimized


def _store_query_result(query_id: str, df: pd.DataFrame) -> bool:
    """Store result and return True when persisted via parquet spill."""
    if df is None or df.empty:
        return False

    optimized_df = _optimize_groupby_dtypes(df)
    df_mb = optimized_df.memory_usage(deep=True).sum() / (1024 * 1024)
    should_spill = _REJECT_ENGINE_SPILL_ENABLED and (
        len(optimized_df) >= _REJECT_ENGINE_MAX_TOTAL_ROWS
        or df_mb >= _REJECT_ENGINE_MAX_RESULT_MB
    )

    if should_spill:
        spilled = store_spooled_df(
            _REDIS_NAMESPACE,
            query_id,
            optimized_df,
            ttl_seconds=_REJECT_ENGINE_SPOOL_TTL_SECONDS,
        )
        if spilled:
            _dataset_cache.set(query_id, True)  # lightweight marker
            _redis_delete_df(query_id)
            logger.info(
                "Stored query result via parquet spill (query_id=%s, rows=%d, size_mb=%.1f)",
                query_id,
                len(optimized_df),
                df_mb,
            )
            return True
        logger.warning(
            "Parquet spill failed, fallback to dataset cache (query_id=%s, rows=%d, size_mb=%.1f)",
            query_id,
            len(optimized_df),
            df_mb,
        )

    _store_df(query_id, optimized_df)
    return False


def _df_memory_mb(df: pd.DataFrame) -> float:
    from mes_dashboard.core.interactive_memory_guard import df_memory_mb
    return df_memory_mb(df)


def _enforce_interactive_memory_guard(df: pd.DataFrame, *, operation: str, query_id: str) -> None:
    """Prevent expensive cache-based recomputation from pushing worker memory over limit."""
    from mes_dashboard.core.interactive_memory_guard import enforce_dataset_memory_guard
    enforce_dataset_memory_guard(
        df,
        operation=operation,
        query_id=query_id,
        max_input_mb=float(_REJECT_DERIVE_MAX_INPUT_MB),
        max_projected_rss_mb=float(_REJECT_DERIVE_MAX_PROJECTED_RSS_MB),
        working_set_factor=float(_REJECT_DERIVE_WORKING_SET_FACTOR),
    )


def _maybe_collect_after_interactive_compute() -> None:
    from mes_dashboard.core.interactive_memory_guard import maybe_gc_collect
    maybe_gc_collect(force=_REJECT_DERIVE_FORCE_GC)


def _read_sql_with_caller(sql: str, params: Dict[str, Any], caller: str) -> pd.DataFrame:
    try:
        return read_sql_df(sql, params, caller=caller)
    except TypeError as exc:
        if "caller" in str(exc):
            return read_sql_df(sql, params)
        raise


# ============================================================
# Container resolution (reuse query_tool_service resolvers)
# ============================================================


_RESOLVERS = {
    "lot": _resolve_by_lot_id,
    "work_order": _resolve_by_work_order,
    "wafer_lot": _resolve_by_wafer_lot,
}


def resolve_containers(
    input_type: str, values: List[str]
) -> Dict[str, Any]:
    """Dispatch to existing resolver → return container IDs + resolution info."""
    cleaned_values = normalize_input_values(values)
    validation_error = validate_resolution_request(input_type, cleaned_values)
    if validation_error:
        raise ValueError(validation_error)

    resolver = _RESOLVERS.get(input_type)
    if resolver is None:
        raise ValueError(f"不支援的輸入類型: {input_type}")

    result = resolver(cleaned_values)
    if "error" in result:
        raise ValueError(result["error"])

    guard_assessment = assess_resolution_result(result)
    overflow_tokens = guard_assessment.get("expansion_offenders") or []
    overflow_total = bool(guard_assessment.get("over_container_limit"))
    if overflow_tokens or overflow_total:
        logger.warning(
            "Container resolution guardrail overflow (input_type=%s, offenders=%s, resolved=%s, max=%s); continuing with ID decomposition",
            input_type,
            len(overflow_tokens),
            guard_assessment.get("resolved_container_ids"),
            guard_assessment.get("max_container_ids"),
        )
    # strict=False: don't block oversized resolution; continue to downstream ID chunking.
    _ = validate_resolution_result(result, strict=False)

    container_ids = extract_container_ids(result.get("data", []))

    return {
        "container_ids": container_ids,
        "resolution_info": {
            "input_count": result.get("input_count", len(cleaned_values)),
            "resolved_count": len(container_ids),
            "not_found": result.get("not_found", []),
            "expansion_info": result.get("expansion_info", {}),
            "guardrail": {
                "overflow": bool(overflow_tokens or overflow_total),
                "expansion_offenders": overflow_tokens,
                "resolved_container_ids": guard_assessment.get("resolved_container_ids"),
                "max_container_ids": guard_assessment.get("max_container_ids"),
            },
        },
    }


# ============================================================
# Core execution helper (usable by both sync path and RQ worker)
# ============================================================


def _execute_and_spool(
    *,
    query_id: str,
    mode: str,
    base_where: str,
    base_params: Dict[str, Any],
    container_ids: Optional[List[str]] = None,
    progress_callback=None,
) -> Dict[str, Any]:
    """Execute Oracle query and store result in spool/cache.

    This function contains the pure Oracle-execution and result-storage logic,
    extracted from ``execute_primary_query`` so it can be called from both the
    synchronous Gunicorn path and the asynchronous RQ worker path.

    Args:
        query_id: Pre-computed deterministic hash for this query.
        mode: "date_range" or "container".
        base_where: SQL WHERE clause fragment (no leading "WHERE ").
        base_params: Bind parameters dict for the WHERE clause.
        container_ids: List of container IDs (container mode).
        progress_callback: Optional callable(status, progress_str, pct_int) invoked
            after each chunk completes.  May be None.

    Returns:
        partial_failure_meta dict (may be empty).

    Raises:
        RejectPrimaryQueryOverloadError: On RSS guard or result-size overflow.
        Exception: Any Oracle or engine error is propagated to the caller.
    """
    from mes_dashboard.services.batch_query_engine import (
        compute_query_hash,
        decompose_by_ids,
        decompose_by_time_range,
        execute_plan,
        get_batch_progress,
        merge_chunks_to_spool,
        should_decompose_by_ids,
        should_decompose_by_time,
    )
    from mes_dashboard.core.query_spool_store import (
        QUERY_SPOOL_DIR,
        register_spool_file,
    )

    _chunk_counter = [0]
    partial_failure_meta: Dict[str, Any] = {}
    use_engine = False
    engine_chunks: Optional[list] = None
    engine_parallel = 1
    engine_hash: Optional[str] = None

    # Parse start_date/end_date from base_params for decompose check
    start_date = base_params.get("start_date")
    end_date = base_params.get("end_date")

    if mode == "date_range" and start_date and end_date and should_decompose_by_time(start_date, end_date):
        engine_chunks = decompose_by_time_range(
            start_date,
            end_date,
            grain_days=_REJECT_ENGINE_GRAIN_DAYS,
        )
        engine_parallel = _REJECT_ENGINE_PARALLEL
        use_engine = True
        logger.info(
            "Engine activated for date_range: %d chunks (query_id=%s, grain_days=%d, parallel=%d)",
            len(engine_chunks), query_id, _REJECT_ENGINE_GRAIN_DAYS, engine_parallel,
        )
    elif mode == "container" and container_ids and should_decompose_by_ids(container_ids):
        id_batches = decompose_by_ids(container_ids)
        engine_chunks = [{"ids": batch} for batch in id_batches]
        use_engine = True
        logger.info(
            "Engine activated for container IDs: %d batches (query_id=%s)",
            len(engine_chunks), query_id,
        )

    df: pd.DataFrame = pd.DataFrame()
    spool_tmp_path: Optional[str] = None
    spool_row_count: int = 0

    if use_engine and engine_chunks:
        total_chunks = len(engine_chunks)

        def _run_reject_chunk(chunk, max_rows_per_chunk=None):
            chunk_where_parts: List[str] = []
            chunk_params: Dict[str, Any] = {}

            if "chunk_start" in chunk:
                chunk_where_parts.append(
                    "r.TXNDATE >= TO_DATE(:start_date, 'YYYY-MM-DD')"
                    " AND r.TXNDATE < TO_DATE(:end_date, 'YYYY-MM-DD') + 1"
                )
                chunk_params["start_date"] = chunk["chunk_start"]
                chunk_params["end_date"] = chunk["chunk_end"]
            elif "ids" in chunk:
                b = QueryBuilder()
                b.add_in_condition("r.CONTAINERID", chunk["ids"])
                cid_w, cid_p = b.build_where_only()
                cid_c = cid_w.strip()
                if cid_c.upper().startswith("WHERE "):
                    cid_c = cid_c[6:].strip()
                chunk_where_parts.append(cid_c)
                chunk_params.update(cid_p)
            chunk_where = " AND ".join(chunk_where_parts)
            chunk_sql = _prepare_sql(
                _REJECT_PRIMARY_SQL_TEMPLATE,
                where_clause="",
                base_variant="lot",
                base_where=chunk_where,
            )
            if max_rows_per_chunk:
                chunk_sql = (
                    f"SELECT * FROM ({chunk_sql}) WHERE ROWNUM <= {int(max_rows_per_chunk) + 1}"
                )
            chunk_df = _read_sql_with_caller(
                chunk_sql,
                chunk_params,
                "reject_dataset_cache:_execute_and_spool_chunk",
            )
            if chunk_df is None:
                return pd.DataFrame()
            if max_rows_per_chunk and len(chunk_df) == int(max_rows_per_chunk) + 1:
                chunk_df = chunk_df.head(int(max_rows_per_chunk))

            # Report progress after each chunk
            if progress_callback is not None:
                _chunk_counter[0] += 1
                completed = _chunk_counter[0]
                pct = int(completed / total_chunks * 100) if total_chunks > 0 else 0
                try:
                    progress_callback("running", f"{completed}/{total_chunks}", pct)
                except Exception:
                    pass

            return chunk_df

        # Build engine hash from the query_id_input-equivalent fields
        engine_hash_input = {
            "cache_schema_version": _CACHE_SCHEMA_VERSION,
            "mode": mode,
            "start_date": start_date,
            "end_date": end_date,
            "container_values": sorted(container_ids or []),
        }
        engine_hash = compute_query_hash(engine_hash_input)
        redis_clear_batch("reject", engine_hash)
        logger.info(
            "Reject primary SQL selected for engine execution (template=%s, chunks=%d)",
            _REJECT_PRIMARY_SQL_TEMPLATE,
            len(engine_chunks),
        )

        try:
            execute_plan(
                engine_chunks,
                _run_reject_chunk,
                parallel=engine_parallel,
                skip_cached=False,
                query_hash=engine_hash,
                cache_prefix="reject",
                chunk_ttl=_CACHE_TTL,
                max_rows_per_chunk=_REJECT_ENGINE_MAX_ROWS_PER_CHUNK,
            )
            spool_tmp_path, spool_row_count = merge_chunks_to_spool(
                "reject",
                engine_hash,
                spool_dir=QUERY_SPOOL_DIR,
            )
            progress_meta = get_batch_progress("reject", engine_hash) or {}
            progress_partial = parse_partial_failure_meta(progress_meta)
            if progress_partial:
                partial_failure_meta = progress_partial
        finally:
            redis_clear_batch("reject", engine_hash)

        if spool_tmp_path is not None:
            spool_registered = register_spool_file(
                _REDIS_NAMESPACE,
                query_id,
                spool_tmp_path,
                spool_row_count,
                ttl_seconds=_REJECT_ENGINE_SPOOL_TTL_SECONDS,
            )
            if spool_registered:
                df = load_spooled_df(_REDIS_NAMESPACE, query_id) or pd.DataFrame()
            else:
                from pathlib import Path as _Path
                _p = _Path(spool_tmp_path)
                if _p.exists():
                    try:
                        df = pd.read_parquet(str(_p), engine="pyarrow")
                    except Exception:
                        df = pd.DataFrame()
    else:
        # Direct path (short query, no engine overhead)
        logger.info(
            "Reject primary SQL selected for direct execution (template=%s)",
            _REJECT_PRIMARY_SQL_TEMPLATE,
        )
        sql = _prepare_sql(
            _REJECT_PRIMARY_SQL_TEMPLATE,
            where_clause="",
            base_variant="lot",
            base_where=base_where,
        )
        df = _read_sql_with_caller(
            sql,
            base_params,
            "reject_dataset_cache:_execute_and_spool_direct",
        )
        if df is None:
            df = pd.DataFrame()
        # Report 100% for direct path
        if progress_callback is not None:
            try:
                progress_callback("running", "1/1", 100)
            except Exception:
                pass

    # Store result
    if not df.empty:
        stored_via_spool = _store_query_result(query_id, df)
        if partial_failure_meta.get("has_partial_failure"):
            flag_ttl = (
                _REJECT_ENGINE_SPOOL_TTL_SECONDS if stored_via_spool else _CACHE_TTL
            )
            _store_partial_failure_flag(
                query_id,
                partial_failure_meta.get("failed_chunk_count", 0),
                partial_failure_meta.get("failed_ranges"),
                flag_ttl,
            )
            logger.warning(
                "reject partial failure (query_id=%s): failed_ranges=%s",
                query_id, partial_failure_meta.get("failed_ranges"),
            )
        else:
            _clear_partial_failure_flag(query_id)

    return partial_failure_meta


# ============================================================
# Primary query
# ============================================================


def execute_primary_query(
    *,
    mode: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    container_input_type: Optional[str] = None,
    container_values: Optional[List[str]] = None,
    include_excluded_scrap: bool = False,
    exclude_material_scrap: bool = True,
    exclude_pb_diode: bool = True,
    build_response: bool = True,
) -> Dict[str, Any]:
    """Execute Oracle query → cache DataFrame → return structured result."""

    # ---- Build base_where + params for the primary filter ----
    base_where_parts: List[str] = []
    base_params: Dict[str, Any] = {}
    resolution_info: Optional[Dict[str, Any]] = None
    container_ids: List[str] = []  # populated in container mode

    if mode == "date_range":
        if not start_date or not end_date:
            raise ValueError("date_range mode 需要 start_date 和 end_date")
        _validate_range(start_date, end_date)
        base_where_parts.append(
            "r.TXNDATE >= TO_DATE(:start_date, 'YYYY-MM-DD')"
            " AND r.TXNDATE < TO_DATE(:end_date, 'YYYY-MM-DD') + 1"
        )
        base_params["start_date"] = start_date
        base_params["end_date"] = end_date

    elif mode == "container":
        if not container_values:
            raise ValueError("container mode 需要至少一個容器值")
        resolved = resolve_containers(
            container_input_type or "lot", container_values
        )
        resolution_info = resolved["resolution_info"]
        container_ids = resolved["container_ids"]
        if not container_ids:
            raise ValueError("未找到任何對應的容器")

        builder = QueryBuilder()
        builder.add_in_condition("r.CONTAINERID", container_ids)
        cid_where, cid_params = builder.build_where_only()
        # build_where_only returns "WHERE ..." — strip "WHERE " prefix
        cid_condition = cid_where.strip()
        if cid_condition.upper().startswith("WHERE "):
            cid_condition = cid_condition[6:].strip()
        base_where_parts.append(cid_condition)
        base_params.update(cid_params)

    else:
        raise ValueError(f"不支援的查詢模式: {mode}")

    base_where = " AND ".join(base_where_parts)

    # ---- Build policy meta (for response only, NOT for SQL) ----
    _, _, meta = _build_where_clause(
        include_excluded_scrap=include_excluded_scrap,
        exclude_material_scrap=exclude_material_scrap,
        exclude_pb_diode=exclude_pb_diode,
    )

    # ---- Compute query_id from base params only (policy filters applied in-memory) ----
    query_id_input = {
        "cache_schema_version": _CACHE_SCHEMA_VERSION,
        "mode": mode,
        "start_date": start_date,
        "end_date": end_date,
        "container_input_type": container_input_type,
        "container_values": sorted(container_values or []),
    }
    query_id = _make_query_id(query_id_input)

    def _build_response_from_spool() -> Dict[str, Any]:
        cached_partial_meta = _load_partial_failure_flag(query_id)
        response_meta = dict(meta)
        if cached_partial_meta:
            response_meta.update(cached_partial_meta)

        result = apply_view(
            query_id=query_id,
            page=1,
            per_page=50,
            include_excluded_scrap=include_excluded_scrap,
            exclude_material_scrap=exclude_material_scrap,
            exclude_pb_diode=exclude_pb_diode,
        )
        if result is None:
            raise RuntimeError(
                f"Stored reject spool unavailable while building response (query_id={query_id})"
            )

        analytics_raw = result.get("analytics_raw") or []
        # Derive trend from DuckDB analytics_raw (pure Python groupby-by-date)
        by_date: Dict[str, Dict[str, int]] = {}
        for _row in analytics_raw:
            _d = _row.get("bucket_date", "")
            if _d not in by_date:
                by_date[_d] = {"MOVEIN_QTY": 0, "REJECT_TOTAL_QTY": 0, "DEFECT_QTY": 0}
            by_date[_d]["MOVEIN_QTY"] += _row.get("MOVEIN_QTY", 0)
            by_date[_d]["REJECT_TOTAL_QTY"] += _row.get("REJECT_TOTAL_QTY", 0)
            by_date[_d]["DEFECT_QTY"] += _row.get("DEFECT_QTY", 0)
        trend_items = []
        for _date_str in sorted(by_date.keys()):
            _vals = by_date[_date_str]
            _movein = _vals["MOVEIN_QTY"]
            _reject = _vals["REJECT_TOTAL_QTY"]
            _defect = _vals["DEFECT_QTY"]
            trend_items.append({
                "bucket_date": _date_str,
                "MOVEIN_QTY": _movein,
                "REJECT_TOTAL_QTY": _reject,
                "DEFECT_QTY": _defect,
                "REJECT_RATE_PCT": round((_reject / _movein * 100) if _movein else 0, 4),
                "DEFECT_RATE_PCT": round((_defect / _movein * 100) if _movein else 0, 4),
            })

        response: Dict[str, Any] = {
            "query_id": query_id,
            "analytics_raw": analytics_raw,
            "summary": result.get("summary") or {},
            "trend": {
                "items": trend_items,
                "granularity": "day",
            },
            "detail": result.get("detail") or {
                "items": [],
                "pagination": {"page": 1, "perPage": 50, "total": 0, "totalPages": 0},
            },
            "available_filters": result.get("available_filters") or {},
            "meta": response_meta,
        }
        if resolution_info is not None:
            response["resolution_info"] = resolution_info
        return response

    # ---- Check cache first ----
    if _has_cached_df(query_id):
        logger.info("Dataset cache hit for query_id=%s", query_id)
        return _build_response_from_spool()

    lock_owner = f"{os.getpid()}:{uuid.uuid4().hex}"
    has_query_lock = False
    _slot_owner: Optional[str] = None
    _slot_acquired = False
    try:
        has_query_lock = _acquire_query_lock(query_id, lock_owner)
        if not has_query_lock:
            logger.info("Reject query in-flight, waiting for existing run (query_id=%s)", query_id)
            in_flight_ready = _wait_for_inflight_query_result(query_id)
            if in_flight_ready:
                logger.info("Reject query reused completed in-flight result (query_id=%s)", query_id)
                return _build_response_from_spool()
            has_query_lock = _acquire_query_lock(query_id, lock_owner)
            if not has_query_lock:
                raise RejectPrimaryQueryOverloadError(
                    "同條件查詢正在執行中，請稍後重試",
                    code="SERVICE_UNAVAILABLE",
                    retry_after=5,
                )

        if _has_cached_df(query_id):
            logger.info("Dataset cache hit after lock for query_id=%s", query_id)
            return _build_response_from_spool()

        # ---- Execute Oracle query (NO policy filters — cache unfiltered) ----
        logger.info("Dataset cache miss for query_id=%s, querying Oracle", query_id)

        # Acquire global concurrency slot (fail-open: proceeds if Redis unavailable)
        _slot_owner = f"sync:{os.getpid()}:{lock_owner}"
        _slot_acquired = acquire_heavy_query_slot(_slot_owner)

        # Decide whether to route through BatchQueryEngine
        from mes_dashboard.services.batch_query_engine import (
            MergeChunksMaxRowsExceeded,
            compute_query_hash,
            decompose_by_ids,
            decompose_by_time_range,
            execute_plan,
            get_batch_progress,
            merge_chunks_to_spool,
            should_decompose_by_ids,
            should_decompose_by_time,
        )
        from mes_dashboard.core.query_spool_store import (
            QUERY_SPOOL_DIR,
            register_spool_file,
        )

        use_engine = False
        engine_chunks: Optional[list] = None
        engine_parallel = 1
        engine_hash: Optional[str] = None
        partial_failure_meta: Dict[str, Any] = {}

        if mode == "date_range" and should_decompose_by_time(start_date, end_date):
            engine_chunks = decompose_by_time_range(
                start_date,
                end_date,
                grain_days=_REJECT_ENGINE_GRAIN_DAYS,
            )
            engine_parallel = _REJECT_ENGINE_PARALLEL
            use_engine = True
            logger.info(
                "Engine activated for date_range: %d chunks (query_id=%s, grain_days=%d, parallel=%d)",
                len(engine_chunks), query_id, _REJECT_ENGINE_GRAIN_DAYS, engine_parallel,
            )
        elif mode == "container" and should_decompose_by_ids(container_ids):
            id_batches = decompose_by_ids(container_ids)
            engine_chunks = [{"ids": batch} for batch in id_batches]
            use_engine = True
            logger.info(
                "Engine activated for container IDs: %d batches (query_id=%s)",
                len(engine_chunks), query_id,
            )

        stored_via_spool = False
        spool_ready_for_response = False

        if use_engine and engine_chunks:
            # --- Engine path ---
            engine_hash = compute_query_hash(query_id_input)
            redis_clear_batch("reject", engine_hash)
            logger.info(
                "Reject primary SQL selected for engine execution (template=%s, chunks=%d)",
                _REJECT_PRIMARY_SQL_TEMPLATE,
                len(engine_chunks),
            )

            def _run_reject_chunk(chunk, max_rows_per_chunk=None):
                """Execute one reject chunk via dedicated primary SQL."""
                chunk_where_parts: List[str] = []
                chunk_params: Dict[str, Any] = {}

                if "chunk_start" in chunk:
                    # Time-range chunk
                    chunk_where_parts.append(
                        "r.TXNDATE >= TO_DATE(:start_date, 'YYYY-MM-DD')"
                        " AND r.TXNDATE < TO_DATE(:end_date, 'YYYY-MM-DD') + 1"
                    )
                    chunk_params["start_date"] = chunk["chunk_start"]
                    chunk_params["end_date"] = chunk["chunk_end"]
                elif "ids" in chunk:
                    # ID-batch chunk
                    b = QueryBuilder()
                    b.add_in_condition("r.CONTAINERID", chunk["ids"])
                    cid_w, cid_p = b.build_where_only()
                    cid_c = cid_w.strip()
                    if cid_c.upper().startswith("WHERE "):
                        cid_c = cid_c[6:].strip()
                    chunk_where_parts.append(cid_c)
                    chunk_params.update(cid_p)

                chunk_where = " AND ".join(chunk_where_parts)
                chunk_sql = _prepare_sql(
                    _REJECT_PRIMARY_SQL_TEMPLATE,
                    where_clause="",
                    base_variant="lot",
                    base_where=chunk_where,
                )
                if max_rows_per_chunk:
                    chunk_sql = (
                        f"SELECT * FROM ({chunk_sql}) WHERE ROWNUM <= {int(max_rows_per_chunk) + 1}"
                    )
                chunk_df = _read_sql_with_caller(
                    chunk_sql,
                    chunk_params,
                    "reject_dataset_cache:execute_primary_query_chunk",
                )
                if chunk_df is None:
                    return pd.DataFrame()
                if max_rows_per_chunk and len(chunk_df) == int(max_rows_per_chunk) + 1:
                    logger.warning(
                        "Reject chunk hit max_rows_per_chunk limit (max=%d), truncating to %d rows",
                        int(max_rows_per_chunk),
                        int(max_rows_per_chunk),
                    )
                    chunk_df = chunk_df.head(int(max_rows_per_chunk))
                return chunk_df

            try:
                execute_plan(
                    engine_chunks,
                    _run_reject_chunk,
                    parallel=engine_parallel,
                    skip_cached=False,
                    query_hash=engine_hash,
                    cache_prefix="reject",
                    chunk_ttl=_CACHE_TTL,
                    max_rows_per_chunk=_REJECT_ENGINE_MAX_ROWS_PER_CHUNK,
                )
                spool_tmp_path, spool_row_count = merge_chunks_to_spool(
                    "reject",
                    engine_hash,
                    spool_dir=QUERY_SPOOL_DIR,
                )
                # 4.6: read progress BEFORE redis_clear_batch
                progress_meta = get_batch_progress("reject", engine_hash) or {}
                progress_partial = parse_partial_failure_meta(progress_meta)
                if progress_partial:
                    partial_failure_meta = progress_partial
            finally:
                redis_clear_batch("reject", engine_hash)

            # 4.5: Register streamed spool file and load df for response
            if spool_tmp_path is not None:
                spool_registered = register_spool_file(
                    _REDIS_NAMESPACE,
                    query_id,
                    spool_tmp_path,
                    spool_row_count,
                    ttl_seconds=_REJECT_ENGINE_SPOOL_TTL_SECONDS,
                )
                if spool_registered:
                    _dataset_cache.set(query_id, True)
                    stored_via_spool = True
                    spool_ready_for_response = True
                    df = pd.DataFrame()
                else:
                    # Fallback: spool_tmp_path still exists if register_spool_file did not move it
                    from pathlib import Path as _Path
                    _p = _Path(spool_tmp_path)
                    if _p.exists():
                        try:
                            df = pd.read_parquet(str(_p), engine="pyarrow")
                        except Exception:
                            df = pd.DataFrame()
                    else:
                        df = pd.DataFrame()
            else:
                df = pd.DataFrame()
        else:
            # --- Direct path (short query, no engine overhead) ---
            logger.info(
                "Reject primary SQL selected for direct execution (template=%s)",
                _REJECT_PRIMARY_SQL_TEMPLATE,
            )
            sql = _prepare_sql(
                _REJECT_PRIMARY_SQL_TEMPLATE,
                where_clause="",
                base_variant="lot",
                base_where=base_where,
            )
            df = _read_sql_with_caller(
                sql,
                base_params,
                "reject_dataset_cache:execute_primary_query_direct",
            )
            if df is None:
                df = pd.DataFrame()

        # ---- Cache unfiltered, return filtered ----
        if partial_failure_meta:
            meta.update(partial_failure_meta)

        if not stored_via_spool and not df.empty:
            stored_via_spool = _store_query_result(query_id, df)
            spool_ready_for_response = bool(stored_via_spool)

        if partial_failure_meta.get("has_partial_failure"):
            flag_ttl = (
                _REJECT_ENGINE_SPOOL_TTL_SECONDS if stored_via_spool else _CACHE_TTL
            )
            _store_partial_failure_flag(
                query_id,
                partial_failure_meta.get("failed_chunk_count", 0),
                partial_failure_meta.get("failed_ranges"),
                flag_ttl,
            )
            logger.warning(
                "reject partial failure (query_id=%s): failed_ranges=%s",
                query_id, partial_failure_meta.get("failed_ranges"),
            )
        else:
            _clear_partial_failure_flag(query_id)

        if not build_response:
            response: Dict[str, Any] = {"query_id": query_id, "meta": dict(meta)}
            if resolution_info is not None:
                response["resolution_info"] = resolution_info
            return response

        return _build_response_from_spool()
    finally:
        if _slot_acquired and _slot_owner:
            release_heavy_query_slot(_slot_owner)
        if has_query_lock:
            _release_query_lock(query_id, lock_owner)


def ensure_dataset_loaded() -> Dict[str, Any]:
    """Ensure the default reject dataset exists in cache."""
    end_date = date.today()
    start_date = end_date - timedelta(days=_WARMUP_DAYS - 1)
    start_date_str = start_date.strftime("%Y-%m-%d")
    end_date_str = end_date.strftime("%Y-%m-%d")

    query_id_input = {
        "cache_schema_version": _CACHE_SCHEMA_VERSION,
        "mode": "date_range",
        "start_date": start_date_str,
        "end_date": end_date_str,
        "container_input_type": None,
        "container_values": [],
    }
    query_id = _make_query_id(query_id_input)
    if _has_cached_df(query_id):
        return {
            "query_id": query_id,
            "cache_hit": True,
            "start_date": start_date_str,
            "end_date": end_date_str,
        }

    result = execute_primary_query(
        mode="date_range",
        start_date=start_date_str,
        end_date=end_date_str,
        include_excluded_scrap=False,
        exclude_material_scrap=True,
        exclude_pb_diode=True,
    )
    return {
        "query_id": result.get("query_id", query_id),
        "cache_hit": False,
        "start_date": start_date_str,
        "end_date": end_date_str,
    }


def _apply_policy_filters(
    df: pd.DataFrame,
    *,
    include_excluded_scrap: bool = False,
    exclude_material_scrap: bool = True,
    exclude_pb_diode: bool = True,
) -> pd.DataFrame:
    """Apply policy toggle filters in-memory (pandas).

    Mirrors the SQL-level policy from _build_where_clause but operates
    on the cached DataFrame so that toggling filters doesn't require
    a new Oracle round-trip.
    """
    if df is None or df.empty:
        return df

    mask = pd.Series(True, index=df.index)

    # ---- Material scrap exclusion ----
    if exclude_material_scrap and "SCRAP_OBJECTTYPE" in df.columns:
        obj_type = df["SCRAP_OBJECTTYPE"].fillna("").str.strip().str.upper()
        mask &= obj_type != "MATERIAL"

    # ---- PB diode exclusion ----
    if exclude_pb_diode and "PRODUCTLINENAME" in df.columns:
        mask &= ~df["PRODUCTLINENAME"].fillna("").str.match(r"(?i)^PB_")

    # ---- Scrap reason exclusion policy ----
    if not include_excluded_scrap:
        from mes_dashboard.services.scrap_reason_exclusion_cache import (
            get_excluded_reasons,
        )

        excluded = get_excluded_reasons()
        if excluded and "LOSSREASON_CODE" in df.columns:
            code_upper = df["LOSSREASON_CODE"].fillna("").str.strip().str.upper()
            mask &= ~code_upper.isin(excluded)
        if excluded and "LOSSREASONNAME" in df.columns:
            name_upper = df["LOSSREASONNAME"].fillna("").str.strip().str.upper()
            mask &= ~name_upper.isin(excluded)

        # Only keep reasons matching ^[0-9]{3}_ pattern
        if "LOSSREASONNAME" in df.columns:
            name_trimmed = df["LOSSREASONNAME"].fillna("").str.strip().str.upper()
            mask &= name_trimmed.str.match(r"^[0-9]{3}_")
            # Exclude XXX_ and ZZZ_ prefixes
            mask &= ~name_trimmed.str.match(r"^(XXX|ZZZ)_")

    return df[mask]


# ============================================================
# View (supplementary + interactive filtering on cache)
# ============================================================


def apply_view(
    *,
    query_id: str,
    packages: Optional[List[str]] = None,
    workcenter_groups: Optional[List[str]] = None,
    reasons: Optional[List[str]] = None,
    metric_filter: str = "all",
    trend_dates: Optional[List[str]] = None,
    detail_reason: Optional[str] = None,
    pareto_dimension: Optional[str] = None,
    pareto_values: Optional[List[str]] = None,
    pareto_selections: Optional[Dict[str, List[str]]] = None,
    page: int = 1,
    per_page: int = 50,
    include_excluded_scrap: bool = False,
    exclude_material_scrap: bool = True,
    exclude_pb_diode: bool = True,
) -> Optional[Dict[str, Any]]:
    """Read cache → apply filters → return derived data. Returns None if expired."""
    from mes_dashboard.services.reject_cache_sql_runtime import (
        try_compute_view_from_spool,
    )

    sql_result, sql_meta = try_compute_view_from_spool(
        query_id=query_id,
        namespace=_REDIS_NAMESPACE,
        packages=packages,
        workcenter_groups=workcenter_groups,
        reasons=reasons,
        metric_filter=metric_filter,
        trend_dates=trend_dates,
        detail_reason=detail_reason,
        pareto_dimension=pareto_dimension,
        pareto_values=pareto_values,
        pareto_selections=pareto_selections,
        page=page,
        per_page=per_page,
        include_excluded_scrap=include_excluded_scrap,
        exclude_material_scrap=exclude_material_scrap,
        exclude_pb_diode=exclude_pb_diode,
        dim_to_column=_DIM_TO_DF_COLUMN,
    )
    if sql_result is not None:
        logger.info(
            "Reject view served by cache-sql (query_id=%s, runtime=%s, source=%s, detail_total=%s, analytics_rows=%s, latency_s=%s)",
            query_id,
            sql_meta.get("view_runtime"),
            sql_meta.get("view_runtime_path"),
            (sql_result.get("detail", {}).get("pagination", {}) or {}).get("total", 0),
            len(sql_result.get("analytics_raw", []) or []),
            sql_meta.get("view_sql_latency_s"),
        )
        return sql_result
    return None


def _apply_supplementary_filters(
    df: pd.DataFrame,
    *,
    packages: Optional[List[str]] = None,
    workcenter_groups: Optional[List[str]] = None,
    reasons: Optional[List[str]] = None,
    metric_filter: str = "all",
) -> pd.DataFrame:
    """Apply supplementary filters via pandas boolean indexing."""
    if df is None or df.empty:
        return df

    mask = pd.Series(True, index=df.index)

    if packages:
        pkg_set = {p.strip() for p in packages if p.strip()}
        if pkg_set and "PRODUCTLINENAME" in df.columns:
            mask &= df["PRODUCTLINENAME"].isin(pkg_set)

    if workcenter_groups:
        wc_groups = [g.strip() for g in workcenter_groups if g.strip()]
        if wc_groups:
            specs = get_specs_for_groups(wc_groups)
            if specs and "SPECNAME" in df.columns:
                spec_set = {s.upper() for s in specs}
                mask &= df["SPECNAME"].str.strip().str.upper().isin(spec_set)
            elif "WORKCENTER_GROUP" in df.columns:
                mask &= df["WORKCENTER_GROUP"].isin(wc_groups)

    if reasons and "LOSSREASONNAME" in df.columns:
        reason_set = {r.strip() for r in reasons if r.strip()}
        if reason_set:
            mask &= df["LOSSREASONNAME"].str.strip().isin(reason_set)

    if metric_filter == "reject" and "REJECT_TOTAL_QTY" in df.columns:
        mask &= df["REJECT_TOTAL_QTY"] > 0
    elif metric_filter == "defect" and "DEFECT_QTY" in df.columns:
        mask &= df["DEFECT_QTY"] > 0

    return df[mask]


def _normalize_pareto_values(values: Optional[List[str]]) -> List[str]:
    normalized: List[str] = []
    seen = set()
    for value in values or []:
        item = _normalize_text(value)
        if not item or item in seen:
            continue
        seen.add(item)
        normalized.append(item)
    return normalized


def _apply_pareto_selection_filter(
    df: pd.DataFrame,
    *,
    pareto_dimension: Optional[str] = None,
    pareto_values: Optional[List[str]] = None,
    pareto_selections: Optional[Dict[str, List[str]]] = None,
) -> pd.DataFrame:
    """Apply Pareto multi-select filters on detail/export datasets."""
    if df is None or df.empty:
        return df

    normalized_selections = _normalize_pareto_selections(pareto_selections)
    if normalized_selections:
        filtered = df
        for dim in _PARETO_DIMENSIONS:
            selected_values = normalized_selections.get(dim)
            if not selected_values:
                continue
            dim_col = _DIM_TO_DF_COLUMN.get(dim)
            if not dim_col:
                raise ValueError(f"不支援的 pareto_dimension: {dim}")
            if dim_col not in filtered.columns:
                return filtered.iloc[0:0]
            value_set = set(selected_values)
            normalized_dimension_values = filtered[dim_col].map(
                lambda value: _normalize_text(value) or "(未知)"
            )
            filtered = filtered[normalized_dimension_values.isin(value_set)]
            if filtered.empty:
                return filtered
        return filtered

    normalized_values = _normalize_pareto_values(pareto_values)
    if not normalized_values:
        return df

    dimension = _normalize_text(pareto_dimension).lower() or "reason"
    dim_col = _DIM_TO_DF_COLUMN.get(dimension)
    if not dim_col:
        raise ValueError(f"不支援的 pareto_dimension: {pareto_dimension}")
    if dim_col not in df.columns:
        return df.iloc[0:0]

    value_set = set(normalized_values)
    normalized_dimension_values = df[dim_col].map(
        lambda value: _normalize_text(value) or "(未知)"
    )
    return df[normalized_dimension_values.isin(value_set)]


def _paginate_detail(
    df: pd.DataFrame, *, page: int = 1, per_page: int = 50
) -> dict:
    """Sort + paginate LOT-level rows."""
    if df is None or df.empty:
        return {
            "items": [],
            "pagination": {
                "page": 1,
                "perPage": per_page,
                "total": 0,
                "totalPages": 1,
            },
        }

    page = max(int(page), 1)
    per_page = min(max(int(per_page), 1), 200)

    # Sort
    sort_cols = []
    sort_asc = []
    for col, asc in [
        ("TXN_DAY", False),
        ("WORKCENTERSEQUENCE_GROUP", True),
        ("WORKCENTERNAME", True),
        ("REJECT_TOTAL_QTY", False),
        ("CONTAINERNAME", True),
    ]:
        if col in df.columns:
            sort_cols.append(col)
            sort_asc.append(asc)

    if sort_cols:
        sorted_df = df.sort_values(sort_cols, ascending=sort_asc)
    else:
        sorted_df = df

    total = len(sorted_df)
    total_pages = max((total + per_page - 1) // per_page, 1)
    offset = (page - 1) * per_page
    page_df = sorted_df.iloc[offset : offset + per_page]

    items = []
    for _, row in page_df.iterrows():
        items.append(
            {
                "TXN_TIME": _to_datetime_str(row.get("TXN_TIME")),
                "TXN_DAY": _to_date_str(row.get("TXN_DAY")),
                "TXN_MONTH": _normalize_text(row.get("TXN_MONTH")),
                "WORKCENTER_GROUP": _normalize_text(row.get("WORKCENTER_GROUP")),
                "WORKCENTERNAME": _normalize_text(row.get("WORKCENTERNAME")),
                "SPECNAME": _normalize_text(row.get("SPECNAME")),
                "EQUIPMENTNAME": _normalize_text(row.get("EQUIPMENTNAME")),
                "WORKFLOWNAME": _normalize_text(row.get("WORKFLOWNAME")),
                "PRODUCTLINENAME": _normalize_text(row.get("PRODUCTLINENAME")),
                "PJ_TYPE": _normalize_text(row.get("PJ_TYPE")),
                "CONTAINERNAME": _normalize_text(row.get("CONTAINERNAME")),
                "PJ_FUNCTION": _normalize_text(row.get("PJ_FUNCTION")),
                "PRODUCTNAME": _normalize_text(row.get("PRODUCTNAME")),
                "LOSSREASONNAME": _normalize_text(row.get("LOSSREASONNAME")),
                "LOSSREASON_CODE": _normalize_text(row.get("LOSSREASON_CODE")),
                "REJECTCOMMENT": _normalize_text(row.get("REJECTCOMMENT")),
                "MOVEIN_QTY": _as_int(row.get("MOVEIN_QTY")),
                "REJECT_QTY": _as_int(row.get("REJECT_QTY")),
                "STANDBY_QTY": _as_int(row.get("STANDBY_QTY")),
                "QTYTOPROCESS_QTY": _as_int(row.get("QTYTOPROCESS_QTY")),
                "INPROCESS_QTY": _as_int(row.get("INPROCESS_QTY")),
                "PROCESSED_QTY": _as_int(row.get("PROCESSED_QTY")),
                "REJECT_TOTAL_QTY": _as_int(row.get("REJECT_TOTAL_QTY")),
                "DEFECT_QTY": _as_int(row.get("DEFECT_QTY")),
                "REJECT_RATE_PCT": round(
                    _as_float(row.get("REJECT_RATE_PCT")), 4
                ),
                "DEFECT_RATE_PCT": round(
                    _as_float(row.get("DEFECT_RATE_PCT")), 4
                ),
                "REJECT_SHARE_PCT": round(
                    _as_float(row.get("REJECT_SHARE_PCT")), 4
                ),
                "AFFECTED_WORKORDER_COUNT": _as_int(
                    row.get("AFFECTED_WORKORDER_COUNT")
                ),
            }
        )

    return {
        "items": items,
        "pagination": {
            "page": page,
            "perPage": per_page,
            "total": total,
            "totalPages": total_pages,
        },
    }


def _extract_available_filters(df: pd.DataFrame) -> dict:
    """Extract distinct packages/reasons/WC groups from the full cache DF."""
    return {
        "workcenter_groups": _extract_workcenter_group_options(df),
        "packages": _extract_distinct_text_values(df, "PRODUCTLINENAME"),
        "reasons": _extract_distinct_text_values(df, "LOSSREASONNAME"),
    }


# ============================================================
# Dimension Pareto from cache
# ============================================================

# Dimension → DF column mapping (matches _DIMENSION_COLUMN_MAP in reject_history_service)
_DIM_TO_DF_COLUMN = {
    "reason": "LOSSREASONNAME",
    "package": "PRODUCTLINENAME",
    "type": "PJ_TYPE",
}
_PARETO_DIMENSIONS = tuple(_DIM_TO_DF_COLUMN.keys())
_PARETO_TOP20_DIMENSIONS = {"type"}
_PARETO_GUARD_REQUIRED_COLUMNS = (
    tuple(_DIM_TO_DF_COLUMN.values())
    + ("MOVEIN_QTY", "REJECT_TOTAL_QTY", "DEFECT_QTY", "AFFECTED_LOT_COUNT", "TXN_DAY")
)


def _project_pareto_guard_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Project and compact frame for Pareto memory guard and aggregation.

    Batch/Dimension Pareto only need a subset of columns. Converting high-cardinality
    text dimensions to category reduces deep-memory significantly for large ranges.
    """
    if df is None or df.empty:
        return df

    required_cols = [col for col in _PARETO_GUARD_REQUIRED_COLUMNS if col in df.columns]
    projected = df.loc[:, required_cols].copy()
    for dim_col in _DIM_TO_DF_COLUMN.values():
        if dim_col not in projected.columns:
            continue
        series = projected[dim_col]
        if str(series.dtype) == "object":
            projected[dim_col] = series.fillna("(未知)").astype("category")
    return projected


def _normalize_metric_mode(metric_mode: str) -> str:
    mode = _normalize_text(metric_mode).lower()
    if mode not in {"reject_total", "defect"}:
        raise ValueError("Invalid metric_mode, supported: reject_total, defect")
    return mode


def _normalize_pareto_scope(pareto_scope: str) -> str:
    scope = _normalize_text(pareto_scope).lower() or "top80"
    if scope not in {"top80", "all"}:
        raise ValueError("Invalid pareto_scope, supported: top80, all")
    return scope


def _normalize_pareto_display_scope(display_scope: str) -> str:
    scope = _normalize_text(display_scope).lower() or "all"
    if scope not in {"all", "top20"}:
        raise ValueError("Invalid pareto_display_scope, supported: all, top20")
    return scope


def _normalize_pareto_selections(
    pareto_selections: Optional[Dict[str, List[str]]],
) -> Dict[str, List[str]]:
    normalized: Dict[str, List[str]] = {}
    for dim, values in (pareto_selections or {}).items():
        dim_key = _normalize_text(dim).lower()
        if not dim_key:
            continue
        if dim_key not in _DIM_TO_DF_COLUMN:
            raise ValueError(f"不支援的 pareto_dimension: {dim}")
        normalized_values = _normalize_pareto_values(values)
        if normalized_values:
            normalized[dim_key] = normalized_values
    return normalized


def _build_dimension_pareto_items(
    df: pd.DataFrame,
    *,
    dim_col: str,
    metric_mode: str,
    pareto_scope: str,
) -> List[Dict[str, Any]]:
    if df is None or df.empty:
        return []
    if dim_col not in df.columns:
        return []

    metric_col = "DEFECT_QTY" if metric_mode == "defect" else "REJECT_TOTAL_QTY"
    if metric_col not in df.columns:
        return []

    agg_dict = {}
    for col in ["MOVEIN_QTY", "REJECT_TOTAL_QTY", "DEFECT_QTY", "AFFECTED_LOT_COUNT"]:
        if col in df.columns:
            agg_dict[col] = (col, "sum")

    grouped = df.groupby(dim_col, sort=False, observed=True).agg(**agg_dict).reset_index()
    if grouped.empty:
        return []

    if "AFFECTED_LOT_COUNT" not in grouped.columns:
        grouped["AFFECTED_LOT_COUNT"] = 0

    grouped["METRIC_VALUE"] = grouped[metric_col].fillna(0)
    grouped = grouped[grouped["METRIC_VALUE"] > 0].sort_values(
        "METRIC_VALUE", ascending=False
    )
    if grouped.empty:
        return []

    total_metric = grouped["METRIC_VALUE"].sum()
    grouped["PCT"] = (grouped["METRIC_VALUE"] / total_metric * 100).round(4)
    grouped["CUM_PCT"] = grouped["PCT"].cumsum().round(4)

    items: List[Dict[str, Any]] = []
    for _, row in grouped.iterrows():
        items.append({
            "reason": _normalize_text(row.get(dim_col)) or "(未知)",
            "metric_value": _as_float(row.get("METRIC_VALUE")),
            "MOVEIN_QTY": _as_int(row.get("MOVEIN_QTY")),
            "REJECT_TOTAL_QTY": _as_int(row.get("REJECT_TOTAL_QTY")),
            "DEFECT_QTY": _as_int(row.get("DEFECT_QTY")),
            "count": _as_int(row.get("AFFECTED_LOT_COUNT")),
            "pct": round(_as_float(row.get("PCT")), 4),
            "cumPct": round(_as_float(row.get("CUM_PCT")), 4),
        })

    if pareto_scope == "top80" and items:
        top_items = [item for item in items if _as_float(item.get("cumPct")) <= 80.0]
        if not top_items:
            top_items = [items[0]]
        return top_items
    return items


def _apply_cross_filter(
    df: pd.DataFrame,
    selections: Dict[str, List[str]],
    exclude_dim: str,
) -> pd.DataFrame:
    if df is None or df.empty or not selections:
        return df

    filtered = df
    for dim in _PARETO_DIMENSIONS:
        if dim == exclude_dim:
            continue
        selected_values = selections.get(dim)
        if not selected_values:
            continue
        dim_col = _DIM_TO_DF_COLUMN.get(dim)
        if not dim_col:
            raise ValueError(f"不支援的 pareto_dimension: {dim}")
        if dim_col not in filtered.columns:
            return filtered.iloc[0:0]
        value_set = set(selected_values)
        normalized_dimension_values = filtered[dim_col].map(
            lambda value: _normalize_text(value) or "(未知)"
        )
        filtered = filtered[normalized_dimension_values.isin(value_set)]
        if filtered.empty:
            return filtered
    return filtered


def compute_dimension_pareto(
    *,
    query_id: str,
    dimension: str = "reason",
    metric_mode: str = "reject_total",
    pareto_scope: str = "top80",
    packages: Optional[List[str]] = None,
    workcenter_groups: Optional[List[str]] = None,
    reasons: Optional[List[str]] = None,
    trend_dates: Optional[List[str]] = None,
    include_excluded_scrap: bool = False,
    exclude_material_scrap: bool = True,
    exclude_pb_diode: bool = True,
) -> Optional[Dict[str, Any]]:
    """Compute dimension pareto from cached DataFrame (no Oracle query).

    Prefers materialized Pareto snapshots when available, falling back to
    legacy DataFrame-based computation on miss/stale/build-failure.
    """
    metric_mode = _normalize_metric_mode(metric_mode)
    pareto_scope = _normalize_pareto_scope(pareto_scope)
    dimension = _normalize_text(dimension).lower() or "reason"
    if dimension not in _DIM_TO_DF_COLUMN:
        raise ValueError(
            f"Invalid dimension, supported: {', '.join(sorted(_DIM_TO_DF_COLUMN.keys()))}"
        )

    # ---- Materialized read-through path ------------------------------------
    from mes_dashboard.services.reject_pareto_materialized import (
        try_materialized_dimension_pareto,
    )

    mat_result, mat_meta = try_materialized_dimension_pareto(
        query_id,
        lambda: load_spooled_df(_REDIS_NAMESPACE, query_id),
        dimension=dimension,
        metric_mode=metric_mode,
        pareto_scope=pareto_scope,
        include_excluded_scrap=include_excluded_scrap,
        exclude_material_scrap=exclude_material_scrap,
        exclude_pb_diode=exclude_pb_diode,
        packages=packages,
        workcenter_groups=workcenter_groups,
        reasons=reasons,
        trend_dates=trend_dates,
    )
    if mat_result is not None:
        mat_result["_pareto_meta"] = mat_meta
        return mat_result

    # ---- Legacy DataFrame-based compute (fallback) -------------------------
    df = load_spooled_df(_REDIS_NAMESPACE, query_id)
    if df is None:
        return None

    try:
        # Keep cache-based pareto behavior aligned with primary/view policy filters.
        df = _apply_policy_filters(
            df,
            include_excluded_scrap=include_excluded_scrap,
            exclude_material_scrap=exclude_material_scrap,
            exclude_pb_diode=exclude_pb_diode,
        )
        if df is None or df.empty:
            return {"items": [], "dimension": dimension, "metric_mode": metric_mode}

        dim_col = _DIM_TO_DF_COLUMN.get(dimension)
        if dim_col not in df.columns:
            return {"items": [], "dimension": dimension, "metric_mode": metric_mode}

        # Apply supplementary filters
        filtered = _apply_supplementary_filters(
            df,
            packages=packages,
            workcenter_groups=workcenter_groups,
            reasons=reasons,
        )
        if filtered is None or filtered.empty:
            return {"items": [], "dimension": dimension, "metric_mode": metric_mode}

        # Apply trend date filter
        if trend_dates and "TXN_DAY" in filtered.columns:
            date_set = set(trend_dates)
            filtered = filtered[
                filtered["TXN_DAY"].apply(lambda d: _to_date_str(d) in date_set)
            ]
            if filtered.empty:
                return {"items": [], "dimension": dimension, "metric_mode": metric_mode}

        filtered = _project_pareto_guard_frame(filtered)
        _enforce_interactive_memory_guard(filtered, operation="柏拉圖查詢", query_id=query_id)

        items = _build_dimension_pareto_items(
            filtered,
            dim_col=dim_col,
            metric_mode=metric_mode,
            pareto_scope=pareto_scope,
        )

        result = {
            "items": items,
            "dimension": dimension,
            "metric_mode": metric_mode,
        }
        if mat_meta:
            result["_pareto_meta"] = mat_meta
        return result
    finally:
        _maybe_collect_after_interactive_compute()


def compute_batch_pareto(
    *,
    query_id: str,
    metric_mode: str = "reject_total",
    pareto_scope: str = "top80",
    pareto_display_scope: str = "all",
    packages: Optional[List[str]] = None,
    workcenter_groups: Optional[List[str]] = None,
    reasons: Optional[List[str]] = None,
    trend_dates: Optional[List[str]] = None,
    pareto_selections: Optional[Dict[str, List[str]]] = None,
    include_excluded_scrap: bool = False,
    exclude_material_scrap: bool = True,
    exclude_pb_diode: bool = True,
) -> Optional[Dict[str, Any]]:
    """Compute all six Pareto dimensions from cached DataFrame (no Oracle query).

    Prefers materialized Pareto snapshots when available, falling back to
    legacy DataFrame-based computation on miss/stale/build-failure.
    """
    metric_mode = _normalize_metric_mode(metric_mode)
    pareto_scope = _normalize_pareto_scope(pareto_scope)
    pareto_display_scope = _normalize_pareto_display_scope(pareto_display_scope)
    normalized_selections = _normalize_pareto_selections(pareto_selections)

    # ---- Materialized read-through path ------------------------------------
    from mes_dashboard.services.reject_pareto_materialized import (
        try_materialized_batch_pareto,
    )

    mat_result, mat_meta = try_materialized_batch_pareto(
        query_id,
        lambda: load_spooled_df(_REDIS_NAMESPACE, query_id),
        metric_mode=metric_mode,
        pareto_scope=pareto_scope,
        pareto_display_scope=pareto_display_scope,
        pareto_selections=normalized_selections,
        include_excluded_scrap=include_excluded_scrap,
        exclude_material_scrap=exclude_material_scrap,
        exclude_pb_diode=exclude_pb_diode,
        packages=packages,
        workcenter_groups=workcenter_groups,
        reasons=reasons,
        trend_dates=trend_dates,
    )
    if mat_result is not None:
        mat_result["_pareto_meta"] = mat_meta
        return mat_result

    # ---- Cache-SQL path (DuckDB over parquet spool) ----------------
    from mes_dashboard.services.reject_cache_sql_runtime import (
        try_compute_batch_pareto_from_spool,
    )

    sql_result, sql_meta = try_compute_batch_pareto_from_spool(
        query_id=query_id,
        namespace=_REDIS_NAMESPACE,
        metric_mode=metric_mode,
        pareto_scope=pareto_scope,
        pareto_display_scope=pareto_display_scope,
        pareto_selections=normalized_selections,
        include_excluded_scrap=include_excluded_scrap,
        exclude_material_scrap=exclude_material_scrap,
        exclude_pb_diode=exclude_pb_diode,
        packages=packages,
        workcenter_groups=workcenter_groups,
        reasons=reasons,
        trend_dates=trend_dates,
        dim_to_column=_DIM_TO_DF_COLUMN,
        top20_dimensions=_PARETO_TOP20_DIMENSIONS,
    )
    if sql_result is not None:
        merged_meta: Dict[str, Any] = {}
        if isinstance(mat_meta, dict):
            merged_meta.update(mat_meta)
        if isinstance(sql_meta, dict):
            merged_meta.update(sql_meta)
        logger.info(
            "Reject batch-pareto served by cache-sql (query_id=%s, runtime=%s, source=%s, latency_s=%s)",
            query_id,
            merged_meta.get("pareto_runtime"),
            merged_meta.get("pareto_runtime_path"),
            merged_meta.get("pareto_sql_latency_s"),
        )
        if merged_meta:
            sql_result["_pareto_meta"] = merged_meta
        return sql_result

    pareto_sql_fallback_reason = _normalize_text(
        (sql_meta or {}).get("pareto_sql_fallback_reason")
    ) or "unknown"
    raise RuntimeError(
        f"cache-sql batch-pareto unavailable (reason={pareto_sql_fallback_reason})"
    )


# ============================================================
# CSV export from cache
# ============================================================


def export_csv_from_cache(
    *,
    query_id: str,
    packages: Optional[List[str]] = None,
    workcenter_groups: Optional[List[str]] = None,
    reasons: Optional[List[str]] = None,
    metric_filter: str = "all",
    trend_dates: Optional[List[str]] = None,
    detail_reason: Optional[str] = None,
    pareto_dimension: Optional[str] = None,
    pareto_values: Optional[List[str]] = None,
    pareto_selections: Optional[Dict[str, List[str]]] = None,
    include_excluded_scrap: bool = False,
    exclude_material_scrap: bool = True,
    exclude_pb_diode: bool = True,
) -> Optional[Iterable[Dict[str, Any]]]:
    """Read cache → apply filters → return list of dicts for CSV export."""
    from mes_dashboard.services.reject_cache_sql_runtime import (
        try_iter_export_rows_from_spool,
    )

    sql_rows, sql_meta = try_iter_export_rows_from_spool(
        query_id=query_id,
        namespace=_REDIS_NAMESPACE,
        packages=packages,
        workcenter_groups=workcenter_groups,
        reasons=reasons,
        metric_filter=metric_filter,
        trend_dates=trend_dates,
        detail_reason=detail_reason,
        pareto_dimension=pareto_dimension,
        pareto_values=pareto_values,
        pareto_selections=pareto_selections,
        include_excluded_scrap=include_excluded_scrap,
        exclude_material_scrap=exclude_material_scrap,
        exclude_pb_diode=exclude_pb_diode,
        dim_to_column=_DIM_TO_DF_COLUMN,
    )
    if sql_rows is not None:
        logger.info(
            "Reject export-cached served by cache-sql stream (query_id=%s, runtime=%s, source=%s, sql_latency_s=%s)",
            query_id,
            sql_meta.get("export_runtime"),
            sql_meta.get("export_runtime_path"),
            sql_meta.get("export_sql_query_latency_s"),
        )
        return sql_rows

    export_sql_fallback_reason = _normalize_text(
        (sql_meta or {}).get("export_sql_fallback_reason")
    ) or "unknown"
    raise RuntimeError(
        f"cache-sql export unavailable (reason={export_sql_fallback_reason})"
    )
