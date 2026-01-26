"""Cache abstraction for MES Dashboard."""

from __future__ import annotations

import json
from typing import Any, Optional, Protocol

from flask import current_app

from mes_dashboard.config.constants import CACHE_TTL_DEFAULT


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
