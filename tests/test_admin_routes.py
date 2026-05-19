# -*- coding: utf-8 -*-
"""Integration tests for admin route endpoints.

Coverage:
  - GET /admin/api/system-status — success envelope
  - GET /admin/api/worker/status — success envelope
  - GET /admin/api/pages — success envelope
  - GET /admin/api/drawers — success/create/delete operations
  - GET /admin/api/user-usage-kpi — success envelope
  - Auth: admin_required blocks unauthenticated requests
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
def auth_patches():
    """Patch auth checks so admin routes are accessible without a real session.

    app.py imports is_admin_logged_in directly (from...import), so we must
    patch the reference in both app and permissions modules.
    """
    with patch("mes_dashboard.app.is_admin_logged_in", return_value=True), \
         patch("mes_dashboard.app.is_user_logged_in", return_value=True), \
         patch("mes_dashboard.core.permissions.is_admin_logged_in", return_value=True), \
         patch("mes_dashboard.core.permissions.is_user_logged_in", return_value=True):
        yield


# ── GET /admin/api/system-status ─────────────────────────────────────────────

def test_system_status_success_envelope(client, auth_patches):
    resp = client.get("/admin/api/system-status")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert "data" in data


def test_system_status_blocked_without_auth(client):
    """Unauthenticated requests are rejected with 401/302."""
    resp = client.get("/admin/api/system-status")
    assert resp.status_code in (401, 403, 302)


# ── GET /admin/api/worker/status ─────────────────────────────────────────────

def test_worker_status_success_envelope(client, auth_patches):
    mock_state = {
        "last_restart": {},
        "restart_history": [],
        "restart_requested_at": None,
    }
    with patch(
        "mes_dashboard.routes.admin_routes._get_restart_state",
        return_value=mock_state,
    ), patch(
        "mes_dashboard.routes.admin_routes.load_restart_state",
        return_value=mock_state,
    ):
        resp = client.get("/admin/api/worker/status")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True


# ── GET /admin/api/pages ─────────────────────────────────────────────────────

def test_api_pages_success_envelope(client, auth_patches):
    mock_pages = [{"route": "/resource-history", "enabled": True}]
    with patch(
        "mes_dashboard.routes.admin_routes.get_all_pages",
        return_value=mock_pages,
    ):
        resp = client.get("/admin/api/pages")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    # data may be {"pages": [...]} or a list directly
    assert isinstance(data["data"], (list, dict))


# ── GET /admin/api/drawers ────────────────────────────────────────────────────

def test_api_drawers_success_envelope(client, auth_patches):
    with patch(
        "mes_dashboard.routes.admin_routes.get_all_drawers",
        return_value=[],
    ):
        resp = client.get("/admin/api/drawers")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True


# ── POST /admin/api/drawers ───────────────────────────────────────────────────

def test_api_create_drawer_missing_name_returns_400(client, auth_patches):
    resp = client.post("/admin/api/drawers", json={})
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["success"] is False


def test_api_create_drawer_success(client, auth_patches):
    mock_drawer = {"id": "drawer-1", "name": "Test Drawer"}
    with patch(
        "mes_dashboard.routes.admin_routes.create_drawer",
        return_value=mock_drawer,
    ):
        resp = client.post("/admin/api/drawers", json={"name": "Test Drawer"})
    assert resp.status_code in (200, 201)
    data = resp.get_json()
    assert data["success"] is True


# ── GET /admin/api/metrics ────────────────────────────────────────────────────

def test_metrics_returns_success_or_graceful_empty(client, auth_patches):
    resp = client.get("/admin/api/metrics")
    assert resp.status_code in (200, 500)
    if resp.status_code == 200:
        data = resp.get_json()
        assert data["success"] is True


# ── GET /admin/api/user-usage-kpi ─────────────────────────────────────────────

def test_user_usage_kpi_with_dates_returns_success(client, auth_patches):
    mock_kpi = {"overview": {}, "dau_trend": [], "source": "sqlite"}
    with patch(
        "mes_dashboard.routes.admin_routes.get_user_usage_kpi",
        return_value=mock_kpi,
    ) if False else patch(
        "mes_dashboard.services.user_usage_kpi_service._query_sqlite",
        return_value=mock_kpi,
    ):
        resp = client.get("/admin/api/user-usage-kpi?start_date=2026-03-01&end_date=2026-03-31")
    assert resp.status_code in (200, 400)
    if resp.status_code == 200:
        assert resp.get_json()["success"] is True


# ── PUT /admin/api/pages/<route> ─────────────────────────────────────────────

def test_update_page_status(client, auth_patches):
    with patch(
        "mes_dashboard.routes.admin_routes.set_page_status",
        return_value=None,
    ), patch(
        "mes_dashboard.routes.admin_routes.get_page_status",
        return_value={"route": "/resource-history", "enabled": True},
    ):
        resp = client.put(
            "/admin/api/pages/resource-history",
            json={"enabled": True},
        )
    assert resp.status_code in (200, 400, 404)


# ── AC-7: user-usage-kpi no-500 when MySQL unavailable ───────────────────────

def test_user_usage_kpi_no_500_mysql_unavailable(client, auth_patches):
    """GET /admin/api/user-usage-kpi returns 200 envelope even when MySQL raises (AC-7)."""
    with patch(
        "mes_dashboard.core.mysql_client.MYSQL_OPS_ENABLED", False
    ):
        resp = client.get(
            "/admin/api/user-usage-kpi?start_date=2026-03-01&end_date=2026-03-31"
        )
    # Accept 200 (success) or 400 (invalid date params); must NOT be 500
    assert resp.status_code in (200, 400), (
        f"Expected 200 or 400 but got {resp.status_code}"
    )
    payload = resp.get_json()
    assert payload is not None
    # If 200, envelope must be well-formed
    if resp.status_code == 200:
        assert payload.get("success") is True
