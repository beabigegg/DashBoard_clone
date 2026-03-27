# -*- coding: utf-8 -*-
"""E2E tests for Material Trace module.

Endpoints:
  POST /api/material-trace/query          → forward/reverse trace
  GET  /api/material-trace/filter-options  → workcenter group options

Run with: pytest tests/e2e/test_material_trace_e2e.py -v -s
"""

import time

import pytest
import requests


def _poll_material_trace_until_ready(app_server, job_id, timeout=180):
    """Poll material trace async job until any valid status is observable."""
    deadline = time.time() + timeout
    final_status = None
    while time.time() < deadline:
        status_resp = requests.get(
            f"{app_server}/api/material-trace/job/{job_id}",
            timeout=30,
        )
        if status_resp.status_code == 429:
            retry_after = status_resp.headers.get("Retry-After")
            try:
                wait_seconds = float(retry_after) if retry_after else 3.0
            except ValueError:
                wait_seconds = 3.0
            time.sleep(max(wait_seconds, 1.0))
            continue
        assert status_resp.status_code == 200
        final_status = status_resp.json().get("data", status_resp.json())
        if final_status.get("status") in ("queued", "started", "running", "completed", "failed"):
            break
        time.sleep(2)
    return final_status


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
        """POST /query with valid lot IDs returns data immediately or via async polling."""
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
        assert resp.status_code in (200, 202)
        payload = resp.json()
        assert payload["success"] is True
        data = payload["data"]
        if resp.status_code == 202:
            assert data.get("async") is True
            assert data.get("job_id")
            assert data.get("query_hash")
            final_status = _poll_material_trace_until_ready(app_server, data["job_id"])
            assert final_status is not None, "Material trace async job polling timed out"
            assert final_status.get("status") in ("queued", "started", "running", "completed"), (
                f"Material trace async job entered unexpected state: {final_status}"
            )
            return
        assert "rows" in data or "items" in data
        assert "pagination" in data
