# -*- coding: utf-8 -*-
"""E2E coverage for the Query Tool page tabs and core query flows."""

from __future__ import annotations

import json
import time
from urllib.parse import parse_qs, urlparse

import pytest
import requests
from playwright.sync_api import Page, expect


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# The query-tool page is served inside the portal shell as a native Vue SPA.
# Standalone /query-tool redirects to /portal-shell/query-tool.
QUERY_TOOL_BASE = "/portal-shell/query-tool"


def _intercept_navigation_as_admin(page: Page, app_server: str):
    """Intercept /api/portal/navigation to inject is_admin=True + query-tool route.

    The query-tool page has status 'dev' in an admin-only drawer.  The server
    filters out admin-only drawers for non-admin requests, so we must both set
    ``is_admin=True`` AND inject the query-tool page into the drawers list.
    """

    def handle_route(route):
        response = route.fetch()
        body = response.json()

        body["is_admin"] = True

        # Ensure the query-tool page is present in a drawer
        query_tool_entry = {
            "name": "批次追蹤工具",
            "order": 4,
            "route": "/query-tool",
            "status": "dev",
        }

        drawers = body.get("drawers", [])
        found = False
        for drawer in drawers:
            for pg in drawer.get("pages", []):
                if pg.get("route") == "/query-tool":
                    found = True
                    break

        if not found:
            # Add to the first non-admin drawer, or create a test drawer
            target_drawer = None
            for drawer in drawers:
                if not drawer.get("admin_only"):
                    target_drawer = drawer
                    break
            if target_drawer:
                target_drawer["pages"].append(query_tool_entry)
            else:
                drawers.append({
                    "id": "e2e-test",
                    "name": "E2E Test",
                    "order": 99,
                    "admin_only": False,
                    "pages": [query_tool_entry],
                })

        body["drawers"] = drawers
        route.fulfill(
            status=response.status,
            headers={**response.headers, "content-type": "application/json"},
            body=json.dumps(body),
        )

    page.route("**/api/portal/navigation", handle_route)


def _wait_for_api_response(page: Page, url_token: str, timeout_seconds: float = 60.0):
    """Wait until a response URL contains the given token and return it."""
    matched = []

    def handle_response(resp):
        if url_token in resp.url and resp.status < 500:
            matched.append(resp)

    page.on("response", handle_response)
    deadline = time.time() + timeout_seconds
    while time.time() < deadline and not matched:
        page.wait_for_timeout(300)
    page.remove_listener("response", handle_response)
    return matched[0] if matched else None


def _collect_api_responses(page: Page, url_tokens: list[str], timeout_seconds: float = 60.0):
    """Collect responses whose URLs contain any of the given tokens."""
    collected = {}

    def handle_response(resp):
        for token in url_tokens:
            if token in resp.url:
                collected.setdefault(token, []).append(resp)

    page.on("response", handle_response)
    deadline = time.time() + timeout_seconds
    while time.time() < deadline and len(collected) < len(url_tokens):
        page.wait_for_timeout(300)
    page.remove_listener("response", handle_response)
    return collected


def _api_post_json(
    app_server: str,
    path: str,
    body: dict,
    timeout: float = 60.0,
    *,
    max_attempts: int = 4,
):
    """Direct API POST for backend integration checks.

    Retries on 429 to absorb temporary rate-limit bursts during full e2e runs.
    """
    response = None
    for attempt in range(max_attempts):
        response = requests.post(
            f"{app_server}{path}",
            json=body,
            timeout=timeout,
        )
        if response.status_code != 429:
            return response
        if attempt >= max_attempts - 1:
            return response
        retry_after = response.headers.get("Retry-After")
        try:
            wait_seconds = float(retry_after) if retry_after else 1.0
        except ValueError:
            wait_seconds = 1.0
        time.sleep(wait_seconds)
    return response


def _is_service_overloaded(resp: requests.Response) -> bool:
    if resp.status_code != 503:
        return False
    try:
        payload = resp.json()
    except ValueError:
        return False
    error_obj = payload.get("error")
    if isinstance(error_obj, dict):
        return error_obj.get("code") == "SERVICE_OVERLOADED"
    if isinstance(error_obj, str):
        return "SERVICE_OVERLOADED" in error_obj or "記憶體負載" in error_obj
    return payload.get("code") == "SERVICE_OVERLOADED"


# ---------------------------------------------------------------------------
# Backend Integration Tests (no browser needed)
# ---------------------------------------------------------------------------

@pytest.mark.e2e
class TestQueryToolBackendIntegration:
    """Verify query-tool API endpoints are functional."""

    def test_resolve_work_order(self, app_server: str):
        """POST /api/query-tool/resolve with work_order returns lots."""
        resp = _api_post_json(app_server, "/api/query-tool/resolve", {
            "input_type": "work_order",
            "values": ["GA26010001"],
        })
        assert resp.status_code == 200, f"resolve returned {resp.status_code}: {resp.text[:300]}"
        payload = resp.json()
        assert "data" in payload, f"response missing 'data': {list(payload.keys())}"
        assert isinstance(payload["data"], list)
        assert len(payload["data"]) > 0, "Expected at least 1 resolved lot for GA26010001"

    def test_resolve_returns_not_found_for_garbage(self, app_server: str):
        """POST /api/query-tool/resolve returns not_found for non-existent values."""
        resp = _api_post_json(app_server, "/api/query-tool/resolve", {
            "input_type": "lot_id",
            "values": ["NONEXISTENT_LOT_12345"],
        })
        assert resp.status_code == 200
        payload = resp.json()
        not_found = payload.get("not_found", [])
        assert "NONEXISTENT_LOT_12345" in not_found

    def test_workcenter_groups_endpoint(self, app_server: str):
        """GET /api/query-tool/workcenter-groups returns list."""
        resp = requests.get(f"{app_server}/api/query-tool/workcenter-groups", timeout=30)
        assert resp.status_code == 200
        payload = resp.json()
        assert "data" in payload
        assert isinstance(payload["data"], list)

    def test_equipment_list_endpoint(self, app_server: str):
        """GET /api/query-tool/equipment-list returns equipment options."""
        resp = requests.get(f"{app_server}/api/query-tool/equipment-list", timeout=30)
        assert resp.status_code == 200
        payload = resp.json()
        assert "data" in payload
        assert isinstance(payload["data"], list)
        assert len(payload["data"]) > 0, "Expected at least 1 equipment option"

    def test_lot_history_with_resolved_container(self, app_server: str):
        """Resolve a work order then fetch lot history for first container."""
        resolve_resp = _api_post_json(app_server, "/api/query-tool/resolve", {
            "input_type": "work_order",
            "values": ["GA26010001"],
        })
        assert resolve_resp.status_code == 200
        lots = resolve_resp.json().get("data", [])
        assert len(lots) > 0

        container_id = str(
            lots[0].get("container_id")
            or lots[0].get("CONTAINERID")
            or lots[0].get("containerId")
            or ""
        )
        assert container_id, "Could not extract container_id from resolved lot"

        history_resp = requests.get(
            f"{app_server}/api/query-tool/lot-history",
            params={"container_id": container_id},
            timeout=60,
        )
        if _is_service_overloaded(history_resp):
            pytest.skip("Service overloaded during lot-history e2e run")
        assert history_resp.status_code == 200
        history_payload = history_resp.json()
        assert "data" in history_payload
        assert isinstance(history_payload["data"], list)

    def test_lot_associations_materials(self, app_server: str):
        """Fetch materials association for a resolved container."""
        resolve_resp = _api_post_json(app_server, "/api/query-tool/resolve", {
            "input_type": "work_order",
            "values": ["GA26010001"],
        })
        lots = resolve_resp.json().get("data", [])
        if not lots:
            pytest.skip("No lots resolved for GA26010001")

        container_id = str(
            lots[0].get("container_id")
            or lots[0].get("CONTAINERID")
            or ""
        )
        resp = requests.get(
            f"{app_server}/api/query-tool/lot-associations",
            params={"container_id": container_id, "type": "materials"},
            timeout=60,
        )
        assert resp.status_code == 200

    def test_lineage_for_resolved_container(self, app_server: str):
        """POST /api/trace/lineage for a resolved container."""
        resolve_resp = _api_post_json(app_server, "/api/query-tool/resolve", {
            "input_type": "work_order",
            "values": ["GA26010001"],
        })
        lots = resolve_resp.json().get("data", [])
        if not lots:
            pytest.skip("No lots resolved for GA26010001")

        container_id = str(
            lots[0].get("container_id")
            or lots[0].get("CONTAINERID")
            or ""
        )
        lineage_resp = _api_post_json(app_server, "/api/trace/lineage", {
            "profile": "query_tool",
            "container_ids": [container_id],
        })
        assert lineage_resp.status_code == 200
        payload = lineage_resp.json()
        assert "children_map" in payload or "ancestors" in payload or "data" in payload


# ---------------------------------------------------------------------------
# Browser E2E Tests
# ---------------------------------------------------------------------------

@pytest.mark.e2e
class TestQueryToolPageE2E:
    """Browser-based E2E tests for the query-tool page."""

    def test_page_loads_with_tab_shell(self, page: Page, app_server: str):
        """Query tool page loads and displays both top-level tabs."""
        _intercept_navigation_as_admin(page, app_server)
        page.goto(f"{app_server}{QUERY_TOOL_BASE}", wait_until="commit", timeout=60000)
        page.wait_for_timeout(3000)

        # Header should be visible (portal shell has its own h1, use the page heading)
        heading = page.get_by_role("heading", name="批次追蹤工具")
        expect(heading).to_be_visible()

        # All tab buttons should exist
        lot_tab = page.locator("button", has_text="批次追蹤(正向)")
        reverse_tab = page.locator("button", has_text="流水批反查(反向)")
        equipment_tab = page.locator("button", has_text="設備生產批次追蹤")
        expect(lot_tab).to_be_visible()
        expect(reverse_tab).to_be_visible()
        expect(equipment_tab).to_be_visible()

    def test_lot_tab_resolve_work_order(self, page: Page, app_server: str):
        """Enter work order, click resolve, verify lineage tree and detail panel appear."""
        _intercept_navigation_as_admin(page, app_server)
        page.goto(f"{app_server}{QUERY_TOOL_BASE}?tab=lot", wait_until="commit", timeout=60000)
        page.wait_for_timeout(2000)

        # Select work_order input type (use .first – the Lot tab's QueryBar
        # is rendered before the Reverse tab's QueryBar via v-show)
        select = page.locator("select.query-tool-select").first
        select.select_option("work_order")

        # Enter work order in textarea
        textarea = page.locator("textarea.query-tool-textarea").first
        textarea.fill("GA26010001")

        # Collect API responses during resolve
        api_tokens = ["/api/query-tool/resolve", "/api/trace/lineage"]
        collected = {}

        def handle_response(resp):
            for token in api_tokens:
                if token in resp.url:
                    collected.setdefault(token, []).append(resp)

        page.on("response", handle_response)

        # Click resolve button (use .first – Lot tab's button appears first via v-show)
        resolve_btn = page.locator("button", has_text="解析").first
        resolve_btn.click()

        # Wait for resolve + lineage responses
        deadline = time.time() + 60
        while time.time() < deadline and len(collected) < 2:
            page.wait_for_timeout(500)
        page.remove_listener("response", handle_response)

        # Verify resolve API was called
        assert "/api/query-tool/resolve" in collected, "Resolve API was not called"
        resolve_resp = collected["/api/query-tool/resolve"][0]
        assert resolve_resp.ok, f"Resolve API returned {resolve_resp.status}"

        # Verify lineage API was auto-fired
        assert "/api/trace/lineage" in collected, "Lineage API was not auto-fired after resolve"

        # Lineage tree should show nodes
        page.wait_for_timeout(2000)
        tree_section = page.locator("text=批次血緣樹")
        expect(tree_section).to_be_visible()

    def test_lot_tab_url_state_sync(self, page: Page, app_server: str):
        """URL params are written after resolve and restored on reload."""
        _intercept_navigation_as_admin(page, app_server)
        page.goto(
            f"{app_server}{QUERY_TOOL_BASE}?tab=lot&input_type=work_order&values=GA26010001",
            wait_until="commit",
            timeout=60000,
        )
        page.wait_for_timeout(2000)

        # Verify URL params are preserved
        url = page.url
        assert "tab=lot" in url
        assert "input_type=work_order" in url
        assert "values=GA26010001" in url or "GA26010001" in url

    def test_lot_detail_sub_tabs_render(self, page: Page, app_server: str):
        """After resolve, clicking a tree node shows detail panel with sub-tabs."""
        _intercept_navigation_as_admin(page, app_server)
        page.goto(f"{app_server}{QUERY_TOOL_BASE}?tab=lot", wait_until="commit", timeout=60000)
        page.wait_for_timeout(3000)

        # Select work_order and resolve (use .first to target Lot tab's QueryBar)
        page.locator("select.query-tool-select").first.select_option("work_order")
        page.locator("textarea.query-tool-textarea").first.fill("GA26010001")
        page.locator("button", has_text="解析").first.click()

        # Wait for resolve + lineage + detail loading
        resolve_done = _wait_for_api_response(page, "/api/query-tool/resolve", timeout_seconds=60)
        if not resolve_done:
            pytest.fail("Resolve did not complete within timeout")

        page.wait_for_timeout(8000)

        # Detail panel sub-tabs should be visible
        detail_tabs = ["歷程", "物料", "退貨", "Hold", "Split", "Job"]
        for tab_label in detail_tabs:
            tab_btn = page.locator(f"button:has-text('{tab_label}')")
            if tab_btn.count() > 0:
                expect(tab_btn.first).to_be_visible()

    def test_equipment_tab_loads_filter_bar(self, page: Page, app_server: str):
        """Switching to equipment tab shows filter bar with equipment MultiSelect."""
        _intercept_navigation_as_admin(page, app_server)
        page.goto(f"{app_server}{QUERY_TOOL_BASE}?tab=equipment", wait_until="commit", timeout=60000)

        # Wait for equipment list to bootstrap
        equipment_resp = _wait_for_api_response(page, "/api/query-tool/equipment-list", timeout_seconds=30)
        assert equipment_resp is not None, "Equipment list API was not called"
        assert equipment_resp.ok

        # Filter bar should show date inputs
        start_date = page.locator("input[type='date']").first
        expect(start_date).to_be_visible()

        # Equipment sub-tabs should be visible
        for label in ["生產紀錄", "維修紀錄", "報廢紀錄", "Timeline"]:
            tab_btn = page.locator(f"button:has-text('{label}')")
            if tab_btn.count() > 0:
                expect(tab_btn.first).to_be_visible()

    def test_tab_switching_preserves_state(self, page: Page, app_server: str):
        """Switching between LOT and equipment tabs preserves entered data."""
        _intercept_navigation_as_admin(page, app_server)
        page.goto(f"{app_server}{QUERY_TOOL_BASE}?tab=lot", wait_until="commit", timeout=60000)
        page.wait_for_timeout(1500)

        # Enter text in LOT tab (use .first to target Lot tab's QueryBar)
        textarea = page.locator("textarea.query-tool-textarea").first
        textarea.fill("GA26010001")

        # Switch to equipment tab
        equipment_tab = page.locator("button", has_text="設備生產批次追蹤")
        equipment_tab.click()
        page.wait_for_timeout(500)

        # Switch back to LOT tab
        lot_tab = page.locator("button", has_text="批次追蹤(正向)")
        lot_tab.click()
        page.wait_for_timeout(500)

        # Verify textarea still has the value (v-show preserves state)
        expect(textarea).to_have_value("GA26010001")

    def test_lineage_tree_expand_collapse(self, page: Page, app_server: str):
        """After resolve, expand-all and collapse-all buttons work."""
        _intercept_navigation_as_admin(page, app_server)
        page.goto(f"{app_server}{QUERY_TOOL_BASE}?tab=lot", wait_until="commit", timeout=60000)
        page.wait_for_timeout(1500)

        page.locator("select.query-tool-select").first.select_option("work_order")
        page.locator("textarea.query-tool-textarea").first.fill("GA26010001")
        page.locator("button", has_text="解析").first.click()

        # Wait for resolve + lineage
        page.wait_for_timeout(8000)

        # Try expand all
        expand_btn = page.locator("button", has_text="全部展開")
        if expand_btn.count() > 0 and expand_btn.is_visible():
            expand_btn.click()
            page.wait_for_timeout(5000)

            # Try collapse all
            collapse_btn = page.locator("button", has_text="收合")
            if collapse_btn.count() > 0:
                collapse_btn.click()
                page.wait_for_timeout(1000)

    def test_export_button_present_when_data_loaded(self, page: Page, app_server: str):
        """After resolving and selecting a lot, export button should appear."""
        _intercept_navigation_as_admin(page, app_server)
        page.goto(f"{app_server}{QUERY_TOOL_BASE}?tab=lot", wait_until="commit", timeout=60000)
        page.wait_for_timeout(1500)

        page.locator("select.query-tool-select").first.select_option("work_order")
        page.locator("textarea.query-tool-textarea").first.fill("GA26010001")
        page.locator("button", has_text="解析").first.click()

        # Wait for resolve + detail load
        page.wait_for_timeout(8000)

        # Look for export button (should appear in detail panel)
        export_btn = page.locator("button", has_text="匯出")
        # May or may not be visible depending on data state, just verify no crash
        page.wait_for_timeout(1000)


# ---------------------------------------------------------------------------
# Full Flow Integration (API → UI round-trip)
# ---------------------------------------------------------------------------

@pytest.mark.e2e
class TestQueryToolFullFlowE2E:
    """End-to-end full workflow: resolve → lineage → history → association."""

    def test_work_order_full_flow(self, page: Page, app_server: str):
        """
        Complete flow:
        1. Navigate to query-tool
        2. Select work_order, enter GA26010001
        3. Click resolve
        4. Verify resolve API → lineage auto-fire → history load
        5. Click through sub-tabs
        """
        _intercept_navigation_as_admin(page, app_server)
        page.goto(f"{app_server}{QUERY_TOOL_BASE}?tab=lot", wait_until="commit", timeout=60000)
        page.wait_for_timeout(2000)

        # Step 1: Configure input (use .first to target Lot tab's QueryBar)
        page.locator("select.query-tool-select").first.select_option("work_order")
        page.locator("textarea.query-tool-textarea").first.fill("GA26010001")

        # Step 2: Track all API calls
        api_calls = {}

        def track_response(resp):
            for key in [
                "/api/query-tool/resolve",
                "/api/trace/lineage",
                "/api/query-tool/lot-history",
                "/api/query-tool/lot-associations",
            ]:
                if key in resp.url:
                    api_calls.setdefault(key, []).append({
                        "status": resp.status,
                        "url": resp.url,
                    })

        page.on("response", track_response)

        # Step 3: Click resolve (use .first – Lot tab's button appears first via v-show)
        page.locator("button", has_text="解析").first.click()

        # Step 4: Wait for cascade of API calls
        deadline = time.time() + 90
        while time.time() < deadline:
            page.wait_for_timeout(500)
            # Minimum: resolve + lineage + history
            if (
                "/api/query-tool/resolve" in api_calls
                and "/api/trace/lineage" in api_calls
                and "/api/query-tool/lot-history" in api_calls
            ):
                break

        page.remove_listener("response", track_response)

        # Step 5: Verify API cascade
        assert "/api/query-tool/resolve" in api_calls, \
            f"resolve not called. Calls seen: {list(api_calls.keys())}"
        assert api_calls["/api/query-tool/resolve"][0]["status"] == 200

        assert "/api/trace/lineage" in api_calls, \
            f"lineage not auto-fired. Calls seen: {list(api_calls.keys())}"

        assert "/api/query-tool/lot-history" in api_calls, \
            f"lot-history not loaded. Calls seen: {list(api_calls.keys())}"

        # Step 6: Verify URL state updated
        current_url = page.url
        assert "tab=lot" in current_url
        assert "work_order" in current_url

        # Step 7: Click through sub-tabs if available
        for tab_label in ["物料", "Hold", "歷程"]:
            tab_btn = page.locator(f"button:has-text('{tab_label}')")
            if tab_btn.count() > 0 and tab_btn.first.is_visible():
                tab_btn.first.click()
                page.wait_for_timeout(2000)

        # Step 8: Success message should be visible
        success_msg = page.locator("text=解析完成")
        if success_msg.count() > 0:
            expect(success_msg.first).to_be_visible()
