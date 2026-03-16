# -*- coding: utf-8 -*-
"""E2E tests for Job Query module.

Endpoints:
  GET  /api/job-query/resources → equipment list
  POST /api/job-query/jobs      → query jobs
  GET  /api/job-query/txn/<id>  → job transactions

Run with: pytest tests/e2e/test_job_query_e2e.py -v -s
"""

import pytest
import requests


@pytest.mark.e2e
class TestJobQueryE2E:
    """E2E tests for Job Query endpoints."""

    def test_resources_returns_list(self, app_server):
        """GET /resources returns available equipment list."""
        resp = requests.get(f"{app_server}/api/job-query/resources", timeout=30)
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["success"] is True
        assert isinstance(payload["data"], dict)

    def test_jobs_requires_params(self, app_server):
        """POST /jobs without required params returns 400."""
        resp = requests.post(
            f"{app_server}/api/job-query/jobs", json={}, timeout=30
        )
        assert resp.status_code == 400

    def test_jobs_returns_data_with_valid_params(self, app_server):
        """POST /jobs with valid params returns job data."""
        # First discover a resource
        res_resp = requests.get(f"{app_server}/api/job-query/resources", timeout=30)
        if res_resp.status_code != 200:
            pytest.skip("Cannot discover resources")
        res_data = res_resp.json().get("data", {})
        resources = res_data.get("data", [])
        if not resources:
            pytest.skip("No resources available")

        resource_id = str(resources[0].get("RESOURCEID", ""))
        if not resource_id:
            pytest.skip("No RESOURCEID in first resource")

        resp = requests.post(
            f"{app_server}/api/job-query/jobs",
            json={
                "resource_ids": [resource_id],
                "start_date": "2026-03-01",
                "end_date": "2026-03-07",
            },
            timeout=60,
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["success"] is True

    def test_jobs_rejects_too_many_resources(self, app_server):
        """POST /jobs with >50 resource_ids returns 400."""
        resp = requests.post(
            f"{app_server}/api/job-query/jobs",
            json={
                "resource_ids": [f"RES-{i}" for i in range(51)],
                "start_date": "2026-03-01",
                "end_date": "2026-03-07",
            },
            timeout=30,
        )
        assert resp.status_code == 400

    def test_jobs_rejects_over_730_day_range(self, app_server):
        """POST /jobs with >730-day range returns 400."""
        resp = requests.post(
            f"{app_server}/api/job-query/jobs",
            json={
                "resource_ids": ["RES-1"],
                "start_date": "2023-01-01",
                "end_date": "2025-02-28",
            },
            timeout=30,
        )
        assert resp.status_code == 400
        payload = resp.json()
        assert "730" in payload.get("error", {}).get("message", "")
