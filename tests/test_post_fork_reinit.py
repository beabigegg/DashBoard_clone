# -*- coding: utf-8 -*-
"""Unit tests for post_fork reinitialization primitives (IP-3, IP-4, IP-5).

Tier 1 — no pytest marker; runs in default ``pytest`` with no real Oracle/Redis
required.  All external dependencies are mocked.

Test names and AC mapping:
  AC-3  test_close_redis_disposes_connection_pool
  AC-4  test_sqlite_handles_reopen_per_worker
"""

from __future__ import annotations

import os
import threading
import types
from unittest import mock

import pytest


# ---------------------------------------------------------------------------
# AC-3: Redis pool disposal
# ---------------------------------------------------------------------------


def test_close_redis_disposes_connection_pool():
    """close_redis() must disconnect (dispose) the underlying connection pool.

    The Redis client exposes a ``connection_pool`` attribute; calling
    ``close()`` on the client should trigger ``connection_pool.disconnect()``.
    This test verifies the module-level ``_REDIS_CLIENT`` singleton is set to
    None after close_redis(), so the next lazy initialisation in the new worker
    process creates a fresh pool rather than reusing a shared (fork-inherited) one.
    """
    from mes_dashboard.core import redis_client as rc

    mock_pool = mock.MagicMock()
    mock_client = mock.MagicMock()
    mock_client.connection_pool = mock_pool

    original_client = rc._REDIS_CLIENT
    original_control = rc._REDIS_CONTROL_CLIENT
    try:
        rc._REDIS_CLIENT = mock_client
        rc._REDIS_CONTROL_CLIENT = None

        rc.close_redis()

        # After close_redis(), the module-level handle must be None so the
        # worker's lazy initialisation creates a fresh pool.
        assert rc._REDIS_CLIENT is None
        # The close() call is what drops the connection pool.
        mock_client.close.assert_called_once()
    finally:
        rc._REDIS_CLIENT = original_client
        rc._REDIS_CONTROL_CLIENT = original_control


def test_close_redis_handles_control_client_separately():
    """close_redis() must also close the control-plane Redis client if present."""
    from mes_dashboard.core import redis_client as rc

    mock_main = mock.MagicMock()
    mock_ctrl = mock.MagicMock()

    original_client = rc._REDIS_CLIENT
    original_control = rc._REDIS_CONTROL_CLIENT
    try:
        rc._REDIS_CLIENT = mock_main
        rc._REDIS_CONTROL_CLIENT = mock_ctrl

        rc.close_redis()

        assert rc._REDIS_CLIENT is None
        assert rc._REDIS_CONTROL_CLIENT is None
        mock_main.close.assert_called_once()
        mock_ctrl.close.assert_called_once()
    finally:
        rc._REDIS_CLIENT = original_client
        rc._REDIS_CONTROL_CLIENT = original_control


# ---------------------------------------------------------------------------
# AC-4: SQLite handle reopen per worker
# ---------------------------------------------------------------------------


def test_sqlite_handles_reopen_per_worker():
    """_reinit_sqlite_handles() must close and clear the thread-local SQLite
    connections for log_store, login_session_store, and metrics_history so that
    each post-fork worker obtains a fresh (non-inherited) handle on next access.

    We verify the inherited handle is distinct from the child handle by checking
    that the module-level store's thread-local connection is None after reinit
    (the next _get_connection() call will open a fresh fd).

    NOTE: FLASK_TESTING must NOT be set while calling the function under test,
    because the function's own guard short-circuits on FLASK_TESTING.
    """
    # Ensure FLASK_TESTING is not set so the production code path runs.
    original_testing = os.environ.pop("FLASK_TESTING", None)
    try:
        from mes_dashboard.app import _reinit_sqlite_handles
        from mes_dashboard.core import log_store as ls_mod
        from mes_dashboard.core import login_session_store as lss_mod
        from mes_dashboard.core import metrics_history as mh_mod

        # Plant a mock connection on the thread-local of each singleton.
        mock_conn_ls = mock.MagicMock()
        mock_conn_lss = mock.MagicMock()
        mock_conn_mh = mock.MagicMock()

        store_ls = ls_mod.get_log_store()
        store_ls._local.connection = mock_conn_ls

        store_lss = lss_mod.get_login_session_store()
        store_lss._local.connection = mock_conn_lss

        store_mh = mh_mod.get_metrics_history_store()
        store_mh._local.connection = mock_conn_mh

        _reinit_sqlite_handles()

        # After reinit the thread-local connections should be cleared (None),
        # so the next access creates a fresh fd — not the inherited pre-fork fd.
        assert store_ls._local.connection is None, (
            "log_store thread-local connection was not cleared by _reinit_sqlite_handles"
        )
        assert store_lss._local.connection is None, (
            "login_session_store thread-local connection was not cleared by _reinit_sqlite_handles"
        )
        assert store_mh._local.connection is None, (
            "metrics_history thread-local connection was not cleared by _reinit_sqlite_handles"
        )
    finally:
        # Restore FLASK_TESTING state so other tests are not affected.
        if original_testing is not None:
            os.environ["FLASK_TESTING"] = original_testing


def test_reinit_sqlite_handles_returns_early_in_test_mode():
    """_reinit_sqlite_handles() must no-op when FLASK_TESTING is set, so it is
    safe to call in test suites without touching real SQLite databases."""
    os.environ["FLASK_TESTING"] = "true"
    try:
        from mes_dashboard.app import _reinit_sqlite_handles
        # Should not raise and should return None (early return)
        result = _reinit_sqlite_handles()
        assert result is None
    finally:
        os.environ.pop("FLASK_TESTING", None)


def test_start_per_worker_services_returns_early_in_test_mode():
    """_start_per_worker_services() must no-op when FLASK_TESTING is set."""
    os.environ["FLASK_TESTING"] = "true"
    try:
        from mes_dashboard.app import _start_per_worker_services
        result = _start_per_worker_services()
        assert result is None
    finally:
        os.environ.pop("FLASK_TESTING", None)
