# -*- coding: utf-8 -*-
"""E2E tests for Material Trace module.

Endpoints:
  POST /api/material-trace/query          → forward/reverse trace
  GET  /api/material-trace/filter-options  → workcenter group options

Run with: pytest tests/e2e/test_material_trace_e2e.py -v -s
"""

import pytest
import requests


@pytest.mark.e2e
class TestMaterialTraceE2E:
    """E2E tests for Material Trace endpoints."""

    def test_filter_options_returns_data(self, app_server):
        """GET /filter-options returns workcenter group options."""
        resp = requests.get(
            f"{app_server}/api/material-trace/filter-options", timeout=30
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["success"] is True

    def test_query_requires_mode_and_values(self, app_server):
        """POST /query without mode returns 400."""
        resp = requests.post(
            f"{app_server}/api/material-trace/query", json={}, timeout=30
        )
        assert resp.status_code == 400

    def test_query_rejects_invalid_mode(self, app_server):
        """POST /query with invalid mode returns 400."""
        resp = requests.post(
            f"{app_server}/api/material-trace/query",
            json={"mode": "invalid_mode", "values": ["LOT-001"]},
            timeout=30,
        )
        assert resp.status_code == 400

    def test_query_rejects_empty_values(self, app_server):
        """POST /query with empty values returns 400."""
        resp = requests.post(
            f"{app_server}/api/material-trace/query",
            json={"mode": "lot", "values": []},
            timeout=30,
        )
        assert resp.status_code == 400

    def test_query_rejects_too_many_values(self, app_server):
        """POST /query with >200 values returns 400."""
        resp = requests.post(
            f"{app_server}/api/material-trace/query",
            json={"mode": "lot", "values": [f"LOT-{i:04d}" for i in range(201)]},
            timeout=30,
        )
        assert resp.status_code == 400

    def test_query_with_valid_params_succeeds(self, app_server):
        """POST /query with valid lot IDs returns data (may be empty)."""
        resp = requests.post(
            f"{app_server}/api/material-trace/query",
            json={
                "mode": "lot",
                "values": ["TEST-LOT-001"],
                "page": 1,
                "per_page": 10,
            },
            timeout=120,
        )
        # Should succeed even if no matching data
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["success"] is True
        data = payload["data"]
        assert "rows" in data or "items" in data
        assert "pagination" in data
