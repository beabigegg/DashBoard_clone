# -*- coding: utf-8 -*-
"""E2E tests for Production History page.

Tests:
  GET  /api/production-history/type-options — filter options
  POST /api/production-history/query        — primary dataset query
  POST /api/production-history/page         — paginated detail
  POST /api/production-history/matrix       — matrix summary

Run with: pytest tests/e2e/test_production_history_e2e.py -v --run-e2e
"""

import pytest
import requests
from playwright.sync_api import Page, expect

from tests.e2e.browser_helpers import goto_shell_route, wait_for_any_visible


@pytest.mark.e2e
class TestProductionHistoryTypeOptions:
    """E2E tests for /type-options endpoint."""

    def test_type_options_returns_pj_types_list(self, api_base_url):
        resp = requests.get(
            f"{api_base_url}/production-history/type-options", timeout=30
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["success"] is True
        data = payload["data"]
        assert isinstance(data, dict) and isinstance(data.get("items"), list)


@pytest.mark.e2e
class TestProductionHistoryQuery:
    """E2E tests for primary POST /query endpoint."""

    def test_query_missing_pj_types_returns_400(self, api_base_url):
        resp = requests.post(
            f"{api_base_url}/production-history/query",
            json={"start_date": "2026-03-01", "end_date": "2026-03-10"},
            timeout=30,
        )
        assert resp.status_code == 400
        payload = resp.json()
        assert payload["success"] is False

    def test_query_missing_start_date_returns_400(self, api_base_url):
        resp = requests.post(
            f"{api_base_url}/production-history/query",
            json={"pj_types": ["GA"], "end_date": "2026-03-10"},
            timeout=30,
        )
        assert resp.status_code == 400
        payload = resp.json()
        assert payload["success"] is False

    def test_query_valid_params_returns_success_envelope(self, api_base_url):
        resp = requests.post(
            f"{api_base_url}/production-history/query",
            json={
                "pj_types": ["GA"],
                "start_date": "2026-03-01",
                "end_date": "2026-03-07",
            },
            timeout=120,
        )
        # 200/202 = success (sync or async); 400 = no data for range; 503 = overloaded
        assert resp.status_code in (200, 202, 400, 503)
        if resp.status_code in (200, 202):
            payload = resp.json()
            assert payload["success"] is True
            assert "dataset_id" in payload["data"]

    def test_query_date_range_too_wide_returns_400(self, api_base_url):
        resp = requests.post(
            f"{api_base_url}/production-history/query",
            json={
                "pj_types": ["GA"],
                "start_date": "2020-01-01",
                "end_date": "2026-03-31",
            },
            timeout=30,
        )
        assert resp.status_code == 400


@pytest.mark.e2e
class TestProductionHistoryPage:
    """E2E tests for POST /page endpoint."""

    def test_page_missing_dataset_id_returns_410(self, api_base_url):
        resp = requests.post(
            f"{api_base_url}/production-history/page",
            json={"dataset_id": "nonexistent-dataset-xyz"},
            timeout=30,
        )
        assert resp.status_code in (410, 400)
        payload = resp.json()
        assert payload["success"] is False


@pytest.mark.e2e
class TestProductionHistoryMatrix:
    """E2E tests for POST /matrix endpoint."""

    def test_matrix_missing_dataset_id_returns_error(self, api_base_url):
        resp = requests.post(
            f"{api_base_url}/production-history/matrix",
            json={"dataset_id": "nonexistent-matrix-xyz"},
            timeout=30,
        )
        assert resp.status_code in (410, 400)
        payload = resp.json()
        assert payload["success"] is False


@pytest.mark.e2e
class TestProductionHistoryBrowserE2E:
    """Browser E2E for production-history primary workflow."""

    def test_production_history_page_runs_query(self, page: Page, app_server: str):
        resp = requests.get(f"{app_server}/api/production-history/type-options", timeout=30)
        if resp.status_code != 200:
            pytest.skip("Cannot load production-history type options")
        payload = resp.json().get("data", {})
        type_items = payload.get("items") if isinstance(payload, dict) else payload
        if not type_items:
            pytest.skip("No production-history types available")

        first_type = type_items[0]
        if isinstance(first_type, dict):
            type_label = str(first_type.get("label") or first_type.get("value") or first_type.get("name") or "").strip()
        else:
            type_label = str(first_type).strip()
        if not type_label:
            pytest.skip("Unable to resolve production-history type label")

        goto_shell_route(page, app_server, "/production-history", "生產歷程查詢")
        expect(page.get_by_role("heading", name="生產歷程查詢")).to_be_visible()

        trigger = page.locator(".ph-app__filter-field--type .multi-select-trigger").first
        expect(trigger).to_be_visible(timeout=60000)
        trigger.click()
        page.locator(".multi-select-option", has_text=type_label).first.click()
        page.locator(".multi-select-actions button", has_text="關閉").click()

        query_button = page.locator(".ph-app__filter-actions .ui-btn--primary").first
        expect(query_button).to_be_enabled()
        query_button.click()

        wait_for_any_visible(
            page,
            [
                "text=Workcenter x Equipment Matrix",
                "text=明細資料",
                ".ph-app__empty-state",
            ],
            timeout_ms=180000,
        )
        expect(page.locator("text=明細資料")).to_be_visible(timeout=180000)
