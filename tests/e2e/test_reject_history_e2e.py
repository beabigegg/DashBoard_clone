# -*- coding: utf-8 -*-
"""E2E tests for reject-history long-range query flow."""

from __future__ import annotations

import os
import time

import pytest
import requests
from playwright.sync_api import Page, expect

from tests.e2e.browser_helpers import goto_shell_route, wait_for_any_visible


def _post_reject_query(
    app_server: str,
    body: dict,
    timeout: float = 420.0,
    *,
    max_attempts: int = 4,
) -> requests.Response:
    """POST reject query and retry transient overload responses."""
    response = None
    for attempt in range(max_attempts):
        response = requests.post(
            f"{app_server}/api/reject-history/query",
            json=body,
            timeout=timeout,
        )
        if response.status_code != 503:
            return response
        payload = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
        if payload.get("code") != "SERVICE_UNAVAILABLE":
            return response
        if attempt >= max_attempts - 1:
            return response
        retry_after = response.headers.get("Retry-After")
        try:
            wait_seconds = float(retry_after) if retry_after else 2.0
        except ValueError:
            wait_seconds = 2.0
        time.sleep(wait_seconds)
    return response


def _poll_async_job(app_server: str, job_id: str, timeout_seconds: float = 300.0) -> dict:
    """Poll async job until terminal state, return final status dict."""
    status_url = f"{app_server}/api/reject-history/job/{job_id}"
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        resp = requests.get(status_url, timeout=30)
        assert resp.status_code == 200, f"Job status returned {resp.status_code}: {resp.text[:300]}"
        payload = resp.json()
        status = payload.get("data", payload)
        if status.get("status") in ("completed", "finished", "failed"):
            return status
        time.sleep(3)
    pytest.fail(f"Job {job_id} did not reach terminal state within {timeout_seconds}s")


def _query_and_wait(app_server: str, body: dict) -> str:
    """POST query, handle both sync 200 and async 202, return query_id."""
    query_resp = _post_reject_query(app_server, body)
    query_payload = query_resp.json()
    assert query_payload.get("success") is True, query_payload

    if query_resp.status_code == 200:
        query_id = query_payload.get("data", {}).get("query_id")
        assert query_id, f"Sync 200 response missing query_id: {query_payload}"
        return query_id

    if query_resp.status_code == 202:
        data = query_payload.get("data", query_payload)
        job_id = data.get("job_id")
        query_id = data.get("query_id")
        assert job_id, f"Async 202 response missing job_id: {query_payload}"
        assert query_id, f"Async 202 response missing query_id: {query_payload}"

        final = _poll_async_job(app_server, job_id)
        assert final.get("status") in ("completed", "finished"), (
            f"Async job failed: {final}"
        )
        return query_id

    pytest.fail(
        f"Unexpected status {query_resp.status_code}: {query_resp.text[:500]}"
    )


@pytest.mark.e2e
class TestRejectHistoryBasicE2E:
    """Basic E2E tests for reject-history endpoints (always run)."""

    def test_options_returns_filter_data(self, app_server: str):
        """GET /options returns filter options."""
        resp = requests.get(f"{app_server}/api/reject-history/options", timeout=30)
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["success"] is True

    def test_query_requires_mode(self, app_server: str):
        """POST /query without mode returns 400."""
        resp = requests.post(
            f"{app_server}/api/reject-history/query", json={}, timeout=30
        )
        assert resp.status_code == 400
        assert resp.json()["success"] is False

    def test_query_date_range_requires_dates(self, app_server: str):
        """POST /query with mode=date_range but no dates returns 400."""
        resp = requests.post(
            f"{app_server}/api/reject-history/query",
            json={"mode": "date_range"},
            timeout=30,
        )
        assert resp.status_code == 400

    def test_view_requires_query_id(self, app_server: str):
        """GET /view without query_id returns 400."""
        resp = requests.get(f"{app_server}/api/reject-history/view", timeout=30)
        assert resp.status_code == 400

    def test_view_expired_returns_410(self, app_server: str):
        """GET /view with nonexistent query_id returns 410."""
        resp = requests.get(
            f"{app_server}/api/reject-history/view",
            params={"query_id": "nonexistent-expired-id"},
            timeout=30,
        )
        assert resp.status_code == 410
        payload = resp.json()
        assert payload["success"] is False

    def test_short_range_query_view_cycle(self, app_server: str):
        """POST /query + GET /view for a short date range (7 days)."""
        query_resp = _post_reject_query(
            app_server,
            {
                "mode": "date_range",
                "start_date": "2026-03-01",
                "end_date": "2026-03-07",
            },
            timeout=120,
        )
        if query_resp.status_code == 503:
            pytest.skip("Service busy")
        payload = query_resp.json()
        assert payload.get("success") is True, payload

        # Extract query_id regardless of sync/async
        if query_resp.status_code == 202:
            data = payload.get("data", payload)
            job_id = data.get("job_id")
            if job_id:
                final = _poll_async_job(app_server, job_id, timeout_seconds=120)
                assert final.get("status") in ("completed", "finished")
            query_id = data.get("query_id")
        else:
            query_id = payload.get("query_id") or payload.get("data", {}).get("query_id")

        assert query_id, f"No query_id: {payload}"

        view_resp = requests.get(
            f"{app_server}/api/reject-history/view",
            params={"query_id": query_id, "page": 1, "per_page": 10},
            timeout=60,
        )
        assert view_resp.status_code == 200
        view_payload = view_resp.json()
        assert view_payload["success"] is True
        view_data = view_payload["data"]
        assert view_data.get("total_row_count", 0) > 0, (
            "Reject history view returned 0 total_row_count — Oracle query may have failed silently"
        )
        assert len(view_data.get("detail", {}).get("items", [])) > 0, (
            "Reject history view detail.items is empty despite non-zero total_row_count"
        )

    def test_summary_returns_data(self, app_server: str):
        """GET /summary (query_id) returns reject summary KPIs with non-zero values."""
        query_id = _query_and_wait(
            app_server,
            {"mode": "date_range", "start_date": "2026-03-01", "end_date": "2026-03-07"},
        )
        resp = requests.get(
            f"{app_server}/api/reject-history/summary",
            params={"query_id": query_id},
            timeout=60,
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["success"] is True
        data = payload["data"]
        assert (data.get("REJECT_TOTAL_QTY", 0) > 0 or data.get("DEFECT_QTY", 0) > 0), (
            f"Reject history summary returned all-zero KPIs — Oracle may have failed silently "
            f"(data: {data})"
        )

    def test_trend_returns_data(self, app_server: str):
        """GET /trend (query_id) returns reject trend with data points."""
        query_id = _query_and_wait(
            app_server,
            {"mode": "date_range", "start_date": "2026-03-01", "end_date": "2026-03-07"},
        )
        resp = requests.get(
            f"{app_server}/api/reject-history/trend",
            params={"query_id": query_id},
            timeout=60,
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["success"] is True
        items = payload["data"].get("items", [])
        assert len(items) > 0, "Reject history trend returned no data points for a 7-day range with known data"

    def test_reason_pareto_returns_data(self, app_server: str):
        """GET /reason-pareto (query_id) returns pareto analysis (empty valid if no reason data)."""
        query_id = _query_and_wait(
            app_server,
            {"mode": "date_range", "start_date": "2026-03-01", "end_date": "2026-03-07"},
        )
        resp = requests.get(
            f"{app_server}/api/reject-history/reason-pareto",
            params={"query_id": query_id},
            timeout=60,
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["success"] is True
        data = payload["data"]
        assert isinstance(data.get("items", []), list), "reason-pareto items should be a list"
        # Note: items may legitimately be empty if no reason codes are assigned in this period

    def test_list_returns_paginated_data(self, app_server: str):
        """GET /list (query_id) returns paginated reject records with actual rows."""
        query_id = _query_and_wait(
            app_server,
            {"mode": "date_range", "start_date": "2026-03-01", "end_date": "2026-03-07"},
        )
        resp = requests.get(
            f"{app_server}/api/reject-history/list",
            params={"query_id": query_id, "page": 1, "per_page": 10},
            timeout=60,
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["success"] is True
        data = payload["data"]
        assert len(data.get("items", [])) > 0, "Reject history list returned empty items for known date range"
        assert data.get("pagination", {}).get("total", 0) > 0, "Reject history pagination.total is 0"


@pytest.mark.e2e
@pytest.mark.skipif(
    os.environ.get("RUN_LONG_E2E") != "1",
    reason="Long-range reject-history E2E disabled; set RUN_LONG_E2E=1 to run.",
)
class TestRejectHistoryLongRangeE2E:
    """Real backend E2E checks for long-range reject history query."""

    def test_query_190_day_range_respects_guardrail(self, app_server: str):
        response = _post_reject_query(
            app_server,
            {
                "mode": "date_range",
                "start_date": "2025-01-01",
                "end_date": "2025-07-09",
                "include_excluded_scrap": False,
                "exclude_material_scrap": True,
                "exclude_pb_diode": True,
            },
        )

        if response.status_code == 200:
            payload = response.json()
            assert payload.get("success") is True, payload
            assert payload.get("query_id")
            return

        if response.status_code == 202:
            payload = response.json()
            assert payload.get("success") is True, payload
            data = payload.get("data", payload)
            assert data.get("job_id"), "202 response missing job_id"
            return

        assert response.status_code == 503, response.text[:500]
        payload = response.json()
        assert payload.get("code") == "RESULT_TOO_LARGE", payload

    def test_query_then_view_returns_cached_result(self, app_server: str):
        query_id = _query_and_wait(
            app_server,
            {
                "mode": "date_range",
                "start_date": "2025-02-01",
                "end_date": "2025-02-28",
                "exclude_material_scrap": True,
                "exclude_pb_diode": True,
            },
        )

        view_resp = requests.get(
            f"{app_server}/api/reject-history/view",
            params={
                "query_id": query_id,
                "page": 1,
                "per_page": 50,
                "exclude_material_scrap": "true",
                "exclude_pb_diode": "true",
            },
            timeout=120,
        )
        assert view_resp.status_code == 200, view_resp.text[:500]
        view_payload = view_resp.json()
        assert view_payload.get("success") is True, view_payload

    def test_query_then_export_cached_returns_csv(self, app_server: str):
        query_id = _query_and_wait(
            app_server,
            {
                "mode": "date_range",
                "start_date": "2025-02-01",
                "end_date": "2025-02-28",
                "exclude_material_scrap": True,
                "exclude_pb_diode": True,
            },
        )

        export_resp = requests.get(
            f"{app_server}/api/reject-history/export-cached",
            params={"query_id": query_id},
            timeout=120,
        )
        assert export_resp.status_code == 200, export_resp.text[:300]
        assert "text/csv" in export_resp.headers.get("Content-Type", "")
        assert "LOT" in export_resp.text[:200]


@pytest.mark.e2e
class TestRejectHistoryBrowserE2E:
    """Browser E2E for reject-history primary workflow."""

    def test_reject_history_page_runs_primary_query(self, page: Page, app_server: str):
        preflight = _post_reject_query(
            app_server,
            {
                "mode": "date_range",
                "start_date": "2026-03-01",
                "end_date": "2026-03-07",
            },
            timeout=120,
            max_attempts=1,
        )
        if preflight.status_code == 503:
            pytest.skip("reject-history service busy")

        goto_shell_route(page, app_server, "/reject-history", "報廢歷史查詢")
        # reject-history imports PageHeader but never renders it — no
        # page-title heading exists; "報廢歷史查詢" is only the sidebar link text.
        query_button = page.locator(".filter-panel .ui-btn--primary").first
        expect(query_button).to_be_enabled(timeout=60000)
        query_button.click()

        wait_for_any_visible(
            page,
            [
                "text=明細列表",
                ".async-job-status-bar",
                ".warning-banner",
            ],
            timeout_ms=180000,
        )

        if page.locator(".async-job-status-bar").count() > 0:
            expect(page.locator("text=明細列表")).to_be_visible(timeout=180000)
        else:
            expect(page.locator("text=明細列表")).to_be_visible()
