# -*- coding: utf-8 -*-
"""Tests for sync_worker — SQLite → MySQL dual-layer sync."""

from __future__ import annotations

import os
import sqlite3
import tempfile
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch, call

import pytest

from mes_dashboard.core.log_store import LogStore
from mes_dashboard.core.metrics_history import MetricsHistoryStore
from mes_dashboard.core.sync_worker import SyncWorker


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def temp_log_store():
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    store = LogStore(db_path=path)
    store.initialize()
    yield store
    try:
        os.unlink(path)
    except OSError:
        pass


@pytest.fixture
def temp_metrics_store():
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    store = MetricsHistoryStore(db_path=path)
    store.initialize()
    yield store
    try:
        os.unlink(path)
    except OSError:
        pass


@pytest.fixture
def worker(temp_log_store, temp_metrics_store):
    return SyncWorker(
        log_store=temp_log_store,
        metrics_store=temp_metrics_store,
        interval=9999,  # Never fires automatically
    )


# ============================================================
# Test: Normal sync flow
# ============================================================

class TestNormalSyncFlow:
    """Verify rows move from SQLite to MySQL and get marked synced."""

    def test_sync_logs_inserts_to_mysql_and_marks_synced(self, worker, temp_log_store):
        temp_log_store.write_log(level="INFO", logger_name="test", message="hello")
        temp_log_store.write_log(level="ERROR", logger_name="test", message="world")

        assert len(temp_log_store.get_unsynced()) == 2

        mock_conn = MagicMock()
        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_conn)
        mock_ctx.__exit__ = MagicMock(return_value=False)

        with (
            patch('mes_dashboard.core.sync_worker.MYSQL_OPS_ENABLED', True),
            patch('mes_dashboard.core.sync_worker.get_mysql_connection', return_value=mock_ctx),
        ):
            worker._sync_logs()

        # After a6fecb9: executemany — execute called ONCE with a list of 2 params
        assert mock_conn.execute.call_count == 1
        call_params = mock_conn.execute.call_args[0][1]
        assert isinstance(call_params, list)
        assert len(call_params) == 2
        assert len(temp_log_store.get_unsynced()) == 0

    def test_sync_metrics_inserts_to_mysql_and_marks_synced(self, worker, temp_metrics_store):
        temp_metrics_store.write_snapshot({"pool": {}, "redis": {}, "route_cache": {}, "latency": {}})

        assert len(temp_metrics_store.get_unsynced()) == 1

        mock_conn = MagicMock()
        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_conn)
        mock_ctx.__exit__ = MagicMock(return_value=False)

        with (
            patch('mes_dashboard.core.sync_worker.MYSQL_OPS_ENABLED', True),
            patch('mes_dashboard.core.sync_worker.get_mysql_connection', return_value=mock_ctx),
        ):
            worker._sync_metrics()

        assert mock_conn.execute.call_count == 1
        assert len(temp_metrics_store.get_unsynced()) == 0

    def test_sync_skipped_when_no_unsynced_rows(self, worker):
        mock_ctx = MagicMock()

        with (
            patch('mes_dashboard.core.sync_worker.MYSQL_OPS_ENABLED', True),
            patch('mes_dashboard.core.sync_worker.get_mysql_connection', return_value=mock_ctx),
        ):
            worker._sync_logs()
            worker._sync_metrics()

        # get_mysql_connection should never be entered when no rows
        mock_ctx.__enter__.assert_not_called()


# ============================================================
# Test: MySQL offline graceful fallback
# ============================================================

class TestMySQLOfflineFallback:
    """When MySQL is unreachable, rows stay in SQLite and no error is raised."""

    def test_log_sync_survives_mysql_failure(self, worker, temp_log_store):
        temp_log_store.write_log(level="INFO", logger_name="test", message="offline test")

        with (
            patch('mes_dashboard.core.sync_worker.MYSQL_OPS_ENABLED', True),
            patch(
                'mes_dashboard.core.sync_worker.get_mysql_connection',
                side_effect=Exception("Connection refused"),
            ),
        ):
            # Should not raise
            worker._sync_logs()

        # Rows must remain unsynced (safe in SQLite)
        assert len(temp_log_store.get_unsynced()) == 1

    def test_metrics_sync_survives_mysql_failure(self, worker, temp_metrics_store):
        temp_metrics_store.write_snapshot({"pool": {}, "redis": {}, "route_cache": {}, "latency": {}})

        with (
            patch('mes_dashboard.core.sync_worker.MYSQL_OPS_ENABLED', True),
            patch(
                'mes_dashboard.core.sync_worker.get_mysql_connection',
                side_effect=Exception("Connection refused"),
            ),
        ):
            worker._sync_metrics()

        assert len(temp_metrics_store.get_unsynced()) == 1

    def test_disabled_mysql_skips_sync(self, worker, temp_log_store):
        """When MYSQL_OPS_ENABLED=False, sync is a no-op."""
        temp_log_store.write_log(level="INFO", logger_name="test", message="disabled")

        with (
            patch('mes_dashboard.core.sync_worker.MYSQL_OPS_ENABLED', False),
            patch('mes_dashboard.core.sync_worker.get_mysql_connection') as mock_conn,
        ):
            worker._sync_logs()
            mock_conn.assert_not_called()


# ============================================================
# Test: Crash recovery (INSERT IGNORE idempotency)
# ============================================================

class TestCrashRecovery:
    """Re-syncing already-synced rows via INSERT IGNORE must not raise."""

    def test_insert_ignore_idempotent(self, worker, temp_log_store):
        """Simulate crash: rows were sent to MySQL but mark_synced wasn't called.
        Second sync call (INSERT IGNORE) should silently skip duplicates."""
        temp_log_store.write_log(level="INFO", logger_name="test", message="crash test")

        call_count = 0

        def fake_execute(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            # Simulate INSERT IGNORE: no error even on duplicate
            return MagicMock()

        mock_conn = MagicMock()
        mock_conn.execute.side_effect = fake_execute
        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_conn)
        mock_ctx.__exit__ = MagicMock(return_value=False)

        with (
            patch('mes_dashboard.core.sync_worker.MYSQL_OPS_ENABLED', True),
            patch('mes_dashboard.core.sync_worker.get_mysql_connection', return_value=mock_ctx),
        ):
            worker._sync_logs()  # First sync
            # Manually reset synced=0 to simulate crash before mark_synced
            temp_log_store._write_lock.acquire()
            with temp_log_store._get_connection() as conn:
                conn.execute("UPDATE logs SET synced = 0")
                conn.commit()
            temp_log_store._write_lock.release()

            worker._sync_logs()  # Second sync (INSERT IGNORE scenario)

        # Both calls executed, no exceptions
        assert call_count == 2
        assert len(temp_log_store.get_unsynced()) == 0


# ============================================================
# Test: cleanup_synced
# ============================================================

class TestCleanupSynced:
    """cleanup_synced removes old synced rows from both stores."""

    def test_cleanup_removes_old_synced_logs(self, worker, temp_log_store):
        temp_log_store.write_log(level="INFO", logger_name="test", message="old log")
        unsynced = temp_log_store.get_unsynced()
        temp_log_store.mark_synced([unsynced[0]["id"]])

        # Backdate
        db_path = temp_log_store.db_path
        old_ts = (datetime.now() - timedelta(hours=2)).isoformat()
        conn = sqlite3.connect(db_path)
        conn.execute("UPDATE logs SET timestamp = ? WHERE synced = 1", (old_ts,))
        conn.commit()
        conn.close()

        worker._cleanup_synced()

        conn = sqlite3.connect(db_path)
        count = conn.execute("SELECT COUNT(*) FROM logs").fetchone()[0]
        conn.close()
        assert count == 0

    def test_cleanup_leaves_unsynced_alone(self, worker, temp_log_store):
        temp_log_store.write_log(level="INFO", logger_name="test", message="keep me")

        worker._cleanup_synced()  # synced=0, so nothing deleted

        assert len(temp_log_store.get_unsynced()) == 1
