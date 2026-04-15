# -*- coding: utf-8 -*-
"""E2E tests for page query race condition fixes.

Tests verify:
  A: yield-alert-center — RQ Job polling stops after SPA navigate away
  B: reject-history     — RQ Job polling stops after SPA navigate away
  C: production-history — loading guard prevents duplicate requests on rapid clicks

Run with:
  conda run -n mes-dashboard pytest tests/e2e/test_query_race_condition_e2e.py -v -s --timeout=180
"""

import json

import pytest
from playwright.sync_api import Page

from tests.e2e.browser_helpers import ensure_shell_admin, goto_shell_route

# Must match useAsyncJobPolling.js JOB_POLL_INTERVAL_MS
POLL_INTERVAL_MS = 3000

# How long to wait after navigate to verify no new poll requests (> 1 poll cycle)
POLL_VERIFY_WAIT_MS = POLL_INTERVAL_MS + 1500


def _fulfill_job_running(route):
    """Mock a job status endpoint to always return 'running' (never completes)."""
    route.fulfill(
        status=200,
        content_type="application/json",
        body=json.dumps(
            {"success": True, "data": {"status": "running", "progress": "50%", "pct": 50}}
        ),
    )


def _fulfill_async_job_accepted(job_id: str):
    """Return a 202 async-accepted response with the given job_id."""
    def handler(route):
        route.fulfill(
            status=202,
            content_type="application/json",
            body=json.dumps(
                {
                    "success": True,
                    "data": {"async": True, "job_id": job_id, "query_id": None},
                }
            ),
        )

    return handler


@pytest.mark.e2e
@pytest.mark.local_only
class TestYieldAlertPollingAbort:
    """Test A: yield-alert-center RQ Job polling stops when component is unmounted via SPA nav."""

    def test_polling_stops_after_spa_navigate_away(self, page: Page, app_server: str):
        """Navigate away from yield-alert-center via SPA router link — polling must stop."""
        # Pre-register destination route so both appear in the sidebar nav
        ensure_shell_admin(page, "/reject-history", "報廢歷史查詢")

        # Mock: query → 202 async accepted (starts polling)
        page.route(
            "**/api/yield-alert/query",
            _fulfill_async_job_accepted("yac-race-test-job"),
        )
        # Mock: filter-options → empty (page loads without real data)
        page.route(
            "**/api/yield-alert/filter-options",
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"success": True, "data": {"workcenter_groups": []}}),
            ),
        )
        # Mock: job status → always running (polling never self-terminates)
        page.route("**/api/yield-alert/job/**", _fulfill_job_running)

        # Navigate to yield-alert-center (both routes registered → both appear in sidebar)
        goto_shell_route(page, app_server, "/yield-alert-center", "Yield Alert Center")

        # Wait for page mount; setDefaultDateRange() sets dates → canSubmit = true
        page.wait_for_timeout(2000)

        # Click the primary query button to start a query (and polling)
        query_btn = page.locator(
            ".filter-panel.primary-query-panel button.ui-btn--primary"
        ).first
        query_btn.wait_for(state="visible", timeout=10000)
        query_btn.click()

        # Wait at least 1 poll cycle to confirm polling is running
        page.wait_for_timeout(POLL_INTERVAL_MS + 500)

        # SPA navigate away via Vue Router push (bypasses the page-level LoadingOverlay
        # that blocks pointer events on the sidebar while a query is in-flight).
        page.evaluate(
            "document.querySelector('#app')?.__vue_app__"
            "?.config.globalProperties.$router.push('/reject-history')"
        )

        # Wait for navigation to settle and onUnmounted to fire (→ abort() called)
        page.wait_for_timeout(1000)

        # --- From here, count new requests to the job status endpoint ---
        job_requests_after_nav: list[str] = []

        def _on_request(req):
            if "/api/yield-alert/job/" in req.url:
                job_requests_after_nav.append(req.url)

        page.on("request", _on_request)

        # Wait longer than one poll interval
        page.wait_for_timeout(POLL_VERIFY_WAIT_MS)

        assert len(job_requests_after_nav) == 0, (
            f"yield-alert-center: {len(job_requests_after_nav)} job poll request(s) made "
            f"after SPA navigate away — _jobAbortController?.abort() in onUnmounted may not be working"
        )


@pytest.mark.e2e
@pytest.mark.local_only
class TestRejectHistoryPollingAbort:
    """Test B: reject-history RQ Job polling stops when component is unmounted via SPA nav."""

    def test_polling_stops_after_spa_navigate_away(self, page: Page, app_server: str):
        """Navigate away from reject-history via SPA router link — polling must stop."""
        # Pre-register destination route so both appear in the sidebar
        ensure_shell_admin(page, "/yield-alert-center", "Yield Alert Center")

        # Mock: query → 202 async accepted
        page.route(
            "**/api/reject-history/query",
            _fulfill_async_job_accepted("rh-race-test-job"),
        )
        # Mock: options → empty (page loads without real data)
        page.route(
            "**/api/reject-history/options",
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(
                    {
                        "success": True,
                        "data": {
                            "work_orders": [],
                            "lot_ids": [],
                            "packages": [],
                            "bop_codes": [],
                            "workcenter_groups": [],
                        },
                    }
                ),
            ),
        )
        # Mock: job status → always running
        page.route("**/api/reject-history/job/**", _fulfill_job_running)

        # Navigate to reject-history (both routes registered)
        goto_shell_route(page, app_server, "/reject-history", "報廢歷史查詢")

        # Wait for page mount and default date range to be set
        page.wait_for_timeout(2000)

        # Click the primary query button (inside FilterPanel component)
        query_btn = page.locator("button.ui-btn--primary").first
        query_btn.wait_for(state="visible", timeout=10000)
        query_btn.click()

        # Wait at least 1 poll cycle to confirm polling is running
        page.wait_for_timeout(POLL_INTERVAL_MS + 500)

        # SPA navigate away via Vue Router push (bypasses the page-level LoadingOverlay
        # that blocks pointer events on the sidebar while a query is in-flight).
        page.evaluate(
            "document.querySelector('#app')?.__vue_app__"
            "?.config.globalProperties.$router.push('/yield-alert-center')"
        )

        # Wait for navigation to settle and onUnmounted to fire (→ abort() called)
        page.wait_for_timeout(1000)

        # --- From here, count new requests to the job status endpoint ---
        job_requests_after_nav: list[str] = []

        def _on_request(req):
            if "/api/reject-history/job/" in req.url:
                job_requests_after_nav.append(req.url)

        page.on("request", _on_request)

        # Wait longer than one poll interval
        page.wait_for_timeout(POLL_VERIFY_WAIT_MS)

        assert len(job_requests_after_nav) == 0, (
            f"reject-history: {len(job_requests_after_nav)} job poll request(s) made "
            f"after SPA navigate away — _jobAbortController?.abort() in onUnmounted may not be working"
        )


@pytest.mark.e2e
@pytest.mark.local_only
class TestProductionHistoryLoadingGuard:
    """Test C: production-history loading guard prevents duplicate requests on rapid clicks."""

    def test_rapid_clicks_produce_at_most_one_inflight_request(
        self, page: Page, app_server: str
    ):
        """Clicking the query button while a query is in-flight must not send additional requests."""
        query_request_count = [0]
        max_concurrent = [0]
        inflight = [0]

        def handle_slow_query(route):
            query_request_count[0] += 1
            inflight[0] += 1
            if inflight[0] > max_concurrent[0]:
                max_concurrent[0] = inflight[0]
            # Simulate slow query: delay response (never actually finishes during test)
            # Playwright's route.fulfill blocks the response; use a long timeout
            route.fulfill(
                status=202,
                content_type="application/json",
                body=json.dumps(
                    {
                        "success": True,
                        "data": {
                            "async": True,
                            "job_id": "ph-race-test-job",
                            "query_id": None,
                        },
                    }
                ),
            )
            inflight[0] -= 1

        # Mock: query endpoint (slow response handled above)
        page.route("**/api/production-history/query", handle_slow_query)
        # Mock: job status → always running (so loading stays true)
        page.route("**/api/production-history/job/**", _fulfill_job_running)
        # Mock: type-options → return one option so the form validates
        page.route(
            "**/api/production-history/type-options",
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(
                    {"success": True, "data": {"items": ["TEST_TYPE"]}}
                ),
            ),
        )

        # Navigate to production-history
        goto_shell_route(page, app_server, "/production-history", "生產歷程查詢")
        page.wait_for_timeout(2000)

        # Select type from MultiSelect (click trigger, then click first option)
        ms_trigger = page.locator(".multi-select-trigger").first
        ms_trigger.wait_for(state="visible", timeout=10000)
        ms_trigger.click()
        page.wait_for_timeout(500)
        first_option = page.locator(".multi-select-option").first
        first_option.wait_for(state="visible", timeout=5000)
        first_option.click()
        ms_trigger.click()  # close dropdown

        # First click: query starts, loading = true
        query_btn = page.locator("button.ui-btn--primary:has-text('查詢')").first
        query_btn.wait_for(state="visible", timeout=10000)
        query_btn.click()

        # Rapid additional click attempts (should be blocked by loading guard / disabled button)
        for _ in range(4):
            query_btn.click(force=True)  # force=True bypasses disabled state check
            page.wait_for_timeout(50)

        # Wait for any pending network activity
        page.wait_for_timeout(1000)

        assert query_request_count[0] == 1, (
            f"production-history: {query_request_count[0]} query requests made during rapid clicks "
            f"(expected exactly 1) — loading guard may not be working"
        )
        assert max_concurrent[0] <= 1, (
            f"production-history: max {max_concurrent[0]} concurrent in-flight requests detected "
            f"(expected ≤ 1)"
        )
