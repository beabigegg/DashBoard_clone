# -*- coding: utf-8 -*-
"""
Tier 1 mock tests: query-tool RQ async dispatch.

query-path-c-elimination-cleanup (IP-11):
  AC-1: When QUERY_TOOL_USE_RQ=on and classify_query_cost==ASYNC → 202+job_id.
  AC-2: When QUERY_TOOL_USE_RQ=off (default) → sync inline path unchanged.

NOT marked integration_real — all Oracle/RQ calls are mocked at the service boundary.
Run without special flags:

    conda run -n mes-dashboard pytest \
        tests/integration/test_query_tool_rq_async.py -v --tb=short
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

import mes_dashboard.routes.query_tool_routes as qtr_module


@pytest.fixture
def qt_app(tmp_path):
    """Minimal Flask app with query_tool blueprint registered."""
    from mes_dashboard.app import create_app
    app = create_app("testing")
    return app


# ---------------------------------------------------------------------------
# AC-1: flag=on + oversized query → 202 + job_id
# ---------------------------------------------------------------------------


class TestFlagOnOversizedQuery:
    """When QUERY_TOOL_USE_RQ=on and date range triggers ASYNC cost → 202 + job_id."""

    def test_flag_on_oversized_query_returns_202_with_job_id(self, qt_app, monkeypatch):
        """AC-1: flag=on + ASYNC cost → HTTP 202 with job_id in response."""
        monkeypatch.setattr(qtr_module, "_QUERY_TOOL_USE_RQ", True)

        with patch.object(
            qtr_module, "is_async_available", return_value=True
        ), patch.object(
            qtr_module, "classify_query_cost", return_value="ASYNC"
        ), patch.object(
            qtr_module, "enqueue_query_job",
            return_value=("qt-abc123", None, None),
        ), patch.object(
            qtr_module, "get_owner_token", return_value="test-user"
        ):
            with qt_app.test_client() as client:
                resp = client.post(
                    "/api/query-tool/equipment-period",
                    json={
                        "equipment_ids": ["EQ001"],
                        "start_date": "2024-01-01",
                        "end_date": "2024-04-01",
                        "query_type": "status_hours",
                    },
                )

        assert resp.status_code == 202, (
            f"Expected 202 when QUERY_TOOL_USE_RQ=on + ASYNC cost, got {resp.status_code}"
        )
        data = resp.get_json()
        assert data["data"]["async"] is True
        assert "job_id" in data["data"]
        assert data["data"]["job_id"] == "qt-abc123"

    def test_flag_on_oversized_enqueues_rq_job_not_inline(self, qt_app, monkeypatch):
        """AC-1: enqueue_query_job must be called; get_equipment_status_hours must NOT."""
        monkeypatch.setattr(qtr_module, "_QUERY_TOOL_USE_RQ", True)

        mock_enqueue = MagicMock(return_value=("qt-def456", None, None))
        mock_inline = MagicMock()

        with patch.object(qtr_module, "is_async_available", return_value=True), \
             patch.object(qtr_module, "classify_query_cost", return_value="ASYNC"), \
             patch.object(qtr_module, "enqueue_query_job", mock_enqueue), \
             patch.object(qtr_module, "get_owner_token", return_value="test-user"), \
             patch(
                 "mes_dashboard.services.query_tool_service.get_equipment_status_hours",
                 mock_inline,
             ):
            with qt_app.test_client() as client:
                resp = client.post(
                    "/api/query-tool/equipment-period",
                    json={
                        "equipment_ids": ["EQ001"],
                        "start_date": "2024-01-01",
                        "end_date": "2024-04-01",
                        "query_type": "status_hours",
                    },
                )

        assert resp.status_code == 202
        mock_enqueue.assert_called_once()
        # Inline service must NOT have been called
        mock_inline.assert_not_called()


# ---------------------------------------------------------------------------
# AC-2: flag=off (default) → sync path unchanged
# ---------------------------------------------------------------------------


class TestFlagOffParity:
    """When QUERY_TOOL_USE_RQ=off → sync path identical to pre-change behavior."""

    def test_flag_off_oversized_query_returns_inline_as_before(self, qt_app, monkeypatch):
        """AC-2: flag=off → no RQ dispatch; sync path runs regardless of date span."""
        monkeypatch.setattr(qtr_module, "_QUERY_TOOL_USE_RQ", False)

        mock_result = {"data": [], "total": 0}
        mock_enqueue = MagicMock()

        with patch.object(qtr_module, "enqueue_query_job", mock_enqueue), \
             patch(
                 "mes_dashboard.routes.query_tool_routes.get_equipment_status_hours",
                 return_value=mock_result,
             ):
            with qt_app.test_client() as client:
                resp = client.post(
                    "/api/query-tool/equipment-period",
                    json={
                        "equipment_ids": ["EQ001"],
                        "start_date": "2024-01-01",
                        "end_date": "2024-04-01",
                        "query_type": "status_hours",
                    },
                )

        # Must be 200 (sync), NOT 202
        assert resp.status_code == 200, (
            f"Expected 200 (sync) when QUERY_TOOL_USE_RQ=off, got {resp.status_code}"
        )
        # enqueue must NOT have been called
        mock_enqueue.assert_not_called()

    def test_flag_off_small_query_identical_to_pre_change(self, qt_app, monkeypatch):
        """AC-2: flag=off, small query → 200, no RQ involvement."""
        monkeypatch.setattr(qtr_module, "_QUERY_TOOL_USE_RQ", False)

        mock_result = {"data": [{"hour": 1}], "total": 1}
        mock_enqueue = MagicMock()

        with patch.object(qtr_module, "enqueue_query_job", mock_enqueue), \
             patch(
                 "mes_dashboard.routes.query_tool_routes.get_equipment_status_hours",
                 return_value=mock_result,
             ):
            with qt_app.test_client() as client:
                resp = client.post(
                    "/api/query-tool/equipment-period",
                    json={
                        "equipment_ids": ["EQ001"],
                        "start_date": "2024-01-10",
                        "end_date": "2024-01-15",
                        "query_type": "status_hours",
                    },
                )

        assert resp.status_code == 200
        mock_enqueue.assert_not_called()
        data = resp.get_json()
        assert data["data"]["total"] == 1
