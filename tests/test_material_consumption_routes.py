# -*- coding: utf-8 -*-
"""Tier 0-1 route forwarding tests for material_consumption_routes.

TDD: These tests are written FIRST (failing) before the implementation.

Rules (CLAUDE.md Test Coverage Discipline):
- Per-kwarg forwarding assertions, non-default values.
- mock.assert_called_once() + call_args.kwargs[key] == value — NEVER assert_called_once_with.
"""

from __future__ import annotations

import json
from unittest import mock
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Shared client fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def client():
    from mes_dashboard.app import create_app
    import mes_dashboard.core.database as db
    db._ENGINE = None
    app = create_app("testing")
    app.config["TESTING"] = True
    c = app.test_client()
    with c.session_transaction() as sess:
        sess["admin"] = {"displayName": "TestUser", "employeeNo": "T001"}
    return c


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    try:
        from mes_dashboard.core import rate_limit as rl
        with rl._RATE_LOCK:
            rl._RATE_ATTEMPTS.clear()
    except Exception:
        pass
    yield


# ---------------------------------------------------------------------------
# TestFilterOptions
# ---------------------------------------------------------------------------


class TestFilterOptions:
    def test_returns_parts_and_pj_types(self, client):
        """GET /filter-options returns parts and pj_types only."""
        with patch(
            "mes_dashboard.services.material_consumption_service.get_filter_options"
        ) as mock_svc:
            mock_svc.return_value = {
                "parts": ["MAT-A", "MAT-B"],
                "pj_types": ["TypeX", "TypeY"],
            }
            r = client.get("/api/material-consumption/filter-options")
        assert r.status_code == 200
        data = r.get_json()
        assert data["success"] is True
        assert "parts" in data["data"]
        assert "pj_types" in data["data"]
        # workcenter_groups and primary_categories must NOT be present
        assert "workcenter_groups" not in data["data"]
        assert "primary_categories" not in data["data"]


# ---------------------------------------------------------------------------
# TestQuerySubmit
# ---------------------------------------------------------------------------


class TestQuerySubmit:
    def _post_query(self, client, body: dict):
        return client.post(
            "/api/material-consumption/query",
            json=body,
            content_type="application/json",
        )

    def test_forwards_material_parts_kwarg_non_default(self, client):
        """material_parts is forwarded to service with non-default value."""
        with patch(
            "mes_dashboard.services.material_consumption_service.get_summary"
        ) as mock_svc:
            mock_svc.return_value = {
                "query_id": "qid-1",
                "kpi": {},
                "trend": [],
                "type_breakdown": [],
            }
            r = self._post_query(client, {
                "material_parts": ["PART-XYZ"],
                "start_date": "2026-01-01",
                "end_date": "2026-01-31",
                "granularity": "week",
            })
        assert r.status_code == 200
        mock_svc.assert_called_once()
        assert mock_svc.call_args.kwargs["material_parts"] == ["PART-XYZ"]

    def test_forwards_date_range_kwargs_non_default(self, client):
        """start_date / end_date forwarded with non-default values."""
        with patch(
            "mes_dashboard.services.material_consumption_service.get_summary"
        ) as mock_svc:
            mock_svc.return_value = {
                "query_id": "qid-2",
                "kpi": {},
                "trend": [],
                "type_breakdown": [],
            }
            r = self._post_query(client, {
                "material_parts": ["MAT-A"],
                "start_date": "2026-03-01",
                "end_date": "2026-03-31",
                "granularity": "month",
            })
        assert r.status_code == 200
        mock_svc.assert_called_once()
        assert mock_svc.call_args.kwargs["start_date"] == "2026-03-01"
        assert mock_svc.call_args.kwargs["end_date"] == "2026-03-31"

    def test_over_20_parts_returns_400(self, client):
        """More than 20 material_parts returns 400 VALIDATION_ERROR."""
        r = self._post_query(client, {
            "material_parts": [f"P{i}" for i in range(21)],
            "start_date": "2026-01-01",
            "end_date": "2026-01-31",
            "granularity": "week",
        })
        assert r.status_code == 400
        body = r.get_json()
        assert body["error"]["code"] == "VALIDATION_ERROR"

    def test_sql_meta_char_in_part_returns_400(self, client):
        """SQL meta-char in material_parts returns 400 VALIDATION_ERROR."""
        r = self._post_query(client, {
            "material_parts": ["MAT'; DROP TABLE x--"],
            "start_date": "2026-01-01",
            "end_date": "2026-01-31",
            "granularity": "week",
        })
        assert r.status_code == 400
        body = r.get_json()
        assert body["error"]["code"] == "VALIDATION_ERROR"

    def test_wildcard_star_accepted(self, client):
        """Token with * wildcard is accepted and forwarded to service."""
        with patch(
            "mes_dashboard.services.material_consumption_service.get_summary"
        ) as mock_svc:
            mock_svc.return_value = {
                "query_id": "qid-3",
                "kpi": {},
                "trend": [],
                "type_breakdown": [],
            }
            r = self._post_query(client, {
                "material_parts": ["MAT-A*"],
                "start_date": "2026-01-01",
                "end_date": "2026-01-31",
                "granularity": "week",
            })
        assert r.status_code == 200

    def test_day_granularity_accepted(self, client):
        """granularity='day' is now valid and accepted."""
        with patch(
            "mes_dashboard.services.material_consumption_service.get_summary"
        ) as mock_svc:
            mock_svc.return_value = {
                "query_id": "qid-day",
                "kpi": {},
                "trend": [],
                "type_breakdown": [],
            }
            r = self._post_query(client, {
                "material_parts": ["MAT-A"],
                "start_date": "2026-01-01",
                "end_date": "2026-01-31",
                "granularity": "day",
            })
        assert r.status_code == 200
        mock_svc.assert_called_once()
        assert mock_svc.call_args.kwargs["granularity"] == "day"

    def test_workcenter_groups_not_forwarded_to_service(self, client):
        """workcenter_groups in body must NOT be forwarded to get_summary (removed param)."""
        with patch(
            "mes_dashboard.services.material_consumption_service.get_summary"
        ) as mock_svc:
            mock_svc.return_value = {
                "query_id": "qid-wc",
                "kpi": {},
                "trend": [],
                "type_breakdown": [],
            }
            r = self._post_query(client, {
                "material_parts": ["MAT-A"],
                "start_date": "2026-01-01",
                "end_date": "2026-01-31",
                "granularity": "month",
                "workcenter_groups": ["WC-A"],  # should be silently ignored
            })
        assert r.status_code == 200
        mock_svc.assert_called_once()
        # Service must NOT receive workcenter_groups kwarg
        assert "workcenter_groups" not in mock_svc.call_args.kwargs


# ---------------------------------------------------------------------------
# TestViewEndpoint
# ---------------------------------------------------------------------------


class TestViewEndpoint:
    def test_forwards_granularity_kwarg_non_default(self, client):
        """GET /view forwards granularity kwarg with non-default value."""
        with patch(
            "mes_dashboard.services.material_consumption_service.apply_view"
        ) as mock_svc:
            mock_svc.return_value = {"trend": [], "type_breakdown": []}
            r = client.get("/api/material-consumption/view?query_id=test-qid&granularity=quarter")
        assert r.status_code == 200
        mock_svc.assert_called_once()
        assert mock_svc.call_args.kwargs["granularity"] == "quarter"

    def test_forwards_query_id_kwarg(self, client):
        """GET /view forwards query_id kwarg."""
        with patch(
            "mes_dashboard.services.material_consumption_service.apply_view"
        ) as mock_svc:
            mock_svc.return_value = {"trend": [], "type_breakdown": []}
            r = client.get("/api/material-consumption/view?query_id=specific-qid&granularity=week")
        assert r.status_code == 200
        mock_svc.assert_called_once()
        assert mock_svc.call_args.kwargs["query_id"] == "specific-qid"

    def test_day_granularity_accepted(self, client):
        """GET /view accepts day granularity."""
        with patch(
            "mes_dashboard.services.material_consumption_service.apply_view"
        ) as mock_svc:
            mock_svc.return_value = {"trend": [], "type_breakdown": []}
            r = client.get("/api/material-consumption/view?query_id=qid-day&granularity=day")
        assert r.status_code == 200
        mock_svc.assert_called_once()
        assert mock_svc.call_args.kwargs["granularity"] == "day"

    def test_forwards_types_kwarg_non_default(self, client):
        """GET /view?types=TypeA forwards types kwarg to apply_view."""
        with patch(
            "mes_dashboard.services.material_consumption_service.apply_view"
        ) as mock_svc:
            mock_svc.return_value = {"trend": [], "type_breakdown": []}
            r = client.get(
                "/api/material-consumption/view?query_id=qid-t&granularity=month&types=TypeA&types=TypeB"
            )
        assert r.status_code == 200
        mock_svc.assert_called_once()
        assert mock_svc.call_args.kwargs.get("types") == ["TypeA", "TypeB"], (
            f"types not forwarded: {mock_svc.call_args.kwargs}"
        )

    def test_no_types_param_passes_none_to_service(self, client):
        """GET /view without types param passes types=None to apply_view."""
        with patch(
            "mes_dashboard.services.material_consumption_service.apply_view"
        ) as mock_svc:
            mock_svc.return_value = {"trend": [], "type_breakdown": []}
            r = client.get("/api/material-consumption/view?query_id=qid-none&granularity=month")
        assert r.status_code == 200
        mock_svc.assert_called_once()
        assert mock_svc.call_args.kwargs.get("types") is None


# ---------------------------------------------------------------------------
# TestDetailSubmit
# ---------------------------------------------------------------------------


class TestDetailSubmit:
    def _post_detail(self, client, body: dict):
        return client.post(
            "/api/material-consumption/detail",
            json=body,
            content_type="application/json",
        )

    def _base_body(self):
        return {
            "material_parts": ["MAT-A"],
            "start_date": "2026-01-01",
            "end_date": "2026-01-31",
        }

    def test_sync_path_when_rows_under_threshold(self, client):
        """Sync 200 response when rows under SYNC_ROW_LIMIT."""
        with patch(
            "mes_dashboard.services.material_consumption_service.get_detail_summary"
        ) as mock_svc:
            mock_svc.return_value = {
                "async": False,
                "query_id": "dqid-1",
                "rows": [],
                "pagination": {"page": 1, "total_pages": 1, "total_rows": 0, "per_page": 50},
            }
            r = self._post_detail(client, self._base_body())
        assert r.status_code == 200

    def test_async_202_when_rows_over_threshold(self, client):
        """Async 202 response when rows over SYNC_ROW_LIMIT."""
        with patch(
            "mes_dashboard.services.material_consumption_service.get_detail_summary"
        ) as mock_svc:
            mock_svc.return_value = {
                "async": True,
                "job_id": "job-abc",
                "query_id": "dqid-2",
            }
            r = self._post_detail(client, self._base_body())
        assert r.status_code == 202

    def test_pj_types_not_forwarded_to_detail_summary(self, client):
        """pj_types in POST /detail body must NOT be forwarded to get_detail_summary.

        pj_type filtering on detail is done at the /detail/page level via DuckDB.
        """
        with patch(
            "mes_dashboard.services.material_consumption_service.get_detail_summary"
        ) as mock_svc:
            mock_svc.return_value = {
                "async": False,
                "query_id": "dqid-3",
                "rows": [],
                "pagination": {"page": 1, "total_pages": 1, "total_rows": 0, "per_page": 50},
            }
            body = self._base_body()
            body["pj_types"] = ["TypeX"]  # should be silently ignored
            r = self._post_detail(client, body)
        assert r.status_code == 200
        mock_svc.assert_called_once()
        # Service must NOT receive pj_types kwarg (removed from detail Oracle path)
        assert "pj_types" not in mock_svc.call_args.kwargs

    def test_workcenter_groups_not_forwarded_to_detail_summary(self, client):
        """workcenter_groups in POST /detail body must NOT be forwarded (removed param)."""
        with patch(
            "mes_dashboard.services.material_consumption_service.get_detail_summary"
        ) as mock_svc:
            mock_svc.return_value = {
                "async": False,
                "query_id": "dqid-4",
                "rows": [],
                "pagination": {"page": 1, "total_pages": 1, "total_rows": 0, "per_page": 50},
            }
            body = self._base_body()
            body["workcenter_groups"] = ["WC-A"]  # should be silently ignored
            r = self._post_detail(client, body)
        assert r.status_code == 200
        mock_svc.assert_called_once()
        assert "workcenter_groups" not in mock_svc.call_args.kwargs

    def test_async_202_includes_status_url(self, client):
        """Async 202 response must include status_url pointing to job endpoint."""
        with patch(
            "mes_dashboard.services.material_consumption_service.get_detail_summary"
        ) as mock_svc:
            mock_svc.return_value = {
                "async": True,
                "job_id": "job-url-test",
                "query_id": "dqid-url",
            }
            r = self._post_detail(client, self._base_body())
        assert r.status_code == 202
        body = r.get_json()
        assert body["success"] is True
        data = body["data"]
        assert "status_url" in data, (
            f"202 response missing 'status_url' key. data={data}"
        )
        assert data["status_url"] == "/api/material-consumption/detail/job/job-url-test", (
            f"status_url has wrong value: {data['status_url']!r}"
        )


# ---------------------------------------------------------------------------
# TestDetailJob
# ---------------------------------------------------------------------------


class TestDetailJob:
    def test_poll_returns_job_status(self, client):
        """GET /detail/job/<job_id> returns status from service."""
        with patch(
            "mes_dashboard.services.material_consumption_service.get_job_status"
        ) as mock_svc:
            mock_svc.return_value = {"status": "done", "query_id": "dqid-1"}
            r = client.get("/api/material-consumption/detail/job/test-job-123")
        assert r.status_code == 200
        body = r.get_json()
        assert body["data"]["status"] == "done"


# ---------------------------------------------------------------------------
# TestExport
# ---------------------------------------------------------------------------


class TestExport:
    def test_export_returns_streaming_response(self, client):
        """POST /export returns streaming text/csv response."""
        def _chunks():
            yield b"CONTAINERID,pj_type\r\n"
            yield b"C001,TypeX\r\n"

        with patch(
            "mes_dashboard.services.material_consumption_service.export_csv_stream"
        ) as mock_svc:
            mock_svc.return_value = _chunks()
            r = client.post(
                "/api/material-consumption/export",
                json={"query_id": "test-qid"},
                content_type="application/json",
            )
        assert r.status_code == 200
        assert "text/csv" in r.content_type


# ---------------------------------------------------------------------------
# TestRqMonitor
# ---------------------------------------------------------------------------


class TestRqMonitor:
    def test_material_consumption_queue_in_rq_monitor_queue_names(self):
        """_QUEUE_NAMES list must include the material-consumption queue."""
        import mes_dashboard.services.rq_monitor_service as rq_svc
        assert any(
            "material-consumption" in q for q in rq_svc._QUEUE_NAMES
        ), f"material-consumption queue not in _QUEUE_NAMES: {rq_svc._QUEUE_NAMES}"
