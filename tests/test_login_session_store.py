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


# ---------------------------------------------------------------------------
# Presence (online) vs engagement (active) windows — query-arch B-1
# ---------------------------------------------------------------------------

def _insert_session(temp_db_path, *, sid, minutes_ago, logged_out=False):
    """Insert a session whose last_active is `minutes_ago` in the past."""
    now = datetime.now()
    last_active = (now - timedelta(minutes=minutes_ago)).isoformat()
    logout_time = now.isoformat() if logged_out else None
    conn = sqlite3.connect(temp_db_path)
    conn.execute(
        """
        INSERT INTO login_sessions
            (session_id, emp_id, username, display_name, login_time,
             last_active, logout_time, synced)
        VALUES (?, 'U001', 'user1', 'User One', ?, ?, ?, 0)
        """,
        (sid, last_active, last_active, logout_time),
    )
    conn.commit()
    conn.close()


def test_online_count_uses_tighter_window_than_active_count(store, temp_db_path):
    """Default windows: online=15 min, active=30 min.

    - 10 min ago  → counts in BOTH online and active
    - 20 min ago  → counts in active only (outside the 15-min presence window)
    - 40 min ago  → counts in NEITHER
    - 5 min ago but logged out → counts in NEITHER (logout_time excludes it)
    """
    _insert_session(temp_db_path, sid="s-10m", minutes_ago=10)
    _insert_session(temp_db_path, sid="s-20m", minutes_ago=20)
    _insert_session(temp_db_path, sid="s-40m", minutes_ago=40)
    _insert_session(temp_db_path, sid="s-out", minutes_ago=5, logged_out=True)

    assert store.get_online_count() == 1, "only the 10-min session is within 15-min presence"
    assert store.get_active_count() == 2, "10-min and 20-min sessions within 30-min engagement"


def test_active_count_default_window_is_30_min(store, temp_db_path):
    """Behaviour-preservation: get_active_count() default stays a 30-min window."""
    _insert_session(temp_db_path, sid="s-29m", minutes_ago=29)
    _insert_session(temp_db_path, sid="s-31m", minutes_ago=31)
    assert store.get_active_count() == 1


def test_windows_are_configurable(store, temp_db_path, monkeypatch):
    """Module-level window globals are read at call time (monkeypatchable)."""
    import mes_dashboard.core.login_session_store as mod

    _insert_session(temp_db_path, sid="s-22m", minutes_ago=22)
    # Default 15-min presence excludes a 22-min-old session.
    assert store.get_online_count() == 0
    # Widen the presence window to 25 min → now included.
    monkeypatch.setattr(mod, "ONLINE_WINDOW_MINUTES", 25)
    assert store.get_online_count() == 1


def test_count_window_override_argument(store, temp_db_path):
    """Explicit window_minutes overrides the module default."""
    _insert_session(temp_db_path, sid="s-12m", minutes_ago=12)
    assert store.get_online_count(window_minutes=10) == 0
    assert store.get_online_count(window_minutes=20) == 1
