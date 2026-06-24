# -*- coding: utf-8 -*-
"""Integration tests for Material Trace API routes."""

import json
from unittest.mock import MagicMock, patch

import pytest

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
        assert "無效的查詢模式" in payload["error"]["message"]

    def test_invalid_mode_returns_400(self, client):
        response = client.post(
            "/api/material-trace/query",
            data=json.dumps({"mode": "invalid", "values": ["LOT-A"]}),
            content_type="application/json",
        )
        assert response.status_code == 400
        assert "無效的查詢模式" in response.get_json()["error"]["message"]

    def test_empty_values_returns_400(self, client):
        response = client.post(
            "/api/material-trace/query",
            data=json.dumps({"mode": "lot", "values": []}),
            content_type="application/json",
        )
        assert response.status_code == 400
        assert "請輸入至少一筆" in response.get_json()["error"]["message"]

    def test_blank_values_returns_400(self, client):
        response = client.post(
            "/api/material-trace/query",
            data=json.dumps({"mode": "lot", "values": ["", "  "]}),
            content_type="application/json",
        )
        assert response.status_code == 400
        assert "請輸入至少一筆" in response.get_json()["error"]["message"]

    def test_forward_over_200_returns_400(self, client):
        values = [f"LOT-{i}" for i in range(201)]
        response = client.post(
            "/api/material-trace/query",
            data=json.dumps({"mode": "lot", "values": values}),
            content_type="application/json",
        )
        assert response.status_code == 400
        assert "正向查詢上限 200 筆" in response.get_json()["error"]["message"]

    def test_workorder_over_200_returns_400(self, client):
        values = [f"WO-{i}" for i in range(201)]
        response = client.post(
            "/api/material-trace/query",
            data=json.dumps({"mode": "workorder", "values": values}),
            content_type="application/json",
        )
        assert response.status_code == 400
        assert "正向查詢上限 200 筆" in response.get_json()["error"]["message"]

    def test_reverse_over_50_returns_400(self, client):
        values = [f"MLOT-{i}" for i in range(51)]
        response = client.post(
            "/api/material-trace/query",
            data=json.dumps({"mode": "material_lot", "values": values}),
            content_type="application/json",
        )
        assert response.status_code == 400
        assert "反向查詢上限 50 筆" in response.get_json()["error"]["message"]

    def test_non_json_returns_415(self, client):
        response = client.post(
            "/api/material-trace/query",
            data="plain text",
            content_type="text/plain",
        )
        assert response.status_code == 400
        assert response.get_json()["error"]["message"] is not None

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
    @patch("mes_dashboard.routes.material_trace_routes.MaterialTraceDuckdbRuntime")
    def test_query_returns_pagination_structure_on_spool_hit(self, mock_runtime_cls, client):
        mock_runtime = MagicMock()
        mock_runtime.is_available.return_value = True
        mock_runtime.get_page.return_value = {
            "rows": [{"CONTAINERNAME": "LOT-1", "PJ_WORKORDER": "WO-1"}],
            "pagination": {
                "page": 1,
                "per_page": 50,
                "total": 100,
                "total_pages": 2,
            },
            "query_hash": "mtrace-hit-001",
        }
        mock_runtime_cls.return_value = mock_runtime

        response = client.post(
            "/api/material-trace/query",
            data=json.dumps({"mode": "workorder", "values": ["WO-001"]}),
            content_type="application/json",
        )

        assert response.status_code == 200
        payload = response.get_json()
        assert payload["success"] is True
        assert "pagination" in payload["data"]
        pag = payload["data"]["pagination"]
        assert pag["page"] == 1
        assert pag["per_page"] == 50
        assert pag["total"] == 100
        assert pag["total_pages"] == 2
        assert len(payload["data"]["rows"]) == 1
        assert payload["data"]["query_hash"] == "mtrace-hit-001"

    @patch("mes_dashboard.routes.material_trace_routes.MaterialTraceDuckdbRuntime")
    def test_query_passes_page_param(self, mock_runtime_cls, client):
        mock_runtime = MagicMock()
        mock_runtime.is_available.return_value = True
        mock_runtime.get_page.return_value = {
            "rows": [],
            "pagination": {"page": 3, "per_page": 50, "total": 200, "total_pages": 4},
            "query_hash": "mtrace-hit-002",
        }
        mock_runtime_cls.return_value = mock_runtime

        response = client.post(
            "/api/material-trace/query",
            data=json.dumps({"mode": "workorder", "values": ["WO-001"], "page": 3}),
            content_type="application/json",
        )

        assert response.status_code == 200
        mock_runtime.get_page.assert_called_once_with(3, 50)

    @patch("mes_dashboard.routes.material_trace_routes.MATERIAL_TRACE_USE_UNIFIED_JOB", False)
    @patch("mes_dashboard.routes.material_trace_routes.enqueue_job")
    @patch("mes_dashboard.routes.material_trace_routes.MaterialTraceDuckdbRuntime")
    def test_spool_miss_enqueues_async_job(self, mock_runtime_cls, mock_enqueue_job, client):
        mock_runtime = MagicMock()
        mock_runtime.is_available.return_value = False
        mock_runtime_cls.return_value = mock_runtime
        mock_enqueue_job.return_value = ("mtrace-job-001", None)
        response = client.post(
            "/api/material-trace/query",
            data=json.dumps({"mode": "material_lot", "values": ["MLOT-A"]}),
            content_type="application/json",
        )

        assert response.status_code == 202
        payload = response.get_json()
        assert payload["success"] is True
        assert payload["data"]["async"] is True
        assert payload["data"]["job_id"] == "mtrace-job-001"
        assert "/api/material-trace/job/mtrace-job-001" in payload["data"]["status_url"]

    @patch("mes_dashboard.routes.material_trace_routes.enqueue_job", return_value=(None, "redis unavailable"))
    @patch("mes_dashboard.routes.material_trace_routes.MaterialTraceDuckdbRuntime")
    def test_spool_miss_returns_503_when_enqueue_fails(self, mock_runtime_cls, _mock_enqueue_job, client):
        mock_runtime = MagicMock()
        mock_runtime.is_available.return_value = False
        mock_runtime_cls.return_value = mock_runtime

        response = client.post(
            "/api/material-trace/query",
            data=json.dumps({"mode": "workorder", "values": ["WO-001"]}),
            content_type="application/json",
        )

        assert response.status_code == 503
        assert response.headers.get("Retry-After") == "30"
        payload = response.get_json()
        assert payload["success"] is False

    @patch("mes_dashboard.routes.material_trace_routes.get_job_status", return_value={"job_id": "mtrace-job-001", "status": "running"})
    def test_job_status_endpoint_returns_status(self, _mock_status, client):
        response = client.get("/api/material-trace/job/mtrace-job-001")
        assert response.status_code == 200
        payload = response.get_json()
        assert payload["data"]["status"] == "running"


# ============================================================
# 7.8 Export endpoint — CSV content-type and UTF-8 BOM
# ============================================================


class TestExportEndpoint:
    @patch("mes_dashboard.routes.material_trace_routes.MaterialTraceDuckdbRuntime")
    def test_export_returns_csv_content_type(self, mock_runtime_cls, client):
        mock_runtime = MagicMock()
        mock_runtime.is_available.return_value = True
        mock_runtime.export_csv.return_value = iter([b"\xef\xbb\xbfLOT ID,\xe5\xb7\xa5\xe5\x96\xae\n"])
        mock_runtime_cls.return_value = mock_runtime

        response = client.post(
            "/api/material-trace/export",
            data=json.dumps({"mode": "workorder", "values": ["WO-001"], "query_hash": "mtrace-hit-001"}),
            content_type="application/json",
        )

        assert response.status_code == 200
        assert "text/csv" in response.content_type
        # Check UTF-8 BOM
        assert response.data[:3] == b"\xef\xbb\xbf"
        assert response.headers.get("X-Query-Quality-Status") == "complete"

    @patch("mes_dashboard.routes.material_trace_routes.MaterialTraceDuckdbRuntime")
    def test_export_returns_409_when_query_not_ready(self, mock_runtime_cls, client):
        mock_runtime = MagicMock()
        mock_runtime.is_available.return_value = False
        mock_runtime_cls.return_value = mock_runtime

        response = client.post(
            "/api/material-trace/export",
            data=json.dumps({"mode": "workorder", "values": ["WO-001"], "query_hash": "mtrace-miss-001"}),
            content_type="application/json",
        )

        assert response.status_code == 409
        payload = response.get_json()
        assert payload["error"]["code"] == "QUERY_NOT_READY"

    def test_export_validation_same_as_query(self, client):
        """Export should reject invalid mode same as query."""
        response = client.post(
            "/api/material-trace/export",
            data=json.dumps({"mode": "invalid", "values": ["X"], "query_hash": "mtrace-hit-001"}),
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_export_requires_query_hash(self, client):
        response = client.post(
            "/api/material-trace/export",
            data=json.dumps({"mode": "workorder", "values": ["WO-001"]}),
            content_type="application/json",
        )

        assert response.status_code == 400
        payload = response.get_json()
        assert "query_hash" in payload["error"]["message"]

    @patch("mes_dashboard.routes.material_trace_routes.MaterialTraceDuckdbRuntime")
    def test_export_memory_guard_returns_503(self, mock_runtime_cls, client):
        mock_runtime_cls.side_effect = MemoryError("記憶體負載較高")

        response = client.post(
            "/api/material-trace/export",
            data=json.dumps({"mode": "workorder", "values": ["WO-001"], "query_hash": "mtrace-hit-001"}),
            content_type="application/json",
        )

        assert response.status_code == 503
        assert response.headers.get("Retry-After") == "30"
        payload = response.get_json()
        assert payload["success"] is False


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


# ============================================================
# query_hash stability
# ============================================================


class TestQueryHashStability:
    """make_route_query_hash must produce deterministic, stable IDs."""

    def test_same_inputs_same_hash(self):
        from mes_dashboard.services.material_trace_service import make_route_query_hash
        h1 = make_route_query_hash("workorder", ["WO-001", "WO-002"])
        h2 = make_route_query_hash("workorder", ["WO-001", "WO-002"])
        assert h1 == h2

    def test_value_order_normalized(self):
        """Values in different order must produce the same hash."""
        from mes_dashboard.services.material_trace_service import make_route_query_hash
        h1 = make_route_query_hash("workorder", ["WO-001", "WO-002"])
        h2 = make_route_query_hash("workorder", ["WO-002", "WO-001"])
        assert h1 == h2

    def test_different_mode_different_hash(self):
        from mes_dashboard.services.material_trace_service import make_route_query_hash
        h1 = make_route_query_hash("workorder", ["WO-001"])
        h2 = make_route_query_hash("lot_id", ["WO-001"])
        assert h1 != h2

    def test_different_values_different_hash(self):
        from mes_dashboard.services.material_trace_service import make_route_query_hash
        h1 = make_route_query_hash("workorder", ["WO-001"])
        h2 = make_route_query_hash("workorder", ["WO-999"])
        assert h1 != h2

    def test_hash_starts_with_mtrace_prefix(self):
        from mes_dashboard.services.material_trace_service import make_route_query_hash
        h = make_route_query_hash("workorder", ["WO-001"])
        assert h.startswith("mtrace-")

    def test_hash_is_url_safe(self):
        """Hash must contain only URL/filename-safe characters."""
        import re
        from mes_dashboard.services.material_trace_service import make_route_query_hash
        h = make_route_query_hash("workorder", ["WO-001", "WO-002"])
        assert re.match(r'^[a-zA-Z0-9\-_]+$', h), f"Hash not URL-safe: {h!r}"

    def test_workcenter_groups_affect_hash(self):
        """workcenter_groups must be included in the hash key."""
        from mes_dashboard.services.material_trace_service import make_route_query_hash
        h1 = make_route_query_hash("workorder", ["WO-001"], workcenter_groups=["DB"])
        h2 = make_route_query_hash("workorder", ["WO-001"], workcenter_groups=["WB"])
        assert h1 != h2

    def test_no_workcenter_groups_vs_empty_same_hash(self):
        """None and [] for workcenter_groups must produce the same hash."""
        from mes_dashboard.services.material_trace_service import make_route_query_hash
        h1 = make_route_query_hash("workorder", ["WO-001"], workcenter_groups=None)
        h2 = make_route_query_hash("workorder", ["WO-001"], workcenter_groups=[])
        assert h1 == h2


# ============================================================
# Export 409 QUERY_NOT_READY (already covered; verified via alias)
# ============================================================


class TestExport409QueryNotReady:
    """Dedicated class for 409 QUERY_NOT_READY export error — explicit race case."""

    @patch("mes_dashboard.routes.material_trace_routes.MaterialTraceDuckdbRuntime")
    def test_export_spool_miss_returns_409(self, mock_runtime_cls, client):
        """When spool is not available, export must return 409 QUERY_NOT_READY."""
        mock_runtime = mock_runtime_cls.return_value
        mock_runtime.is_available.return_value = False

        response = client.post(
            "/api/material-trace/export",
            data=json.dumps({"mode": "workorder", "values": ["WO-001"], "query_hash": "mtrace-miss-001"}),
            content_type="application/json",
        )
        assert response.status_code == 409
        payload = response.get_json()
        assert payload["success"] is False
        assert payload["error"]["code"] == "QUERY_NOT_READY"

    @patch("mes_dashboard.routes.material_trace_routes.MaterialTraceDuckdbRuntime")
    def test_export_after_spool_expiry_is_409(self, mock_runtime_cls, client):
        """If spool was created but has since expired, export must still return 409."""
        mock_runtime = mock_runtime_cls.return_value
        mock_runtime.is_available.return_value = False  # spool gone

        response = client.post(
            "/api/material-trace/export",
            data=json.dumps({
                "mode": "workorder",
                "values": ["WO-EXPIRED"],
                "query_hash": "mtrace-expired-001",
            }),
            content_type="application/json",
        )
        assert response.status_code == 409
        payload = response.get_json()
        assert payload["error"]["code"] == "QUERY_NOT_READY"

    @patch("mes_dashboard.routes.material_trace_routes.get_workcenter_groups")
    def test_filter_options_unavailable_returns_503(self, mock_groups, client):
        mock_groups.return_value = None

        response = client.get("/api/material-trace/filter-options")

        assert response.status_code == 503


class TestMemoryGuardContract:
    @patch("mes_dashboard.routes.material_trace_routes.MaterialTraceDuckdbRuntime")
    def test_query_memory_guard_returns_503(self, mock_runtime_cls, client):
        mock_runtime_cls.side_effect = MemoryError("記憶體負載較高")

        response = client.post(
            "/api/material-trace/query",
            data=json.dumps({"mode": "workorder", "values": ["WO-001"]}),
            content_type="application/json",
        )

        assert response.status_code == 503
        assert response.headers.get("Retry-After") == "30"
        payload = response.get_json()
        assert payload["success"] is False
