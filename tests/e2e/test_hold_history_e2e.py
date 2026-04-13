# -*- coding: utf-8 -*-
"""E2E tests for Hold History module.

Tests the two-phase query/view pattern:
  POST /api/hold-history/query → execute Oracle, cache result
  GET  /api/hold-history/view  → read cache, apply filters

Run with: pytest tests/e2e/test_hold_history_e2e.py -v -s
"""

import pytest
import requests


@pytest.mark.e2e
class TestHoldHistoryQuery:
    """E2E tests for Hold History primary query endpoint."""

    def test_query_requires_dates(self, api_base_url):
        """POST /query without dates returns 400."""
        resp = requests.post(f"{api_base_url}/hold-history/query", json={}, timeout=30)
        assert resp.status_code == 400
        payload = resp.json()
        assert payload["success"] is False

    def test_query_rejects_invalid_date_format(self, api_base_url):
        """POST /query with bad date format returns 400."""
        resp = requests.post(
            f"{api_base_url}/hold-history/query",
            json={"start_date": "03-01-2026", "end_date": "03-06-2026"},
            timeout=30,
        )
        assert resp.status_code == 400

    def test_query_rejects_inverted_dates(self, api_base_url):
        """POST /query with end_date < start_date returns 400."""
        resp = requests.post(
            f"{api_base_url}/hold-history/query",
            json={"start_date": "2026-03-10", "end_date": "2026-03-01"},
            timeout=30,
        )
        assert resp.status_code == 400

    def test_query_returns_query_id(self, api_base_url):
        """POST /query with valid dates returns query_id and meta."""
        resp = requests.post(
            f"{api_base_url}/hold-history/query",
            json={"start_date": "2026-03-01", "end_date": "2026-03-07"},
            timeout=120,
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["success"] is True
        assert "query_id" in payload.get("data", {}) or "query_id" in payload.get("meta", {})

    def test_query_with_hold_type_filter(self, api_base_url):
        """POST /query with hold_type=quality succeeds."""
        resp = requests.post(
            f"{api_base_url}/hold-history/query",
            json={
                "start_date": "2026-03-01",
                "end_date": "2026-03-07",
                "hold_type": "quality",
            },
            timeout=120,
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["success"] is True


@pytest.mark.e2e
class TestHoldHistoryView:
    """E2E tests for Hold History cached view endpoint."""

    @pytest.fixture(scope="class")
    def query_id(self, api_base_url):
        """Execute a query and return the query_id for view tests."""
        resp = requests.post(
            f"{api_base_url}/hold-history/query",
            json={"start_date": "2026-03-01", "end_date": "2026-03-07"},
            timeout=120,
        )
        assert resp.status_code == 200
        payload = resp.json()
        data = payload.get("data", {})
        qid = data.get("query_id") or payload.get("meta", {}).get("query_id")
        assert qid, f"No query_id in response: {payload}"
        return qid

    def test_view_requires_query_id(self, api_base_url):
        """GET /view without query_id returns 400."""
        resp = requests.get(f"{api_base_url}/hold-history/view", timeout=30)
        assert resp.status_code == 400

    def test_view_returns_data(self, api_base_url, query_id):
        """GET /view with valid query_id returns hold data with actual records."""
        resp = requests.get(
            f"{api_base_url}/hold-history/view",
            params={"query_id": query_id},
            timeout=60,
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["success"] is True
        data = payload["data"]
        assert isinstance(data, dict)
        assert data.get("total_row_count", 0) > 0, (
            "Hold history view returned 0 total_row_count — Oracle query may have failed silently "
            f"(data keys: {list(data.keys())})"
        )
        items = data.get("list", {}).get("items", [])
        assert len(items) > 0, "Hold history list.items is empty despite non-zero total_row_count"
        assert len(data.get("trend", [])) > 0, "Hold history trend data is empty"

    def test_view_pagination(self, api_base_url, query_id):
        """GET /view supports pagination and returns non-empty page."""
        resp = requests.get(
            f"{api_base_url}/hold-history/view",
            params={"query_id": query_id, "page": 1, "per_page": 10},
            timeout=60,
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["success"] is True
        data = payload["data"]
        items = data.get("list", {}).get("items", [])
        assert len(items) > 0, "Hold history pagination returned empty items page"

    def test_view_with_hold_type_filter(self, api_base_url, query_id):
        """GET /view with hold_type filter returns filtered data."""
        resp = requests.get(
            f"{api_base_url}/hold-history/view",
            params={"query_id": query_id, "hold_type": "quality"},
            timeout=60,
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["success"] is True

    def test_view_with_duration_range_filter(self, api_base_url, query_id):
        """GET /view with duration_range filter returns filtered data."""
        resp = requests.get(
            f"{api_base_url}/hold-history/view",
            params={"query_id": query_id, "duration_range": "<4h"},
            timeout=60,
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["success"] is True

    def test_view_expired_query_id_returns_410(self, api_base_url):
        """GET /view with expired query_id returns 410 CACHE_EXPIRED."""
        resp = requests.get(
            f"{api_base_url}/hold-history/view",
            params={"query_id": "nonexistent-expired-id"},
            timeout=30,
        )
        assert resp.status_code == 410
        payload = resp.json()
        assert payload["success"] is False
