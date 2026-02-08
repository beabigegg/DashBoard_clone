# -*- coding: utf-8 -*-
"""Cache abstraction for MES Dashboard.

Provides table-level caching for WIP data using Redis.
Falls back to Oracle direct query when Redis is unavailable.
"""

from __future__ import annotations

import io
import json
import logging
import os
import threading
import time
from collections import OrderedDict
from typing import Any, Optional, Protocol, Tuple

import pandas as pd
from flask import current_app

from mes_dashboard.config.constants import CACHE_TTL_DEFAULT
from mes_dashboard.core.redis_client import (
    get_redis_client,
    get_key,
    redis_available,
    REDIS_ENABLED
)

logger = logging.getLogger('mes_dashboard.cache')


# ============================================================
# Process-Level DataFrame Cache (Prevents redundant JSON parsing)
# ============================================================

class ProcessLevelCache:
    """Thread-safe process-level cache for parsed DataFrames.

    Prevents redundant JSON parsing across concurrent requests.
    Uses a lock to ensure only one thread parses at a time.
    """

    def __init__(self, ttl_seconds: int = 30, max_size: int = 32):
        self._cache: OrderedDict[str, Tuple[pd.DataFrame, float]] = OrderedDict()
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

    def get(self, key: str) -> Optional[pd.DataFrame]:
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

    def clear(self) -> None:
        """Clear all cached data."""
        with self._lock:
            self._cache.clear()


def _resolve_cache_max_size(env_name: str, default: int) -> int:
    value = os.getenv(env_name)
    if value is None:
        return max(int(default), 1)
    try:
        return max(int(value), 1)
    except (TypeError, ValueError):
        return max(int(default), 1)


# Global process-level cache for WIP DataFrame (30s TTL)
PROCESS_CACHE_MAX_SIZE = _resolve_cache_max_size("PROCESS_CACHE_MAX_SIZE", 32)
WIP_PROCESS_CACHE_MAX_SIZE = _resolve_cache_max_size(
    "WIP_PROCESS_CACHE_MAX_SIZE",
    PROCESS_CACHE_MAX_SIZE,
)
_wip_df_cache = ProcessLevelCache(
    ttl_seconds=30,
    max_size=WIP_PROCESS_CACHE_MAX_SIZE,
)
_wip_parse_lock = threading.Lock()

# ============================================================
# Legacy Cache Backend Interface (for backwards compatibility)
# ============================================================


class CacheBackend(Protocol):
    """Protocol for cache backends."""

    def get(self, key: str) -> Optional[Any]:
        ...

    def set(self, key: str, value: Any, ttl: int) -> None:
        ...


class NoOpCache:
    """No-op cache backend (default)."""

    def get(self, key: str) -> Optional[Any]:
        return None

    def set(self, key: str, value: Any, ttl: int) -> None:
        return None


class MemoryTTLCache:
    """Thread-safe in-memory TTL cache backend.

    This is used as the L1 cache for route-level API responses.
    """

    def __init__(self) -> None:
        self._store: dict[str, tuple[Any, float]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        now = time.time()
        with self._lock:
            payload = self._store.get(key)
            if payload is None:
                return None
            value, expires_at = payload
            if expires_at <= now:
                self._store.pop(key, None)
                return None
            return value

    def set(self, key: str, value: Any, ttl: int) -> None:
        expires_at = time.time() + max(ttl, 1)
        with self._lock:
            self._store[key] = (value, expires_at)

    def size(self) -> int:
        """Return live key count (best effort)."""
        with self._lock:
            return len(self._store)


class RedisJSONCache:
    """Redis cache backend for JSON-serializable API responses."""

    def __init__(self, namespace: str = "route_cache") -> None:
        self._namespace = namespace
        self._error_count = 0
        self._last_error: str | None = None
        self._last_error_at: float | None = None

    def _full_key(self, key: str) -> str:
        return get_key(f"{self._namespace}:{key}")

    def get(self, key: str) -> Optional[Any]:
        if not REDIS_ENABLED:
            return None

        client = get_redis_client()
        if client is None:
            return None

        try:
            payload = client.get(self._full_key(key))
            if payload is None:
                return None
            return json.loads(payload)
        except Exception as exc:
            logger.warning("Failed to read route cache from Redis: %s", exc)
            self._error_count += 1
            self._last_error = str(exc)
            self._last_error_at = time.time()
            return None

    def set(self, key: str, value: Any, ttl: int) -> None:
        if not REDIS_ENABLED:
            return

        client = get_redis_client()
        if client is None:
            return

        try:
            payload = json.dumps(value, ensure_ascii=False, default=str)
            client.setex(self._full_key(key), max(ttl, 1), payload)
        except Exception as exc:
            logger.warning("Failed to write route cache to Redis: %s", exc)
            self._error_count += 1
            self._last_error = str(exc)
            self._last_error_at = time.time()

    def telemetry(self) -> dict[str, Any]:
        return {
            "namespace": self._namespace,
            "error_count": self._error_count,
            "last_error": self._last_error,
            "last_error_at": self._last_error_at,
        }


class LayeredCache:
    """L1 memory + L2 Redis cache backend."""

    def __init__(
        self,
        l1: MemoryTTLCache,
        l2: Optional[RedisJSONCache] = None,
        redis_expected: bool = False,
    ):
        self._l1 = l1
        self._l2 = l2
        self._redis_expected = redis_expected
        self._l1_hits = 0
        self._l2_hits = 0
        self._misses = 0
        self._writes = 0

    def get(self, key: str) -> Optional[Any]:
        value = self._l1.get(key)
        if value is not None:
            self._l1_hits += 1
            return value

        if self._l2 is None:
            self._misses += 1
            return None

        value = self._l2.get(key)
        if value is not None:
            # Keep warm in memory for fast subsequent reads.
            self._l1.set(key, value, CACHE_TTL_DEFAULT)
            self._l2_hits += 1
            return value

        self._misses += 1
        return value

    def set(self, key: str, value: Any, ttl: int) -> None:
        self._writes += 1
        self._l1.set(key, value, ttl)
        if self._l2 is not None:
            self._l2.set(key, value, ttl)

    def telemetry(self) -> dict[str, Any]:
        mode = "l1+l2" if self._l2 is not None else "l1-only"
        degraded = self._redis_expected and self._l2 is None
        total_reads = self._l1_hits + self._l2_hits + self._misses
        l1_hit_rate = round(self._l1_hits / total_reads, 4) if total_reads else 0
        l2_hit_rate = round(self._l2_hits / total_reads, 4) if total_reads else 0
        miss_rate = round(self._misses / total_reads, 4) if total_reads else 0
        return {
            "mode": mode,
            "degraded": degraded,
            "redis_expected": self._redis_expected,
            "l1_size": self._l1.size(),
            "reads_total": total_reads,
            "writes_total": self._writes,
            "l1_hits": self._l1_hits,
            "l2_hits": self._l2_hits,
            "misses": self._misses,
            "l1_hit_rate": l1_hit_rate,
            "l2_hit_rate": l2_hit_rate,
            "miss_rate": miss_rate,
            "l2_telemetry": self._l2.telemetry() if self._l2 is not None else None,
        }


def create_default_cache_backend() -> CacheBackend:
    """Create the default route cache backend.

    Uses in-memory TTL cache for all environments and adds Redis as L2
    when Redis is available.
    """
    l1_cache = MemoryTTLCache()
    l2_cache = RedisJSONCache() if redis_available() else None
    return LayeredCache(l1=l1_cache, l2=l2_cache, redis_expected=REDIS_ENABLED)


def get_cache() -> CacheBackend:
    """Return the configured cache backend or a no-op default."""
    try:
        cache = current_app.extensions.get("cache")
    except RuntimeError:
        cache = None
    return cache if cache is not None else NoOpCache()


def cache_get(key: str) -> Optional[Any]:
    """Get value from cache backend."""
    return get_cache().get(key)


def cache_set(key: str, value: Any, ttl: int = CACHE_TTL_DEFAULT) -> None:
    """Set value on cache backend."""
    get_cache().set(key, value, ttl)


def make_cache_key(prefix: str, days_back: Optional[int] = None, filters: Optional[dict] = None) -> str:
    """Generate a cache key from prefix and parameters."""
    filters_key = json.dumps(filters, sort_keys=True, ensure_ascii=False) if filters else ""
    return f"{prefix}:{days_back}:{filters_key}"


# ============================================================
# WIP Table-Level Cache Functions
# ============================================================


def get_cached_wip_data() -> Optional[pd.DataFrame]:
    """Get cached WIP data from Redis with process-level caching.

    Uses a two-tier cache strategy:
    1. Process-level cache: Parsed DataFrame (30s TTL) - fast, no parsing
    2. Redis cache: Raw JSON data - shared across workers

    This prevents redundant JSON parsing of 14+ MB data across
    concurrent requests, significantly improving response times.

    Returns:
        DataFrame with full DWH.DW_MES_LOT_V data, or None if cache miss.
    """
    cache_key = "wip_dataframe"

    # Tier 1: Check process-level cache first (fast path)
    cached_df = _wip_df_cache.get(cache_key)
    if cached_df is not None:
        logger.debug(f"Process cache hit: {len(cached_df)} rows")
        return cached_df

    # Tier 2: Parse from Redis (slow path - needs lock)
    if not REDIS_ENABLED:
        return None

    client = get_redis_client()
    if client is None:
        return None

    try:
        start_time = time.time()
        data_json = client.get(get_key("data"))
        if data_json is None:
            logger.debug("Cache miss: no data in Redis")
            return None

        # Parse outside lock to reduce contention on hot paths.
        parsed_df = pd.read_json(io.StringIO(data_json), orient='records')
        parse_time = time.time() - start_time
    except Exception as e:
        logger.warning(f"Failed to read cache: {e}")
        return None

    # Keep lock scope tight: consistency check + cache write only.
    with _wip_parse_lock:
        cached_df = _wip_df_cache.get(cache_key)
        if cached_df is not None:
            logger.debug(f"Process cache hit (after parse): {len(cached_df)} rows")
            return cached_df
        _wip_df_cache.set(cache_key, parsed_df)

    logger.debug(f"Cache hit: loaded {len(parsed_df)} rows from Redis (parsed in {parse_time:.2f}s)")
    return parsed_df


def get_cached_sys_date() -> Optional[str]:
    """Get cached SYS_DATE from Redis.

    Returns:
        SYS_DATE string or None if not cached.
    """
    if not REDIS_ENABLED:
        return None

    client = get_redis_client()
    if client is None:
        return None

    try:
        return client.get(get_key("meta:sys_date"))
    except Exception as e:
        logger.warning(f"Failed to get cached SYS_DATE: {e}")
        return None


def get_cache_updated_at() -> Optional[str]:
    """Get cache update timestamp from Redis.

    Returns:
        ISO 8601 timestamp string or None.
    """
    if not REDIS_ENABLED:
        return None

    client = get_redis_client()
    if client is None:
        return None

    try:
        return client.get(get_key("meta:updated_at"))
    except Exception as e:
        logger.warning(f"Failed to get cache updated_at: {e}")
        return None


def is_cache_available() -> bool:
    """Check if WIP cache is available and populated.

    Returns:
        True if Redis has cached data.
    """
    if not REDIS_ENABLED:
        return False

    client = get_redis_client()
    if client is None:
        return False

    try:
        return client.exists(get_key("data")) > 0
    except Exception as e:
        logger.warning(f"Failed to check cache availability: {e}")
        return False


def get_wip_data_with_fallback(fallback_fn) -> pd.DataFrame:
    """Get WIP data from cache, falling back to Oracle if needed.

    Args:
        fallback_fn: Function to call for Oracle direct query.
                     Should return a DataFrame.

    Returns:
        DataFrame with WIP data (from cache or Oracle).
    """
    # Try cache first
    df = get_cached_wip_data()
    if df is not None:
        return df

    # Fallback to Oracle
    logger.info("Cache miss or unavailable, falling back to Oracle query")
    return fallback_fn()
