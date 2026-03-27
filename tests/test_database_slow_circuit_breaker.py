# -*- coding: utf-8 -*-
"""Unit tests for read_sql_df_slow circuit breaker integration.

read_sql_df_slow imports get_database_circuit_breaker and CIRCUIT_BREAKER_ENABLED
from mes_dashboard.core.circuit_breaker at call time, so patches must target
that source module.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import mes_dashboard.core.database as db
from mes_dashboard.core.database import DatabaseCircuitOpenError

_CB_MODULE = "mes_dashboard.core.circuit_breaker"


class TestReadSqlDfSlowCircuitBreaker:
    """Tests that read_sql_df_slow checks and records to the circuit breaker."""

    @patch.object(db, "_get_slow_query_semaphore")
    @patch.object(db, "get_db_runtime_config")
    def test_circuit_open_raises_immediately(self, mock_runtime, mock_sem_fn):
        """When circuit breaker is OPEN, read_sql_df_slow raises without querying DB."""
        mock_runtime.return_value = {
            "slow_call_timeout_ms": 60000,
            "tcp_connect_timeout": 10,
            "retry_count": 1,
            "retry_delay": 1.0,
        }
        sem = MagicMock()
        mock_sem_fn.return_value = sem

        mock_breaker = MagicMock()
        mock_breaker.allow_request.return_value = False
        mock_breaker.recovery_timeout = 30

        with patch(f"{_CB_MODULE}.get_database_circuit_breaker", return_value=mock_breaker):
            with patch(f"{_CB_MODULE}.CIRCUIT_BREAKER_ENABLED", True):
                with pytest.raises(DatabaseCircuitOpenError):
                    db.read_sql_df_slow("SELECT 1 FROM DUAL")

        # Semaphore should NOT be acquired — fail fast before taking resources
        sem.acquire.assert_not_called()

    @patch.object(db, "_get_slow_query_connection")
    @patch.object(db, "_get_slow_query_semaphore")
    @patch.object(db, "get_db_runtime_config")
    def test_success_records_to_circuit_breaker(self, mock_runtime, mock_sem_fn, mock_get_conn):
        """Successful slow query records success to circuit breaker."""
        mock_runtime.return_value = {
            "slow_call_timeout_ms": 60000,
            "tcp_connect_timeout": 10,
            "retry_count": 1,
            "retry_delay": 1.0,
        }
        sem = MagicMock()
        sem.acquire.return_value = True
        mock_sem_fn.return_value = sem

        cursor = MagicMock()
        cursor.description = [("COL",)]
        cursor.fetchall.return_value = [("val",)]
        conn = MagicMock()
        conn.cursor.return_value = cursor
        mock_get_conn.return_value = (conn, True)

        mock_breaker = MagicMock()
        mock_breaker.allow_request.return_value = True

        with patch(f"{_CB_MODULE}.get_database_circuit_breaker", return_value=mock_breaker):
            with patch(f"{_CB_MODULE}.CIRCUIT_BREAKER_ENABLED", True):
                with patch("mes_dashboard.core.metrics.record_query_latency"):
                    result = db.read_sql_df_slow("SELECT 1 FROM DUAL")

        mock_breaker.record_success.assert_called_once()
        mock_breaker.record_failure.assert_not_called()
        assert len(result) == 1

    @patch.object(db, "_get_slow_query_connection")
    @patch.object(db, "_get_slow_query_semaphore")
    @patch.object(db, "get_db_runtime_config")
    def test_failure_records_to_circuit_breaker(self, mock_runtime, mock_sem_fn, mock_get_conn):
        """Oracle error during slow query records failure to circuit breaker."""
        mock_runtime.return_value = {
            "slow_call_timeout_ms": 60000,
            "tcp_connect_timeout": 10,
            "retry_count": 1,
            "retry_delay": 1.0,
        }
        sem = MagicMock()
        sem.acquire.return_value = True
        mock_sem_fn.return_value = sem

        conn = MagicMock()
        conn.cursor.side_effect = Exception("ORA-12345: connection lost")
        mock_get_conn.return_value = (conn, True)

        mock_breaker = MagicMock()
        mock_breaker.allow_request.return_value = True

        with patch(f"{_CB_MODULE}.get_database_circuit_breaker", return_value=mock_breaker):
            with patch(f"{_CB_MODULE}.CIRCUIT_BREAKER_ENABLED", True):
                with patch("mes_dashboard.core.metrics.record_query_latency"):
                    with pytest.raises(Exception, match="ORA-12345"):
                        db.read_sql_df_slow("SELECT 1 FROM DUAL")

        mock_breaker.record_failure.assert_called_once()
        mock_breaker.record_success.assert_not_called()
