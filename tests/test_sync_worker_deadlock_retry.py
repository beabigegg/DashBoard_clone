# -*- coding: utf-8 -*-
"""Unit tests pinning the sync_worker deadlock retry fix (commit a6fecb9).

Covers:
- _is_deadlock recognizes MySQL error 1213 via exc.orig.args[0]
- _is_deadlock returns False for non-1213 errors
- _sync_logs retries on deadlock and eventually succeeds
- _sync_logs retries max 3 times then gives up without raising
- executemany (batch execute) path passes params list to conn.execute
"""

from __future__ import annotations

from unittest.mock import patch, MagicMock



class TestIsDeadlock:
    """_is_deadlock must identify MySQL error 1213 and nothing else."""

    def test_recognizes_mysql_1213_via_orig_args(self):
        from mes_dashboard.core.sync_worker import _is_deadlock

        exc = Exception("deadlock")
        exc.orig = MagicMock()
        exc.orig.args = (1213,)
        assert _is_deadlock(exc) is True

    def test_rejects_other_mysql_errors(self):
        from mes_dashboard.core.sync_worker import _is_deadlock

        exc = Exception("duplicate key")
        exc.orig = MagicMock()
        exc.orig.args = (1062,)  # duplicate key, not deadlock
        assert _is_deadlock(exc) is False

    def test_rejects_plain_exception_without_orig(self):
        from mes_dashboard.core.sync_worker import _is_deadlock

        exc = Exception("generic error")
        assert _is_deadlock(exc) is False

    def test_rejects_exc_with_empty_args(self):
        from mes_dashboard.core.sync_worker import _is_deadlock

        exc = Exception("no args")
        exc.orig = MagicMock()
        exc.orig.args = ()
        assert _is_deadlock(exc) is False

    def test_recognizes_1213_on_exc_itself_when_no_orig(self):
        """If exc.args[0] == 1213 (no .orig), must also detect deadlock."""
        from mes_dashboard.core.sync_worker import _is_deadlock

        exc = Exception(1213)
        # exc has no .orig, so getattr(exc, 'orig', exc) returns exc itself
        assert _is_deadlock(exc) is True


class TestSyncLogsDeadlockRetry:
    """_sync_logs retries on deadlock and succeeds within 3 attempts."""

    def _make_deadlock_exc(self):
        exc = Exception("deadlock")
        exc.orig = MagicMock()
        exc.orig.args = (1213,)
        return exc

    def _make_worker(self):
        from mes_dashboard.core.sync_worker import SyncWorker
        worker = SyncWorker.__new__(SyncWorker)
        worker._log_store = MagicMock()
        worker._metrics_store = MagicMock()
        worker._login_store = MagicMock()
        worker._stop_event = MagicMock()
        worker._thread = None
        return worker

    def test_sync_logs_retries_on_deadlock_and_succeeds(self):
        """If first attempt raises deadlock, second attempt must succeed."""

        worker = self._make_worker()
        worker._log_store.get_unsynced.return_value = [
            {"id": 1, "sync_id": "s1", "timestamp": "2024-01-01T00:00:00",
             "level": "INFO", "logger_name": "test", "message": "msg",
             "request_id": None, "user": None, "ip": None, "extra": None}
        ]

        deadlock_exc = self._make_deadlock_exc()
        mock_conn = MagicMock()
        # First call raises deadlock, second succeeds
        mock_conn.execute.side_effect = [deadlock_exc, None]
        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_conn)
        mock_ctx.__exit__ = MagicMock(return_value=False)

        with patch('mes_dashboard.core.sync_worker.MYSQL_OPS_ENABLED', True), \
             patch('mes_dashboard.core.sync_worker.get_mysql_connection', return_value=mock_ctx), \
             patch('mes_dashboard.core.sync_worker.time.sleep'):
            worker._sync_logs()

        assert mock_conn.execute.call_count == 2
        worker._log_store.mark_synced.assert_called_once()

    def test_sync_logs_gives_up_after_3_deadlock_attempts(self):
        """After 3 deadlock attempts, _sync_logs must stop retrying without raising."""
        worker = self._make_worker()
        worker._log_store.get_unsynced.return_value = [
            {"id": 1, "sync_id": "s1", "timestamp": "2024-01-01T00:00:00",
             "level": "INFO", "logger_name": "test", "message": "msg",
             "request_id": None, "user": None, "ip": None, "extra": None}
        ]

        deadlock_exc = self._make_deadlock_exc()
        mock_conn = MagicMock()
        mock_conn.execute.side_effect = deadlock_exc  # always deadlock
        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_conn)
        mock_ctx.__exit__ = MagicMock(return_value=False)

        with patch('mes_dashboard.core.sync_worker.MYSQL_OPS_ENABLED', True), \
             patch('mes_dashboard.core.sync_worker.get_mysql_connection', return_value=mock_ctx), \
             patch('mes_dashboard.core.sync_worker.time.sleep') as mock_sleep:
            worker._sync_logs()  # must not raise

        # 3 attempts total; sleep called between attempts 1→2 and 2→3
        assert mock_conn.execute.call_count == 3
        assert mock_sleep.call_count == 2  # once per retry
        # mark_synced must NOT be called (all attempts failed)
        worker._log_store.mark_synced.assert_not_called()

    def test_sync_logs_non_deadlock_error_does_not_retry(self):
        """Non-deadlock errors must NOT trigger the retry loop."""
        worker = self._make_worker()
        worker._log_store.get_unsynced.return_value = [
            {"id": 1, "sync_id": "s1", "timestamp": "2024-01-01T00:00:00",
             "level": "INFO", "logger_name": "test", "message": "msg",
             "request_id": None, "user": None, "ip": None, "extra": None}
        ]

        # Non-deadlock error (connection timeout)
        regular_exc = Exception("connection timeout")
        mock_conn = MagicMock()
        mock_conn.execute.side_effect = regular_exc
        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_conn)
        mock_ctx.__exit__ = MagicMock(return_value=False)

        with patch('mes_dashboard.core.sync_worker.MYSQL_OPS_ENABLED', True), \
             patch('mes_dashboard.core.sync_worker.get_mysql_connection', return_value=mock_ctx), \
             patch('mes_dashboard.core.sync_worker.time.sleep') as mock_sleep:
            worker._sync_logs()  # must not raise

        # Only 1 attempt — no retry on non-deadlock errors
        assert mock_conn.execute.call_count == 1
        mock_sleep.assert_not_called()

    def test_batch_execute_passes_params_list_not_row_by_row(self):
        """conn.execute must be called ONCE with the full params list (executemany)."""
        worker = self._make_worker()
        worker._log_store.get_unsynced.return_value = [
            {"id": 1, "sync_id": "s1", "timestamp": "2024-01-01T00:00:00",
             "level": "INFO", "logger_name": "test", "message": "msg1",
             "request_id": None, "user": None, "ip": None, "extra": None},
            {"id": 2, "sync_id": "s2", "timestamp": "2024-01-02T00:00:00",
             "level": "DEBUG", "logger_name": "test", "message": "msg2",
             "request_id": None, "user": None, "ip": None, "extra": None},
            {"id": 3, "sync_id": "s3", "timestamp": "2024-01-03T00:00:00",
             "level": "WARNING", "logger_name": "test", "message": "msg3",
             "request_id": None, "user": None, "ip": None, "extra": None},
        ]

        mock_conn = MagicMock()
        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_conn)
        mock_ctx.__exit__ = MagicMock(return_value=False)

        with patch('mes_dashboard.core.sync_worker.MYSQL_OPS_ENABLED', True), \
             patch('mes_dashboard.core.sync_worker.get_mysql_connection', return_value=mock_ctx):
            worker._sync_logs()

        # executemany: execute called ONCE with a list of 3 param dicts
        assert mock_conn.execute.call_count == 1
        call_args = mock_conn.execute.call_args
        params_arg = call_args[0][1]  # second positional arg is the params
        assert isinstance(params_arg, list)
        assert len(params_arg) == 3
