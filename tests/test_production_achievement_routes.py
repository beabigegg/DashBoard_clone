# -*- coding: utf-8 -*-
"""Route/contract tests for production-achievement endpoints (api-contract.md
rows 256-261).

Covers per-kwarg forwarding (test-discipline.md), permission gating (403/503),
and the admin-only whitelist endpoints.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from mes_dashboard.app import create_app


@pytest.fixture
def app():
    app = create_app("testing")
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth_client(app):
    c = app.test_client()
    with c.session_transaction() as sess:
        sess["user"] = {"username": "alice", "mail": "alice@test.com", "is_admin": False}
    return c


@pytest.fixture
def admin_client(app):
    c = app.test_client()
    with c.session_transaction() as sess:
        sess["user"] = {"username": "admin", "mail": "admin@test.com", "is_admin": True}
    return c


# ---------------------------------------------------------------------------
# GET /api/production-achievement/report
# ---------------------------------------------------------------------------

class TestReportRoute:
    def test_report_requires_login(self, client):
        resp = client.get(
            "/api/production-achievement/report",
            query_string={"start_date": "2026-04-01", "end_date": "2026-04-02"},
        )
        assert resp.status_code == 401

    def test_report_requires_date_range(self, auth_client):
        resp = auth_client.get("/api/production-achievement/report")
        assert resp.status_code == 400
        payload = resp.get_json()
        assert payload["success"] is False

    def test_report_rejects_over_730_day_range(self, auth_client):
        resp = auth_client.get(
            "/api/production-achievement/report",
            query_string={"start_date": "2020-01-01", "end_date": "2022-01-02"},
        )
        assert resp.status_code == 400

    @patch("mes_dashboard.routes.production_achievement_routes.get_achievement_report")
    def test_report_forwards_kwargs_per_key(self, mock_report, auth_client):
        mock_report.return_value = []
        auth_client.get(
            "/api/production-achievement/report",
            query_string={
                "start_date": "2026-04-01",
                "end_date": "2026-04-02",
                "shift_code": "D",
                "workcenter_group": "焊接_DB",
            },
        )
        assert mock_report.called
        kwargs = mock_report.call_args.kwargs
        assert kwargs["start_date"] == "2026-04-01"
        assert kwargs["end_date"] == "2026-04-02"
        assert kwargs["shift_code"] == "D"
        assert kwargs["workcenter_group"] == "焊接_DB"

    @patch("mes_dashboard.routes.production_achievement_routes.get_achievement_report")
    def test_report_forwards_optional_filters_as_none_when_absent(self, mock_report, auth_client):
        mock_report.return_value = []
        auth_client.get(
            "/api/production-achievement/report",
            query_string={"start_date": "2026-04-01", "end_date": "2026-04-02"},
        )
        kwargs = mock_report.call_args.kwargs
        assert kwargs["shift_code"] is None
        assert kwargs["workcenter_group"] is None


# ---------------------------------------------------------------------------
# GET /api/production-achievement/filter-options
# ---------------------------------------------------------------------------

class TestFilterOptionsRoute:
    def test_filter_options_requires_login(self, client):
        resp = client.get("/api/production-achievement/filter-options")
        assert resp.status_code == 401

    @patch("mes_dashboard.routes.production_achievement_routes.get_filter_options")
    def test_filter_options_returns_success(self, mock_options, auth_client):
        mock_options.return_value = {"shift_codes": ["N", "D"], "workcenter_groups": ["切割"]}
        resp = auth_client.get("/api/production-achievement/filter-options")
        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload["success"] is True


# ---------------------------------------------------------------------------
# GET /api/production-achievement/targets (view-only, no permission gate)
# ---------------------------------------------------------------------------

class TestGetTargetsRoute:
    def test_get_targets_no_permission_gate(self, auth_client):
        """Any authenticated user (not whitelisted) can GET targets."""
        with patch(
            "mes_dashboard.routes.production_achievement_routes.get_targets",
            return_value=[],
        ):
            resp = auth_client.get("/api/production-achievement/targets")
        assert resp.status_code == 200

    @patch("mes_dashboard.routes.production_achievement_routes.get_targets")
    def test_get_targets_forwards_optional_filter_kwargs(self, mock_get, auth_client):
        mock_get.return_value = []
        auth_client.get(
            "/api/production-achievement/targets",
            query_string={"shift_code": "D", "workcenter_group": "切割"},
        )
        kwargs = mock_get.call_args.kwargs
        assert kwargs["shift_code"] == "D"
        assert kwargs["workcenter_group"] == "切割"


# ---------------------------------------------------------------------------
# PUT /api/production-achievement/targets (permission-gated write)
# ---------------------------------------------------------------------------

class TestPutTargetsRoute:
    def test_put_targets_requires_login(self, client):
        resp = client.put(
            "/api/production-achievement/targets",
            json={"shift_code": "D", "workcenter_group": "切割", "target_qty": 100},
        )
        assert resp.status_code == 401

    @patch("mes_dashboard.routes.production_achievement_routes.can_edit_targets", return_value=False)
    def test_put_targets_403_when_not_whitelisted(self, mock_can_edit, auth_client):
        resp = auth_client.put(
            "/api/production-achievement/targets",
            json={"shift_code": "D", "workcenter_group": "切割", "target_qty": 100},
        )
        assert resp.status_code == 403
        payload = resp.get_json()
        assert payload["error"]["code"] == "FORBIDDEN"

    @patch("mes_dashboard.routes.production_achievement_routes.can_edit_targets", return_value=True)
    @patch("mes_dashboard.routes.production_achievement_routes.MYSQL_OPS_ENABLED", False)
    def test_put_targets_503_when_mysql_ops_disabled(self, mock_can_edit, auth_client):
        resp = auth_client.put(
            "/api/production-achievement/targets",
            json={"shift_code": "D", "workcenter_group": "切割", "target_qty": 100},
        )
        assert resp.status_code == 503
        payload = resp.get_json()
        assert payload["error"]["code"] == "SERVICE_UNAVAILABLE"

    @patch("mes_dashboard.routes.production_achievement_routes.can_edit_targets", return_value=True)
    @patch("mes_dashboard.routes.production_achievement_routes.MYSQL_OPS_ENABLED", True)
    @patch("mes_dashboard.routes.production_achievement_routes.upsert_target")
    def test_put_targets_success_forwards_kwargs(self, mock_upsert, mock_can_edit, auth_client):
        resp = auth_client.put(
            "/api/production-achievement/targets",
            json={"shift_code": "D", "workcenter_group": "切割", "target_qty": 100},
        )
        assert resp.status_code == 200
        kwargs = mock_upsert.call_args.kwargs
        assert kwargs["shift_code"] == "D"
        assert kwargs["workcenter_group"] == "切割"
        assert kwargs["target_qty"] == 100
        assert kwargs["updated_by"] == "alice"

    @patch("mes_dashboard.routes.production_achievement_routes.can_edit_targets", return_value=True)
    @patch("mes_dashboard.routes.production_achievement_routes.MYSQL_OPS_ENABLED", True)
    def test_put_targets_rejects_negative_qty(self, mock_can_edit, auth_client):
        resp = auth_client.put(
            "/api/production-achievement/targets",
            json={"shift_code": "D", "workcenter_group": "切割", "target_qty": -5},
        )
        assert resp.status_code == 400
        payload = resp.get_json()
        assert payload["error"]["code"] == "VALIDATION_ERROR"

    @patch("mes_dashboard.routes.production_achievement_routes.can_edit_targets", return_value=True)
    @patch("mes_dashboard.routes.production_achievement_routes.MYSQL_OPS_ENABLED", True)
    def test_put_targets_rejects_non_numeric_qty(self, mock_can_edit, auth_client):
        resp = auth_client.put(
            "/api/production-achievement/targets",
            json={"shift_code": "D", "workcenter_group": "切割", "target_qty": "abc"},
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Admin permission-management endpoints
# ---------------------------------------------------------------------------

class TestAdminPermissionsRoutes:
    def test_admin_get_permissions_requires_admin(self, auth_client):
        """Non-admin authenticated user is blocked from admin permissions endpoints."""
        resp = auth_client.get(
            "/admin/api/production-achievement/permissions",
            headers={"Accept": "application/json"},
        )
        assert resp.status_code in (401, 403)

    @patch("mes_dashboard.routes.production_achievement_routes.get_permissions")
    @patch("mes_dashboard.routes.production_achievement_routes.MYSQL_OPS_ENABLED", True)
    def test_admin_get_permissions_success(self, mock_get, admin_client):
        mock_get.return_value = []
        resp = admin_client.get("/admin/api/production-achievement/permissions")
        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload["success"] is True

    def test_admin_permissions_put_requires_admin(self, auth_client):
        resp = auth_client.put(
            "/admin/api/production-achievement/permissions/alice",
            json={"can_edit_targets": True},
        )
        assert resp.status_code in (401, 403)

    @patch("mes_dashboard.routes.production_achievement_routes.upsert_permission")
    @patch("mes_dashboard.routes.production_achievement_routes.MYSQL_OPS_ENABLED", True)
    def test_admin_permissions_put_forwards_kwargs(self, mock_upsert, admin_client):
        resp = admin_client.put(
            "/admin/api/production-achievement/permissions/alice",
            json={"can_edit_targets": True},
        )
        assert resp.status_code == 200
        kwargs = mock_upsert.call_args.kwargs
        assert kwargs["user_identifier"] == "alice"
        assert kwargs["can_edit_targets"] is True
        assert kwargs["granted_by"] == "admin"

    @patch("mes_dashboard.routes.production_achievement_routes.upsert_permission")
    @patch("mes_dashboard.routes.production_achievement_routes.MYSQL_OPS_ENABLED", False)
    def test_admin_permissions_put_503_when_ops_disabled(self, mock_upsert, admin_client):
        resp = admin_client.put(
            "/admin/api/production-achievement/permissions/alice",
            json={"can_edit_targets": True},
        )
        assert resp.status_code == 503
