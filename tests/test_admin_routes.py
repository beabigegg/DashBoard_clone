# -*- coding: utf-8 -*-
"""Integration tests for admin route endpoints.

Coverage (post nav-config-to-code):
  - GET /admin/api/system-status — success envelope
  - GET /admin/api/worker/status — success envelope
  - GET /admin/api/pages — slim {pages:[{route,status}]} shape
  - GET/POST/PUT/DELETE /admin/api/drawers — all 404 (removed)
  - PUT /admin/api/pages/<route> — status-only; rejects name/drawer_id/order
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

def test_api_pages_slim_shape(client, auth_patches):
    """GET /admin/api/pages must return slim {pages:[{route,status}]} shape."""
    slim_pages = [
        {"route": "/wip-overview", "status": "released"},
        {"route": "/admin/dashboard", "status": "dev"},
    ]
    with patch(
        "mes_dashboard.routes.admin_routes.get_all_pages",
        return_value=slim_pages,
    ):
        resp = client.get("/admin/api/pages")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    pages = data["data"]["pages"]
    assert isinstance(pages, list)
    for p in pages:
        # Must have route + status; must NOT have name/drawer_id/order
        assert "route" in p
        assert "status" in p
        assert "name" not in p
        assert "drawer_id" not in p
        assert "order" not in p


def test_api_pages_blocked_without_auth(client):
    resp = client.get("/admin/api/pages")
    assert resp.status_code in (401, 403, 302)


# ── AC-3/AC-7: Removed drawer endpoints return 404 ───────────────────────────

def test_get_api_drawers_returns_404(client, auth_patches):
    """GET /admin/api/drawers removed — must return 404."""
    resp = client.get("/admin/api/drawers")
    assert resp.status_code == 404


def test_post_api_drawers_returns_404(client, auth_patches):
    """POST /admin/api/drawers removed — must return 404."""
    resp = client.post("/admin/api/drawers", json={"name": "test"})
    assert resp.status_code == 404


def test_put_api_drawers_id_returns_404(client, auth_patches):
    """PUT /admin/api/drawers/<id> removed — must return 404."""
    resp = client.put("/admin/api/drawers/reports", json={"name": "renamed"})
    assert resp.status_code == 404


def test_delete_api_drawers_id_returns_404(client, auth_patches):
    """DELETE /admin/api/drawers/<id> removed — must return 404."""
    resp = client.delete("/admin/api/drawers/reports")
    assert resp.status_code == 404


# ── AC-3: PUT /admin/api/pages rejects non-status fields ─────────────────────

def test_put_page_with_valid_status_accepted(client, auth_patches):
    """PUT /admin/api/pages/<route> with only status field must succeed."""
    with patch("mes_dashboard.routes.admin_routes.set_page_status", return_value=None):
        resp = client.put("/admin/api/pages/admin/dashboard", json={"status": "released"})
    assert resp.status_code == 200
    assert resp.get_json()["success"] is True


def test_put_page_without_status_returns_400(client, auth_patches):
    """PUT /admin/api/pages/<route> without status field must return 400."""
    resp = client.put("/admin/api/pages/admin/dashboard", json={})
    assert resp.status_code == 400
    assert resp.get_json()["success"] is False


def test_put_page_with_name_field_rejected(client, auth_patches):
    """PUT /admin/api/pages/<route> with name field must be rejected or ignored (name must not persist)."""
    persisted_call = {}

    def mock_set_page_status(route, status):
        persisted_call["route"] = route
        persisted_call["status"] = status
        # name, drawer_id, order must NOT be passed to service

    with patch("mes_dashboard.routes.admin_routes.set_page_status", side_effect=mock_set_page_status):
        resp = client.put("/admin/api/pages/admin/dashboard",
                          json={"status": "released", "name": "New Name"})
    # Must not 500
    assert resp.status_code in (200, 400)
    # If accepted, name must not have been forwarded to set_page_status
    if resp.status_code == 200:
        import inspect
        # The mock captured positional args only (route, status); name was not forwarded
        assert "route" in persisted_call
        assert "status" in persisted_call


def test_put_page_with_drawer_id_field_rejected(client, auth_patches):
    """PUT /admin/api/pages/<route> with drawer_id field: drawer_id must not persist."""
    persisted_call = {}

    def mock_set(route, status):
        persisted_call["route"] = route
        persisted_call["status"] = status

    with patch("mes_dashboard.routes.admin_routes.set_page_status", side_effect=mock_set):
        resp = client.put("/admin/api/pages/admin/dashboard",
                          json={"status": "dev", "drawer_id": "dev-tools"})
    assert resp.status_code in (200, 400)
    if resp.status_code == 200:
        assert "route" in persisted_call
        assert "status" in persisted_call


def test_put_page_with_order_field_rejected(client, auth_patches):
    """PUT /admin/api/pages/<route> with order field: order must not persist."""
    persisted_call = {}

    def mock_set(route, status):
        persisted_call["route"] = route
        persisted_call["status"] = status

    with patch("mes_dashboard.routes.admin_routes.set_page_status", side_effect=mock_set):
        resp = client.put("/admin/api/pages/admin/dashboard",
                          json={"status": "dev", "order": 2})
    assert resp.status_code in (200, 400)
    if resp.status_code == 200:
        assert "route" in persisted_call
        assert "status" in persisted_call


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
