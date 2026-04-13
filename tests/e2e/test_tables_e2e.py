# -*- coding: utf-8 -*-
"""Browser E2E tests for the Tables page."""

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.browser_helpers import goto_shell_route, wait_for_any_visible


@pytest.mark.e2e
class TestTablesBrowserE2E:
    """Tables page should support selecting a table and querying rows."""

    def test_tables_page_selects_table_and_runs_query(self, page: Page, app_server: str):
        goto_shell_route(page, app_server, "/tables", "表格總覽")
        expect(page.get_by_role("heading", name="MES 數據表查詢工具")).to_be_visible()

        first_card = page.locator(".table-card").first
        expect(first_card).to_be_visible(timeout=60000)
        first_card.click()

        expect(page.locator(".data-viewer")).to_be_visible(timeout=60000)
        expect(page.locator(".viewer-header h3")).to_be_visible()

        query_button = page.locator(".data-viewer .query-btn").first
        expect(query_button).to_be_enabled()
        query_button.click()

        wait_for_any_visible(
            page,
            [
                ".data-viewer thead th",
                "text=查無資料",
                "text=請輸入篩選條件後點擊「查詢」",
            ],
            timeout_ms=120000,
        )
        assert page.locator(".data-viewer thead th").count() > 0
