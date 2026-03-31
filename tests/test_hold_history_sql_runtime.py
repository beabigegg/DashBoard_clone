# -*- coding: utf-8 -*-
"""Unit tests for hold_history_sql_runtime.py — DuckDB hold-history view helpers."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from unittest.mock import MagicMock

from mes_dashboard.services.hold_history_sql_runtime import (
    _qid,
    _sql_str_literal,
    _attach_spool_view,
    _fetch_dict_rows,
    _sf,
    SQL_FALLBACK_DISABLED,
    SQL_FALLBACK_DEP_MISSING,
    SQL_FALLBACK_SPOOL_MISS,
    SQL_FALLBACK_RUNTIME_ERROR,
    _SPOOL_NAMESPACE,
)


class TestQidHelper:
    def test_quotes_identifier(self):
        assert _qid("HOLDDATE") == '"HOLDDATE"'

    def test_escapes_embedded_double_quote(self):
        result = _qid('bad"col')
        assert '""' in result


class TestSqlStrLiteralHelper:
    def test_wraps_string(self):
        assert _sql_str_literal("abc") == "'abc'"

    def test_escapes_single_quote(self):
        result = _sql_str_literal("O'clock")
        assert "''" in result


class TestAttachSpoolView:
    def test_creates_hold_src_view(self):
        mock_conn = MagicMock()
        _attach_spool_view(mock_conn, "/tmp/hold.parquet")
        sql = mock_conn.execute.call_args[0][0]
        assert "hold_src" in sql
        assert "read_parquet" in sql
        assert "/tmp/hold.parquet" in sql

    def test_create_or_replace_temp_view(self):
        mock_conn = MagicMock()
        _attach_spool_view(mock_conn, "/tmp/hold.parquet")
        sql = mock_conn.execute.call_args[0][0]
        assert "CREATE OR REPLACE TEMP VIEW" in sql


class TestFetchDictRows:
    def test_returns_list_of_dicts(self):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.description = [("col_a",), ("col_b",)]
        mock_cursor.fetchall.return_value = [("val1", "val2"), ("val3", "val4")]
        mock_conn.execute.return_value = mock_cursor
        result = _fetch_dict_rows(mock_conn, "SELECT col_a, col_b FROM hold_src")
        assert result == [
            {"col_a": "val1", "col_b": "val2"},
            {"col_a": "val3", "col_b": "val4"},
        ]

    def test_empty_result_returns_empty_list(self):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.description = [("col_a",)]
        mock_cursor.fetchall.return_value = []
        mock_conn.execute.return_value = mock_cursor
        result = _fetch_dict_rows(mock_conn, "SELECT col_a FROM hold_src")
        assert result == []


class TestSfHelper:
    def test_numeric_value(self):
        assert _sf(5.5) == 5.5

    def test_none_default(self):
        assert _sf(None) == 0.0

    def test_custom_default(self):
        assert _sf(None, default=-1.0) == -1.0

    def test_invalid_value(self):
        assert _sf("nope") == 0.0


class TestFallbackConstants:
    def test_disabled(self):
        assert SQL_FALLBACK_DISABLED == "hold_history_sql_disabled"

    def test_dep_missing(self):
        assert SQL_FALLBACK_DEP_MISSING == "hold_history_sql_dependency_missing"

    def test_spool_miss(self):
        assert SQL_FALLBACK_SPOOL_MISS == "hold_history_sql_spool_miss"

    def test_runtime_error(self):
        assert SQL_FALLBACK_RUNTIME_ERROR == "hold_history_sql_runtime_error"


class TestSpoolNamespace:
    def test_hold_dataset_namespace(self):
        assert _SPOOL_NAMESPACE == "hold_dataset"
