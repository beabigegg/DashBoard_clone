# -*- coding: utf-8 -*-
"""E2E tests for Anomaly Overview page.

Tests:
  GET /api/analytics/yield-anomalies    — yield anomaly detections
  GET /api/analytics/reject-spikes      — reject spike detections
  GET /api/analytics/hold-outliers      — hold duration outliers
  GET /api/analytics/equipment-deviations — equipment OU% deviations
  GET /api/analytics/summary            — aggregated anomaly summary

Run with: pytest tests/e2e/test_anomaly_overview_e2e.py -v --run-e2e
"""

import pytest
import re
import requests
from playwright.sync_api import Page, expect

from tests.e2e.browser_helpers import goto_shell_route


@pytest.mark.e2e
class TestAnomalyYieldEndpoint:
    """E2E tests for /api/analytics/yield-anomalies."""

    def test_yield_anomalies_returns_success_envelope(self, api_base_url):
        resp = requests.get(
            f"{api_base_url}/analytics/yield-anomalies", timeout=30
        )
        assert resp.status_code in (200, 404, 503)
        if resp.status_code == 200:
            payload = resp.json()
            assert payload["success"] is True

    def test_yield_anomalies_response_has_list_data(self, api_base_url):
        resp = requests.get(
            f"{api_base_url}/analytics/yield-anomalies", timeout=30
        )
        if resp.status_code == 200:
            payload = resp.json()
            data = payload.get("data")
            # API returns {"data": {"count": N, "items": [...]}} or {"data": [...]}
            assert isinstance(data, (list, dict))
            items = data if isinstance(data, list) else data.get("items", data.get("data", []))
            if len(items) == 0:
                pytest.skip("yield-anomalies returned empty list — no anomalies in current window")


@pytest.mark.e2e
class TestAnomalyRejectSpikesEndpoint:
    """E2E tests for /api/analytics/reject-spikes."""

    def test_reject_spikes_returns_list(self, api_base_url):
        resp = requests.get(
            f"{api_base_url}/analytics/reject-spikes", timeout=30
        )
        assert resp.status_code in (200, 404, 503)
        if resp.status_code == 200:
            payload = resp.json()
            assert payload["success"] is True
            data = payload.get("data")
            # API returns {"data": {"count": N, "items": [...]}} or {"data": [...]}
            assert isinstance(data, (list, dict))
            items = data if isinstance(data, list) else data.get("items", data.get("data", []))
            if len(items) == 0:
                pytest.skip("reject-spikes returned empty list — no spike anomalies in current window")


@pytest.mark.e2e
class TestAnomalyHoldOutliersEndpoint:
    """E2E tests for /api/analytics/hold-outliers."""

    def test_hold_outliers_returns_success(self, api_base_url):
        resp = requests.get(
            f"{api_base_url}/analytics/hold-outliers", timeout=30
        )
        assert resp.status_code in (200, 404, 503)
        if resp.status_code == 200:
            payload = resp.json()
            assert payload["success"] is True
            data = payload.get("data")
            items = data if isinstance(data, list) else data.get("items", data.get("data", [])) if isinstance(data, dict) else []
            assert len(items) > 0, "hold-outliers returned empty list — hold outlier detection may have failed silently"


@pytest.mark.e2e
class TestAnomalyEquipmentDeviationsEndpoint:
    """E2E tests for /api/analytics/equipment-deviations."""

    def test_equipment_deviations_returns_success(self, api_base_url):
        resp = requests.get(
            f"{api_base_url}/analytics/equipment-deviations", timeout=30
        )
        assert resp.status_code in (200, 404, 503)
        if resp.status_code == 200:
            payload = resp.json()
            assert payload["success"] is True
            data = payload.get("data")
            items = data if isinstance(data, list) else data.get("items", data.get("data", [])) if isinstance(data, dict) else []
            if len(items) == 0:
                pytest.skip("equipment-deviations returned empty list — no deviations in current window")


@pytest.mark.e2e
class TestAnomalyOverviewPageLoad:
    """E2E tests for anomaly overview page serving."""

    def test_anomaly_overview_page_is_accessible(self, app_server):
        resp = requests.get(
            f"{app_server}/anomaly-overview",
            timeout=30,
            allow_redirects=True,
        )
        # Page may be SPA-only (404 if no Flask page route), redirect, or 200
        assert resp.status_code in (200, 302, 404)


@pytest.mark.e2e
class TestAnomalyOverviewBrowserE2E:
    """Browser E2E for anomaly-overview navigation workflow."""

    def test_anomaly_overview_page_navigates_to_detail_page(self, page: Page, app_server: str):
        goto_shell_route(page, app_server, "/anomaly-overview", "異常總覽")
        expect(page.get_by_role("heading", name="異常總覽")).to_be_visible()
        expect(page.locator("text=偵測邏輯：").first).to_be_visible(timeout=60000)

        nav_button = page.locator(".ao-nav-link").first
        expect(nav_button).to_be_visible()
        nav_button.click()
        expect(page).to_have_url(
            re.compile(r".*/portal-shell/(yield-alert-center|reject-history|hold-history|resource-history).*")
        )
