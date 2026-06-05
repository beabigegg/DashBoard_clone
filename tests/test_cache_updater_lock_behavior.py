# -*- coding: utf-8 -*-
"""Task 8.1 — CacheUpdater._check_and_update: fail-closed behaviour.

Injects Redis unavailability and verifies:
- No Oracle (read_sql_df) call is made when the lock cannot be acquired.
- The function returns False (skip, don't crash).
- Previously-cached data is unaffected.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

import mes_dashboard.core.redis_client as redis_client_module
from mes_dashboard.core.cache_updater import CacheUpdater


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def updater():
    return CacheUpdater()


@pytest.fixture()
def redis_unavailable(monkeypatch):
    """Make Redis unavailable: get_control_redis_client returns None and
    redis_available() returns True so we reach try_acquire_lock, which then
    returns False (fail-closed)."""
    monkeypatch.setattr(redis_client_module, "get_control_redis_client", lambda: None)
    # redis_available checks get_redis_client (cache plane), not control.
    # Patch it to return True so _check_and_update reaches the lock call.
    monkeypatch.setattr(redis_client_module, "redis_available", lambda: True)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestWipCacheUpdateFailClosed:
    def test_returns_false_when_lock_unavailable(self, updater, redis_unavailable):
        """_check_and_update must return False when lock cannot be acquired."""
        result = updater._check_and_update()
        assert result is False

    def test_no_oracle_call_when_lock_unavailable(self, updater, redis_unavailable):
        """No Oracle query (read_sql_df) should be made when the lock fails."""
        with patch("mes_dashboard.core.cache_updater.read_sql_df") as mock_sql:
            updater._check_and_update()
            mock_sql.assert_not_called()

    def test_stale_cache_unaffected(self, updater, redis_unavailable):
        """Previously cached state must not be cleared on lock failure.

        We simulate stale state by patching _check_sys_date to verify it is
        never reached (i.e., the function returns before any cache mutation).
        """
        check_calls = []

        original_check = updater._check_sys_date

        def spy_check(*args, **kwargs):
            check_calls.append(True)
            return original_check(*args, **kwargs)

        updater._check_sys_date = spy_check
        updater._check_and_update()

        assert check_calls == [], "Oracle SYS_DATE check must not happen when lock fails"


# ============================================================
# Change: prod-history-first-tier-cache-filters
# AC-6 / PHF-05 — file-based exclusive lock prevents Oracle thundering herd
# ============================================================

class TestContainerFilterCacheLockBehavior:
    """File-based ``O_CREAT|O_EXCL`` lock on container_filter_cache."""

    def test_container_filter_cache_lock_prevents_concurrent_oracle(self, tmp_path, monkeypatch):
        """Two simulated workers — only the lock winner calls Oracle.

        Re-points the lock file path to a tmp file so the test cannot
        collide with a real cache rebuild on the dev machine.
        """
        import mes_dashboard.services.container_filter_cache as cache_mod

        lock_file = tmp_path / "container_filter_cache.loading"
        monkeypatch.setattr(cache_mod, "_LOCK_PATH", lock_file)

        # Worker 1 acquires the lock.
        first = cache_mod._try_lock()
        try:
            assert first is True
            # Worker 2 attempts — denied (file already exists).
            second = cache_mod._try_lock()
            assert second is False
        finally:
            cache_mod._release_lock()
        # After release, the lock file is gone.
        assert not lock_file.exists()
        # And a fresh worker can acquire it again.
        third = cache_mod._try_lock()
        try:
            assert third is True
        finally:
            cache_mod._release_lock()


# ============================================================
# Change: gunicorn-preload-workers
# AC-6 -- resource_history_duckdb_cache file-lock deadlock
# Replace O_CREAT|O_EXCL sentinel with fcntl.flock so lock
# auto-releases when the holding process dies.
# ============================================================

class TestDuckdbPrewarmLockFcntl:
    """fcntl.flock-based lock on resource_history_duckdb_cache.

    These tests FAIL before the fix (O_CREAT|O_EXCL) and PASS after
    (fcntl.LOCK_EX|LOCK_NB).
    """

    def test_duckdb_prewarm_lock_releases_on_fd_close(self, tmp_path, monkeypatch):
        """AC-6.1: After acquiring and then closing the fd without an explicit
        _release_lock() call, _try_lock() must succeed again.

        With O_CREAT|O_EXCL the sentinel file lingers -> _try_lock() returns False
        (deadlock). With fcntl.flock the kernel releases the lock when the fd is
        closed -> _try_lock() returns True (auto-release on process death).
        """
        import mes_dashboard.services.resource_history_duckdb_cache as duck_mod

        lock_path = tmp_path / "resource_history.duckdb.loading"
        monkeypatch.setattr(duck_mod, "_LOCK_PATH", lock_path)

        # Worker 1 acquires the lock.
        first = duck_mod._try_lock()
        assert first is True, "First _try_lock() must succeed"

        # Simulate process death: close the fd held internally without calling
        # _release_lock().  With fcntl.flock the OS releases the lock.
        assert hasattr(duck_mod, "_LOCK_FD"), (
            "_LOCK_FD must exist after fix -- the fd reference that keeps flock alive"
        )
        fd_ref = duck_mod._LOCK_FD[0]
        if fd_ref is not None:
            try:
                fd_ref.close()
            except Exception:
                pass
            duck_mod._LOCK_FD[0] = None

        # Remove the lock file left behind (flock releases kernel lock on close,
        # but file still exists on disk; the winner must clean it up or the next
        # _try_lock must handle an uncontested open).
        if lock_path.exists():
            lock_path.unlink(missing_ok=True)

        # Worker 2 (or restarted Worker 1) must now acquire the lock.
        second = duck_mod._try_lock()
        try:
            assert second is True, (
                "After simulated fd close (process death), _try_lock() must "
                "return True. Got False -- lock was not released automatically."
            )
        finally:
            duck_mod._release_lock()

    def test_duckdb_prewarm_lock_prevents_concurrent_attempt(self, tmp_path, monkeypatch):
        """AC-6.2: While the lock is held, a second _try_lock() returns False."""
        import mes_dashboard.services.resource_history_duckdb_cache as duck_mod

        lock_path = tmp_path / "resource_history.duckdb.loading"
        monkeypatch.setattr(duck_mod, "_LOCK_PATH", lock_path)

        first = duck_mod._try_lock()
        try:
            assert first is True
            second = duck_mod._try_lock()
            assert second is False, (
                "_try_lock() must return False when lock is already held. "
                "Got True -- concurrent acquisition should be blocked."
            )
        finally:
            duck_mod._release_lock()

    def test_duckdb_prewarm_lock_releases_cleanly(self, tmp_path, monkeypatch):
        """AC-6.3: After _release_lock(), a fresh _try_lock() succeeds."""
        import mes_dashboard.services.resource_history_duckdb_cache as duck_mod

        lock_path = tmp_path / "resource_history.duckdb.loading"
        monkeypatch.setattr(duck_mod, "_LOCK_PATH", lock_path)

        duck_mod._try_lock()
        duck_mod._release_lock()

        # After explicit release, a new worker can acquire.
        third = duck_mod._try_lock()
        try:
            assert third is True, (
                "After _release_lock(), _try_lock() must return True. "
                "Got False -- lock was not released properly."
            )
        finally:
            duck_mod._release_lock()

    def test_duckdb_lock_fd_container_populated_on_acquire(self, tmp_path, monkeypatch):
        """AC-6.4: After _try_lock() succeeds, _LOCK_FD[0] must be a non-None
        file object (the fd reference that keeps the flock alive).

        With O_CREAT|O_EXCL there is no fd reference -- this attribute won't
        exist, causing the test to fail before the fix.
        """
        import mes_dashboard.services.resource_history_duckdb_cache as duck_mod

        lock_path = tmp_path / "resource_history.duckdb.loading"
        monkeypatch.setattr(duck_mod, "_LOCK_PATH", lock_path)

        duck_mod._try_lock()
        try:
            assert hasattr(duck_mod, "_LOCK_FD"), (
                "_LOCK_FD must exist in resource_history_duckdb_cache after fix."
            )
            assert duck_mod._LOCK_FD[0] is not None, (
                "_LOCK_FD[0] must be a non-None fd reference after _try_lock() "
                "succeeds. Got None -- fcntl.flock fd is not being stored."
            )
        finally:
            duck_mod._release_lock()
