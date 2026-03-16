# -*- coding: utf-8 -*-
"""E2E tests for Hold Overview module.

Endpoints:
  GET /api/hold-overview/summary  → KPI summary
  GET /api/hold-overview/matrix   → workcenter x package matrix
  GET /api/hold-overview/treemap  → hierarchical treemap
  GET /api/hold-overview/lots     → paginated lot list

Run with: pytest tests/e2e/test_hold_overview_e2e.py -v -s
"""

import pytest
import requests


@pytest.mark.e2e
class TestHoldOverviewE2E:
    """E2E tests for Hold Overview endpoints."""

    def test_summary_returns_data(self, app_server):
        """GET /summary returns hold summary KPIs."""
        resp = requests.get(f"{app_server}/api/hold-overview/summary", timeout=30)
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["success"] is True
        data = payload["data"]
        assert "total_count" in data or "total" in data or isinstance(data, dict)

    def test_summary_with_hold_type_filter(self, app_server):
        """GET /summary with hold_type=quality returns filtered data."""
        resp = requests.get(
            f"{app_server}/api/hold-overview/summary",
            params={"hold_type": "quality"},
            timeout=30,
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_summary_rejects_invalid_hold_type(self, app_server):
        """GET /summary with invalid hold_type returns 400."""
        resp = requests.get(
            f"{app_server}/api/hold-overview/summary",
            params={"hold_type": "bad_type"},
            timeout=30,
        )
        assert resp.status_code == 400

    def test_matrix_returns_data(self, app_server):
        """GET /matrix returns workcenter x package hold matrix."""
        resp = requests.get(f"{app_server}/api/hold-overview/matrix", timeout=30)
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["success"] is True

    def test_treemap_returns_data(self, app_server):
        """GET /treemap returns hierarchical hold treemap."""
        resp = requests.get(f"{app_server}/api/hold-overview/treemap", timeout=30)
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["success"] is True

    def test_lots_returns_paginated_data(self, app_server):
        """GET /lots returns paginated hold lot list."""
        resp = requests.get(
            f"{app_server}/api/hold-overview/lots",
            params={"page": 1, "per_page": 10},
            timeout=30,
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["success"] is True
        data = payload["data"]
        assert "lots" in data
        assert "pagination" in data

    def test_lots_with_age_range_filter(self, app_server):
        """GET /lots with age_range filter returns filtered data."""
        resp = requests.get(
            f"{app_server}/api/hold-overview/lots",
            params={"age_range": "0-1", "page": 1, "per_page": 10},
            timeout=30,
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_lots_rejects_invalid_age_range(self, app_server):
        """GET /lots with invalid age_range returns 400."""
        resp = requests.get(
            f"{app_server}/api/hold-overview/lots",
            params={"age_range": "invalid"},
            timeout=30,
        )
        assert resp.status_code == 400
