# -*- coding: utf-8 -*-
"""Cache abstraction for MES Dashboard.

Provides table-level caching for WIP data using Redis.
Falls back to Oracle direct query when Redis is unavailable.
"""

from __future__ import annotations

import io
import json
import logging
import threading
import time
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

    def __init__(self, ttl_seconds: int = 30):
        self._cache: dict[str, Tuple[pd.DataFrame, float]] = {}
        self._lock = threading.Lock()
        self._ttl = ttl_seconds

    def get(self, key: str) -> Optional[pd.DataFrame]:
        """Get cached DataFrame if not expired."""
        with self._lock:
            if key not in self._cache:
                return None
            df, timestamp = self._cache[key]
            if time.time() - timestamp > self._ttl:
                del self._cache[key]
                return None
            return df

    def set(self, key: str, df: pd.DataFrame) -> None:
        """Cache a DataFrame with current timestamp."""
        with self._lock:
            self._cache[key] = (df, time.time())

    def invalidate(self, key: str) -> None:
        """Remove a key from cache."""
        with self._lock:
            self._cache.pop(key, None)

    def clear(self) -> None:
        """Clear all cached data."""
        with self._lock:
            self._cache.clear()


# Global process-level cache for WIP DataFrame (30s TTL)
_wip_df_cache = ProcessLevelCache(ttl_seconds=30)
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

    # Use lock to prevent multiple threads from parsing simultaneously
    with _wip_parse_lock:
        # Double-check after acquiring lock (another thread may have parsed)
        cached_df = _wip_df_cache.get(cache_key)
        if cached_df is not None:
            logger.debug(f"Process cache hit (after lock): {len(cached_df)} rows")
            return cached_df

        try:
            start_time = time.time()
            data_json = client.get(get_key("data"))
            if data_json is None:
                logger.debug("Cache miss: no data in Redis")
                return None

            # Parse JSON to DataFrame
            df = pd.read_json(io.StringIO(data_json), orient='records')
            parse_time = time.time() - start_time

            # Store in process-level cache
            _wip_df_cache.set(cache_key, df)

            logger.debug(f"Cache hit: loaded {len(df)} rows from Redis (parsed in {parse_time:.2f}s)")
            return df
        except Exception as e:
            logger.warning(f"Failed to read cache: {e}")
            return None


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
