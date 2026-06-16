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
        from mes_dashboard.services.production_history_sql_runtime import _SORT_COLUMN_MAP

        # Default frontend sort key "trackin_time" must map to TRACKINTIMESTAMP (PH-04)
        assert _SORT_COLUMN_MAP["trackin_time"] == "TRACKINTIMESTAMP"


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


# ============================================================
# Change: prod-history-first-tier-cache-filters
# extra_filters wildcard emit
# ============================================================

class TestExtraFiltersWildcardEmit:
    """_build_extra_filters wires wildcard tokens through the shared emitter."""

    def test_extra_filters_wildcard_emit(self):
        """All three wildcard fields produce LIKE ESCAPE clauses with bound params."""
        from mes_dashboard.services.production_history_service import (
            _build_extra_filters,
            validate_query_params,
        )
        params = validate_query_params({
            "pj_types": ["GA"],
            "start_date": "2026-03-01",
            "end_date": "2026-03-10",
            "mfg_orders": "MA2025*",
            "wafer_lots": ["W001*"],
            "lot_ids": ["GA*"],
        })
        sql, binds = _build_extra_filters(params)

        # Three LIKE ESCAPE clauses appear, one per wildcard column.
        assert sql.count("LIKE :") >= 3
        assert "ESCAPE '\\'" in sql
        # All three column references present.
        assert "c.MFGORDERNAME" in sql
        assert "c.FIRSTNAME" in sql
        assert "c.CONTAINERNAME" in sql
        # Bound values reflect % translation, NOT inline interpolation.
        assert any(v == "MA2025%" for v in binds.values())
        assert any(v == "W001%" for v in binds.values())
        assert any(v == "GA%" for v in binds.values())


# ============================================================
# Change: fix-matrix-distinct-count
# Matrix parent-level count must be COUNT(DISTINCT CONTAINERNAME)
# re-evaluated per grain, NOT the sum of child distinct counts.
# Option C: raw distinct-tuple rows + Python set rollup in
# _build_matrix_tree.
#   row contract: {wc, spec, eqp_id, eqp_name, month_bucket, container}
# ============================================================


def _matrix_row(wc, spec, eqp_id, eqp_name, month, container):
    """Build one distinct-tuple input row for _build_matrix_tree."""
    return {
        "wc": wc,
        "spec": spec,
        "eqp_id": eqp_id,
        "eqp_name": eqp_name,
        "month_bucket": month,
        "container": container,
    }


def _find_node(nodes, label):
    for n in nodes:
        if n["label"] == label:
            return n
    raise AssertionError(f"node {label!r} not found in {[n['label'] for n in nodes]}")


class TestMatrixDistinctCountRollup:
    """AC-1..AC-3, AC-6: _build_matrix_tree distinct-count assignment per grain."""

    def test_one_container_three_specs_workcenter_count_is_one(self):
        """FAILING-FIRST anchor (AC-1): one CONTAINERNAME across 3 SPECs under one
        workcenter → each spec count == 1 AND workcenter count == 1 (was 3)."""
        from mes_dashboard.services.production_history_sql_runtime import _build_matrix_tree

        rows = [
            _matrix_row("WC-A", "SPEC-1", "EQ1", "Eqp 1", "2026-01", "LOT-X"),
            _matrix_row("WC-A", "SPEC-2", "EQ2", "Eqp 2", "2026-01", "LOT-X"),
            _matrix_row("WC-A", "SPEC-3", "EQ3", "Eqp 3", "2026-01", "LOT-X"),
        ]
        result = _build_matrix_tree(rows)
        wc_node = _find_node(result["tree"], "WC-A")
        assert wc_node["count"] == 1
        for spec_label in ("SPEC-1", "SPEC-2", "SPEC-3"):
            spec_node = _find_node(wc_node["children"], spec_label)
            assert spec_node["count"] == 1

    def test_one_lot_two_equipment_spec_count_is_one(self):
        """AC-2: one CONTAINERNAME across 2 equipment under one spec →
        spec count == 1 (was 2); equipment leaves remain correct."""
        from mes_dashboard.services.production_history_sql_runtime import _build_matrix_tree

        rows = [
            _matrix_row("WC-A", "SPEC-1", "EQ1", "Eqp 1", "2026-01", "LOT-X"),
            _matrix_row("WC-A", "SPEC-1", "EQ2", "Eqp 2", "2026-01", "LOT-X"),
        ]
        result = _build_matrix_tree(rows)
        wc_node = _find_node(result["tree"], "WC-A")
        spec_node = _find_node(wc_node["children"], "SPEC-1")
        assert spec_node["count"] == 1
        assert wc_node["count"] == 1
        for eqp_label in ("EQ1", "EQ2"):
            eqp_node = _find_node(spec_node["children"], eqp_label)
            assert eqp_node["count"] == 1

    def test_equipment_leaf_count_unchanged(self):
        """AC-6: equipment-level leaf count and month_counts unchanged by the fix."""
        from mes_dashboard.services.production_history_sql_runtime import _build_matrix_tree

        rows = [
            _matrix_row("WC-A", "SPEC-1", "EQ1", "Eqp 1", "2026-01", "LOT-A"),
            _matrix_row("WC-A", "SPEC-1", "EQ1", "Eqp 1", "2026-01", "LOT-B"),
            _matrix_row("WC-A", "SPEC-1", "EQ1", "Eqp 1", "2026-02", "LOT-C"),
        ]
        result = _build_matrix_tree(rows)
        wc_node = _find_node(result["tree"], "WC-A")
        spec_node = _find_node(wc_node["children"], "SPEC-1")
        eqp_node = _find_node(spec_node["children"], "EQ1")
        assert eqp_node["count"] == 3
        assert eqp_node["month_counts"] == {"2026-01": 2, "2026-02": 1}

    def test_month_counts_distinct_at_every_level(self):
        """AC-3: spec/workcenter month_counts[m] = independent distinct count at
        that grain×month, not sum of children."""
        from mes_dashboard.services.production_history_sql_runtime import _build_matrix_tree

        rows = [
            # LOT-X spans two equipment within SPEC-1 in the same month
            _matrix_row("WC-A", "SPEC-1", "EQ1", "Eqp 1", "2026-01", "LOT-X"),
            _matrix_row("WC-A", "SPEC-1", "EQ2", "Eqp 2", "2026-01", "LOT-X"),
            # LOT-Y only on EQ1
            _matrix_row("WC-A", "SPEC-1", "EQ1", "Eqp 1", "2026-01", "LOT-Y"),
        ]
        result = _build_matrix_tree(rows)
        wc_node = _find_node(result["tree"], "WC-A")
        spec_node = _find_node(wc_node["children"], "SPEC-1")
        # EQ1 month_counts = 2 (LOT-X, LOT-Y); EQ2 = 1 (LOT-X)
        # spec independent distinct = {LOT-X, LOT-Y} = 2, NOT 2+1=3
        assert spec_node["month_counts"]["2026-01"] == 2
        assert wc_node["month_counts"]["2026-01"] == 2

    def test_lot_spanning_two_months_one_equipment(self):
        """AC-3: one CONTAINERNAME tracked-in across 2 months at one equipment →
        counted once per month bucket, equipment total count == 1."""
        from mes_dashboard.services.production_history_sql_runtime import _build_matrix_tree

        rows = [
            _matrix_row("WC-A", "SPEC-1", "EQ1", "Eqp 1", "2026-01", "LOT-X"),
            _matrix_row("WC-A", "SPEC-1", "EQ1", "Eqp 1", "2026-02", "LOT-X"),
        ]
        result = _build_matrix_tree(rows)
        wc_node = _find_node(result["tree"], "WC-A")
        spec_node = _find_node(wc_node["children"], "SPEC-1")
        eqp_node = _find_node(spec_node["children"], "EQ1")
        assert eqp_node["count"] == 1
        assert eqp_node["month_counts"] == {"2026-01": 1, "2026-02": 1}
        assert spec_node["count"] == 1
        assert wc_node["count"] == 1

    def test_lot_same_month_two_specs(self):
        """AC-3: one CONTAINERNAME in the same month under 2 specs → that
        month_counts entry is 1 at workcenter and 1 at each spec."""
        from mes_dashboard.services.production_history_sql_runtime import _build_matrix_tree

        rows = [
            _matrix_row("WC-A", "SPEC-1", "EQ1", "Eqp 1", "2026-01", "LOT-X"),
            _matrix_row("WC-A", "SPEC-2", "EQ2", "Eqp 2", "2026-01", "LOT-X"),
        ]
        result = _build_matrix_tree(rows)
        wc_node = _find_node(result["tree"], "WC-A")
        assert wc_node["month_counts"]["2026-01"] == 1
        for spec_label in ("SPEC-1", "SPEC-2"):
            spec_node = _find_node(wc_node["children"], spec_label)
            assert spec_node["month_counts"]["2026-01"] == 1

    def test_distinct_containers_still_additive_when_disjoint(self):
        """Guard: disjoint CONTAINERNAMEs across specs still roll up to the true
        distinct total — the fix must not under-count."""
        from mes_dashboard.services.production_history_sql_runtime import _build_matrix_tree

        rows = [
            _matrix_row("WC-A", "SPEC-1", "EQ1", "Eqp 1", "2026-01", "LOT-A"),
            _matrix_row("WC-A", "SPEC-2", "EQ2", "Eqp 2", "2026-01", "LOT-B"),
            _matrix_row("WC-A", "SPEC-3", "EQ3", "Eqp 3", "2026-01", "LOT-C"),
        ]
        result = _build_matrix_tree(rows)
        wc_node = _find_node(result["tree"], "WC-A")
        assert wc_node["count"] == 3
        assert wc_node["month_counts"]["2026-01"] == 3
        for spec_label in ("SPEC-1", "SPEC-2", "SPEC-3"):
            spec_node = _find_node(wc_node["children"], spec_label)
            assert spec_node["count"] == 1


class TestMatrixTreeNodeShape:
    """AC-5, AC-7: node-shape invariance + structural rule of data-shape §3.5."""

    def test_node_shape_unchanged(self):
        """AC-5: every node has exactly {label, level, count, month_counts,
        children}; equipment node also keeps equipment_name."""
        from mes_dashboard.services.production_history_sql_runtime import _build_matrix_tree

        rows = [
            _matrix_row("WC-A", "SPEC-1", "EQ1", "Eqp 1", "2026-01", "LOT-X"),
        ]
        result = _build_matrix_tree(rows)
        wc_node = _find_node(result["tree"], "WC-A")
        assert set(wc_node.keys()) == {"label", "level", "count", "month_counts", "children"}
        spec_node = _find_node(wc_node["children"], "SPEC-1")
        assert set(spec_node.keys()) == {"label", "level", "count", "month_counts", "children"}
        eqp_node = _find_node(spec_node["children"], "EQ1")
        assert set(eqp_node.keys()) == {
            "label", "equipment_name", "level", "count", "month_counts", "children",
        }

    def test_parent_count_equals_independent_distinct_not_child_sum(self):
        """AC-7: structural rule of data-shape §3.5 / business PH-05 — parent count
        != Σ child count when a container spans children, equals independent distinct."""
        from mes_dashboard.services.production_history_sql_runtime import _build_matrix_tree

        rows = [
            _matrix_row("WC-A", "SPEC-1", "EQ1", "Eqp 1", "2026-01", "LOT-X"),
            _matrix_row("WC-A", "SPEC-2", "EQ2", "Eqp 2", "2026-01", "LOT-X"),
        ]
        result = _build_matrix_tree(rows)
        wc_node = _find_node(result["tree"], "WC-A")
        child_sum = sum(c["count"] for c in wc_node["children"])
        assert child_sum == 2
        assert wc_node["count"] == 1
        assert wc_node["count"] != child_sum

    def test_month_columns_and_levels_preserved(self):
        """AC-5/AC-7: level values and month_columns ordering preserved."""
        from mes_dashboard.services.production_history_sql_runtime import _build_matrix_tree

        rows = [
            _matrix_row("WC-A", "SPEC-1", "EQ1", "Eqp 1", "2026-02", "LOT-A"),
            _matrix_row("WC-A", "SPEC-1", "EQ1", "Eqp 1", "2026-01", "LOT-B"),
        ]
        result = _build_matrix_tree(rows)
        assert result["month_columns"] == ["2026-01", "2026-02"]
        wc_node = _find_node(result["tree"], "WC-A")
        assert wc_node["level"] == "workcenter"
        spec_node = _find_node(wc_node["children"], "SPEC-1")
        assert spec_node["level"] == "spec"
        eqp_node = _find_node(spec_node["children"], "EQ1")
        assert eqp_node["level"] == "equipment"


class TestMatrixDualPathParity:
    """AC-4: compute_matrix_view (DuckDB) vs _pandas_matrix_view (pandas) parity."""

    def _write_spool(self, tmp_path, records):
        import pandas as pd

        df = pd.DataFrame.from_records(records)
        path = str(tmp_path / "ph_spool.parquet")
        df.to_parquet(path)
        return path

    def _records(self):
        # Minimal spool schema fields consumed by the matrix path.
        base = {
            "MFGORDERNAME": "WO1", "FIRSTNAME": "WL1", "PRODUCTLINENAME": "PKG1",
            "PJ_TYPE": "GA", "PJ_BOP": "B1", "PJ_FUNCTION": "F1",
            "TRACKOUTTIMESTAMP": "2026-01-02 00:00:00",
            "TRACKINQTY": 1, "TRACKOUTQTY": 1,
        }
        return base

    def test_duckdb_and_pandas_produce_identical_tree(self, tmp_path):
        from mes_dashboard.services.production_history_sql_runtime import (
            compute_matrix_view, _pandas_matrix_view,
        )
        base = self._records()
        records = [
            {**base, "WORKCENTERNAME": "WC-A", "SPECNAME": "SPEC-1",
             "EQUIPMENTID": "EQ1", "EQUIPMENTNAME": "Eqp 1",
             "TRACKINTIMESTAMP": "2026-01-01 08:00:00", "CONTAINERNAME": "LOT-A"},
            {**base, "WORKCENTERNAME": "WC-A", "SPECNAME": "SPEC-1",
             "EQUIPMENTID": "EQ1", "EQUIPMENTNAME": "Eqp 1",
             "TRACKINTIMESTAMP": "2026-02-01 08:00:00", "CONTAINERNAME": "LOT-B"},
            {**base, "WORKCENTERNAME": "WC-A", "SPECNAME": "SPEC-2",
             "EQUIPMENTID": "EQ2", "EQUIPMENTNAME": "Eqp 2",
             "TRACKINTIMESTAMP": "2026-01-05 08:00:00", "CONTAINERNAME": "LOT-C"},
        ]
        path = self._write_spool(tmp_path, records)
        duck = compute_matrix_view(path, {})
        pan = _pandas_matrix_view(path, {})
        assert duck == pan

    def test_dual_path_parity_with_cross_spec_container(self, tmp_path):
        from mes_dashboard.services.production_history_sql_runtime import (
            compute_matrix_view, _pandas_matrix_view,
        )
        base = self._records()
        records = [
            # LOT-X spans SPEC-1/EQ1 and SPEC-2/EQ2 — exercises rollup on both engines
            {**base, "WORKCENTERNAME": "WC-A", "SPECNAME": "SPEC-1",
             "EQUIPMENTID": "EQ1", "EQUIPMENTNAME": "Eqp 1",
             "TRACKINTIMESTAMP": "2026-01-01 08:00:00", "CONTAINERNAME": "LOT-X"},
            {**base, "WORKCENTERNAME": "WC-A", "SPECNAME": "SPEC-2",
             "EQUIPMENTID": "EQ2", "EQUIPMENTNAME": "Eqp 2",
             "TRACKINTIMESTAMP": "2026-01-03 08:00:00", "CONTAINERNAME": "LOT-X"},
            {**base, "WORKCENTERNAME": "WC-A", "SPECNAME": "SPEC-1",
             "EQUIPMENTID": "EQ1", "EQUIPMENTNAME": "Eqp 1",
             "TRACKINTIMESTAMP": "2026-01-04 08:00:00", "CONTAINERNAME": "LOT-Y"},
        ]
        path = self._write_spool(tmp_path, records)
        duck = compute_matrix_view(path, {})
        pan = _pandas_matrix_view(path, {})
        assert duck == pan
        wc_node = _find_node(duck["tree"], "WC-A")
        assert wc_node["count"] == 2  # LOT-X, LOT-Y


class TestMatrixDataBoundary:
    """AC-1..AC-3 data-boundary: single-row, empty, overlapping month buckets."""

    def test_single_row_input(self):
        from mes_dashboard.services.production_history_sql_runtime import _build_matrix_tree

        rows = [_matrix_row("WC-A", "SPEC-1", "EQ1", "Eqp 1", "2026-01", "LOT-X")]
        result = _build_matrix_tree(rows)
        wc_node = _find_node(result["tree"], "WC-A")
        spec_node = _find_node(wc_node["children"], "SPEC-1")
        eqp_node = _find_node(spec_node["children"], "EQ1")
        assert wc_node["count"] == 1
        assert spec_node["count"] == 1
        assert eqp_node["count"] == 1

    def test_empty_input(self):
        from mes_dashboard.services.production_history_sql_runtime import _build_matrix_tree

        assert _build_matrix_tree([]) == {"tree": [], "month_columns": []}

    def test_overlapping_month_buckets(self):
        """Same (wc,spec,eqp) across multiple month buckets → per-month counts
        isolated, total = distinct over all months."""
        from mes_dashboard.services.production_history_sql_runtime import _build_matrix_tree

        rows = [
            _matrix_row("WC-A", "SPEC-1", "EQ1", "Eqp 1", "2026-01", "LOT-A"),
            _matrix_row("WC-A", "SPEC-1", "EQ1", "Eqp 1", "2026-02", "LOT-A"),
            _matrix_row("WC-A", "SPEC-1", "EQ1", "Eqp 1", "2026-02", "LOT-B"),
        ]
        result = _build_matrix_tree(rows)
        wc_node = _find_node(result["tree"], "WC-A")
        spec_node = _find_node(wc_node["children"], "SPEC-1")
        eqp_node = _find_node(spec_node["children"], "EQ1")
        assert eqp_node["month_counts"] == {"2026-01": 1, "2026-02": 2}
        assert eqp_node["count"] == 2  # distinct {LOT-A, LOT-B}
        assert spec_node["count"] == 2
        assert wc_node["count"] == 2


# ============================================================
# Change: prod-history-detail-partial-merge
# AC-1: DuckDB path aggregates partial track-outs (MAX trackout_time, SUM qty, partial_count)
# AC-2: ABA interleave (different TRACKINTIMESTAMP) is NOT merged
# AC-3: strict guard falls back to raw rows when non-key columns diverge
# AC-4: pagination.total_rows = post-aggregation count
# AC-5: CSV export rows match API rows (parity)
# AC-6: partial_count field present in row schema
# PH-06 parity: DuckDB path == pandas path
# ============================================================

def _ph_base_record(overrides: dict | None = None) -> dict:
    """Build a minimal spool record for production-history detail tests."""
    base = {
        "CONTAINERNAME": "LOT-A",
        "SPECNAME": "SPEC-1",
        "EQUIPMENTID": "EQ-01",
        "TRACKINTIMESTAMP": "2026-01-01 08:00:00",
        "TRACKINQTY": 100,
        "TRACKOUTTIMESTAMP": "2026-01-01 10:00:00",
        "TRACKOUTQTY": 50,
        "MFGORDERNAME": "WO-001",
        "FIRSTNAME": "WL-001",
        "PJ_TYPE": "GA",
        "PJ_BOP": "BOP1",
        "PJ_FUNCTION": "FN1",
        "PRODUCTLINENAME": "PKG-A",
        "WORKCENTERNAME": "WC-X",
        "EQUIPMENTNAME": "EQP-NAME-01",
    }
    if overrides:
        base.update(overrides)
    return base


def _write_ph_spool(tmp_path, records: list) -> str:
    import pandas as pd
    df = pd.DataFrame.from_records(records)
    path = str(tmp_path / "ph_spool.parquet")
    df.to_parquet(path)
    return path


class TestPartialMergeAggregation:
    """DuckDB primary path (compute_detail_page) + CSV export (stream_export)
    must apply 5-tuple aggregation with strict guard.  Covers AC-1..AC-6, PH-06.
    """

    # AC-1: two partial track-outs of the same 5-tuple → ONE aggregated row
    def test_partial_merge_sum_qty_max_time(self, tmp_path):
        """AC-1: two partials collapse to one row; trackout_qty=SUM, trackout_time=MAX."""
        from mes_dashboard.services.production_history_sql_runtime import compute_detail_page

        records = [
            _ph_base_record({"TRACKOUTTIMESTAMP": "2026-01-01 10:00:00", "TRACKOUTQTY": 30}),
            _ph_base_record({"TRACKOUTTIMESTAMP": "2026-01-01 12:00:00", "TRACKOUTQTY": 70}),
        ]
        path = _write_ph_spool(tmp_path, records)
        result = compute_detail_page(path, {}, page=1, per_page=25)
        rows = result["rows"]
        assert len(rows) == 1, f"expected 1 aggregated row, got {len(rows)}"
        row = rows[0]
        assert row["trackout_qty"] == 100, f"SUM trackout_qty must be 100, got {row['trackout_qty']}"
        assert "12:00:00" in str(row["trackout_time"]), (
            f"MAX trackout_time must be 12:00:00, got {row['trackout_time']}"
        )

    # AC-1: partial_count equals group size
    def test_partial_count_equals_group_size(self, tmp_path):
        """AC-1: partial_count == number of spool rows sharing the 5-tuple key."""
        from mes_dashboard.services.production_history_sql_runtime import compute_detail_page

        records = [
            _ph_base_record({"TRACKOUTTIMESTAMP": "2026-01-01 09:00:00", "TRACKOUTQTY": 20}),
            _ph_base_record({"TRACKOUTTIMESTAMP": "2026-01-01 10:00:00", "TRACKOUTQTY": 30}),
            _ph_base_record({"TRACKOUTTIMESTAMP": "2026-01-01 11:00:00", "TRACKOUTQTY": 50}),
        ]
        path = _write_ph_spool(tmp_path, records)
        result = compute_detail_page(path, {}, page=1, per_page=25)
        rows = result["rows"]
        assert len(rows) == 1
        assert rows[0]["partial_count"] == 3, (
            f"partial_count must be 3, got {rows[0].get('partial_count')}"
        )

    # AC-2: ABA interleave — different TRACKINTIMESTAMP → two rows
    def test_aba_interleave_not_merged(self, tmp_path):
        """AC-2: same lot/spec/equip but different TRACKINTIMESTAMP → 2 rows, NOT merged."""
        from mes_dashboard.services.production_history_sql_runtime import compute_detail_page

        records = [
            _ph_base_record({
                "TRACKINTIMESTAMP": "2026-01-01 08:00:00",
                "TRACKOUTTIMESTAMP": "2026-01-01 10:00:00", "TRACKOUTQTY": 50,
            }),
            _ph_base_record({
                "TRACKINTIMESTAMP": "2026-01-02 08:00:00",
                "TRACKOUTTIMESTAMP": "2026-01-02 10:00:00", "TRACKOUTQTY": 50,
            }),
        ]
        path = _write_ph_spool(tmp_path, records)
        result = compute_detail_page(path, {}, page=1, per_page=25)
        rows = result["rows"]
        assert len(rows) == 2, f"ABA interleave must produce 2 rows, got {len(rows)}"
        for row in rows:
            assert row["partial_count"] == 1, (
                f"single-row group must have partial_count=1, got {row.get('partial_count')}"
            )

    # AC-3: strict guard — non-key column diverges → raw rows
    def test_duckdb_strict_guard_fallback_to_raw_rows(self, tmp_path):
        """AC-3: when MFGORDERNAME (non-key) diverges, emit 2 raw rows each with partial_count=1."""
        from mes_dashboard.services.production_history_sql_runtime import compute_detail_page

        records = [
            _ph_base_record({
                "MFGORDERNAME": "WO-001",
                "TRACKOUTTIMESTAMP": "2026-01-01 10:00:00", "TRACKOUTQTY": 40,
            }),
            _ph_base_record({
                "MFGORDERNAME": "WO-002",   # diverges
                "TRACKOUTTIMESTAMP": "2026-01-01 11:00:00", "TRACKOUTQTY": 60,
            }),
        ]
        path = _write_ph_spool(tmp_path, records)
        result = compute_detail_page(path, {}, page=1, per_page=25)
        rows = result["rows"]
        assert len(rows) == 2, (
            f"strict guard must emit 2 raw rows when non-key diverges, got {len(rows)}"
        )
        for row in rows:
            assert row["partial_count"] == 1, (
                f"strict-guard raw rows must have partial_count=1, got {row.get('partial_count')}"
            )

    # AC-4: pagination.total_rows = post-aggregation row count
    def test_pagination_total_rows_is_post_aggregation_count(self, tmp_path):
        """AC-4: total_rows must equal the number of aggregated rows, not raw spool rows."""
        from mes_dashboard.services.production_history_sql_runtime import compute_detail_page

        # 3 spool rows in one 5-tuple group → 1 aggregated row → total_rows should be 1
        records = [
            _ph_base_record({"TRACKOUTTIMESTAMP": "2026-01-01 09:00:00", "TRACKOUTQTY": 20}),
            _ph_base_record({"TRACKOUTTIMESTAMP": "2026-01-01 10:00:00", "TRACKOUTQTY": 30}),
            _ph_base_record({"TRACKOUTTIMESTAMP": "2026-01-01 11:00:00", "TRACKOUTQTY": 50}),
        ]
        path = _write_ph_spool(tmp_path, records)
        result = compute_detail_page(path, {}, page=1, per_page=25)
        assert result["pagination"]["total_rows"] == 1, (
            f"total_rows must be 1 (post-agg), got {result['pagination']['total_rows']}"
        )

    # AC-6: partial_count field present in row dict with integer type
    def test_detail_row_includes_partial_count_field(self, tmp_path):
        """AC-6: every row in compute_detail_page result must have 'partial_count' as an integer >=1."""
        from mes_dashboard.services.production_history_sql_runtime import compute_detail_page

        records = [_ph_base_record()]
        path = _write_ph_spool(tmp_path, records)
        result = compute_detail_page(path, {}, page=1, per_page=25)
        rows = result["rows"]
        assert rows, "expected at least one row in result"
        row = rows[0]
        assert "partial_count" in row, f"'partial_count' field missing from row: {list(row.keys())}"
        assert isinstance(row["partial_count"], int), (
            f"partial_count must be int, got {type(row['partial_count'])}"
        )
        assert row["partial_count"] >= 1, f"partial_count must be >= 1, got {row['partial_count']}"

    # AC-5: CSV rows match API rows in count and partial_count
    def test_csv_rows_match_api_rows_aggregated(self, tmp_path):
        """AC-5: stream_export emits the same number of rows as compute_detail_page
        (both apply the same aggregation logic)."""
        import csv
        import io
        from mes_dashboard.services.production_history_sql_runtime import (
            compute_detail_page, stream_export,
        )

        # 2 raw rows merging into 1 aggregated row
        records = [
            _ph_base_record({"TRACKOUTTIMESTAMP": "2026-01-01 10:00:00", "TRACKOUTQTY": 30}),
            _ph_base_record({"TRACKOUTTIMESTAMP": "2026-01-01 12:00:00", "TRACKOUTQTY": 70}),
        ]
        path = _write_ph_spool(tmp_path, records)

        api_result = compute_detail_page(path, {}, page=1, per_page=25)
        api_rows = api_result["rows"]

        # Collect CSV output (skip BOM + header)
        csv_text = "".join(stream_export(path, {}))
        csv_text = csv_text.lstrip('﻿')
        reader = csv.DictReader(io.StringIO(csv_text))
        csv_rows = list(reader)

        assert len(csv_rows) == len(api_rows), (
            f"CSV row count ({len(csv_rows)}) must equal API row count ({len(api_rows)})"
        )

    # AC-5: CSV PartialCount matches API partial_count per row
    def test_csv_partial_count_matches_api(self, tmp_path):
        """AC-5: PartialCount column in CSV must match partial_count in API response."""
        import csv
        import io
        from mes_dashboard.services.production_history_sql_runtime import (
            compute_detail_page, stream_export,
        )

        records = [
            _ph_base_record({"TRACKOUTTIMESTAMP": "2026-01-01 10:00:00", "TRACKOUTQTY": 30}),
            _ph_base_record({"TRACKOUTTIMESTAMP": "2026-01-01 12:00:00", "TRACKOUTQTY": 70}),
        ]
        path = _write_ph_spool(tmp_path, records)

        api_result = compute_detail_page(path, {}, page=1, per_page=25)
        api_partial_count = api_result["rows"][0]["partial_count"]

        csv_text = "".join(stream_export(path, {}))
        csv_text = csv_text.lstrip('﻿')
        reader = csv.DictReader(io.StringIO(csv_text))
        csv_rows = list(reader)
        assert csv_rows, "CSV must have at least one data row"
        csv_partial_count = int(csv_rows[0]["PartialCount"])
        assert csv_partial_count == api_partial_count, (
            f"CSV PartialCount ({csv_partial_count}) != API partial_count ({api_partial_count})"
        )

    # PH-06 parity: DuckDB SQL path == pandas fallback path
    def test_duckdb_pandas_parity_aggregation_output(self, tmp_path):
        """PH-06 parity: compute_detail_page (DuckDB) and _pandas_detail_page (pandas)
        must produce identical row count, per-row field values, and partial_count."""
        from mes_dashboard.services.production_history_sql_runtime import (
            compute_detail_page, _pandas_detail_page,
        )

        # Mix: one group with 2 consistent partials (will merge), one group with divergent non-key (strict guard)
        records = [
            # Group A — consistent (will merge)
            _ph_base_record({
                "CONTAINERNAME": "LOT-A",
                "TRACKINTIMESTAMP": "2026-01-01 08:00:00",
                "TRACKOUTTIMESTAMP": "2026-01-01 10:00:00", "TRACKOUTQTY": 30,
            }),
            _ph_base_record({
                "CONTAINERNAME": "LOT-A",
                "TRACKINTIMESTAMP": "2026-01-01 08:00:00",
                "TRACKOUTTIMESTAMP": "2026-01-01 12:00:00", "TRACKOUTQTY": 70,
            }),
            # Group B — divergent MFGORDERNAME (strict guard)
            _ph_base_record({
                "CONTAINERNAME": "LOT-B", "MFGORDERNAME": "WO-X",
                "TRACKINTIMESTAMP": "2026-01-02 08:00:00",
                "TRACKOUTTIMESTAMP": "2026-01-02 10:00:00", "TRACKOUTQTY": 40,
            }),
            _ph_base_record({
                "CONTAINERNAME": "LOT-B", "MFGORDERNAME": "WO-Y",
                "TRACKINTIMESTAMP": "2026-01-02 08:00:00",
                "TRACKOUTTIMESTAMP": "2026-01-02 11:00:00", "TRACKOUTQTY": 60,
            }),
        ]
        path = _write_ph_spool(tmp_path, records)

        duck_result = compute_detail_page(path, {}, page=1, per_page=25)
        pandas_result = _pandas_detail_page(path, {}, page=1, per_page=25)

        duck_rows = duck_result["rows"]
        pan_rows = pandas_result["rows"]

        assert len(duck_rows) == len(pan_rows), (
            f"DuckDB row count ({len(duck_rows)}) != pandas row count ({len(pan_rows)})"
        )
        # Compare partial_count per row (sort by lot_id for determinism)
        duck_counts = sorted((r["lot_id"], r["partial_count"]) for r in duck_rows)
        pan_counts = sorted((r["lot_id"], r["partial_count"]) for r in pan_rows)
        assert duck_counts == pan_counts, (
            f"partial_count mismatch:\n  DuckDB: {duck_counts}\n  pandas: {pan_counts}"
        )
        # total_rows must also match
        assert duck_result["pagination"]["total_rows"] == pandas_result["pagination"]["total_rows"], (
            "pagination.total_rows mismatch between DuckDB and pandas paths"
        )

    # Regression: real-MES partial trackouts share TRACKINTIMESTAMP but have
    # DIFFERENT TRACKINQTY (MES records qty REMAINING at each partial's start,
    # not the original load).  Must still merge under 4-tuple key.
    # Evidence: lot GA26041607-A00-005 on equipment GWBA-0146, TrackIn 2026-04-30
    # 00:09:29 had TrackInQty=99424 (first partial) and 26624 (second partial);
    # 5-tuple key wrongly emitted two rows.  4-tuple must produce one row with
    # TRACKINQTY=MAX (= 99424 original load), TRACKOUTQTY=SUM, partial_count=2.
    def test_partial_merge_same_trackin_time_different_trackin_qty(self, tmp_path):
        """PH-06 4-tuple: TrackInQty differs across partials (MES records remaining qty).
        Must merge into one row with TrackInQty=MAX (original load)."""
        from mes_dashboard.services.production_history_sql_runtime import compute_detail_page

        records = [
            # First partial: starts with 99424 on equipment, 72800 leaves at 06:54
            _ph_base_record({
                "TRACKINTIMESTAMP": "2026-04-30 00:09:29",
                "TRACKOUTTIMESTAMP": "2026-04-30 06:54:26",
                "TRACKINQTY": 99424, "TRACKOUTQTY": 72800,
            }),
            # Second partial: starts with 26624 remaining (= 99424 - 72800), 26606 leaves at 10:26
            _ph_base_record({
                "TRACKINTIMESTAMP": "2026-04-30 00:09:29",
                "TRACKOUTTIMESTAMP": "2026-04-30 10:26:11",
                "TRACKINQTY": 26624, "TRACKOUTQTY": 26606,
            }),
        ]
        path = _write_ph_spool(tmp_path, records)
        result = compute_detail_page(path, {}, page=1, per_page=25)
        rows = result["rows"]
        assert len(rows) == 1, (
            f"expected 1 merged row, got {len(rows)} (TRACKINQTY must NOT be a key)"
        )
        row = rows[0]
        assert row["partial_count"] == 2, f"partial_count must be 2, got {row['partial_count']}"
        assert row["trackin_qty"] == 99424, (
            f"trackin_qty must be MAX=99424 (original load), got {row['trackin_qty']}"
        )
        assert row["trackout_qty"] == 99406, (
            f"trackout_qty must be SUM(72800+26606)=99406, got {row['trackout_qty']}"
        )
        assert "10:26:11" in str(row["trackout_time"]), (
            f"trackout_time must be MAX=10:26:11, got {row['trackout_time']}"
        )

    # Regression: raw-branch WHERE must compose with user filter via AND, not WHERE.
    # The raw CTE already opens `WHERE (key-tuple) IN (...)`; a second `WHERE` is
    # a Parser Error.  This failure mode hit production on 2026-05-15 because all
    # prior unit tests used `{}` filter, leaving `where_for_raw=""` and never
    # exercising the concat path.  Any non-empty filter must succeed.
    def test_compute_detail_page_succeeds_with_non_empty_filter(self, tmp_path):
        """Regression: filter_params must not cause `... WHERE (...) IN (...) WHERE ...`
        Parser Error.  See logs/error.log 2026-05-15 16:32:32."""
        from mes_dashboard.services.production_history_sql_runtime import compute_detail_page

        records = [
            _ph_base_record({"TRACKOUTTIMESTAMP": "2026-01-01 10:00:00", "TRACKOUTQTY": 30}),
            _ph_base_record({"TRACKOUTTIMESTAMP": "2026-01-01 12:00:00", "TRACKOUTQTY": 70}),
        ]
        path = _write_ph_spool(tmp_path, records)
        # `lot_ids` triggers _build_filter_where to emit a `WHERE ...` clause.
        # Without the AND-prefix fix, this raises duckdb.ParserException.
        result = compute_detail_page(path, {"lot_ids": ["LOT-A"]}, page=1, per_page=25)
        assert isinstance(result["rows"], list)
        assert result["pagination"]["total_rows"] >= 0  # must not crash
