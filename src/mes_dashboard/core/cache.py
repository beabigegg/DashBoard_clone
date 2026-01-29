# -*- coding: utf-8 -*-
"""Cache abstraction for MES Dashboard.

Provides table-level caching for WIP data using Redis.
Falls back to Oracle direct query when Redis is unavailable.
"""

from __future__ import annotations

import io
import json
import logging
from typing import Any, Optional, Protocol

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
    """Get cached WIP data from Redis.

    Returns:
        DataFrame with full DW_PJ_LOT_V data, or None if cache miss.
    """
    if not REDIS_ENABLED:
        return None

    client = get_redis_client()
    if client is None:
        return None

    try:
        data_json = client.get(get_key("data"))
        if data_json is None:
            logger.debug("Cache miss: no data in Redis")
            return None

        # Use StringIO to wrap the JSON string for pd.read_json
        df = pd.read_json(io.StringIO(data_json), orient='records')
        logger.debug(f"Cache hit: loaded {len(df)} rows from Redis")
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
