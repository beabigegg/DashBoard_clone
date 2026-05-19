# -*- coding: utf-8 -*-
"""Unit tests for LoginSessionStore — cleanup_synced boundary (AC-2)."""

from __future__ import annotations

import os
import sqlite3
import tempfile
from datetime import datetime, timedelta

import pytest

from mes_dashboard.core.login_session_store import LoginSessionStore


@pytest.fixture
def temp_db_path():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    try:
        os.unlink(path)
    except OSError:
        pass


@pytest.fixture
def store(temp_db_path):
    s = LoginSessionStore(db_path=temp_db_path)
    s.initialize()
    return s


def _insert_synced_session(temp_db_path: str, login_time: str) -> None:
    """Insert a synced=1 session row directly into SQLite for testing."""
    conn = sqlite3.connect(temp_db_path)
    conn.execute(
        """
        INSERT INTO login_sessions
            (session_id, emp_id, username, display_name, login_time, synced)
        VALUES
            (?, 'U001', 'user1', 'User One', ?, 1)
        """,
        (f"sid-{login_time}", login_time),
    )
    conn.commit()
    conn.close()


def test_cleanup_synced_retains_within_24h(store, temp_db_path):
    """Synced session logged in 23 hours ago is retained by cleanup_synced() (AC-2)."""
    ts_23h = (datetime.now() - timedelta(hours=23)).isoformat()
    _insert_synced_session(temp_db_path, ts_23h)

    deleted = store.cleanup_synced()  # default is 24h
    assert deleted == 0, "Session within 24h window must not be deleted"

    conn = sqlite3.connect(temp_db_path)
    count = conn.execute("SELECT COUNT(*) FROM login_sessions").fetchone()[0]
    conn.close()
    assert count == 1


def test_cleanup_synced_deletes_beyond_24h(store, temp_db_path):
    """Synced session logged in 25 hours ago is deleted by cleanup_synced() (AC-2)."""
    ts_25h = (datetime.now() - timedelta(hours=25)).isoformat()
    _insert_synced_session(temp_db_path, ts_25h)

    deleted = store.cleanup_synced()  # default is 24h
    assert deleted == 1, "Session older than 24h must be deleted"

    conn = sqlite3.connect(temp_db_path)
    count = conn.execute("SELECT COUNT(*) FROM login_sessions").fetchone()[0]
    conn.close()
    assert count == 0
