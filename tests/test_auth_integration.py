# -*- coding: utf-8 -*-
"""Integration tests for authentication routes and permission middleware."""

import json
import pytest
from unittest.mock import patch, MagicMock
import tempfile
from pathlib import Path

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import mes_dashboard.core.database as db
from mes_dashboard.app import create_app
from mes_dashboard.services import page_registry


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


class TestLoginRoute:
    """Tests for login route."""

    def test_login_page_renders(self, client):
        """Test login page is accessible."""
        response = client.get("/admin/login")
        assert response.status_code == 200
        assert "管理員登入" in response.data.decode("utf-8") or "login" in response.data.decode("utf-8").lower()

    @patch('mes_dashboard.services.auth_service.requests.post')
    def test_login_success(self, mock_post, client):
        """Test successful login."""
        # Mock LDAP response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "success": True,
            "user": {
                "username": "92367",
                "displayName": "Admin User",
                "mail": "ymirliu@panjit.com.tw",
                "department": "Test Dept"
            }
        }
        mock_post.return_value = mock_response

        response = client.post("/admin/login", data={
            "username": "92367",
            "password": "password123"
        }, follow_redirects=False)

        # Should redirect after successful login
        assert response.status_code == 302

        # Check session contains admin
        with client.session_transaction() as sess:
            assert "admin" in sess
            assert sess["admin"]["username"] == "92367"

    @patch('mes_dashboard.services.auth_service.requests.post')
    def test_login_invalid_credentials(self, mock_post, client):
        """Test login with invalid credentials."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"success": False}
        mock_post.return_value = mock_response

        response = client.post("/admin/login", data={
            "username": "wrong",
            "password": "wrong"
        })

        assert response.status_code == 200
        # Should show error message
        assert "錯誤" in response.data.decode("utf-8") or "error" in response.data.decode("utf-8").lower()

    @patch('mes_dashboard.services.auth_service.requests.post')
    def test_login_non_admin_user(self, mock_post, client):
        """Test login with non-admin user."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "success": True,
            "user": {
                "username": "99999",
                "displayName": "Regular User",
                "mail": "regular@panjit.com.tw",
                "department": "Test Dept"
            }
        }
        mock_post.return_value = mock_response

        response = client.post("/admin/login", data={
            "username": "99999",
            "password": "password123"
        })

        assert response.status_code == 200
        # Should show non-admin error
        content = response.data.decode("utf-8")
        assert "管理員" in content or "admin" in content.lower()

    def test_login_empty_credentials(self, client):
        """Test login with empty credentials."""
        response = client.post("/admin/login", data={
            "username": "",
            "password": ""
        })

        assert response.status_code == 200


class TestLogoutRoute:
    """Tests for logout route."""

    def test_logout(self, client):
        """Test logout clears session."""
        # Login first
        with client.session_transaction() as sess:
            sess["admin"] = {"username": "admin"}

        response = client.get("/admin/logout", follow_redirects=False)

        assert response.status_code == 302

        with client.session_transaction() as sess:
            assert "admin" not in sess


class TestPermissionMiddleware:
    """Tests for permission middleware."""

    def test_released_page_accessible_without_login(self, client):
        """Test released pages are accessible without login."""
        response = client.get("/wip-overview")
        # Should not be 403 (might be 200 or redirect)
        assert response.status_code != 403

    def test_dev_page_returns_403_without_login(self, client, temp_page_status):
        """Test dev pages return 403 for non-admin."""
        # Add a dev route that exists in the app
        # First update page status to have an existing route as dev
        data = json.loads(temp_page_status.read_text())
        data["pages"].append({"route": "/tables", "name": "Tables", "status": "dev"})
        temp_page_status.write_text(json.dumps(data))
        page_registry._cache = None

        response = client.get("/tables")
        assert response.status_code == 403

    def test_dev_page_accessible_with_admin_login(self, client, temp_page_status):
        """Test dev pages are accessible for admin."""
        # Update tables to dev
        data = json.loads(temp_page_status.read_text())
        data["pages"].append({"route": "/tables", "name": "Tables", "status": "dev"})
        temp_page_status.write_text(json.dumps(data))
        page_registry._cache = None

        # Login as admin
        with client.session_transaction() as sess:
            sess["admin"] = {"username": "admin", "mail": "admin@test.com"}

        response = client.get("/tables")
        assert response.status_code != 403

    def test_admin_pages_redirect_without_login(self, client):
        """Test admin pages redirect to login without authentication."""
        response = client.get("/admin/pages", follow_redirects=False)
        assert response.status_code == 302
        assert "/admin/login" in response.location

    def test_admin_pages_accessible_with_login(self, client):
        """Test admin pages are accessible with login."""
        with client.session_transaction() as sess:
            sess["admin"] = {"username": "admin", "mail": "admin@test.com"}

        response = client.get("/admin/pages")
        assert response.status_code == 200


class TestAdminAPI:
    """Tests for admin API endpoints."""

    def test_get_pages_without_login(self, client):
        """Test get pages API requires login."""
        response = client.get("/admin/api/pages")
        # Should redirect
        assert response.status_code == 302

    def test_get_pages_with_login(self, client):
        """Test get pages API with login."""
        with client.session_transaction() as sess:
            sess["admin"] = {"username": "admin"}

        response = client.get("/admin/api/pages")
        assert response.status_code == 200

        data = json.loads(response.data)
        assert data["success"] is True
        assert "pages" in data

    def test_update_page_status(self, client, temp_page_status):
        """Test updating page status via API."""
        with client.session_transaction() as sess:
            sess["admin"] = {"username": "admin"}

        response = client.put(
            "/admin/api/pages/wip-overview",
            data=json.dumps({"status": "dev"}),
            content_type="application/json"
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["success"] is True

        # Verify status changed
        page_registry._cache = None
        assert page_registry.get_page_status("/wip-overview") == "dev"

    def test_update_page_invalid_status(self, client):
        """Test updating page with invalid status."""
        with client.session_transaction() as sess:
            sess["admin"] = {"username": "admin"}

        response = client.put(
            "/admin/api/pages/wip-overview",
            data=json.dumps({"status": "invalid"}),
            content_type="application/json"
        )

        assert response.status_code == 400


class TestContextProcessor:
    """Tests for template context processor."""

    def test_is_admin_in_context_when_logged_in(self, client):
        """Test is_admin is True in context when logged in."""
        with client.session_transaction() as sess:
            sess["admin"] = {"username": "admin", "displayName": "Admin"}

        response = client.get("/")
        content = response.data.decode("utf-8")

        # Should show admin-related content (logout link, etc.)
        assert "登出" in content or "logout" in content.lower() or "Admin" in content

    def test_is_admin_in_context_when_not_logged_in(self, client):
        """Test is_admin is False in context when not logged in."""
        response = client.get("/")
        content = response.data.decode("utf-8")

        # Should show login link, not logout
        assert "管理員登入" in content or "login" in content.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
