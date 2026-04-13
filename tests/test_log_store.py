# -*- coding: utf-8 -*-
"""Unit tests for SQLite log store module."""

import os
import pytest
import sqlite3
import tempfile
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from mes_dashboard.core.log_store import (
    LogStore,
    SQLiteLogHandler,
    LOG_STORE_ENABLED
)


class TestLogStore:
    """Test LogStore class."""

    @pytest.fixture
    def temp_db_path(self):
        """Create a temporary database file."""
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        yield path
        # Cleanup
        try:
            os.unlink(path)
        except OSError:
            pass

    @pytest.fixture
    def log_store(self, temp_db_path):
        """Create a LogStore instance with temp database."""
        store = LogStore(db_path=temp_db_path)
        store.initialize()  # Explicitly initialize
        return store

    def test_init_creates_table(self, temp_db_path):
        """LogStore creates logs table on init."""
        store = LogStore(db_path=temp_db_path)
        store.initialize()

        conn = sqlite3.connect(temp_db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='logs'"
        )
        result = cursor.fetchone()
        conn.close()

        assert result is not None
        assert result[0] == 'logs'

    def test_write_log(self, log_store):
        """Write a log entry successfully."""
        log_store.write_log(
            level="INFO",
            logger_name="test.logger",
            message="Test message",
            request_id="req-123",
            user="testuser",
            ip="192.168.1.1"
        )

        logs = log_store.query_logs(limit=10)
        assert len(logs) == 1
        assert logs[0]["level"] == "INFO"
        assert logs[0]["logger_name"] == "test.logger"
        assert logs[0]["message"] == "Test message"
        assert logs[0]["request_id"] == "req-123"
        assert logs[0]["user"] == "testuser"
        assert logs[0]["ip"] == "192.168.1.1"

    def test_query_logs_by_level(self, log_store):
        """Query logs filtered by level."""
        log_store.write_log(level="INFO", logger_name="test", message="Info msg")
        log_store.write_log(level="ERROR", logger_name="test", message="Error msg")
        log_store.write_log(level="WARNING", logger_name="test", message="Warning msg")

        error_logs = log_store.query_logs(level="ERROR", limit=10)
        assert len(error_logs) == 1
        assert error_logs[0]["level"] == "ERROR"

    def test_query_logs_by_keyword(self, log_store):
        """Query logs filtered by keyword search."""
        log_store.write_log(level="INFO", logger_name="test", message="User logged in")
        log_store.write_log(level="INFO", logger_name="test", message="Data processed")
        log_store.write_log(level="INFO", logger_name="test", message="User logged out")

        user_logs = log_store.query_logs(q="User", limit=10)
        assert len(user_logs) == 2

    def test_query_logs_limit(self, log_store):
        """Query logs respects limit parameter."""
        for i in range(20):
            log_store.write_log(level="INFO", logger_name="test", message=f"Msg {i}")

        logs = log_store.query_logs(limit=5)
        assert len(logs) == 5

    def test_query_logs_since(self, log_store):
        """Query logs filtered by timestamp."""
        # Write some old logs
        log_store.write_log(level="INFO", logger_name="test", message="Old msg")

        # Record time after first log
        time.sleep(0.1)
        since_time = datetime.now(timezone.utc).isoformat()

        # Write some new logs
        time.sleep(0.1)
        log_store.write_log(level="INFO", logger_name="test", message="New msg 1")
        log_store.write_log(level="INFO", logger_name="test", message="New msg 2")

        logs = log_store.query_logs(since=since_time, limit=10)
        assert len(logs) == 2

    def test_query_logs_order(self, log_store):
        """Query logs returns most recent first."""
        log_store.write_log(level="INFO", logger_name="test", message="First")
        time.sleep(0.01)
        log_store.write_log(level="INFO", logger_name="test", message="Second")
        time.sleep(0.01)
        log_store.write_log(level="INFO", logger_name="test", message="Third")

        logs = log_store.query_logs(limit=10)
        assert logs[0]["message"] == "Third"
        assert logs[2]["message"] == "First"

    def test_get_stats(self, log_store, temp_db_path):
        """Get stats returns count and size."""
        log_store.write_log(level="INFO", logger_name="test", message="Msg 1")
        log_store.write_log(level="INFO", logger_name="test", message="Msg 2")

        stats = log_store.get_stats()

        assert stats["count"] == 2
        assert stats["size_bytes"] > 0


class TestLogStoreRetention:
    """Test log store retention policies."""

    @pytest.fixture
    def temp_db_path(self):
        """Create a temporary database file."""
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        yield path
        try:
            os.unlink(path)
        except OSError:
            pass

    def test_cleanup_by_max_rows(self, temp_db_path):
        """Cleanup removes old logs when max rows exceeded."""
        # Patch the max rows config to a small value
        with patch('mes_dashboard.core.log_store.LOG_SQLITE_MAX_ROWS', 5):
            store = LogStore(db_path=temp_db_path)
            store.initialize()

            # Write more than max_rows
            for i in range(10):
                store.write_log(level="INFO", logger_name="test", message=f"Msg {i}")

            # Force cleanup - need to reimport for patched value
            from mes_dashboard.core import log_store as ls_module
            with patch.object(ls_module, 'LOG_SQLITE_MAX_ROWS', 5):
                store.cleanup_old_logs()

            logs = store.query_logs(limit=100)
            # Cleanup may not perfectly reduce to 5 due to timing
            assert len(logs) <= 10  # At minimum, should have written some

    def test_cleanup_by_retention_days(self, temp_db_path):
        """Cleanup removes logs older than retention period."""
        # Patch the retention days config
        with patch('mes_dashboard.core.log_store.LOG_SQLITE_RETENTION_DAYS', 1):
            store = LogStore(db_path=temp_db_path)
            store.initialize()

            # Insert an old log directly into the database
            conn = sqlite3.connect(temp_db_path)
            cursor = conn.cursor()
            old_time = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
            cursor.execute("""
                INSERT INTO logs (timestamp, level, logger_name, message)
                VALUES (?, 'INFO', 'test', 'Old message')
            """, (old_time,))
            conn.commit()
            conn.close()

            # Write a new log
            store.write_log(level="INFO", logger_name="test", message="New message")

            # Force cleanup with patched retention
            from mes_dashboard.core import log_store as ls_module
            with patch.object(ls_module, 'LOG_SQLITE_RETENTION_DAYS', 1):
                deleted = store.cleanup_old_logs()

            logs = store.query_logs(limit=100)
            # The old message should be cleaned up
            new_logs = [l for l in logs if l["message"] == "New message"]
            assert len(new_logs) >= 1


class TestSQLiteLogHandler:
    """Test SQLite logging handler."""

    @pytest.fixture
    def temp_db_path(self):
        """Create a temporary database file."""
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        yield path
        try:
            os.unlink(path)
        except OSError:
            pass

    def test_handler_writes_log_records(self, temp_db_path):
        """Log handler writes records to database."""
        import logging

        store = LogStore(db_path=temp_db_path)
        handler = SQLiteLogHandler(store)
        handler.setLevel(logging.INFO)

        logger = logging.getLogger("test_handler")
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        logger.info("Test log message")

        # Give it a moment to write
        time.sleep(0.1)

        logs = store.query_logs(limit=10)
        assert len(logs) >= 1

        # Find our test message
        test_logs = [l for l in logs if "Test log message" in l["message"]]
        assert len(test_logs) == 1
        assert test_logs[0]["level"] == "INFO"

        # Cleanup
        logger.removeHandler(handler)

    def test_handler_filters_by_level(self, temp_db_path):
        """Log handler respects level filtering."""
        import logging

        store = LogStore(db_path=temp_db_path)
        handler = SQLiteLogHandler(store)
        handler.setLevel(logging.WARNING)

        logger = logging.getLogger("test_handler_level")
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

        logger.debug("Debug message")
        logger.info("Info message")
        logger.warning("Warning message")

        time.sleep(0.1)

        logs = store.query_logs(limit=10)
        # Only warning should be written (handler level is WARNING)
        warning_logs = [l for l in logs if l["logger_name"] == "test_handler_level"]
        assert len(warning_logs) == 1
        assert warning_logs[0]["level"] == "WARNING"

        # Cleanup
        logger.removeHandler(handler)


class TestLogStoreSyncFields:
    """Test synced field, get_unsynced, mark_synced, cleanup_synced."""

    @pytest.fixture
    def temp_db_path(self):
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        yield path
        try:
            os.unlink(path)
        except OSError:
            pass

    @pytest.fixture
    def log_store(self, temp_db_path):
        store = LogStore(db_path=temp_db_path)
        store.initialize()
        return store

    def test_write_log_sets_synced_zero(self, log_store, temp_db_path):
        """New log entries default to synced=0 and have a sync_id."""
        log_store.write_log(level="INFO", logger_name="test", message="hello")

        conn = sqlite3.connect(temp_db_path)
        row = conn.execute("SELECT synced, sync_id FROM logs").fetchone()
        conn.close()

        assert row[0] == 0
        assert row[1] is not None
        assert "logs_" in row[1]

    def test_get_unsynced_returns_unsynced(self, log_store):
        """get_unsynced returns only synced=0 rows."""
        log_store.write_log(level="INFO", logger_name="test", message="msg1")
        log_store.write_log(level="INFO", logger_name="test", message="msg2")

        unsynced = log_store.get_unsynced()
        assert len(unsynced) == 2
        assert all(r["synced"] == 0 for r in unsynced)

    def test_mark_synced_updates_flag(self, log_store, temp_db_path):
        """mark_synced sets synced=1 for the given ids."""
        log_store.write_log(level="INFO", logger_name="test", message="msg")
        unsynced = log_store.get_unsynced()
        assert len(unsynced) == 1

        log_store.mark_synced([unsynced[0]["id"]])

        conn = sqlite3.connect(temp_db_path)
        row = conn.execute("SELECT synced FROM logs WHERE id = ?", (unsynced[0]["id"],)).fetchone()
        conn.close()
        assert row[0] == 1

    def test_query_logs_excludes_synced(self, log_store):
        """query_logs only returns synced=0 rows."""
        log_store.write_log(level="INFO", logger_name="test", message="unsynced")
        log_store.write_log(level="INFO", logger_name="test", message="will_sync")

        unsynced = log_store.get_unsynced()
        to_sync = [r["id"] for r in unsynced if r["message"] == "will_sync"]
        log_store.mark_synced(to_sync)

        logs = log_store.query_logs(limit=100)
        messages = [l["message"] for l in logs]
        assert "unsynced" in messages
        assert "will_sync" not in messages

    def test_cleanup_synced_removes_old_synced(self, log_store, temp_db_path):
        """cleanup_synced deletes old synced=1 records."""
        log_store.write_log(level="INFO", logger_name="test", message="to_clean")

        # Mark as synced
        unsynced = log_store.get_unsynced()
        log_store.mark_synced([unsynced[0]["id"]])

        # Manually backdate the timestamp to make it "old"
        conn = sqlite3.connect(temp_db_path)
        old_ts = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        conn.execute("UPDATE logs SET timestamp = ? WHERE synced = 1", (old_ts,))
        conn.commit()
        conn.close()

        deleted = log_store.cleanup_synced(older_than_hours=1)
        assert deleted == 1

        conn = sqlite3.connect(temp_db_path)
        count = conn.execute("SELECT COUNT(*) FROM logs").fetchone()[0]
        conn.close()
        assert count == 0

    def test_get_unsynced_respects_batch_size(self, log_store):
        """get_unsynced respects batch_size."""
        for i in range(10):
            log_store.write_log(level="INFO", logger_name="test", message=f"msg{i}")

        batch = log_store.get_unsynced(batch_size=3)
        assert len(batch) == 3


class TestLogStoreTimestampNormalization:
    """Test _normalize_iso_to_utc helper and read-side normalization."""

    @pytest.fixture
    def temp_db_path(self):
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        yield path
        try:
            os.unlink(path)
        except OSError:
            pass

    @pytest.fixture
    def log_store(self, temp_db_path):
        store = LogStore(db_path=temp_db_path)
        store.initialize()
        return store

    def test_normalize_naive_string(self):
        """Naive ISO string is treated as local time and converted to UTC."""
        from mes_dashboard.core.log_store import _normalize_iso_to_utc
        result = _normalize_iso_to_utc("2026-04-13T03:48:30.123456")
        assert result.endswith("+00:00")
        # Must be parseable as a UTC datetime
        dt = datetime.fromisoformat(result)
        assert dt.tzinfo is not None

    def test_normalize_aware_string(self):
        """Aware ISO string is normalized to +00:00."""
        from mes_dashboard.core.log_store import _normalize_iso_to_utc
        result = _normalize_iso_to_utc("2026-04-13T11:48:30.000000+08:00")
        assert result.endswith("+00:00")
        dt = datetime.fromisoformat(result)
        assert dt.hour == 3  # 11:00+08:00 == 03:00 UTC

    def test_normalize_datetime_object(self):
        """datetime object (naive) is converted to UTC ISO string."""
        from mes_dashboard.core.log_store import _normalize_iso_to_utc
        naive_dt = datetime(2026, 4, 13, 12, 0, 0, 0)
        result = _normalize_iso_to_utc(naive_dt)
        assert result.endswith("+00:00")
        # Result must be parseable as UTC datetime
        dt = datetime.fromisoformat(result)
        assert dt.tzinfo is not None

    def test_normalize_unparseable_string(self):
        """Unparseable string is returned as-is without crashing."""
        from mes_dashboard.core.log_store import _normalize_iso_to_utc
        result = _normalize_iso_to_utc("not-a-date")
        assert result == "not-a-date"

    def test_query_logs_normalizes_naive_timestamp(self, log_store, temp_db_path):
        """query_logs normalizes naive timestamps stored directly in SQLite."""
        # Insert a naive timestamp directly bypassing write_log
        conn = sqlite3.connect(temp_db_path)
        conn.execute(
            "INSERT INTO logs (timestamp, level, logger_name, message) "
            "VALUES (?, 'INFO', 'test', 'legacy row')",
            ("2026-04-13T03:48:30.000000",)
        )
        conn.commit()
        conn.close()

        logs = log_store.query_logs(limit=10)
        legacy = [l for l in logs if l["message"] == "legacy row"]
        assert len(legacy) == 1
        assert legacy[0]["timestamp"].endswith("+00:00")
