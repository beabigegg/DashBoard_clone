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
    """202/200-spool-hit/503 async branches (production-achievement-async-spool).

    Mocks is_async_available() + enqueue_query_job (CI has no Redis) for the
    202/503 branches, and get_spool_file_path + the two inline-map source
    functions for the 200 spool-hit branch -- never spool-hit mocks that
    would require real Redis (test-plan.md Notes).
    """

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

    # ── AC-1: spool miss + worker available -> 202 ──────────────────────────

    @patch("mes_dashboard.routes.production_achievement_routes.is_async_available", return_value=True)
    @patch("mes_dashboard.routes.production_achievement_routes.enqueue_query_job")
    @patch("mes_dashboard.routes.production_achievement_routes.get_spool_file_path", return_value=None)
    def test_report_spool_miss_enqueues_returns_202_with_job_id(
        self, mock_spool, mock_enqueue, mock_avail, auth_client
    ):
        mock_enqueue.return_value = ("production-achievement-abc123", None, None)
        resp = auth_client.get(
            "/api/production-achievement/report",
            query_string={"start_date": "2026-04-01", "end_date": "2026-04-02"},
        )
        assert resp.status_code == 202
        payload = resp.get_json()
        assert payload["success"] is True
        assert payload["data"]["async"] is True
        assert payload["data"]["job_id"] == "production-achievement-abc123"
        assert payload["data"]["status_url"] == (
            "/api/job/production-achievement-abc123?prefix=production-achievement"
        )

        # Per-kwarg assertion of the enqueue call (test-discipline.md).
        # params must be NESTED under a "params" key so enqueue_job_dynamic's
        # kwargs={"job_id": ..., **params} yields the worker's (job_id, params)
        # signature -- a flat dict here raises TypeError in the worker at runtime.
        call_kwargs = mock_enqueue.call_args.kwargs
        assert call_kwargs["params"] == {
            "params": {"start_date": "2026-04-01", "end_date": "2026-04-02"}
        }
        assert call_kwargs["sync_fallback_allowed"] is False

    @patch("mes_dashboard.routes.production_achievement_routes.is_async_available", return_value=True)
    @patch("mes_dashboard.routes.production_achievement_routes.enqueue_query_job")
    @patch("mes_dashboard.routes.production_achievement_routes.get_spool_file_path", return_value=None)
    def test_report_enqueue_params_bind_to_worker_signature(
        self, mock_spool, mock_enqueue, mock_avail, auth_client
    ):
        """Regression (real end-to-end bug): the params the route hands to
        enqueue_query_job must, once enqueue_job_dynamic spreads them into
        kwargs={"job_id": ..., **params}, bind cleanly to the RQ worker entry
        function execute_production_achievement_unified_job(job_id, params).

        The mocked-enqueue tests above never invoke the real worker, so a
        shape mismatch (flat params -> start_date/end_date spread as unexpected
        top-level kwargs) slips past them and only fails at worker runtime with
        `TypeError: got an unexpected keyword argument 'start_date'`.
        """
        import inspect

        from mes_dashboard.workers.production_achievement_worker import (
            execute_production_achievement_unified_job as worker_fn,
        )

        mock_enqueue.return_value = ("production-achievement-abc123", None, None)
        auth_client.get(
            "/api/production-achievement/report",
            query_string={"start_date": "2026-04-01", "end_date": "2026-04-02"},
        )
        # The exact params dict the route passed:
        route_params = mock_enqueue.call_args.kwargs["params"]
        # enqueue_job_dynamic builds the RQ call kwargs like this:
        rq_kwargs = {"job_id": "production-achievement-abc123", **route_params}
        # Must bind to the worker signature without TypeError:
        bound = inspect.signature(worker_fn).bind(**rq_kwargs)
        bound.apply_defaults()
        assert bound.arguments["job_id"] == "production-achievement-abc123"
        assert bound.arguments["params"] == {
            "start_date": "2026-04-01",
            "end_date": "2026-04-02",
        }

    @patch("mes_dashboard.routes.production_achievement_routes.is_async_available", return_value=True)
    @patch("mes_dashboard.routes.production_achievement_routes.enqueue_query_job")
    @patch("mes_dashboard.routes.production_achievement_routes.get_spool_file_path", return_value=None)
    def test_report_route_never_calls_get_achievement_report_or_read_sql_df(
        self, mock_spool, mock_enqueue, mock_avail, auth_client
    ):
        """AC-1: the request path must not import get_achievement_report --
        it was removed by production-achievement-async-spool."""
        import mes_dashboard.routes.production_achievement_routes as _routes
        assert not hasattr(_routes, "get_achievement_report")

        mock_enqueue.return_value = ("job-1", None, None)
        resp = auth_client.get(
            "/api/production-achievement/report",
            query_string={"start_date": "2026-04-01", "end_date": "2026-04-02"},
        )
        assert resp.status_code == 202

    # ── AC-2/AC-8: spool hit -> 200, unconditional map injection ────────────

    @patch(
        "mes_dashboard.routes.production_achievement_routes.get_targets_map",
        return_value={("D", "焊接_DB"): 500, ("N", "焊接_WB"): None},
    )
    @patch(
        "mes_dashboard.routes.production_achievement_routes.get_spec_workcenter_mapping",
        return_value={"EPOXY D/B": {"workcenter": "WC1", "group": "焊接_DB", "sequence": 1}},
    )
    @patch(
        "mes_dashboard.routes.production_achievement_routes.get_spool_file_path",
        return_value="/tmp/fake/spool.parquet",
    )
    def test_spool_hit_response_shape_has_spool_download_url_spec_map_targets_map(
        self, mock_spool, mock_spec_map, mock_targets_map, auth_client
    ):
        resp = auth_client.get(
            "/api/production-achievement/report",
            query_string={"start_date": "2026-04-01", "end_date": "2026-04-02"},
        )
        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload["success"] is True
        data = payload["data"]
        assert "query_id" in data
        assert data["spool_download_url"] == (
            f"/api/spool/production_achievement/{data['query_id']}.parquet"
        )
        assert data["spec_workcenter_map"] == [
            {"SPECNAME": "EPOXY D/B", "workcenter_group": "焊接_DB"}
        ]
        assert {"shift_code": "D", "workcenter_group": "焊接_DB", "target_qty": 500} in data["targets_map"]
        assert {"shift_code": "N", "workcenter_group": "焊接_WB", "target_qty": None} in data["targets_map"]
        # Enqueue must never be reached on a spool hit.
        mock_spool.assert_called_once()

    @patch(
        "mes_dashboard.routes.production_achievement_routes.get_targets_map",
        return_value={},
    )
    @patch(
        "mes_dashboard.routes.production_achievement_routes.get_spec_workcenter_mapping",
        return_value={},
    )
    @patch(
        "mes_dashboard.routes.production_achievement_routes.get_spool_file_path",
        return_value="/tmp/fake/spool.parquet",
    )
    def test_spool_hit_injects_download_url_unconditionally_not_row_count_gated(
        self, mock_spool, mock_spec_map, mock_targets_map, auth_client
    ):
        """AC-8: injection is unconditional -- even with empty maps (which
        would correspond to a tiny/empty spool), spool_download_url must
        still be present (unlike resource_history's row-count threshold)."""
        resp = auth_client.get(
            "/api/production-achievement/report",
            query_string={"start_date": "2026-04-01", "end_date": "2026-04-02"},
        )
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["spool_download_url"].startswith("/api/spool/production_achievement/")
        assert data["spec_workcenter_map"] == []
        assert data["targets_map"] == []

    # ── AC-1/AC-8: spool miss + no worker -> 503, no sync fallback ──────────

    @patch("mes_dashboard.routes.production_achievement_routes.is_async_available", return_value=False)
    @patch("mes_dashboard.routes.production_achievement_routes.enqueue_query_job")
    @patch("mes_dashboard.routes.production_achievement_routes.get_spool_file_path", return_value=None)
    def test_report_503_when_worker_unavailable(
        self, mock_spool, mock_enqueue, mock_avail, auth_client
    ):
        resp = auth_client.get(
            "/api/production-achievement/report",
            query_string={"start_date": "2026-04-01", "end_date": "2026-04-02"},
        )
        assert resp.status_code == 503
        payload = resp.get_json()
        assert payload["error"]["code"] == "SERVICE_UNAVAILABLE"
        mock_enqueue.assert_not_called()

    @patch("mes_dashboard.routes.production_achievement_routes.is_async_available", return_value=True)
    @patch("mes_dashboard.routes.production_achievement_routes.enqueue_query_job")
    @patch("mes_dashboard.routes.production_achievement_routes.get_spool_file_path", return_value=None)
    def test_report_503_when_enqueue_returns_none(
        self, mock_spool, mock_enqueue, mock_avail, auth_client
    ):
        """Kill-switch equivalent: unregistered job type / enqueue failure
        also surfaces as 503 (env-contract.md PRODUCTION_ACHIEVEMENT_USE_UNIFIED_JOB=off)."""
        mock_enqueue.return_value = (None, "Unknown job type: 'production-achievement'", None)
        resp = auth_client.get(
            "/api/production-achievement/report",
            query_string={"start_date": "2026-04-01", "end_date": "2026-04-02"},
        )
        assert resp.status_code == 503
        payload = resp.get_json()
        assert payload["error"]["code"] == "SERVICE_UNAVAILABLE"


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
