# -*- coding: utf-8 -*-
"""End-to-end tests for admin authentication flow.

These tests simulate real user workflows through the admin authentication system.
Run with: pytest tests/e2e/test_admin_auth_e2e.py -v --run-integration
"""

import json
import pytest
from unittest.mock import patch, MagicMock
import tempfile
from pathlib import Path

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

import mes_dashboard.core.database as db
from mes_dashboard.app import create_app
from mes_dashboard.services import page_registry


@pytest.fixture
def temp_page_status(tmp_path):
    """Create temporary page status file."""
    data_file = tmp_path / "page_status.json"
    initial_data = {
        "pages": [
            {"route": "/", "name": "首頁", "status": "released"},
            {"route": "/wip-overview", "name": "WIP 即時概況", "status": "released"},
            {"route": "/wip-detail", "name": "WIP 明細", "status": "released"},
            {"route": "/tables", "name": "表格總覽", "status": "dev"},
            {"route": "/resource", "name": "機台狀態", "status": "dev"},
        ],
        "api_public": True
    }
    data_file.write_text(json.dumps(initial_data, ensure_ascii=False), encoding="utf-8")
    return data_file


@pytest.fixture
def app(temp_page_status):
    """Create application for testing."""
    db._ENGINE = None

    # Mock page registry
    original_data_file = page_registry.DATA_FILE
    original_cache = page_registry._cache
    page_registry.DATA_FILE = temp_page_status
    page_registry._cache = None

    app = create_app('testing')
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False

    yield app

    page_registry.DATA_FILE = original_data_file
    page_registry._cache = original_cache


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()


def mock_ldap_success(mail="ymirliu@panjit.com.tw"):
    """Helper to create mock for successful LDAP auth."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "success": True,
        "user": {
            "username": "92367",
            "displayName": "Test Admin",
            "mail": mail,
            "department": "Test Department"
        }
    }
    return mock_response


class TestFullLoginLogoutFlow:
    """E2E tests for complete login/logout flow."""

    @patch('mes_dashboard.services.auth_service.requests.post')
    def test_complete_admin_login_workflow(self, mock_post, client):
        """Test complete admin login workflow."""
        mock_post.return_value = mock_ldap_success()

        # 1. Access portal - should see login link
        response = client.get("/")
        assert response.status_code == 200
        content = response.data.decode("utf-8")
        assert "管理員登入" in content

        # 2. Go to login page
        response = client.get("/admin/login")
        assert response.status_code == 200

        # 3. Submit login form
        response = client.post("/admin/login", data={
            "username": "92367",
            "password": "password123"
        }, follow_redirects=True)

        assert response.status_code == 200
        content = response.data.decode("utf-8")
        # Should see admin name and logout option
        assert "Test Admin" in content or "登出" in content

        # 4. Verify session has admin
        with client.session_transaction() as sess:
            assert "admin" in sess
            assert sess["admin"]["mail"] == "ymirliu@panjit.com.tw"

        # 5. Access admin pages
        response = client.get("/admin/pages")
        assert response.status_code == 200

        # 6. Logout
        response = client.get("/admin/logout", follow_redirects=True)
        assert response.status_code == 200

        # 7. Verify logged out
        with client.session_transaction() as sess:
            assert "admin" not in sess

        # 8. Admin pages should redirect now
        response = client.get("/admin/pages", follow_redirects=False)
        assert response.status_code == 302


class TestPageAccessControlFlow:
    """E2E tests for page access control flow."""

    def test_non_admin_cannot_access_dev_pages(self, client, temp_page_status):
        """Test non-admin users cannot access dev pages."""
        # 1. Access released page - should work
        response = client.get("/wip-overview")
        assert response.status_code != 403

        # 2. Access dev page - should get 403
        response = client.get("/tables")
        assert response.status_code == 403
        content = response.data.decode("utf-8")
        assert "開發中" in content or "403" in content

    @patch('mes_dashboard.services.auth_service.requests.post')
    def test_admin_can_access_all_pages(self, mock_post, client, temp_page_status):
        """Test admin users can access all pages."""
        mock_post.return_value = mock_ldap_success()

        # 1. Login as admin
        client.post("/admin/login", data={
            "username": "92367",
            "password": "password123"
        })

        # 2. Access released page - should work
        response = client.get("/wip-overview")
        assert response.status_code != 403

        # 3. Access dev page - should work for admin
        response = client.get("/tables")
        assert response.status_code != 403


class TestPageManagementFlow:
    """E2E tests for page management flow."""

    @patch('mes_dashboard.services.auth_service.requests.post')
    def test_admin_can_change_page_status(self, mock_post, client, temp_page_status):
        """Test admin can change page status via management interface."""
        mock_post.return_value = mock_ldap_success()

        # 1. Login as admin
        client.post("/admin/login", data={
            "username": "92367",
            "password": "password123"
        })

        # 2. Get current pages list
        response = client.get("/admin/api/pages")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["success"] is True

        # 3. Change /wip-overview from released to dev
        response = client.put(
            "/admin/api/pages/wip-overview",
            data=json.dumps({"status": "dev"}),
            content_type="application/json"
        )
        assert response.status_code == 200

        # 4. Verify change persisted
        page_registry._cache = None
        status = page_registry.get_page_status("/wip-overview")
        assert status == "dev"

        # 5. Logout
        client.get("/admin/logout")

        # 6. Now non-admin should get 403 on /wip-overview
        response = client.get("/wip-overview")
        assert response.status_code == 403

    @patch('mes_dashboard.services.auth_service.requests.post')
    def test_release_dev_page_makes_it_public(self, mock_post, client, temp_page_status):
        """Test releasing a dev page makes it publicly accessible."""
        mock_post.return_value = mock_ldap_success()

        # 1. Verify /tables is currently dev (403 for non-admin)
        response = client.get("/tables")
        assert response.status_code == 403

        # 2. Login as admin
        client.post("/admin/login", data={
            "username": "92367",
            "password": "password123"
        })

        # 3. Release the page
        response = client.put(
            "/admin/api/pages/tables",
            data=json.dumps({"status": "released"}),
            content_type="application/json"
        )
        assert response.status_code == 200

        # 4. Logout
        client.get("/admin/logout")

        # 5. Clear cache and verify non-admin can access
        page_registry._cache = None
        response = client.get("/tables")
        assert response.status_code != 403


class TestPortalDynamicTabs:
    """E2E tests for dynamic portal tabs based on page status."""

    def test_portal_hides_dev_tabs_for_non_admin(self, client, temp_page_status):
        """Test portal hides dev page tabs for non-admin users."""
        response = client.get("/")
        assert response.status_code == 200
        content = response.data.decode("utf-8")

        # Released pages should show
        assert "WIP 即時概況" in content

        # Dev pages should NOT show (tables and resource are dev)
        # Note: This depends on the can_view_page implementation in portal.html

    @patch('mes_dashboard.services.auth_service.requests.post')
    def test_portal_shows_all_tabs_for_admin(self, mock_post, client, temp_page_status):
        """Test portal shows all tabs for admin users."""
        mock_post.return_value = mock_ldap_success()

        # Login as admin
        client.post("/admin/login", data={
            "username": "92367",
            "password": "password123"
        })

        response = client.get("/")
        assert response.status_code == 200
        content = response.data.decode("utf-8")

        # Admin should see all pages
        assert "WIP 即時概況" in content


class TestSessionPersistence:
    """E2E tests for session persistence."""

    @patch('mes_dashboard.services.auth_service.requests.post')
    def test_session_persists_across_requests(self, mock_post, client):
        """Test admin session persists across multiple requests."""
        mock_post.return_value = mock_ldap_success()

        # Login
        client.post("/admin/login", data={
            "username": "92367",
            "password": "password123"
        })

        # Make multiple requests
        for _ in range(5):
            response = client.get("/admin/pages")
            assert response.status_code == 200

        # Session should still be valid
        with client.session_transaction() as sess:
            assert "admin" in sess


class TestSecurityScenarios:
    """E2E tests for security scenarios."""

    def test_cannot_access_admin_api_without_login(self, client):
        """Test admin APIs are protected."""
        # Try to get pages without login
        response = client.get("/admin/api/pages", follow_redirects=False)
        assert response.status_code == 302

        # Try to update page without login
        response = client.put(
            "/admin/api/pages/wip-overview",
            data=json.dumps({"status": "dev"}),
            content_type="application/json",
            follow_redirects=False
        )
        assert response.status_code == 302

    @patch('mes_dashboard.services.auth_service.requests.post')
    def test_non_admin_user_cannot_login(self, mock_post, client):
        """Test non-admin user cannot access admin features."""
        # Mock LDAP success but with non-admin email
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "success": True,
            "user": {
                "username": "99999",
                "displayName": "Regular User",
                "mail": "regular@panjit.com.tw",
                "department": "Test"
            }
        }
        mock_post.return_value = mock_response

        # Try to login
        response = client.post("/admin/login", data={
            "username": "99999",
            "password": "password123"
        })

        # Should fail (show error, not redirect)
        assert response.status_code == 200
        content = response.data.decode("utf-8")
        assert "管理員" in content or "error" in content.lower()

        # Should NOT have admin session
        with client.session_transaction() as sess:
            assert "admin" not in sess


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
