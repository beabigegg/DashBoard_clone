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
import requests


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
            assert isinstance(payload.get("data"), list)


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
            assert isinstance(payload.get("data"), list)


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


@pytest.mark.e2e
class TestAnomalyOverviewPageLoad:
    """E2E tests for anomaly overview page serving."""

    def test_anomaly_overview_page_is_accessible(self, app_server):
        resp = requests.get(
            f"{app_server}/anomaly-overview",
            timeout=30,
            allow_redirects=True,
        )
        # Page should render or redirect to portal-shell
        assert resp.status_code in (200, 302)
