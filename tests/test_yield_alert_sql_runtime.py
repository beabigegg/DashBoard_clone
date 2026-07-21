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
    _query_summary,
    _query_alerts,
    _build_reason_exclusion_sql,
    _build_dimension_filter_sql,
    _build_alerts_filtered_cte,
    _TX_EXTRA_COLS,
    compute_cross_filter_options,
    try_compute_view_from_spool,
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

    def test_selecting_one_workcenter_does_not_hide_other_groups_own_stations(self, tmp_path, monkeypatch):
        """Regression: selecting one 站別群組 (workcenter) value must NOT narrow the
        workcenter_groups dropdown's OWN option list down to only its own group's
        siblings, or the user could never add a station from a different group to
        the same multi-select — it would appear to "vanish" the moment one is picked.

        _common_filters() derives `departments` FROM the current `workcenter_groups`
        selection (expand_workcenter_groups_to_departments()), so `departments` must be
        excluded from workcenter_groups' own other_filter_keys in dim_specs — including
        it would self-narrow the dimension by its own selection under a different key.
        """
        parquet_path = _make_cross_filter_fixture(tmp_path)

        monkeypatch.setattr(
            "mes_dashboard.services.yield_alert_sql_runtime.get_spool_file_path",
            lambda namespace, query_id: str(parquet_path),
        )
        monkeypatch.setattr(
            "mes_dashboard.core.duckdb_runtime.create_heavy_query_connection",
            lambda: duckdb.connect(database=":memory:"),
        )

        # Simulate what _common_filters() builds after the user selects ONE raw
        # DEPARTMENT_NAME station belonging to the "焊接_WB" group.
        result = compute_cross_filter_options(
            query_id="qid-001",
            filters={
                "workcenter_groups": ["焊接_WB_1線"],
                "departments": ["焊接_WB"],
            },
        )

        assert result is not None
        assert set(result["workcenter_groups"]) == {"焊接_WB_1線", "焊接_WB_2線", "切割_A線"}, (
            "selecting one station must not hide a different group's station from "
            "the same multi-select's own dropdown"
        )

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


# ── yield-alert-kpi-csv-parity (bug-fix-engineer reproduction, IP-1) ──────────
#
# Bug: `_query_summary()` aggregates the WHOLE dept/proc-filtered scope (no
# `SCRAP_QTY <> 0` filter, no risk_threshold/min_scrap_qty exclusion), while
# `_query_alerts()` restricts to the "alert-candidate" set. The two numbers
# diverge and cannot be reconciled by users comparing KPI cards to the CSV
# export. design.md Decisions 1+2 require the fix to reuse `_query_alerts`'s
# `alerts_filtered` CTE chain and dedup `transaction_qty` over the
# non-REASON_CODE `tx_extra_cols` (+ bucketed DATE_BUCKET) dimension.
#
# Fixture layout (single parquet, 4 raw rows):
#   Group A (WO-1): 2 REASON_CODE rows sharing one (date, workorder, dept,
#     proc, line, package, type, function, operation) key —
#       R1: TRANSACTION_QTY=600, SCRAP_QTY=10
#       R2: TRANSACTION_QTY=400, SCRAP_QTY=5
#     tx_lookup dedup key sums BOTH raw rows -> transaction_qty = 1000 for the
#     group; alert_groups (grouped WITH REASON_CODE) produces 2 rows, each
#     joined to the SAME transaction_qty=1000 — a naive SUM over those 2 rows
#     double-counts to 2000. Both R1/R2 pass the alert-candidate predicate
#     under risk_threshold=98.0/min_scrap_qty=2.0 (scrap_qty 10 and 5 are both
#     >= min_scrap_qty, so neither is excluded), so both rows appear in
#     alerts_filtered — this is the exact trap the fix's DISTINCT-based dedup
#     (design.md Decision 2) must avoid.
#   Group B (WO-2): 1 row, TRANSACTION_QTY=2000, SCRAP_QTY=1. yield_pct =
#     (1 - 1/2000)*100 = 99.95 >= risk_threshold(98.0) AND scrap_qty(1) <
#     min_scrap_qty(2.0) -> excluded by the alert-candidate predicate.
#   Group C (WO-3): 1 row, TRANSACTION_QTY=500, SCRAP_QTY=0 -> excluded
#     directly by `SCRAP_QTY <> 0`.
#
# Expected alert-candidate-scope summary: transaction_qty=1000 (Group A only,
# deduped once), scrap_qty=15 (10+5, Group A only). Current (buggy) whole-scope
# summary returns transaction_qty=3500 (1000+2000+500) and scrap_qty=16
# (10+5+1+0) — proving the divergence.

_RISK_THRESHOLD = 98.0
_MIN_SCRAP_QTY = 2.0


def _make_kpi_csv_parity_fixture(tmp_path):
    """Real DuckDB parquet fixture reproducing the KPI/CSV scope divergence and
    the multi-reason-code double-count trap (see module comment above)."""
    parquet_path = tmp_path / "yield-alert-kpi-parity.parquet"
    common = {
        "DEPARTMENT_NAME": "焊接_WB_1線",
        "DEPARTMENT_GROUP": "焊接_WB",
        "PROCESS_CATEGORY": "PC1",
        "LINE_NAME": "L1",
        "PACKAGE_NAME": "PKG1",
        "TYPE_NAME": "TY1",
        "FUNCTION_NAME": "FN1",
        "OPERATION_TEXT": "OP1",
        "DATE_BUCKET": "2026-03-01",
    }
    rows = [
        # Group A — WO-1, two reason codes sharing one tx_extra_cols group.
        {**common, "WORKORDER": "WO-1", "REASON_CODE": "R1", "REASON_NAME": "Reason1",
         "TRANSACTION_QTY": 600.0, "SCRAP_QTY": 10.0},
        {**common, "WORKORDER": "WO-1", "REASON_CODE": "R2", "REASON_NAME": "Reason2",
         "TRANSACTION_QTY": 400.0, "SCRAP_QTY": 5.0},
        # Group B — WO-2, excluded by risk_threshold/min_scrap_qty (high yield, tiny scrap).
        {**common, "WORKORDER": "WO-2", "REASON_CODE": "R3", "REASON_NAME": "Reason3",
         "TRANSACTION_QTY": 2000.0, "SCRAP_QTY": 1.0},
        # Group C — WO-3, excluded directly by SCRAP_QTY <> 0.
        {**common, "WORKORDER": "WO-3", "REASON_CODE": "R4", "REASON_NAME": "Reason4",
         "TRANSACTION_QTY": 500.0, "SCRAP_QTY": 0.0},
    ]
    pd.DataFrame(rows).to_parquet(parquet_path, index=False)
    return parquet_path


class TestQuerySummaryAlertScopeParity:
    """IP-1: failing tests proving `_query_summary()` does not yet apply the
    alert-candidate predicate/tx-dedup that `_query_alerts()` applies.

    These tests call `_query_summary()` with the NEW expected keyword
    signature (`risk_threshold`, `min_scrap_qty`) per design.md Decisions 1+2.
    Current `_query_summary()` does not accept these kwargs, so these tests
    are expected to fail with a TypeError until backend-engineer implements
    IP-3/IP-4 (see implementation-plan.md). This is intentional: it pins the
    exact target signature and numeric expectations for the fix.
    """

    def _build_alert_scope_kwargs(self, tmp_path):
        parquet_path = _make_kpi_csv_parity_fixture(tmp_path)
        conn = duckdb.connect(database=":memory:")
        _attach_spool_view(conn, str(parquet_path))

        reason_excl_sql, reason_excl_params = _build_reason_exclusion_sql(set())
        full_where, full_params = _build_dimension_filter_sql({}, dept_proc_only=False)
        return conn, full_where, full_params, reason_excl_sql, reason_excl_params

    def test_transaction_qty_matches_tx_extra_cols_dedup_sum_of_alert_candidates(self, tmp_path):
        """AC-1: KPI transaction_qty must equal the tx_extra_cols-deduped sum of
        alert-candidate rows (Group A only, summed ONCE = 1000), not the naive
        double-counted 2000, and not the whole-scope 3500."""
        conn, full_where, full_params, reason_excl_sql, reason_excl_params = (
            self._build_alert_scope_kwargs(tmp_path)
        )

        summary = _query_summary(
            conn,
            dept_proc_where=full_where,
            dept_proc_params=full_params,
            reason_excl_sql=reason_excl_sql,
            reason_excl_params=reason_excl_params,
            risk_threshold=_RISK_THRESHOLD,
            min_scrap_qty=_MIN_SCRAP_QTY,
        )

        assert summary["transaction_qty"] == 1000.0, (
            f"expected tx_extra_cols-deduped alert-candidate sum 1000.0, got "
            f"{summary['transaction_qty']} (2000.0 would indicate the naive "
            f"reason-code double-count trap; 3500.0 would indicate the old "
            f"whole-scope bug)"
        )

    def test_scrap_qty_matches_sum_of_alert_candidate_rows(self, tmp_path):
        """AC-2: KPI scrap_qty must equal the plain sum of alert-candidate rows
        (Group A: 10 + 5 = 15), excluding Group B's 1 and Group C's 0."""
        conn, full_where, full_params, reason_excl_sql, reason_excl_params = (
            self._build_alert_scope_kwargs(tmp_path)
        )

        summary = _query_summary(
            conn,
            dept_proc_where=full_where,
            dept_proc_params=full_params,
            reason_excl_sql=reason_excl_sql,
            reason_excl_params=reason_excl_params,
            risk_threshold=_RISK_THRESHOLD,
            min_scrap_qty=_MIN_SCRAP_QTY,
        )

        assert summary["scrap_qty"] == 15.0, (
            f"expected alert-candidate scrap_qty sum 15.0 (10+5 from Group A "
            f"only), got {summary['scrap_qty']} (16.0 would indicate the old "
            f"whole-scope bug including Group B's 1 and Group C's 0)"
        )

    def test_summary_excludes_rows_failing_alert_candidate_predicate(self, tmp_path):
        """AC-3: rows failing SCRAP_QTY<>0 (Group C) or the
        (yield_pct>=risk_threshold AND scrap_qty<min_scrap_qty) exclusion
        (Group B) must not contribute to either transaction_qty or scrap_qty."""
        conn, full_where, full_params, reason_excl_sql, reason_excl_params = (
            self._build_alert_scope_kwargs(tmp_path)
        )

        summary = _query_summary(
            conn,
            dept_proc_where=full_where,
            dept_proc_params=full_params,
            reason_excl_sql=reason_excl_sql,
            reason_excl_params=reason_excl_params,
            risk_threshold=_RISK_THRESHOLD,
            min_scrap_qty=_MIN_SCRAP_QTY,
        )

        # Whole-scope (current buggy) totals would be 3500 / 16 — assert the
        # candidate-scope totals are strictly smaller, proving Group B/C were
        # excluded rather than merely coincidentally equal.
        assert summary["transaction_qty"] < 3500.0
        assert summary["transaction_qty"] == 1000.0
        assert summary["scrap_qty"] < 16.0
        assert summary["scrap_qty"] == 15.0

    def test_multi_reason_code_group_counts_transaction_qty_once(self, tmp_path):
        """AC-4 (core double-count regression): Group A has 2 distinct
        REASON_CODE rows (R1, R2) sharing one tx_extra_cols group. A naive
        `SUM(transaction_qty)` over `alerts_filtered`-shaped rows would count
        the group's transaction_qty (1000) twice -> 2000. The fix must count
        it exactly once. This pins the exact numeric expectation the fix must
        satisfy, independent of whether `_query_summary` already reuses the
        `_query_alerts` CTE chain."""
        conn, full_where, full_params, reason_excl_sql, reason_excl_params = (
            self._build_alert_scope_kwargs(tmp_path)
        )

        # First, prove the trap is real by tracing the same CTE chain
        # `_query_alerts` builds and naively summing `alerts_filtered` rows
        # (mirrors the change-request's documented root cause).
        alerts_result = _query_alerts(
            conn,
            full_where=full_where,
            full_params=full_params,
            reason_excl_sql=reason_excl_sql,
            reason_excl_params=reason_excl_params,
            granularity="day",
            risk_threshold=_RISK_THRESHOLD,
            min_scrap_qty=_MIN_SCRAP_QTY,
            sort_by="date_bucket",
            sort_dir="desc",
            page=1,
            per_page=100,
        )
        wo1_items = [i for i in alerts_result["items"] if i["workorder"] == "WO-1"]
        assert len(wo1_items) == 2, "Group A must surface as 2 alerts_filtered rows (R1, R2)"
        naive_sum = sum(i["transaction_qty"] for i in wo1_items)
        assert naive_sum == 2000.0, (
            "naive SUM(transaction_qty) over the 2 reason-coded rows must "
            "double-count the group's 1000 transaction_qty to 2000 — this is "
            "the double-count trap the fix's dedup must avoid"
        )

        # Now assert the KPI summary (once implemented) uses the deduped
        # value, not the naive double-counted one.
        summary = _query_summary(
            conn,
            dept_proc_where=full_where,
            dept_proc_params=full_params,
            reason_excl_sql=reason_excl_sql,
            reason_excl_params=reason_excl_params,
            risk_threshold=_RISK_THRESHOLD,
            min_scrap_qty=_MIN_SCRAP_QTY,
        )
        assert summary["transaction_qty"] == 1000.0, (
            f"KPI transaction_qty must count Group A's transaction_qty exactly "
            f"once (1000.0), got {summary['transaction_qty']} — "
            f"{naive_sum} would indicate the naive double-count trap leaked "
            f"into the summary"
        )

    def test_naive_sum_over_reason_coded_rows_would_double_count_documents_the_trap(self, tmp_path):
        """AC-4 data-boundary tripwire: a naive SUM(transaction_qty) directly over
        alerts_filtered rows (no DISTINCT tx_extra_cols dedup) must diverge from
        the correct deduped total for a multi-reason-code group. This documents
        the trap `_query_summary` must avoid; it is not itself the summary call."""
        conn, full_where, full_params, reason_excl_sql, reason_excl_params = (
            self._build_alert_scope_kwargs(tmp_path)
        )

        base_sql, all_cte_params = _build_alerts_filtered_cte(
            full_where=full_where,
            full_params=full_params,
            reason_excl_sql=reason_excl_sql,
            reason_excl_params=reason_excl_params,
            granularity="day",
            risk_threshold=_RISK_THRESHOLD,
            min_scrap_qty=_MIN_SCRAP_QTY,
        )
        naive_sql = base_sql + "SELECT SUM(transaction_qty) AS naive_tx FROM alerts_filtered"
        cursor = conn.execute(naive_sql, all_cte_params)
        naive_tx = cursor.fetchone()[0]

        assert naive_tx == 2000.0, (
            "naive SUM(transaction_qty) over alerts_filtered rows (no dedup) "
            "must double-count Group A's 1000 to 2000 — this is the exact trap "
            "the tx_extra_cols DISTINCT dedup in _query_summary must avoid"
        )

        summary = _query_summary(
            conn,
            dept_proc_where=full_where,
            dept_proc_params=full_params,
            reason_excl_sql=reason_excl_sql,
            reason_excl_params=reason_excl_params,
            risk_threshold=_RISK_THRESHOLD,
            min_scrap_qty=_MIN_SCRAP_QTY,
        )
        assert summary["transaction_qty"] != naive_tx
        assert summary["transaction_qty"] == 1000.0

    def test_department_name_split_within_one_tx_lookup_group_does_not_break_dedup(self, tmp_path):
        """AC-4 dedup-key regression tripwire: one tx_extra_cols group (WORKORDER +
        DEPARTMENT_GROUP + ... + DATE_BUCKET) spanning two distinct raw
        DEPARTMENT_NAME values must still dedup to ONE transaction_qty contribution.
        Using `_TX_DEDUP_COLS` (which wrongly adds raw DEPARTMENT_NAME) would split
        this group into two and double the KPI total — this test pins that the
        correct (coarser) `_TX_EXTRA_COLS` key is used instead (design.md Decision 2)."""
        parquet_path = tmp_path / "dept-name-split.parquet"
        common = {
            "DEPARTMENT_GROUP": "焊接_WB",
            "PROCESS_CATEGORY": "PC1",
            "LINE_NAME": "L1",
            "PACKAGE_NAME": "PKG1",
            "TYPE_NAME": "TY1",
            "FUNCTION_NAME": "FN1",
            "OPERATION_TEXT": "OP1",
            "DATE_BUCKET": "2026-03-01",
            "WORKORDER": "WO-SPLIT",
        }
        rows = [
            # Same tx_extra_cols group, but two different raw DEPARTMENT_NAME values.
            {**common, "DEPARTMENT_NAME": "焊接_WB_1線", "REASON_CODE": "R1",
             "REASON_NAME": "Reason1", "TRANSACTION_QTY": 300.0, "SCRAP_QTY": 10.0},
            {**common, "DEPARTMENT_NAME": "焊接_WB_2線", "REASON_CODE": "R1",
             "REASON_NAME": "Reason1", "TRANSACTION_QTY": 300.0, "SCRAP_QTY": 10.0},
        ]
        pd.DataFrame(rows).to_parquet(parquet_path, index=False)

        conn = duckdb.connect(database=":memory:")
        _attach_spool_view(conn, str(parquet_path))
        reason_excl_sql, reason_excl_params = _build_reason_exclusion_sql(set())
        full_where, full_params = _build_dimension_filter_sql({}, dept_proc_only=False)

        summary = _query_summary(
            conn,
            dept_proc_where=full_where,
            dept_proc_params=full_params,
            reason_excl_sql=reason_excl_sql,
            reason_excl_params=reason_excl_params,
            risk_threshold=_RISK_THRESHOLD,
            min_scrap_qty=_MIN_SCRAP_QTY,
        )

        # tx_extra_cols does NOT include DEPARTMENT_NAME, so the two rows fall
        # into the same tx_lookup group -> tx_raw = 300+300 = 600, deduped once.
        assert summary["transaction_qty"] == 600.0, (
            f"expected the coarser tx_extra_cols key to keep both DEPARTMENT_NAME "
            f"rows in one group (600.0), got {summary['transaction_qty']} — "
            f"1200.0 would indicate the wrong (too fine) _TX_DEDUP_COLS-style key "
            f"was used, splitting the group and double-counting"
        )
        assert "DEPARTMENT_NAME" not in _TX_EXTRA_COLS

    def test_summary_and_alerts_share_the_same_cte_builder(self, tmp_path):
        """Decision 1 structural guard: `_query_summary` and `_query_alerts` must
        both build their SQL from the SAME `_build_alerts_filtered_cte` fragment,
        not two independently-maintained copies of the CTE chain."""
        conn, full_where, full_params, reason_excl_sql, reason_excl_params = (
            self._build_alert_scope_kwargs(tmp_path)
        )

        base_sql_1, params_1 = _build_alerts_filtered_cte(
            full_where=full_where,
            full_params=full_params,
            reason_excl_sql=reason_excl_sql,
            reason_excl_params=reason_excl_params,
            granularity="day",
            risk_threshold=_RISK_THRESHOLD,
            min_scrap_qty=_MIN_SCRAP_QTY,
        )
        base_sql_2, params_2 = _build_alerts_filtered_cte(
            full_where=full_where,
            full_params=full_params,
            reason_excl_sql=reason_excl_sql,
            reason_excl_params=reason_excl_params,
            granularity="day",
            risk_threshold=_RISK_THRESHOLD,
            min_scrap_qty=_MIN_SCRAP_QTY,
        )
        assert base_sql_1 == base_sql_2
        assert params_1 == params_2
        assert "alerts_filtered AS (" in base_sql_1

        import inspect
        summary_src = inspect.getsource(_query_summary)
        alerts_src = inspect.getsource(_query_alerts)
        assert "_build_alerts_filtered_cte(" in summary_src, (
            "_query_summary must call the shared _build_alerts_filtered_cte builder"
        )
        assert "_build_alerts_filtered_cte(" in alerts_src, (
            "_query_alerts must call the shared _build_alerts_filtered_cte builder"
        )

    def test_try_compute_view_forwards_risk_threshold_and_min_scrap_qty_to_summary(
        self, tmp_path, monkeypatch,
    ):
        """AC-3: try_compute_view_from_spool must forward risk_threshold/
        min_scrap_qty into `_query_summary`, not only `_query_alerts` (design.md
        Open Risk #2)."""
        parquet_path = _make_kpi_csv_parity_fixture(tmp_path)

        monkeypatch.setattr(
            "mes_dashboard.services.yield_alert_sql_runtime.get_spool_file_path",
            lambda namespace, query_id: str(parquet_path),
        )
        monkeypatch.setattr(
            "mes_dashboard.core.duckdb_runtime.create_heavy_query_connection",
            lambda: duckdb.connect(database=":memory:"),
        )

        result, meta = try_compute_view_from_spool(
            query_id="qid-forward-001",
            filters={},
            granularity="day",
            page=1,
            per_page=50,
            sort_by="date_bucket",
            sort_dir="desc",
            risk_threshold=_RISK_THRESHOLD,
            min_scrap_qty=_MIN_SCRAP_QTY,
            excluded_reason_tokens=set(),
        )

        assert result is not None, f"expected a result, got fallback meta={meta}"
        # If risk_threshold/min_scrap_qty were NOT forwarded to _query_summary,
        # it would fall back to the whole-scope (buggy) totals (3500/16) instead
        # of the alert-candidate scope (1000/15).
        assert result["summary"]["transaction_qty"] == 1000.0
        assert result["summary"]["scrap_qty"] == 15.0
