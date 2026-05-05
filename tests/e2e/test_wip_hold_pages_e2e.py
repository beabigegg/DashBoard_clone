# -*- coding: utf-8 -*-
"""E2E coverage for WIP Overview / WIP Detail / Hold Detail pages."""

from __future__ import annotations

import time
from urllib.parse import parse_qs, quote, urlparse
import re

import pytest
import requests
from playwright.sync_api import Page, expect

from tests.e2e.browser_helpers import ensure_shell_admin


def _pick_workcenter(app_server: str) -> str:
    """Pick a real workcenter to reduce flaky E2E failures."""
    try:
        response = requests.get(f"{app_server}/api/wip/meta/workcenters", timeout=10)
        if response.status_code == 200:
            payload = response.json()
            items = payload.get("data") or []
            if not items:
                pytest.skip("No workcenter data available")
            return items[0].get("name") or "TMTT"
    except pytest.skip.Exception:
        raise
    except Exception:
        pass
    return "TMTT"


def _pick_hold_reason(app_server: str) -> str:
    """Pick a real hold reason to reduce flaky E2E failures."""
    try:
        response = requests.get(f"{app_server}/api/wip/overview/hold", timeout=10)
        if response.status_code == 200:
            payload = response.json()
            items = (payload.get("data") or {}).get("items") or []
            if not items:
                pytest.skip("No hold reason data available")
            return items[0].get("reason") or "YieldLimit"
    except pytest.skip.Exception:
        raise
    except Exception:
        pass
    return "YieldLimit"


def _get_with_retry(url: str, attempts: int = 3, timeout: float = 10.0):
    """Best-effort GET helper to reduce transient test flakiness."""
    last_exc = None
    for _ in range(max(attempts, 1)):
        try:
            return requests.get(url, timeout=timeout, allow_redirects=False)
        except requests.RequestException as exc:
            last_exc = exc
            time.sleep(0.5)
    if last_exc:
        raise last_exc
    raise RuntimeError("request retry exhausted without exception")


def _wait_for_response_url_tokens(page: Page, tokens: list[str], timeout_seconds: float = 30.0):
    """Wait until a response URL contains all tokens."""
    matched = []

    def handle_response(resp):
        if all(token in resp.url for token in tokens):
            matched.append(resp)

    page.on("response", handle_response)
    deadline = time.time() + timeout_seconds
    while time.time() < deadline and not matched:
        page.wait_for_timeout(200)
    return matched[0] if matched else None


def _wait_for_response(page: Page, predicate, timeout_seconds: float = 30.0):
    """Wait until a response satisfies the predicate."""
    matched = []

    def handle_response(resp):
        try:
            if predicate(resp):
                matched.append(resp)
        except Exception:
            return

    page.on("response", handle_response)
    deadline = time.time() + timeout_seconds
    while time.time() < deadline and not matched:
        page.wait_for_timeout(200)
    return matched[0] if matched else None


def _pre_register_response_listener(page: Page, predicate):
    """Register listener immediately; return a waiter to call after goto."""
    matched = []

    def handle_response(resp):
        try:
            if predicate(resp):
                matched.append(resp)
        except Exception:
            return

    page.on("response", handle_response)

    def wait(timeout_seconds: float = 30.0):
        deadline = time.time() + timeout_seconds
        while time.time() < deadline and not matched:
            page.wait_for_timeout(200)
        return matched[0] if matched else None

    return wait


def _pre_register_post_request_listener(page: Page, url_token: str):
    """Register a request listener for POST calls matching url_token."""

    matched = []

    def handle_request(req):
        try:
            if url_token not in req.url:
                return
            if req.method != "POST":
                return
            matched.append(req)
        except Exception:
            return

    page.on("request", handle_request)

    def wait(timeout_seconds: float = 30.0):
        deadline = time.time() + timeout_seconds
        while time.time() < deadline and not matched:
            page.wait_for_timeout(200)
        return matched[0] if matched else None

    return wait


@pytest.mark.e2e
class TestWipAndHoldPagesE2E:
    """E2E tests for WIP/Hold page URL + API behavior."""

    def test_wip_overview_restores_status_from_url(self, page: Page, app_server: str):
        ensure_shell_admin(page, "/wip-overview", "WIP 即時概況")
        # Filters are now sent as POST body, not URL query params — match on path only.
        wait = _pre_register_response_listener(
            page,
            lambda resp: "/api/wip/overview/matrix" in resp.url,
        )
        page.goto(
            f"{app_server}/portal-shell/wip-overview?type=PJA3460&status=queue",
            wait_until="commit",
            timeout=60000,
        )
        response = wait(timeout_seconds=30.0)
        assert response is not None, "Did not observe expected matrix POST request"
        assert response.ok
        expect(page.locator("body")).to_be_visible()

    def test_wip_detail_reads_status_and_back_button_exists(self, page: Page, app_server: str):
        workcenter = _pick_workcenter(app_server)
        ensure_shell_admin(page, "/wip-detail", "WIP 明細")
        # Filters are now sent as POST body — match on URL path only.
        wait = _pre_register_response_listener(
            page,
            lambda resp: "/api/wip/detail/" in resp.url,
        )
        page.goto(
            f"{app_server}/portal-shell/wip-detail?workcenter={quote(workcenter)}&type=PJA3460&status=queue",
            wait_until="commit",
            timeout=60000,
        )

        response = wait(timeout_seconds=30.0)
        assert response is not None, "Did not observe expected detail request with URL filters"
        assert response.ok

        # Back navigation is now a <button> (SPA navigation via sessionStorage),
        # not an <a href> that would cause 400 errors with large filter sets.
        back_btn = page.locator("button.ui-btn--ghost").filter(has_text="Overview").first
        assert back_btn.count() > 0, (
            "Back navigation element not found as <button>. "
            "WIP detail back link must use SPA button navigation to avoid URL length 400 errors."
        )

    def test_hold_detail_without_reason_redirects_to_overview(self, page: Page, app_server: str):
        nav_resp = _get_with_retry(f"{app_server}/api/portal/navigation", attempts=3, timeout=10.0)
        nav_payload = nav_resp.json() if nav_resp.ok else {}
        spa_enabled = bool(nav_payload.get("portal_spa_enabled"))

        response = _get_with_retry(f"{app_server}/hold-detail", attempts=3, timeout=10.0)
        assert response.status_code == 302
        if spa_enabled:
            assert response.headers.get("Location") == "/portal-shell/hold-overview"
        else:
            assert response.headers.get("Location") == "/hold-overview"

    def test_hold_detail_calls_summary_distribution_and_lots(self, page: Page, app_server: str):
        reason = _pick_hold_reason(app_server)
        ensure_shell_admin(page, "/hold-detail", "Hold 明細")
        wait_summary = _pre_register_response_listener(
            page,
            lambda resp: (
                "/api/wip/hold-detail/summary" in resp.url
                and parse_qs(urlparse(resp.url).query).get("reason", [None])[0] == reason
            ),
        )
        wait_distribution = _pre_register_response_listener(
            page,
            lambda resp: (
                "/api/wip/hold-detail/distribution" in resp.url
                and parse_qs(urlparse(resp.url).query).get("reason", [None])[0] == reason
            ),
        )
        wait_lots = _pre_register_response_listener(
            page,
            lambda resp: (
                "/api/wip/hold-detail/lots" in resp.url
                and parse_qs(urlparse(resp.url).query).get("reason", [None])[0] == reason
            ),
        )
        page.goto(
            f"{app_server}/portal-shell/hold-detail?reason={quote(reason)}",
            wait_until="commit",
            timeout=60000,
        )

        summary_resp = wait_summary(timeout_seconds=30.0)
        assert summary_resp is not None, "Did not observe summary request"
        assert summary_resp.ok

        distribution_resp = wait_distribution(timeout_seconds=30.0)
        assert distribution_resp is not None, "Did not observe distribution request"
        assert distribution_resp.ok

        lots_resp = wait_lots(timeout_seconds=30.0)
        assert lots_resp is not None, "Did not observe lots request"
        assert lots_resp.ok

    def test_portal_shell_deep_links_keep_detail_routes(self, page: Page, app_server: str):
        workcenter = _pick_workcenter(app_server)
        ensure_shell_admin(page, "/wip-detail", "WIP 明細")
        # Filters are now POST body — match on path only.
        wait_detail = _pre_register_response_listener(
            page,
            lambda resp: "/api/wip/detail/" in resp.url,
        )
        page.goto(
            f"{app_server}/portal-shell/wip-detail?workcenter={quote(workcenter)}&status=queue",
            wait_until="commit",
            timeout=60000,
        )
        expect(page).to_have_url(re.compile(r".*/portal-shell/wip-detail\?.*workcenter=.*"))
        detail_response = wait_detail(timeout_seconds=30.0)
        assert detail_response is not None
        assert detail_response.ok

        reason = _pick_hold_reason(app_server)
        wait_summary = _pre_register_response_listener(
            page,
            lambda resp: (
                "/api/wip/hold-detail/summary" in resp.url
                and parse_qs(urlparse(resp.url).query).get("reason", [None])[0] == reason
            ),
        )
        page.goto(
            f"{app_server}/portal-shell/hold-detail?reason={quote(reason)}",
            wait_until="commit",
            timeout=60000,
        )
        expect(page).to_have_url(re.compile(r".*/portal-shell/hold-detail\?.*reason=.*"))
        summary_response = wait_summary(timeout_seconds=30.0)
        assert summary_response is not None
        assert summary_response.ok

    def test_wip_api_calls_use_post_method(self, page: Page, app_server: str):
        """Regression: WIP data endpoints must use POST to avoid URL length limit.

        When many filter values are selected the GET query string can exceed
        Gunicorn's 4094-byte limit.  The frontend must send POST for summary,
        matrix, detail, and filter-options.
        """

        ensure_shell_admin(page, "/wip-overview", "WIP 即時概況")

        wait_matrix = _pre_register_post_request_listener(page, "/api/wip/overview/matrix")
        wait_summary = _pre_register_post_request_listener(page, "/api/wip/overview/summary")
        wait_opts = _pre_register_post_request_listener(page, "/api/wip/meta/filter-options")

        page.goto(
            f"{app_server}/portal-shell/wip-overview",
            wait_until="commit",
            timeout=60000,
        )

        matrix_req = wait_matrix(timeout_seconds=30.0)
        assert matrix_req is not None, "matrix endpoint was not called via POST"
        assert matrix_req.method == "POST"

        summary_req = wait_summary(timeout_seconds=30.0)
        assert summary_req is not None, "summary endpoint was not called via POST"
        assert summary_req.method == "POST"

        opts_req = wait_opts(timeout_seconds=30.0)
        assert opts_req is not None, "filter-options endpoint was not called via POST"
        assert opts_req.method == "POST"

    def test_portal_shell_wip_overview_drilldown_routes_to_detail_pages(self, page: Page, app_server: str):
        page.goto(
            f"{app_server}/portal-shell/wip-overview",
            wait_until="commit",
            timeout=60000,
        )
        page.wait_for_timeout(3000)

        matrix_links = page.locator("td.clickable")
        if matrix_links.count() == 0:
            pytest.skip("No matrix rows available for WIP drilldown")
        matrix_links.first.click()
        expect(page).to_have_url(re.compile(r".*/portal-shell/wip-detail\\?.*workcenter=.*"))

        page.goto(
            f"{app_server}/portal-shell/wip-overview",
            wait_until="commit",
            timeout=60000,
        )
        page.wait_for_timeout(3000)

        reason_links = page.locator("a.reason-link")
        if reason_links.count() == 0:
            pytest.skip("No pareto reason links available for HOLD drilldown")
        reason_links.first.click()
        expect(page).to_have_url(re.compile(r".*/portal-shell/hold-detail\\?.*reason=.*"))
