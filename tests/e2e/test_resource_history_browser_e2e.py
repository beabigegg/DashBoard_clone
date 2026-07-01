# -*- coding: utf-8 -*-
"""Browser E2E tests for the resource-history page."""

import pytest
import requests
from playwright.sync_api import Page, expect

from tests.e2e.browser_helpers import goto_shell_route, wait_for_any_visible


@pytest.mark.e2e
class TestResourceHistoryBrowserE2E:
    """Resource-history should auto-run its primary query and render results."""

    def test_resource_history_page_loads_primary_dashboard(self, page: Page, app_server: str):
        options_resp = requests.get(f"{app_server}/api/resource/history/options", timeout=60)
        if options_resp.status_code != 200:
            pytest.skip(f"Resource history options unavailable: {options_resp.status_code}")

        goto_shell_route(page, app_server, "/resource-history", "設備歷史績效")
        # resource-history has no page-title heading — "設備歷史績效" only
        # exists as the sidebar nav link text.
        wait_for_any_visible(
            page,
            [
                "text=明細資料",
                ".ui-table-wrap",
                ".section-card",
            ],
            timeout_ms=180000,
        )
        expect(page.locator("text=明細資料")).to_be_visible()
