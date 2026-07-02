# -*- coding: utf-8 -*-
"""Unit tests for production_achievement_target_service.

Data-shape §3.26: production_achievement_targets table, keyed on
(shift_code, workcenter_group), no date dimension, upsert via
INSERT ... ON DUPLICATE KEY UPDATE, direct MySQL via core/mysql_client.py.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from mes_dashboard.services.production_achievement_target_service import (
    TargetValidationError,
    get_targets,
    upsert_target,
    validate_target_qty,
)


class TestValidateTargetQty:
    def test_negative_target_qty_rejected(self):
        with pytest.raises(TargetValidationError):
            validate_target_qty(-1)

    def test_non_numeric_target_qty_rejected(self):
        with pytest.raises(TargetValidationError):
            validate_target_qty("abc")

    def test_zero_is_valid(self):
        assert validate_target_qty(0) == 0

    def test_positive_int_is_valid(self):
        assert validate_target_qty(500) == 500

    def test_float_with_integral_value_is_valid(self):
        assert validate_target_qty(500.0) == 500

    def test_float_with_fractional_value_rejected(self):
        with pytest.raises(TargetValidationError):
            validate_target_qty(500.5)

    def test_bool_rejected(self):
        # bool is a subclass of int in Python; must not silently accept True/False.
        with pytest.raises(TargetValidationError):
            validate_target_qty(True)


class TestUpsertTarget:
    @patch("mes_dashboard.services.production_achievement_target_service.MYSQL_OPS_ENABLED", True)
    @patch("mes_dashboard.services.production_achievement_target_service.get_mysql_connection")
    def test_upsert_target_unique_key_shift_workcenter_group(self, mock_conn_ctx):
        conn = MagicMock()
        mock_conn_ctx.return_value.__enter__.return_value = conn

        upsert_target(
            shift_code="D",
            workcenter_group="切割",
            target_qty=1000,
            updated_by="tester",
        )

        assert conn.execute.called
        call_args = conn.execute.call_args
        sql_text = str(call_args.args[0])
        assert "ON DUPLICATE KEY UPDATE" in sql_text
        params = call_args.args[1] if len(call_args.args) > 1 else call_args.kwargs.get("parameters")
        assert params["shift_code"] == "D"
        assert params["workcenter_group"] == "切割"
        assert params["target_qty"] == 1000
        assert params["updated_by"] == "tester"


class TestTargetReadNoDateDimension:
    @patch("mes_dashboard.services.production_achievement_target_service.MYSQL_OPS_ENABLED", True)
    @patch("mes_dashboard.services.production_achievement_target_service.get_mysql_connection")
    def test_target_read_no_date_dimension(self, mock_conn_ctx):
        conn = MagicMock()
        row = MagicMock()
        row._mapping = {
            "shift_code": "D",
            "workcenter_group": "切割",
            "target_qty": 1000,
            "updated_at": "2026-07-01T00:00:00",
            "updated_by": "tester",
        }
        result = MagicMock()
        result.fetchall.return_value = [row]
        conn.execute.return_value = result
        mock_conn_ctx.return_value.__enter__.return_value = conn

        rows = get_targets()

        assert rows == [
            {
                "shift_code": "D",
                "workcenter_group": "切割",
                "target_qty": 1000,
                "updated_at": "2026-07-01T00:00:00",
                "updated_by": "tester",
            }
        ]
        # No date-range param present in the underlying SELECT call.
        call_args = conn.execute.call_args
        sql_text = str(call_args.args[0])
        assert "output_date" not in sql_text.lower()
        assert "start_date" not in sql_text.lower()

    @patch("mes_dashboard.services.production_achievement_target_service.MYSQL_OPS_ENABLED", False)
    def test_read_degrades_to_empty_when_ops_disabled(self):
        """When MYSQL_OPS_ENABLED=false, read degrades (empty list), never raises."""
        assert get_targets() == []

    @patch("mes_dashboard.services.production_achievement_target_service.MYSQL_OPS_ENABLED", True)
    @patch("mes_dashboard.services.production_achievement_target_service.get_mysql_connection")
    def test_read_degrades_to_empty_on_mysql_exception(self, mock_conn_ctx):
        mock_conn_ctx.side_effect = RuntimeError("connection refused")
        assert get_targets() == []
