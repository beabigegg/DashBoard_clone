# -*- coding: utf-8 -*-
"""Redis client management for MES Dashboard WIP cache."""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Iterator, Literal, Optional
from urllib.parse import urlsplit, urlunsplit

import redis

logger = logging.getLogger('mes_dashboard.redis')

# ============================================================
# Configuration from environment variables
# ============================================================

REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
REDIS_ENABLED = os.getenv('REDIS_ENABLED', 'true').lower() == 'true'
REDIS_KEY_PREFIX = os.getenv('REDIS_KEY_PREFIX', 'mes_wip')

# Control-plane Redis URL (defaults to REDIS_URL when not set).
# Point this to a Redis instance / DB with maxmemory-policy=noeviction so that
# locks, job status, and inflight state are never evicted under memory pressure.
# Cache-plane data (spool metadata, snapshot payloads) uses REDIS_URL which may
# have a volatile-lru or allkeys-lru eviction policy for memory management.
REDIS_CONTROL_URL = os.getenv('REDIS_CONTROL_URL', REDIS_URL)

# ============================================================
# Redis Client Singletons
# ============================================================

_REDIS_CLIENT: Optional[redis.Redis] = None
_REDIS_CONTROL_CLIENT: Optional[redis.Redis] = None


def redact_connection_url(url: str) -> str:
    """Redact credentials in URL-like connection strings."""
    if not url:
        return url
    try:
        parsed = urlsplit(url)
    except Exception:
        return url

    netloc = parsed.netloc
    if "@" not in netloc:
        return url

    credentials, host = netloc.rsplit("@", 1)
    if ":" in credentials:
        user, _password = credentials.split(":", 1)
        masked = f"{user}:***" if user else "***"
    else:
        masked = "***"

    return urlunsplit(
        (parsed.scheme, f"{masked}@{host}", parsed.path, parsed.query, parsed.fragment)
    )


def get_redis_client() -> Optional[redis.Redis]:
    """Get Redis client with connection pooling and health check.

    Returns:
        Redis client instance, or None if Redis is disabled or unavailable.
    """
    global _REDIS_CLIENT

    if not REDIS_ENABLED:
        logger.debug("Redis is disabled via REDIS_ENABLED=false")
        return None

    if _REDIS_CLIENT is None:
        try:
            _REDIS_CLIENT = redis.Redis.from_url(
                REDIS_URL,
                decode_responses=True,
                socket_timeout=5,
                socket_connect_timeout=5,
                retry_on_timeout=True,
                health_check_interval=30
            )
            # Test connection
            _REDIS_CLIENT.ping()
            logger.info("Redis client connected to %s", redact_connection_url(REDIS_URL))
        except redis.RedisError as e:
            logger.warning(f"Failed to connect to Redis: {e}")
            _REDIS_CLIENT = None
            return None

    return _REDIS_CLIENT


def get_control_redis_client() -> Optional[redis.Redis]:
    """Get the control-plane Redis client.

    Used for keys that must not be evicted under memory pressure: distributed
    locks, job status HSET, and inflight state.  Configured via REDIS_CONTROL_URL
    (defaults to REDIS_URL when not set, so single-instance deployments work
    without any extra configuration).
    """
    global _REDIS_CONTROL_CLIENT

    if not REDIS_ENABLED:
        return None

    # Fast-path: reuse cache client when both URLs are identical
    if REDIS_CONTROL_URL == REDIS_URL:
        return get_redis_client()

    if _REDIS_CONTROL_CLIENT is None:
        try:
            _REDIS_CONTROL_CLIENT = redis.Redis.from_url(
                REDIS_CONTROL_URL,
                decode_responses=True,
                socket_timeout=5,
                socket_connect_timeout=5,
                retry_on_timeout=True,
                health_check_interval=30,
            )
            _REDIS_CONTROL_CLIENT.ping()
            logger.info(
                "Control-plane Redis client connected to %s",
                redact_connection_url(REDIS_CONTROL_URL),
            )
        except redis.RedisError as exc:
            logger.warning("Failed to connect to control-plane Redis: %s", exc)
            _REDIS_CONTROL_CLIENT = None
            return None

    return _REDIS_CONTROL_CLIENT


def redis_available() -> bool:
    """Check if Redis connection is available.

    Returns:
        True if Redis is enabled and responding to PING.
    """
    if not REDIS_ENABLED:
        return False

    client = get_redis_client()
    if client is None:
        return False

    try:
        client.ping()
        return True
    except redis.RedisError as e:
        logger.warning(f"Redis health check failed: {e}")
        return False


def get_key(key: str) -> str:
    """Get full Redis key with prefix.

    Args:
        key: Key name without prefix (e.g., "meta:sys_date")

    Returns:
        Full key with prefix (e.g., "mes_wip:meta:sys_date")
    """
    return f"{REDIS_KEY_PREFIX}:{key}"


def get_key_prefix() -> str:
    """Get the Redis key prefix.

    Returns:
        The configured key prefix (e.g., "mes_wip")
    """
    return REDIS_KEY_PREFIX


def close_redis() -> None:
    """Close Redis connections.

    Call this during application shutdown.
    """
    global _REDIS_CLIENT, _REDIS_CONTROL_CLIENT

    if _REDIS_CLIENT is not None:
        try:
            _REDIS_CLIENT.close()
            logger.info("Redis connection closed")
        except Exception as e:
            logger.warning(f"Error closing Redis connection: {e}")
        finally:
            _REDIS_CLIENT = None

    # Only close control client if it's a separate connection
    if _REDIS_CONTROL_CLIENT is not None:
        try:
            _REDIS_CONTROL_CLIENT.close()
            logger.info("Control-plane Redis connection closed")
        except Exception as e:
            logger.warning(f"Error closing control-plane Redis connection: {e}")
        finally:
            _REDIS_CONTROL_CLIENT = None


def try_acquire_lock(
    lock_name: str,
    ttl_seconds: int = 60,
    *,
    fail_mode: Literal["closed", "raise", "open"],
) -> bool:
    """Try to acquire a distributed lock using Redis SET NX.

    Uses the control-plane Redis client so locks are not subject to cache
    eviction pressure.  Non-blocking: returns False immediately if held.

    Spec: ``distributed-lock-policy`` (openspec/changes/redis-lock-policy).

    Args:
        lock_name: Name of the lock (will be prefixed with key prefix).
        ttl_seconds: Lock expiration time in seconds (prevents deadlocks).
        fail_mode: Required keyword-only argument controlling behaviour when
            Redis is unavailable or raises an exception:

            ``"closed"``
                Return ``False`` — the caller must treat the protected
                operation as "don't run now".  Use this for cache-refresh
                patterns where serving stale data for one tick is acceptable.

            ``"raise"``
                Raise :class:`~mes_dashboard.core.exceptions.LockUnavailableError`
                — the caller must catch it and abort the current tick cleanly.
                Use this for leader-election patterns where running without
                exclusivity is a correctness bug.

            ``"open"``
                Log a warning and return ``True`` (previous behaviour).
                Use **only** when duplicate execution is genuinely cheap and
                idempotent.  Each opt-in site MUST carry a
                ``# fail_mode=open: <reason>`` comment.

    Returns:
        True if lock was acquired, False if already held by another process.
        Under ``fail_mode="closed"`` or ``fail_mode="open"`` also returns a
        boolean when Redis is unavailable.

    Raises:
        LockUnavailableError: When Redis is unavailable and
            ``fail_mode="raise"``.
    """
    from mes_dashboard.core.exceptions import LockUnavailableError
    from mes_dashboard.core.heavy_query_telemetry import record_lock_fail_mode_triggered

    def _handle_failure(cause: Optional[Exception]) -> bool:
        record_lock_fail_mode_triggered(lock_name, fail_mode)
        if fail_mode == "closed":
            logger.warning(f"Redis unavailable, skipping lock for {lock_name} (fail-closed)")
            return False
        elif fail_mode == "raise":
            logger.warning(f"Redis unavailable, raising for lock {lock_name} (fail-raise)")
            raise LockUnavailableError(
                f"Could not acquire lock '{lock_name}': Redis unavailable",
                details={"lock_name": lock_name},
                cause=cause,
            ) from cause
        else:  # "open"
            logger.warning(f"Redis unavailable, proceeding without lock for {lock_name} (fail-open)")
            return True

    client = get_control_redis_client()
    if client is None:
        return _handle_failure(None)

    try:
        lock_key = f"{REDIS_KEY_PREFIX}:lock:{lock_name}"
        # SET NX EX is atomic: only sets if key doesn't exist
        acquired = client.set(lock_key, str(os.getpid()), nx=True, ex=ttl_seconds)
        if acquired:
            logger.debug(f"Acquired lock: {lock_name}")
        else:
            logger.debug(f"Lock already held: {lock_name}")
        return bool(acquired)
    except Exception as e:
        logger.warning(f"Failed to acquire lock {lock_name}: {e}")
        return _handle_failure(e)


@contextmanager
def with_distributed_lock(
    name: str,
    ttl_seconds: int = 60,
    *,
    fail_mode: Literal["closed", "raise", "open"],
) -> Iterator[bool]:
    """Context manager wrapping :func:`try_acquire_lock` and :func:`release_lock`.

    Yields ``True`` if the lock was acquired, ``False`` if not (only possible
    under ``fail_mode="closed"``).  Under ``fail_mode="raise"`` a
    :class:`~mes_dashboard.core.exceptions.LockUnavailableError` propagates
    before the body is entered.

    The lock is released in a ``finally`` block only when it was acquired.

    Example::

        with with_distributed_lock("my_job", ttl_seconds=120, fail_mode="closed") as acquired:
            if not acquired:
                return  # Redis unavailable, skip this tick
            do_expensive_work()

    Import path: ``from mes_dashboard.core.redis_client import with_distributed_lock``
    """
    acquired = try_acquire_lock(name, ttl_seconds, fail_mode=fail_mode)
    if not acquired:
        yield False
        return
    try:
        yield True
    finally:
        release_lock(name)


def release_lock(lock_name: str) -> None:
    """Release a distributed lock.

    Args:
        lock_name: Name of the lock to release.
    """
    client = get_control_redis_client()
    if client is None:
        return

    try:
        lock_key = f"{REDIS_KEY_PREFIX}:lock:{lock_name}"
        client.delete(lock_key)
        logger.debug(f"Released lock: {lock_name}")
    except Exception as e:
        logger.warning(f"Failed to release lock {lock_name}: {e}")
