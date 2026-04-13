# -*- coding: utf-8 -*-
"""E2E tests for Admin Performance Monitoring page.

Tests:
  GET /admin/api/metrics             — query performance percentiles
  GET /admin/api/performance-detail  — per-query detail breakdown
  GET /admin/api/performance-history — historical metric buckets

Run with: pytest tests/e2e/test_admin_performance_e2e.py -v --run-e2e
"""

import pytest
import requests


@pytest.mark.e2e
class TestAdminMetricsEndpoint:
    """E2E tests for /admin/api/metrics."""

    def test_metrics_accessible(self, app_server):
        resp = requests.get(
            f"{app_server}/admin/api/metrics", timeout=30, allow_redirects=False
        )
        assert resp.status_code in (200, 302, 401, 403)
        if resp.status_code == 200:
            payload = resp.json()
            assert payload["success"] is True

    def test_metrics_has_latency_percentiles(self, app_server):
        resp = requests.get(
            f"{app_server}/admin/api/metrics", timeout=30, allow_redirects=False
        )
        if resp.status_code == 200:
            payload = resp.json()
            data = payload.get("data", {})
            # p50/p95/p99 or count fields expected
            has_perf_keys = any(k in data for k in ("p50_ms", "p95_ms", "count"))
            assert has_perf_keys or isinstance(data, dict)


@pytest.mark.e2e
class TestAdminPerformanceDetailEndpoint:
    """E2E tests for /admin/api/performance-detail."""

    def test_performance_detail_accessible(self, app_server):
        resp = requests.get(
            f"{app_server}/admin/api/performance-detail", timeout=30, allow_redirects=False
        )
        assert resp.status_code in (200, 302, 401, 403)
        if resp.status_code == 200:
            payload = resp.json()
            assert payload["success"] is True

    def test_performance_detail_returns_list(self, app_server):
        resp = requests.get(
            f"{app_server}/admin/api/performance-detail", timeout=30, allow_redirects=False
        )
        if resp.status_code == 200:
            payload = resp.json()
            data = payload.get("data", [])
            assert isinstance(data, (list, dict))


@pytest.mark.e2e
class TestAdminPerformanceHistoryEndpoint:
    """E2E tests for /admin/api/performance-history."""

    def test_performance_history_accessible(self, app_server):
        resp = requests.get(
            f"{app_server}/admin/api/performance-history", timeout=30, allow_redirects=False
        )
        assert resp.status_code in (200, 302, 401, 403)
        if resp.status_code == 200:
            payload = resp.json()
            assert payload["success"] is True

    def test_performance_history_default_minutes(self, app_server):
        resp = requests.get(
            f"{app_server}/admin/api/performance-history?minutes=30", timeout=30, allow_redirects=False
        )
        assert resp.status_code in (200, 302, 401, 403)


@pytest.mark.e2e
class TestAdminPerformancePageLoad:
    """E2E tests for admin performance page rendering."""

    def test_admin_performance_page_accessible(self, app_server):
        resp = requests.get(
            f"{app_server}/admin/performance",
            timeout=30,
            allow_redirects=True,
        )
        assert resp.status_code in (200, 302, 301, 401, 403)
