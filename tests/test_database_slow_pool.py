# -*- coding: utf-8 -*-
"""Unit tests for isolated slow-query pool path."""

from __future__ import annotations

import itertools
from unittest.mock import MagicMock, patch

import pandas as pd

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


@patch.object(db, "oracledb")
@patch.object(db, "get_slow_engine")
@patch.object(db, "_get_slow_query_semaphore")
@patch.object(db, "get_db_runtime_config")
def test_read_sql_df_slow_warning_includes_caller_tag(
    mock_runtime,
    mock_sem_fn,
    mock_get_slow_engine,
    mock_oracledb,
):
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
    cursor.description = [("COL_A",)]
    cursor.fetchall.return_value = [("v1",)]
    conn = MagicMock()
    conn.cursor.return_value = cursor
    engine = MagicMock()
    engine.raw_connection.return_value = conn
    mock_get_slow_engine.return_value = engine

    import time as _time_mod

    _real_time = _time_mod.time
    _epoch = [None]

    def _fake_time():
        now = _real_time()
        if _epoch[0] is None:
            _epoch[0] = now
        # Offset every call so elapsed is always > 2s from start_time
        return _epoch[0] + (now - _epoch[0]) + 2.5

    with patch.object(db.time, "time", wraps=_fake_time), \
         patch("mes_dashboard.core.database.logger") as mock_logger:
        db.read_sql_df_slow("SELECT 1", {"p0": "x"}, caller="slow_pool_test")

    # The caller tag should appear in either warning (slow) or debug (fast) log
    all_calls = mock_logger.warning.call_args_list + mock_logger.debug.call_args_list
    assert any(
        call.args and "slow_pool_test" in str(call.args)
        for call in all_calls
    ), f"caller tag not found in log calls: {all_calls}"


def test_read_sql_df_warning_includes_caller_tag():
    circuit_breaker = MagicMock()
    circuit_breaker.allow_request.return_value = True

    conn = MagicMock()
    conn.__enter__.return_value = conn
    conn.__exit__.return_value = False
    engine = MagicMock()
    engine.connect.return_value = conn

    with patch("mes_dashboard.core.circuit_breaker.get_database_circuit_breaker", return_value=circuit_breaker), \
         patch("mes_dashboard.core.circuit_breaker.CIRCUIT_BREAKER_ENABLED", True), \
         patch("mes_dashboard.core.metrics.record_query_latency"), \
         patch.object(db, "get_engine", return_value=engine), \
         patch.object(db.pd, "read_sql", return_value=pd.DataFrame({"A": [1]})), \
         patch("mes_dashboard.core.database.time.time", side_effect=[100.0, 102.2]), \
         patch("mes_dashboard.core.database.logger.warning") as mock_warning:
        db.read_sql_df("SELECT 1", {"p0": "x"}, caller="read_sql_df_test")

    assert any(
        call.args and call.args[0] == "Slow query (%s, %.2fs): %s..."
        and call.args[1] == "read_sql_df_test"
        for call in mock_warning.call_args_list
    )
