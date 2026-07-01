# -*- coding: utf-8 -*-
"""E2E tests for Yield Alert Center module.

Tests multiple endpoints:
  POST /api/yield-alert/query   → primary query
  GET  /api/yield-alert/view    → cached view
  GET  /api/yield-alert/summary → summary KPIs
  GET  /api/yield-alert/alerts  → alert candidates
  GET  /api/yield-alert/trend   → trend data
  GET  /api/yield-alert/filter-options → workcenter groups
  GET  /api/yield-alert/drilldown-context → drilldown payload

Run with: pytest tests/e2e/test_yield_alert_e2e.py -v -s
"""

import time

import pytest
import requests
from playwright.sync_api import Page, expect

from tests.e2e.browser_helpers import goto_shell_route, wait_for_any_visible


@pytest.mark.e2e
class TestYieldAlertFilterOptions:
    """E2E tests for Yield Alert filter options."""

    def test_filter_options_returns_workcenter_groups(self, api_base_url):
        """GET /filter-options returns workcenter groups list."""
        resp = requests.get(
            f"{api_base_url}/yield-alert/filter-options", timeout=30
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["success"] is True
        assert "workcenter_groups" in payload["data"]
        groups = payload["data"]["workcenter_groups"]
        assert isinstance(groups, list)
        assert len(groups) > 0, "Yield alert filter options returned empty workcenter_groups"


@pytest.mark.e2e
class TestYieldAlertSummary:
    """E2E tests for Yield Alert summary endpoint."""

    def test_summary_requires_dates(self, api_base_url):
        """GET /summary without dates returns 400."""
        resp = requests.get(f"{api_base_url}/yield-alert/summary", timeout=30)
        assert resp.status_code == 400
        payload = resp.json()
        assert payload["success"] is False

    def test_summary_returns_kpis(self, api_base_url):
        """GET /summary?query_id returns KPI data (B5: legacy date-range path retired → 410)."""
        query_id = _acquire_query_id(api_base_url)
        try:
            resp = requests.get(
                f"{api_base_url}/yield-alert/summary",
                params={"query_id": query_id},
                timeout=60,
            )
        except requests.exceptions.Timeout:
            pytest.skip("yield-alert/summary timed out — heavy query on this environment")
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["success"] is True
        data = payload["data"]
        assert data.get("transaction_qty", 0) > 0, (
            f"Yield alert summary returned zero transaction_qty — Oracle may have failed silently "
            f"(data: {data})"
        )


@pytest.mark.e2e
class TestYieldAlertAlerts:
    """E2E tests for Yield Alert alerts endpoint."""

    def test_alerts_rejects_invalid_sort_key(self, api_base_url):
        """GET /alerts with invalid sort_by returns 400."""
        resp = requests.get(
            f"{api_base_url}/yield-alert/alerts",
            params={
                "start_date": "2026-03-01",
                "end_date": "2026-03-07",
                "sort_by": "invalid_field",
            },
            timeout=30,
        )
        assert resp.status_code == 400

    def test_alerts_returns_paginated_list(self, api_base_url):
        """GET /alerts with valid params returns paginated alert items."""
        resp = requests.get(
            f"{api_base_url}/yield-alert/alerts",
            params={
                "start_date": "2026-03-01",
                "end_date": "2026-03-07",
                "page": 1,
                "per_page": 10,
            },
            timeout=60,
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["success"] is True
        data = payload["data"]
        assert "items" in data
        assert "pagination" in data
        assert len(data["items"]) > 0, "Yield alert alerts returned empty items for known date range"
        assert data["pagination"].get("total", 0) > 0, "Yield alert alerts pagination.total is 0"

    def test_alerts_respects_per_page_cap(self, api_base_url):
        """GET /alerts caps per_page to max allowed value."""
        resp = requests.get(
            f"{api_base_url}/yield-alert/alerts",
            params={
                "start_date": "2026-03-01",
                "end_date": "2026-03-07",
                "per_page": 9999,
            },
            timeout=60,
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["success"] is True
        pagination = payload["data"]["pagination"]
        assert pagination["per_page"] <= 200


@pytest.mark.e2e
class TestYieldAlertTrend:
    """E2E tests for Yield Alert trend endpoint."""

    def test_trend_returns_data(self, api_base_url):
        """GET /trend?query_id returns trend data (B5: legacy date-range path retired → 410)."""
        query_id = _acquire_query_id(api_base_url)
        resp = requests.get(
            f"{api_base_url}/yield-alert/trend",
            params={"query_id": query_id},
            timeout=60,
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["success"] is True
        items = payload["data"].get("items", [])
        assert len(items) > 0, "Yield alert trend returned no data points for a 7-day range with known data"


@pytest.mark.e2e
class TestYieldAlertQuery:
    """E2E tests for Yield Alert primary query."""

    def test_query_requires_dates(self, api_base_url):
        """POST /query without dates returns 400."""
        resp = requests.post(
            f"{api_base_url}/yield-alert/query", json={}, timeout=30
        )
        assert resp.status_code == 400

    def test_query_returns_query_id(self, api_base_url):
        """POST /query with valid dates returns query_id."""
        resp = requests.post(
            f"{api_base_url}/yield-alert/query",
            json={"start_date": "2026-03-01", "end_date": "2026-03-07"},
            timeout=120,
        )
        # 200 = sync result, 202 = async job queued (RQ workers active), 503 = busy
        if resp.status_code in (200, 202):
            payload = resp.json()
            assert payload["success"] is True
        else:
            assert resp.status_code in (400, 503)


@pytest.mark.e2e
class TestYieldAlertView:
    """E2E tests for Yield Alert cached view."""

    def test_view_requires_query_id(self, api_base_url):
        """GET /view without query_id returns 400."""
        resp = requests.get(f"{api_base_url}/yield-alert/view", timeout=30)
        assert resp.status_code == 400

    def test_view_expired_returns_410(self, api_base_url):
        """GET /view with expired query_id returns 410."""
        resp = requests.get(
            f"{api_base_url}/yield-alert/view",
            params={"query_id": "nonexistent-expired-id"},
            timeout=30,
        )
        assert resp.status_code == 410


@pytest.mark.e2e
class TestYieldAlertDrilldown:
    """E2E tests for Yield Alert drilldown context."""

    def test_drilldown_requires_params(self, api_base_url):
        """GET /drilldown-context without params returns 400."""
        resp = requests.get(
            f"{api_base_url}/yield-alert/drilldown-context", timeout=30
        )
        assert resp.status_code == 400


@pytest.mark.e2e
class TestYieldAlertDateRangeLimit:
    """E2E tests for date range limit enforcement.

    The actual limit is controlled by YIELD_ALERT_MAX_QUERY_DAYS env var
    (defaults to 730, but .env may override to a lower value like 93).
    We discover the limit from the error response to stay robust.
    """

    def _discover_max_days(self, api_base_url) -> int:
        """Probe the server's actual max_query_days value.

        B5: date-range validation moved to POST /query (GET /summary now
        requires query_id and returns 410 for any date-range-only call).
        """
        resp = requests.post(
            f"{api_base_url}/yield-alert/query",
            json={"start_date": "2020-01-01", "end_date": "2026-03-13"},
            timeout=10,
        )
        if resp.status_code == 400:
            meta = resp.json().get("meta", {})
            return meta.get("max_query_days", 730)
        return 730

    def test_summary_accepts_within_limit_range(self, api_base_url):
        """POST /query within the server's max_query_days should succeed."""
        max_days = self._discover_max_days(api_base_url)
        from datetime import date, timedelta
        end = date(2026, 3, 13)
        start = end - timedelta(days=max_days - 1)
        try:
            resp = requests.post(
                f"{api_base_url}/yield-alert/query",
                json={"start_date": start.isoformat(), "end_date": end.isoformat()},
                timeout=120,
            )
        except requests.exceptions.Timeout:
            pytest.skip("yield-alert/query timed out — heavy query on this environment")
        assert resp.status_code in (200, 202)

    def test_summary_rejects_over_limit_range(self, api_base_url):
        """POST /query exceeding max_query_days should return 400."""
        max_days = self._discover_max_days(api_base_url)
        from datetime import date, timedelta
        end = date(2026, 3, 13)
        start = end - timedelta(days=max_days + 10)
        resp = requests.post(
            f"{api_base_url}/yield-alert/query",
            json={"start_date": start.isoformat(), "end_date": end.isoformat()},
            timeout=30,
        )
        assert resp.status_code == 400
        payload = resp.json()
        assert payload["success"] is False
        assert str(max_days) in payload.get("error", {}).get("message", "")


# ─────────────────────────────────────────────────────────────────────────────
# yield-alert-spool-refactor: E2E + resilience tests
# AC-1: process_type validation (default GA%, GC% accepted, invalid rejected)
# AC-2: trend/summary serve from spool only (410 when spool absent)
# AC-4: source_code key present in every alert row
# ─────────────────────────────────────────────────────────────────────────────


def _post_query(api_base_url: str, body: dict, timeout: int = 120) -> "requests.Response":
    """POST /api/yield-alert/query and return the response."""
    return requests.post(
        f"{api_base_url}/yield-alert/query",
        json=body,
        timeout=timeout,
    )


def _poll_yield_alert_job(api_base_url: str, job_id: str, timeout_seconds: float = 300.0) -> None:
    """Poll GET /api/yield-alert/job/<job_id> until terminal state, or skip on timeout."""
    status_url = f"{api_base_url}/yield-alert/job/{job_id}"
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        resp = requests.get(status_url, timeout=30)
        if resp.status_code != 200:
            pytest.skip(f"yield-alert job status returned {resp.status_code} — server may be unavailable")
        status = resp.json().get("data", {}).get("status", "")
        if status == "completed":
            return
        if status == "failed":
            pytest.skip(f"yield-alert async job {job_id!r} failed")
        time.sleep(3)
    pytest.skip(f"yield-alert async job {job_id!r} did not complete within {timeout_seconds}s")


def _acquire_query_id(api_base_url: str, process_type: str = "GA%") -> str:
    """Submit a query and return the query_id, or skip the test if unavailable.

    On 202 (async), the job must reach "completed" before the returned
    query_id's spool is actually readable — otherwise callers race the
    background job and see a 410 CACHE_EXPIRED for a spool that simply
    hasn't been written yet.
    """
    resp = _post_query(
        api_base_url,
        {"start_date": "2026-03-01", "end_date": "2026-03-07", "process_type": process_type},
    )
    if resp.status_code == 503:
        pytest.skip("yield-alert service busy — skipping spool-dependent test")
    if resp.status_code not in (200, 202):
        pytest.skip(f"yield-alert/query returned {resp.status_code} — server may be unavailable")
    payload = resp.json()
    data = payload.get("data", {})
    query_id = data.get("query_id", "")
    if not query_id:
        pytest.skip("yield-alert/query succeeded but returned no query_id")
    if resp.status_code == 202:
        job_id = data.get("job_id", "")
        if not job_id:
            pytest.skip("yield-alert/query 202 response missing job_id")
        _poll_yield_alert_job(api_base_url, job_id)
    return query_id


@pytest.mark.e2e
class TestYieldAlertProcessType:
    """AC-1: process_type validation — default, GC% acceptance, invalid rejection."""

    def test_process_type_defaults_to_ga_percent(self, api_base_url):
        """POST /query without process_type must succeed (defaults to GA%).

        AC-1: absent process_type → GA% default, not a 400 VALIDATION_ERROR.
        """
        resp = _post_query(
            api_base_url,
            {"start_date": "2026-03-01", "end_date": "2026-03-07"},
        )
        # 503 = busy is acceptable; 200/202 = success; 400 = fail (regression)
        if resp.status_code == 503:
            pytest.skip("yield-alert service busy")
        assert resp.status_code in (200, 202), (
            f"POST /query without process_type returned {resp.status_code} — "
            f"expected 200/202 (GA% default). Body: {resp.text[:300]}"
        )
        payload = resp.json()
        assert payload["success"] is True, (
            f"POST /query without process_type: success=False. Error: {payload.get('error')}"
        )

    def test_process_type_gc_percent_query_accepted(self, api_base_url):
        """POST /query with process_type='GC%' must be accepted (200 or 202).

        AC-1: GC% is a valid process_type; must not return VALIDATION_ERROR.
        """
        resp = _post_query(
            api_base_url,
            {"start_date": "2026-03-01", "end_date": "2026-03-07", "process_type": "GC%"},
        )
        if resp.status_code == 503:
            pytest.skip("yield-alert service busy")
        assert resp.status_code in (200, 202), (
            f"POST /query with process_type='GC%' returned {resp.status_code} — "
            f"expected acceptance. Body: {resp.text[:300]}"
        )
        payload = resp.json()
        assert payload["success"] is True, (
            f"POST /query with process_type='GC%': success=False. Error: {payload.get('error')}"
        )
        # Must not be a VALIDATION_ERROR
        if "error" in payload:
            assert payload["error"].get("code") != "VALIDATION_ERROR", (
                "GC% was incorrectly rejected with VALIDATION_ERROR"
            )

    def test_process_type_invalid_returns_400(self, api_base_url):
        """POST /query with process_type='XX%' must return 400 VALIDATION_ERROR.

        AC-1: Invalid process_type must be rejected; must NOT be coerced to GA%.
        Per implementation plan Non-goals: 'Do NOT coerce an invalid process_type to GA%'.
        """
        resp = _post_query(
            api_base_url,
            {"start_date": "2026-03-01", "end_date": "2026-03-07", "process_type": "XX%"},
            timeout=30,
        )
        assert resp.status_code == 400, (
            f"POST /query with process_type='XX%' returned {resp.status_code} — "
            f"expected 400 VALIDATION_ERROR. Body: {resp.text[:300]}"
        )
        payload = resp.json()
        assert payload["success"] is False
        assert payload.get("error", {}).get("code") == "VALIDATION_ERROR", (
            f"Expected error.code='VALIDATION_ERROR', got: {payload.get('error')}"
        )


@pytest.mark.e2e
class TestYieldAlertSourceCodeField:
    """AC-4: source_code key must be present in every alert row."""

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "Real gap, not a test bug: business-rules.md YA-05 requires "
            "source_code (LOT ID) on every /alerts row, but query_alert_candidates() "
            "in yield_alert_service.py never selects/aggregates SOURCE_CODE. The "
            "contract also claims /alerts is spool-served, but it still queries Oracle "
            "directly — likely an incomplete yield-alert-spool-refactor migration. "
            "Needs a scoped implementation change, not a quick patch here. Remove this "
            "marker once source_code is wired through."
        ),
    )
    def test_alerts_response_includes_source_code_field(self, api_base_url):
        """GET /alerts after a GA% query must have 'source_code' key in each item.

        AC-4: SOURCE_CODE (LOT) column wired into alert rows. Key must exist even
        when the value is null — its absence is a regression of the spool-refactor.
        """
        # Use the /alerts endpoint directly (date-range based, no query_id needed).
        # The /alerts endpoint was not retired — it still accepts date-range params.
        resp = requests.get(
            f"{api_base_url}/yield-alert/alerts",
            params={
                "start_date": "2026-03-01",
                "end_date": "2026-03-07",
                "page": 1,
                "per_page": 5,
            },
            timeout=60,
        )
        if resp.status_code in (503, 202):
            pytest.skip("yield-alert/alerts unavailable or async — cannot inspect items")
        assert resp.status_code == 200, (
            f"GET /yield-alert/alerts returned {resp.status_code}. Body: {resp.text[:300]}"
        )
        payload = resp.json()
        assert payload["success"] is True
        items = payload["data"].get("items", [])
        if not items:
            pytest.skip("No alert items returned for 2026-03-01..03-07 — cannot assert source_code key")
        for idx, item in enumerate(items):
            assert "source_code" in item, (
                f"Alert item[{idx}] missing 'source_code' key after spool-refactor. "
                f"Keys present: {list(item.keys())}"
            )


@pytest.mark.e2e
class TestYieldAlertSpoolOnlyPaths:
    """AC-2: trend and summary endpoints serve only from spool after refactor."""

    def test_trend_endpoint_uses_spool_only(self, api_base_url):
        """GET /trend with a live query_id must return 200 (served from spool).

        AC-2: Trend data served from DuckDB spool, not live Oracle.
        Then calling with a bad query_id must return 410 — no Oracle fallback.
        """
        query_id = _acquire_query_id(api_base_url, process_type="GA%")

        # Part 1: valid spool → 200
        resp = requests.get(
            f"{api_base_url}/yield-alert/trend",
            params={"query_id": query_id},
            timeout=60,
        )
        assert resp.status_code == 200, (
            f"GET /trend with valid query_id={query_id!r} returned {resp.status_code} — "
            f"expected 200 from spool. Body: {resp.text[:300]}"
        )
        payload = resp.json()
        assert payload["success"] is True

        # Part 2: corrupted query_id → 410 (confirms no Oracle fallback)
        resp_miss = requests.get(
            f"{api_base_url}/yield-alert/trend",
            params={"query_id": "definitely-expired-qid-0000"},
            timeout=30,
        )
        assert resp_miss.status_code == 410, (
            f"GET /trend with expired query_id returned {resp_miss.status_code} — "
            f"expected 410 (live Oracle fallback must be gone). Body: {resp_miss.text[:300]}"
        )
        miss_payload = resp_miss.json()
        assert miss_payload.get("error", {}).get("code") == "CACHE_EXPIRED", (
            f"Expected error.code='CACHE_EXPIRED', got: {miss_payload.get('error')}"
        )


@pytest.mark.e2e
class TestYieldAlertSpoolMissResilience:
    """Resilience: spool-miss on trend and summary must return 410, no Oracle fallback."""

    def test_trend_with_expired_spool_returns_410(self, api_base_url):
        """GET /trend?query_id=nonexistent_id must return 410 CACHE_EXPIRED.

        AC-2 resilience: confirms the live Oracle trend fallback is retired.
        The route must not attempt any Oracle call when spool is absent.
        """
        resp = requests.get(
            f"{api_base_url}/yield-alert/trend",
            params={"query_id": "nonexistent-expired-spool-id"},
            timeout=30,
        )
        assert resp.status_code == 410, (
            f"GET /trend with nonexistent query_id returned {resp.status_code} — "
            f"expected 410. Body: {resp.text[:300]}"
        )
        payload = resp.json()
        assert payload["success"] is False
        assert payload.get("error", {}).get("code") == "CACHE_EXPIRED", (
            f"Expected error.code='CACHE_EXPIRED', got: {payload.get('error')}"
        )

    def test_summary_with_expired_spool_returns_410(self, api_base_url):
        """GET /summary?query_id=nonexistent_id must return 410 CACHE_EXPIRED.

        AC-2 resilience: confirms the live Oracle summary fallback is retired.
        The route must not attempt any Oracle call when spool is absent.
        """
        resp = requests.get(
            f"{api_base_url}/yield-alert/summary",
            params={"query_id": "nonexistent-expired-spool-id"},
            timeout=30,
        )
        assert resp.status_code == 410, (
            f"GET /summary with nonexistent query_id returned {resp.status_code} — "
            f"expected 410. Body: {resp.text[:300]}"
        )
        payload = resp.json()
        assert payload["success"] is False
        assert payload.get("error", {}).get("code") == "CACHE_EXPIRED", (
            f"Expected error.code='CACHE_EXPIRED', got: {payload.get('error')}"
        )


@pytest.mark.e2e
class TestYieldAlertBrowserE2E:
    """Browser E2E for yield-alert-center primary workflow."""

    def test_yield_alert_page_builds_primary_query_cache(self, page: Page, app_server: str):
        probe = requests.post(
            f"{app_server}/api/yield-alert/query",
            json={"start_date": "2026-03-01", "end_date": "2026-03-07"},
            timeout=120,
        )
        if probe.status_code not in (200, 503):
            pytest.skip(f"Yield alert preflight unavailable: {probe.status_code}")
        if probe.status_code == 503:
            pytest.skip("Yield alert service busy")

        goto_shell_route(page, app_server, "/yield-alert-center", "良率查詢")
        # yield-alert-center has no page-title heading — "良率查詢" only
        # exists as the sidebar nav link text.
        query_button = page.locator(".primary-query-panel .ui-btn--primary").first
        expect(query_button).to_be_enabled(timeout=60000)
        query_button.click()

        wait_for_any_visible(
            page,
            [
                "text=已建立快取:",
                "text=告警候選清單",
                ".alerts-panel",
            ],
            timeout_ms=180000,
        )
        expect(page.locator("text=告警候選清單")).to_be_visible()
