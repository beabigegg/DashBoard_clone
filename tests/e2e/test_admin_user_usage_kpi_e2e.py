# -*- coding: utf-8 -*-
"""E2E tests for Admin User Usage KPI page.

Tests:
  GET /admin/api/user-usage-kpi — KPI aggregation endpoint

Run with: pytest tests/e2e/test_admin_user_usage_kpi_e2e.py -v --run-e2e
"""

import pytest
import requests


@pytest.mark.e2e
class TestAdminUserUsageKpiEndpoint:
    """E2E tests for /admin/api/user-usage-kpi."""

    def test_kpi_without_dates_returns_validation_error_or_success(self, app_server):
        resp = requests.get(
            f"{app_server}/admin/api/user-usage-kpi",
            timeout=30,
            allow_redirects=False,
        )
        assert resp.status_code in (200, 400, 302, 401, 403)
        if resp.status_code in (200, 400):
            payload = resp.json()
            assert "success" in payload

    def test_kpi_with_valid_dates_returns_overview(self, app_server):
        resp = requests.get(
            f"{app_server}/admin/api/user-usage-kpi",
            params={"start_date": "2026-03-01", "end_date": "2026-03-31"},
            timeout=60,
            allow_redirects=False,
        )
        assert resp.status_code in (200, 302, 401, 403)
        if resp.status_code == 200:
            payload = resp.json()
            assert payload["success"] is True
            data = payload.get("data", {})
            assert isinstance(data, dict)

    def test_kpi_with_department_filter(self, app_server):
        resp = requests.get(
            f"{app_server}/admin/api/user-usage-kpi",
            params={
                "start_date": "2026-03-01",
                "end_date": "2026-03-31",
                "department": "ENG",
            },
            timeout=60,
            allow_redirects=False,
        )
        assert resp.status_code in (200, 302, 401, 403)
        if resp.status_code == 200:
            payload = resp.json()
            assert payload["success"] is True

    def test_kpi_response_has_expected_fields(self, app_server):
        resp = requests.get(
            f"{app_server}/admin/api/user-usage-kpi",
            params={"start_date": "2026-03-01", "end_date": "2026-03-31"},
            timeout=60,
            allow_redirects=False,
        )
        if resp.status_code == 200:
            payload = resp.json()
            data = payload.get("data", {})
            # Expected fields from user_usage_kpi_service
            expected_fields = {"overview", "dau_trend", "duration_distribution"}
            assert expected_fields.issubset(set(data.keys())), (
                f"Missing fields: {expected_fields - set(data.keys())}"
            )


@pytest.mark.e2e
class TestAdminUserUsageKpiPageLoad:
    """E2E tests for user usage KPI page rendering."""

    def test_user_usage_kpi_page_accessible(self, app_server):
        resp = requests.get(
            f"{app_server}/admin/user-usage-kpi",
            timeout=30,
            allow_redirects=True,
        )
        assert resp.status_code in (200, 302, 401, 403)
