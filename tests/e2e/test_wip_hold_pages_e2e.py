# -*- coding: utf-8 -*-
"""E2E coverage for WIP Overview / WIP Detail / Hold Detail pages."""

from __future__ import annotations

import time
from urllib.parse import parse_qs, quote, urlparse
import re

import pytest
import requests
from playwright.sync_api import Page, expect


def _pick_workcenter(app_server: str) -> str:
    """Pick a real workcenter to reduce flaky E2E failures."""
    try:
        response = requests.get(f"{app_server}/api/wip/meta/workcenters", timeout=10)
        payload = response.json() if response.ok else {}
        items = payload.get("data") or []
        if items:
            return items[0].get("name") or "TMTT"
    except Exception:
        pass
    return "TMTT"


def _pick_hold_reason(app_server: str) -> str:
    """Pick a real hold reason to reduce flaky E2E failures."""
    try:
        response = requests.get(f"{app_server}/api/wip/overview/hold", timeout=10)
        payload = response.json() if response.ok else {}
        items = (payload.get("data") or {}).get("items") or []
        if items:
            return items[0].get("reason") or "YieldLimit"
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


@pytest.mark.e2e
class TestWipAndHoldPagesE2E:
    """E2E tests for WIP/Hold page URL + API behavior."""

    def test_wip_overview_restores_status_from_url(self, page: Page, app_server: str):
        page.goto(
            f"{app_server}/wip-overview?type=PJA3460&status=queue",
            wait_until="commit",
            timeout=60000,
        )
        response = _wait_for_response_url_tokens(
            page,
            ["/api/wip/overview/matrix", "type=PJA3460", "status=QUEUE"],
            timeout_seconds=30.0,
        )
        assert response is not None, "Did not observe expected matrix request with URL filters"
        assert response.ok
        expect(page.locator("body")).to_be_visible()

    def test_wip_detail_reads_status_and_back_link_keeps_filters(self, page: Page, app_server: str):
        workcenter = _pick_workcenter(app_server)
        page.goto(
            f"{app_server}/wip-detail?workcenter={quote(workcenter)}&type=PJA3460&status=queue",
            wait_until="commit",
            timeout=60000,
        )

        response = _wait_for_response(
            page,
            lambda resp: (
                "/api/wip/detail/" in resp.url
                and (
                    parse_qs(urlparse(resp.url).query).get("type", [None])[0] == "PJA3460"
                    or parse_qs(urlparse(resp.url).query).get("pj_type", [None])[0] == "PJA3460"
                )
                and parse_qs(urlparse(resp.url).query).get("status", [None])[0] in {"QUEUE", "queue"}
            ),
            timeout_seconds=30.0,
        )
        assert response is not None, "Did not observe expected detail request with URL filters"
        assert response.ok

        back_link = page.locator("a.btn-back, a.ui-btn--ghost").filter(has_text="Overview").first
        back_href = back_link.get_attribute("href") or ""
        parsed = urlparse(back_href)
        params = parse_qs(parsed.query)
        assert parsed.path in {"/wip-overview", "/portal-shell/wip-overview"}
        assert params.get("type", [None])[0] == "PJA3460"
        assert params.get("status", [None])[0] in {"queue", "QUEUE"}

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
        seen = set()

        def handle_response(resp):
            parsed = urlparse(resp.url)
            query = parse_qs(parsed.query)
            if query.get("reason", [None])[0] != reason:
                return
            if parsed.path.endswith("/api/wip/hold-detail/summary"):
                seen.add("summary")
            elif parsed.path.endswith("/api/wip/hold-detail/distribution"):
                seen.add("distribution")
            elif parsed.path.endswith("/api/wip/hold-detail/lots"):
                seen.add("lots")

        page.on("response", handle_response)
        page.goto(
            f"{app_server}/hold-detail?reason={quote(reason)}",
            wait_until="commit",
            timeout=60000,
        )

        deadline = time.time() + 30
        while time.time() < deadline and len(seen) < 3:
            page.wait_for_timeout(200)

        assert seen == {"summary", "distribution", "lots"}

    def test_portal_shell_deep_links_keep_detail_routes(self, page: Page, app_server: str):
        workcenter = _pick_workcenter(app_server)
        page.goto(
            f"{app_server}/portal-shell/wip-detail?workcenter={quote(workcenter)}&status=queue",
            wait_until="commit",
            timeout=60000,
        )
        expect(page).to_have_url(re.compile(r".*/portal-shell/wip-detail\\?.*workcenter=.*"))
        detail_response = _wait_for_response(
            page,
            lambda resp: (
                "/api/wip/detail/" in resp.url
                and parse_qs(urlparse(resp.url).query).get("status", [None])[0] in {"QUEUE", "queue"}
            ),
            timeout_seconds=30.0,
        )
        assert detail_response is not None
        assert detail_response.ok

        reason = _pick_hold_reason(app_server)
        page.goto(
            f"{app_server}/portal-shell/hold-detail?reason={quote(reason)}",
            wait_until="commit",
            timeout=60000,
        )
        expect(page).to_have_url(re.compile(r".*/portal-shell/hold-detail\\?.*reason=.*"))
        summary_response = _wait_for_response(
            page,
            lambda resp: (
                "/api/wip/hold-detail/summary" in resp.url
                and parse_qs(urlparse(resp.url).query).get("reason", [None])[0] == reason
            ),
            timeout_seconds=30.0,
        )
        assert summary_response is not None
        assert summary_response.ok

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
