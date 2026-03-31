# -*- coding: utf-8 -*-
"""Unit tests for resource_history_sql_runtime.py — DuckDB view helpers."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from unittest.mock import MagicMock

from mes_dashboard.services.resource_history_sql_runtime import (
    _qid,
    _sql_str_literal,
    _attach_spool_view,
    _attach_oee_spool_view,
    SQL_FALLBACK_DISABLED,
    SQL_FALLBACK_DEP_MISSING,
    SQL_FALLBACK_SPOOL_MISS,
    SQL_FALLBACK_RUNTIME_ERROR,
    _SPOOL_NAMESPACE,
    _OEE_SPOOL_NAMESPACE,
)


class TestQidHelper:
    def test_simple_column(self):
        assert _qid("DATA_DATE") == '"DATA_DATE"'

    def test_escapes_double_quote(self):
        result = _qid('col"x')
        assert result.startswith('"') and result.endswith('"')
        assert '""' in result


class TestSqlStrLiteralHelper:
    def test_wraps_in_single_quotes(self):
        assert _sql_str_literal("/tmp/data.parquet") == "'/tmp/data.parquet'"

    def test_escapes_single_quotes(self):
        result = _sql_str_literal("it's")
        assert "''" in result


class TestAttachSpoolView:
    def test_creates_resource_src_view(self):
        mock_conn = MagicMock()
        _attach_spool_view(mock_conn, "/tmp/resource.parquet")
        sql = mock_conn.execute.call_args[0][0]
        assert "resource_src" in sql
        assert "read_parquet" in sql
        assert "/tmp/resource.parquet" in sql

    def test_uses_create_or_replace_temp_view(self):
        mock_conn = MagicMock()
        _attach_spool_view(mock_conn, "/tmp/resource.parquet")
        sql = mock_conn.execute.call_args[0][0]
        assert "CREATE OR REPLACE TEMP VIEW" in sql


class TestAttachOeeSpoolView:
    def test_creates_oee_src_view(self):
        mock_conn = MagicMock()
        _attach_oee_spool_view(mock_conn, "/tmp/oee.parquet")
        sql = mock_conn.execute.call_args[0][0]
        assert "oee_src" in sql
        assert "read_parquet" in sql


class TestFallbackConstants:
    def test_disabled_constant(self):
        assert SQL_FALLBACK_DISABLED == "resource_history_sql_disabled"

    def test_dep_missing_constant(self):
        assert SQL_FALLBACK_DEP_MISSING == "resource_history_sql_dependency_missing"

    def test_spool_miss_constant(self):
        assert SQL_FALLBACK_SPOOL_MISS == "resource_history_sql_spool_miss"

    def test_runtime_error_constant(self):
        assert SQL_FALLBACK_RUNTIME_ERROR == "resource_history_sql_runtime_error"


class TestSpoolNamespaces:
    def test_primary_namespace(self):
        assert _SPOOL_NAMESPACE == "resource_dataset"

    def test_oee_namespace(self):
        assert _OEE_SPOOL_NAMESPACE == "resource_oee"
