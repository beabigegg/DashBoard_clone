from unittest.mock import MagicMock

import pytest

from mes_dashboard.core import database


def test_read_sql_df_slow_closes_cursor_when_fetch_fails(monkeypatch):
    database._SLOW_QUERY_SEMAPHORE = None
    database._SLOW_QUERY_ACTIVE = 0
    cursor = MagicMock()
    cursor.description = [("ID",)]
    cursor.fetchall.side_effect = RuntimeError("fetch failed")
    conn = MagicMock()
    conn.cursor.return_value = cursor

    monkeypatch.setattr(
        database,
        "get_db_runtime_config",
        lambda: {
            "slow_call_timeout_ms": 10000,
            "slow_pool_timeout": 1,
            "slow_max_concurrent": 1,
            "slow_pool_enabled": False,
        },
    )
    monkeypatch.setattr(
        database,
        "_get_slow_query_connection",
        lambda runtime, timeout_ms: (conn, False),
    )
    monkeypatch.setattr(
        "mes_dashboard.core.metrics.record_query_latency", lambda elapsed: None
    )

    with pytest.raises(RuntimeError, match="fetch failed"):
        database.read_sql_df_slow("select 1 from dual")

    cursor.close.assert_called_once()
    conn.close.assert_called_once()
    assert database.get_slow_query_active_count() == 0


def test_read_sql_df_slow_iter_closes_cursor_when_consumer_stops(monkeypatch):
    database._SLOW_QUERY_SEMAPHORE = None
    database._SLOW_QUERY_ACTIVE = 0
    cursor = MagicMock()
    cursor.description = [("ID",)]
    cursor.fetchmany.return_value = [(1,)]
    conn = MagicMock()
    conn.cursor.return_value = cursor

    monkeypatch.setattr(
        database,
        "get_db_runtime_config",
        lambda: {
            "slow_call_timeout_ms": 10000,
            "slow_fetchmany_size": 100,
            "slow_pool_timeout": 1,
            "slow_max_concurrent": 1,
            "slow_pool_enabled": False,
        },
    )
    monkeypatch.setattr(
        database,
        "_get_slow_query_connection",
        lambda runtime, timeout_ms: (conn, False),
    )
    monkeypatch.setattr(
        "mes_dashboard.core.metrics.record_query_latency", lambda elapsed: None
    )

    gen = database.read_sql_df_slow_iter("select 1 from dual")
    assert next(gen) == (["ID"], [(1,)])
    gen.close()

    cursor.close.assert_called_once()
    conn.close.assert_called_once()
    assert database.get_slow_query_active_count() == 0
