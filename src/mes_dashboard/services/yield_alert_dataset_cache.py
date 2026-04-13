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
import tempfile
import threading
import time
from datetime import date, timedelta
from typing import Any, Optional

import numpy as np
import pandas as pd

from mes_dashboard.core.cache import ProcessLevelCache, register_process_cache
from mes_dashboard.core.database import read_sql_df_slow, read_sql_df_slow_iter
from mes_dashboard.core.interactive_memory_guard import maybe_gc_collect
from mes_dashboard.core.query_spool_store import (
    QUERY_SPOOL_DIR,
    get_spool_file_path,
    get_spool_metadata,
    register_spool_file,
    store_spooled_df,
)
from mes_dashboard.core.redis_client import release_lock, try_acquire_lock
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
_CACHE_MAX_SIZE = max(1, int(os.getenv("YIELD_ALERT_DATASET_CACHE_MAX_SIZE", "1")))
_REDIS_NAMESPACE = "yield_alert_dataset"
_CACHE_SCHEMA_VERSION = 4
_SPOOL_NAMESPACE = "yield_alert_dataset"
_WARMUP_DAYS = max(1, int(os.getenv("YIELD_ALERT_DATASET_WARMUP_DAYS", "30")))
_STREAMING_SPOOL_ENABLED = os.getenv("YIELD_ALERT_STREAMING_SPOOL_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}


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


class SpoolWriteError(Exception):
    """Raised when the streaming spool write pipeline fails."""


_PRIMARY_DETAIL_SQL = """
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




_VALID_GRANULARITIES = frozenset({"day", "week", "month", "year"})
_DEPT_SEQ_MAP: dict[str, int] = {g: i for i, g in enumerate(_YIELD_WORKCENTER_GROUP_ORDER)}

_GRANULARITY_LABEL = {"day": "日", "week": "週", "month": "月", "year": "年"}


_dataset_cache = ProcessLevelCache(ttl_seconds=_CACHE_TTL, max_size=_CACHE_MAX_SIZE)
register_process_cache("yield_alert_dataset", _dataset_cache, "Yield Alert Dataset (L1)")


def _make_query_id(params: dict[str, Any]) -> str:
    canonical = json.dumps(params, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


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


def _prepare_detail_chunk(columns: list, rows: list) -> "Any":
    """Build a mini PyArrow Table from a (columns, rows) batch from read_sql_df_slow_iter.

    Applies the same normalizations as _prepare_detail_df but in-place (no .copy()).
    Returns a pa.Table with only _DETAIL_COLUMNS columns.
    """
    import pyarrow as pa

    df = pd.DataFrame(rows, columns=columns)

    df["DATE_BUCKET"] = df["DATE_BUCKET"].map(_bucket_to_text)
    df["WORKORDER"] = df["WIP_ENTITY_NAME"].fillna("(NA)").astype(str).str.strip()
    df["REASON_RAW"] = df["REASON_RAW"].fillna("(UNMAPPED)").astype(str).str.strip()
    df["REASON_NAME"] = df["REASON_NAME"].fillna("(未填寫)").astype(str).str.strip()
    df["DEPARTMENT_NAME"] = df["DEPARTMENT_NAME"].fillna("(NA)").astype(str).str.strip()
    df["DEPARTMENT_GROUP"] = df["DEPARTMENT_NAME"].map(_normalize_yield_department_group)
    df["PROCESS_CATEGORY"] = df["DEPARTMENT_GROUP"].map(_normalize_process_category)
    df["LINE_NAME"] = df["LINE_NAME"].fillna("(NA)").astype(str).str.strip()
    df["PACKAGE_NAME"] = df["PACKAGE_NAME"].fillna("(NA)").astype(str).str.strip()
    df["TYPE_NAME"] = df["TYPE_NAME"].fillna("(NA)").astype(str).str.strip()
    df["FUNCTION_NAME"] = df["FUNCTION_NAME"].fillna("(NA)").astype(str).str.strip()

    def _op_text_chunk(v: Any) -> str:
        if v == -1:
            return "-1"
        try:
            return str(int(float(v)))
        except (TypeError, ValueError):
            return "-1"

    df["OPERATION_TEXT"] = df["OPERATION_SEQ_NUM"].fillna(-1).map(_op_text_chunk)
    df["REASON_CODE"] = df["REASON_RAW"].map(normalize_reason_code)
    df["REASON_RAW_UPPER"] = df["REASON_RAW"].str.upper()
    df["REASON_NAME_UPPER"] = df["REASON_NAME"].str.upper()
    df["TRANSACTION_QTY"] = pd.to_numeric(df["TRANSACTION_QTY"], errors="coerce").fillna(0.0)
    df["SCRAP_QTY"] = pd.to_numeric(df["SCRAP_QTY"], errors="coerce").fillna(0.0)

    return pa.Table.from_pandas(df[_DETAIL_COLUMNS], preserve_index=False)


def _streaming_write_to_spool(
    sql: str,
    params: dict,
    query_id: str,
) -> "tuple[Any, int]":
    """Stream SQL results batch-by-batch into a temporary Parquet spool file.

    Returns (tmp_path, total_rows). If no rows were returned, returns (None, 0)
    and cleans up the temp file.
    """
    import pyarrow as pa
    import pyarrow.parquet as pq
    from pathlib import Path

    spool_dir = (QUERY_SPOOL_DIR / _SPOOL_NAMESPACE).resolve()
    spool_dir.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path_str = tempfile.mkstemp(
        prefix=f"{query_id}_streaming_",
        suffix=".tmp.parquet",
        dir=spool_dir,
    )
    os.close(tmp_fd)
    tmp_path = Path(tmp_path_str)

    writer = None
    schema = None
    total_rows = 0
    try:
        for columns, rows in read_sql_df_slow_iter(sql, params):
            table = _prepare_detail_chunk(columns, rows)
            if writer is None:
                schema = table.schema
                writer = pq.ParquetWriter(str(tmp_path), schema)
            else:
                if table.schema != schema:
                    try:
                        table = table.cast(schema, safe=False)
                    except Exception:
                        pass  # best-effort cast
            writer.write_table(table)
            total_rows += len(rows)
            del table
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
            try:
                writer.close()
            except Exception:
                pass

    if total_rows == 0:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except Exception:
                pass
        return None, 0

    return tmp_path, total_rows


def _prepare_linkage_df(linked: dict[str, float]) -> pd.DataFrame:
    if not linked:
        return pd.DataFrame(columns=_LINKAGE_COLUMNS)
    rows = [{"CANONICAL_KEY": key, "REJECT_TOTAL_QTY": _safe_float(value)} for key, value in linked.items()]
    return pd.DataFrame(rows, columns=_LINKAGE_COLUMNS)


def _store_payload(
    query_id: str,
    *,
    linkage_df: pd.DataFrame,
    spool_ready: bool = True,
    empty_result: bool = False,
    start_date: str = "",
    end_date: str = "",
) -> None:
    """Store dataset metadata to L1 (in-memory) cache.

    L1 keeps linkage_df (tiny) + spool/empty flags + date metadata.
    detail_df is NOT stored here — DuckDB reads from the spool file,
    and the pandas fallback reads from the spool file on demand.
    Linkage is also stored in Redis for cross-process / post-restart recovery.
    """
    _dataset_cache.set(query_id, {
        "linkage_df": linkage_df,
        "spool_ready": spool_ready,
        "empty_result": empty_result,
        "start_date": start_date,
        "end_date": end_date,
    })
    if linkage_df is not None and not linkage_df.empty:
        linkage_ok = redis_store_df(_linkage_cache_key(query_id), linkage_df, ttl=_CACHE_TTL)
        if not linkage_ok:
            logger.warning(
                "_store_payload: Redis linkage store failed query_id=%s",
                query_id,
            )


def _get_cached_payload(query_id: str) -> Optional[dict]:
    """Return a lightweight payload dict if the query_id is valid and data is ready.

    Returns None when neither L1 nor Redis+spool can confirm the dataset exists.
    """
    payload = _dataset_cache.get(query_id)
    if isinstance(payload, dict):
        # Backward compat: old L1 payloads (pre-refactor) have no 'spool_ready' key.
        # Treat them as spool_ready=True so existing callers continue to work.
        if "spool_ready" not in payload:
            payload = dict(payload)
            payload["spool_ready"] = True
            payload.setdefault("empty_result", False)

        empty = payload.get("empty_result", False)
        spool_ready = payload.get("spool_ready", True)

        if empty or (spool_ready and get_spool_file_path(_SPOOL_NAMESPACE, query_id) is not None):
            logger.debug("_get_cached_payload: L1 hit for query_id=%s", query_id)
            return payload

        logger.debug(
            "_get_cached_payload: L1 stale (spool missing) for query_id=%s", query_id
        )
        # Fall through to Redis check

    # L1 miss — check Redis linkage and spool file
    logger.debug("_get_cached_payload: L1 miss for query_id=%s, trying Redis+spool", query_id)
    linkage_df = redis_load_df(_linkage_cache_key(query_id))
    spool_path = get_spool_file_path(_SPOOL_NAMESPACE, query_id)
    spool_exists = spool_path is not None

    if linkage_df is None and not spool_exists:
        logger.warning(
            "_get_cached_payload: Redis+spool miss for query_id=%s",
            query_id,
        )
        return None

    if linkage_df is None:
        linkage_df = pd.DataFrame(columns=_LINKAGE_COLUMNS)

    # Promote lightweight L1
    promoted: dict = {
        "linkage_df": linkage_df,
        "spool_ready": spool_exists,
        "empty_result": not spool_exists,
        "start_date": "",
        "end_date": "",
    }
    _dataset_cache.set(query_id, promoted)
    logger.debug(
        "_get_cached_payload: promoted lightweight L1 for query_id=%s spool=%s",
        query_id, spool_exists,
    )
    return promoted


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
    return _prepare_detail_df(
        read_sql_df_slow(
            sql,
            {"start_date": start_date, "end_date": end_date},
            caller="yield_alert_dataset_cache:_load_primary_detail_df",
        )
    )


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
        spool_meta = get_spool_metadata(_SPOOL_NAMESPACE, query_id) or {}
        detail_rows = spool_meta.get("row_count")
        cache_hit_meta: dict = {
            "cache_hit": True,
            "max_query_days": MAX_QUERY_DAYS,
            "linkage_ready": linkage_ready,
        }
        if detail_rows is not None:
            cache_hit_meta["detail_rows"] = int(detail_rows)
        return {
            "query_id": query_id,
            "meta": cache_hit_meta,
        }

    logger.info("Yield alert dataset cache miss: query_id=%s", query_id)

    if _STREAMING_SPOOL_ENABLED:
        # ── Streaming spool path ─────────────────────────────────────────
        lock_name = f"yield_alert_primary:{query_id}"
        lock_acquired = try_acquire_lock(lock_name, ttl_seconds=300)
        if not lock_acquired:
            # Another worker is executing the same query — wait for it to finish
            logger.info(
                "execute_primary_query: single-flight wait for query_id=%s", query_id
            )
            for _ in range(15):  # up to 30s (15 × 2s)
                time.sleep(2)
                cached = _get_cached_payload(query_id)
                if cached is not None:
                    logger.info(
                        "execute_primary_query: single-flight resolved from cache query_id=%s",
                        query_id,
                    )
                    linkage_ready = (
                        cached.get("linkage_df") is not None
                        and not cached["linkage_df"].empty
                    )
                    return {
                        "query_id": query_id,
                        "meta": {
                            "cache_hit": True,
                            "max_query_days": MAX_QUERY_DAYS,
                            "linkage_ready": linkage_ready,
                        },
                    }
            raise SpoolWriteError(
                "single_flight_timeout: 查詢已有另一個 worker 正在執行，請稍後重試"
            )

        try:
            started = time.perf_counter()
            try:
                tmp_path, total_rows = _streaming_write_to_spool(
                    _PRIMARY_DETAIL_SQL,
                    {"start_date": start_date, "end_date": end_date},
                    query_id,
                )
            except Exception as exc:
                raise SpoolWriteError(f"SPOOL_WRITE_FAILED: {exc}") from exc

            elapsed_ms = round((time.perf_counter() - started) * 1000, 2)

            if total_rows == 0:
                _store_payload(
                    query_id,
                    linkage_df=pd.DataFrame(columns=_LINKAGE_COLUMNS),
                    spool_ready=False,
                    empty_result=True,
                    start_date=start_date,
                    end_date=end_date,
                )
                logger.info(
                    "execute_primary_query: empty result query_id=%s latency_ms=%.2f",
                    query_id, elapsed_ms,
                )
                return {
                    "query_id": query_id,
                    "meta": {
                        "cache_hit": False,
                        "query_latency_ms": elapsed_ms,
                        "max_query_days": MAX_QUERY_DAYS,
                        "detail_rows": 0,
                        "linkage_ready": True,
                    },
                }

            registered = register_spool_file(_SPOOL_NAMESPACE, query_id, tmp_path, total_rows)
            if not registered:
                raise SpoolWriteError(
                    "spool_register_failed: Spool 註冊失敗，請稍後重試"
                )

            _store_payload(
                query_id,
                linkage_df=pd.DataFrame(columns=_LINKAGE_COLUMNS),
                spool_ready=True,
                empty_result=False,
                start_date=start_date,
                end_date=end_date,
            )
            maybe_gc_collect()
            logger.info(
                "execute_primary_query: streaming spool done query_id=%s rows=%s latency_ms=%.2f",
                query_id, total_rows, elapsed_ms,
            )
            return {
                "query_id": query_id,
                "meta": {
                    "cache_hit": False,
                    "query_latency_ms": elapsed_ms,
                    "max_query_days": MAX_QUERY_DAYS,
                    "detail_rows": int(total_rows),
                    "linkage_ready": False,
                },
            }
        finally:
            try:
                release_lock(lock_name)
            except Exception:
                pass

    else:
        # ── Legacy path (YIELD_ALERT_STREAMING_SPOOL_ENABLED=false) ─────
        started = time.perf_counter()
        detail_df = _load_primary_detail_df(start_date, end_date)
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)

        # NOTE: No memory guard here — follows reject module pattern.
        # Primary query only loads → spool to parquet → store cache → release.
        # DuckDB handles heavy aggregation out-of-core via parquet spool.

        logger.info(
            "Yield alert detail loaded (legacy): query_id=%s detail_rows=%s scrap_rows=%s latency_ms=%.2f",
            query_id,
            len(detail_df),
            int((detail_df["SCRAP_QTY"] > 0).sum()) if not detail_df.empty else 0,
            elapsed_ms,
        )

        spool_ok = False
        try:
            store_spooled_df(_SPOOL_NAMESPACE, query_id, detail_df)
            spool_ok = True
        except Exception as exc:
            logger.warning("Spool write failed (legacy, query_id=%s): %s", query_id, exc)

        detail_row_count = len(detail_df)
        _store_payload(
            query_id,
            linkage_df=pd.DataFrame(columns=_LINKAGE_COLUMNS),
            spool_ready=spool_ok,
            empty_result=detail_df.empty,
            start_date=start_date,
            end_date=end_date,
        )

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


def ensure_dataset_loaded() -> dict[str, Any]:
    """Ensure the default yield-alert dataset exists in cache."""
    end = date.today()
    start = end - timedelta(days=_WARMUP_DAYS - 1)
    start_date = start.strftime("%Y-%m-%d")
    end_date = end.strftime("%Y-%m-%d")

    query_id = _make_query_id(
        {
            "cache_schema_version": _CACHE_SCHEMA_VERSION,
            "start_date": start_date,
            "end_date": end_date,
        }
    )
    if _get_cached_payload(query_id) is not None:
        return {
            "query_id": query_id,
            "cache_hit": True,
            "start_date": start_date,
            "end_date": end_date,
        }

    result = execute_primary_query(start_date=start_date, end_date=end_date)
    return {
        "query_id": result.get("query_id", query_id),
        "cache_hit": False,
        "start_date": start_date,
        "end_date": end_date,
    }


def _extract_workorders_from_spool(query_id: str) -> list[str]:
    """Query DISTINCT WORKORDER values from the spool parquet file via DuckDB."""
    spool_path = get_spool_file_path(_SPOOL_NAMESPACE, query_id)
    if spool_path is None:
        return []
    try:
        from mes_dashboard.core.duckdb_runtime import create_heavy_query_connection
        conn = create_heavy_query_connection()
        try:
            rows = conn.execute(
                'SELECT DISTINCT "WORKORDER" FROM read_parquet(?)', [spool_path]
            ).fetchall()
        finally:
            conn.close()
        return [str(r[0]).strip().upper() for r in rows if r[0]]
    except Exception as exc:
        logger.warning(
            "_extract_workorders_from_spool: failed for query_id=%s: %s", query_id, exc
        )
        return []


def execute_linkage_query(*, query_id: str) -> Optional[dict[str, Any]]:
    """Compute reject linkage for a cached dataset and update the cache."""
    payload = _get_cached_payload(query_id)
    if payload is None:
        return None

    start_date: str = payload.get("start_date") or ""
    end_date: str = payload.get("end_date") or ""

    if payload.get("empty_result"):
        return {
            "query_id": query_id,
            "meta": {"linkage_ready": True, "linkage_rows": 0},
        }

    spool_ready = payload.get("spool_ready", True)
    spool_path = get_spool_file_path(_SPOOL_NAMESPACE, query_id)
    if not spool_ready or spool_path is None:
        return {
            "query_id": query_id,
            "meta": {
                "linkage_ready": False,
                "linkage_not_ready_reason": "spool_not_available",
            },
        }

    workorders = _extract_workorders_from_spool(query_id)
    if not workorders:
        _store_payload(
            query_id,
            linkage_df=pd.DataFrame(columns=_LINKAGE_COLUMNS),
            spool_ready=spool_ready,
            empty_result=False,
            start_date=start_date,
            end_date=end_date,
        )
        return {
            "query_id": query_id,
            "meta": {"linkage_ready": True, "linkage_rows": 0},
        }

    # If date range is missing from payload, derive it from the spool via DuckDB
    if not start_date or not end_date:
        try:
            from mes_dashboard.core.duckdb_runtime import create_heavy_query_connection
            conn = create_heavy_query_connection()
            try:
                row = conn.execute(
                    'SELECT MIN("DATE_BUCKET"), MAX("DATE_BUCKET") FROM read_parquet(?)',
                    [spool_path],
                ).fetchone()
            finally:
                conn.close()
            if row and row[0] and row[1]:
                start_date = str(row[0])[:10]
                end_date = str(row[1])[:10]
        except Exception as exc:
            logger.warning(
                "execute_linkage_query: date range derivation failed query_id=%s: %s",
                query_id, exc,
            )

    started = time.perf_counter()
    linked = _compute_reject_linkage(
        start_date=start_date, end_date=end_date, workorders=workorders
    )
    linkage_df = _prepare_linkage_df(linked)
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)

    _store_payload(
        query_id,
        linkage_df=linkage_df,
        spool_ready=spool_ready,
        empty_result=False,
        start_date=start_date,
        end_date=end_date,
    )
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


def _to_numeric(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


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

    return None
