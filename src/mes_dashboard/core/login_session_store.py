# -*- coding: utf-8 -*-
"""SQLite-based login session store.

Stores login session records in a local SQLite database for user tracking.
Follows the LogStore pattern with dual-layer SQLite + MySQL sync support.
"""

from __future__ import annotations

import logging
import os
import socket
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

logger = logging.getLogger('mes_dashboard.login_session_store')

# ============================================================
# Configuration
# ============================================================

LOGIN_SESSION_SQLITE_PATH = os.getenv(
    'LOGIN_SESSION_SQLITE_PATH',
    'logs/login_sessions.sqlite'
)

_HOSTNAME = socket.gethostname()

# ============================================================
# Database Schema
# ============================================================

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS login_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    emp_id TEXT NOT NULL,
    username TEXT NOT NULL,
    display_name TEXT NOT NULL,
    real_name TEXT,
    department TEXT,
    email TEXT,
    phone TEXT,
    domain TEXT,
    ip TEXT,
    login_time TEXT NOT NULL,
    last_active TEXT,
    logout_time TEXT,
    duration_sec INTEGER,
    is_admin INTEGER DEFAULT 0,
    sync_id TEXT,
    synced INTEGER DEFAULT 0
);
"""

_CREATE_INDEXES_SQL = [
    "CREATE INDEX IF NOT EXISTS idx_login_time ON login_sessions(login_time);",
    "CREATE INDEX IF NOT EXISTS idx_synced ON login_sessions(synced);",
    "CREATE INDEX IF NOT EXISTS idx_session_id ON login_sessions(session_id);",
]


# ============================================================
# LoginSessionStore Implementation
# ============================================================

class LoginSessionStore:
    """SQLite-based login session storage.

    Thread-safe implementation using thread-local SQLite connections.
    Supports the dual-layer SQLite + MySQL sync via SyncWorker.
    """

    def __init__(self, db_path: str = LOGIN_SESSION_SQLITE_PATH):
        self.db_path = db_path
        self._local = threading.local()
        self._write_lock = threading.Lock()
        self._initialized = False

    def initialize(self) -> None:
        """Initialize the database schema (idempotent)."""
        if self._initialized:
            return

        db_dir = Path(self.db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(_CREATE_TABLE_SQL)
            for index_sql in _CREATE_INDEXES_SQL:
                cursor.execute(index_sql)
            conn.commit()

        self._initialized = True
        logger.info("LoginSessionStore initialized at %s", self.db_path)

    @contextmanager
    def _get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Get a thread-local database connection."""
        if not hasattr(self._local, 'connection') or self._local.connection is None:
            self._local.connection = sqlite3.connect(
                self.db_path,
                timeout=30.0,
                check_same_thread=False,
            )
            self._local.connection.row_factory = sqlite3.Row
            self._local.connection.execute('PRAGMA journal_mode=WAL')
            self._local.connection.execute('PRAGMA synchronous=NORMAL')

        try:
            yield self._local.connection
        except sqlite3.Error as e:
            logger.error("LoginSessionStore DB error: %s", e)
            try:
                self._local.connection.close()
            except Exception:
                pass
            self._local.connection = None
            raise

    def _generate_sync_id(self, rowid: int) -> str:
        return f"{_HOSTNAME}_login_{rowid}"

    def create_session(self, user_info: Dict[str, Any], ip: str) -> str:
        """Record a new login session, or resume an existing active one.

        If the user already has an active session (no logout, within 8 hours),
        reuse it — update last_active and return the existing session_id.
        Otherwise close any expired orphan sessions and create a new one.
        """
        if not self._initialized:
            self.initialize()

        now = datetime.now()
        now_iso = now.isoformat()
        emp_id = str(user_info.get("username", ""))
        session_lifetime_hours = 8

        try:
            with self._write_lock:
                with self._get_connection() as conn:
                    cursor = conn.cursor()

                    # Check for an existing active session (no logout, within 8h).
                    cutoff = (now - timedelta(hours=session_lifetime_hours)).isoformat()
                    cursor.execute(
                        """
                        SELECT session_id, login_time FROM login_sessions
                        WHERE emp_id = ? AND logout_time IS NULL
                          AND login_time >= ?
                        ORDER BY id DESC LIMIT 1
                        """,
                        (emp_id, cutoff),
                    )
                    active = cursor.fetchone()

                    if active:
                        # Resume existing session — update last_active.
                        existing_sid = active[0]
                        cursor.execute(
                            "UPDATE login_sessions SET last_active = ?, synced = 0 "
                            "WHERE session_id = ?",
                            (now_iso, existing_sid),
                        )
                        conn.commit()
                        logger.info("Resumed session %s for user %s", existing_sid, emp_id)
                        return existing_sid

                    # Close any expired orphan sessions for this user.
                    cursor.execute(
                        """
                        UPDATE login_sessions
                        SET logout_time = ?, duration_sec = CAST(
                            (julianday(?) - julianday(login_time)) * 86400 AS INTEGER
                        ), synced = 0
                        WHERE emp_id = ? AND logout_time IS NULL
                        """,
                        (now_iso, now_iso, emp_id),
                    )

                    # Create a new session.
                    session_id = str(uuid.uuid4())
                    display_name = str(user_info.get("displayName", ""))
                    real_name = str(user_info.get("real_name", ""))
                    is_admin_flag = 1 if user_info.get("is_admin") else 0

                    cursor.execute(
                        """
                        INSERT INTO login_sessions
                            (session_id, emp_id, username, display_name, real_name,
                             department, email, phone, domain, ip,
                             login_time, last_active, is_admin, synced)
                        VALUES
                            (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                        """,
                        (
                            session_id,
                            emp_id,
                            emp_id,
                            display_name,
                            real_name,
                            user_info.get("department"),
                            user_info.get("mail"),
                            user_info.get("telephoneNumber"),
                            user_info.get("domain"),
                            ip,
                            now_iso,
                            now_iso,
                            is_admin_flag,
                        ),
                    )
                    rowid = cursor.lastrowid
                    cursor.execute(
                        "UPDATE login_sessions SET sync_id = ? WHERE id = ?",
                        (self._generate_sync_id(rowid), rowid),
                    )
                    conn.commit()
            return session_id
        except Exception as e:
            logger.error("Failed to create login session: %s", e)
            return str(uuid.uuid4())

    def update_last_active(self, session_id: str) -> None:
        """Update last_active timestamp for an active session (heartbeat).

        Only resets synced=0 if the row is currently synced=1, avoiding
        unnecessary re-sync of rows the SyncWorker hasn't picked up yet.

        If the session was closed (e.g. by graceful shutdown) but the user is
        still active (Flask session cookie survived restart), reopen it by
        clearing logout_time and duration_sec.
        """
        if not self._initialized:
            return
        now = datetime.now().isoformat()
        try:
            with self._write_lock:
                with self._get_connection() as conn:
                    # Reopen sessions closed by server restart while user stayed active.
                    conn.execute(
                        "UPDATE login_sessions "
                        "SET logout_time = NULL, duration_sec = NULL, "
                        "    last_active = ?, synced = 0 "
                        "WHERE session_id = ? AND logout_time IS NOT NULL",
                        (now, session_id),
                    )
                    conn.execute(
                        "UPDATE login_sessions SET last_active = ?, synced = 0 "
                        "WHERE session_id = ? AND (synced = 1 OR last_active IS NULL)",
                        (now, session_id),
                    )
                    # Also update last_active even if synced is already 0
                    conn.execute(
                        "UPDATE login_sessions SET last_active = ? "
                        "WHERE session_id = ? AND synced = 0",
                        (now, session_id),
                    )
                    conn.commit()
        except Exception as e:
            logger.error("Failed to update_last_active: %s", e)

    def close_session(self, session_id: str) -> None:
        """Record logout: set logout_time and compute duration_sec using last_active."""
        if not self._initialized:
            return
        now = datetime.now()
        now_iso = now.isoformat()
        try:
            with self._write_lock:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT login_time, last_active FROM login_sessions WHERE session_id = ?",
                        (session_id,),
                    )
                    row = cursor.fetchone()
                    duration_sec = None
                    if row:
                        try:
                            login_dt = datetime.fromisoformat(row[0])
                            last_active = row[1]
                            if last_active:
                                ref_dt = datetime.fromisoformat(last_active)
                            else:
                                ref_dt = now
                            duration_sec = int((ref_dt - login_dt).total_seconds())
                        except (ValueError, TypeError):
                            pass
                    conn.execute(
                        """
                        UPDATE login_sessions
                        SET logout_time = ?, duration_sec = ?, synced = 0
                        WHERE session_id = ?
                        """,
                        (now_iso, duration_sec, session_id),
                    )
                    conn.commit()
        except Exception as e:
            logger.error("Failed to close_session: %s", e)

    def get_active_count(self) -> int:
        """Return count of sessions active within the last 30 minutes."""
        if not self._initialized:
            self.initialize()
        cutoff = (datetime.now() - timedelta(minutes=30)).isoformat()
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT COUNT(*) FROM login_sessions "
                    "WHERE logout_time IS NULL AND last_active >= ?",
                    (cutoff,),
                )
                row = cursor.fetchone()
                return row[0] if row else 0
        except Exception as e:
            logger.error("Failed to get_active_count: %s", e)
            return 0

    def close_all_active_sessions(self) -> int:
        """Close all sessions with logout_time IS NULL using last_active as logout time.

        Returns count of sessions closed.
        """
        if not self._initialized:
            return 0
        try:
            with self._write_lock:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        """
                        UPDATE login_sessions
                        SET logout_time = COALESCE(last_active, login_time),
                            duration_sec = CAST(
                                (julianday(COALESCE(last_active, login_time))
                                 - julianday(login_time)) * 86400
                                AS INTEGER
                            ),
                            synced = 0
                        WHERE logout_time IS NULL
                        """
                    )
                    count = cursor.rowcount
                    conn.commit()
            if count > 0:
                logger.info("close_all_active_sessions: closed %d sessions", count)
            return count
        except Exception as e:
            logger.error("Failed to close_all_active_sessions: %s", e)
            return 0

    def get_unsynced(self, batch_size: int = 500) -> List[Dict[str, Any]]:
        """Return up to batch_size unsynced login session rows."""
        if not self._initialized:
            self.initialize()
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT * FROM login_sessions WHERE synced = 0 ORDER BY id ASC LIMIT ?",
                    (batch_size,),
                )
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error("Failed to get_unsynced login sessions: %s", e)
            return []

    def mark_synced(self, rowids: List[int]) -> None:
        """Mark the given row ids as synced=1."""
        if not rowids or not self._initialized:
            return
        try:
            with self._write_lock:
                with self._get_connection() as conn:
                    placeholders = ",".join("?" * len(rowids))
                    conn.execute(
                        f"UPDATE login_sessions SET synced = 1 WHERE id IN ({placeholders})",
                        rowids,
                    )
                    conn.commit()
        except Exception as e:
            logger.error("Failed to mark_synced login sessions: %s", e)

    def cleanup_orphan_sessions(self, older_than_hours: int = 8) -> int:
        """Close orphan sessions older than older_than_hours using last_active as logout time.

        Returns count of sessions closed.
        """
        if not self._initialized:
            return 0
        cutoff = (datetime.now() - timedelta(hours=older_than_hours)).isoformat()
        try:
            with self._write_lock:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        """
                        UPDATE login_sessions
                        SET logout_time = COALESCE(last_active, login_time),
                            duration_sec = CAST(
                                (julianday(COALESCE(last_active, login_time))
                                 - julianday(login_time)) * 86400
                                AS INTEGER
                            ),
                            synced = 0
                        WHERE logout_time IS NULL AND login_time < ?
                        """,
                        (cutoff,),
                    )
                    count = cursor.rowcount
                    conn.commit()
            return count
        except Exception as e:
            logger.error("Failed to cleanup_orphan_sessions: %s", e)
            return 0

    def cleanup_synced(self, older_than_hours: int = 24) -> int:
        """Delete synced=1 records older than older_than_hours. Returns deleted count."""
        if not self._initialized:
            return 0
        cutoff = (datetime.now() - timedelta(hours=older_than_hours)).isoformat()
        try:
            with self._write_lock:
                with self._get_connection() as conn:
                    cursor = conn.execute(
                        "DELETE FROM login_sessions WHERE synced = 1 AND login_time < ?",
                        (cutoff,),
                    )
                    deleted = cursor.rowcount
                    conn.commit()
            if deleted > 0:
                logger.info("Cleaned up %d synced login session entries", deleted)
            return deleted
        except Exception as e:
            logger.error("Failed to cleanup_synced login sessions: %s", e)
            return 0

    def close(self) -> None:
        """Close thread-local database connection."""
        if hasattr(self._local, 'connection') and self._local.connection:
            try:
                self._local.connection.close()
            except Exception:
                pass
            self._local.connection = None


# ============================================================
# Global Singleton Factory
# ============================================================

_LOGIN_SESSION_STORE: Optional[LoginSessionStore] = None


def get_login_session_store() -> LoginSessionStore:
    """Get or create the global LoginSessionStore instance."""
    global _LOGIN_SESSION_STORE
    if _LOGIN_SESSION_STORE is None:
        _LOGIN_SESSION_STORE = LoginSessionStore()
        _LOGIN_SESSION_STORE.initialize()
    return _LOGIN_SESSION_STORE
