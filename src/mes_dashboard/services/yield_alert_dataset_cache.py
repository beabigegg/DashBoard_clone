# -*- coding: utf-8 -*-
"""Two-phase dataset cache for Yield Alert Center.

Primary query (POST /query):
  Date range only -> Oracle -> cache grouped datasets

Supplementary view (GET /view):
  Read cache -> in-memory filtering/aggregation -> return summary/trend/alerts
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import threading
import time
from typing import Any, Optional

import numpy as np
import pandas as pd

from mes_dashboard.core.cache import ProcessLevelCache, register_process_cache
from mes_dashboard.core.database import read_sql_df_slow
from mes_dashboard.core.interactive_memory_guard import enforce_dataset_memory_guard, maybe_gc_collect
from mes_dashboard.core.query_spool_store import get_spool_file_path, store_spooled_df
from mes_dashboard.core.redis_client import REDIS_ENABLED, get_redis_client
from mes_dashboard.core.redis_df_store import redis_load_df, redis_store_df
from mes_dashboard.services.yield_alert_service import (
    DEFAULT_PAGE_SIZE,
    LINKAGE_WARN_UNMATCHED_RATIO,
    MAX_PAGE_SIZE,
    MAX_QUERY_DAYS,
    VALID_SORT_FIELDS,
    _YIELD_WORKCENTER_GROUP_ORDER,
    _bucket_to_text,
    _build_normalized_exclusion_tokens,
    _compute_reject_linkage,
    _load_excluded_reason_tokens,
    _normalize_process_category,
    _normalize_tokens,
    _normalize_yield_department_group,
    _risk_level,
    _safe_float,
    build_canonical_key,
    normalize_reason_code,
    validate_date_range,
)

logger = logging.getLogger("mes_dashboard.yield_alert_dataset_cache")

_CACHE_TTL = max(30, int(os.getenv("YIELD_ALERT_CACHE_TTL_SECONDS", "300")))
_CACHE_MAX_SIZE = max(1, int(os.getenv("YIELD_ALERT_DATASET_CACHE_MAX_SIZE", "3")))
_REDIS_NAMESPACE = "yield_alert_dataset"
_CACHE_SCHEMA_VERSION = 4
_SPOOL_NAMESPACE = "yield_alert_dataset"

_VIEW_MAX_INPUT_MB = float(os.getenv("YIELD_ALERT_VIEW_MAX_INPUT_MB", "96"))
_VIEW_MAX_PROJECTED_RSS_MB = float(os.getenv("YIELD_ALERT_VIEW_MAX_PROJECTED_RSS_MB", "1100"))
_VIEW_WORKING_SET_FACTOR = float(os.getenv("YIELD_ALERT_VIEW_WORKING_SET_FACTOR", "2.5"))

_DETAIL_COLUMNS = [
    "DATE_BUCKET",
    "WORKORDER",
    "REASON_RAW",
    "REASON_NAME",
    "DEPARTMENT_NAME",
    "DEPARTMENT_GROUP",
    "PROCESS_CATEGORY",
    "LINE_NAME",
    "PACKAGE_NAME",
    "TYPE_NAME",
    "FUNCTION_NAME",
    "OPERATION_TEXT",
    "REASON_CODE",
    "REASON_RAW_UPPER",
    "REASON_NAME_UPPER",
    "TRANSACTION_QTY",
    "SCRAP_QTY",
]
_LINKAGE_COLUMNS = ["CANONICAL_KEY", "REJECT_TOTAL_QTY"]

_FILTER_COLUMN_MAP = {
    "departments": "DEPARTMENT_GROUP",
    "process_category": "PROCESS_CATEGORY",
    "lines": "LINE_NAME",
    "packages": "PACKAGE_NAME",
    "types": "TYPE_NAME",
    "functions": "FUNCTION_NAME",
}

_TX_DEDUP_COLUMNS = [
    "DATE_BUCKET", "WORKORDER",
    "DEPARTMENT_NAME", "DEPARTMENT_GROUP", "PROCESS_CATEGORY",
    "LINE_NAME", "PACKAGE_NAME", "TYPE_NAME", "FUNCTION_NAME", "OPERATION_TEXT",
]


def _dedup_tx_df(df: pd.DataFrame) -> pd.DataFrame:
    """Collapse the reason dimension to compute accurate TRANSACTION_QTY.

    Uses groupby+sum instead of drop_duplicates so that multiple move
    transactions sharing the same non-reason dimensions are ALL counted,
    even when they map to the same DEPARTMENT_GROUP but originate from
    distinct DEPARTMENT_NAMEs (sub-stations).
    """
    if df.empty:
        return df
    return df.groupby(_TX_DEDUP_COLUMNS, as_index=False)["TRANSACTION_QTY"].sum()


_VALID_GRANULARITIES = frozenset({"day", "week", "month", "year"})
_DEPT_SEQ_MAP: dict[str, int] = {g: i for i, g in enumerate(_YIELD_WORKCENTER_GROUP_ORDER)}

_GRANULARITY_LABEL = {"day": "日", "week": "週", "month": "月", "year": "年"}


def _bucket_date_str(date_val: Any, granularity: str) -> str:
    """Convert a single DATE_BUCKET value to a time-period bucket label (scalar fallback)."""
    try:
        dt = pd.Timestamp(str(date_val)[:10])
    except Exception:
        return str(date_val)[:10]
    if granularity == "week":
        monday = dt - pd.Timedelta(days=dt.weekday())
        return monday.strftime("%Y-%m-%d")
    if granularity == "month":
        return dt.strftime("%Y-%m")
    if granularity == "year":
        return dt.strftime("%Y")
    return dt.strftime("%Y-%m-%d")


def _vectorized_bucket(series: pd.Series, granularity: str) -> pd.Series:
    """Vectorized date bucketing — avoids per-row Python lambda on large DataFrames."""
    if granularity == "day":
        # DATE_BUCKET is already stored as 'YYYY-MM-DD' strings; just normalise
        return series.astype(str).str[:10]
    dt = pd.to_datetime(series.astype(str).str[:10], format="%Y-%m-%d", errors="coerce")
    if granularity == "week":
        return (dt - pd.to_timedelta(dt.dt.dayofweek, unit="D")).dt.strftime("%Y-%m-%d")
    if granularity == "month":
        return dt.dt.strftime("%Y-%m")
    if granularity == "year":
        return dt.dt.strftime("%Y")
    return dt.dt.strftime("%Y-%m-%d")


def _build_heatmap_data(
    *,
    tx_df: pd.DataFrame,
    scrap_df: pd.DataFrame,
    granularity: str,
) -> list[dict[str, Any]]:
    """Return station × date yield% matrix rows from pre-computed tx/scrap DataFrames."""
    if tx_df.empty:
        return []

    # Vectorized date bucketing — avoids per-row Python lambda on large DataFrames
    tx_bucketed = tx_df.assign(DATE_STR=_vectorized_bucket(tx_df["DATE_BUCKET"], granularity))
    tx_grouped = (
        tx_bucketed.groupby(["DATE_STR", "DEPARTMENT_GROUP"], as_index=False)["TRANSACTION_QTY"].sum()
    )

    if scrap_df.empty:
        scrap_grouped = pd.DataFrame(columns=["DATE_STR", "DEPARTMENT_GROUP", "SCRAP_QTY"])
    else:
        scrap_bucketed = scrap_df.assign(DATE_STR=_vectorized_bucket(scrap_df["DATE_BUCKET"], granularity))
        scrap_grouped = (
            scrap_bucketed.groupby(["DATE_STR", "DEPARTMENT_GROUP"], as_index=False)["SCRAP_QTY"].sum()
        )

    merged = tx_grouped.merge(scrap_grouped, on=["DATE_STR", "DEPARTMENT_GROUP"], how="left")
    merged["SCRAP_QTY"] = pd.to_numeric(merged["SCRAP_QTY"], errors="coerce").fillna(0.0)
    merged["TRANSACTION_QTY"] = pd.to_numeric(merged["TRANSACTION_QTY"], errors="coerce").fillna(0.0)

    tx_arr = merged["TRANSACTION_QTY"].to_numpy(dtype=float)
    sc_arr = merged["SCRAP_QTY"].to_numpy(dtype=float)
    depts = merged["DEPARTMENT_GROUP"].tolist()
    dates = merged["DATE_STR"].tolist()

    result: list[dict[str, Any]] = [
        {
            "station": dept,
            "station_seq": _DEPT_SEQ_MAP.get(dept, 999),
            "date": date,
            "transaction_qty": round(float(tx), 4),
            "scrap_qty": round(float(sc), 4),
            "yield_pct": 100.0 if tx <= 0 else round((1 - sc / tx) * 100, 4),
        }
        for dept, date, tx, sc in zip(depts, dates, tx_arr, sc_arr)
    ]
    result.sort(key=lambda x: (_DEPT_SEQ_MAP.get(x["station"], 999), x["date"]))
    return result


def _build_station_summary(
    *,
    tx_df: pd.DataFrame,
    scrap_df: pd.DataFrame,
) -> list[dict[str, Any]]:
    """Return per-station yield summary sorted by yield_pct ascending (worst first)."""
    if tx_df.empty:
        return []

    tx_grouped = tx_df.groupby("DEPARTMENT_GROUP", as_index=False)["TRANSACTION_QTY"].sum()

    if scrap_df.empty:
        scrap_grouped = pd.DataFrame(columns=["DEPARTMENT_GROUP", "SCRAP_QTY"])
    else:
        scrap_grouped = scrap_df.groupby("DEPARTMENT_GROUP", as_index=False)["SCRAP_QTY"].sum()

    merged = tx_grouped.merge(scrap_grouped, on="DEPARTMENT_GROUP", how="left")
    merged["SCRAP_QTY"] = pd.to_numeric(merged["SCRAP_QTY"], errors="coerce").fillna(0.0)
    merged["TRANSACTION_QTY"] = pd.to_numeric(merged["TRANSACTION_QTY"], errors="coerce").fillna(0.0)

    tx_arr = merged["TRANSACTION_QTY"].to_numpy(dtype=float)
    sc_arr = merged["SCRAP_QTY"].to_numpy(dtype=float)

    result: list[dict[str, Any]] = [
        {
            "station": dept,
            "station_seq": _DEPT_SEQ_MAP.get(dept, 999),
            "transaction_qty": round(float(tx), 4),
            "scrap_qty": round(float(sc), 4),
            "yield_pct": 100.0 if tx <= 0 else round((1 - sc / tx) * 100, 4),
        }
        for dept, tx, sc in zip(merged["DEPARTMENT_GROUP"].tolist(), tx_arr, sc_arr)
    ]
    result.sort(key=lambda x: (x["yield_pct"], _DEPT_SEQ_MAP.get(x["station"], 999)))
    return result


def _build_package_summary(
    *,
    tx_df: pd.DataFrame,
    scrap_df: pd.DataFrame,
) -> list[dict[str, Any]]:
    """Return per-package yield summary sorted by scrap_qty descending (worst first)."""
    if tx_df.empty:
        return []

    tx_grouped = tx_df.groupby("PACKAGE_NAME", as_index=False)["TRANSACTION_QTY"].sum()

    if scrap_df.empty:
        scrap_grouped = pd.DataFrame(columns=["PACKAGE_NAME", "SCRAP_QTY"])
    else:
        scrap_grouped = scrap_df.groupby("PACKAGE_NAME", as_index=False)["SCRAP_QTY"].sum()

    merged = tx_grouped.merge(scrap_grouped, on="PACKAGE_NAME", how="left")
    merged["SCRAP_QTY"] = pd.to_numeric(merged["SCRAP_QTY"], errors="coerce").fillna(0.0)
    merged["TRANSACTION_QTY"] = pd.to_numeric(merged["TRANSACTION_QTY"], errors="coerce").fillna(0.0)

    tx_arr = merged["TRANSACTION_QTY"].to_numpy(dtype=float)
    sc_arr = merged["SCRAP_QTY"].to_numpy(dtype=float)

    result: list[dict[str, Any]] = [
        {
            "package": pkg,
            "transaction_qty": round(float(tx), 4),
            "scrap_qty": round(float(sc), 4),
            "yield_pct": 100.0 if tx <= 0 else round((1 - sc / tx) * 100, 4),
        }
        for pkg, tx, sc in zip(merged["PACKAGE_NAME"].tolist(), tx_arr, sc_arr)
    ]
    result.sort(key=lambda x: (-x["scrap_qty"], x["yield_pct"]))
    return result


_dataset_cache = ProcessLevelCache(ttl_seconds=_CACHE_TTL, max_size=_CACHE_MAX_SIZE)
register_process_cache("yield_alert_dataset", _dataset_cache, "Yield Alert Dataset (L1)")


def _make_query_id(params: dict[str, Any]) -> str:
    canonical = json.dumps(params, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def _detail_cache_key(query_id: str) -> str:
    return f"{_REDIS_NAMESPACE}:{query_id}:detail"


def _linkage_cache_key(query_id: str) -> str:
    return f"{_REDIS_NAMESPACE}:{query_id}:linkage"


def _prepare_detail_df(df: Optional[pd.DataFrame]) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=_DETAIL_COLUMNS)

    prepared = df.copy()
    prepared["DATE_BUCKET"] = prepared["DATE_BUCKET"].map(_bucket_to_text)
    prepared["WORKORDER"] = prepared["WIP_ENTITY_NAME"].fillna("(NA)").astype(str).str.strip()
    prepared["REASON_RAW"] = prepared["REASON_RAW"].fillna("(UNMAPPED)").astype(str).str.strip()
    prepared["REASON_NAME"] = prepared["REASON_NAME"].fillna("(未填寫)").astype(str).str.strip()
    prepared["DEPARTMENT_NAME"] = prepared["DEPARTMENT_NAME"].fillna("(NA)").astype(str).str.strip()
    prepared["DEPARTMENT_GROUP"] = prepared["DEPARTMENT_NAME"].map(_normalize_yield_department_group)
    prepared["PROCESS_CATEGORY"] = prepared["DEPARTMENT_GROUP"].map(_normalize_process_category)
    prepared["LINE_NAME"] = prepared["LINE_NAME"].fillna("(NA)").astype(str).str.strip()
    prepared["PACKAGE_NAME"] = prepared["PACKAGE_NAME"].fillna("(NA)").astype(str).str.strip()
    prepared["TYPE_NAME"] = prepared["TYPE_NAME"].fillna("(NA)").astype(str).str.strip()
    prepared["FUNCTION_NAME"] = prepared["FUNCTION_NAME"].fillna("(NA)").astype(str).str.strip()
    def _op_text(value: Any) -> str:
        try:
            return str(int(float(value)))
        except (TypeError, ValueError):
            return str(value or "").strip() or "-1"

    prepared["OPERATION_TEXT"] = prepared["OPERATION_SEQ_NUM"].fillna(-1).map(_op_text)
    prepared["REASON_CODE"] = prepared["REASON_RAW"].map(normalize_reason_code)
    prepared["REASON_RAW_UPPER"] = prepared["REASON_RAW"].str.upper()
    prepared["REASON_NAME_UPPER"] = prepared["REASON_NAME"].str.upper()
    prepared["TRANSACTION_QTY"] = pd.to_numeric(prepared["TRANSACTION_QTY"], errors="coerce").fillna(0.0)
    prepared["SCRAP_QTY"] = pd.to_numeric(prepared["SCRAP_QTY"], errors="coerce").fillna(0.0)
    return prepared[_DETAIL_COLUMNS]


def _prepare_linkage_df(linked: dict[str, float]) -> pd.DataFrame:
    if not linked:
        return pd.DataFrame(columns=_LINKAGE_COLUMNS)
    rows = [{"CANONICAL_KEY": key, "REJECT_TOTAL_QTY": _safe_float(value)} for key, value in linked.items()]
    return pd.DataFrame(rows, columns=_LINKAGE_COLUMNS)


def _store_payload(query_id: str, *, detail_df: pd.DataFrame, linkage_df: pd.DataFrame) -> None:
    """Store dataset to L1 (in-memory, lightweight) and L2 (Redis) caches.

    L1 only keeps ``linkage_df`` (tiny) — **not** ``detail_df`` (hundreds of
    MB).  ``detail_df`` lives in Redis (L2) and the parquet spool file on
    disk.  The DuckDB view path reads from the spool file directly; the
    pandas fallback path loads ``detail_df`` from Redis on demand.
    """
    # L1: lightweight — only linkage_df + existence marker
    _dataset_cache.set(query_id, {
        "detail_df": None,
        "linkage_df": linkage_df,
    })
    # L2: full data in Redis
    detail_ok = redis_store_df(_detail_cache_key(query_id), detail_df, ttl=_CACHE_TTL)
    linkage_ok = redis_store_df(_linkage_cache_key(query_id), linkage_df, ttl=_CACHE_TTL)
    if not detail_ok or not linkage_ok:
        logger.warning(
            "_store_payload: Redis store partial failure query_id=%s detail=%s linkage=%s",
            query_id, detail_ok, linkage_ok,
        )


def _get_cached_payload(query_id: str) -> Optional[dict[str, pd.DataFrame]]:
    """Return a lightweight payload dict if the query_id is known.

    The returned ``detail_df`` may be ``None`` (L1 hit — only marker stored).
    Callers that need the full detail DataFrame should call
    ``_load_detail_df_from_redis`` explicitly.
    """
    payload = _dataset_cache.get(query_id)
    if isinstance(payload, dict):
        logger.debug("_get_cached_payload: L1 hit for query_id=%s", query_id)
        return payload

    # L1 miss — check Redis for existence (load only linkage, not detail)
    logger.debug("_get_cached_payload: L1 miss for query_id=%s, trying Redis", query_id)
    # Quick existence check: try loading linkage (tiny) first
    linkage_df = redis_load_df(_linkage_cache_key(query_id))
    # Also verify detail exists in Redis (peek only, don't load)
    detail_exists = _redis_key_exists(_detail_cache_key(query_id))
    if not detail_exists:
        logger.warning(
            "_get_cached_payload: Redis miss for query_id=%s key=%s",
            query_id, _detail_cache_key(query_id),
        )
        return None
    if linkage_df is None:
        linkage_df = pd.DataFrame(columns=_LINKAGE_COLUMNS)

    # Promote to L1 — lightweight (no detail_df)
    payload = {
        "detail_df": None,
        "linkage_df": linkage_df,
    }
    _dataset_cache.set(query_id, payload)
    logger.debug("_get_cached_payload: Redis confirmed for query_id=%s, lightweight L1 promoted", query_id)
    return payload


def _redis_key_exists(key: str) -> bool:
    """Check if a Redis key exists without loading its value."""
    if not REDIS_ENABLED:
        return False
    client = get_redis_client()
    if client is None:
        return False
    try:
        from mes_dashboard.core.redis_df_store import get_key
        return bool(client.exists(get_key(key)))
    except Exception:
        return False


def _load_detail_df_from_redis(query_id: str) -> Optional[pd.DataFrame]:
    """Load detail_df from Redis on demand (for pandas fallback path)."""
    detail_df = redis_load_df(_detail_cache_key(query_id))
    if detail_df is None:
        logger.warning(
            "_load_detail_df_from_redis: Redis miss for query_id=%s", query_id,
        )
    return detail_df


def _load_primary_detail_df(start_date: str, end_date: str) -> pd.DataFrame:
    sql = """
        SELECT
            TRUNC(d.TXN_DATE) AS DATE_BUCKET,
            NVL(TRIM(d.WIP_ENTITY_NAME), '(NA)') AS WIP_ENTITY_NAME,
            NVL(TRIM(d.REASON_CODE), NVL(TRIM(d.REASON_NAME), '(UNMAPPED)')) AS REASON_RAW,
            NVL(TRIM(d.REASON_NAME), '(未填寫)') AS REASON_NAME,
            NVL(TRIM(d.DEPARTMENT_NAME), '(NA)') AS DEPARTMENT_NAME,
            NVL(TRIM(d.LINE), '(NA)') AS LINE_NAME,
            NVL(TRIM(d.PACKAGE), '(NA)') AS PACKAGE_NAME,
            NVL(TRIM(d.TYPE), '(NA)') AS TYPE_NAME,
            NVL(TRIM(d.FUNCTION), '(NA)') AS FUNCTION_NAME,
            NVL(d.OPERATION_SEQ_NUM, -1) AS OPERATION_SEQ_NUM,
            SUM(NVL(d.TRANSACTION_QUANTITY, 0)) AS TRANSACTION_QTY,
            SUM(NVL(d.SCRAP_QUANTITY, 0)) AS SCRAP_QTY
        FROM DWH.ERP_WIP_MOVETXN_DETAIL d
        WHERE d.TXN_DATE >= TO_DATE(:start_date, 'YYYY-MM-DD')
          AND d.TXN_DATE < TO_DATE(:end_date, 'YYYY-MM-DD') + 1
          AND UPPER(NVL(TRIM(d.WIP_ENTITY_NAME), '-')) LIKE 'GA%'
          AND d.PACKAGE IS NOT NULL
          AND TRIM(d.PACKAGE) NOT IN ('N/A', 'NA', '(NA)', '(N/A)', 'NULL')
        GROUP BY
            TRUNC(d.TXN_DATE),
            NVL(TRIM(d.WIP_ENTITY_NAME), '(NA)'),
            NVL(TRIM(d.REASON_CODE), NVL(TRIM(d.REASON_NAME), '(UNMAPPED)')),
            NVL(TRIM(d.REASON_NAME), '(未填寫)'),
            NVL(TRIM(d.DEPARTMENT_NAME), '(NA)'),
            NVL(TRIM(d.LINE), '(NA)'),
            NVL(TRIM(d.PACKAGE), '(NA)'),
            NVL(TRIM(d.TYPE), '(NA)'),
            NVL(TRIM(d.FUNCTION), '(NA)'),
            NVL(d.OPERATION_SEQ_NUM, -1)
    """
    return _prepare_detail_df(read_sql_df_slow(sql, {"start_date": start_date, "end_date": end_date}))


def _build_linkage_df(start_date: str, end_date: str, detail_df: pd.DataFrame) -> pd.DataFrame:
    if detail_df.empty:
        return pd.DataFrame(columns=_LINKAGE_COLUMNS)

    workorders = sorted({
        str(workorder or "").strip().upper()
        for workorder in detail_df["WORKORDER"].tolist()
        if str(workorder or "").strip()
    })
    linked = _compute_reject_linkage(start_date=start_date, end_date=end_date, workorders=workorders)
    return _prepare_linkage_df(linked)


def execute_primary_query(*, start_date: str, end_date: str) -> dict[str, Any]:
    validate_date_range(start_date, end_date)
    query_id = _make_query_id(
        {
            "cache_schema_version": _CACHE_SCHEMA_VERSION,
            "start_date": start_date,
            "end_date": end_date,
        }
    )

    cached = _get_cached_payload(query_id)
    if cached is not None:
        logger.info("Yield alert dataset cache hit: query_id=%s", query_id)
        linkage_ready = cached.get("linkage_df") is not None and not cached["linkage_df"].empty
        return {
            "query_id": query_id,
            "meta": {
                "cache_hit": True,
                "max_query_days": MAX_QUERY_DAYS,
                "linkage_ready": linkage_ready,
            },
        }

    logger.info("Yield alert dataset cache miss: query_id=%s", query_id)
    started = time.perf_counter()
    detail_df = _load_primary_detail_df(start_date, end_date)
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)

    # NOTE: No memory guard here — follows reject module pattern.
    # Primary query only loads → spool to parquet → store cache → release.
    # DuckDB handles heavy aggregation out-of-core via parquet spool.
    # Guard is applied in apply_view's pandas fallback path only.

    logger.info(
        "Yield alert detail loaded: query_id=%s detail_rows=%s scrap_rows=%s latency_ms=%.2f",
        query_id,
        len(detail_df),
        int((detail_df["SCRAP_QTY"] > 0).sum()) if not detail_df.empty else 0,
        elapsed_ms,
    )
    linkage_df = pd.DataFrame(columns=_LINKAGE_COLUMNS)

    # Spool write (parquet to disk) — synchronous so DuckDB view path
    # can use it immediately on the subsequent /view request.
    try:
        store_spooled_df(_SPOOL_NAMESPACE, query_id, detail_df)
    except Exception as exc:
        logger.warning("Spool write failed (query_id=%s): %s", query_id, exc)

    # L1 (lightweight marker + linkage only) + L2 Redis (full detail).
    # detail_df is NOT kept in L1 — DuckDB reads from spool file,
    # pandas fallback loads from Redis on demand.
    detail_row_count = len(detail_df)
    _store_payload(query_id, detail_df=detail_df, linkage_df=linkage_df)

    # Explicitly release the large DataFrame reference to help GC
    del detail_df
    maybe_gc_collect()

    return {
        "query_id": query_id,
        "meta": {
            "cache_hit": False,
            "query_latency_ms": elapsed_ms,
            "max_query_days": MAX_QUERY_DAYS,
            "detail_rows": int(detail_row_count),
            "linkage_ready": False,
        },
    }


def execute_linkage_query(*, query_id: str) -> Optional[dict[str, Any]]:
    """Compute reject linkage for a cached dataset and update the cache."""
    payload = _get_cached_payload(query_id)
    if payload is None:
        return None

    # detail_df may be None in L1 (lightweight mode) — load from Redis
    detail_df = payload.get("detail_df")
    if detail_df is None:
        detail_df = _load_detail_df_from_redis(query_id)
    if detail_df is None or detail_df.empty:
        return {
            "query_id": query_id,
            "meta": {"linkage_ready": True, "linkage_rows": 0},
        }

    # Derive date range from the cached data
    start_date = str(detail_df["DATE_BUCKET"].min())[:10]
    end_date = str(detail_df["DATE_BUCKET"].max())[:10]

    started = time.perf_counter()
    linkage_df = _build_linkage_df(start_date, end_date, detail_df)
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)

    # Update cache with computed linkage (detail_df written to Redis again, L1 stays lightweight)
    _store_payload(query_id, detail_df=detail_df, linkage_df=linkage_df)
    del detail_df
    maybe_gc_collect()
    logger.info(
        "Yield alert linkage computed: query_id=%s rows=%s latency_ms=%.2f",
        query_id, len(linkage_df), elapsed_ms,
    )
    return {
        "query_id": query_id,
        "meta": {
            "linkage_ready": True,
            "linkage_rows": int(len(linkage_df)),
            "query_latency_ms": elapsed_ms,
        },
    }


def _normalize_filter_values(filters: Optional[dict[str, Any]]) -> dict[str, list[str]]:
    base = filters or {}
    normalized: dict[str, list[str]] = {}
    for key in _FILTER_COLUMN_MAP:
        normalized[key] = _normalize_tokens(base.get(key) or [])
    return normalized


def _apply_dimension_filters(df: pd.DataFrame, filters: dict[str, list[str]]) -> pd.DataFrame:
    if df.empty:
        return df
    mask = pd.Series(True, index=df.index)
    for filter_key, column in _FILTER_COLUMN_MAP.items():
        values = filters.get(filter_key) or []
        if not values:
            continue
        mask &= df[column].isin(values)
    return df[mask]


def _apply_reason_policy(df: pd.DataFrame, *, excluded_reason_tokens: set[str]) -> pd.DataFrame:
    if df.empty:
        return df
    normalized_excluded = _build_normalized_exclusion_tokens(excluded_reason_tokens)

    # Negative SCRAP_QTY = reversal/correction; always include regardless of reason code.
    reversal_mask = df["SCRAP_QTY"] < 0

    mask = df["REASON_CODE"] != "UNMAPPED_REASON"
    if normalized_excluded:
        mask &= ~df["REASON_CODE"].isin(normalized_excluded)
    if excluded_reason_tokens:
        mask &= ~df["REASON_RAW_UPPER"].isin(excluded_reason_tokens)
        mask &= ~df["REASON_NAME_UPPER"].isin(excluded_reason_tokens)
    return df[mask | reversal_mask]


def _to_numeric(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _build_summary_and_trend(
    *,
    tx_df: pd.DataFrame,
    scrap_df: pd.DataFrame,
    granularity: str = "day",
) -> tuple[dict[str, float], list[dict[str, float]]]:
    """Build overall summary and date-bucketed trend from pre-computed tx/scrap DataFrames."""
    transaction_qty = _safe_float(tx_df["TRANSACTION_QTY"].sum()) if not tx_df.empty else 0.0
    scrap_qty = _safe_float(scrap_df["SCRAP_QTY"].sum()) if not scrap_df.empty else 0.0

    yield_pct = 100.0 if transaction_qty <= 0 else round((1 - (scrap_qty / transaction_qty)) * 100, 4)
    summary = {
        "transaction_qty": round(transaction_qty, 4),
        "scrap_qty": round(scrap_qty, 4),
        "yield_pct": yield_pct,
    }

    tx_by_date: dict[str, float] = {}
    if not tx_df.empty:
        date_str = _vectorized_bucket(tx_df["DATE_BUCKET"], granularity)
        grouped_tx = tx_df.groupby(date_str, as_index=True)["TRANSACTION_QTY"].sum()
        tx_by_date = {str(k): _safe_float(v) for k, v in grouped_tx.items()}

    scrap_by_date: dict[str, float] = {}
    if not scrap_df.empty:
        date_str = _vectorized_bucket(scrap_df["DATE_BUCKET"], granularity)
        grouped_scrap = scrap_df.groupby(date_str, as_index=True)["SCRAP_QTY"].sum()
        scrap_by_date = {str(k): _safe_float(v) for k, v in grouped_scrap.items()}

    trend_items: list[dict[str, float]] = []
    for bucket in sorted(set(tx_by_date.keys()) | set(scrap_by_date.keys())):
        tx_qty = _safe_float(tx_by_date.get(bucket, 0.0))
        sc_qty = _safe_float(scrap_by_date.get(bucket, 0.0))
        day_yield = 100.0 if tx_qty <= 0 else round((1 - (sc_qty / tx_qty)) * 100, 4)
        trend_items.append(
            {
                "date_bucket": bucket,
                "transaction_qty": round(tx_qty, 4),
                "scrap_qty": round(sc_qty, 4),
                "yield_pct": day_yield,
            }
        )

    return summary, trend_items


_ALERTS_SORT_COLUMN: dict[str, str] = {
    "date_bucket": "DATE_BUCKET",
    "workorder": "WORKORDER",
    "reason_code": "REASON_CODE",
    "package": "PACKAGE_NAME",
    "type": "TYPE_NAME",
    "scrap_qty": "SCRAP_QTY",
    "yield_pct": "_yield_pct",
    "risk_score": "_risk_score",
}


def _build_alerts_view(
    *,
    detail_df: pd.DataFrame,
    linkage_df: pd.DataFrame,
    linkage_ready: bool,
    filters: dict[str, list[str]],
    page: int,
    per_page: int,
    sort_by: str,
    sort_dir: str,
    risk_threshold: float,
    min_scrap_qty: float,
    excluded_reason_tokens: set[str],
) -> dict[str, Any]:
    filtered = _apply_dimension_filters(detail_df, filters)
    filtered = _apply_reason_policy(filtered, excluded_reason_tokens=excluded_reason_tokens)
    if not filtered.empty:
        filtered = filtered[filtered["SCRAP_QTY"] != 0]

    _empty_quality = {
        "matched": 0, "partially_matched": 0, "unmatched": 0,
        "matched_scrap_qty": 0.0, "partially_matched_scrap_qty": 0.0,
        "unmatched_scrap_qty": 0.0, "total_scrap_qty": 0.0,
        "unmatched_ratio": 0.0, "warning": False, "warning_code": None,
    }
    if filtered.empty:
        return {
            "items": [],
            "pagination": {"page": 1, "per_page": per_page, "total": 0, "total_pages": 1},
            "quality": _empty_quality,
            "sort": {"sort_by": sort_by, "sort_dir": sort_dir},
        }

    grouped = (
        filtered.groupby(
            [
                "DATE_BUCKET", "WORKORDER", "REASON_CODE", "REASON_NAME",
                "DEPARTMENT_GROUP", "PROCESS_CATEGORY", "LINE_NAME", "PACKAGE_NAME",
                "TYPE_NAME", "FUNCTION_NAME", "OPERATION_TEXT",
            ],
            dropna=False,
            as_index=False,
        )[["TRANSACTION_QTY", "SCRAP_QTY"]].sum()
    )

    # Vectorized derivations — avoids per-row Python loop on large DataFrames
    tx_arr = grouped["TRANSACTION_QTY"].to_numpy(dtype=float)
    sc_arr = grouped["SCRAP_QTY"].to_numpy(dtype=float)
    nonzero_tx = tx_arr > 0
    _tx_safe = np.where(nonzero_tx, tx_arr, 1.0)
    yield_pct_arr = np.where(nonzero_tx, np.round((1 - sc_arr / _tx_safe) * 100, 4), 100.0)
    scrap_rate_pct_arr = np.where(nonzero_tx, np.round((sc_arr / _tx_safe) * 100, 4), 0.0)
    scrap_weight_arr = np.minimum(np.maximum(sc_arr, 0.0), 200.0) / 20.0
    risk_score_arr = np.round(np.maximum(0.0, risk_threshold - yield_pct_arr) + scrap_weight_arr, 4)

    grouped = grouped.assign(
        _yield_pct=yield_pct_arr,
        _scrap_rate_pct=scrap_rate_pct_arr,
        _risk_score=risk_score_arr,
    )

    # Filter by threshold (vectorized boolean mask)
    threshold_mask = (yield_pct_arr < risk_threshold) | (sc_arr >= min_scrap_qty)
    grouped = grouped[threshold_mask].reset_index(drop=True)

    if grouped.empty:
        return {
            "items": [],
            "pagination": {"page": 1, "per_page": per_page, "total": 0, "total_pages": 1},
            "quality": _empty_quality,
            "sort": {"sort_by": sort_by, "sort_dir": sort_dir},
        }

    # Sort in pandas before pagination
    sort_col = _ALERTS_SORT_COLUMN.get(sort_by, "DATE_BUCKET")
    if sort_col in grouped.columns:
        grouped = grouped.sort_values(
            sort_col, ascending=(sort_dir == "asc"), kind="stable"
        ).reset_index(drop=True)

    total = len(grouped)
    total_pages = max(1, math.ceil(total / per_page))
    normalized_page = min(max(1, page), total_pages)
    start_idx = (normalized_page - 1) * per_page
    end_idx = start_idx + per_page

    # Build linkage maps
    linkage_exact: dict[str, float] = {}
    linkage_prefix: dict[str, float] = {}
    if linkage_df is not None and not linkage_df.empty:
        for _, lrow in linkage_df.iterrows():
            key = str(lrow.get("CANONICAL_KEY") or "").strip()
            qty = _safe_float(lrow.get("REJECT_TOTAL_QTY"))
            if not key:
                continue
            linkage_exact[key] = qty
            parts = key.split("|", 2)
            if len(parts) == 3:
                prefix = f"{parts[0]}|{parts[1]}|"
                linkage_prefix[prefix] = linkage_prefix.get(prefix, 0.0) + qty

    # Vectorized linkage quality metrics across ALL filtered rows
    date_ser = grouped["DATE_BUCKET"].astype(str).str[:10]
    wo_ser = grouped["WORKORDER"].fillna("(NA)").astype(str).str.strip().str.upper()
    rc_ser = grouped["REASON_CODE"].fillna("UNMAPPED_REASON").astype(str).str.strip()
    canonical_key_ser = date_ser + "|" + wo_ser + "|" + rc_ser
    prefix_key_ser = date_ser + "|" + wo_ser + "|"

    exact_qty_ser = canonical_key_ser.map(linkage_exact).fillna(0.0)
    partial_lookup_ser = prefix_key_ser.map(linkage_prefix).fillna(0.0)
    is_exact = exact_qty_ser > 0
    is_partial = (~is_exact) & (partial_lookup_ser > 0)
    is_unmatched = ~(is_exact | is_partial)

    sc_ser = grouped["SCRAP_QTY"].astype(float)
    matched = int(is_exact.sum())
    partial_count = int(is_partial.sum())
    unmatched_count = int(is_unmatched.sum())
    matched_qty = float(sc_ser[is_exact].sum())
    partial_qty = float(sc_ser[is_partial].sum())
    unmatched_qty = float(sc_ser[is_unmatched].sum())

    # Build page items — iterrows only on the current page slice
    page_df = grouped.iloc[start_idx:end_idx]
    page_canonical_keys = canonical_key_ser.iloc[start_idx:end_idx].tolist()
    page_prefix_keys = prefix_key_ser.iloc[start_idx:end_idx].tolist()

    page_rows: list[dict[str, Any]] = []
    for (_, row), canonical_key, prefix_key in zip(
        page_df.iterrows(), page_canonical_keys, page_prefix_keys
    ):
        transaction_qty = _safe_float(row.get("TRANSACTION_QTY"))
        scrap_qty = _safe_float(row.get("SCRAP_QTY"))
        yield_pct = _safe_float(row.get("_yield_pct"))
        scrap_rate_pct = _safe_float(row.get("_scrap_rate_pct"))
        risk_score = _safe_float(row.get("_risk_score"))
        risk_level, _ = _risk_level(yield_pct, scrap_qty, risk_threshold)

        item: dict[str, Any] = {
            "date_bucket": str(row.get("DATE_BUCKET") or ""),
            "workorder": str(row.get("WORKORDER") or "").strip(),
            "reason_code": str(row.get("REASON_CODE") or "").strip(),
            "reason_name": str(row.get("REASON_NAME") or "").strip(),
            "department": str(row.get("DEPARTMENT_GROUP") or "(NA)"),
            "process_category": str(row.get("PROCESS_CATEGORY") or "OTHER"),
            "line": str(row.get("LINE_NAME") or "(NA)"),
            "package": str(row.get("PACKAGE_NAME") or "(NA)"),
            "type": str(row.get("TYPE_NAME") or "(NA)"),
            "function": str(row.get("FUNCTION_NAME") or "(NA)"),
            "operation": str(row.get("OPERATION_TEXT") or "-1"),
            "transaction_qty": round(transaction_qty, 4),
            "scrap_qty": round(scrap_qty, 4),
            "yield_pct": yield_pct,
            "scrap_rate_pct": scrap_rate_pct,
            "risk_level": risk_level,
            "risk_score": risk_score,
            "match_status": "none",
            "fallback_reason": None,
            "reject_total_qty": 0.0,
        }

        exact_qty = _safe_float(linkage_exact.get(canonical_key, 0.0))
        if exact_qty > 0:
            item["match_status"] = "exact"
            item["reject_total_qty"] = round(exact_qty, 4)
        else:
            partial_qty_val = _safe_float(linkage_prefix.get(prefix_key, 0.0))
            if partial_qty_val > 0:
                item["match_status"] = "partial"
                item["fallback_reason"] = "reason_code_not_exact"
                item["reject_total_qty"] = round(partial_qty_val, 4)

        page_rows.append(item)

    total_scrap = matched_qty + partial_qty + unmatched_qty
    unmatched_ratio = 0.0 if total_scrap <= 0 else round(unmatched_qty / total_scrap, 4)

    if not linkage_ready:
        quality_warning = False
        quality_warning_code = "linkage_not_ready"
    elif unmatched_ratio >= LINKAGE_WARN_UNMATCHED_RATIO:
        quality_warning = True
        quality_warning_code = "high_unmatched_ratio"
    else:
        quality_warning = False
        quality_warning_code = None

    return {
        "items": page_rows,
        "pagination": {
            "page": normalized_page,
            "per_page": per_page,
            "total": total,
            "total_pages": total_pages,
        },
        "quality": {
            "matched": matched,
            "partially_matched": partial_count,
            "unmatched": unmatched_count,
            "matched_scrap_qty": round(matched_qty, 4),
            "partially_matched_scrap_qty": round(partial_qty, 4),
            "unmatched_scrap_qty": round(unmatched_qty, 4),
            "total_scrap_qty": round(total_scrap, 4),
            "unmatched_ratio": unmatched_ratio,
            "warning": quality_warning,
            "warning_code": quality_warning_code,
        },
        "sort": {"sort_by": sort_by, "sort_dir": sort_dir},
    }


def _compute_filter_options(detail_df: pd.DataFrame) -> dict[str, list[str]]:
    if detail_df.empty:
        return {}
    options: dict[str, list[str]] = {}
    for key, col in [
        ("lines", "LINE_NAME"),
        ("packages", "PACKAGE_NAME"),
        ("types", "TYPE_NAME"),
        ("functions", "FUNCTION_NAME"),
    ]:
        values = sorted({
            str(v) for v in detail_df[col].dropna()
            if str(v) not in ("(NA)", "-1", "")
        })
        options[key] = values
    options["process_categories"] = sorted({
        str(v) for v in detail_df["PROCESS_CATEGORY"].dropna()
        if str(v) not in ("OTHER", "")
    })
    return options


def _enrich_alerts_with_linkage(
    alerts: dict[str, Any],
    *,
    linkage_df: Optional[pd.DataFrame],
    linkage_ready: bool,
) -> None:
    """Add linkage matching to alert page items and compute quality metrics in-place.

    When ``_quality_keys`` is present in ``alerts`` (set by DuckDB SQL runtime),
    quality metrics are computed across ALL filtered alerts (full population),
    matching the pandas path behavior. Otherwise, quality is computed on page
    items only.
    """
    linkage_exact: dict[str, float] = {}
    linkage_prefix: dict[str, float] = {}
    if linkage_df is not None and not linkage_df.empty:
        for _, lrow in linkage_df.iterrows():
            key = str(lrow.get("CANONICAL_KEY") or "").strip()
            qty = _safe_float(lrow.get("REJECT_TOTAL_QTY"))
            if not key:
                continue
            linkage_exact[key] = qty
            parts = key.split("|", 2)
            if len(parts) == 3:
                prefix = f"{parts[0]}|{parts[1]}|"
                linkage_prefix[prefix] = linkage_prefix.get(prefix, 0.0) + qty

    # Enrich page items with linkage match status
    for item in alerts.get("items") or []:
        canonical_key = build_canonical_key(
            item["date_bucket"], item["workorder"], item["reason_code"]
        )
        exact_qty = _safe_float(linkage_exact.get(canonical_key, 0.0))
        if exact_qty > 0:
            item["match_status"] = "exact"
            item["reject_total_qty"] = round(exact_qty, 4)
        else:
            prefix_key = f"{item['date_bucket']}|{item['workorder'].upper()}|"
            partial_qty_val = _safe_float(linkage_prefix.get(prefix_key, 0.0))
            if partial_qty_val > 0:
                item["match_status"] = "partial"
                item["fallback_reason"] = "reason_code_not_exact"
                item["reject_total_qty"] = round(partial_qty_val, 4)

    # Compute quality metrics across full population
    # Use _quality_keys (from DuckDB) if available; otherwise iterate page items
    quality_source = alerts.pop("_quality_keys", None) or alerts.get("items") or []

    matched = 0
    partial_count = 0
    unmatched_count = 0
    matched_qty = 0.0
    partial_qty = 0.0
    unmatched_qty = 0.0

    for row in quality_source:
        date_bucket = str(row.get("date_bucket") or "")
        workorder = str(row.get("workorder") or "")
        reason_code = str(row.get("reason_code") or "")
        scrap_qty = _safe_float(row.get("scrap_qty"))

        canonical_key = build_canonical_key(date_bucket, workorder, reason_code)
        exact_qty = _safe_float(linkage_exact.get(canonical_key, 0.0))
        if exact_qty > 0:
            matched += 1
            matched_qty += scrap_qty
        else:
            prefix_key = f"{date_bucket}|{workorder.upper()}|"
            partial_qty_val = _safe_float(linkage_prefix.get(prefix_key, 0.0))
            if partial_qty_val > 0:
                partial_count += 1
                partial_qty += scrap_qty
            else:
                unmatched_count += 1
                unmatched_qty += scrap_qty

    total_scrap = matched_qty + partial_qty + unmatched_qty
    unmatched_ratio = 0.0 if total_scrap <= 0 else round(unmatched_qty / total_scrap, 4)

    if not linkage_ready:
        quality_warning = False
        quality_warning_code = "linkage_not_ready"
    elif unmatched_ratio >= LINKAGE_WARN_UNMATCHED_RATIO:
        quality_warning = True
        quality_warning_code = "high_unmatched_ratio"
    else:
        quality_warning = False
        quality_warning_code = None

    alerts["quality"] = {
        "matched": matched,
        "partially_matched": partial_count,
        "unmatched": unmatched_count,
        "matched_scrap_qty": round(matched_qty, 4),
        "partially_matched_scrap_qty": round(partial_qty, 4),
        "unmatched_scrap_qty": round(unmatched_qty, 4),
        "total_scrap_qty": round(total_scrap, 4),
        "unmatched_ratio": unmatched_ratio,
        "warning": quality_warning,
        "warning_code": quality_warning_code,
    }


def apply_view(
    *,
    query_id: str,
    filters: Optional[dict[str, Any]] = None,
    granularity: str = "day",
    page: int = 1,
    per_page: int = DEFAULT_PAGE_SIZE,
    sort_by: str = "date_bucket",
    sort_dir: str = "desc",
    risk_threshold: float = 98.0,
    min_scrap_qty: float = 1.0,
) -> Optional[dict[str, Any]]:
    payload = _get_cached_payload(query_id)
    if payload is None:
        logger.warning(
            "apply_view cache miss: query_id=%s process_cache_stats=%s",
            query_id, _dataset_cache.stats(),
        )
        return None

    normalized_per_page = min(max(1, int(per_page or DEFAULT_PAGE_SIZE)), MAX_PAGE_SIZE)
    normalized_page = max(1, int(page or 1))
    normalized_sort_by = sort_by if sort_by in VALID_SORT_FIELDS else "date_bucket"
    normalized_sort_dir = "asc" if str(sort_dir).lower() == "asc" else "desc"
    normalized_risk = _to_numeric(risk_threshold, 98.0)
    normalized_min_scrap = _to_numeric(min_scrap_qty, 1.0)
    normalized_filters = _normalize_filter_values(filters)
    normalized_granularity = granularity if granularity in _VALID_GRANULARITIES else "day"

    started = time.perf_counter()
    excluded_reason_tokens = _load_excluded_reason_tokens()

    # ── DuckDB-first path (Task 5.1) ──────────────────────────────────────────
    from mes_dashboard.services.yield_alert_sql_runtime import try_compute_view_from_spool

    sql_result, sql_meta = try_compute_view_from_spool(
        query_id=query_id,
        filters=normalized_filters,
        granularity=normalized_granularity,
        page=normalized_page,
        per_page=normalized_per_page,
        sort_by=normalized_sort_by,
        sort_dir=normalized_sort_dir,
        risk_threshold=normalized_risk,
        min_scrap_qty=normalized_min_scrap,
        excluded_reason_tokens=excluded_reason_tokens,
    )

    if sql_result is not None:
        # Task 5.2: linkage matching on page rows in Python layer
        linkage_df = payload["linkage_df"]
        _linkage_ready = linkage_df is not None and not linkage_df.empty
        _enrich_alerts_with_linkage(
            sql_result["alerts"], linkage_df=linkage_df, linkage_ready=_linkage_ready
        )
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.info(
            "Yield alert DuckDB view computed: query_id=%s latency_ms=%.2f fallback=%s",
            query_id, elapsed_ms, sql_meta.get("view_sql_fallback_reason"),
        )
        return {
            "summary": sql_result["summary"],
            "trend": sql_result["trend"],
            "heatmap": sql_result["heatmap"],
            "station_summary": sql_result["station_summary"],
            "package_summary": sql_result["package_summary"],
            "alerts": sql_result["alerts"],
            "meta": {
                "query_latency_ms": elapsed_ms,
                "max_query_days": MAX_QUERY_DAYS,
                "max_per_page": MAX_PAGE_SIZE,
                "reason_exclusion_applied": True,
                "excluded_reason_count": len(excluded_reason_tokens),
                "cache": {"query_id": query_id},
                "linkage_ready": _linkage_ready,
                "view_source": "duckdb",
                **sql_meta,
            },
            "filter_options": sql_result["filter_options"],
        }

    # ── Task 5.3: Pandas fallback path ───────────────────────────────────────
    if sql_meta.get("view_sql_fallback_reason"):
        logger.info(
            "Yield alert DuckDB fallback to pandas: query_id=%s reason=%s",
            query_id, sql_meta.get("view_sql_fallback_reason"),
        )

    # detail_df may be None in L1 (lightweight mode) — load from Redis on demand
    detail_df = payload.get("detail_df")
    if detail_df is None:
        detail_df = _load_detail_df_from_redis(query_id)
    if detail_df is None:
        logger.warning("apply_view pandas fallback: detail_df unavailable from Redis query_id=%s", query_id)
        return None
    linkage_df = payload["linkage_df"]

    # Task 1.3: memory guard before pandas computation
    enforce_dataset_memory_guard(
        detail_df,
        operation="視圖查詢",
        query_id=query_id,
        max_input_mb=_VIEW_MAX_INPUT_MB,
        max_projected_rss_mb=_VIEW_MAX_PROJECTED_RSS_MB,
        working_set_factor=_VIEW_WORKING_SET_FACTOR,
    )

    # Apply ALL dimension filters to summary/trend/heatmap/station/package (not just dept/process)
    detail_filt = _apply_dimension_filters(detail_df, normalized_filters)
    tx_df_base = _dedup_tx_df(detail_filt)
    scrap_df_base = _apply_reason_policy(detail_filt, excluded_reason_tokens=excluded_reason_tokens)

    summary, trend_items = _build_summary_and_trend(
        tx_df=tx_df_base,
        scrap_df=scrap_df_base,
        granularity=normalized_granularity,
    )
    heatmap_items = _build_heatmap_data(
        tx_df=tx_df_base,
        scrap_df=scrap_df_base,
        granularity=normalized_granularity,
    )
    station_summary_items = _build_station_summary(
        tx_df=tx_df_base,
        scrap_df=scrap_df_base,
    )
    package_summary_items = _build_package_summary(
        tx_df=tx_df_base,
        scrap_df=scrap_df_base,
    )
    _linkage_ready = linkage_df is not None and not linkage_df.empty
    alerts = _build_alerts_view(
        detail_df=detail_df,
        linkage_df=linkage_df,
        linkage_ready=_linkage_ready,
        filters=normalized_filters,
        page=normalized_page,
        per_page=normalized_per_page,
        sort_by=normalized_sort_by,
        sort_dir=normalized_sort_dir,
        risk_threshold=normalized_risk,
        min_scrap_qty=normalized_min_scrap,
        excluded_reason_tokens=excluded_reason_tokens,
    )
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    logger.info("Yield alert cached view computed: query_id=%s latency_ms=%.2f", query_id, elapsed_ms)

    result = {
        "summary": summary,
        "trend": {
            "items": trend_items,
            "granularity": normalized_granularity,
        },
        "heatmap": {
            "items": heatmap_items,
            "granularity": normalized_granularity,
        },
        "station_summary": {
            "items": station_summary_items,
        },
        "package_summary": {
            "items": package_summary_items,
        },
        "alerts": alerts,
        "meta": {
            "query_latency_ms": elapsed_ms,
            "max_query_days": MAX_QUERY_DAYS,
            "max_per_page": MAX_PAGE_SIZE,
            "reason_exclusion_applied": True,
            "excluded_reason_count": len(excluded_reason_tokens),
            "cache": {"query_id": query_id},
            "linkage_ready": _linkage_ready,
            "view_source": "pandas",
        },
        "filter_options": _compute_filter_options(payload["detail_df"]),
    }
    # Task 1.3: GC after heavy pandas computation
    maybe_gc_collect()
    return result
