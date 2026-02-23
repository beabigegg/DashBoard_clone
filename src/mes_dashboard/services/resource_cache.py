# -*- coding: utf-8 -*-
"""Resource Cache - DWH.DW_MES_RESOURCE 全表快取模組.

全表快取套用全域篩選後的設備主檔資料至 Redis。
提供統一 API 供各模組取用設備資料和篩選器選項。
"""

from __future__ import annotations

import io
import json
import logging
import os
import threading
import time
from collections import OrderedDict
from datetime import datetime
from typing import Any

import pandas as pd

from mes_dashboard.core.cache import register_process_cache
from mes_dashboard.core.redis_client import (
    get_redis_client,
    redis_available,
    REDIS_ENABLED,
    REDIS_KEY_PREFIX,
)
from mes_dashboard.core.database import read_sql_df
from mes_dashboard.config.constants import (
    EXCLUDED_LOCATIONS,
    EXCLUDED_ASSET_STATUSES,
    EQUIPMENT_TYPE_FILTER,
)
from mes_dashboard.sql import QueryBuilder
from mes_dashboard.services.sql_fragments import (
    RESOURCE_BASE_SELECT_TEMPLATE,
    RESOURCE_VERSION_SELECT_TEMPLATE,
)

logger = logging.getLogger('mes_dashboard.resource_cache')

ResourceRecord = dict[str, Any]
RowPosition = int
PositionBucket = dict[str, list[RowPosition]]
FlagBuckets = dict[str, list[RowPosition]]
ResourceIndex = dict[str, Any]

DEFAULT_PROCESS_CACHE_TTL_SECONDS = 30
DEFAULT_PROCESS_CACHE_MAX_SIZE = 32
DEFAULT_RESOURCE_SYNC_INTERVAL_SECONDS = 14_400  # 4 hours
DEFAULT_INDEX_VERSION_CHECK_INTERVAL_SECONDS = 5
RESOURCE_DF_CACHE_KEY = "resource_data"
TRUE_BUCKET = "1"
FALSE_BUCKET = "0"

# ============================================================
# Process-Level Cache (Prevents redundant JSON parsing)
# ============================================================

class _ProcessLevelCache:
    """Thread-safe process-level cache for parsed DataFrames."""

    def __init__(self, ttl_seconds: int = DEFAULT_PROCESS_CACHE_TTL_SECONDS, max_size: int = DEFAULT_PROCESS_CACHE_MAX_SIZE):
        self._cache: OrderedDict[str, tuple[pd.DataFrame, float]] = OrderedDict()
        self._lock = threading.Lock()
        self._ttl = max(int(ttl_seconds), 1)
        self._max_size = max(int(max_size), 1)

    @property
    def max_size(self) -> int:
        return self._max_size

    def _evict_expired_locked(self, now: float) -> None:
        stale_keys = [
            key for key, (_, timestamp) in self._cache.items()
            if now - timestamp > self._ttl
        ]
        for key in stale_keys:
            self._cache.pop(key, None)

    def get(self, key: str) -> pd.DataFrame | None:
        """Get cached DataFrame if not expired."""
        with self._lock:
            payload = self._cache.get(key)
            if payload is None:
                return None
            df, timestamp = payload
            now = time.time()
            if now - timestamp > self._ttl:
                self._cache.pop(key, None)
                return None
            self._cache.move_to_end(key, last=True)
            return df

    def set(self, key: str, df: pd.DataFrame) -> None:
        """Cache a DataFrame with current timestamp."""
        with self._lock:
            now = time.time()
            self._evict_expired_locked(now)
            if key in self._cache:
                self._cache.pop(key, None)
            elif len(self._cache) >= self._max_size:
                self._cache.popitem(last=False)
            self._cache[key] = (df, now)
            self._cache.move_to_end(key, last=True)

    def invalidate(self, key: str) -> None:
        """Remove a key from cache."""
        with self._lock:
            self._cache.pop(key, None)

    def stats(self) -> dict:
        """Return live cache statistics for telemetry."""
        with self._lock:
            now = time.time()
            live = sum(1 for _, (_, ts) in self._cache.items() if now - ts <= self._ttl)
            return {"entries": live, "max_size": self._max_size, "ttl_seconds": self._ttl}


def _resolve_cache_max_size(env_name: str, default: int) -> int:
    value = os.getenv(env_name)
    if value is None:
        return max(int(default), 1)
    try:
        return max(int(value), 1)
    except (TypeError, ValueError):
        return max(int(default), 1)


# Global process-level cache for resource data (30s TTL)
PROCESS_CACHE_MAX_SIZE = _resolve_cache_max_size("PROCESS_CACHE_MAX_SIZE", DEFAULT_PROCESS_CACHE_MAX_SIZE)
RESOURCE_PROCESS_CACHE_MAX_SIZE = _resolve_cache_max_size(
    "RESOURCE_PROCESS_CACHE_MAX_SIZE",
    PROCESS_CACHE_MAX_SIZE,
)
_resource_df_cache = _ProcessLevelCache(
    ttl_seconds=DEFAULT_PROCESS_CACHE_TTL_SECONDS,
    max_size=RESOURCE_PROCESS_CACHE_MAX_SIZE,
)
register_process_cache("resource", _resource_df_cache, "Resource DataFrame (L1, 30s)")
_resource_parse_lock = threading.Lock()
_resource_index_lock = threading.Lock()
_resource_index: ResourceIndex = {
    "ready": False,
    "source": None,
    "version": None,
    "updated_at": None,
    "built_at": None,
    "version_checked_at": 0.0,
    "count": 0,
    "all_positions": [],
    "by_resource_id": {},
    "by_workcenter": {},
    "by_family": {},
    "by_department": {},
    "by_location": {},
    "by_is_production": {TRUE_BUCKET: [], FALSE_BUCKET: []},
    "by_is_key": {TRUE_BUCKET: [], FALSE_BUCKET: []},
    "by_is_monitor": {TRUE_BUCKET: [], FALSE_BUCKET: []},
    "memory": {
        "frame_bytes": 0,
        "index_bytes": 0,
        "records_json_bytes": 0,
        "bucket_entries": 0,
        "amplification_ratio": 0.0,
        "representation": "dataframe+row-index",
    },
}


def _new_empty_index() -> ResourceIndex:
    return {
        "ready": False,
        "source": None,
        "version": None,
        "updated_at": None,
        "built_at": None,
        "version_checked_at": 0.0,
        "count": 0,
        "all_positions": [],
        "by_resource_id": {},
        "by_workcenter": {},
        "by_family": {},
        "by_department": {},
        "by_location": {},
        "by_is_production": {TRUE_BUCKET: [], FALSE_BUCKET: []},
        "by_is_key": {TRUE_BUCKET: [], FALSE_BUCKET: []},
        "by_is_monitor": {TRUE_BUCKET: [], FALSE_BUCKET: []},
        "memory": {
            "frame_bytes": 0,
            "index_bytes": 0,
            "records_json_bytes": 0,
            "bucket_entries": 0,
            "amplification_ratio": 0.0,
            "representation": "dataframe+row-index",
        },
    }


def _invalidate_resource_index() -> None:
    with _resource_index_lock:
        global _resource_index
        _resource_index = _new_empty_index()


def _is_truthy_flag(value: Any) -> bool:
    if value is True:
        return True
    if value in (1, "1"):
        return True
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "y"}
    return False


def _bucket_append(bucket: PositionBucket, key: Any, row_position: RowPosition) -> None:
    if key is None:
        return
    if isinstance(key, float) and pd.isna(key):
        return
    key_str = str(key)
    bucket.setdefault(key_str, []).append(int(row_position))


def _estimate_dataframe_bytes(df: pd.DataFrame) -> int:
    try:
        return int(df.memory_usage(index=True, deep=True).sum())
    except Exception:
        return 0


def _estimate_index_bytes(index: ResourceIndex) -> int:
    """Estimate lightweight index memory footprint for telemetry."""
    by_resource_id = index.get("by_resource_id", {})
    by_workcenter = index.get("by_workcenter", {})
    by_family = index.get("by_family", {})
    by_department = index.get("by_department", {})
    by_location = index.get("by_location", {})
    by_is_production = index.get("by_is_production", {TRUE_BUCKET: [], FALSE_BUCKET: []})
    by_is_key = index.get("by_is_key", {TRUE_BUCKET: [], FALSE_BUCKET: []})
    by_is_monitor = index.get("by_is_monitor", {TRUE_BUCKET: [], FALSE_BUCKET: []})
    all_positions = index.get("all_positions", [])

    position_entries = (
        len(all_positions)
        + sum(len(v) for v in by_workcenter.values())
        + sum(len(v) for v in by_family.values())
        + sum(len(v) for v in by_department.values())
        + sum(len(v) for v in by_location.values())
        + len(by_is_production.get(TRUE_BUCKET, []))
        + len(by_is_production.get(FALSE_BUCKET, []))
        + len(by_is_key.get(TRUE_BUCKET, []))
        + len(by_is_key.get(FALSE_BUCKET, []))
        + len(by_is_monitor.get(TRUE_BUCKET, []))
        + len(by_is_monitor.get(FALSE_BUCKET, []))
    )
    # Approximate integer/list/dict overhead; telemetry only needs directional signal.
    return int(position_entries * 8 + len(by_resource_id) * 64)


def _build_resource_index(
    df: pd.DataFrame,
    *,
    source: str,
    version: str | None,
    updated_at: str | None,
) -> ResourceIndex:
    normalized_df = df.reset_index(drop=True)
    index = _new_empty_index()
    index["ready"] = True
    index["source"] = source
    index["version"] = version
    index["updated_at"] = updated_at
    index["built_at"] = datetime.now().isoformat()
    index["version_checked_at"] = time.time()
    index["count"] = len(normalized_df)
    index["all_positions"] = list(range(len(normalized_df)))

    for row_position, record in normalized_df.iterrows():
        resource_id = record.get("RESOURCEID")
        if resource_id is not None and not (isinstance(resource_id, float) and pd.isna(resource_id)):
            index["by_resource_id"][str(resource_id)] = int(row_position)

        _bucket_append(index["by_workcenter"], record.get("WORKCENTERNAME"), row_position)
        _bucket_append(index["by_family"], record.get("RESOURCEFAMILYNAME"), row_position)
        _bucket_append(index["by_department"], record.get("PJ_DEPARTMENT"), row_position)
        _bucket_append(index["by_location"], record.get("LOCATIONNAME"), row_position)

        index["by_is_production"][TRUE_BUCKET if _is_truthy_flag(record.get("PJ_ISPRODUCTION")) else FALSE_BUCKET].append(int(row_position))
        index["by_is_key"][TRUE_BUCKET if _is_truthy_flag(record.get("PJ_ISKEY")) else FALSE_BUCKET].append(int(row_position))
        index["by_is_monitor"][TRUE_BUCKET if _is_truthy_flag(record.get("PJ_ISMONITOR")) else FALSE_BUCKET].append(int(row_position))

    bucket_entries = (
        sum(len(v) for v in index["by_workcenter"].values())
        + sum(len(v) for v in index["by_family"].values())
        + sum(len(v) for v in index["by_department"].values())
        + sum(len(v) for v in index["by_location"].values())
        + len(index["by_is_production"][TRUE_BUCKET])
        + len(index["by_is_production"][FALSE_BUCKET])
        + len(index["by_is_key"][TRUE_BUCKET])
        + len(index["by_is_key"][FALSE_BUCKET])
        + len(index["by_is_monitor"][TRUE_BUCKET])
        + len(index["by_is_monitor"][FALSE_BUCKET])
    )
    frame_bytes = _estimate_dataframe_bytes(normalized_df)
    index_bytes = _estimate_index_bytes(index)
    amplification_ratio = round(
        (frame_bytes + index_bytes) / max(frame_bytes, 1),
        4,
    )
    index["memory"] = {
        "frame_bytes": int(frame_bytes),
        "index_bytes": int(index_bytes),
        "records_json_bytes": 0,  # kept for backward-compatible telemetry shape
        "bucket_entries": int(bucket_entries),
        "amplification_ratio": amplification_ratio,
        "representation": "dataframe+row-index",
    }

    return index


def _index_matches(
    current: ResourceIndex,
    *,
    source: str,
    version: str | None,
    row_count: int,
) -> bool:
    if not current.get("ready"):
        return False
    if current.get("source") != source:
        return False
    if version and current.get("version") != version:
        return False
    return int(current.get("count", 0)) == int(row_count)


def _ensure_resource_index(
    df: pd.DataFrame,
    *,
    source: str,
    version: str | None = None,
    updated_at: str | None = None,
) -> None:
    global _resource_index
    with _resource_index_lock:
        current = _resource_index
        if _index_matches(current, source=source, version=version, row_count=len(df)):
            return

    new_index = _build_resource_index(
        df,
        source=source,
        version=version,
        updated_at=updated_at,
    )
    with _resource_index_lock:
        _resource_index = new_index


def _get_resource_index() -> ResourceIndex:
    with _resource_index_lock:
        return _resource_index


def _get_cache_meta(client=None) -> tuple[str | None, str | None]:
    redis_client = client or get_redis_client()
    if redis_client is None:
        return None, None

    try:
        version, updated_at = redis_client.mget([
            _get_key("meta:version"),
            _get_key("meta:updated"),
        ])
        return version, updated_at
    except Exception:
        return None, None


def _redis_data_available(client=None) -> bool:
    """Check whether Redis currently has resource payload."""
    redis_client = client or get_redis_client()
    if redis_client is None:
        return False

    try:
        return redis_client.get(_get_key("data")) is not None
    except Exception:
        return False


def _pick_bucket_positions(
    bucket: PositionBucket,
    keys: list[Any],
) -> list[RowPosition]:
    seen: set[int] = set()
    result: list[int] = []
    for key in keys:
        for row_position in bucket.get(str(key), []):
            normalized = int(row_position)
            if normalized in seen:
                continue
            seen.add(normalized)
            result.append(normalized)
    return result


def _records_from_positions(df: pd.DataFrame, positions: list[RowPosition]) -> list[ResourceRecord]:
    if not positions:
        return []
    unique_positions = sorted({int(pos) for pos in positions if 0 <= int(pos) < len(df)})
    if not unique_positions:
        return []
    return df.iloc[unique_positions].to_dict(orient='records')


def _records_from_index(index: ResourceIndex, positions: list[RowPosition] | None = None) -> list[ResourceRecord]:
    if not index.get("ready"):
        return []
    df = _resource_df_cache.get(RESOURCE_DF_CACHE_KEY)
    if df is None:
        legacy_records = index.get("records")
        if isinstance(legacy_records, list):
            if positions is None:
                return list(legacy_records)
            selected = [legacy_records[int(pos)] for pos in positions if 0 <= int(pos) < len(legacy_records)]
            return selected
        # DataFrame evicted from process cache (TTL expired) and no legacy
        # records stored in index.  Reload from Redis before giving up.
        df = _get_cached_data()
        if df is None:
            return []
    selected_positions = positions if positions is not None else index.get("all_positions", [])
    if not selected_positions:
        selected_positions = list(range(len(df)))
    return _records_from_positions(df, selected_positions)

# ============================================================
# Configuration
# ============================================================

RESOURCE_CACHE_ENABLED = os.getenv('RESOURCE_CACHE_ENABLED', 'true').lower() == 'true'
RESOURCE_SYNC_INTERVAL = int(
    os.getenv('RESOURCE_SYNC_INTERVAL', str(DEFAULT_RESOURCE_SYNC_INTERVAL_SECONDS))
)
RESOURCE_INDEX_VERSION_CHECK_INTERVAL = int(
    os.getenv('RESOURCE_INDEX_VERSION_CHECK_INTERVAL', str(DEFAULT_INDEX_VERSION_CHECK_INTERVAL_SECONDS))
)

# Redis key helpers
def _get_key(key: str) -> str:
    """Get full Redis key with resource prefix."""
    return f"{REDIS_KEY_PREFIX}:resource:{key}"


# ============================================================
# Internal: Oracle Load Functions
# ============================================================

def _build_filter_builder() -> QueryBuilder:
    """Build QueryBuilder with global filter conditions.

    Returns:
        QueryBuilder instance with filter conditions applied.
    """
    builder = QueryBuilder()

    # Equipment type filter - raw SQL condition from config
    builder.add_condition(EQUIPMENT_TYPE_FILTER.strip())

    # Workcenter filter - exclude resources without WORKCENTERNAME
    builder.add_is_not_null("WORKCENTERNAME")

    # Location filter - exclude locations, allow NULL
    if EXCLUDED_LOCATIONS:
        builder.add_not_in_condition(
            "LOCATIONNAME",
            list(EXCLUDED_LOCATIONS),
            allow_null=True
        )

    # Asset status filter - exclude statuses, allow NULL
    if EXCLUDED_ASSET_STATUSES:
        builder.add_not_in_condition(
            "PJ_ASSETSSTATUS",
            list(EXCLUDED_ASSET_STATUSES),
            allow_null=True
        )

    return builder


def _load_from_oracle() -> pd.DataFrame | None:
    """從 Oracle 載入全表資料（套用全域篩選）.

    Returns:
        DataFrame with all columns, or None if query failed.
    """
    builder = _build_filter_builder()
    builder.base_sql = RESOURCE_BASE_SELECT_TEMPLATE
    sql, params = builder.build()

    try:
        df = read_sql_df(sql, params)
        if df is not None:
            logger.info(f"Loaded {len(df)} resources from Oracle")
        return df
    except Exception as e:
        logger.error(f"Failed to load resources from Oracle: {e}")
        return None


def _get_version_from_oracle() -> str | None:
    """取得 Oracle 資料版本（MAX(LASTCHANGEDATE)）.

    Returns:
        Version string (ISO format), or None if query failed.
    """
    builder = _build_filter_builder()
    builder.base_sql = RESOURCE_VERSION_SELECT_TEMPLATE
    sql, params = builder.build()

    try:
        df = read_sql_df(sql, params)
        if df is not None and not df.empty:
            version = df.iloc[0]['VERSION']
            if version is not None:
                if hasattr(version, 'isoformat'):
                    return version.isoformat()
                return str(version)
        return None
    except Exception as e:
        logger.error(f"Failed to get version from Oracle: {e}")
        return None


# ============================================================
# Internal: Redis Functions
# ============================================================

def _get_version_from_redis() -> str | None:
    """取得 Redis 快取版本.

    Returns:
        Cached version string, or None.
    """
    client = get_redis_client()
    if client is None:
        return None

    try:
        return client.get(_get_key("meta:version"))
    except Exception as e:
        logger.warning(f"Failed to get version from Redis: {e}")
        return None


def _sync_to_redis(df: pd.DataFrame, version: str) -> bool:
    """同步至 Redis（使用 pipeline 確保原子性）.

    Args:
        df: DataFrame with resource data.
        version: Version string (MAX(LASTCHANGEDATE)).

    Returns:
        True if sync was successful.
    """
    client = get_redis_client()
    if client is None:
        return False

    try:
        # Convert DataFrame to JSON
        # Handle datetime columns
        df_copy = df.copy()
        for col in df_copy.select_dtypes(include=['datetime64']).columns:
            df_copy[col] = df_copy[col].astype(str)

        data_json = df_copy.to_json(orient='records', force_ascii=False)

        # Atomic update using pipeline
        now = datetime.now().isoformat()
        pipe = client.pipeline()
        pipe.set(_get_key("data"), data_json)
        pipe.set(_get_key("meta:version"), version)
        pipe.set(_get_key("meta:updated"), now)
        pipe.set(_get_key("meta:count"), str(len(df)))
        pipe.execute()

        # Invalidate process-level cache so next request picks up new data
        _resource_df_cache.invalidate(RESOURCE_DF_CACHE_KEY)
        _invalidate_resource_index()

        logger.info(f"Resource cache synced: {len(df)} rows, version={version}")
        return True
    except Exception as e:
        logger.error(f"Failed to sync to Redis: {e}")
        return False


def _get_cached_data() -> pd.DataFrame | None:
    """Get cached resource data from Redis with process-level caching.

    Uses a two-tier cache strategy:
    1. Process-level cache: Parsed DataFrame (30s TTL) - fast, no parsing
    2. Redis cache: Raw JSON data - shared across workers

    This prevents redundant JSON parsing across concurrent requests.

    Returns:
        DataFrame with resource data, or None if cache miss.
    """
    cache_key = RESOURCE_DF_CACHE_KEY

    # Tier 1: Check process-level cache first (fast path)
    cached_df = _resource_df_cache.get(cache_key)
    if cached_df is not None:
        if REDIS_ENABLED and RESOURCE_CACHE_ENABLED and not _redis_data_available():
            _resource_df_cache.invalidate(cache_key)
            _invalidate_resource_index()
        else:
            if not _get_resource_index().get("ready"):
                version, updated_at = _get_cache_meta()
                _ensure_resource_index(
                    cached_df,
                    source="redis",
                    version=version,
                    updated_at=updated_at,
                )
            logger.debug(f"Process cache hit: {len(cached_df)} rows")
            return cached_df

    # Tier 2: Parse from Redis (slow path - needs lock)
    if not REDIS_ENABLED or not RESOURCE_CACHE_ENABLED:
        return None

    client = get_redis_client()
    if client is None:
        return None

    # Use lock to prevent multiple threads from parsing simultaneously
    with _resource_parse_lock:
        # Double-check after acquiring lock
        cached_df = _resource_df_cache.get(cache_key)
        if cached_df is not None:
            logger.debug(f"Process cache hit (after lock): {len(cached_df)} rows")
            return cached_df

        try:
            start_time = time.time()
            data_json = client.get(_get_key("data"))
            if data_json is None:
                logger.debug("Resource cache miss: no data in Redis")
                return None

            df = pd.read_json(io.StringIO(data_json), orient='records')
            parse_time = time.time() - start_time
            version, updated_at = _get_cache_meta(client)

            # Store in process-level cache
            _resource_df_cache.set(cache_key, df)
            _ensure_resource_index(
                df,
                source="redis",
                version=version,
                updated_at=updated_at,
            )

            logger.debug(f"Resource cache hit: loaded {len(df)} rows from Redis (parsed in {parse_time:.2f}s)")
            return df
        except Exception as e:
            logger.warning(f"Failed to read resource cache: {e}")
            return None


# ============================================================
# Cache Management API
# ============================================================

def refresh_cache(force: bool = False) -> bool:
    """手動刷新快取.

    Args:
        force: 強制刷新，忽略版本檢查.

    Returns:
        True if cache was refreshed.
    """
    if not REDIS_ENABLED or not RESOURCE_CACHE_ENABLED:
        logger.info("Resource cache is disabled")
        return False

    if not redis_available():
        logger.warning("Redis not available, cannot refresh resource cache")
        return False

    try:
        # Get versions
        oracle_version = _get_version_from_oracle()
        if oracle_version is None:
            logger.error("Failed to get version from Oracle")
            return False

        redis_version = _get_version_from_redis()

        # Check if update needed
        if not force and redis_version == oracle_version:
            logger.debug(f"Resource cache version unchanged ({oracle_version}), skipping")
            return False

        logger.info(f"Resource cache version changed: {redis_version} -> {oracle_version}")

        # Load and sync
        df = _load_from_oracle()
        if df is None or df.empty:
            logger.error("Failed to load resources from Oracle")
            return False

        return _sync_to_redis(df, oracle_version)

    except Exception as e:
        logger.error(f"Failed to refresh resource cache: {e}", exc_info=True)
        return False


def init_cache() -> None:
    """初始化快取（應用啟動時呼叫）."""
    if not REDIS_ENABLED or not RESOURCE_CACHE_ENABLED:
        logger.info("Resource cache is disabled, skipping init")
        return

    if not redis_available():
        logger.warning("Redis not available during resource cache init")
        return

    # Check if cache exists
    client = get_redis_client()
    if client is None:
        return

    try:
        exists = client.exists(_get_key("data"))
        if not exists:
            logger.info("Resource cache empty, performing initial load...")
            refresh_cache(force=True)
        else:
            logger.info("Resource cache already populated")
    except Exception as e:
        logger.error(f"Failed to init resource cache: {e}")


def get_cache_status() -> dict[str, Any]:
    """取得快取狀態資訊.

    Returns:
        Dict with cache status.
    """
    status = {
        'enabled': REDIS_ENABLED and RESOURCE_CACHE_ENABLED,
        'loaded': False,
        'count': 0,
        'version': None,
        'updated_at': None,
    }

    if not status['enabled']:
        return status

    client = get_redis_client()
    if client is None:
        return status

    try:
        status['loaded'] = client.exists(_get_key("data")) > 0
        if status['loaded']:
            count_str = client.get(_get_key("meta:count"))
            status['count'] = int(count_str) if count_str else 0
            status['version'] = client.get(_get_key("meta:version"))
            status['updated_at'] = client.get(_get_key("meta:updated"))
    except Exception as e:
        logger.warning(f"Failed to get resource cache status: {e}")

    derived = get_resource_index_status()
    derived_version = derived.get("version")
    derived["is_fresh"] = bool(status.get("version")) and derived_version == status.get("version")
    status["derived_index"] = derived

    return status


# ============================================================
# Query API
# ============================================================

def get_resource_index_status() -> dict[str, Any]:
    """Get process-level derived index telemetry."""
    index = _get_resource_index()
    memory = index.get("memory") or {}
    built_at = index.get("built_at")
    age_seconds = None
    if built_at:
        try:
            age_seconds = max((datetime.now() - datetime.fromisoformat(built_at)).total_seconds(), 0.0)
        except Exception:
            age_seconds = None

    return {
        "ready": bool(index.get("ready")),
        "source": index.get("source"),
        "version": index.get("version"),
        "updated_at": index.get("updated_at"),
        "built_at": built_at,
        "count": int(index.get("count", 0)),
        "age_seconds": round(age_seconds, 3) if age_seconds is not None else None,
        "memory": {
            "frame_bytes": int(memory.get("frame_bytes", 0)),
            "index_bytes": int(memory.get("index_bytes", 0)),
            "records_json_bytes": int(memory.get("records_json_bytes", 0)),
            "bucket_entries": int(memory.get("bucket_entries", 0)),
            "amplification_ratio": float(memory.get("amplification_ratio", 0.0)),
            "representation": str(memory.get("representation", "unknown")),
        },
    }


def get_resource_index_snapshot() -> ResourceIndex:
    """Get derived resource index snapshot, rebuilding if needed."""
    index = _get_resource_index()
    if index.get("ready"):
        if index.get("source") == "redis":
            if not _redis_data_available():
                _resource_df_cache.invalidate(RESOURCE_DF_CACHE_KEY)
                _invalidate_resource_index()
                index = _get_resource_index()

            # If Redis metadata version is missing, verify payload existence on every call.
            # This avoids serving stale in-process index when Redis payload is evicted.
            if index.get("ready") and not index.get("version"):
                if not _redis_data_available():
                    _resource_df_cache.invalidate(RESOURCE_DF_CACHE_KEY)
                    _invalidate_resource_index()
                    index = _get_resource_index()
                else:
                    with _resource_index_lock:
                        _resource_index["version_checked_at"] = time.time()
                    return _get_resource_index()

            if index.get("ready"):
                checked_at = float(index.get("version_checked_at") or 0.0)
                if time.time() - checked_at >= RESOURCE_INDEX_VERSION_CHECK_INTERVAL:
                    latest_version = _get_version_from_redis()
                    current_version = index.get("version")
                    if latest_version and current_version and latest_version != current_version:
                        logger.info(
                            "Resource cache version changed (%s -> %s), rebuilding derived index",
                            current_version,
                            latest_version,
                        )
                        _resource_df_cache.invalidate(RESOURCE_DF_CACHE_KEY)
                        _invalidate_resource_index()
                        index = _get_resource_index()
                    else:
                        with _resource_index_lock:
                            _resource_index["version_checked_at"] = time.time()
                        return _get_resource_index()
                else:
                    return index
        else:
            # Oracle fallback snapshot should be treated as ephemeral to avoid serving
            # stale process data indefinitely if subsequent fallback query fails.
            _invalidate_resource_index()
            index = _get_resource_index()

    df = _get_cached_data()
    if df is not None:
        _resource_df_cache.set(RESOURCE_DF_CACHE_KEY, df.reset_index(drop=True))
        version, updated_at = _get_cache_meta()
        _ensure_resource_index(
            df,
            source="redis",
            version=version,
            updated_at=updated_at,
        )
        return _get_resource_index()

    logger.info("Resource cache miss while building index, falling back to Oracle")
    oracle_df = _load_from_oracle()
    if oracle_df is None:
        _resource_df_cache.invalidate(RESOURCE_DF_CACHE_KEY)
        _invalidate_resource_index()
        return _new_empty_index()

    _ensure_resource_index(
        oracle_df,
        source="oracle",
        version=None,
        updated_at=datetime.now().isoformat(),
    )
    _resource_df_cache.set(RESOURCE_DF_CACHE_KEY, oracle_df.reset_index(drop=True))
    return _get_resource_index()


def get_all_resources() -> list[ResourceRecord]:
    """取得所有快取中的設備資料（全欄位）.

    Falls back to Oracle if cache unavailable.

    Returns:
        List of resource dicts.
    """
    index = get_resource_index_snapshot()
    return _records_from_index(index)


def get_resource_by_id(resource_id: str) -> ResourceRecord | None:
    """依 RESOURCEID 取得單筆設備資料.

    Args:
        resource_id: The RESOURCEID to look up.

    Returns:
        Resource dict, or None if not found.
    """
    if not resource_id:
        return None
    index = get_resource_index_snapshot()
    by_id: dict[str, RowPosition] = index.get("by_resource_id", {})
    row_position = by_id.get(str(resource_id))
    if row_position is not None:
        rows = _records_from_index(index, [int(row_position)])
        if rows:
            return rows[0]

    # Backward-compatible fallback for call sites/tests that patch get_all_resources.
    target = str(resource_id)
    for resource in get_all_resources():
        if str(resource.get("RESOURCEID")) == target:
            return resource
    return None


def get_resources_by_ids(resource_ids: list[str]) -> list[ResourceRecord]:
    """依 RESOURCEID 清單批次取得設備資料.

    Args:
        resource_ids: List of RESOURCEIDs to look up.

    Returns:
        List of matching resource dicts.
    """
    index = get_resource_index_snapshot()
    by_id: dict[str, RowPosition] = index.get("by_resource_id", {})
    positions = [by_id[str(resource_id)] for resource_id in resource_ids if str(resource_id) in by_id]
    if positions:
        rows = _records_from_index(index, positions)
        if rows:
            return rows

    # Backward-compatible fallback for call sites/tests that patch get_all_resources.
    id_set = set(resource_ids)
    return [r for r in get_all_resources() if r.get('RESOURCEID') in id_set]


def get_resources_by_filter(
    workcenters: list[str] | None = None,
    families: list[str] | None = None,
    departments: list[str] | None = None,
    locations: list[str] | None = None,
    is_production: bool | None = None,
    is_key: bool | None = None,
    is_monitor: bool | None = None,
) -> list[ResourceRecord]:
    """依條件篩選設備資料（在 Python 端篩選）.

    Args:
        workcenters: Filter by WORKCENTERNAME values.
        families: Filter by RESOURCEFAMILYNAME values.
        departments: Filter by PJ_DEPARTMENT values.
        locations: Filter by LOCATIONNAME values.
        is_production: Filter by PJ_ISPRODUCTION flag.
        is_key: Filter by PJ_ISKEY flag.
        is_monitor: Filter by PJ_ISMONITOR flag.

    Returns:
        List of matching resource dicts.
    """
    def _filter_from_records(resources: list[ResourceRecord]) -> list[ResourceRecord]:
        result: list[ResourceRecord] = []
        for r in resources:
            if workcenters and r.get('WORKCENTERNAME') not in workcenters:
                continue
            if families and r.get('RESOURCEFAMILYNAME') not in families:
                continue
            if departments and r.get('PJ_DEPARTMENT') not in departments:
                continue
            if locations and r.get('LOCATIONNAME') not in locations:
                continue
            if is_production is not None and (r.get('PJ_ISPRODUCTION') == 1) != is_production:
                continue
            if is_key is not None and (r.get('PJ_ISKEY') == 1) != is_key:
                continue
            if is_monitor is not None and (r.get('PJ_ISMONITOR') == 1) != is_monitor:
                continue
            result.append(r)
        return result

    index = get_resource_index_snapshot()
    if not index.get("ready"):
        return _filter_from_records(get_all_resources())
    if _resource_df_cache.get(RESOURCE_DF_CACHE_KEY) is None:
        return _filter_from_records(get_all_resources())

    candidate_positions: set[int] = set(int(pos) for pos in index.get("all_positions", []))
    if not candidate_positions:
        return []

    def _intersect_with_positions(selected: list[int] | None) -> None:
        nonlocal candidate_positions
        if selected is None:
            return
        candidate_positions &= set(int(item) for item in selected)

    if workcenters:
        _intersect_with_positions(
            _pick_bucket_positions(index.get("by_workcenter", {}), workcenters)
        )
    if families:
        _intersect_with_positions(
            _pick_bucket_positions(index.get("by_family", {}), families)
        )
    if departments:
        _intersect_with_positions(
            _pick_bucket_positions(index.get("by_department", {}), departments)
        )
    if locations:
        _intersect_with_positions(
            _pick_bucket_positions(index.get("by_location", {}), locations)
        )
    if is_production is not None:
        _intersect_with_positions(
            index.get("by_is_production", {}).get(TRUE_BUCKET if is_production else FALSE_BUCKET, [])
        )
    if is_key is not None:
        _intersect_with_positions(
            index.get("by_is_key", {}).get(TRUE_BUCKET if is_key else FALSE_BUCKET, [])
        )
    if is_monitor is not None:
        _intersect_with_positions(
            index.get("by_is_monitor", {}).get(TRUE_BUCKET if is_monitor else FALSE_BUCKET, [])
        )

    return _records_from_index(index, sorted(candidate_positions))


# ============================================================
# Distinct Values API (for filters)
# ============================================================

def get_distinct_values(column: str) -> list[str]:
    """取得指定欄位的唯一值清單（排序後）.

    Args:
        column: Column name (e.g., 'RESOURCEFAMILYNAME').

    Returns:
        Sorted list of unique values (excluding None, NaN, and empty strings).
    """
    resources = get_all_resources()
    values = set()
    for r in resources:
        val = r.get(column)
        # Skip None, empty strings, and NaN (pandas converts NaN to float)
        if val is None or val == '':
            continue
        # Check for NaN (float type and is NaN)
        if isinstance(val, float) and pd.isna(val):
            continue
        values.add(str(val) if not isinstance(val, str) else val)
    return sorted(values)


def get_resource_families() -> list[str]:
    """取得型號清單（便捷方法）."""
    return get_distinct_values('RESOURCEFAMILYNAME')


def get_workcenters() -> list[str]:
    """取得站點清單（便捷方法）."""
    return get_distinct_values('WORKCENTERNAME')


def get_departments() -> list[str]:
    """取得部門清單（便捷方法）."""
    return get_distinct_values('PJ_DEPARTMENT')


def get_locations() -> list[str]:
    """取得區域清單（便捷方法）."""
    return get_distinct_values('LOCATIONNAME')


def get_vendors() -> list[str]:
    """取得供應商清單（便捷方法）."""
    return get_distinct_values('VENDORNAME')


def get_resource_cascade_metadata() -> list[dict]:
    """取得所有設備的輕量 metadata 供前端 cascade 篩選.

    利用已快取的 get_all_resources() + filter_cache.get_workcenter_mapping()
    產生前端所需的最小資料集。

    Returns:
        List of dicts with keys: id, name, family, workcenter,
        workcenterGroup, isProduction, isKey, isMonitor
    """
    from mes_dashboard.services.filter_cache import get_workcenter_mapping

    wc_mapping = get_workcenter_mapping() or {}
    return [
        {
            'id': r.get('RESOURCEID', ''),
            'name': r.get('RESOURCENAME', ''),
            'family': r.get('RESOURCEFAMILYNAME', ''),
            'workcenter': r.get('WORKCENTERNAME', ''),
            'workcenterGroup': (wc_mapping.get(r.get('WORKCENTERNAME')) or {}).get('group', ''),
            'isProduction': bool(r.get('PJ_ISPRODUCTION')),
            'isKey': bool(r.get('PJ_ISKEY')),
            'isMonitor': bool(r.get('PJ_ISMONITOR')),
        }
        for r in get_all_resources()
    ]
