# -*- coding: utf-8 -*-
"""Global Redis-based concurrency limiter for heavy queries.

Uses a Redis sorted set where each member is an owner_id and the score is
the epoch timestamp when the slot was acquired.  A Lua script performs
atomic expire-cleanup + count-check + add in one round-trip.

Usage:
    acquired = acquire_heavy_query_slot(owner_id)
    try:
        ...execute query...
    finally:
        if acquired:
            release_heavy_query_slot(owner_id)
"""

from __future__ import annotations

import logging
import os
import time
from typing import Optional

from mes_dashboard.core.redis_client import get_key, get_redis_client

logger = logging.getLogger("mes_dashboard.global_concurrency")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
HEAVY_QUERY_MAX_CONCURRENT = int(os.getenv("HEAVY_QUERY_MAX_CONCURRENT", "3"))
_SLOT_KEY_SUFFIX = "heavy_query_slots"

# Lua script: atomically remove expired members, then conditionally add owner.
# KEYS[1] = sorted-set key
# ARGV[1] = current time as float string
# ARGV[2] = expiry cutoff (current_time - ttl)
# ARGV[3] = max concurrent
# ARGV[4] = owner_id
# ARGV[5] = ttl seconds
# Returns 1 if slot acquired, 0 if limit reached.
_LUA_ACQUIRE = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local cutoff = tonumber(ARGV[2])
local max_concurrent = tonumber(ARGV[3])
local owner = ARGV[4]
local ttl = tonumber(ARGV[5])

-- Remove expired entries
redis.call('ZREMRANGEBYSCORE', key, '-inf', cutoff)

-- Count active slots
local active = redis.call('ZCARD', key)
if active >= max_concurrent then
    return 0
end

-- Add owner with score = now + ttl (so it auto-expires conceptually)
redis.call('ZADD', key, now + ttl, owner)
redis.call('EXPIRE', key, math.ceil(ttl * 2))
return 1
"""

_acquire_script = None


def _get_acquire_script(conn):
    global _acquire_script
    if _acquire_script is None:
        _acquire_script = conn.register_script(_LUA_ACQUIRE)
    return _acquire_script


def _slot_key() -> str:
    return get_key(_SLOT_KEY_SUFFIX)


def acquire_heavy_query_slot(owner_id: str, ttl: int = 600) -> bool:
    """Try to acquire a heavy query concurrency slot.

    Args:
        owner_id: Unique identifier for this query (e.g., "{pid}:{uuid}").
        ttl: Seconds until the slot is considered stale (fail-safe expiry).

    Returns:
        True if slot acquired, False if at the concurrency limit.
        Returns True on Redis failure (fail-open).
    """
    conn = get_redis_client()
    if conn is None:
        return True  # fail-open

    try:
        script = _get_acquire_script(conn)
        now = time.time()
        cutoff = now - ttl
        result = script(
            keys=[_slot_key()],
            args=[str(now), str(cutoff), str(HEAVY_QUERY_MAX_CONCURRENT), owner_id, str(ttl)],
        )
        acquired = bool(result)
        if not acquired:
            logger.info(
                "global_concurrency: slot not acquired (at limit=%d) owner=%s",
                HEAVY_QUERY_MAX_CONCURRENT,
                owner_id,
            )
        return acquired
    except Exception as exc:
        logger.warning("global_concurrency: acquire_heavy_query_slot error (fail-open): %s", exc)
        return True  # fail-open


def release_heavy_query_slot(owner_id: str) -> None:
    """Release a heavy query concurrency slot."""
    conn = get_redis_client()
    if conn is None:
        return
    try:
        conn.zrem(_slot_key(), owner_id)
    except Exception as exc:
        logger.warning("global_concurrency: release_heavy_query_slot error: %s", exc)


def get_active_slot_count() -> int:
    """Return current number of active heavy query slots (best-effort)."""
    conn = get_redis_client()
    if conn is None:
        return 0
    try:
        now = time.time()
        # Remove truly expired entries first (TTL 600s default)
        conn.zremrangebyscore(_slot_key(), "-inf", now - 600)
        return int(conn.zcard(_slot_key()))
    except Exception:
        return 0
