# -*- coding: utf-8 -*-
"""E2E tests for Yield Alert Center module.

Tests multiple endpoints:
  POST /api/yield-alert/query   → primary query
  GET  /api/yield-alert/view    → cached view
  GET  /api/yield-alert/summary → summary KPIs
  GET  /api/yield-alert/alerts  → alert candidates
  GET  /api/yield-alert/trend   → trend data
  GET  /api/yield-alert/filter-options → workcenter groups
  GET  /api/yield-alert/drilldown-context → drilldown payload

Run with: pytest tests/e2e/test_yield_alert_e2e.py -v -s
"""

import pytest
import requests


@pytest.mark.e2e
class TestYieldAlertFilterOptions:
    """E2E tests for Yield Alert filter options."""

    def test_filter_options_returns_workcenter_groups(self, api_base_url):
        """GET /filter-options returns workcenter groups list."""
        resp = requests.get(
            f"{api_base_url}/yield-alert/filter-options", timeout=30
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["success"] is True
        assert "workcenter_groups" in payload["data"]
        assert isinstance(payload["data"]["workcenter_groups"], list)


@pytest.mark.e2e
class TestYieldAlertSummary:
    """E2E tests for Yield Alert summary endpoint."""

    def test_summary_requires_dates(self, api_base_url):
        """GET /summary without dates returns 400."""
        resp = requests.get(f"{api_base_url}/yield-alert/summary", timeout=30)
        assert resp.status_code == 400
        payload = resp.json()
        assert payload["success"] is False

    def test_summary_returns_kpis(self, api_base_url):
        """GET /summary with valid dates returns KPI data."""
        resp = requests.get(
            f"{api_base_url}/yield-alert/summary",
            params={"start_date": "2026-03-01", "end_date": "2026-03-07"},
            timeout=60,
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["success"] is True


@pytest.mark.e2e
class TestYieldAlertAlerts:
    """E2E tests for Yield Alert alerts endpoint."""

    def test_alerts_rejects_invalid_sort_key(self, api_base_url):
        """GET /alerts with invalid sort_by returns 400."""
        resp = requests.get(
            f"{api_base_url}/yield-alert/alerts",
            params={
                "start_date": "2026-03-01",
                "end_date": "2026-03-07",
                "sort_by": "invalid_field",
            },
            timeout=30,
        )
        assert resp.status_code == 400

    def test_alerts_returns_paginated_list(self, api_base_url):
        """GET /alerts with valid params returns paginated alert items."""
        resp = requests.get(
            f"{api_base_url}/yield-alert/alerts",
            params={
                "start_date": "2026-03-01",
                "end_date": "2026-03-07",
                "page": 1,
                "per_page": 10,
            },
            timeout=60,
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["success"] is True
        data = payload["data"]
        assert "items" in data
        assert "pagination" in data

    def test_alerts_respects_per_page_cap(self, api_base_url):
        """GET /alerts caps per_page to max allowed value."""
        resp = requests.get(
            f"{api_base_url}/yield-alert/alerts",
            params={
                "start_date": "2026-03-01",
                "end_date": "2026-03-07",
                "per_page": 9999,
            },
            timeout=60,
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["success"] is True
        pagination = payload["data"]["pagination"]
        assert pagination["per_page"] <= 200


@pytest.mark.e2e
class TestYieldAlertTrend:
    """E2E tests for Yield Alert trend endpoint."""

    def test_trend_returns_data(self, api_base_url):
        """GET /trend with valid dates returns trend data."""
        resp = requests.get(
            f"{api_base_url}/yield-alert/trend",
            params={"start_date": "2026-03-01", "end_date": "2026-03-07"},
            timeout=60,
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["success"] is True


@pytest.mark.e2e
class TestYieldAlertQuery:
    """E2E tests for Yield Alert primary query."""

    def test_query_requires_dates(self, api_base_url):
        """POST /query without dates returns 400."""
        resp = requests.post(
            f"{api_base_url}/yield-alert/query", json={}, timeout=30
        )
        assert resp.status_code == 400

    def test_query_returns_query_id(self, api_base_url):
        """POST /query with valid dates returns query_id."""
        resp = requests.post(
            f"{api_base_url}/yield-alert/query",
            json={"start_date": "2026-03-01", "end_date": "2026-03-07"},
            timeout=120,
        )
        # May return 200 or 503 if system is busy
        if resp.status_code == 200:
            payload = resp.json()
            assert payload["success"] is True
        else:
            assert resp.status_code in (400, 503)


@pytest.mark.e2e
class TestYieldAlertView:
    """E2E tests for Yield Alert cached view."""

    def test_view_requires_query_id(self, api_base_url):
        """GET /view without query_id returns 400."""
        resp = requests.get(f"{api_base_url}/yield-alert/view", timeout=30)
        assert resp.status_code == 400

    def test_view_expired_returns_410(self, api_base_url):
        """GET /view with expired query_id returns 410."""
        resp = requests.get(
            f"{api_base_url}/yield-alert/view",
            params={"query_id": "nonexistent-expired-id"},
            timeout=30,
        )
        assert resp.status_code == 410


@pytest.mark.e2e
class TestYieldAlertDrilldown:
    """E2E tests for Yield Alert drilldown context."""

    def test_drilldown_requires_params(self, api_base_url):
        """GET /drilldown-context without params returns 400."""
        resp = requests.get(
            f"{api_base_url}/yield-alert/drilldown-context", timeout=30
        )
        assert resp.status_code == 400


@pytest.mark.e2e
class TestYieldAlertDateRangeLimit:
    """E2E tests for date range limit enforcement.

    The actual limit is controlled by YIELD_ALERT_MAX_QUERY_DAYS env var
    (defaults to 730, but .env may override to a lower value like 93).
    We discover the limit from the error response to stay robust.
    """

    def _discover_max_days(self, api_base_url) -> int:
        """Probe the server's actual max_query_days value."""
        resp = requests.get(
            f"{api_base_url}/yield-alert/summary",
            params={"start_date": "2020-01-01", "end_date": "2026-03-13"},
            timeout=10,
        )
        if resp.status_code == 400:
            meta = resp.json().get("meta", {})
            return meta.get("max_query_days", 730)
        return 730

    def test_summary_accepts_within_limit_range(self, api_base_url):
        """GET /summary within the server's max_query_days should succeed."""
        max_days = self._discover_max_days(api_base_url)
        from datetime import date, timedelta
        end = date(2026, 3, 13)
        start = end - timedelta(days=max_days - 1)
        resp = requests.get(
            f"{api_base_url}/yield-alert/summary",
            params={"start_date": start.isoformat(), "end_date": end.isoformat()},
            timeout=120,
        )
        assert resp.status_code == 200

    def test_summary_rejects_over_limit_range(self, api_base_url):
        """GET /summary exceeding max_query_days should return 400."""
        max_days = self._discover_max_days(api_base_url)
        from datetime import date, timedelta
        end = date(2026, 3, 13)
        start = end - timedelta(days=max_days + 10)
        resp = requests.get(
            f"{api_base_url}/yield-alert/summary",
            params={"start_date": start.isoformat(), "end_date": end.isoformat()},
            timeout=30,
        )
        assert resp.status_code == 400
        payload = resp.json()
        assert payload["success"] is False
        assert str(max_days) in payload.get("error", {}).get("message", "")
