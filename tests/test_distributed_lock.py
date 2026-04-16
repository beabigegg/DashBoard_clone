# -*- coding: utf-8 -*-
"""Task 6.8 — Distributed lock: dual-worker exclusivity, TTL expiry, fairness.

Integration tests for try_acquire_lock() / release_lock() in redis_client.py.
All tests are skipped automatically when Redis is unavailable.

Key scenarios:
  - Only one of two concurrent callers can hold the lock at a time
  - A lock with a short TTL expires and becomes acquirable by another caller
  - Releasing a lock allows immediate reacquisition
  - A "crashed" holder (never calls release_lock) causes auto-expiry
"""

from __future__ import annotations

import threading
import time
import uuid

import pytest

from mes_dashboard.core.redis_client import (
    REDIS_KEY_PREFIX,
    get_control_redis_client,
    redis_available,
    release_lock,
    try_acquire_lock,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _unique_lock() -> str:
    """Return a unique lock name for each test to avoid key collisions."""
    return f"test-lock-{uuid.uuid4().hex[:12]}"


def _lock_key(lock_name: str) -> str:
    return f"{REDIS_KEY_PREFIX}:lock:{lock_name}"


def _force_delete(lock_name: str) -> None:
    """Unconditionally remove a lock key (test teardown)."""
    conn = get_control_redis_client()
    if conn is not None:
        conn.delete(_lock_key(lock_name))


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestDistributedLock:
    """Distributed lock invariants using Redis SET NX."""

    def setup_method(self):
        if not redis_available():
            pytest.skip("Redis not available")

    # ------------------------------------------------------------------
    # test_try_acquire_lock_exclusive
    # ------------------------------------------------------------------
    def test_try_acquire_lock_exclusive(self):
        """Only one of two concurrent threads may hold the lock simultaneously.

        Both threads race to acquire the same lock name.  Exactly one must
        succeed (True) and the other must fail (False).
        """
        lock_name = _unique_lock()
        results: list[bool] = []
        errors: list[Exception] = []

        def worker():
            try:
                acquired = try_acquire_lock(lock_name, ttl_seconds=30, fail_mode="closed")
                results.append(acquired)
            except Exception as exc:
                errors.append(exc)

        t1 = threading.Thread(target=worker)
        t2 = threading.Thread(target=worker)
        t1.start()
        t2.start()
        t1.join(timeout=5)
        t2.join(timeout=5)

        try:
            assert not errors, f"unexpected exceptions in lock workers: {errors}"
            assert len(results) == 2, "both threads must have completed"
            true_count = sum(1 for r in results if r)
            assert true_count == 1, (
                f"exactly one thread should acquire the lock, got {true_count} successes"
            )
        finally:
            _force_delete(lock_name)

    # ------------------------------------------------------------------
    # test_lock_expires_after_ttl
    # ------------------------------------------------------------------
    def test_lock_expires_after_ttl(self):
        """A lock with TTL=1 must expire within ~2 seconds and become reacquirable."""
        lock_name = _unique_lock()
        try:
            acquired = try_acquire_lock(lock_name, ttl_seconds=1, fail_mode="closed")
            assert acquired, "should acquire an uncontested lock"

            # Without releasing, wait for TTL to expire
            time.sleep(1.5)

            # A second caller must now be able to acquire
            reacquired = try_acquire_lock(lock_name, ttl_seconds=10, fail_mode="closed")
            assert reacquired, "lock should be reacquirable after TTL expiry"
        finally:
            _force_delete(lock_name)

    # ------------------------------------------------------------------
    # test_release_lock_allows_reacquire
    # ------------------------------------------------------------------
    def test_release_lock_allows_reacquire(self):
        """After release_lock(), another caller must acquire the lock immediately."""
        lock_name = _unique_lock()
        try:
            acquired = try_acquire_lock(lock_name, ttl_seconds=60, fail_mode="closed")
            assert acquired, "initial acquisition must succeed"

            # Verify a concurrent caller cannot grab it while held
            blocked = try_acquire_lock(lock_name, ttl_seconds=60, fail_mode="closed")
            assert not blocked, "lock must be blocked while held"

            # Release
            release_lock(lock_name)

            # Now a new caller must succeed
            reacquired = try_acquire_lock(lock_name, ttl_seconds=60, fail_mode="closed")
            assert reacquired, "lock must be acquirable immediately after release"
        finally:
            _force_delete(lock_name)

    # ------------------------------------------------------------------
    # test_holder_crash_expiry
    # ------------------------------------------------------------------
    def test_holder_crash_expiry(self):
        """A holder that never calls release_lock must not block forever.

        Simulates a worker crash: the lock is acquired with a short TTL and
        release_lock() is deliberately NOT called.  After the TTL elapses,
        a new caller must be able to acquire the lock.
        """
        lock_name = _unique_lock()
        try:
            # "Crash" simulation: acquire then abandon (no release)
            acquired = try_acquire_lock(lock_name, ttl_seconds=1, fail_mode="closed")
            assert acquired, "crash victim must acquire the lock initially"

            # Do NOT call release_lock() — the holder "crashed"
            # Wait beyond TTL
            time.sleep(1.5)

            # New worker must be unblocked
            recovered = try_acquire_lock(lock_name, ttl_seconds=30, fail_mode="closed")
            assert recovered, (
                "lock must auto-expire after TTL so a new holder can proceed"
            )
        finally:
            _force_delete(lock_name)
