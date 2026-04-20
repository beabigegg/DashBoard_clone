# -*- coding: utf-8 -*-
"""Unit tests for yield_alert_sql_runtime.py — DuckDB view computation helpers."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import duckdb
import pandas as pd
from unittest.mock import patch, MagicMock

from mes_dashboard.services.yield_alert_sql_runtime import (
    _qid,
    _sql_str_literal,
    _attach_spool_view,
    compute_cross_filter_options,
    SQL_FALLBACK_DISABLED,
    SQL_FALLBACK_DEP_MISSING,
    SQL_FALLBACK_SPOOL_MISS,
    SQL_FALLBACK_RUNTIME_ERROR,
    _SPOOL_NAMESPACE,
    _DEPT_SEQ_MAP,
    _YIELD_WORKCENTER_GROUP_ORDER,
)


class TestQidHelper:
    def test_simple_identifier_quoted(self):
        assert _qid("DATE_BUCKET") == '"DATE_BUCKET"'

    def test_double_quotes_in_name_escaped(self):
        result = _qid('col"bad')
        assert '""' in result

    def test_result_wrapped_in_double_quotes(self):
        result = _qid("X")
        assert result[0] == '"' and result[-1] == '"'


class TestSqlStrLiteralHelper:
    def test_plain_string(self):
        assert _sql_str_literal("abc") == "'abc'"

    def test_single_quote_escaped(self):
        result = _sql_str_literal("it's")
        assert "''" in result

    def test_path_string(self):
        result = _sql_str_literal("/tmp/test.parquet")
        assert "/tmp/test.parquet" in result


class TestAttachSpoolView:
    def test_creates_yield_alert_src_view(self):
        mock_conn = MagicMock()
        _attach_spool_view(mock_conn, "/tmp/test.parquet")
        call_args = mock_conn.execute.call_args[0][0]
        assert "yield_alert_src" in call_args
        assert "read_parquet" in call_args
        assert "/tmp/test.parquet" in call_args

    def test_creates_or_replaces_view(self):
        mock_conn = MagicMock()
        _attach_spool_view(mock_conn, "/tmp/test.parquet")
        call_sql = mock_conn.execute.call_args[0][0]
        assert "CREATE OR REPLACE TEMP VIEW" in call_sql


class TestFallbackConstants:
    def test_disabled_constant(self):
        assert SQL_FALLBACK_DISABLED == "yield_alert_sql_disabled"

    def test_dep_missing_constant(self):
        assert SQL_FALLBACK_DEP_MISSING == "yield_alert_sql_dependency_missing"

    def test_spool_miss_constant(self):
        assert SQL_FALLBACK_SPOOL_MISS == "yield_alert_sql_spool_miss"

    def test_runtime_error_constant(self):
        assert SQL_FALLBACK_RUNTIME_ERROR == "yield_alert_sql_runtime_error"


class TestSpoolNamespace:
    def test_namespace_matches_dataset(self):
        assert _SPOOL_NAMESPACE == "yield_alert_dataset"


class TestDeptSeqMap:
    def test_seq_map_covers_all_workcenter_groups(self):
        for group in _YIELD_WORKCENTER_GROUP_ORDER:
            assert group in _DEPT_SEQ_MAP

    def test_seq_map_values_are_unique_indices(self):
        indices = list(_DEPT_SEQ_MAP.values())
        assert len(indices) == len(set(indices))

    def test_seq_map_starts_at_zero(self):
        assert 0 in _DEPT_SEQ_MAP.values()


class TestCrossFilterOptions:
    def test_compute_cross_filter_options_applies_other_dimension_filters(self, tmp_path, monkeypatch):
        parquet_path = tmp_path / "yield-alert.parquet"
        pd.DataFrame([
            {
                "DEPARTMENT_GROUP": "焊接_WB",
                "LINE_NAME": "L1",
                "PACKAGE_NAME": "PKG-A",
                "TYPE_NAME": "TYPE-A",
                "FUNCTION_NAME": "FUNC-A",
            },
            {
                "DEPARTMENT_GROUP": "焊接_WB",
                "LINE_NAME": "L1",
                "PACKAGE_NAME": "PKG-B",
                "TYPE_NAME": "TYPE-B",
                "FUNCTION_NAME": "FUNC-B",
            },
            {
                "DEPARTMENT_GROUP": "切割",
                "LINE_NAME": "L2",
                "PACKAGE_NAME": "PKG-C",
                "TYPE_NAME": "TYPE-C",
                "FUNCTION_NAME": "FUNC-C",
            },
        ]).to_parquet(parquet_path, index=False)

        monkeypatch.setattr(
            "mes_dashboard.services.yield_alert_sql_runtime.get_spool_file_path",
            lambda namespace, query_id: str(parquet_path),
        )
        monkeypatch.setattr(
            "mes_dashboard.core.duckdb_runtime.create_heavy_query_connection",
            lambda: duckdb.connect(database=":memory:"),
        )

        result = compute_cross_filter_options(
            query_id="qid-001",
            filters={
                "departments": ["焊接_WB"],
                "lines": ["L1"],
                "packages": ["PKG-A"],
            },
        )

        assert result is not None
        assert result["lines"] == ["L1"]
        assert result["packages"] == ["PKG-A", "PKG-B"]
        assert result["types"] == ["TYPE-A"]
        assert result["functions"] == ["FUNC-A"]
