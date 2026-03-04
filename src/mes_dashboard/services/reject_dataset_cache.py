# -*- coding: utf-8 -*-
"""Two-phase reject-history dataset cache.

Primary query (POST /query) → Oracle → cache full LOT-level DataFrame.
Supplementary view (GET /view) → read cache → pandas filter/derive.

Cache layers:
  L1: ProcessLevelCache (in-process, per-worker)
  L2: Redis (cross-worker, parquet bytes encoded as base64 string)
"""

from __future__ import annotations

import gc
import hashlib
import json
import logging
import os
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd

from mes_dashboard.core.cache import ProcessLevelCache, register_process_cache
from mes_dashboard.core.database import read_sql_df_slow as read_sql_df
from mes_dashboard.core.feature_flags import resolve_bool_flag
from mes_dashboard.core.query_spool_store import (
    clear_spooled_df,
    load_spooled_df,
    store_spooled_df,
)
from mes_dashboard.core.redis_client import get_key, get_redis_client
from mes_dashboard.core.redis_df_store import (
    redis_clear_batch,
    redis_load_df,
    redis_store_df,
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

_CACHE_TTL = 900  # 15 minutes
_CACHE_MAX_SIZE = 8
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
_REJECT_CACHE_SQL_FALLBACK_LEGACY_ENABLED = resolve_bool_flag(
    "REJECT_CACHE_SQL_FALLBACK_LEGACY_ENABLED",
    default=True,
)
_REJECT_CACHE_SQL_BATCH_PARETO_FALLBACK_LEGACY_ENABLED = resolve_bool_flag(
    "REJECT_CACHE_SQL_BATCH_PARETO_FALLBACK_LEGACY_ENABLED",
    default=True,
)
_REJECT_CACHE_SQL_VIEW_FALLBACK_LEGACY_ENABLED = resolve_bool_flag(
    "REJECT_CACHE_SQL_VIEW_FALLBACK_LEGACY_ENABLED",
    default=True,
)
_REJECT_CACHE_SQL_EXPORT_FALLBACK_LEGACY_ENABLED = resolve_bool_flag(
    "REJECT_CACHE_SQL_EXPORT_FALLBACK_LEGACY_ENABLED",
    default=True,
)

_dataset_cache = ProcessLevelCache(ttl_seconds=_CACHE_TTL, max_size=_CACHE_MAX_SIZE)
register_process_cache("reject_dataset", _dataset_cache, "Reject Dataset (L1, 15min)")


def _allow_legacy_fallback(flag_enabled: bool) -> bool:
    return bool(_REJECT_CACHE_SQL_FALLBACK_LEGACY_ENABLED and flag_enabled)


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


def _redis_store_df(query_id: str, df: pd.DataFrame) -> None:
    redis_store_df(f"{_REDIS_NAMESPACE}:{query_id}", df, ttl=_CACHE_TTL)


def _redis_load_df(query_id: str) -> Optional[pd.DataFrame]:
    return redis_load_df(f"{_REDIS_NAMESPACE}:{query_id}")


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
    mapping = {
        "has_partial_failure": "True",
        "failed_chunk_count": str(max(int(failed_count), 0)),
        "failed_ranges": json.dumps(failed_ranges or [], ensure_ascii=False, default=str),
    }
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
    if not raw:
        return {}

    has_partial = str(raw.get("has_partial_failure", "")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if not has_partial:
        return {}

    failed_count_raw = raw.get("failed_chunk_count", raw.get("failed", "0"))
    try:
        failed_count = max(int(str(failed_count_raw)), 0)
    except Exception:
        failed_count = 0

    failed_ranges: List[Dict[str, str]] = []
    raw_ranges = raw.get("failed_ranges", "[]")
    try:
        parsed_ranges = json.loads(raw_ranges) if raw_ranges else []
        if isinstance(parsed_ranges, list):
            for item in parsed_ranges:
                if not isinstance(item, dict):
                    continue
                start = str(item.get("start", "")).strip()
                end = str(item.get("end", "")).strip()
                if start and end:
                    failed_ranges.append({"start": start, "end": end})
    except Exception:
        failed_ranges = []

    return {
        "has_partial_failure": True,
        "failed_chunk_count": failed_count,
        "failed_ranges": failed_ranges,
    }


def _clear_partial_failure_flag(query_id: str) -> None:
    client = get_redis_client()
    if client is None:
        return
    try:
        client.delete(get_key(_partial_failure_key(query_id)))
    except Exception:
        return


# ============================================================
# Cache read (L1 → L2 → None)
# ============================================================


def _get_cached_df(query_id: str) -> Optional[pd.DataFrame]:
    """Read cache: L1 hit → L2 hit → spool fallback."""
    df = _dataset_cache.get(query_id)
    if df is not None:
        return df

    df = _redis_load_df(query_id)
    if df is not None:
        _dataset_cache.set(query_id, df)
        return df

    df = load_spooled_df(_REDIS_NAMESPACE, query_id)
    if df is not None:
        # Keep large payload out of L1 cache to avoid worker RSS spikes.
        df_mb = df.memory_usage(deep=True).sum() / (1024 * 1024)
        if df_mb <= min(float(_REJECT_ENGINE_MAX_RESULT_MB), 32.0):
            _dataset_cache.set(query_id, df)
        return df
    return None


def _store_df(query_id: str, df: pd.DataFrame) -> None:
    """Write to L1 and L2."""
    _dataset_cache.set(query_id, df)
    _redis_store_df(query_id, df)
    clear_spooled_df(_REDIS_NAMESPACE, query_id)


def _store_query_result(query_id: str, df: pd.DataFrame) -> bool:
    """Store result and return True when persisted via parquet spill."""
    if df is None or df.empty:
        return False

    df_mb = df.memory_usage(deep=True).sum() / (1024 * 1024)
    should_spill = _REJECT_ENGINE_SPILL_ENABLED and (
        len(df) >= _REJECT_ENGINE_MAX_TOTAL_ROWS or df_mb >= _REJECT_ENGINE_MAX_RESULT_MB
    )

    if should_spill:
        spilled = store_spooled_df(
            _REDIS_NAMESPACE,
            query_id,
            df,
            ttl_seconds=_REJECT_ENGINE_SPOOL_TTL_SECONDS,
        )
        if spilled:
            _dataset_cache.invalidate(query_id)
            _redis_delete_df(query_id)
            logger.info(
                "Stored query result via parquet spill (query_id=%s, rows=%d, size_mb=%.1f)",
                query_id,
                len(df),
                df_mb,
            )
            return True
        logger.warning(
            "Parquet spill failed, fallback to dataset cache (query_id=%s, rows=%d, size_mb=%.1f)",
            query_id,
            len(df),
            df_mb,
        )

    _store_df(query_id, df)
    return False


def _df_memory_mb(df: pd.DataFrame) -> float:
    if df is None or df.empty:
        return 0.0
    try:
        return float(df.memory_usage(deep=True).sum()) / (1024 * 1024)
    except Exception:
        return 0.0


def _process_rss_mb() -> Optional[float]:
    try:
        import psutil  # local import: optional runtime dependency
    except Exception:
        return None
    try:
        process = psutil.Process(os.getpid())
        return float(process.memory_info().rss) / (1024 * 1024)
    except Exception:
        return None


def _enforce_interactive_memory_guard(df: pd.DataFrame, *, operation: str, query_id: str) -> None:
    """Prevent expensive cache-based recomputation from pushing worker memory over limit."""
    if df is None or df.empty:
        return

    df_mb = _df_memory_mb(df)
    if df_mb > float(_REJECT_DERIVE_MAX_INPUT_MB):
        logger.warning(
            "Reject %s due to dataset size guard (query_id=%s, df_mb=%.1f, limit_mb=%d)",
            operation,
            query_id,
            df_mb,
            _REJECT_DERIVE_MAX_INPUT_MB,
        )
        raise MemoryError(
            f"{operation}資料量約 {df_mb:.1f} MB，超過 {_REJECT_DERIVE_MAX_INPUT_MB} MB 上限，請縮小篩選條件後重試"
        )

    rss_mb = _process_rss_mb()
    if rss_mb is None:
        return

    projected_rss_mb = rss_mb + (df_mb * float(_REJECT_DERIVE_WORKING_SET_FACTOR))
    if projected_rss_mb > float(_REJECT_DERIVE_MAX_PROJECTED_RSS_MB):
        logger.warning(
            "Reject %s due to projected RSS guard (query_id=%s, rss_mb=%.1f, df_mb=%.1f, factor=%.2f, projected_mb=%.1f, limit_mb=%d)",
            operation,
            query_id,
            rss_mb,
            df_mb,
            _REJECT_DERIVE_WORKING_SET_FACTOR,
            projected_rss_mb,
            _REJECT_DERIVE_MAX_PROJECTED_RSS_MB,
        )
        raise MemoryError(
            (
                f"目前服務記憶體負載較高（RSS {rss_mb:.1f} MB），暫停{operation}計算以保護系統，"
                "請稍後再試或縮小篩選條件"
            )
        )


def _maybe_collect_after_interactive_compute() -> None:
    if not _REJECT_DERIVE_FORCE_GC:
        return
    try:
        gc.collect()
    except Exception:
        return


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
) -> Dict[str, Any]:
    """Execute Oracle query → cache DataFrame → return structured result."""

    # ---- Build base_where + params for the primary filter ----
    base_where_parts: List[str] = []
    base_params: Dict[str, Any] = {}
    resolution_info: Optional[Dict[str, Any]] = None
    workflow_filter: str = ""  # empty = use default date-based filter
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

        # Build workflow_filter for the workflow_lookup CTE (uses r0 alias).
        # Reuses the same bind param names (p0, p1, ...) already in base_params.
        wf_builder = QueryBuilder()
        wf_builder.add_in_condition("r0.CONTAINERID", container_ids)
        wf_where, _ = wf_builder.build_where_only()
        wf_condition = wf_where.strip()
        if wf_condition.upper().startswith("WHERE "):
            wf_condition = wf_condition[6:].strip()
        workflow_filter = wf_condition

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

    # ---- Check cache first ----
    cached_df = _get_cached_df(query_id)
    if cached_df is not None:
        logger.info("Dataset cache hit for query_id=%s", query_id)
        cached_partial_meta = _load_partial_failure_flag(query_id)
        if cached_partial_meta:
            meta.update(cached_partial_meta)
        filtered = _apply_policy_filters(
            cached_df,
            include_excluded_scrap=include_excluded_scrap,
            exclude_material_scrap=exclude_material_scrap,
            exclude_pb_diode=exclude_pb_diode,
        )
        return _build_primary_response(
            query_id, filtered, meta, resolution_info
        )

    # ---- Execute Oracle query (NO policy filters — cache unfiltered) ----
    logger.info("Dataset cache miss for query_id=%s, querying Oracle", query_id)

    # Decide whether to route through BatchQueryEngine
    from mes_dashboard.services.batch_query_engine import (
        decompose_by_time_range,
        decompose_by_ids,
        execute_plan,
        merge_chunks,
        get_batch_progress,
        compute_query_hash,
        should_decompose_by_time,
        should_decompose_by_ids,
        BATCH_QUERY_TIME_THRESHOLD_DAYS,
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
            chunk_wf_filter = ""

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
                # Workflow filter for container mode
                wfb = QueryBuilder()
                wfb.add_in_condition("r0.CONTAINERID", chunk["ids"])
                wf_w, _ = wfb.build_where_only()
                wf_c = wf_w.strip()
                if wf_c.upper().startswith("WHERE "):
                    wf_c = wf_c[6:].strip()
                chunk_wf_filter = wf_c

            chunk_where = " AND ".join(chunk_where_parts)
            chunk_sql = _prepare_sql(
                _REJECT_PRIMARY_SQL_TEMPLATE,
                where_clause="",
                base_variant="lot",
                base_where=chunk_where,
                workflow_filter=chunk_wf_filter,
            )
            if max_rows_per_chunk:
                logger.debug(
                    "Reject chunk execution ignores max_rows_per_chunk on primary SQL path "
                    "(max_rows_per_chunk=%s)",
                    max_rows_per_chunk,
                )
            chunk_df = read_sql_df(chunk_sql, chunk_params)
            if chunk_df is None:
                return pd.DataFrame()
            return chunk_df

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
        df = merge_chunks(
            "reject",
            engine_hash,
        )
        progress_meta = get_batch_progress("reject", engine_hash) or {}
        has_partial_failure = str(
            progress_meta.get("has_partial_failure", "")
        ).strip().lower() in {"1", "true", "yes", "on"}
        if has_partial_failure:
            failed_raw = progress_meta.get("failed", "0")
            try:
                failed_count = max(int(str(failed_raw)), 0)
            except Exception:
                failed_count = 0

            failed_ranges: List[Dict[str, str]] = []
            raw_failed_ranges = progress_meta.get("failed_ranges", "")
            if raw_failed_ranges:
                try:
                    parsed = json.loads(raw_failed_ranges)
                except Exception:
                    parsed = []
                if isinstance(parsed, list):
                    for item in parsed:
                        if not isinstance(item, dict):
                            continue
                        start = str(item.get("start", "")).strip()
                        end = str(item.get("end", "")).strip()
                        if start and end:
                            failed_ranges.append({"start": start, "end": end})

            partial_failure_meta = {
                "has_partial_failure": True,
                "failed_chunk_count": failed_count,
                "failed_ranges": failed_ranges,
            }
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
            workflow_filter=workflow_filter,
        )
        df = read_sql_df(sql, base_params)
        if df is None:
            df = pd.DataFrame()

    # ---- Cache unfiltered, return filtered ----
    if partial_failure_meta:
        meta.update(partial_failure_meta)

    stored_via_spool = False
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
        else:
            _clear_partial_failure_flag(query_id)
    if engine_hash:
        redis_clear_batch("reject", engine_hash)

    filtered = _apply_policy_filters(
        df,
        include_excluded_scrap=include_excluded_scrap,
        exclude_material_scrap=exclude_material_scrap,
        exclude_pb_diode=exclude_pb_diode,
    )
    return _build_primary_response(query_id, filtered, meta, resolution_info)


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


def _build_primary_response(
    query_id: str,
    df: pd.DataFrame,
    meta: Dict[str, Any],
    resolution_info: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Build the full response from a LOT-level DataFrame."""
    analytics_raw = _derive_analytics_raw(df)
    summary = _derive_summary_from_analytics(analytics_raw)
    trend_items = _derive_trend_from_analytics(analytics_raw)
    first_page = _paginate_detail(df, page=1, per_page=50)
    available = _extract_available_filters(df)

    result: Dict[str, Any] = {
        "query_id": query_id,
        "analytics_raw": analytics_raw,
        "summary": summary,
        "trend": {"items": trend_items, "granularity": "day"},
        "detail": first_page,
        "available_filters": available,
        "meta": meta,
    }
    if resolution_info is not None:
        result["resolution_info"] = resolution_info
    return result


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

    view_sql_fallback_reason = _normalize_text(
        (sql_meta or {}).get("view_sql_fallback_reason")
    ) or "unknown"
    if not _allow_legacy_fallback(_REJECT_CACHE_SQL_VIEW_FALLBACK_LEGACY_ENABLED):
        raise RuntimeError(
            f"cache-sql view unavailable (reason={view_sql_fallback_reason})"
        )
    logger.info(
        "Reject view fallback to legacy path (query_id=%s, reason=%s)",
        query_id,
        view_sql_fallback_reason,
    )

    df = _get_cached_df(query_id)
    if df is None:
        return None

    _enforce_interactive_memory_guard(df, operation="視圖查詢", query_id=query_id)
    try:
        # Apply policy filters first (cache stores unfiltered data)
        df = _apply_policy_filters(
            df,
            include_excluded_scrap=include_excluded_scrap,
            exclude_material_scrap=exclude_material_scrap,
            exclude_pb_diode=exclude_pb_diode,
        )

        filtered = _apply_supplementary_filters(
            df,
            packages=packages,
            workcenter_groups=workcenter_groups,
            reasons=reasons,
            metric_filter=metric_filter,
        )

        # Analytics always uses full date range (supplementary-filtered only).
        # The frontend derives trend from analytics_raw and filters Pareto by
        # selectedTrendDates client-side.
        analytics_raw = _derive_analytics_raw(filtered)
        summary = _derive_summary_from_analytics(analytics_raw)

        # Detail list: additionally filter by detail_reason and trend_dates
        detail_df = filtered
        if trend_dates:
            date_set = set(trend_dates)
            detail_df = detail_df[
                detail_df["TXN_DAY"].apply(lambda d: _to_date_str(d) in date_set)
            ]
        if detail_reason:
            detail_df = detail_df[
                detail_df["LOSSREASONNAME"].str.strip() == detail_reason.strip()
            ]
        detail_df = _apply_pareto_selection_filter(
            detail_df,
            pareto_dimension=pareto_dimension,
            pareto_values=pareto_values,
            pareto_selections=pareto_selections,
        )

        detail_page = _paginate_detail(detail_df, page=page, per_page=per_page)

        return {
            "analytics_raw": analytics_raw,
            "summary": summary,
            "detail": detail_page,
        }
    finally:
        _maybe_collect_after_interactive_compute()


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


# ============================================================
# Derivation helpers
# ============================================================


def _derive_analytics_raw(df: pd.DataFrame) -> list:
    """GROUP BY (TXN_DAY, LOSSREASONNAME) → per date×reason rows."""
    if df is None or df.empty:
        return []

    agg_cols = {
        "MOVEIN_QTY": ("MOVEIN_QTY", "sum"),
        "REJECT_TOTAL_QTY": ("REJECT_TOTAL_QTY", "sum"),
        "DEFECT_QTY": ("DEFECT_QTY", "sum"),
    }
    # Add optional columns if present
    if "AFFECTED_WORKORDER_COUNT" in df.columns:
        agg_cols["AFFECTED_WORKORDER_COUNT"] = ("AFFECTED_WORKORDER_COUNT", "sum")

    grouped = (
        df.groupby(["TXN_DAY", "LOSSREASONNAME"], sort=True)
        .agg(**agg_cols)
        .reset_index()
    )

    # Count distinct CONTAINERIDs per group for AFFECTED_LOT_COUNT
    if "CONTAINERID" in df.columns:
        lot_counts = (
            df.groupby(["TXN_DAY", "LOSSREASONNAME"])["CONTAINERID"]
            .nunique()
            .reset_index()
            .rename(columns={"CONTAINERID": "AFFECTED_LOT_COUNT"})
        )
        grouped = grouped.merge(
            lot_counts, on=["TXN_DAY", "LOSSREASONNAME"], how="left"
        )
    else:
        grouped["AFFECTED_LOT_COUNT"] = 0

    items = []
    for _, row in grouped.iterrows():
        items.append(
            {
                "bucket_date": _to_date_str(row["TXN_DAY"]),
                "reason": _normalize_text(row["LOSSREASONNAME"]) or "(未填寫)",
                "MOVEIN_QTY": _as_int(row.get("MOVEIN_QTY")),
                "REJECT_TOTAL_QTY": _as_int(row.get("REJECT_TOTAL_QTY")),
                "DEFECT_QTY": _as_int(row.get("DEFECT_QTY")),
                "AFFECTED_LOT_COUNT": _as_int(row.get("AFFECTED_LOT_COUNT")),
                "AFFECTED_WORKORDER_COUNT": _as_int(
                    row.get("AFFECTED_WORKORDER_COUNT")
                ),
            }
        )
    return items


def _derive_summary_from_analytics(analytics_raw: list) -> dict:
    """Aggregate analytics_raw into a single summary dict."""
    movein = sum(r.get("MOVEIN_QTY", 0) for r in analytics_raw)
    reject_total = sum(r.get("REJECT_TOTAL_QTY", 0) for r in analytics_raw)
    defect = sum(r.get("DEFECT_QTY", 0) for r in analytics_raw)
    affected_lot = sum(r.get("AFFECTED_LOT_COUNT", 0) for r in analytics_raw)
    affected_wo = sum(r.get("AFFECTED_WORKORDER_COUNT", 0) for r in analytics_raw)

    total_scrap = reject_total + defect
    return {
        "MOVEIN_QTY": movein,
        "REJECT_TOTAL_QTY": reject_total,
        "DEFECT_QTY": defect,
        "REJECT_RATE_PCT": round((reject_total / movein * 100) if movein else 0, 4),
        "DEFECT_RATE_PCT": round((defect / movein * 100) if movein else 0, 4),
        "REJECT_SHARE_PCT": round(
            (reject_total / total_scrap * 100) if total_scrap else 0, 4
        ),
        "AFFECTED_LOT_COUNT": affected_lot,
        "AFFECTED_WORKORDER_COUNT": affected_wo,
    }


def _derive_trend_from_analytics(analytics_raw: list) -> list:
    """Group analytics_raw by date into trend items."""
    by_date: Dict[str, Dict[str, int]] = {}
    for row in analytics_raw:
        d = row.get("bucket_date", "")
        if d not in by_date:
            by_date[d] = {"MOVEIN_QTY": 0, "REJECT_TOTAL_QTY": 0, "DEFECT_QTY": 0}
        by_date[d]["MOVEIN_QTY"] += row.get("MOVEIN_QTY", 0)
        by_date[d]["REJECT_TOTAL_QTY"] += row.get("REJECT_TOTAL_QTY", 0)
        by_date[d]["DEFECT_QTY"] += row.get("DEFECT_QTY", 0)

    items = []
    for date_str in sorted(by_date.keys()):
        vals = by_date[date_str]
        movein = vals["MOVEIN_QTY"]
        reject = vals["REJECT_TOTAL_QTY"]
        defect = vals["DEFECT_QTY"]
        items.append(
            {
                "bucket_date": date_str,
                "MOVEIN_QTY": movein,
                "REJECT_TOTAL_QTY": reject,
                "DEFECT_QTY": defect,
                "REJECT_RATE_PCT": round(
                    (reject / movein * 100) if movein else 0, 4
                ),
                "DEFECT_RATE_PCT": round(
                    (defect / movein * 100) if movein else 0, 4
                ),
            }
        )
    return items


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
                "WORKFLOWNAME": _normalize_text(row.get("WORKFLOWNAME")),
                "EQUIPMENTNAME": _normalize_text(row.get("EQUIPMENTNAME")),
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
    "workflow": "WORKFLOWNAME",
    "workcenter": "WORKCENTER_GROUP",
    "equipment": "PRIMARY_EQUIPMENTNAME",
}
_PARETO_DIMENSIONS = tuple(_DIM_TO_DF_COLUMN.keys())
_PARETO_TOP20_DIMENSIONS = {"type", "workflow", "equipment"}
_PARETO_GUARD_REQUIRED_COLUMNS = (
    tuple(_DIM_TO_DF_COLUMN.values())
    + ("MOVEIN_QTY", "REJECT_TOTAL_QTY", "DEFECT_QTY", "CONTAINERID", "TXN_DAY")
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
    for col in ["MOVEIN_QTY", "REJECT_TOTAL_QTY", "DEFECT_QTY"]:
        if col in df.columns:
            agg_dict[col] = (col, "sum")

    grouped = df.groupby(dim_col, sort=False).agg(**agg_dict).reset_index()
    if grouped.empty:
        return []

    if "CONTAINERID" in df.columns:
        lot_counts = (
            df.groupby(dim_col)["CONTAINERID"]
            .nunique()
            .reset_index()
            .rename(columns={"CONTAINERID": "AFFECTED_LOT_COUNT"})
        )
        grouped = grouped.merge(lot_counts, on=dim_col, how="left")
    else:
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
        lambda: _get_cached_df(query_id),
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
    df = _get_cached_df(query_id)
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
        lambda: _get_cached_df(query_id),
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

    # ---- Cache-SQL fallback path (DuckDB over parquet spool) ----------------
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
    if not _allow_legacy_fallback(_REJECT_CACHE_SQL_BATCH_PARETO_FALLBACK_LEGACY_ENABLED):
        raise RuntimeError(
            f"cache-sql batch-pareto unavailable (reason={pareto_sql_fallback_reason})"
        )
    logger.info(
        "Reject batch-pareto fallback to legacy path (query_id=%s, reason=%s)",
        query_id,
        pareto_sql_fallback_reason,
    )

    # ---- Legacy DataFrame-based compute (fallback) -------------------------
    df = _get_cached_df(query_id)
    if df is None:
        return None

    try:
        df = _apply_policy_filters(
            df,
            include_excluded_scrap=include_excluded_scrap,
            exclude_material_scrap=exclude_material_scrap,
            exclude_pb_diode=exclude_pb_diode,
        )
        if df is None or df.empty:
            return {
                "dimensions": {
                    dim: {"items": [], "dimension": dim, "metric_mode": metric_mode}
                    for dim in _PARETO_DIMENSIONS
                }
            }

        filtered = _apply_supplementary_filters(
            df,
            packages=packages,
            workcenter_groups=workcenter_groups,
            reasons=reasons,
        )
        if filtered is None or filtered.empty:
            return {
                "dimensions": {
                    dim: {"items": [], "dimension": dim, "metric_mode": metric_mode}
                    for dim in _PARETO_DIMENSIONS
                }
            }

        if trend_dates and "TXN_DAY" in filtered.columns:
            date_set = set(trend_dates)
            filtered = filtered[
                filtered["TXN_DAY"].apply(lambda d: _to_date_str(d) in date_set)
            ]
            if filtered.empty:
                return {
                    "dimensions": {
                        dim: {"items": [], "dimension": dim, "metric_mode": metric_mode}
                        for dim in _PARETO_DIMENSIONS
                    }
                }

        filtered = _project_pareto_guard_frame(filtered)
        _enforce_interactive_memory_guard(filtered, operation="柏拉圖批次查詢", query_id=query_id)

        dimensions: Dict[str, Dict[str, Any]] = {}
        for dim in _PARETO_DIMENSIONS:
            dim_col = _DIM_TO_DF_COLUMN.get(dim)
            dim_df = _apply_cross_filter(filtered, normalized_selections, exclude_dim=dim)
            items = _build_dimension_pareto_items(
                dim_df,
                dim_col=dim_col,
                metric_mode=metric_mode,
                pareto_scope=pareto_scope,
            )
            if pareto_display_scope == "top20" and dim in _PARETO_TOP20_DIMENSIONS:
                items = items[:20]
            dimensions[dim] = {
                "items": items,
                "dimension": dim,
                "metric_mode": metric_mode,
            }

        result = {
            "dimensions": dimensions,
            "metric_mode": metric_mode,
            "pareto_scope": pareto_scope,
            "pareto_display_scope": pareto_display_scope,
        }
        merged_meta: Dict[str, Any] = {}
        if isinstance(mat_meta, dict):
            merged_meta.update(mat_meta)
        if isinstance(sql_meta, dict):
            merged_meta.update(sql_meta)
        if merged_meta:
            result["_pareto_meta"] = merged_meta
        logger.info(
            "Reject batch-pareto served by legacy fallback (query_id=%s, reason=%s)",
            query_id,
            pareto_sql_fallback_reason,
        )
        return result
    finally:
        _maybe_collect_after_interactive_compute()


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
    if not _allow_legacy_fallback(_REJECT_CACHE_SQL_EXPORT_FALLBACK_LEGACY_ENABLED):
        raise RuntimeError(
            f"cache-sql export unavailable (reason={export_sql_fallback_reason})"
        )
    logger.info(
        "Reject export-cached fallback to legacy path (query_id=%s, reason=%s)",
        query_id,
        export_sql_fallback_reason,
    )

    df = _get_cached_df(query_id)
    if df is None:
        return None

    _enforce_interactive_memory_guard(df, operation="CSV匯出", query_id=query_id)
    try:
        df = _apply_policy_filters(
            df,
            include_excluded_scrap=include_excluded_scrap,
            exclude_material_scrap=exclude_material_scrap,
            exclude_pb_diode=exclude_pb_diode,
        )

        filtered = _apply_supplementary_filters(
            df,
            packages=packages,
            workcenter_groups=workcenter_groups,
            reasons=reasons,
            metric_filter=metric_filter,
        )

        if trend_dates:
            date_set = set(trend_dates)
            filtered = filtered[
                filtered["TXN_DAY"].apply(lambda d: _to_date_str(d) in date_set)
            ]
        if detail_reason and "LOSSREASONNAME" in filtered.columns:
            filtered = filtered[
                filtered["LOSSREASONNAME"].str.strip() == detail_reason.strip()
            ]
        filtered = _apply_pareto_selection_filter(
            filtered,
            pareto_dimension=pareto_dimension,
            pareto_values=pareto_values,
            pareto_selections=pareto_selections,
        )

        rows: List[Dict[str, Any]] = []
        for _, row in filtered.iterrows():
            rows.append(
                {
                    "LOT": _normalize_text(row.get("CONTAINERNAME")),
                    "WORKCENTER": _normalize_text(row.get("WORKCENTERNAME")),
                    "WORKCENTER_GROUP": _normalize_text(row.get("WORKCENTER_GROUP")),
                    "Package": _normalize_text(row.get("PRODUCTLINENAME")),
                    "FUNCTION": _normalize_text(row.get("PJ_FUNCTION")),
                    "TYPE": _normalize_text(row.get("PJ_TYPE")),
                    "WORKFLOW": _normalize_text(row.get("WORKFLOWNAME")),
                    "PRODUCT": _normalize_text(row.get("PRODUCTNAME")),
                    "原因": _normalize_text(row.get("LOSSREASONNAME")),
                    "EQUIPMENT": _normalize_text(row.get("EQUIPMENTNAME")),
                    "COMMENT": _normalize_text(row.get("REJECTCOMMENT")),
                    "SPEC": _normalize_text(row.get("SPECNAME")),
                    "REJECT_QTY": _as_int(row.get("REJECT_QTY")),
                    "STANDBY_QTY": _as_int(row.get("STANDBY_QTY")),
                    "QTYTOPROCESS_QTY": _as_int(row.get("QTYTOPROCESS_QTY")),
                    "INPROCESS_QTY": _as_int(row.get("INPROCESS_QTY")),
                    "PROCESSED_QTY": _as_int(row.get("PROCESSED_QTY")),
                    "扣帳報廢量": _as_int(row.get("REJECT_TOTAL_QTY")),
                    "不扣帳報廢量": _as_int(row.get("DEFECT_QTY")),
                    "MOVEIN_QTY": _as_int(row.get("MOVEIN_QTY")),
                    "報廢時間": _to_datetime_str(row.get("TXN_TIME")),
                    "日期": _to_date_str(row.get("TXN_DAY")),
                }
            )
        logger.info(
            "Reject export-cached served by legacy fallback (query_id=%s, rows=%d, reason=%s)",
            query_id,
            len(rows),
            export_sql_fallback_reason,
        )
        return rows
    finally:
        _maybe_collect_after_interactive_compute()
