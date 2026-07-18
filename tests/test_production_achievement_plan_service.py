# -*- coding: utf-8 -*-
"""Unit tests for production_achievement_plan_service.

Oracle-sourced production plan/target cache (business-rules.md PA-11),
replacing the Excel-imported production_achievement_daily_plans table.
Month-keyed L1(dict)+L2(Redis)+Oracle two-tier cache, mirrors
filter_cache.py/reason_filter_cache.py's established pattern.
"""

from __future__ import annotations

import time
from unittest.mock import patch

import pandas as pd
import pytest


@pytest.fixture(autouse=True)
def reset_cache():
    """Reset the per-month cache dict before/after each test."""
    import mes_dashboard.services.production_achievement_plan_service as svc
    svc._CACHE.clear()
    yield
    svc._CACHE.clear()


def _oracle_df(rows):
    return pd.DataFrame(rows, columns=["PLAN_PACKAGE_GROUP", "OUTPUT_DATE", "PLANQTY_INPUT", "PLANQTY_OUTPUT"])


class TestMonthsBetween:
    def test_single_day_within_one_month(self):
        from mes_dashboard.services.production_achievement_plan_service import _months_between
        assert _months_between("2026-07-05", "2026-07-05") == ["202607"]

    def test_full_month_range(self):
        from mes_dashboard.services.production_achievement_plan_service import _months_between
        assert _months_between("2026-07-01", "2026-07-31") == ["202607"]

    def test_range_spanning_two_calendar_months(self):
        from mes_dashboard.services.production_achievement_plan_service import _months_between
        assert _months_between("2026-06-20", "2026-07-05") == ["202606", "202607"]

    def test_range_spanning_year_boundary(self):
        from mes_dashboard.services.production_achievement_plan_service import _months_between
        assert _months_between("2025-12-15", "2026-01-10") == ["202512", "202601"]

    def test_range_spanning_three_months(self):
        from mes_dashboard.services.production_achievement_plan_service import _months_between
        assert _months_between("2026-05-31", "2026-07-01") == ["202605", "202606", "202607"]


class TestGetOraclePlanRows:
    def test_single_month_query_shapes_rows(self):
        import mes_dashboard.services.production_achievement_plan_service as svc

        df = _oracle_df([
            ("SOD-123FL", pd.Timestamp("2026-07-01"), 2814, 2758),
            ("DFN2510/0603", pd.Timestamp("2026-07-01"), 350, 192),
        ])
        with patch("mes_dashboard.services.production_achievement_plan_service.read_sql_df", return_value=df):
            rows = svc.get_oracle_plan_rows("2026-07-01", "2026-07-01")

        assert rows == [
            {"output_date": "2026-07-01", "plan_package_group": "SOD-123FL", "planqty_input": 2814, "planqty_output": 2758},
            {"output_date": "2026-07-01", "plan_package_group": "DFN2510/0603", "planqty_input": 350, "planqty_output": 192},
        ]

    def test_cross_month_range_queries_each_month_once(self):
        import mes_dashboard.services.production_achievement_plan_service as svc

        june_df = _oracle_df([("SOD-123FL", pd.Timestamp("2026-06-30"), 100, 90)])
        july_df = _oracle_df([("SOD-123FL", pd.Timestamp("2026-07-01"), 200, 190)])

        with patch(
            "mes_dashboard.services.production_achievement_plan_service.read_sql_df",
            side_effect=[june_df, july_df],
        ) as mock_sql:
            rows = svc.get_oracle_plan_rows("2026-06-30", "2026-07-01")

        assert mock_sql.call_count == 2
        tmonths = [call.args[1]["tmonth"] for call in mock_sql.call_args_list]
        assert tmonths == ["202606", "202607"]
        assert {r["output_date"] for r in rows} == {"2026-06-30", "2026-07-01"}

    def test_second_call_within_ttl_reuses_cache_no_oracle_call(self):
        import mes_dashboard.services.production_achievement_plan_service as svc

        df = _oracle_df([("SOD-123FL", pd.Timestamp("2026-07-01"), 2814, 2758)])
        with patch(
            "mes_dashboard.services.production_achievement_plan_service.read_sql_df",
            return_value=df,
        ) as mock_sql:
            svc.get_oracle_plan_rows("2026-07-01", "2026-07-01")
            svc.get_oracle_plan_rows("2026-07-01", "2026-07-01")

        mock_sql.assert_called_once()

    def test_force_refresh_bypasses_cache(self):
        import mes_dashboard.services.production_achievement_plan_service as svc

        df = _oracle_df([("SOD-123FL", pd.Timestamp("2026-07-01"), 2814, 2758)])
        with patch(
            "mes_dashboard.services.production_achievement_plan_service.read_sql_df",
            return_value=df,
        ) as mock_sql:
            svc.get_oracle_plan_rows("2026-07-01", "2026-07-01")
            svc.get_oracle_plan_rows("2026-07-01", "2026-07-01", force_refresh=True)

        assert mock_sql.call_count == 2

    def test_expired_ttl_triggers_requery(self):
        import mes_dashboard.services.production_achievement_plan_service as svc

        df = _oracle_df([("SOD-123FL", pd.Timestamp("2026-07-01"), 2814, 2758)])
        with patch(
            "mes_dashboard.services.production_achievement_plan_service.read_sql_df",
            return_value=df,
        ) as mock_sql:
            svc.get_oracle_plan_rows("2026-07-01", "2026-07-01")
            # Backdate the cached entry's loaded_at past the TTL window.
            svc._CACHE["202607"]["loaded_at"] = time.time() - svc._CACHE_TTL_SECONDS - 1
            svc.get_oracle_plan_rows("2026-07-01", "2026-07-01")

        assert mock_sql.call_count == 2

    def test_oracle_failure_degrades_that_month_to_empty_list(self):
        import mes_dashboard.services.production_achievement_plan_service as svc

        with patch(
            "mes_dashboard.services.production_achievement_plan_service.read_sql_df",
            side_effect=RuntimeError("ORA-12541: TNS:no listener"),
        ):
            rows = svc.get_oracle_plan_rows("2026-07-01", "2026-07-01")

        assert rows == []

    def test_oracle_failure_on_one_month_does_not_block_the_other(self):
        import mes_dashboard.services.production_achievement_plan_service as svc

        july_df = _oracle_df([("SOD-123FL", pd.Timestamp("2026-07-01"), 200, 190)])
        with patch(
            "mes_dashboard.services.production_achievement_plan_service.read_sql_df",
            side_effect=[RuntimeError("ORA-12541"), july_df],
        ):
            rows = svc.get_oracle_plan_rows("2026-06-30", "2026-07-01")

        assert rows == [
            {"output_date": "2026-07-01", "plan_package_group": "SOD-123FL", "planqty_input": 200, "planqty_output": 190},
        ]

    def test_full_month_shipped_not_narrowed_to_requested_range(self):
        """get_oracle_plan_rows ships the FULL cached month, not just the
        requested sub-range -- the cache is keyed per-month for reuse across
        different report requests touching that month; the client narrows."""
        import mes_dashboard.services.production_achievement_plan_service as svc

        df = _oracle_df([
            ("SOD-123FL", pd.Timestamp("2026-07-01"), 100, 90),
            ("SOD-123FL", pd.Timestamp("2026-07-15"), 100, 90),
            ("SOD-123FL", pd.Timestamp("2026-07-31"), 100, 90),
        ])
        with patch("mes_dashboard.services.production_achievement_plan_service.read_sql_df", return_value=df):
            rows = svc.get_oracle_plan_rows("2026-07-01", "2026-07-05")

        assert {r["output_date"] for r in rows} == {"2026-07-01", "2026-07-15", "2026-07-31"}

    def test_oracle_read_called_with_tmonth_param(self):
        import mes_dashboard.services.production_achievement_plan_service as svc

        df = _oracle_df([])
        with patch(
            "mes_dashboard.services.production_achievement_plan_service.read_sql_df",
            return_value=df,
        ) as mock_sql:
            svc.get_oracle_plan_rows("2026-07-01", "2026-07-01")

        call = mock_sql.call_args
        assert call.args[1] == {"tmonth": "202607"}
