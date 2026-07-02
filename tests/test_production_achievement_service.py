# -*- coding: utf-8 -*-
"""Unit tests for production_achievement_service (PA-05/PA-06/PA-07).

Tests use pandas DataFrames to simulate the Oracle read_sql_df() result
(grouped rows: output_date, shift_code, SPECNAME, actual_output_qty) and
verify the Python-side workcenter_group resolution (via filter_cache reuse)
and achievement-rate math -- NOT the Oracle SQL text itself (that's covered
by the PA-05 predicate being embedded verbatim in sql/production_achievement.sql,
reviewed statically). Grouping-by-SPECNAME-then-remap-to-workcenter_group
matches design.md's Python-side re-aggregation after filter_cache resolution.
"""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest

from mes_dashboard.services.production_achievement_service import (
    build_achievement_rows,
    PA05_PREDICATE_SQL,
)


class TestPA05PredicateSQL:
    def test_pa05_predicate_excludes_shuangjing_sanjing_rows(self):
        """The 雙晶/三晶 exclusion clause must appear verbatim in the predicate."""
        assert "雙晶" in PA05_PREDICATE_SQL
        assert "三晶" in PA05_PREDICATE_SQL
        assert "WORKFLOWNAME LIKE '%雙晶%'" in PA05_PREDICATE_SQL
        assert "WORKFLOWNAME LIKE '%三晶%'" in PA05_PREDICATE_SQL

    @pytest.mark.parametrize(
        "specname_or_processtype",
        [
            "Epoxy D/B",
            "Eutectic D/B",
            "Solder Paste D/B",
            "Solder D/B+E-Clip+固化",
            "金線製程",
            "銀線製程",
            "銅線製程",
            "手工跳線",
            "雷射焊接",
            "包膠-WB",
            "DWB_WB2",
            "DWB_WB",
            "Epoxy D/B-2",
            "Eutectic D/B-雙晶",
            "Epoxy D/B-3",
            "2DB_DB2",
            "2DB_DB",
            "DBCB_CB",
            "CBA_RO",
        ],
    )
    def test_pa05_predicate_each_specname_processtype_pairing(self, specname_or_processtype):
        assert specname_or_processtype in PA05_PREDICATE_SQL


class TestGroupingAndWorkcenterGroupResolution:
    @patch("mes_dashboard.services.production_achievement_service.get_spec_workcenter_mapping")
    def test_grouping_by_output_date_shift_workcenter_group(self, mock_mapping):
        mock_mapping.return_value = {
            "EPOXY D/B": {"workcenter": "WC1", "group": "焊接_DB", "sequence": 1},
        }
        df = pd.DataFrame(
            [
                {
                    "OUTPUT_DATE": "2026-04-27",
                    "SHIFT_CODE": "D",
                    "SPECNAME": "Epoxy D/B",
                    "ACTUAL_OUTPUT_QTY": 100,
                },
                {
                    "OUTPUT_DATE": "2026-04-27",
                    "SHIFT_CODE": "D",
                    "SPECNAME": "epoxy d/b",
                    "ACTUAL_OUTPUT_QTY": 50,
                },
            ]
        )
        rows = build_achievement_rows(df, targets={})
        assert len(rows) == 1
        row = rows[0]
        assert row["output_date"] == "2026-04-27"
        assert row["shift_code"] == "D"
        assert row["workcenter_group"] == "焊接_DB"
        assert row["actual_output_qty"] == 150

    @patch("mes_dashboard.services.production_achievement_service.get_spec_workcenter_mapping")
    def test_workcenter_group_resolved_via_filter_cache_not_hardcoded(self, mock_mapping):
        mock_mapping.return_value = {"金線製程": {"workcenter": "WC2", "group": "焊接_WB", "sequence": 2}}
        df = pd.DataFrame(
            [
                {
                    "OUTPUT_DATE": "2026-04-27",
                    "SHIFT_CODE": "N",
                    "SPECNAME": "金線製程",
                    "ACTUAL_OUTPUT_QTY": 10,
                }
            ]
        )
        rows = build_achievement_rows(df, targets={})
        assert rows[0]["workcenter_group"] == "焊接_WB"
        mock_mapping.assert_called()

    @patch("mes_dashboard.services.production_achievement_service.get_spec_workcenter_mapping")
    def test_unmapped_specname_excluded_from_output(self, mock_mapping):
        mock_mapping.return_value = {}
        df = pd.DataFrame(
            [
                {
                    "OUTPUT_DATE": "2026-04-27",
                    "SHIFT_CODE": "D",
                    "SPECNAME": "UNKNOWN_SPEC",
                    "ACTUAL_OUTPUT_QTY": 10,
                }
            ]
        )
        rows = build_achievement_rows(df, targets={})
        assert rows == []

    @patch("mes_dashboard.services.production_achievement_service.get_spec_workcenter_mapping")
    def test_empty_qualifying_rows_yields_empty_result_not_error(self, mock_mapping):
        mock_mapping.return_value = {}
        df = pd.DataFrame(columns=["OUTPUT_DATE", "SHIFT_CODE", "SPECNAME", "ACTUAL_OUTPUT_QTY"])
        rows = build_achievement_rows(df, targets={})
        assert rows == []


class TestAchievementRateMath:
    @patch("mes_dashboard.services.production_achievement_service.get_spec_workcenter_mapping")
    def test_achievement_rate_missing_target_is_null(self, mock_mapping):
        mock_mapping.return_value = {"EPOXY D/B": {"workcenter": "WC1", "group": "焊接_DB", "sequence": 1}}
        df = pd.DataFrame(
            [{"OUTPUT_DATE": "2026-04-27", "SHIFT_CODE": "D", "SPECNAME": "Epoxy D/B", "ACTUAL_OUTPUT_QTY": 100}]
        )
        rows = build_achievement_rows(df, targets={})
        assert rows[0]["target_qty"] is None
        assert rows[0]["achievement_rate"] is None

    @patch("mes_dashboard.services.production_achievement_service.get_spec_workcenter_mapping")
    def test_achievement_rate_zero_target_is_null_not_infinity(self, mock_mapping):
        mock_mapping.return_value = {"EPOXY D/B": {"workcenter": "WC1", "group": "焊接_DB", "sequence": 1}}
        df = pd.DataFrame(
            [{"OUTPUT_DATE": "2026-04-27", "SHIFT_CODE": "D", "SPECNAME": "Epoxy D/B", "ACTUAL_OUTPUT_QTY": 100}]
        )
        targets = {("D", "焊接_DB"): 0}
        rows = build_achievement_rows(df, targets=targets)
        assert rows[0]["target_qty"] == 0
        assert rows[0]["achievement_rate"] is None

    @patch("mes_dashboard.services.production_achievement_service.get_spec_workcenter_mapping")
    def test_achievement_rate_zero_output_nonzero_target_is_zero(self, mock_mapping):
        mock_mapping.return_value = {"EPOXY D/B": {"workcenter": "WC1", "group": "焊接_DB", "sequence": 1}}
        df = pd.DataFrame(
            [{"OUTPUT_DATE": "2026-04-27", "SHIFT_CODE": "D", "SPECNAME": "Epoxy D/B", "ACTUAL_OUTPUT_QTY": 0}]
        )
        targets = {("D", "焊接_DB"): 500}
        rows = build_achievement_rows(df, targets=targets)
        assert rows[0]["actual_output_qty"] == 0
        assert rows[0]["achievement_rate"] == 0.0

    @patch("mes_dashboard.services.production_achievement_service.get_spec_workcenter_mapping")
    def test_achievement_rate_normal_division(self, mock_mapping):
        mock_mapping.return_value = {"EPOXY D/B": {"workcenter": "WC1", "group": "焊接_DB", "sequence": 1}}
        df = pd.DataFrame(
            [{"OUTPUT_DATE": "2026-04-27", "SHIFT_CODE": "D", "SPECNAME": "Epoxy D/B", "ACTUAL_OUTPUT_QTY": 250}]
        )
        targets = {("D", "焊接_DB"): 500}
        rows = build_achievement_rows(df, targets=targets)
        assert rows[0]["achievement_rate"] == 0.5
