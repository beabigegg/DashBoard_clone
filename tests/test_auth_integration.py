# -*- coding: utf-8 -*-
"""Integration tests for user authentication routes and permission middleware."""

import json
import pytest
from unittest.mock import patch, MagicMock

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import mes_dashboard.core.database as db
from mes_dashboard.app import create_app
from mes_dashboard.services import page_registry


@pytest.fixture(autouse=True)
def _ldap_defaults(monkeypatch):
    monkeypatch.setattr("mes_dashboard.services.auth_service.LDAP_API_BASE", "https://ldap.panjit.example")
    monkeypatch.setattr("mes_dashboard.services.auth_service.LDAP_CONFIG_ERROR", None)


@pytest.fixture(autouse=True)
def _mock_login_session_store(monkeypatch):
    """Prevent tests from writing to the real login_sessions.sqlite."""
    mock_store = MagicMock()
    mock_store.create_session.return_value = "test-session-id"
    monkeypatch.setattr(
        "mes_dashboard.core.login_session_store.get_login_session_store",
        lambda: mock_store,
    )


@pytest.fixture
def temp_page_status(tmp_path):
    """Create temporary page status file."""
    data_file = tmp_path / "page_status.json"
    initial_data = {
        "pages": [
            {"route": "/", "name": "Portal", "status": "released"},
            {"route": "/wip-overview", "name": "WIP Overview", "status": "released"},
            {"route": "/dev-feature", "name": "Dev Feature", "status": "dev"},
        ],
        "api_public": True
    }
    data_file.write_text(json.dumps(initial_data), encoding="utf-8")
    return data_file


@pytest.fixture
def app(temp_page_status):
    """Create application for testing."""
    db._ENGINE = None

    # Mock page registry to use temp file
    original_data_file = page_registry.DATA_FILE
    original_cache = page_registry._cache
    page_registry.DATA_FILE = temp_page_status
    page_registry._cache = None

    app = create_app('testing')
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False

    yield app

    # Restore
    page_registry.DATA_FILE = original_data_file
    page_registry._cache = original_cache


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()


def _set_admin_session(client):
    """Helper: set session["user"] with admin flag."""
    with client.session_transaction() as sess:
        sess["user"] = {"username": "admin", "mail": "admin@test.com", "is_admin": True, "displayName": "Admin"}


def _api_login(client, username="92367", password="password123"):
    """Helper: POST /api/auth/login."""
    return client.post(
        "/api/auth/login",
        data=json.dumps({"username": username, "password": password}),
        content_type="application/json",
    )


class TestLoginRoute:
    """Tests for /api/auth/login route."""

    def test_login_api_returns_json(self, client):
        """Test login API endpoint is reachable."""
        with patch('mes_dashboard.routes.user_auth_routes.authenticate', return_value=None):
            response = client.post(
                "/api/auth/login",
                data=json.dumps({"username": "bad", "password": "bad"}),
                content_type="application/json",
            )
        assert response.status_code == 400
        assert response.is_json

    @patch('mes_dashboard.services.auth_service.LOCAL_AUTH_ENABLED', False)
    @patch('mes_dashboard.routes.user_auth_routes.is_admin', return_value=True)
    @patch('mes_dashboard.services.auth_service.requests.post')
    def test_login_success(self, mock_post, _mock_is_admin, client):
        """Test successful login via LDAP."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "success": True,
            "user": {
                "username": "92367",
                "displayName": "ymirliu Admin User",
                "mail": "ymirliu@panjit.com.tw",
                "department": "Test Dept",
                "telephoneNumber": "1234",
                "domain": "PANJIT",
            }
        }
        mock_post.return_value = mock_response

        response = client.post(
            "/api/auth/login",
            data=json.dumps({"username": "92367", "password": "password123"}),
            content_type="application/json",
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["data"]["is_admin"] is True

        with client.session_transaction() as sess:
            assert "user" in sess
            assert sess["user"]["username"] == "92367"

    @patch('mes_dashboard.services.auth_service.LOCAL_AUTH_ENABLED', False)
    @patch('mes_dashboard.services.auth_service.requests.post')
    def test_login_invalid_credentials(self, mock_post, client):
        """Test login with invalid credentials returns 400."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"success": False}
        mock_post.return_value = mock_response

        response = client.post(
            "/api/auth/login",
            data=json.dumps({"username": "wrong", "password": "wrong"}),
            content_type="application/json",
        )

        assert response.status_code == 400
        data = response.get_json()
        assert data["success"] is False

    @patch('mes_dashboard.services.auth_service.LOCAL_AUTH_ENABLED', False)
    @patch('mes_dashboard.routes.user_auth_routes.is_admin', return_value=False)
    @patch('mes_dashboard.services.auth_service.requests.post')
    def test_login_non_admin_user(self, mock_post, _mock_is_admin, client):
        """Test login with non-admin user succeeds but is_admin is False."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "success": True,
            "user": {
                "username": "99999",
                "displayName": "Regular User",
                "mail": "regular@panjit.com.tw",
                "department": "Test Dept",
                "telephoneNumber": "5678",
                "domain": "PANJIT",
            }
        }
        mock_post.return_value = mock_response

        response = client.post(
            "/api/auth/login",
            data=json.dumps({"username": "99999", "password": "password123"}),
            content_type="application/json",
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["data"]["is_admin"] is False

    def test_login_empty_credentials(self, client):
        """Test login with empty credentials returns 400."""
        response = client.post(
            "/api/auth/login",
            data=json.dumps({"username": "", "password": ""}),
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_login_blocks_external_next_redirect(self, client):
        """Login itself doesn't redirect; frontend handles next parameter."""
        # The JSON API returns data; routing is handled by the frontend
        with patch('mes_dashboard.routes.user_auth_routes.authenticate', return_value=None):
            response = client.post(
                "/api/auth/login",
                data=json.dumps({"username": "bad", "password": "bad"}),
                content_type="application/json",
            )
        # Should not 302 redirect at all — it's a JSON API
        assert response.status_code != 302

    def test_login_allows_internal_next_redirect(self, client):
        """Login is JSON-only; next redirect handled by frontend."""
        with patch('mes_dashboard.routes.user_auth_routes.authenticate', return_value=None):
            response = client.post(
                "/api/auth/login",
                data=json.dumps({"username": "bad", "password": "bad"}),
                content_type="application/json",
            )
        assert response.is_json


class TestLogoutRoute:
    """Tests for /api/auth/logout route."""

    def test_logout(self, client):
        """Test logout clears session."""
        _set_admin_session(client)

        response = client.post("/api/auth/logout")
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True

        with client.session_transaction() as sess:
            assert "user" not in sess


class TestPermissionMiddleware:
    """Tests for permission middleware."""

    def test_released_page_accessible_without_login(self, client):
        """Test released pages are accessible without login."""
        response = client.get("/wip-overview")
        assert response.status_code != 403

    def test_admin_pages_redirect_without_login(self, client):
        """Test admin pages redirect or return 401/403 without authentication."""
        response = client.get("/admin/pages", follow_redirects=False)
        assert response.status_code in (302, 401, 403)

    def test_admin_pages_accessible_with_login(self, client):
        """Test admin pages are accessible with admin login."""
        _set_admin_session(client)

        response = client.get("/admin/pages")
        assert response.status_code == 200


class TestAdminAPI:
    """Tests for admin API endpoints."""

    def test_get_pages_without_login(self, client):
        """Test get pages API requires login."""
        response = client.get("/admin/api/pages")
        assert response.status_code in (302, 401, 403)

    def test_get_pages_with_login(self, client):
        """Test get pages API with login."""
        _set_admin_session(client)

        response = client.get("/admin/api/pages")
        assert response.status_code == 200

        data = json.loads(response.data)
        assert data["success"] is True
        assert "pages" in data["data"]

    def test_get_drawers_without_login(self, client):
        """Test drawer API requires login."""
        response = client.get("/admin/api/drawers", follow_redirects=False)
        assert response.status_code in (302, 401, 403)

    def test_mutate_drawers_without_login(self, client):
        """Test drawer mutations require login."""
        response = client.post(
            "/admin/api/drawers",
            data=json.dumps({"name": "Unauthorized Drawer"}),
            content_type="application/json",
            follow_redirects=False,
        )
        assert response.status_code in (302, 401, 403)

        response = client.delete("/admin/api/drawers/reports", follow_redirects=False)
        assert response.status_code in (302, 401, 403)

    def test_get_drawers_with_login(self, client):
        """Test list drawers API with login."""
        _set_admin_session(client)

        response = client.get("/admin/api/drawers")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["success"] is True
        assert "drawers" in data["data"]
        assert any(drawer["id"] == "reports" for drawer in data["data"]["drawers"])

    def test_create_drawer_duplicate_name_conflict(self, client):
        """Test creating duplicate drawer name returns 409."""
        _set_admin_session(client)

        response = client.post(
            "/admin/api/drawers",
            data=json.dumps({"name": "報表類", "order": 99}),
            content_type="application/json",
        )
        assert response.status_code == 409

    def test_update_page_status(self, client, temp_page_status):
        """Test updating page status via API."""
        _set_admin_session(client)

        response = client.put(
            "/admin/api/pages/wip-overview",
            data=json.dumps({"status": "dev"}),
            content_type="application/json"
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["success"] is True

        page_registry._cache = None
        assert page_registry.get_page_status("/wip-overview") == "dev"

    def test_update_page_invalid_status(self, client):
        """Test updating page with invalid status."""
        _set_admin_session(client)

        response = client.put(
            "/admin/api/pages/wip-overview",
            data=json.dumps({"status": "invalid"}),
            content_type="application/json"
        )

        assert response.status_code == 400

    def test_update_page_drawer_assignment(self, client):
        """Test assigning page drawer via page update API."""
        _set_admin_session(client)

        response = client.put(
            "/admin/api/pages/wip-overview",
            data=json.dumps({"drawer_id": "queries", "order": 3}),
            content_type="application/json",
        )
        assert response.status_code == 200

        page_registry._cache = None
        pages = page_registry.get_all_pages()
        page = next(item for item in pages if item["route"] == "/wip-overview")
        assert page["drawer_id"] == "queries"
        assert page["order"] == 3

    def test_update_page_invalid_drawer_assignment(self, client):
        """Test assigning a non-existent drawer returns bad request."""
        _set_admin_session(client)

        response = client.put(
            "/admin/api/pages/wip-overview",
            data=json.dumps({"drawer_id": "missing-drawer"}),
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_delete_drawer_with_assigned_pages_conflict(self, client):
        """Test deleting a non-empty drawer returns conflict."""
        _set_admin_session(client)

        response = client.delete("/admin/api/drawers/reports")
        assert response.status_code == 409


class TestContextProcessor:
    """Tests for SPA shell auth context surface."""

    def test_is_admin_in_context_when_logged_in(self, client):
        """Test navigation API exposes admin context when logged in."""
        _set_admin_session(client)

        response = client.get("/api/portal/navigation")
        assert response.status_code == 200
        payload = response.get_json()
        assert payload["is_admin"] is True
        assert payload["admin_user"]["username"] == "admin"
        assert payload["admin_links"]["logout"] == "/api/auth/logout"

    def test_is_admin_in_context_when_not_logged_in(self, client):
        """Test navigation API hides admin context when not logged in."""
        response = client.get("/api/portal/navigation")
        assert response.status_code == 200
        payload = response.get_json()
        assert payload["is_admin"] is False
        assert payload["admin_user"] is None
        assert payload["admin_links"]["logout"] is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
