# -*- coding: utf-8 -*-
"""Integration tests for Material Trace API routes.

Tests input validation, pagination structure, and CSV export.
"""

import json
import pytest
from unittest.mock import patch, MagicMock

from mes_dashboard import create_app
from mes_dashboard.core.cache import NoOpCache
from mes_dashboard.core.rate_limit import reset_rate_limits_for_tests


@pytest.fixture
def app():
    """Create test Flask application."""
    app = create_app()
    app.config["TESTING"] = True
    app.extensions["cache"] = NoOpCache()
    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    reset_rate_limits_for_tests()
    yield
    reset_rate_limits_for_tests()


# ============================================================
# 7.6 Input validation → HTTP 400
# ============================================================


class TestQueryValidation:
    def test_missing_mode_returns_400(self, client):
        response = client.post(
            "/api/material-trace/query",
            data=json.dumps({"values": ["LOT-A"]}),
            content_type="application/json",
        )
        assert response.status_code == 400
        payload = response.get_json()
        assert payload["success"] is False
        assert "無效的查詢模式" in payload["error"]

    def test_invalid_mode_returns_400(self, client):
        response = client.post(
            "/api/material-trace/query",
            data=json.dumps({"mode": "invalid", "values": ["LOT-A"]}),
            content_type="application/json",
        )
        assert response.status_code == 400
        assert "無效的查詢模式" in response.get_json()["error"]

    def test_empty_values_returns_400(self, client):
        response = client.post(
            "/api/material-trace/query",
            data=json.dumps({"mode": "lot", "values": []}),
            content_type="application/json",
        )
        assert response.status_code == 400
        assert "請輸入至少一筆" in response.get_json()["error"]

    def test_blank_values_returns_400(self, client):
        response = client.post(
            "/api/material-trace/query",
            data=json.dumps({"mode": "lot", "values": ["", "  "]}),
            content_type="application/json",
        )
        assert response.status_code == 400
        assert "請輸入至少一筆" in response.get_json()["error"]

    def test_forward_over_200_returns_400(self, client):
        values = [f"LOT-{i}" for i in range(201)]
        response = client.post(
            "/api/material-trace/query",
            data=json.dumps({"mode": "lot", "values": values}),
            content_type="application/json",
        )
        assert response.status_code == 400
        assert "正向查詢上限 200 筆" in response.get_json()["error"]

    def test_workorder_over_200_returns_400(self, client):
        values = [f"WO-{i}" for i in range(201)]
        response = client.post(
            "/api/material-trace/query",
            data=json.dumps({"mode": "workorder", "values": values}),
            content_type="application/json",
        )
        assert response.status_code == 400
        assert "正向查詢上限 200 筆" in response.get_json()["error"]

    def test_reverse_over_50_returns_400(self, client):
        values = [f"MLOT-{i}" for i in range(51)]
        response = client.post(
            "/api/material-trace/query",
            data=json.dumps({"mode": "material_lot", "values": values}),
            content_type="application/json",
        )
        assert response.status_code == 400
        assert "反向查詢上限 50 筆" in response.get_json()["error"]

    def test_non_json_returns_415(self, client):
        response = client.post(
            "/api/material-trace/query",
            data="plain text",
            content_type="text/plain",
        )
        assert response.status_code == 415

    def test_empty_body_returns_400(self, client):
        response = client.post(
            "/api/material-trace/query",
            data=json.dumps({}),
            content_type="application/json",
        )
        # Empty object triggers require_non_empty_object
        assert response.status_code in (400, 415)


# ============================================================
# 7.7 Query endpoint — correct pagination structure
# ============================================================


class TestQueryPagination:
    @patch("mes_dashboard.routes.material_trace_routes.forward_query")
    def test_query_returns_pagination_structure(self, mock_fwd, client):
        mock_fwd.return_value = {
            "rows": [{"CONTAINERNAME": "LOT-1", "PJ_WORKORDER": "WO-1"}],
            "pagination": {
                "page": 1,
                "per_page": 50,
                "total": 100,
                "total_pages": 2,
            },
            "meta": {},
        }

        response = client.post(
            "/api/material-trace/query",
            data=json.dumps({"mode": "workorder", "values": ["WO-001"]}),
            content_type="application/json",
        )

        assert response.status_code == 200
        payload = response.get_json()
        assert payload["success"] is True
        assert "pagination" in payload
        pag = payload["pagination"]
        assert pag["page"] == 1
        assert pag["per_page"] == 50
        assert pag["total"] == 100
        assert pag["total_pages"] == 2
        assert len(payload["rows"]) == 1

    @patch("mes_dashboard.routes.material_trace_routes.forward_query")
    def test_query_passes_page_param(self, mock_fwd, client):
        mock_fwd.return_value = {
            "rows": [],
            "pagination": {"page": 3, "per_page": 50, "total": 200, "total_pages": 4},
            "meta": {},
        }

        response = client.post(
            "/api/material-trace/query",
            data=json.dumps({"mode": "workorder", "values": ["WO-001"], "page": 3}),
            content_type="application/json",
        )

        assert response.status_code == 200
        mock_fwd.assert_called_once()
        call_kwargs = mock_fwd.call_args
        # page should be 3
        assert call_kwargs[0][3] == 3 or call_kwargs.kwargs.get("page") == 3

    @patch("mes_dashboard.routes.material_trace_routes.reverse_query")
    def test_reverse_mode_dispatches_correctly(self, mock_rev, client):
        mock_rev.return_value = {
            "rows": [],
            "pagination": {"page": 1, "per_page": 50, "total": 0, "total_pages": 0},
            "meta": {},
        }

        response = client.post(
            "/api/material-trace/query",
            data=json.dumps({"mode": "material_lot", "values": ["MLOT-A"]}),
            content_type="application/json",
        )

        assert response.status_code == 200
        mock_rev.assert_called_once()


# ============================================================
# 7.8 Export endpoint — CSV content-type and UTF-8 BOM
# ============================================================


class TestExportEndpoint:
    @patch("mes_dashboard.routes.material_trace_routes.export_csv")
    def test_export_returns_csv_content_type(self, mock_export, client):
        csv_content = b"\xef\xbb\xbfLOT ID,\xe5\xb7\xa5\xe5\x96\xae\n"
        mock_export.return_value = (csv_content, {})

        response = client.post(
            "/api/material-trace/export",
            data=json.dumps({"mode": "workorder", "values": ["WO-001"]}),
            content_type="application/json",
        )

        assert response.status_code == 200
        assert "text/csv" in response.content_type
        # Check UTF-8 BOM
        assert response.data[:3] == b"\xef\xbb\xbf"

    @patch("mes_dashboard.routes.material_trace_routes.export_csv")
    def test_export_truncated_sets_header(self, mock_export, client):
        csv_content = b"\xef\xbb\xbfheader\nrow\n"
        mock_export.return_value = (csv_content, {"truncated": True, "export_max_rows": 50000})

        response = client.post(
            "/api/material-trace/export",
            data=json.dumps({"mode": "workorder", "values": ["WO-001"]}),
            content_type="application/json",
        )

        assert response.status_code == 200
        assert response.headers.get("X-Truncated") == "true"

    def test_export_validation_same_as_query(self, client):
        """Export should reject invalid mode same as query."""
        response = client.post(
            "/api/material-trace/export",
            data=json.dumps({"mode": "invalid", "values": ["X"]}),
            content_type="application/json",
        )
        assert response.status_code == 400


# ============================================================
# Filter options endpoint
# ============================================================


class TestFilterOptions:
    @patch("mes_dashboard.routes.material_trace_routes.get_workcenter_groups")
    def test_filter_options_returns_groups(self, mock_groups, client):
        mock_groups.return_value = [
            {"name": "焊接_DB", "sequence": 1},
            {"name": "焊線_WB", "sequence": 2},
        ]

        response = client.get("/api/material-trace/filter-options")

        assert response.status_code == 200
        payload = response.get_json()
        assert payload["success"] is True
        assert payload["data"]["workcenter_groups"] == ["焊接_DB", "焊線_WB"]

    @patch("mes_dashboard.routes.material_trace_routes.get_workcenter_groups")
    def test_filter_options_unavailable_returns_503(self, mock_groups, client):
        mock_groups.return_value = None

        response = client.get("/api/material-trace/filter-options")

        assert response.status_code == 503
