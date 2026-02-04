# -*- coding: utf-8 -*-
"""SQLite-based log store for admin dashboard.

Stores structured logs in a local SQLite database for admin querying.
Maintains existing file/STDERR logs for operations.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

logger = logging.getLogger('mes_dashboard.log_store')

# ============================================================
# Configuration
# ============================================================

# SQLite database path
LOG_SQLITE_PATH = os.getenv(
    'LOG_SQLITE_PATH',
    'logs/admin_logs.sqlite'
)

# Retention policy
LOG_SQLITE_RETENTION_DAYS = int(os.getenv('LOG_SQLITE_RETENTION_DAYS', '7'))
LOG_SQLITE_MAX_ROWS = int(os.getenv('LOG_SQLITE_MAX_ROWS', '100000'))

# Enable/disable log store
LOG_STORE_ENABLED = os.getenv('LOG_STORE_ENABLED', 'true').lower() == 'true'


# ============================================================
# Database Schema
# ============================================================

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    level TEXT NOT NULL,
    logger_name TEXT NOT NULL,
    message TEXT NOT NULL,
    request_id TEXT,
    user TEXT,
    ip TEXT,
    extra TEXT
);
"""

CREATE_INDEXES_SQL = [
    "CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON logs(timestamp);",
    "CREATE INDEX IF NOT EXISTS idx_logs_level ON logs(level);",
    "CREATE INDEX IF NOT EXISTS idx_logs_logger ON logs(logger_name);",
]


# ============================================================
# Log Store Implementation
# ============================================================

class LogStore:
    """SQLite-based log storage for admin dashboard queries.

    Thread-safe implementation with connection pooling per thread.
    Supports retention policy to prevent unbounded growth.

    Usage:
        store = LogStore()
        store.initialize()

        # Write logs
        store.write_log(
            level="ERROR",
            logger_name="mes_dashboard.api",
            message="Database connection failed",
            user="admin@example.com"
        )

        # Query logs
        logs = store.query_logs(level="ERROR", limit=100)
    """

    def __init__(self, db_path: str = LOG_SQLITE_PATH):
        """Initialize log store.

        Args:
            db_path: Path to SQLite database file.
        """
        self.db_path = db_path
        self._local = threading.local()
        self._write_lock = threading.Lock()
        self._initialized = False

    def initialize(self) -> None:
        """Initialize the database schema.

        Creates tables and indexes if they don't exist.
        """
        if self._initialized:
            return

        # Ensure directory exists
        db_dir = Path(self.db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(CREATE_TABLE_SQL)
            for index_sql in CREATE_INDEXES_SQL:
                cursor.execute(index_sql)
            conn.commit()

        self._initialized = True
        logger.info(f"Log store initialized at {self.db_path}")

    @contextmanager
    def _get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Get a thread-local database connection.

        Yields:
            SQLite connection for the current thread.
        """
        if not hasattr(self._local, 'connection') or self._local.connection is None:
            self._local.connection = sqlite3.connect(
                self.db_path,
                timeout=10.0,
                check_same_thread=False
            )
            self._local.connection.row_factory = sqlite3.Row

        try:
            yield self._local.connection
        except sqlite3.Error as e:
            logger.error(f"Database error: {e}")
            # Reset connection on error
            try:
                self._local.connection.close()
            except Exception:
                pass
            self._local.connection = None
            raise

    def write_log(
        self,
        level: str,
        logger_name: str,
        message: str,
        request_id: Optional[str] = None,
        user: Optional[str] = None,
        ip: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Write a log entry to the database.

        Args:
            level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
            logger_name: Name of the logger.
            message: Log message.
            request_id: Optional request identifier.
            user: Optional user identifier.
            ip: Optional client IP address.
            extra: Optional extra data as JSON-serializable dict.

        Returns:
            True if log was written successfully.
        """
        if not LOG_STORE_ENABLED:
            return False

        if not self._initialized:
            self.initialize()

        timestamp = datetime.now().isoformat()
        extra_str = None
        if extra:
            import json
            try:
                extra_str = json.dumps(extra, ensure_ascii=False)
            except (TypeError, ValueError):
                extra_str = str(extra)

        try:
            with self._write_lock:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        """
                        INSERT INTO logs (timestamp, level, logger_name, message, request_id, user, ip, extra)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (timestamp, level, logger_name, message, request_id, user, ip, extra_str)
                    )
                    conn.commit()
            return True
        except Exception as e:
            # Don't let log store errors propagate
            logger.debug(f"Failed to write log to SQLite: {e}")
            return False

    def query_logs(
        self,
        level: Optional[str] = None,
        q: Optional[str] = None,
        limit: int = 200,
        offset: int = 0,
        since: Optional[str] = None,
        logger_name: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Query logs from the database.

        Args:
            level: Filter by log level (e.g., "ERROR", "WARNING").
            q: Search query for message content (case-insensitive).
            limit: Maximum number of logs to return (default: 200).
            offset: Number of logs to skip (for pagination).
            since: ISO timestamp to filter logs after this time.
            logger_name: Filter by logger name prefix.

        Returns:
            List of log entries as dictionaries.
        """
        if not LOG_STORE_ENABLED:
            return []

        if not self._initialized:
            self.initialize()

        query = "SELECT * FROM logs WHERE 1=1"
        params: List[Any] = []

        if level:
            query += " AND level = ?"
            params.append(level.upper())

        if q:
            query += " AND message LIKE ?"
            params.append(f"%{q}%")

        if since:
            query += " AND timestamp >= ?"
            params.append(since)

        if logger_name:
            query += " AND logger_name LIKE ?"
            params.append(f"{logger_name}%")

        query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
        params.append(limit)
        params.append(offset)

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, params)
                rows = cursor.fetchall()

                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to query logs: {e}")
            return []

    def count_logs(
        self,
        level: Optional[str] = None,
        q: Optional[str] = None,
        since: Optional[str] = None,
        logger_name: Optional[str] = None
    ) -> int:
        """Count logs matching the given filters.

        Args:
            level: Filter by log level (e.g., "ERROR", "WARNING").
            q: Search query for message content (case-insensitive).
            since: ISO timestamp to filter logs after this time.
            logger_name: Filter by logger name prefix.

        Returns:
            Number of matching logs.
        """
        if not LOG_STORE_ENABLED:
            return 0

        if not self._initialized:
            self.initialize()

        query = "SELECT COUNT(*) FROM logs WHERE 1=1"
        params: List[Any] = []

        if level:
            query += " AND level = ?"
            params.append(level.upper())

        if q:
            query += " AND message LIKE ?"
            params.append(f"%{q}%")

        if since:
            query += " AND timestamp >= ?"
            params.append(since)

        if logger_name:
            query += " AND logger_name LIKE ?"
            params.append(f"{logger_name}%")

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, params)
                row = cursor.fetchone()
                return row[0] if row else 0
        except Exception as e:
            logger.error(f"Failed to count logs: {e}")
            return 0

    def cleanup_old_logs(self) -> int:
        """Remove logs older than retention period or exceeding max rows.

        Returns:
            Number of logs deleted.
        """
        if not LOG_STORE_ENABLED or not self._initialized:
            return 0

        deleted = 0

        try:
            with self._write_lock:
                with self._get_connection() as conn:
                    cursor = conn.cursor()

                    # Delete logs older than retention days
                    cutoff_date = (
                        datetime.now() - timedelta(days=LOG_SQLITE_RETENTION_DAYS)
                    ).isoformat()

                    cursor.execute(
                        "DELETE FROM logs WHERE timestamp < ?",
                        (cutoff_date,)
                    )
                    deleted += cursor.rowcount

                    # Delete excess logs if over max rows
                    cursor.execute("SELECT COUNT(*) FROM logs")
                    count = cursor.fetchone()[0]

                    if count > LOG_SQLITE_MAX_ROWS:
                        excess = count - LOG_SQLITE_MAX_ROWS
                        cursor.execute(
                            """
                            DELETE FROM logs WHERE id IN (
                                SELECT id FROM logs ORDER BY timestamp ASC LIMIT ?
                            )
                            """,
                            (excess,)
                        )
                        deleted += cursor.rowcount

                    conn.commit()

            if deleted > 0:
                logger.info(f"Cleaned up {deleted} old log entries")

        except Exception as e:
            logger.error(f"Failed to cleanup logs: {e}")

        return deleted

    def get_stats(self) -> Dict[str, Any]:
        """Get log store statistics.

        Returns:
            Dictionary with stats (count, oldest, newest, size_bytes).
        """
        if not LOG_STORE_ENABLED or not self._initialized:
            return {
                "enabled": LOG_STORE_ENABLED,
                "count": 0,
                "oldest": None,
                "newest": None,
                "size_bytes": 0
            }

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("SELECT COUNT(*) FROM logs")
                count = cursor.fetchone()[0]

                cursor.execute("SELECT MIN(timestamp), MAX(timestamp) FROM logs")
                row = cursor.fetchone()
                oldest = row[0]
                newest = row[1]

            # Get file size
            size_bytes = 0
            if Path(self.db_path).exists():
                size_bytes = Path(self.db_path).stat().st_size

            return {
                "enabled": True,
                "count": count,
                "oldest": oldest,
                "newest": newest,
                "size_bytes": size_bytes,
                "retention_days": LOG_SQLITE_RETENTION_DAYS,
                "max_rows": LOG_SQLITE_MAX_ROWS
            }

        except Exception as e:
            logger.error(f"Failed to get log stats: {e}")
            return {
                "enabled": True,
                "count": 0,
                "oldest": None,
                "newest": None,
                "size_bytes": 0,
                "error": str(e)
            }

    def close(self) -> None:
        """Close database connections."""
        if hasattr(self._local, 'connection') and self._local.connection:
            try:
                self._local.connection.close()
            except Exception:
                pass
            self._local.connection = None


# ============================================================
# SQLite Log Handler
# ============================================================

class SQLiteLogHandler(logging.Handler):
    """Logging handler that writes to SQLite log store.

    Integrates with Python's logging framework to automatically
    capture logs for admin dashboard.

    Usage:
        handler = SQLiteLogHandler(log_store)
        handler.setLevel(logging.INFO)
        logging.getLogger().addHandler(handler)
    """

    def __init__(self, log_store: LogStore):
        """Initialize the handler.

        Args:
            log_store: LogStore instance to write to.
        """
        super().__init__()
        self.log_store = log_store

    def emit(self, record: logging.LogRecord) -> None:
        """Write a log record to the store.

        Args:
            record: Log record to write.
        """
        try:
            # Get extra context from request if available
            request_id = getattr(record, 'request_id', None)
            user = getattr(record, 'user', None)
            ip = getattr(record, 'ip', None)

            # Try to get from Flask's g object if not in record
            try:
                from flask import g, has_request_context
                if has_request_context():
                    if not request_id:
                        request_id = getattr(g, 'request_id', None)
                    if not user:
                        user = getattr(g, 'user_email', None)
                    if not ip:
                        from flask import request
                        ip = request.remote_addr
            except ImportError:
                pass

            self.log_store.write_log(
                level=record.levelname,
                logger_name=record.name,
                message=self.format(record),
                request_id=request_id,
                user=user,
                ip=ip
            )
        except Exception:
            # Never let handler errors propagate
            self.handleError(record)


# ============================================================
# Global Log Store Instance
# ============================================================

_LOG_STORE: Optional[LogStore] = None


def get_log_store() -> LogStore:
    """Get or create the global log store instance."""
    global _LOG_STORE
    if _LOG_STORE is None:
        _LOG_STORE = LogStore()
        if LOG_STORE_ENABLED:
            _LOG_STORE.initialize()
    return _LOG_STORE


def get_sqlite_log_handler() -> SQLiteLogHandler:
    """Get a configured SQLite log handler.

    Returns:
        Configured SQLiteLogHandler instance.
    """
    handler = SQLiteLogHandler(get_log_store())
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter('%(message)s'))
    return handler
