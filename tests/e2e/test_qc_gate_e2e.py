# -*- coding: utf-8 -*-
"""Browser E2E tests for the QC-GATE page."""

import pytest
import requests
from playwright.sync_api import Page, expect

from tests.e2e.browser_helpers import goto_shell_route, wait_for_any_visible


@pytest.mark.e2e
class TestQcGateBrowserE2E:
    """QC-GATE page should render its primary dashboard content."""

    def test_qc_gate_page_loads_summary_and_lot_table(self, page: Page, app_server: str):
        summary_resp = requests.get(f"{app_server}/api/qc-gate/summary", timeout=60)
        if summary_resp.status_code != 200:
            pytest.skip(f"QC-GATE summary unavailable: {summary_resp.status_code}")

        goto_shell_route(page, app_server, "/qc-gate", "QC-GATE 狀態")
        # QC-GATE has no page-title heading (only section titles below) —
        # "QC-GATE 狀態" only exists as the sidebar nav link text.
        expect(page.locator("text=站點等待時間分布")).to_be_visible()
        expect(page.locator("text=LOT 明細")).to_be_visible()

        wait_for_any_visible(
            page,
            [
                ".qc-gate-chart .chart-canvas",
                ".qc-gate-page .empty-state",
                ".lot-table-wrap table",
            ],
            timeout_ms=120000,
        )
        expect(page.locator(".lot-table-wrap")).to_be_visible()
