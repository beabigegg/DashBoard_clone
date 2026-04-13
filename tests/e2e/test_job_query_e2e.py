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
from playwright.sync_api import Page, expect

from tests.e2e.browser_helpers import goto_shell_route, wait_for_any_visible


@pytest.mark.e2e
class TestJobQueryE2E:
    """E2E tests for Job Query endpoints."""

    def test_resources_returns_list(self, app_server):
        """GET /resources returns available equipment list with actual items."""
        resp = requests.get(f"{app_server}/api/job-query/resources", timeout=30)
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["success"] is True
        assert isinstance(payload["data"], dict)
        resources = payload["data"].get("data", [])
        assert len(resources) > 0, "Job query resources returned empty list — resource cache may be empty or Oracle failed"

    def test_jobs_requires_params(self, app_server):
        """POST /jobs without required params returns 400."""
        resp = requests.post(
            f"{app_server}/api/job-query/jobs", json={}, timeout=30
        )
        assert resp.status_code == 400

    def test_jobs_returns_data_with_valid_params(self, app_server):
        """POST /jobs with valid params returns job data (tries multiple resources to find one with jobs)."""
        res_resp = requests.get(f"{app_server}/api/job-query/resources", timeout=30)
        if res_resp.status_code != 200:
            pytest.skip("Cannot discover resources")
        resources = res_resp.json().get("data", {}).get("data", [])
        if not resources:
            pytest.skip("No resources available")

        # Try up to 10 resources until we find one with jobs in the date range
        found_jobs = False
        for resource in resources[:10]:
            resource_id = str(resource.get("RESOURCEID", ""))
            if not resource_id:
                continue
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
            if payload["data"].get("total", 0) > 0:
                found_jobs = True
                assert len(payload["data"].get("data", [])) > 0, (
                    "job-query jobs total > 0 but data list is empty — API format mismatch"
                )
                break

        if not found_jobs:
            pytest.skip("No jobs found for first 10 resources in 2026-03-01 ~ 2026-03-07")

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


@pytest.mark.e2e
class TestJobQueryBrowserE2E:
    """Browser E2E for the job-query page workflow."""

    def test_job_query_page_restores_url_and_runs_query(self, page: Page, app_server: str):
        res_resp = requests.get(f"{app_server}/api/job-query/resources", timeout=30)
        if res_resp.status_code != 200:
            pytest.skip("Cannot discover job-query resources")
        resources = res_resp.json().get("data", {}).get("data", [])
        if not resources:
            pytest.skip("No job-query resources available")

        resource_id = str(resources[0].get("RESOURCEID", "")).strip()
        if not resource_id:
            pytest.skip("No RESOURCEID available for browser workflow")

        goto_shell_route(
            page,
            app_server,
            "/job-query",
            "設備維修查詢",
            resource_ids=resource_id,
            start_date="2026-03-01",
            end_date="2026-03-07",
        )
        expect(page.get_by_role("heading", name="設備維修查詢")).to_be_visible()
        expect(page.locator("text=已選設備：1")).to_be_visible(timeout=60000)

        wait_for_any_visible(
            page,
            [
                ".job-query-page .ui-table-wrap",
                "text=目前無資料",
                "text=維修紀錄",
            ],
            timeout_ms=120000,
        )
        expect(page.locator("text=維修紀錄")).to_be_visible()
