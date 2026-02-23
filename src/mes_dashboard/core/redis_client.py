# -*- coding: utf-8 -*-
"""Redis client management for MES Dashboard WIP cache."""

from __future__ import annotations

import logging
import os
from typing import Optional
from urllib.parse import urlsplit, urlunsplit

import redis

logger = logging.getLogger('mes_dashboard.redis')

# ============================================================
# Configuration from environment variables
# ============================================================

REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
REDIS_ENABLED = os.getenv('REDIS_ENABLED', 'true').lower() == 'true'
REDIS_KEY_PREFIX = os.getenv('REDIS_KEY_PREFIX', 'mes_wip')

# ============================================================
# Redis Client Singleton
# ============================================================

_REDIS_CLIENT: Optional[redis.Redis] = None


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
    """Close Redis connection.

    Call this during application shutdown.
    """
    global _REDIS_CLIENT

    if _REDIS_CLIENT is not None:
        try:
            _REDIS_CLIENT.close()
            logger.info("Redis connection closed")
        except Exception as e:
            logger.warning(f"Error closing Redis connection: {e}")
        finally:
            _REDIS_CLIENT = None


def try_acquire_lock(lock_name: str, ttl_seconds: int = 60) -> bool:
    """Try to acquire a distributed lock using Redis SET NX.

    This is a non-blocking lock acquisition. If the lock is already held,
    returns False immediately without waiting.

    Args:
        lock_name: Name of the lock (will be prefixed with key prefix).
        ttl_seconds: Lock expiration time in seconds (prevents deadlocks).

    Returns:
        True if lock was acquired, False if already held by another process.
    """
    client = get_redis_client()
    if client is None:
        # Redis unavailable - allow operation to proceed (fail-open)
        logger.warning(f"Redis unavailable, skipping lock for {lock_name}")
        return True

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
        # Fail-open: allow operation if Redis has issues
        return True


def release_lock(lock_name: str) -> None:
    """Release a distributed lock.

    Args:
        lock_name: Name of the lock to release.
    """
    client = get_redis_client()
    if client is None:
        return

    try:
        lock_key = f"{REDIS_KEY_PREFIX}:lock:{lock_name}"
        client.delete(lock_key)
        logger.debug(f"Released lock: {lock_name}")
    except Exception as e:
        logger.warning(f"Failed to release lock {lock_name}: {e}")
