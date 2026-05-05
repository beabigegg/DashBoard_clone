# -*- coding: utf-8 -*-
"""Unit tests for reject_cache_sql_runtime.py — DuckDB-backed reject SQL helpers."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from unittest.mock import MagicMock

from mes_dashboard.services.reject_cache_sql_runtime import (
    _qid,
    _sql_str_literal,
    _norm_value_expr,
    _append_in_condition,
    _attach_spool_source_view,
    SQL_FALLBACK_DISABLED,
    SQL_FALLBACK_DEP_MISSING,
    SQL_FALLBACK_SPOOL_MISS,
    SQL_FALLBACK_RUNTIME_ERROR,
)


class TestQidHelper:
    def test_wraps_in_double_quotes(self):
        assert _qid("REASON") == '"REASON"'

    def test_escapes_embedded_double_quote(self):
        result = _qid('bad"col')
        assert '""' in result


class TestSqlStrLiteralHelper:
    def test_wraps_in_single_quotes(self):
        assert _sql_str_literal("abc") == "'abc'"

    def test_escapes_single_quote(self):
        result = _sql_str_literal("O'Brien")
        assert "''" in result


class TestNormValueExpr:
    def test_returns_case_expression(self):
        result = _norm_value_expr("MY_COL")
        assert "CASE" in result
        assert "WHEN" in result
        assert "(未知)" in result

    def test_quotes_column_name(self):
        result = _norm_value_expr("REASON")
        assert '"REASON"' in result

    def test_trims_value(self):
        result = _norm_value_expr("COL")
        assert "TRIM" in result


class TestAppendInCondition:
    def test_appends_in_clause(self):
        conditions = []
        params = []
        _append_in_condition(
            conditions,
            params,
            expr="TRIM(COL)",
            values=["A", "B"],
        )
        assert len(conditions) == 1
        assert "IN" in conditions[0]
        assert "A" in params
        assert "B" in params

    def test_empty_values_adds_nothing(self):
        conditions = []
        params = []
        _append_in_condition(
            conditions,
            params,
            expr="TRIM(COL)",
            values=[],
        )
        assert conditions == []
        assert params == []

    def test_whitespace_only_values_filtered(self):
        conditions = []
        params = []
        _append_in_condition(
            conditions,
            params,
            expr="TRIM(COL)",
            values=["  ", "\t", ""],
        )
        assert conditions == []

    def test_handles_multiple_values_with_normalization(self):
        # _append_in_condition normalizes values but does NOT deduplicate
        conditions = []
        params = []
        _append_in_condition(
            conditions,
            params,
            expr="TRIM(COL)",
            values=["A", "B", "C"],
        )
        assert len(params) == 3
        assert "A" in params
        assert "B" in params


class TestAttachSpoolSourceView:
    def test_creates_reject_src_view(self):
        mock_conn = MagicMock()
        _attach_spool_source_view(mock_conn, "/data/test.parquet")
        sql = mock_conn.execute.call_args[0][0]
        assert "reject_src" in sql
        assert "read_parquet" in sql

    def test_uses_create_or_replace(self):
        mock_conn = MagicMock()
        _attach_spool_source_view(mock_conn, "/data/test.parquet")
        sql = mock_conn.execute.call_args[0][0]
        assert "CREATE OR REPLACE TEMP VIEW" in sql


class TestFallbackConstants:
    def test_disabled_value(self):
        assert SQL_FALLBACK_DISABLED == "cache_sql_disabled"

    def test_dep_missing_value(self):
        assert SQL_FALLBACK_DEP_MISSING == "cache_sql_dependency_missing"

    def test_spool_miss_value(self):
        assert SQL_FALLBACK_SPOOL_MISS == "cache_sql_spool_miss"

    def test_runtime_error_value(self):
        assert SQL_FALLBACK_RUNTIME_ERROR == "cache_sql_runtime_error"
