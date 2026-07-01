# -*- coding: utf-8 -*-
"""Unit tests for yield_alert_sql_runtime.py — DuckDB view computation helpers."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import duckdb
import pandas as pd
from unittest.mock import MagicMock

from mes_dashboard.services.yield_alert_sql_runtime import (
    _qid,
    _sql_str_literal,
    _attach_spool_view,
    _query_filter_options,
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


def _make_cross_filter_fixture(tmp_path):
    """Shared fixture: 3 rows across 2 DEPARTMENT_GROUP/DEPARTMENT_NAME buckets.

    DEPARTMENT_NAME is intentionally finer-grained than DEPARTMENT_GROUP (two raw
    names collapse into the same "焊接_WB" group) to exercise the raw-vs-normalized
    column distinction (YA-10 / Pitfall #1).
    """
    parquet_path = tmp_path / "yield-alert.parquet"
    pd.DataFrame([
        {
            "DEPARTMENT_GROUP": "焊接_WB",
            "DEPARTMENT_NAME": "焊接_WB_1線",
            "LINE_NAME": "L1",
            "PACKAGE_NAME": "PKG-A",
            "TYPE_NAME": "TYPE-A",
            "FUNCTION_NAME": "FUNC-A",
        },
        {
            "DEPARTMENT_GROUP": "焊接_WB",
            "DEPARTMENT_NAME": "焊接_WB_2線",
            "LINE_NAME": "L1",
            "PACKAGE_NAME": "PKG-B",
            "TYPE_NAME": "TYPE-B",
            "FUNCTION_NAME": "FUNC-B",
        },
        {
            "DEPARTMENT_GROUP": "切割",
            "DEPARTMENT_NAME": "切割_A線",
            "LINE_NAME": "L2",
            "PACKAGE_NAME": "PKG-C",
            "TYPE_NAME": "TYPE-C",
            "FUNCTION_NAME": "FUNC-C",
        },
    ]).to_parquet(parquet_path, index=False)
    return parquet_path


class TestCrossFilterOptions:
    def test_compute_cross_filter_options_applies_other_dimension_filters(self, tmp_path, monkeypatch):
        parquet_path = _make_cross_filter_fixture(tmp_path)

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

    def test_compute_cross_filter_options_includes_departments_dimension(self, tmp_path, monkeypatch):
        """AC-5: compute_cross_filter_options() must emit a `workcenter_groups` key
        derived from DEPARTMENT_NAME, alongside lines/packages/types/functions."""
        parquet_path = _make_cross_filter_fixture(tmp_path)

        monkeypatch.setattr(
            "mes_dashboard.services.yield_alert_sql_runtime.get_spool_file_path",
            lambda namespace, query_id: str(parquet_path),
        )
        monkeypatch.setattr(
            "mes_dashboard.core.duckdb_runtime.create_heavy_query_connection",
            lambda: duckdb.connect(database=":memory:"),
        )

        result = compute_cross_filter_options(query_id="qid-001", filters={})

        assert result is not None
        assert "workcenter_groups" in result
        assert result["workcenter_groups"] == ["切割_A線", "焊接_WB_1線", "焊接_WB_2線"]

    def test_departments_use_raw_department_name_not_department_group(self, tmp_path, monkeypatch):
        """Pitfall #1: workcenter_groups values must be raw DEPARTMENT_NAME (finer-
        grained), not the normalized DEPARTMENT_GROUP. Proven because two distinct
        DEPARTMENT_NAME values ("焊接_WB_1線"/"焊接_WB_2線") share one DEPARTMENT_GROUP
        ("焊接_WB") in the fixture — if the code read DEPARTMENT_GROUP instead, the
        result would collapse to a single "焊接_WB" entry."""
        parquet_path = _make_cross_filter_fixture(tmp_path)

        monkeypatch.setattr(
            "mes_dashboard.services.yield_alert_sql_runtime.get_spool_file_path",
            lambda namespace, query_id: str(parquet_path),
        )
        monkeypatch.setattr(
            "mes_dashboard.core.duckdb_runtime.create_heavy_query_connection",
            lambda: duckdb.connect(database=":memory:"),
        )

        result = compute_cross_filter_options(query_id="qid-001", filters={})

        assert result is not None
        assert "焊接_WB" not in result["workcenter_groups"], (
            "workcenter_groups must not contain the normalized DEPARTMENT_GROUP value"
        )
        assert set(result["workcenter_groups"]) == {"焊接_WB_1線", "焊接_WB_2線", "切割_A線"}

    def test_selecting_department_narrows_lines_packages_types_functions(self, tmp_path, monkeypatch):
        """AC-6: selecting a `departments` value narrows lines/packages/types/functions
        (existing narrowing direction, still exercised with DEPARTMENT_NAME present)."""
        parquet_path = _make_cross_filter_fixture(tmp_path)

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
            filters={"departments": ["切割"]},
        )

        assert result is not None
        assert result["lines"] == ["L2"]
        assert result["packages"] == ["PKG-C"]
        assert result["types"] == ["TYPE-C"]
        assert result["functions"] == ["FUNC-C"]

    def test_selecting_line_narrows_departments(self, tmp_path, monkeypatch):
        """AC-6: selecting a `lines` value narrows workcenter_groups (the new
        DEPARTMENT_NAME dimension) — cross-filter narrowing tested in the reverse
        direction from the pre-existing case above."""
        parquet_path = _make_cross_filter_fixture(tmp_path)

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
            filters={"lines": ["L1"]},
        )

        assert result is not None
        assert result["workcenter_groups"] == ["焊接_WB_1線", "焊接_WB_2線"]

    def test_workcenter_groups_change_with_process_type_query_id(self, tmp_path, monkeypatch):
        """AC-6: workcenter_groups is scoped to the current query_id's spool — a
        different query_id (e.g. a different process_type) with a different spool
        produces different workcenter_groups."""
        parquet_a = tmp_path / "qid-a.parquet"
        pd.DataFrame([
            {"DEPARTMENT_GROUP": "焊接_WB", "DEPARTMENT_NAME": "焊接_WB_1線",
             "LINE_NAME": "L1", "PACKAGE_NAME": "PKG-A", "TYPE_NAME": "TYPE-A", "FUNCTION_NAME": "FUNC-A"},
        ]).to_parquet(parquet_a, index=False)

        parquet_b = tmp_path / "qid-b.parquet"
        pd.DataFrame([
            {"DEPARTMENT_GROUP": "重工", "DEPARTMENT_NAME": "重工_RW線",
             "LINE_NAME": "L9", "PACKAGE_NAME": "PKG-Z", "TYPE_NAME": "TYPE-Z", "FUNCTION_NAME": "FUNC-Z"},
        ]).to_parquet(parquet_b, index=False)

        spool_paths = {"qid-a": str(parquet_a), "qid-b": str(parquet_b)}
        monkeypatch.setattr(
            "mes_dashboard.services.yield_alert_sql_runtime.get_spool_file_path",
            lambda namespace, query_id: spool_paths[query_id],
        )
        monkeypatch.setattr(
            "mes_dashboard.core.duckdb_runtime.create_heavy_query_connection",
            lambda: duckdb.connect(database=":memory:"),
        )

        result_a = compute_cross_filter_options(query_id="qid-a", filters={})
        result_b = compute_cross_filter_options(query_id="qid-b", filters={})

        assert result_a is not None and result_b is not None
        assert result_a["workcenter_groups"] == ["焊接_WB_1線"]
        assert result_b["workcenter_groups"] == ["重工_RW線"]
        assert result_a["workcenter_groups"] != result_b["workcenter_groups"]


class TestQueryFilterOptions:
    def test_query_filter_options_returns_departments_from_spool_distinct(self, tmp_path, monkeypatch):
        """AC-5: _query_filter_options() must emit `workcenter_groups` computed as
        SELECT DISTINCT CAST(DEPARTMENT_NAME AS VARCHAR), sorted, exclude-set applied,
        same convention as lines/packages/types/functions."""
        parquet_path = tmp_path / "yield-alert.parquet"
        pd.DataFrame([
            {
                "DEPARTMENT_NAME": "焊接_WB_1線", "LINE_NAME": "L1", "PACKAGE_NAME": "PKG-A",
                "TYPE_NAME": "TYPE-A", "FUNCTION_NAME": "FUNC-A", "PROCESS_CATEGORY": "PC-1",
            },
            {
                "DEPARTMENT_NAME": "切割_A線", "LINE_NAME": "L2", "PACKAGE_NAME": "PKG-B",
                "TYPE_NAME": "TYPE-B", "FUNCTION_NAME": "FUNC-B", "PROCESS_CATEGORY": "PC-2",
            },
            {
                "DEPARTMENT_NAME": "(NA)", "LINE_NAME": "L3", "PACKAGE_NAME": "PKG-C",
                "TYPE_NAME": "TYPE-C", "FUNCTION_NAME": "FUNC-C", "PROCESS_CATEGORY": "OTHER",
            },
        ]).to_parquet(parquet_path, index=False)

        conn = duckdb.connect(database=":memory:")
        _attach_spool_view(conn, str(parquet_path))

        options = _query_filter_options(conn)

        assert "workcenter_groups" in options
        assert options["workcenter_groups"] == ["切割_A線", "焊接_WB_1線"]
        assert "(NA)" not in options["workcenter_groups"], (
            "(NA) sentinel must be excluded from workcenter_groups per the shared exclude-set"
        )

    def test_query_filter_options_empty_spool_returns_empty_workcenter_groups(self, tmp_path):
        """AC-7 / YA-12: an empty spool (e.g. a new process_type with zero matching
        rows) must yield workcenter_groups == [] — a valid empty result, not an error."""
        parquet_path = tmp_path / "empty-yield-alert.parquet"
        pd.DataFrame(columns=[
            "DEPARTMENT_NAME", "LINE_NAME", "PACKAGE_NAME", "TYPE_NAME", "FUNCTION_NAME", "PROCESS_CATEGORY",
        ]).to_parquet(parquet_path, index=False)

        conn = duckdb.connect(database=":memory:")
        _attach_spool_view(conn, str(parquet_path))

        options = _query_filter_options(conn)

        assert options["workcenter_groups"] == []
