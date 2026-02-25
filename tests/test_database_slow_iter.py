# -*- coding: utf-8 -*-
"""Unit tests for read_sql_df_slow_iter (fetchmany iterator)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import mes_dashboard.core.database as db


@patch.object(db, "oracledb")
@patch.object(db, "_get_slow_query_semaphore")
@patch.object(db, "get_db_runtime_config")
def test_slow_iter_yields_batches(mock_runtime, mock_sem_fn, mock_oracledb):
    """read_sql_df_slow_iter should yield (columns, rows) batches via fetchmany."""
    mock_runtime.return_value = {
        "slow_call_timeout_ms": 60000,
        "slow_fetchmany_size": 2,
        "tcp_connect_timeout": 10,
        "retry_count": 1,
        "retry_delay": 1.0,
    }

    sem = MagicMock()
    sem.acquire.return_value = True
    mock_sem_fn.return_value = sem

    cursor = MagicMock()
    cursor.description = [("COL_A",), ("COL_B",)]
    cursor.fetchmany.side_effect = [
        [("r1a", "r1b"), ("r2a", "r2b")],
        [("r3a", "r3b")],
        [],
    ]

    conn = MagicMock()
    conn.cursor.return_value = cursor
    mock_oracledb.connect.return_value = conn

    batches = list(db.read_sql_df_slow_iter("SELECT 1", {"p0": "x"}, batch_size=2))

    assert len(batches) == 2
    assert batches[0] == (["COL_A", "COL_B"], [("r1a", "r1b"), ("r2a", "r2b")])
    assert batches[1] == (["COL_A", "COL_B"], [("r3a", "r3b")])
    cursor.fetchmany.assert_called_with(2)
    conn.close.assert_called_once()
    sem.release.assert_called_once()


@patch.object(db, "oracledb")
@patch.object(db, "_get_slow_query_semaphore")
@patch.object(db, "get_db_runtime_config")
def test_slow_iter_empty_result(mock_runtime, mock_sem_fn, mock_oracledb):
    """read_sql_df_slow_iter should yield nothing for empty result."""
    mock_runtime.return_value = {
        "slow_call_timeout_ms": 60000,
        "slow_fetchmany_size": 5000,
        "tcp_connect_timeout": 10,
        "retry_count": 1,
        "retry_delay": 1.0,
    }

    sem = MagicMock()
    sem.acquire.return_value = True
    mock_sem_fn.return_value = sem

    cursor = MagicMock()
    cursor.description = [("ID",)]
    cursor.fetchmany.return_value = []

    conn = MagicMock()
    conn.cursor.return_value = cursor
    mock_oracledb.connect.return_value = conn

    batches = list(db.read_sql_df_slow_iter("SELECT 1"))

    assert batches == []
    conn.close.assert_called_once()
    sem.release.assert_called_once()


@patch.object(db, "oracledb")
@patch.object(db, "_get_slow_query_semaphore")
@patch.object(db, "get_db_runtime_config")
def test_slow_iter_releases_on_error(mock_runtime, mock_sem_fn, mock_oracledb):
    """Semaphore and connection should be released even on error."""
    mock_runtime.return_value = {
        "slow_call_timeout_ms": 60000,
        "slow_fetchmany_size": 5000,
        "tcp_connect_timeout": 10,
        "retry_count": 1,
        "retry_delay": 1.0,
    }

    sem = MagicMock()
    sem.acquire.return_value = True
    mock_sem_fn.return_value = sem

    conn = MagicMock()
    conn.cursor.side_effect = RuntimeError("cursor failed")
    mock_oracledb.connect.return_value = conn

    try:
        list(db.read_sql_df_slow_iter("SELECT 1"))
    except RuntimeError:
        pass

    conn.close.assert_called_once()
    sem.release.assert_called_once()


def test_runtime_config_includes_fetchmany_size():
    """get_db_runtime_config should include slow_fetchmany_size."""
    # Force refresh to pick up current config
    db._DB_RUNTIME_CONFIG = None
    runtime = db.get_db_runtime_config(refresh=True)
    assert "slow_fetchmany_size" in runtime
    assert isinstance(runtime["slow_fetchmany_size"], int)
    assert runtime["slow_fetchmany_size"] > 0
