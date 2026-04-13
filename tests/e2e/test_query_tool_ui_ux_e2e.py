# -*- coding: utf-8 -*-
"""E2E UI/UX resilience tests for query-tool interactions."""

from __future__ import annotations

import json
import re
from urllib.parse import quote

import pytest
import requests
from playwright.sync_api import Page, expect

from tests.e2e.browser_helpers import ensure_shell_admin


QUERY_TOOL_BASE = "/portal-shell/query-tool"


def _intercept_navigation_as_admin(page: Page):
    """Force admin navigation payload and ensure query-tool route is visible."""

    def handle_route(route):
        response = route.fetch()
        body = response.json()

        body["is_admin"] = True
        drawers = body.get("drawers", [])

        query_tool_entry = {
            "name": "批次追蹤工具",
            "order": 4,
            "route": "/query-tool",
            "status": "dev",
        }

        has_query_tool = any(
            page_item.get("route") == "/query-tool"
            for drawer in drawers
            for page_item in drawer.get("pages", [])
        )

        if not has_query_tool:
            target_drawer = next((drawer for drawer in drawers if not drawer.get("admin_only")), None)
            if target_drawer is None:
                drawers.append(
                    {
                        "id": "e2e-test-drawer",
                        "name": "E2E Test",
                        "order": 999,
                        "admin_only": False,
                        "pages": [query_tool_entry],
                    }
                )
            else:
                target_drawer.setdefault("pages", []).append(query_tool_entry)

        body["drawers"] = drawers
        route.fulfill(
            status=response.status,
            headers={**response.headers, "content-type": "application/json"},
            body=json.dumps(body),
        )

    page.route("**/api/portal/navigation", handle_route)


@pytest.mark.e2e
class TestQueryToolUiUxE2E:
    """User-centric UI/UX flows on query-tool page."""

    def test_lot_multi_query_counter_and_url_round_trip(self, page: Page, app_server: str):
        """Multi-query input should sync counter + URL and survive reload."""
        ensure_shell_admin(page, "/query-tool", "批次追蹤工具")
        _intercept_navigation_as_admin(page)
        page.goto(f"{app_server}{QUERY_TOOL_BASE}?tab=lot", wait_until="domcontentloaded", timeout=60000)
        expect(page.locator("textarea.query-tool-textarea:visible").first).to_be_visible(timeout=30000)

        visible_textarea = page.locator("textarea.query-tool-textarea:visible").first
        visible_textarea.fill("GA26010001\nGA26010002, GA26010003")
        expect(page.locator(".query-tool-input-counter:visible").first).to_contain_text("已輸入 3")

        visible_select = page.locator("select.query-tool-select:visible").first
        visible_select.select_option("work_order")

        with page.expect_response(lambda resp: "/api/query-tool/resolve" in resp.url and resp.status < 500, timeout=90000):
            page.locator("button:has-text('解析'):visible").first.click()

        page.wait_for_timeout(1000)
        assert "tab=lot" in page.url
        assert "lot_values=" in page.url or "values=" in page.url

        page.reload(wait_until="domcontentloaded")
        page.wait_for_timeout(1000)

        restored_text = page.locator("textarea.query-tool-textarea:visible").first.input_value()
        restored_values = [v.strip() for v in re.split(r"[\n,]", restored_text) if v.strip()]
        assert len(restored_values) >= 3

    def test_equipment_tab_cross_navigation_preserves_filters(self, page: Page, app_server: str):
        """Equipment filter/date state should persist across tab switching."""
        equipment_resp = requests.get(f"{app_server}/api/query-tool/equipment-list", timeout=30)
        if equipment_resp.status_code != 200:
            pytest.skip("equipment-list API is unavailable")
        raw_data = equipment_resp.json().get("data") or []
        equipment_items = raw_data.get("data", []) if isinstance(raw_data, dict) else raw_data
        if not equipment_items:
            pytest.skip("No equipment item available for E2E test")

        equipment_id = str(equipment_items[0].get("RESOURCEID") or "")
        if not equipment_id:
            pytest.skip("Unable to determine equipment id")

        ensure_shell_admin(page, "/query-tool", "批次追蹤工具")
        _intercept_navigation_as_admin(page)
        start_date = "2026-01-01"
        end_date = "2026-01-31"
        page.goto(
            f"{app_server}{QUERY_TOOL_BASE}"
            f"?tab=equipment&equipment_sub_tab=timeline"
            f"&equipment_ids={quote(equipment_id)}"
            f"&start_date={start_date}&end_date={end_date}",
            wait_until="domcontentloaded",
            timeout=60000,
        )

        date_inputs = page.locator("input[type='date']")
        expect(date_inputs.first).to_be_visible(timeout=30000)
        expect(date_inputs.nth(1)).to_be_visible(timeout=30000)
        expect(date_inputs.first).to_have_value(start_date)
        expect(date_inputs.nth(1)).to_have_value(end_date)

        js_errors = []
        page.on("pageerror", lambda error: js_errors.append(str(error)))

        with page.expect_response(lambda resp: "/api/query-tool/equipment-period" in resp.url and resp.status < 500, timeout=120000):
            page.locator("button:has-text('查詢'):visible").first.click()

        page.wait_for_timeout(1500)

        page.locator("button", has_text="批次追蹤(正向)").click()
        page.wait_for_timeout(400)
        page.locator("button", has_text="設備生產批次追蹤").click()
        page.wait_for_timeout(600)

        expect(date_inputs.first).to_have_value(start_date)
        expect(date_inputs.nth(1)).to_have_value(end_date)
        assert len(js_errors) == 0, f"JS errors found while switching tabs: {js_errors[:3]}"

    def test_rapid_resolve_and_tab_switching_no_ui_crash(self, page: Page, app_server: str):
        """Rapid resolve + tab switching should keep page responsive without crashes."""
        ensure_shell_admin(page, "/query-tool", "批次追蹤工具")
        _intercept_navigation_as_admin(page)
        page.goto(f"{app_server}{QUERY_TOOL_BASE}?tab=lot", wait_until="domcontentloaded", timeout=60000)
        expect(page.locator("select.query-tool-select:visible").first).to_be_visible(timeout=30000)

        js_errors = []
        page.on("pageerror", lambda error: js_errors.append(str(error)))

        # Seed lot tab query input.
        page.locator("select.query-tool-select:visible").first.select_option("work_order")
        page.locator("textarea.query-tool-textarea:visible").first.fill("GA26010001")

        for idx in range(4):
            with page.expect_response(lambda resp: "/api/query-tool/resolve" in resp.url and resp.status < 500, timeout=90000):
                page.locator("button:has-text('解析'):visible").first.click()
            page.wait_for_timeout(350)

            page.locator("button", has_text="流水批反查(反向)").click()
            page.wait_for_timeout(300)
            page.locator("select.query-tool-select:visible").first.select_option("serial_number")
            page.locator("textarea.query-tool-textarea:visible").first.fill(f"GMSN-STRESS-{idx:03d}")

            with page.expect_response(lambda resp: "/api/query-tool/resolve" in resp.url and resp.status < 500, timeout=90000):
                page.locator("button:has-text('解析'):visible").first.click()
            page.wait_for_timeout(300)

            page.locator("button", has_text="批次追蹤(正向)").click()
            page.wait_for_timeout(300)

        expect(page.locator("body")).to_be_visible()
        assert len(js_errors) == 0, f"Detected JS crash signals: {js_errors[:3]}"
