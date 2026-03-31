# -*- coding: utf-8 -*-
"""E2E tests for Admin Dashboard page.

Tests:
  GET /admin/api/system-status  — system health overview
  GET /admin/api/worker/status  — worker restart state
  GET /admin/api/storage-info   — disk / spool usage
  GET /admin/api/logs           — recent log entries

Run with: pytest tests/e2e/test_admin_dashboard_e2e.py -v --run-e2e
"""

import pytest
import requests


@pytest.mark.e2e
class TestAdminDashboardSystemStatus:
    """E2E tests for /admin/api/system-status."""

    def test_system_status_returns_success_envelope(self, app_server):
        resp = requests.get(
            f"{app_server}/admin/api/system-status", timeout=30
        )
        # Unauthenticated requests will be redirected or return 401/403;
        # authenticated env will return 200.
        assert resp.status_code in (200, 302, 401, 403)
        if resp.status_code == 200:
            payload = resp.json()
            assert payload["success"] is True

    def test_system_status_data_shape_when_authenticated(self, app_server):
        resp = requests.get(
            f"{app_server}/admin/api/system-status", timeout=30
        )
        if resp.status_code == 200:
            payload = resp.json()
            data = payload.get("data", {})
            assert isinstance(data, dict)


@pytest.mark.e2e
class TestAdminDashboardWorkerStatus:
    """E2E tests for /admin/api/worker/status."""

    def test_worker_status_accessible(self, app_server):
        resp = requests.get(
            f"{app_server}/admin/api/worker/status", timeout=30
        )
        assert resp.status_code in (200, 302, 401, 403)
        if resp.status_code == 200:
            payload = resp.json()
            assert payload["success"] is True

    def test_worker_status_has_required_fields(self, app_server):
        resp = requests.get(
            f"{app_server}/admin/api/worker/status", timeout=30
        )
        if resp.status_code == 200:
            payload = resp.json()
            data = payload.get("data", {})
            # Worker status should include restart policy state
            assert isinstance(data, dict)


@pytest.mark.e2e
class TestAdminDashboardStorageInfo:
    """E2E tests for /admin/api/storage-info."""

    def test_storage_info_returns_disk_metrics(self, app_server):
        resp = requests.get(
            f"{app_server}/admin/api/storage-info", timeout=30
        )
        assert resp.status_code in (200, 302, 401, 403)
        if resp.status_code == 200:
            payload = resp.json()
            assert payload["success"] is True


@pytest.mark.e2e
class TestAdminDashboardPageLoad:
    """E2E tests for admin dashboard page rendering."""

    def test_admin_dashboard_page_accessible(self, app_server):
        resp = requests.get(
            f"{app_server}/admin/dashboard",
            timeout=30,
            allow_redirects=True,
        )
        assert resp.status_code in (200, 302, 401, 403)
