# -*- coding: utf-8 -*-
"""Unit tests for production_achievement_daily_plan_service.

Data-shape §3.32: production_achievement_daily_plans table, keyed on
(workcenter_group, package_lf_group) -- both already-MERGED/resolved values --
with NO shift dimension, unlike production_achievement_targets (§3.26).
Fully independent/additive: writing this table never mutates
production_achievement_targets. business-rules.md PA-11.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from mes_dashboard.services.production_achievement_daily_plan_service import (
    DailyPlanValidationError,
    MySQLUnavailableError,
    get_daily_plans,
    get_daily_plans_map,
    upsert_daily_plan,
    validate_daily_plan_qty,
)


class TestValidateDailyPlanQty:
    def test_negative_qty_rejected(self):
        with pytest.raises(DailyPlanValidationError):
            validate_daily_plan_qty(-1)

    def test_non_numeric_qty_rejected(self):
        with pytest.raises(DailyPlanValidationError):
            validate_daily_plan_qty("abc")

    def test_zero_is_valid(self):
        assert validate_daily_plan_qty(0) == 0

    def test_positive_int_is_valid(self):
        assert validate_daily_plan_qty(300) == 300

    def test_negative_qty_rejected_before_mysql(self):
        """400 VALIDATION_ERROR must be raised before any MySQL round-trip
        is attempted -- validate_daily_plan_qty is a pure function, never
        touches get_mysql_connection."""
        with patch(
            "mes_dashboard.services.production_achievement_daily_plan_service.get_mysql_connection"
        ) as mock_conn:
            with pytest.raises(DailyPlanValidationError):
                validate_daily_plan_qty(-5)
            mock_conn.assert_not_called()


class TestGetDailyPlans:
    @patch("mes_dashboard.services.production_achievement_daily_plan_service.MYSQL_OPS_ENABLED", True)
    @patch("mes_dashboard.services.production_achievement_daily_plan_service.get_mysql_connection")
    def test_get_daily_plans_returns_full_rows(self, mock_conn_ctx):
        conn = MagicMock()
        row = MagicMock()
        row._mapping = {
            "workcenter_group": "焊接_DB",
            "package_lf_group": "SOD-123FL",
            "daily_plan_qty": 300,
            "updated_at": "2026-07-01T00:00:00",
            "updated_by": "tester",
        }
        result = MagicMock()
        result.fetchall.return_value = [row]
        conn.execute.return_value = result
        mock_conn_ctx.return_value.__enter__.return_value = conn

        rows = get_daily_plans()
        assert rows == [
            {
                "workcenter_group": "焊接_DB",
                "package_lf_group": "SOD-123FL",
                "daily_plan_qty": 300,
                "updated_at": "2026-07-01T00:00:00",
                "updated_by": "tester",
            }
        ]

    @patch("mes_dashboard.services.production_achievement_daily_plan_service.MYSQL_OPS_ENABLED", False)
    def test_read_degrades_empty_null_qty_when_ops_disabled(self):
        """PA-12/PA-13: every client-computed daily/cumulative
        achievement_rate becomes null when this degrades -- verified here at
        the service boundary as an empty list/dict (never 500)."""
        assert get_daily_plans() == []
        assert get_daily_plans_map() == {}

    @patch("mes_dashboard.services.production_achievement_daily_plan_service.MYSQL_OPS_ENABLED", True)
    @patch("mes_dashboard.services.production_achievement_daily_plan_service.get_mysql_connection")
    def test_read_degrades_empty_on_mysql_exception(self, mock_conn_ctx):
        mock_conn_ctx.side_effect = RuntimeError("connection refused")
        assert get_daily_plans() == []
        assert get_daily_plans_map() == {}


class TestGetDailyPlansMap:
    @patch("mes_dashboard.services.production_achievement_daily_plan_service.MYSQL_OPS_ENABLED", True)
    @patch("mes_dashboard.services.production_achievement_daily_plan_service.get_mysql_connection")
    def test_map_keyed_on_workcenter_package_lf_group_tuple(self, mock_conn_ctx):
        conn = MagicMock()
        row = MagicMock()
        row._mapping = {
            "workcenter_group": "焊接_DB",
            "package_lf_group": "SOD-123FL",
            "daily_plan_qty": 300,
            "updated_at": "2026-07-01T00:00:00",
            "updated_by": "tester",
        }
        result = MagicMock()
        result.fetchall.return_value = [row]
        conn.execute.return_value = result
        mock_conn_ctx.return_value.__enter__.return_value = conn

        assert get_daily_plans_map() == {("焊接_DB", "SOD-123FL"): 300}


class TestUpsertDailyPlan:
    @patch("mes_dashboard.services.production_achievement_daily_plan_service.MYSQL_OPS_ENABLED", True)
    @patch("mes_dashboard.services.production_achievement_daily_plan_service.get_mysql_connection")
    def test_upsert_unique_key_workcenter_package_lf_group(self, mock_conn_ctx):
        conn = MagicMock()
        mock_conn_ctx.return_value.__enter__.return_value = conn

        upsert_daily_plan(
            workcenter_group="焊接_DB",
            package_lf_group="SOD-123FL",
            daily_plan_qty=300,
            updated_by="tester",
        )

        assert conn.execute.called
        call_args = conn.execute.call_args
        sql_text = str(call_args.args[0])
        assert "ON DUPLICATE KEY UPDATE" in sql_text
        assert "production_achievement_daily_plans" in sql_text
        params = call_args.args[1] if len(call_args.args) > 1 else call_args.kwargs.get("parameters")
        assert params["workcenter_group"] == "焊接_DB"
        assert params["package_lf_group"] == "SOD-123FL"
        assert params["daily_plan_qty"] == 300
        assert params["updated_by"] == "tester"

    def test_coexists_with_targets_table_no_cross_write(self):
        """PA-11: production_achievement_daily_plans and
        production_achievement_targets are fully independent -- upserting
        one must never reference the other table's name in its SQL text."""
        import mes_dashboard.services.production_achievement_daily_plan_service as svc

        with patch.object(svc, "MYSQL_OPS_ENABLED", True), \
             patch.object(svc, "get_mysql_connection") as mock_conn_ctx:
            conn = MagicMock()
            mock_conn_ctx.return_value.__enter__.return_value = conn

            svc.upsert_daily_plan(
                workcenter_group="焊接_DB",
                package_lf_group="SOD-123FL",
                daily_plan_qty=300,
                updated_by="tester",
            )

            sql_text = str(conn.execute.call_args.args[0])
            assert "production_achievement_targets" not in sql_text
            assert "production_achievement_daily_plans" in sql_text

    @patch("mes_dashboard.services.production_achievement_daily_plan_service.MYSQL_OPS_ENABLED", False)
    def test_write_raises_mysqlunavailableerror_when_ops_disabled(self):
        with pytest.raises(MySQLUnavailableError):
            upsert_daily_plan(
                workcenter_group="焊接_DB",
                package_lf_group="SOD-123FL",
                daily_plan_qty=300,
                updated_by="tester",
            )
