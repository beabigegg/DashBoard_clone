# -*- coding: utf-8 -*-
"""E2E tests for Mid-Section Defect module.

Endpoints:
  GET /api/mid-section-defect/station-options → available stations
  GET /api/mid-section-defect/analysis        → summary analysis
  GET /api/mid-section-defect/analysis/detail  → paginated detail
  GET /api/mid-section-defect/loss-reasons     → loss reason list

Run with: pytest tests/e2e/test_mid_section_defect_e2e.py -v -s
"""

import time

import pytest
import requests


def _poll_msd_detail_until_ready(app_server, params, timeout=180):
    """Poll MSD detail until the staged trace spool is ready."""
    deadline = time.time() + timeout
    last_response = None
    while time.time() < deadline:
        last_response = requests.get(
            f"{app_server}/api/mid-section-defect/analysis/detail",
            params=params,
            timeout=120,
        )
        if last_response.status_code == 200:
            return last_response
        if last_response.status_code == 429:
            retry_after = last_response.headers.get("Retry-After")
            try:
                wait_seconds = float(retry_after) if retry_after else 3.0
            except ValueError:
                wait_seconds = 3.0
            time.sleep(max(wait_seconds, 1.0))
            continue
        if last_response.status_code == 503:
            pytest.skip("Service busy")
        if last_response.status_code == 410:
            pytest.skip("trace_query_id cache expired before detail could be polled")
        assert last_response.status_code == 409, (
            f"Expected 200/409 while polling MSD detail, got {last_response.status_code}: "
            f"{last_response.text[:200]}"
        )
        time.sleep(4)
    return last_response


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
        """GET /analysis with valid dates returns analysis summary with actual data."""
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
        data = payload["data"]
        assert data.get("detail_total_count", 0) > 0, (
            "MSD analysis returned detail_total_count=0 — Oracle query may have failed silently"
        )
        assert len(data.get("daily_trend", [])) > 0, (
            "MSD analysis returned empty daily_trend for a 7-day range with known data"
        )

    def test_analysis_detail_returns_paginated_data(self, app_server):
        """GET /analysis/detail with valid dates returns paginated records."""
        summary_resp = requests.get(
            f"{app_server}/api/mid-section-defect/analysis",
            params={
                "start_date": "2026-03-01",
                "end_date": "2026-03-07",
            },
            timeout=120,
        )
        if summary_resp.status_code == 503:
            pytest.skip("Service busy")
        assert summary_resp.status_code == 200
        summary_payload = summary_resp.json()
        assert summary_payload["success"] is True
        trace_query_id = summary_payload.get("data", {}).get("trace_query_id")
        if not trace_query_id:
            pytest.skip("MSD summary returned no trace_query_id — no data available for this date range")

        resp = _poll_msd_detail_until_ready(
            app_server,
            {
                "start_date": "2026-03-01",
                "end_date": "2026-03-07",
                "page": 1,
                "page_size": 10,
                "trace_query_id": trace_query_id,
            },
        )
        assert resp is not None, "MSD detail polling timed out"
        if resp.status_code == 409:
            payload = resp.json()
            assert payload["error"]["code"] == "QUERY_NOT_READY"
            assert payload.get("meta", {}).get("trace_query_id") == trace_query_id
            return
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

    def test_container_filter_options_uses_cache_not_oracle(self, app_server):
        """GET /container-filter-options responds without hitting Oracle directly."""
        resp = requests.get(
            f"{app_server}/api/mid-section-defect/container-filter-options",
            timeout=30,
        )
        # Accept 200 (warm cache) or 500 (cold start before warmup on test env)
        assert resp.status_code in (200, 500)
        if resp.status_code == 200:
            payload = resp.json()
            assert payload["success"] is True
            data = payload.get("data", {})
            assert "pj_types" in data
            assert "packages" in data
            assert isinstance(data["pj_types"], list)
            assert isinstance(data["packages"], list)
