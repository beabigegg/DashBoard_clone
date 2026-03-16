# -*- coding: utf-8 -*-
"""E2E tests for Mid-Section Defect module.

Endpoints:
  GET /api/mid-section-defect/station-options → available stations
  GET /api/mid-section-defect/analysis        → summary analysis
  GET /api/mid-section-defect/analysis/detail  → paginated detail
  GET /api/mid-section-defect/loss-reasons     → loss reason list

Run with: pytest tests/e2e/test_mid_section_defect_e2e.py -v -s
"""

import pytest
import requests


@pytest.mark.e2e
class TestMidSectionDefectE2E:
    """E2E tests for Mid-Section Defect endpoints."""

    def test_station_options_returns_list(self, app_server):
        """GET /station-options returns available stations."""
        resp = requests.get(
            f"{app_server}/api/mid-section-defect/station-options", timeout=30
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["success"] is True

    def test_loss_reasons_returns_list(self, app_server):
        """GET /loss-reasons returns all loss reason codes."""
        resp = requests.get(
            f"{app_server}/api/mid-section-defect/loss-reasons", timeout=30
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["success"] is True

    def test_analysis_requires_dates(self, app_server):
        """GET /analysis without dates returns 400."""
        resp = requests.get(
            f"{app_server}/api/mid-section-defect/analysis", timeout=30
        )
        assert resp.status_code == 400

    def test_analysis_returns_data(self, app_server):
        """GET /analysis with valid dates returns analysis summary."""
        resp = requests.get(
            f"{app_server}/api/mid-section-defect/analysis",
            params={"start_date": "2026-03-01", "end_date": "2026-03-07"},
            timeout=120,
        )
        # May return 200 or 503 if system is busy
        if resp.status_code == 503:
            pytest.skip("Service busy")
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["success"] is True

    def test_analysis_detail_returns_paginated_data(self, app_server):
        """GET /analysis/detail with valid dates returns paginated records."""
        resp = requests.get(
            f"{app_server}/api/mid-section-defect/analysis/detail",
            params={
                "start_date": "2026-03-01",
                "end_date": "2026-03-07",
                "page": 1,
                "page_size": 10,
            },
            timeout=120,
        )
        if resp.status_code == 503:
            pytest.skip("Service busy")
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["success"] is True

    def test_analysis_rejects_over_730_day_range(self, app_server):
        """GET /analysis with >730-day range returns 400."""
        resp = requests.get(
            f"{app_server}/api/mid-section-defect/analysis",
            params={"start_date": "2023-01-01", "end_date": "2025-02-28"},
            timeout=30,
        )
        assert resp.status_code == 400
        payload = resp.json()
        assert "730" in payload.get("error", {}).get("message", "")
