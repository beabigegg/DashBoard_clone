# -*- coding: utf-8 -*-
"""Global Redis-based concurrency limiter for RQ heavy Oracle queries.

``HEAVY_QUERY_MAX_CONCURRENT`` bounds the number of RQ heavy jobs concurrently
hitting Oracle (cross-job semaphore), not synchronous gunicorn request workers.
The slot is acquired **inside** the RQ worker around the Oracle fetch (per
blueprint §4.2), not at route enqueue time.

Uses a Redis sorted set where each member is an owner_id and the score is
the epoch timestamp when the slot was acquired.  A Lua script performs
atomic expire-cleanup + count-check + add in one round-trip.  Fail-open when
Redis is unavailable.  Lua/fail-open/TTL mechanics are unchanged
(query-path-c-elimination-cleanup, IP-8, D3).

Usage (inside an RQ worker, around the Oracle fetch):
    acquired = acquire_heavy_query_slot(owner_id)
    try:
        ...execute Oracle query...
    finally:
        if acquired:
            release_heavy_query_slot(owner_id)
"""

from __future__ import annotations

import logging
import os
import time
from contextlib import contextmanager

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
    """Try to acquire a heavy Oracle concurrency slot for an RQ worker job.

    Called inside the RQ worker around the Oracle fetch — NOT at route enqueue
    time (D3 / blueprint §4.2).  This caps concurrent RQ jobs hitting Oracle
    simultaneously; it does not throttle gunicorn request workers.

    Args:
        owner_id: Unique identifier for this job (e.g., "{job_type}:{job_id}").
        ttl: Seconds until the slot is considered stale (fail-safe expiry).

    Returns:
        True if slot acquired (or Redis unavailable — fail-open).
        False if at the ``HEAVY_QUERY_MAX_CONCURRENT`` concurrency limit.
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


@contextmanager
def heavy_query_slot(owner: str, ttl: int = 600):
    """Exception-safe context manager around one heavy Oracle concurrency slot.

    Wraps ``acquire_heavy_query_slot`` / ``release_heavy_query_slot`` so callers
    can use a ``with`` statement instead of a bare try/finally.  Release is
    guarded by the ``acquired`` bool so a fail-open (acquired=False, cap reached)
    path never calls release for a slot it never counted.

    Usage (inside an RQ worker, around the Oracle fetch only):

        with heavy_query_slot(f"{job_type}:{job_id}"):
            result = execute_primary_query(...)

    The yielded value is the ``acquired`` bool — useful for logging but can be
    ignored (the Oracle call proceeds either way per fail-open semantics).

    Args:
        owner: Unique identifier for this job (e.g., "hold-history:job-uuid").
        ttl:   Seconds until the slot is considered stale (passed to acquire).

    Yields:
        bool — True if the slot was acquired; False if at capacity (fail-open).
    """
    acquired = acquire_heavy_query_slot(owner, ttl=ttl)
    try:
        yield acquired
    finally:
        if acquired:
            release_heavy_query_slot(owner)


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
