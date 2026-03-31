# -*- coding: utf-8 -*-
"""Unit tests for production_history_sql_runtime.py — DuckDB view helpers."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from unittest.mock import MagicMock

from mes_dashboard.services.production_history_sql_runtime import (
    _qid,
    _sql_str,
    _attach_spool_view,
    _fetch_dict_rows,
    _SPOOL_NAMESPACE,
)


class TestQidHelper:
    def test_simple_column(self):
        assert _qid("LOT_ID") == '"LOT_ID"'

    def test_escapes_double_quote(self):
        result = _qid('col"x')
        assert '""' in result
        assert result.startswith('"') and result.endswith('"')


class TestSqlStrHelper:
    def test_wraps_in_single_quotes(self):
        assert _sql_str("hello") == "'hello'"

    def test_escapes_single_quote(self):
        result = _sql_str("it's")
        assert "''" in result

    def test_path_string(self):
        result = _sql_str("/tmp/data.parquet")
        assert "/tmp/data.parquet" in result


class TestAttachSpoolView:
    def test_creates_ph_src_view(self):
        mock_conn = MagicMock()
        _attach_spool_view(mock_conn, "/tmp/ph.parquet")
        sql = mock_conn.execute.call_args[0][0]
        assert "ph_src" in sql
        assert "read_parquet" in sql

    def test_create_or_replace_temp_view(self):
        mock_conn = MagicMock()
        _attach_spool_view(mock_conn, "/tmp/ph.parquet")
        sql = mock_conn.execute.call_args[0][0]
        assert "CREATE OR REPLACE TEMP VIEW" in sql


class TestFetchDictRows:
    def test_returns_list_of_dicts(self):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.description = [("WORKORDER",), ("LOT_QTY",)]
        mock_cursor.fetchall.return_value = [("WO001", 100)]
        mock_conn.execute.return_value = mock_cursor
        result = _fetch_dict_rows(mock_conn, "SELECT WORKORDER, LOT_QTY FROM ph_src")
        assert result == [{"WORKORDER": "WO001", "LOT_QTY": 100}]

    def test_empty_result(self):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.description = [("COL",)]
        mock_cursor.fetchall.return_value = []
        mock_conn.execute.return_value = mock_cursor
        result = _fetch_dict_rows(mock_conn, "SELECT COL FROM ph_src")
        assert result == []

    def test_passes_params_to_execute(self):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.description = []
        mock_cursor.fetchall.return_value = []
        mock_conn.execute.return_value = mock_cursor
        _fetch_dict_rows(mock_conn, "SELECT ? FROM ph_src", params=["val"])
        mock_conn.execute.assert_called_once_with("SELECT ? FROM ph_src", ["val"])


class TestSpoolNamespace:
    def test_namespace_is_production_history(self):
        assert _SPOOL_NAMESPACE == "production_history"
