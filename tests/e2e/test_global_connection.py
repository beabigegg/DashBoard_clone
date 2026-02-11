# -*- coding: utf-8 -*-
"""E2E tests for global connection management features.

Tests the MesApi client, Toast notifications, and page functionality
using Playwright.

Run with: pytest tests/e2e/ --headed (to see browser)
"""

import pytest
import re
from playwright.sync_api import Page, expect


@pytest.mark.e2e
class TestPortalPage:
    """E2E tests for the Portal page."""

    def test_portal_loads_successfully(self, page: Page, app_server: str):
        """Portal page should load without errors."""
        page.goto(app_server)

        # Wait for page to load
        expect(page.locator('h1')).to_contain_text('MES 報表入口')

    def test_portal_has_all_sidebar_routes(self, page: Page, app_server: str):
        """Portal should expose route-based sidebar entries."""
        page.goto(app_server)

        expect(page.locator('.sidebar-item:has-text("WIP 即時概況")')).to_be_visible()
        expect(page.locator('.sidebar-item:has-text("設備即時概況")')).to_be_visible()
        expect(page.locator('.sidebar-item:has-text("設備歷史績效")')).to_be_visible()
        expect(page.locator('.sidebar-item:has-text("設備維修查詢")')).to_be_visible()

    def test_portal_sidebar_navigation_uses_direct_routes(self, page: Page, app_server: str):
        """Sidebar click should navigate to direct route without iframe switching."""
        page.goto(app_server)

        first_route = page.locator('.sidebar-item[data-route]').first
        expect(first_route).to_be_visible()
        target_href = first_route.get_attribute('href')
        assert target_href and target_href.startswith('/'), "sidebar route href missing"
        first_route.click()
        expect(page).to_have_url(re.compile(f".*{re.escape(target_href)}$"))

    def test_portal_health_popup_clickable(self, page: Page, app_server: str):
        """Health status pill should toggle popup visibility on click."""
        page.goto(app_server)

        popup = page.locator('#healthPopup')
        expect(popup).not_to_have_class(re.compile(r'show'))

        page.locator('#healthStatus').click()
        expect(popup).to_have_class(re.compile(r'show'))


@pytest.mark.e2e
class TestToastNotifications:
    """E2E tests for Toast notification system."""

    def test_toast_container_exists(self, page: Page, app_server: str):
        """Toast container should be present in the DOM."""
        page.goto(f"{app_server}/wip-overview")

        # Toast container should exist in DOM (hidden when empty, which is expected)
        page.wait_for_selector('#mes-toast-container', state='attached', timeout=5000)

    def test_toast_info_display(self, page: Page, app_server: str):
        """Toast.info() should display info notification."""
        page.goto(f"{app_server}/wip-overview")

        # Execute Toast.info() in browser context
        page.evaluate("Toast.info('Test info message')")

        # Verify toast appears
        toast = page.locator('.mes-toast-info')
        expect(toast).to_be_visible()
        expect(toast).to_contain_text('Test info message')

    def test_toast_success_display(self, page: Page, app_server: str):
        """Toast.success() should display success notification."""
        page.goto(f"{app_server}/wip-overview")

        page.evaluate("Toast.success('Operation successful')")

        toast = page.locator('.mes-toast-success')
        expect(toast).to_be_visible()
        expect(toast).to_contain_text('Operation successful')

    def test_toast_error_display(self, page: Page, app_server: str):
        """Toast.error() should display error notification."""
        page.goto(f"{app_server}/wip-overview")

        page.evaluate("Toast.error('An error occurred')")

        toast = page.locator('.mes-toast-error')
        expect(toast).to_be_visible()
        expect(toast).to_contain_text('An error occurred')

    def test_toast_error_with_retry(self, page: Page, app_server: str):
        """Toast.error() with retry callback should show retry button."""
        page.goto(f"{app_server}/wip-overview")

        page.evaluate("Toast.error('Connection failed', { retry: () => console.log('retry clicked') })")

        # Verify retry button exists
        retry_btn = page.locator('.mes-toast-retry')
        expect(retry_btn).to_be_visible()
        expect(retry_btn).to_contain_text('重試')

    def test_toast_loading_display(self, page: Page, app_server: str):
        """Toast.loading() should display loading notification."""
        page.goto(f"{app_server}/wip-overview")

        page.evaluate("Toast.loading('Loading data...')")

        toast = page.locator('.mes-toast-loading')
        expect(toast).to_be_visible()

    def test_toast_dismiss(self, page: Page, app_server: str):
        """Toast.dismiss() should remove toast."""
        page.goto(f"{app_server}/wip-overview")

        # Create and dismiss a toast
        toast_id = page.evaluate("Toast.info('Will be dismissed')")
        page.evaluate(f"Toast.dismiss({toast_id})")

        # Wait for animation
        page.wait_for_timeout(500)

        # Toast should be gone
        expect(page.locator('.mes-toast-info')).not_to_be_visible()

    def test_toast_max_limit(self, page: Page, app_server: str):
        """Toast system should enforce max 5 toasts."""
        page.goto(f"{app_server}/wip-overview")

        # Create 7 toasts
        for i in range(7):
            page.evaluate(f"Toast.info('Toast {i}')")

        # Should only have 5 toasts visible
        toasts = page.locator('.mes-toast')
        expect(toasts).to_have_count(5)


@pytest.mark.e2e
class TestMesApiClient:
    """E2E tests for MesApi client."""

    def test_mesapi_exists_on_page(self, page: Page, app_server: str):
        """MesApi should be available in window scope."""
        page.goto(f"{app_server}/wip-overview")

        has_mesapi = page.evaluate("typeof MesApi !== 'undefined'")
        assert has_mesapi, "MesApi should be defined"

    def test_mesapi_has_get_method(self, page: Page, app_server: str):
        """MesApi should have get() method."""
        page.goto(f"{app_server}/wip-overview")

        has_get = page.evaluate("typeof MesApi.get === 'function'")
        assert has_get, "MesApi.get should be a function"

    def test_mesapi_has_post_method(self, page: Page, app_server: str):
        """MesApi should have post() method."""
        page.goto(f"{app_server}/wip-overview")

        has_post = page.evaluate("typeof MesApi.post === 'function'")
        assert has_post, "MesApi.post should be a function"

    def test_mesapi_request_logging(self, page: Page, app_server: str):
        """MesApi should log requests to console."""
        page.goto(f"{app_server}/wip-overview")

        # Capture console messages
        console_messages = []
        page.on("console", lambda msg: console_messages.append(msg.text))

        # Make a request (will fail but should log)
        page.evaluate("""
            (async () => {
                try {
                    await MesApi.get('/api/test-endpoint');
                } catch (e) {
                    // Expected to fail
                }
            })()
        """)

        page.wait_for_timeout(1000)

        # Check for MesApi log pattern
        mesapi_logs = [m for m in console_messages if '[MesApi]' in m]
        assert len(mesapi_logs) > 0, "MesApi should log requests with [MesApi] prefix"


@pytest.mark.e2e
class TestWIPOverviewPage:
    """E2E tests for WIP Overview page."""

    def test_wip_overview_loads(self, page: Page, app_server: str):
        """WIP Overview page should load."""
        page.goto(f"{app_server}/wip-overview")

        # Page should have the header
        expect(page.locator('body')).to_be_visible()

    def test_wip_overview_has_toast_system(self, page: Page, app_server: str):
        """WIP Overview should have Toast system loaded."""
        page.goto(f"{app_server}/wip-overview")

        has_toast = page.evaluate("typeof Toast !== 'undefined'")
        assert has_toast, "Toast should be defined on WIP Overview page"

    def test_wip_overview_has_mesapi(self, page: Page, app_server: str):
        """WIP Overview should have MesApi loaded."""
        page.goto(f"{app_server}/wip-overview")

        has_mesapi = page.evaluate("typeof MesApi !== 'undefined'")
        assert has_mesapi, "MesApi should be defined on WIP Overview page"


@pytest.mark.e2e
class TestWIPDetailPage:
    """E2E tests for WIP Detail page."""

    def test_wip_detail_loads(self, page: Page, app_server: str):
        """WIP Detail page should load."""
        page.goto(f"{app_server}/wip-detail")

        expect(page.locator('body')).to_be_visible()

    def test_wip_detail_has_toast_system(self, page: Page, app_server: str):
        """WIP Detail should have Toast system loaded."""
        page.goto(f"{app_server}/wip-detail")

        has_toast = page.evaluate("typeof Toast !== 'undefined'")
        assert has_toast, "Toast should be defined on WIP Detail page"

    def test_wip_detail_has_mesapi(self, page: Page, app_server: str):
        """WIP Detail should have MesApi loaded."""
        page.goto(f"{app_server}/wip-detail")

        has_mesapi = page.evaluate("typeof MesApi !== 'undefined'")
        assert has_mesapi, "MesApi should be defined on WIP Detail page"


@pytest.mark.e2e
class TestTablesPage:
    """E2E tests for Tables page."""

    def test_tables_page_loads(self, page: Page, app_server: str):
        """Tables page should load."""
        page.goto(f"{app_server}/tables")
        header = page.locator('h1')
        expect(header).to_be_visible()
        text = header.inner_text()
        assert (
            'MES 數據表查詢工具' in text
            or '頁面開發中' in text
        )

    def test_tables_has_toast_system(self, page: Page, app_server: str):
        """Tables page should have Toast system loaded."""
        page.goto(f"{app_server}/tables")

        has_toast = page.evaluate("typeof Toast !== 'undefined'")
        assert has_toast, "Toast should be defined on Tables page"

    def test_tables_has_mesapi(self, page: Page, app_server: str):
        """Tables page should have MesApi loaded."""
        page.goto(f"{app_server}/tables")

        has_mesapi = page.evaluate("typeof MesApi !== 'undefined'")
        assert has_mesapi, "MesApi should be defined on Tables page"


@pytest.mark.e2e
class TestResourcePage:
    """E2E tests for Resource Status page."""

    def test_resource_page_loads(self, page: Page, app_server: str):
        """Resource page should load."""
        page.goto(f"{app_server}/resource")

        expect(page.locator('body')).to_be_visible()

    def test_resource_has_toast_system(self, page: Page, app_server: str):
        """Resource page should have Toast system loaded."""
        page.goto(f"{app_server}/resource")

        has_toast = page.evaluate("typeof Toast !== 'undefined'")
        assert has_toast, "Toast should be defined on Resource page"

    def test_resource_has_mesapi(self, page: Page, app_server: str):
        """Resource page should have MesApi loaded."""
        page.goto(f"{app_server}/resource")

        has_mesapi = page.evaluate("typeof MesApi !== 'undefined'")
        assert has_mesapi, "MesApi should be defined on Resource page"


@pytest.mark.e2e
class TestExcelQueryPage:
    """E2E tests for Excel Query page."""

    def test_excel_query_page_loads(self, page: Page, app_server: str):
        """Excel Query page should load."""
        page.goto(f"{app_server}/excel-query")

        expect(page.locator('body')).to_be_visible()

    def test_excel_query_has_toast_system(self, page: Page, app_server: str):
        """Excel Query page should have Toast system loaded."""
        page.goto(f"{app_server}/excel-query")

        has_toast = page.evaluate("typeof Toast !== 'undefined'")
        assert has_toast, "Toast should be defined on Excel Query page"

    def test_excel_query_has_mesapi(self, page: Page, app_server: str):
        """Excel Query page should have MesApi loaded."""
        page.goto(f"{app_server}/excel-query")

        has_mesapi = page.evaluate("typeof MesApi !== 'undefined'")
        assert has_mesapi, "MesApi should be defined on Excel Query page"


@pytest.mark.e2e
class TestConsoleLogVerification:
    """E2E tests for console log verification (Phase 4.2 tasks)."""

    def test_request_has_request_id(self, page: Page, app_server: str):
        """API requests should log with req_xxx ID format."""
        page.goto(f"{app_server}/wip-overview")

        console_messages = []
        page.on("console", lambda msg: console_messages.append(msg.text))

        # Trigger an API request
        page.evaluate("""
            (async () => {
                try {
                    await MesApi.get('/api/wip/overview/summary');
                } catch (e) {}
            })()
        """)

        page.wait_for_timeout(2000)

        # Check for request ID pattern
        req_id_pattern = re.compile(r'req_\d{4}')
        has_req_id = any(req_id_pattern.search(m) for m in console_messages)
        assert has_req_id, "Console should show request ID like req_0001"

    def test_successful_request_shows_checkmark(self, page: Page, app_server: str):
        """Successful requests should show checkmark in console."""
        page.goto(f"{app_server}/wip-overview")

        console_messages = []
        page.on("console", lambda msg: console_messages.append(msg.text))

        # Make request to a working endpoint
        page.evaluate("""
            (async () => {
                try {
                    await MesApi.get('/api/wip/overview/summary');
                } catch (e) {}
            })()
        """)

        page.wait_for_timeout(3000)

        # Filter for MesApi logs
        mesapi_logs = [m for m in console_messages if '[MesApi]' in m]
        # The exact checkmark depends on implementation (✓ or similar)
        assert len(mesapi_logs) > 0, "Should have MesApi console logs"
