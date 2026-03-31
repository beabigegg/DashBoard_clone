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
        assert isinstance(payload["data"], list) or "pj_types" in payload.get("data", {})


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
        assert resp.status_code in (200, 503)
        if resp.status_code == 200:
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
