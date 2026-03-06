# -*- coding: utf-8 -*-
"""E2E tests for reject-history long-range query flow."""

from __future__ import annotations

import os

import pytest
import requests


def _post_reject_query(app_server: str, body: dict, timeout: float = 420.0) -> requests.Response:
    return requests.post(
        f"{app_server}/api/reject-history/query",
        json=body,
        timeout=timeout,
    )


@pytest.mark.e2e
@pytest.mark.skipif(
    os.environ.get("RUN_LONG_E2E") != "1",
    reason="Long-range reject-history E2E disabled; set RUN_LONG_E2E=1 to run.",
)
class TestRejectHistoryLongRangeE2E:
    """Real backend E2E checks for long-range reject history query."""

    def test_query_190_day_range_returns_success(self, app_server: str):
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

        assert response.status_code == 200, response.text[:500]
        payload = response.json()
        assert payload.get("success") is True, payload
        assert payload.get("query_id")

    def test_query_then_view_returns_cached_result(self, app_server: str):
        query_resp = _post_reject_query(
            app_server,
            {
                "mode": "date_range",
                "start_date": "2025-01-01",
                "end_date": "2025-07-09",
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
                "start_date": "2025-01-01",
                "end_date": "2025-07-09",
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
