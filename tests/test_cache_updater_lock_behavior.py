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
