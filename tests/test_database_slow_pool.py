# -*- coding: utf-8 -*-
"""Unit tests for isolated slow-query pool path."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import mes_dashboard.core.database as db


@patch.object(db, "oracledb")
@patch.object(db, "get_slow_engine")
@patch.object(db, "_get_slow_query_semaphore")
@patch.object(db, "get_db_runtime_config")
def test_read_sql_df_slow_uses_slow_pool_when_enabled(
    mock_runtime,
    mock_sem_fn,
    mock_get_slow_engine,
    mock_oracledb,
):
    """Slow query should checkout connection from isolated slow pool."""
    mock_runtime.return_value = {
        "slow_pool_enabled": True,
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
    cursor.description = [("COL_A",), ("COL_B",)]
    cursor.fetchall.return_value = [("v1", "v2")]

    conn = MagicMock()
    conn.cursor.return_value = cursor

    engine = MagicMock()
    engine.raw_connection.return_value = conn
    mock_get_slow_engine.return_value = engine

    df = db.read_sql_df_slow("SELECT 1", {"p0": "x"})

    assert list(df.columns) == ["COL_A", "COL_B"]
    assert len(df) == 1
    mock_get_slow_engine.assert_called_once()
    mock_oracledb.connect.assert_not_called()
    conn.close.assert_called_once()
    sem.release.assert_called_once()


@patch.object(db, "oracledb")
@patch.object(db, "get_slow_engine")
@patch.object(db, "_get_slow_query_semaphore")
@patch.object(db, "get_db_runtime_config")
def test_read_sql_df_slow_iter_uses_slow_pool_when_enabled(
    mock_runtime,
    mock_sem_fn,
    mock_get_slow_engine,
    mock_oracledb,
):
    """Slow iterator query should checkout connection from isolated slow pool."""
    mock_runtime.return_value = {
        "slow_pool_enabled": True,
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
        [("r1a", "r1b")],
        [],
    ]

    conn = MagicMock()
    conn.cursor.return_value = cursor

    engine = MagicMock()
    engine.raw_connection.return_value = conn
    mock_get_slow_engine.return_value = engine

    batches = list(db.read_sql_df_slow_iter("SELECT 1", {"p0": "x"}, batch_size=2))

    assert batches == [(["COL_A", "COL_B"], [("r1a", "r1b")])]
    mock_get_slow_engine.assert_called_once()
    mock_oracledb.connect.assert_not_called()
    conn.close.assert_called_once()
    sem.release.assert_called_once()

