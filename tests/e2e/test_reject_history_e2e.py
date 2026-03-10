# -*- coding: utf-8 -*-
"""E2E tests for reject-history long-range query flow."""

from __future__ import annotations

import os
import time

import pytest
import requests


def _post_reject_query(
    app_server: str,
    body: dict,
    timeout: float = 420.0,
    *,
    max_attempts: int = 4,
) -> requests.Response:
    """POST reject query and retry transient overload responses."""
    response = None
    for attempt in range(max_attempts):
        response = requests.post(
            f"{app_server}/api/reject-history/query",
            json=body,
            timeout=timeout,
        )
        if response.status_code != 503:
            return response
        payload = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
        if payload.get("code") != "SERVICE_OVERLOADED":
            return response
        if attempt >= max_attempts - 1:
            return response
        retry_after = response.headers.get("Retry-After")
        try:
            wait_seconds = float(retry_after) if retry_after else 2.0
        except ValueError:
            wait_seconds = 2.0
        time.sleep(wait_seconds)
    return response


@pytest.mark.e2e
@pytest.mark.skipif(
    os.environ.get("RUN_LONG_E2E") != "1",
    reason="Long-range reject-history E2E disabled; set RUN_LONG_E2E=1 to run.",
)
class TestRejectHistoryLongRangeE2E:
    """Real backend E2E checks for long-range reject history query."""

    def test_query_190_day_range_respects_guardrail(self, app_server: str):
        response = _post_reject_query(
            app_server,
            {
                "mode": "date_range",
                "start_date": "2025-01-01",
                "end_date": "2025-07-09",
                "include_excluded_scrap": False,
                "exclude_material_scrap": True,
                "exclude_pb_diode": True,
            },
        )

        if response.status_code == 200:
            payload = response.json()
            assert payload.get("success") is True, payload
            assert payload.get("query_id")
            return

        assert response.status_code == 503, response.text[:500]
        payload = response.json()
        assert payload.get("code") == "RESULT_TOO_LARGE", payload

    def test_query_then_view_returns_cached_result(self, app_server: str):
        query_resp = _post_reject_query(
            app_server,
            {
                "mode": "date_range",
                "start_date": "2025-02-01",
                "end_date": "2025-02-28",
                "exclude_material_scrap": True,
                "exclude_pb_diode": True,
            },
        )
        assert query_resp.status_code == 200, query_resp.text[:500]
        query_payload = query_resp.json()
        assert query_payload.get("success") is True, query_payload
        query_id = query_payload.get("query_id")
        assert query_id

        view_resp = requests.get(
            f"{app_server}/api/reject-history/view",
            params={
                "query_id": query_id,
                "page": 1,
                "per_page": 50,
                "exclude_material_scrap": "true",
                "exclude_pb_diode": "true",
            },
            timeout=120,
        )
        assert view_resp.status_code == 200, view_resp.text[:500]
        view_payload = view_resp.json()
        assert view_payload.get("success") is True, view_payload

    def test_query_then_export_cached_returns_csv(self, app_server: str):
        query_resp = _post_reject_query(
            app_server,
            {
                "mode": "date_range",
                "start_date": "2025-02-01",
                "end_date": "2025-02-28",
                "exclude_material_scrap": True,
                "exclude_pb_diode": True,
            },
        )
        assert query_resp.status_code == 200, query_resp.text[:500]
        query_payload = query_resp.json()
        assert query_payload.get("success") is True, query_payload
        query_id = query_payload.get("query_id")
        assert query_id

        export_resp = requests.get(
            f"{app_server}/api/reject-history/export-cached",
            params={"query_id": query_id},
            timeout=120,
        )
        assert export_resp.status_code == 200, export_resp.text[:300]
        assert "text/csv" in export_resp.headers.get("Content-Type", "")
        assert "LOT" in export_resp.text[:200]
