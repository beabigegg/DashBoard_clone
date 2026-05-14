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


# ============================================================
# Change: prod-history-detail-raw-rows
# Row-grain shift: raw LOTWIPHISTORY partial rows (no GROUP BY)
# AC-1: main_query.sql projects raw columns incl. PJ_FUNCTION
# AC-2: spool schema uses raw column names
# AC-5: CSV export emits raw per-partial rows
# ============================================================

class TestMainQueryRowGrain:
    """AC-1: main_query.sql must NOT use GROUP BY and must project raw columns."""

    def _load_main_sql(self) -> str:
        from mes_dashboard.sql import SQLLoader
        return SQLLoader.load("production_history/main_query")

    @staticmethod
    def _strip_sql_comments(sql: str) -> str:
        """Drop ``--`` line comments so identifier/keyword scans ignore commentary."""
        lines = []
        for line in sql.splitlines():
            stripped = line.split("--", 1)[0]
            lines.append(stripped)
        return "\n".join(lines)

    def test_main_query_has_no_group_by(self):
        sql_no_comments = self._strip_sql_comments(self._load_main_sql())
        # Lower-case comparison to ignore any future formatting change
        assert "group by" not in sql_no_comments.lower(), (
            "main_query.sql must produce raw rows — GROUP BY removed by change "
            "prod-history-detail-raw-rows"
        )

    def test_main_query_projects_pj_function(self):
        sql = self._load_main_sql()
        assert "PJ_FUNCTION" in sql, "PJ_FUNCTION must be in projection (PH-03)"

    def test_main_query_projects_raw_columns(self):
        sql = self._load_main_sql()
        for col in (
            "TRACKINTIMESTAMP",
            "TRACKOUTTIMESTAMP",
            "TRACKINQTY",
            "TRACKOUTQTY",
        ):
            assert col in sql, f"raw column {col!r} missing from main_query.sql"

    def test_main_query_drops_aggregate_aliases(self):
        sql = self._load_main_sql()
        for alias in ("TRACKIN_TS", "TRACKOUT_TS", "TRACKIN_QTY", "TRACKOUT_QTY"):
            assert alias not in sql, (
                f"aggregate alias {alias!r} must be removed from main_query.sql"
            )

    def test_main_query_projects_raw_container_columns(self):
        """Container columns are projected without aliases now."""
        sql = self._load_main_sql()
        for col in (
            "c.MFGORDERNAME",
            "c.FIRSTNAME",
            "c.PRODUCTLINENAME",
        ):
            assert col in sql, f"{col} must be in projection (raw, no alias)"

    def test_count_query_has_no_group_by(self):
        """AC-1 corollary: count_query.sql also matches raw row grain."""
        from mes_dashboard.sql import SQLLoader
        sql = self._strip_sql_comments(SQLLoader.load("production_history/count_query"))
        assert "group by" not in sql.lower()


class TestExportColumns:
    """AC-5: stream_export emits raw columns incl. PJ_FUNCTION."""

    def _export_columns(self):
        import inspect
        from mes_dashboard.services import production_history_sql_runtime as mod

        src = inspect.getsource(mod.stream_export)
        return src

    def test_export_uses_raw_column_names(self):
        src = self._export_columns()
        for col in (
            "TRACKINTIMESTAMP",
            "TRACKOUTTIMESTAMP",
            "TRACKINQTY",
            "TRACKOUTQTY",
            "MFGORDERNAME",
            "FIRSTNAME",
            "PRODUCTLINENAME",
        ):
            assert col in src, f"stream_export must use raw column {col!r}"

    def test_export_emits_pj_function_column(self):
        src = self._export_columns()
        assert "PJ_FUNCTION" in src
        assert '"Function"' in src

    def test_export_drops_aggregate_aliases(self):
        src = self._export_columns()
        for alias in ("TRACKIN_TS", "TRACKOUT_TS", "TRACKIN_QTY", "TRACKOUT_QTY"):
            assert alias not in src, (
                f"aggregate alias {alias!r} must be removed from stream_export"
            )


class TestDetailPagePjFunction:
    """AC-1 / AC-4: compute_detail_page returns pj_function and sorts by TRACKINTIMESTAMP ASC."""

    def test_detail_page_select_includes_pj_function(self):
        import inspect
        from mes_dashboard.services import production_history_sql_runtime as mod

        src = inspect.getsource(mod.compute_detail_page)
        assert "PJ_FUNCTION" in src and "pj_function" in src

    def test_detail_page_orders_by_trackin_ascending(self):
        import inspect
        from mes_dashboard.services import production_history_sql_runtime as mod

        src = inspect.getsource(mod.compute_detail_page)
        assert "ORDER BY TRACKINTIMESTAMP ASC" in src, (
            "Detail rows must sort by TRACKINTIMESTAMP ASC (PH-04)"
        )


class TestFilterWhereMonth:
    """_build_filter_where: month filter must use raw TRACKINTIMESTAMP."""

    def test_month_filter_uses_raw_column(self):
        from mes_dashboard.services.production_history_sql_runtime import _build_filter_where

        where, params = _build_filter_where({"month": "2025-01"})
        assert "TRACKINTIMESTAMP" in where
        assert "TRACKIN_TS" not in where
        assert params == ["2025-01"]

    def test_supplementary_filters_use_raw_columns(self):
        """work_orders → MFGORDERNAME; packages → PRODUCTLINENAME."""
        from mes_dashboard.services.production_history_sql_runtime import _build_filter_where

        where, params = _build_filter_where(
            {"work_orders": ["WO1"], "packages": ["PKG1"]}
        )
        assert "MFGORDERNAME" in where
        assert "PRODUCTLINENAME" in where
        assert "WORK_ORDER" not in where
        assert "PACKAGE_NAME" not in where
