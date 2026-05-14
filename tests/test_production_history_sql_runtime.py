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
