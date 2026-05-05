# -*- coding: utf-8 -*-
"""Frontend stress tests using Playwright.

Tests frontend stability under high-frequency operations:
- Toast notification system under rapid fire
- MesApi client under rapid requests
- AbortController behavior
- Page navigation stress

Run with: pytest tests/stress/test_frontend_stress.py -v -s
"""

import pytest
import time
import requests
from urllib.parse import quote
from playwright.sync_api import Page, expect


@pytest.fixture(scope="session")
def app_server() -> str:
    """Get the base URL for stress testing."""
    import os
    return os.environ.get('STRESS_TEST_URL', 'http://127.0.0.1:8080')


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """Configure browser context for stress tests."""
    return {
        **browser_context_args,
        "viewport": {"width": 1280, "height": 720},
        "locale": "zh-TW",
    }


def load_page_with_js(page: Page, url: str, timeout: int = 60000):
    """Load page and wait for JS to initialize."""
    page.goto(url, wait_until='domcontentloaded', timeout=timeout)
    page.wait_for_timeout(1000)  # Allow JS initialization


def locate_portal_nav_links(page: Page):
    """Locate portal navigation links across legacy/new shell DOM contracts."""
    return page.locator('.drawer-link[href], .sidebar-item[data-route]')


@pytest.mark.stress
class TestToastStress:
    """Stress tests for Toast notification system."""

    def test_rapid_toast_creation(self, page: Page, app_server: str):
        """Test Toast system under rapid creation - should enforce max limit."""
        load_page_with_js(page, f"{app_server}/tables")

        # Create 50 toasts rapidly
        start_time = time.time()
        for i in range(50):
            page.evaluate(f"Toast.info('Rapid toast {i}')")

        creation_time = time.time() - start_time
        print(f"\n  Created 50 toasts in {creation_time:.3f}s")

        page.wait_for_timeout(500)

        # Should only have max 5 toasts visible
        toast_count = page.locator('.mes-toast').count()
        assert toast_count <= 5, f"Toast count {toast_count} exceeds max limit of 5"
        print(f"  Toast count enforced: {toast_count} (max 5)")

    def test_toast_type_cycling(self, page: Page, app_server: str):
        """Test rapid cycling through all toast types - system remains stable."""
        load_page_with_js(page, f"{app_server}/tables")

        toast_types = ['info', 'success', 'warning', 'error']

        start_time = time.time()
        for i in range(100):
            toast_type = toast_types[i % len(toast_types)]
            page.evaluate(f"Toast.{toast_type}('Type cycle {i}')")

        cycle_time = time.time() - start_time
        print(f"\n  Cycled 100 toasts in {cycle_time:.3f}s")

        # Wait for animations to complete
        page.wait_for_timeout(1000)

        # Dismiss all and verify system can recover
        page.evaluate("Toast.dismissAll()")
        page.wait_for_timeout(500)

        toast_count = page.locator('.mes-toast').count()
        assert toast_count <= 5, f"Toast overflow after dismissAll: {toast_count}"
        print(f"  System stable after cleanup, toast count: {toast_count}")

    def test_toast_dismiss_stress(self, page: Page, app_server: str):
        """Test rapid toast creation and dismissal."""
        load_page_with_js(page, f"{app_server}/tables")

        start_time = time.time()

        # Create and immediately dismiss
        for i in range(30):
            toast_id = page.evaluate(f"Toast.info('Dismiss test {i}')")
            page.evaluate(f"Toast.dismiss({toast_id})")

        dismiss_time = time.time() - start_time
        print(f"\n  Created and dismissed 30 toasts in {dismiss_time:.3f}s")

        page.wait_for_timeout(500)

        # Should have no or few toasts
        toast_count = page.locator('.mes-toast').count()
        assert toast_count <= 2, f"Undismissed toasts remain: {toast_count}"
        print(f"  Remaining toasts: {toast_count}")

    def test_loading_toast_stress(self, page: Page, app_server: str):
        """Test loading toasts can be created and properly dismissed."""
        load_page_with_js(page, f"{app_server}/tables")

        toast_ids = []

        # Create 10 loading toasts
        for i in range(10):
            toast_id = page.evaluate(f"Toast.loading('Loading {i}...')")
            toast_ids.append(toast_id)

        page.wait_for_timeout(200)

        # Loading toasts are created
        loading_count = page.locator('.mes-toast-loading').count()
        print(f"\n  Created {len(toast_ids)} loading toasts, visible: {loading_count}")

        # Dismiss all using dismissAll
        page.evaluate("Toast.dismissAll()")
        page.wait_for_timeout(500)

        # All should be gone after dismissAll
        loading_count = page.locator('.mes-toast-loading').count()
        assert loading_count == 0, f"Loading toasts not dismissed: {loading_count}"
        print("  Loading toast dismiss test passed")


@pytest.mark.stress
class TestMesApiStress:
    """Stress tests for MesApi client."""

    def test_rapid_api_requests(self, page: Page, app_server: str):
        """Test MesApi under rapid sequential requests."""
        load_page_with_js(page, f"{app_server}/tables")

        # Make 20 rapid API requests
        results = page.evaluate("""
            async () => {
                const results = [];
                const startTime = Date.now();

                for (let i = 0; i < 20; i++) {
                    try {
                        const response = await MesApi.get('/api/wip/meta/workcenters');
                        results.push({ success: true, status: response?.status || 'ok' });
                    } catch (e) {
                        results.push({ success: false, error: e.message });
                    }
                }

                return {
                    results,
                    duration: Date.now() - startTime,
                    successCount: results.filter(r => r.success).length
                };
            }
        """)

        print(f"\n  20 requests in {results['duration']}ms")
        print(f"  Success: {results['successCount']}/20")

        assert results['successCount'] >= 15, f"Too many failures: {20 - results['successCount']}"

    def test_concurrent_api_requests(self, page: Page, app_server: str):
        """Test MesApi with concurrent requests using Promise.all."""
        load_page_with_js(page, f"{app_server}/tables")

        # Make 10 concurrent requests
        results = page.evaluate("""
            async () => {
                const endpoints = [
                    '/api/wip/overview/summary',
                    '/api/wip/overview/matrix',
                    '/api/wip/meta/workcenters',
                    '/api/wip/meta/packages',
                ];

                const startTime = Date.now();
                const promises = [];

                // 2 requests per endpoint = 8 total concurrent
                for (const endpoint of endpoints) {
                    promises.push(MesApi.get(endpoint).catch(e => ({ error: e.message })));
                    promises.push(MesApi.get(endpoint).catch(e => ({ error: e.message })));
                }

                const results = await Promise.all(promises);
                const successCount = results.filter(r => !r.error).length;

                return {
                    duration: Date.now() - startTime,
                    total: results.length,
                    successCount
                };
            }
        """)

        print(f"\n  {results['total']} concurrent requests in {results['duration']}ms")
        print(f"  Success: {results['successCount']}/{results['total']}")

        assert results['successCount'] >= 6, "Too many concurrent failures"

    def test_abort_controller_stress(self, page: Page, app_server: str):
        """Test AbortController under rapid request cancellation."""
        load_page_with_js(page, f"{app_server}/tables")

        # Start requests and cancel them rapidly
        results = page.evaluate("""
            async () => {
                const results = { started: 0, aborted: 0, completed: 0, errors: 0 };

                for (let i = 0; i < 10; i++) {
                    results.started++;

                    const controller = new AbortController();

                    const request = fetch('/api/wip/overview/summary', {
                        signal: controller.signal
                    }).then(() => {
                        results.completed++;
                    }).catch(e => {
                        if (e.name === 'AbortError') {
                            results.aborted++;
                        } else {
                            results.errors++;
                        }
                    });

                    // Cancel after 50ms
                    setTimeout(() => controller.abort(), 50);

                    await new Promise(resolve => setTimeout(resolve, 100));
                }

                return results;
            }
        """)

        print(f"\n  Started: {results['started']}")
        print(f"  Aborted: {results['aborted']}")
        print(f"  Completed: {results['completed']}")
        print(f"  Errors: {results['errors']}")

        # Most should either abort or complete
        total_resolved = results['aborted'] + results['completed']
        assert total_resolved >= 5, "Too many unresolved requests"


@pytest.mark.stress
class TestPageNavigationStress:
    """Stress tests for rapid route navigation."""

    def test_rapid_route_switching(self, page: Page, app_server: str):
        """Rapid direct-route switching should remain responsive."""
        page.goto(app_server, wait_until='domcontentloaded', timeout=30000)
        page.wait_for_timeout(2000)  # Allow Vue router to resolve auth state
        if "login" in page.url:
            pytest.skip("Unauthenticated — portal redirected to login; run with active session")
        sidebar_items = locate_portal_nav_links(page)
        visible = sidebar_items.first.is_visible()
        if not visible:
            pytest.skip("Sidebar navigation not visible — likely unauthenticated or SPA not loaded")
        expect(sidebar_items.first).to_be_visible()
        item_count = sidebar_items.count()
        assert item_count >= 1, "No portal sidebar routes available for stress test"

        route_hrefs = []
        checked = min(item_count, 5)
        for idx in range(checked):
            href = sidebar_items.nth(idx).get_attribute('href')
            if href and href.startswith('/'):
                route_hrefs.append(href)

        assert route_hrefs, "Unable to resolve route hrefs from sidebar"

        js_errors = []
        page.on("pageerror", lambda error: js_errors.append(str(error)))

        start_time = time.time()
        for i in range(20):
            page.goto(f"{app_server}{route_hrefs[i % len(route_hrefs)]}", wait_until='domcontentloaded', timeout=60000)
            expect(page.locator('body')).to_be_visible()
            page.wait_for_timeout(80)

        switch_time = time.time() - start_time
        print(f"\n  20 route switches in {switch_time:.3f}s")
        assert len(js_errors) == 0, f"JS errors detected during route switching: {js_errors[:3]}"

    def test_portal_navigation_contract_without_iframe(self, page: Page, app_server: str):
        """Portal sidebar should expose route metadata and no iframe DOM."""
        page.goto(app_server, wait_until='domcontentloaded', timeout=30000)
        page.wait_for_timeout(2000)  # Allow Vue router to resolve auth state
        if "login" in page.url:
            pytest.skip("Unauthenticated — portal redirected to login; run with active session")
        sidebar_items = locate_portal_nav_links(page)
        if not sidebar_items.first.is_visible():
            pytest.skip("Sidebar navigation not visible — likely unauthenticated or SPA not loaded")
        expect(sidebar_items.first).to_be_visible()
        assert sidebar_items.count() >= 1, "No route sidebar items found"

        iframe_count = page.locator('iframe').count()
        assert iframe_count == 0, "Portal should not render iframe after migration"

        for idx in range(min(sidebar_items.count(), 3)):
            href = sidebar_items.nth(idx).get_attribute('href')
            assert href and href.startswith('/'), f"Invalid sidebar href: {href}"

        print("\n  Portal route sidebar contract verified without iframe")


@pytest.mark.stress
class TestWipHoldPageStress:
    """Stress tests focused on WIP Overview / WIP Detail / Hold Detail pages."""

    def _pick_workcenter(self, app_server: str) -> str:
        """Get one available workcenter for WIP detail tests."""
        try:
            response = requests.get(f"{app_server}/api/wip/meta/workcenters", timeout=10)
            if response.status_code != 200:
                return "TMTT"
            payload = response.json()
            items = payload.get("data") or []
            if not items:
                return "TMTT"
            return str(items[0].get("name") or "TMTT")
        except Exception:
            return "TMTT"

    def _pick_reason(self, app_server: str) -> str:
        """Get one hold reason for hold-detail tests."""
        try:
            response = requests.get(f"{app_server}/api/wip/overview/hold", timeout=10)
            if response.status_code != 200:
                return "YieldLimit"
            payload = response.json()
            items = (payload.get("data") or {}).get("items") or []
            if not items:
                return "YieldLimit"
            return str(items[0].get("reason") or "YieldLimit")
        except Exception:
            return "YieldLimit"

    def test_rapid_navigation_across_wip_and_hold_pages(self, page: Page, app_server: str):
        """Rapid page switching should keep pages responsive and error-free."""
        workcenter = self._pick_workcenter(app_server)
        reason = self._pick_reason(app_server)

        urls = [
            f"{app_server}/wip-overview",
            f"{app_server}/wip-overview?type=PJA3460&status=queue",
            f"{app_server}/wip-detail?workcenter={quote(workcenter)}&type=PJA3460&status=queue",
            f"{app_server}/hold-detail?reason={quote(reason)}",
        ]

        js_errors = []
        page.on("pageerror", lambda error: js_errors.append(str(error)))

        start_time = time.time()
        for i in range(16):
            page.goto(urls[i % len(urls)], wait_until='domcontentloaded', timeout=60000)
            expect(page.locator("body")).to_be_visible()
            page.wait_for_timeout(150)

        elapsed = time.time() - start_time
        print(f"\n  Rapid navigation across 3 pages completed in {elapsed:.2f}s")

        assert len(js_errors) == 0, f"JavaScript errors detected: {js_errors[:3]}"

    def test_wip_and_hold_api_burst_from_browser(self, page: Page, app_server: str):
        """Browser-side API burst should still return mostly successful responses."""
        load_page_with_js(page, f"{app_server}/wip-overview")

        result = page.evaluate("""
            async () => {
                const safeJson = async (resp) => {
                    try {
                        return await resp.json();
                    } catch (_) {
                        return null;
                    }
                };

                const wcResp = await fetch('/api/wip/meta/workcenters');
                const wcPayload = await safeJson(wcResp) || {};
                const workcenter = (wcPayload.data && wcPayload.data[0] && wcPayload.data[0].name) || 'TMTT';

                const holdResp = await fetch('/api/wip/overview/hold');
                const holdPayload = await safeJson(holdResp) || {};
                const holdItems = (holdPayload.data && holdPayload.data.items) || [];
                const reason = (holdItems[0] && holdItems[0].reason) || 'YieldLimit';

                const endpoints = [
                    '/api/wip/overview/summary',
                    '/api/wip/overview/matrix',
                    '/api/wip/overview/hold',
                    `/api/wip/detail/${encodeURIComponent(workcenter)}?page=1&page_size=100`,
                    `/api/wip/hold-detail/lots?reason=${encodeURIComponent(reason)}&page=1&per_page=50`,
                ];

                let total = 0;
                let success = 0;
                let failures = 0;

                for (let round = 0; round < 5; round++) {
                    const responses = await Promise.all(
                        endpoints.map((endpoint) =>
                            fetch(endpoint)
                                .then((r) => ({ ok: r.status < 500 }))
                                .catch(() => ({ ok: false }))
                        )
                    );
                    total += responses.length;
                    success += responses.filter((r) => r.ok).length;
                    failures += responses.filter((r) => !r.ok).length;
                }

                return { total, success, failures };
            }
        """)

        print(f"\n  Browser burst total={result['total']}, success={result['success']}, failures={result['failures']}")
        assert result['success'] >= 20, f"Too many failed API requests: {result}"


@pytest.mark.stress
class TestMemoryStress:
    """Tests for memory leak detection."""

    def test_toast_memory_cleanup(self, page: Page, app_server: str):
        """Check Toast system cleans up properly."""
        load_page_with_js(page, f"{app_server}/tables")

        # Create and dismiss many toasts
        for batch in range(5):
            for i in range(20):
                page.evaluate(f"Toast.info('Memory test {batch}-{i}')")
            page.evaluate("Toast.dismissAll()")
            page.wait_for_timeout(100)

        page.wait_for_timeout(500)

        # Check DOM is clean
        toast_count = page.locator('.mes-toast').count()
        assert toast_count <= 5, f"Toast elements not cleaned up: {toast_count}"
        print(f"\n  Toast memory cleanup test passed (remaining: {toast_count})")


@pytest.mark.stress
class TestConsoleErrorMonitoring:
    """Monitor for JavaScript errors under stress."""

    def test_no_js_errors_under_stress(self, page: Page, app_server: str):
        """Verify no JavaScript errors occur under stress conditions."""
        js_errors = []

        page.on("pageerror", lambda error: js_errors.append(str(error)))

        load_page_with_js(page, f"{app_server}/tables")

        # Perform stress operations
        for i in range(30):
            page.evaluate(f"Toast.info('Error check {i}')")

        for i in range(10):
            page.evaluate("""
                MesApi.get('/api/wip/overview/summary').catch(() => {})
            """)

        page.wait_for_timeout(2000)

        if js_errors:
            print("\n  JavaScript errors detected:")
            for err in js_errors[:5]:
                print(f"    - {err[:100]}")

        assert len(js_errors) == 0, f"Found {len(js_errors)} JavaScript errors"
        print("\n  No JavaScript errors under stress")
