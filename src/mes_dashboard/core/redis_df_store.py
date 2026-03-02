# -*- coding: utf-8 -*-
"""Reusable parquet-in-Redis DataFrame store.

Extracted from reject/hold/resource_dataset_cache to eliminate
duplication.  Provides both general-purpose store/load and
chunk-level helpers for BatchQueryEngine.
"""

from __future__ import annotations

import base64
import io
import logging
from decimal import Decimal
from numbers import Real
from typing import Optional

import pandas as pd

from mes_dashboard.core.redis_client import (
    REDIS_ENABLED,
    get_key,
    get_redis_client,
)

logger = logging.getLogger("mes_dashboard.redis_df_store")


# ============================================================
# General-purpose DataFrame ↔ Redis
# ============================================================


def _normalize_decimal_object_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize object columns that contain Decimal values.

    PyArrow parquet serialization can fail on mixed Decimal precision in an
    object-typed column. For numeric-like mixed precision Decimal columns,
    coerce to float. For mixed-type columns, cast Decimal values to string.
    """
    if df is None or df.empty:
        return df

    normalized = df.copy()
    for col in normalized.columns:
        series = normalized[col]
        if series.dtype != "object":
            continue

        non_null = series.dropna()
        if non_null.empty:
            continue

        has_decimal = non_null.map(lambda value: isinstance(value, Decimal)).any()
        if not has_decimal:
            continue

        is_numeric_like = non_null.map(
            lambda value: isinstance(value, (Decimal, Real)) and not isinstance(value, bool)
        ).all()
        if is_numeric_like:
            normalized[col] = pd.to_numeric(series, errors="coerce")
        else:
            normalized[col] = series.map(
                lambda value: str(value) if isinstance(value, Decimal) else value
            )

    return normalized


def redis_store_df(key: str, df: pd.DataFrame, ttl: int = 900) -> bool:
    """Serialize *df* to parquet, base64-encode, and SETEX into Redis.

    Args:
        key: Redis key (will be prefixed via ``get_key``).
        df: DataFrame to store.
        ttl: Expiry in seconds (default 900 = 15 min).
    """
    if not REDIS_ENABLED:
        return False
    client = get_redis_client()
    if client is None:
        return False
    try:
        normalized = _normalize_decimal_object_columns(df)
        buf = io.BytesIO()
        normalized.to_parquet(buf, engine="pyarrow", index=False)
        encoded = base64.b64encode(buf.getvalue()).decode("ascii")
        client.setex(get_key(key), ttl, encoded)
        return True
    except Exception as exc:
        logger.warning("Failed to store DataFrame in Redis (%s): %s", key, exc)
        return False


def redis_load_df(key: str) -> Optional[pd.DataFrame]:
    """Load a parquet-encoded DataFrame from Redis.

    Returns ``None`` when the key is missing or Redis is unavailable.
    """
    if not REDIS_ENABLED:
        return None
    client = get_redis_client()
    if client is None:
        return None
    try:
        encoded = client.get(get_key(key))
        if encoded is None:
            return None
        raw = base64.b64decode(encoded)
        return pd.read_parquet(io.BytesIO(raw), engine="pyarrow")
    except Exception as exc:
        logger.warning("Failed to load DataFrame from Redis (%s): %s", key, exc)
        return None


# ============================================================
# Chunk-level helpers (used by BatchQueryEngine)
# ============================================================


def _chunk_key(cache_prefix: str, query_hash: str, idx: int) -> str:
    """Build the raw key (before global prefix) for a single chunk."""
    return f"batch:{cache_prefix}:{query_hash}:chunk:{idx}"


def _meta_key(cache_prefix: str, query_hash: str) -> str:
    """Build the raw key for batch metadata."""
    return f"batch:{cache_prefix}:{query_hash}:meta"


def redis_store_chunk(
    cache_prefix: str,
    query_hash: str,
    idx: int,
    df: pd.DataFrame,
    ttl: int = 900,
) -> bool:
    """Store a single chunk DataFrame in Redis."""
    return redis_store_df(_chunk_key(cache_prefix, query_hash, idx), df, ttl=ttl)


def redis_load_chunk(
    cache_prefix: str,
    query_hash: str,
    idx: int,
) -> Optional[pd.DataFrame]:
    """Load a single chunk DataFrame from Redis."""
    return redis_load_df(_chunk_key(cache_prefix, query_hash, idx))


def redis_chunk_exists(
    cache_prefix: str,
    query_hash: str,
    idx: int,
) -> bool:
    """Check whether a chunk key exists in Redis (without loading data)."""
    if not REDIS_ENABLED:
        return False
    client = get_redis_client()
    if client is None:
        return False
    try:
        return bool(client.exists(get_key(_chunk_key(cache_prefix, query_hash, idx))))
    except Exception as exc:
        logger.warning("redis_chunk_exists failed: %s", exc)
        return False


def redis_clear_batch(cache_prefix: str, query_hash: str) -> int:
    """Delete cached chunk/meta keys for a batch query hash.

    Returns the number of deleted keys.
    """
    if not REDIS_ENABLED:
        return 0
    client = get_redis_client()
    if client is None:
        return 0
    try:
        chunk_pattern = get_key(f"batch:{cache_prefix}:{query_hash}:chunk:*")
        meta_key = get_key(_meta_key(cache_prefix, query_hash))
        chunk_keys = client.keys(chunk_pattern) or []
        delete_keys = list(chunk_keys) + [meta_key]
        if not delete_keys:
            return 0
        return int(client.delete(*delete_keys) or 0)
    except Exception as exc:
        logger.warning(
            "redis_clear_batch failed (prefix=%s, query_hash=%s): %s",
            cache_prefix,
            query_hash,
            exc,
        )
        return 0
