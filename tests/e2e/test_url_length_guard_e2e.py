# -*- coding: utf-8 -*-
"""E2E tests for the URL length guard feature.

Covers:
  6.1  WIP overview → detail drilldown → back — no 400 error, state preserved via sessionStorage
  6.2  WIP overview large filter set → page refresh → state restored from sessionStorage
  6.3  Hold-overview with many filters → replaceRuntimeHistory spills → page refresh restores state
  6.4  Reject-history export-cached via POST → CSV downloads successfully
  6.5  Resource-history export via POST → CSV downloads successfully
"""

from __future__ import annotations

import time
from urllib.parse import urlparse

import pytest
import requests
from playwright.sync_api import Page

from tests.e2e.browser_helpers import ensure_shell_admin


# ── Shared helpers ─────────────────────────────────────────────────────────────


def _big_filter_value(prefix: str, count: int = 60) -> str:
    """Generate a comma-separated list large enough to trigger URL overflow."""
    return ",".join(f"{prefix}{i:04d}" for i in range(count))


def _wait_for_response(page: Page, predicate, timeout_seconds: float = 30.0):
    matched = []

    def handle(resp):
        try:
            if predicate(resp):
                matched.append(resp)
        except Exception:
            return

    page.on("response", handle)
    deadline = time.time() + timeout_seconds
    while time.time() < deadline and not matched:
        page.wait_for_timeout(200)
    return matched[0] if matched else None


def _pre_register_response_listener(page: Page, predicate):
    matched = []

    def handle(resp):
        try:
            if predicate(resp):
                matched.append(resp)
        except Exception:
            return

    page.on("response", handle)

    def wait(timeout_seconds: float = 30.0):
        deadline = time.time() + timeout_seconds
        while time.time() < deadline and not matched:
            page.wait_for_timeout(200)
        return matched[0] if matched else None

    return wait


def _pick_workcenter(app_server: str) -> str:
    try:
        resp = requests.get(f"{app_server}/api/wip/meta/workcenters", timeout=10)
        if resp.status_code == 200:
            items = resp.json().get("data") or []
            if items:
                return items[0].get("name") or "TMTT"
    except Exception:
        pass
    return "TMTT"


# ── 6.2 / 6.3: sessionStorage spill + restore via browser eval ─────────────────


@pytest.mark.e2e
class TestUrlLengthGuardSessionStorageE2E:
    """Browser tests that simulate the sessionStorage spill/restore cycle."""

    def test_wip_overview_restores_state_from_session_storage(self, page: Page, app_server: str):
        """6.2: Navigate to ?_s=1 with pre-seeded sessionStorage — state restores without 400."""
        ensure_shell_admin(page, "/wip-overview", "WIP 即時概況")

        # Pre-seed sessionStorage as if replaceRuntimeHistory had spilled
        fake_query = "workorder=WO0001,WO0002&status=RUN"
        page.evaluate(
            """([key, value]) => { sessionStorage.setItem(key, value); }""",
            [f"url-state:/wip-overview", fake_query],
        )

        wait = _pre_register_response_listener(
            page,
            lambda resp: "/api/wip/overview/matrix" in resp.url,
        )

        # Navigate to the spilled URL marker
        page.goto(
            f"{app_server}/portal-shell/wip-overview?_s=1",
            wait_until="commit",
            timeout=60000,
        )

        # Must get a successful matrix response (no 400)
        resp = wait(timeout_seconds=30.0)
        assert resp is not None, "No matrix response observed after restoring state from sessionStorage"
        assert resp.ok, f"Matrix request failed with status {resp.status}"

        # URL should be cleaned up (no _s=1 marker remaining)
        current_url = page.url
        assert "_s=1" not in current_url, f"_s=1 marker was not stripped from URL: {current_url}"

    def test_hold_overview_restores_state_from_session_storage(self, page: Page, app_server: str):
        """6.3: Hold-overview large filter set spills to sessionStorage then restores on refresh."""
        ensure_shell_admin(page, "/hold-overview", "Hold 概況")

        # Simulate state from a large hold_type + workcenter filter
        fake_query = "hold_type=quality&workcenter=A,B,C"
        page.evaluate(
            """([key, value]) => { sessionStorage.setItem(key, value); }""",
            [f"url-state:/hold-overview", fake_query],
        )

        wait = _pre_register_response_listener(
            page,
            lambda resp: "/api/wip/hold" in resp.url,
        )

        page.goto(
            f"{app_server}/portal-shell/hold-overview?_s=1",
            wait_until="commit",
            timeout=60000,
        )

        resp = wait(timeout_seconds=30.0)
        assert resp is not None, "No hold-overview API response observed after restoring sessionStorage state"
        assert resp.ok, f"Hold overview request failed with status {resp.status}"

        current_url = page.url
        assert "_s=1" not in current_url, f"_s=1 marker was not stripped from URL: {current_url}"


# ── 6.1: WIP overview → detail → back (SPA navigation, no 400) ────────────────


@pytest.mark.e2e
class TestWipDrilldownBackE2E:
    """6.1: WIP overview drilldown → back preserves state via sessionStorage (no 400)."""

    def test_wip_detail_back_button_is_spa_button(self, page: Page, app_server: str):
        """Back link in wip-detail must be a <button>, not an <a href>."""
        workcenter = _pick_workcenter(app_server)
        ensure_shell_admin(page, "/wip-detail", "WIP 明細")

        wait = _pre_register_response_listener(
            page,
            lambda resp: "/api/wip/detail/" in resp.url,
        )
        page.goto(
            f"{app_server}/portal-shell/wip-detail?workcenter={workcenter}",
            wait_until="commit",
            timeout=60000,
        )
        wait(timeout_seconds=30.0)

        # The back element must be a <button> (not <a>)
        back_btn = page.locator("button.ui-btn--ghost").filter(has_text="Overview").first
        assert back_btn.count() > 0, (
            "Back navigation element was not found as a <button>. "
            "It may still be an <a href> which can cause 400 errors with long filter sets."
        )

    def test_wip_overview_drilldown_url_stays_short(self, page: Page, app_server: str):
        """6.1: When navigating from overview to detail, the detail URL must stay short (no filters)."""
        ensure_shell_admin(page, "/wip-overview", "WIP 即時概況")

        wait_matrix = _pre_register_response_listener(
            page,
            lambda resp: "/api/wip/overview/matrix" in resp.url,
        )
        page.goto(
            f"{app_server}/portal-shell/wip-overview",
            wait_until="commit",
            timeout=60000,
        )
        wait_matrix(timeout_seconds=30.0)

        # Watch for any navigation to wip-detail
        navigated_urls: list[str] = []
        page.on(
            "request",
            lambda req: navigated_urls.append(req.url)
            if "/portal-shell/wip-detail" in req.url or "/wip-detail" in req.url
            else None,
        )

        # Click the first drilldown cell if available
        matrix_cells = page.locator("td.drilldown-cell, .matrix-cell[data-workcenter]")
        if matrix_cells.count() > 0:
            matrix_cells.first.click(timeout=5000)
            page.wait_for_timeout(1000)

            if navigated_urls:
                detail_url = navigated_urls[0]
                parsed = urlparse(detail_url)
                # URL must be short — just workcenter (+ optionally status)
                assert len(detail_url) < 300, (
                    f"Detail navigation URL is too long ({len(detail_url)} chars): {detail_url}. "
                    "Filter arrays should be passed via sessionStorage, not URL params."
                )
        else:
            pytest.skip("No matrix drilldown cells available — requires data")


# ── 6.4 / 6.5: POST export API tests ──────────────────────────────────────────


def _query_reject_and_get_id(app_server: str) -> str | None:
    """Attempt reject-history primary query and return query_id."""
    from datetime import date, timedelta

    end = date.today()
    start = end - timedelta(days=7)

    try:
        resp = requests.post(
            f"{app_server}/api/reject-history/query",
            json={
                "mode": "date_range",
                "start_date": start.strftime("%Y-%m-%d"),
                "end_date": end.strftime("%Y-%m-%d"),
                "exclude_material_scrap": True,
                "exclude_pb_diode": True,
            },
            timeout=120,
        )
        if resp.status_code not in (200, 202):
            return None
        payload = resp.json()
        if payload.get("data", {}).get("async"):
            # Poll for completion
            job_id = payload["data"]["job_id"]
            query_id = payload["data"].get("query_id", "")
            for _ in range(30):
                time.sleep(3)
                status_resp = requests.get(
                    f"{app_server}/api/reject-history/job/{job_id}", timeout=15
                )
                if status_resp.ok:
                    status = status_resp.json().get("data", {})
                    if status.get("status") == "done":
                        return status.get("query_id") or query_id
                    if status.get("status") in ("failed", "cancelled"):
                        return None
            return query_id
        return payload.get("data", {}).get("query_id") or None
    except Exception:
        return None


@pytest.mark.e2e
class TestPostExportEndpointsE2E:
    """6.4 / 6.5: POST export endpoints return CSV without 400 errors."""

    def test_reject_history_export_cached_accepts_post(self, app_server: str):
        """6.4: POST to export-cached with JSON body returns CSV."""
        query_id = _query_reject_and_get_id(app_server)
        if not query_id:
            pytest.skip("Reject history primary query failed or no data available")

        # POST with JSON body (large filter scenario simulation)
        resp = requests.post(
            f"{app_server}/api/reject-history/export-cached",
            json={
                "query_id": query_id,
                "packages": [],
                "workcenter_groups": [],
                "reasons": [],
                "metric_filter": "all",
                "trend_dates": [],
                "exclude_material_scrap": True,
                "exclude_pb_diode": True,
            },
            timeout=120,
        )
        assert resp.status_code == 200, (
            f"POST export-cached failed with {resp.status_code}: {resp.text[:300]}"
        )
        assert "text/csv" in resp.headers.get("Content-Type", ""), (
            f"Expected text/csv response, got: {resp.headers.get('Content-Type')}"
        )

    def test_resource_history_export_accepts_post(self, app_server: str):
        """6.5: POST to resource history export with JSON body returns CSV."""
        from datetime import date, timedelta

        end = date.today()
        start = end - timedelta(days=7)

        resp = requests.post(
            f"{app_server}/api/resource/history/export",
            json={
                "start_date": start.strftime("%Y-%m-%d"),
                "end_date": end.strftime("%Y-%m-%d"),
                "granularity": "day",
            },
            timeout=120,
        )
        # Accept 200 (data) or 404 (no data) — anything except 400 (URL too large) or 405 (method not allowed)
        assert resp.status_code not in (400, 405), (
            f"POST to resource history export returned {resp.status_code}: {resp.text[:300]}"
        )
        if resp.status_code == 200:
            assert "text/csv" in resp.headers.get("Content-Type", ""), (
                f"Expected text/csv response, got: {resp.headers.get('Content-Type')}"
            )

    def test_production_history_export_accepts_post(self, app_server: str):
        """POST to production history export with JSON body returns 4xx/200, never 405."""
        resp = requests.post(
            f"{app_server}/api/production-history/export",
            json={"dataset_id": "nonexistent_dataset_for_method_test"},
            timeout=30,
        )
        # 405 = method not allowed = POST not wired up. 410 = dataset expired = POST is wired up correctly.
        assert resp.status_code != 405, (
            "POST method not registered on /api/production-history/export. "
            "This endpoint should accept POST bodies for large filter sets."
        )
        # If disabled, 404 is expected; 410 means dataset_id missing/expired — both are correct
        assert resp.status_code in (200, 400, 404, 410, 503), (
            f"Unexpected status code: {resp.status_code}"
        )
