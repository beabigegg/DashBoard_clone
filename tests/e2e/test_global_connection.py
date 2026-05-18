# -*- coding: utf-8 -*-
"""E2E tests for SPA shell navigation/runtime contracts."""

import pytest
import re
from playwright.sync_api import Page, expect

from tests.e2e.browser_helpers import ensure_shell_admin, goto_shell_route


def _sidebar_links(page: Page):
    """Support both legacy and current shell nav selectors."""
    return page.locator("a.drawer-link[href], a.sidebar-item[data-route]")


def _fetch_json_status(page: Page, url: str):
    """Run fetch in browser context and return status/payload metadata."""
    return page.evaluate(
        """
        async (targetUrl) => {
            const response = await fetch(targetUrl, { cache: 'no-store' });
            let payload = null;
            try {
                payload = await response.json();
            } catch (_) {
                payload = null;
            }
            return { ok: response.ok, status: response.status, payload };
        }
        """,
        url,
    )


@pytest.mark.e2e
class TestPortalPage:
    """E2E tests for portal shell routing and drawer navigation."""

    def test_portal_loads_successfully(self, page: Page, app_server: str):
        goto_shell_route(page, app_server, "/wip-overview", "WIP 即時概況")
        expect(page.get_by_role("heading", name="MES 報表入口")).to_be_visible(timeout=30000)

    def test_portal_has_sidebar_routes(self, page: Page, app_server: str):
        goto_shell_route(page, app_server, "/wip-overview", "WIP 即時概況")

        expect(_sidebar_links(page).first).to_be_visible(timeout=30000)
        expect(page.locator(".drawer-link:has-text('WIP 即時概況')")).to_be_visible(timeout=30000)

    def test_portal_sidebar_navigation_uses_direct_routes(self, page: Page, app_server: str):
        goto_shell_route(page, app_server, "/wip-overview", "WIP 即時概況")

        first_route = _sidebar_links(page).first
        expect(first_route).to_be_visible(timeout=30000)
        target_href = first_route.get_attribute("href")
        assert target_href, "sidebar route href missing"

        first_route.click()
        expect(page).to_have_url(re.compile(f".*{re.escape(target_href)}$"))
        assert page.locator("iframe").count() == 0, "Shell content must not use iframe"

    def test_portal_health_popup_clickable(self, page: Page, app_server: str):
        goto_shell_route(page, app_server, "/wip-overview", "WIP 即時概況")

        trigger = page.locator(".health-trigger")
        expect(trigger).to_be_visible(timeout=30000)
        expect(page.locator("#shellHealthPopup")).to_have_count(0)

        trigger.click()
        expect(page.locator("#shellHealthPopup")).to_be_visible()

        page.keyboard.press("Escape")
        expect(page.locator("#shellHealthPopup")).to_have_count(0)


@pytest.mark.e2e
class TestFrontendApiRuntime:
    """E2E tests for runtime API availability in browser context."""

    def test_wip_overview_can_call_summary_api_via_fetch(self, page: Page, app_server: str):
        page.goto(f"{app_server}/wip-overview")
        result = _fetch_json_status(page, "/api/wip/overview/summary")
        assert result["ok"] is True
        assert result["status"] == 200
        assert isinstance(result.get("payload"), dict)

    def test_wip_detail_can_call_workcenter_api_via_fetch(self, page: Page, app_server: str):
        page.goto(f"{app_server}/wip-detail")
        result = _fetch_json_status(page, "/api/wip/meta/workcenters")
        assert result["ok"] is True
        assert result["status"] == 200
        assert isinstance(result.get("payload"), dict)

    def test_global_mesapi_bridge_is_optional(self, page: Page, app_server: str):
        page.goto(f"{app_server}/wip-overview")

        runtime = page.evaluate(
            """
            () => ({
                hasFetch: typeof window.fetch === 'function',
                hasMesApi: typeof window.MesApi !== 'undefined',
                hasMesApiGet: Boolean(window.MesApi && typeof window.MesApi.get === 'function'),
            })
            """
        )
        assert runtime["hasFetch"] is True
        if runtime["hasMesApi"]:
            assert runtime["hasMesApiGet"] is True


@pytest.mark.e2e
class TestRoutePagesSmoke:
    """Basic smoke checks for key route pages."""

    def test_wip_overview_loads(self, page: Page, app_server: str):
        response = page.goto(f"{app_server}/wip-overview")
        assert response is not None and response.ok
        expect(page.locator("body")).to_be_visible()

    def test_wip_detail_loads(self, page: Page, app_server: str):
        response = page.goto(f"{app_server}/wip-detail")
        assert response is not None and response.ok
        expect(page.locator("body")).to_be_visible()

    def test_resource_page_loads(self, page: Page, app_server: str):
        response = page.goto(f"{app_server}/resource")
        assert response is not None and response.ok
        expect(page.locator("body")).to_be_visible()

@pytest.mark.e2e
class TestConsoleAndErrorSignals:
    """Console/pageerror checks for SPA runtime stability."""

    def test_wip_overview_has_no_uncaught_page_errors(self, page: Page, app_server: str):
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(f"{app_server}/wip-overview")
        page.wait_for_timeout(2000)
        assert errors == [], f"Unexpected page errors: {errors[:3]}"

    def test_wip_overview_triggers_expected_api_requests(self, page: Page, app_server: str):
        observed = set()

        def on_response(resp):
            if "/api/wip/overview/summary" in resp.url:
                observed.add("summary")
            if "/api/wip/overview/matrix" in resp.url:
                observed.add("matrix")

        ensure_shell_admin(page, "/wip-overview", "WIP 即時概況")
        page.on("response", on_response)
        page.goto(f"{app_server}/portal-shell/wip-overview", wait_until="domcontentloaded")

        page.wait_for_timeout(8000)
        assert "summary" in observed
        assert "matrix" in observed
