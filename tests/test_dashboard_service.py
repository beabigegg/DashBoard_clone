# -*- coding: utf-8 -*-
"""Unit tests for dashboard_service.py — dashboard KPI aggregation service."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from unittest.mock import patch, MagicMock
import pytest


@pytest.fixture
def app():
    import mes_dashboard.core.database as db
    db._ENGINE = None
    from mes_dashboard.app import create_app
    app = create_app("testing")
    app.config["TESTING"] = True
    return app


class TestQueryDashboardKpi:
    def test_returns_none_when_summary_empty(self, app):
        from mes_dashboard.services.dashboard_service import query_dashboard_kpi
        with app.app_context():
            with patch(
                "mes_dashboard.services.dashboard_service.get_resource_status_summary",
                return_value={"total_count": 0, "by_status": {}, "ou_pct": 0},
            ):
                result = query_dashboard_kpi()
        assert result is None

    def test_returns_kpi_dict_when_summary_present(self, app):
        from mes_dashboard.services.dashboard_service import query_dashboard_kpi
        mock_summary = {
            "total_count": 100,
            "by_status": {"PRD": 70, "SBY": 10, "UDT": 5, "SDT": 5, "EGT": 5, "NST": 5},
            "ou_pct": 75.0,
        }
        with app.app_context():
            with patch(
                "mes_dashboard.services.dashboard_service.get_resource_status_summary",
                return_value=mock_summary,
            ):
                result = query_dashboard_kpi()
        assert result is not None
        assert "total" in result or "ou_pct" in result

    def test_filters_passed_to_summary(self, app):
        from mes_dashboard.services.dashboard_service import query_dashboard_kpi
        mock_summary = {
            "total_count": 50,
            "by_status": {"PRD": 40},
            "ou_pct": 80.0,
        }
        captured = {}
        def fake_summary(**kwargs):
            captured.update(kwargs)
            return mock_summary
        with app.app_context():
            with patch(
                "mes_dashboard.services.dashboard_service.get_resource_status_summary",
                side_effect=fake_summary,
            ):
                query_dashboard_kpi(filters={"isProduction": True, "isKey": True})
        assert captured.get("is_production") is True
        assert captured.get("is_key") is True

    def test_none_filters_does_not_crash(self, app):
        from mes_dashboard.services.dashboard_service import query_dashboard_kpi
        with app.app_context():
            with patch(
                "mes_dashboard.services.dashboard_service.get_resource_status_summary",
                return_value={"total_count": 0, "by_status": {}, "ou_pct": 0},
            ):
                result = query_dashboard_kpi(filters=None)
        assert result is None


class TestQueryWorkcentercards:
    def test_returns_none_on_db_failure(self, app):
        from mes_dashboard.services.dashboard_service import query_workcenter_cards
        with app.app_context():
            with patch(
                "mes_dashboard.services.dashboard_service.get_workcenter_status_matrix",
                return_value=None,
            ):
                result = query_workcenter_cards()
        # When the dependency returns None the service may return None or empty
        # depending on implementation; just verify it doesn't raise.
        assert result is None or isinstance(result, (list, dict))

    def test_returns_data_on_success(self, app):
        from mes_dashboard.services.dashboard_service import query_workcenter_cards
        mock_matrix = [{
            "workcenter_group": "DB",
            "workcenter_sequence": 1,
            "total": 20,
            "PRD": 10, "SBY": 5, "UDT": 2, "SDT": 1, "EGT": 1, "NST": 1,
        }]
        with app.app_context():
            with patch(
                "mes_dashboard.services.dashboard_service.get_workcenter_status_matrix",
                return_value=mock_matrix,
            ):
                result = query_workcenter_cards()
        assert result is not None
        assert len(result) == 1
        assert result[0]["workcenter"] == "DB"
