# -*- coding: utf-8 -*-
"""End-to-end tests for user authentication flow.

These tests simulate real user workflows through the unified user authentication system.
Run with: pytest tests/e2e/test_admin_auth_e2e.py -v --run-integration
"""

import json
import pytest
from unittest.mock import patch

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

import mes_dashboard.core.database as db
from mes_dashboard.app import create_app
from mes_dashboard.services import page_registry
from mes_dashboard.routes import user_auth_routes

pytestmark = [pytest.mark.e2e, pytest.mark.local_e2e]


@pytest.fixture
def temp_page_status(tmp_path):
    """Create temporary page status file."""
    data_file = tmp_path / "page_status.json"
    initial_data = {
        "pages": [
            {"route": "/", "name": "首頁", "status": "released"},
            {"route": "/wip-overview", "name": "WIP 即時概況", "status": "released"},
            {"route": "/wip-detail", "name": "WIP 明細", "status": "released"},
            {"route": "/production-history", "name": "生產歷程", "status": "dev"},
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
    app.config['CSRF_ENABLED'] = False

    yield app

    page_registry.DATA_FILE = original_data_file
    page_registry._cache = original_cache


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()


@pytest.fixture(autouse=True)
def clear_login_rate_limit():
    """Reset in-memory login attempts to avoid cross-test interference."""
    user_auth_routes._login_attempts.clear()
    yield
    user_auth_routes._login_attempts.clear()


def _mock_admin_user(mail: str = "ymirliu@panjit.com.tw") -> dict:
    return {
        "username": "92367",
        "displayName": "ymirliu Test Admin",
        "mail": mail,
        "department": "Test Department",
        "telephoneNumber": "1234",
        "domain": "PANJIT",
    }


def _do_api_login(client, mock_auth, mock_is_admin, username="92367", password="password123"):
    """Helper: POST /api/auth/login."""
    mock_auth.return_value = _mock_admin_user()
    return client.post(
        "/api/auth/login",
        data=json.dumps({"username": username, "password": password}),
        content_type="application/json",
    )


class TestFullLoginLogoutFlow:
    """E2E tests for complete login/logout flow."""

    @patch('mes_dashboard.routes.user_auth_routes.is_admin', return_value=True)
    @patch('mes_dashboard.routes.user_auth_routes.authenticate')
    def test_complete_admin_login_workflow(self, mock_auth, _mock_is_admin, client):
        """Test complete admin login workflow via JSON API."""
        mock_auth.return_value = _mock_admin_user()

        # 1. Login via JSON API
        response = client.post(
            "/api/auth/login",
            data=json.dumps({"username": "92367", "password": "password123"}),
            content_type="application/json",
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["data"]["is_admin"] is True

        # 2. Verify session has user
        with client.session_transaction() as sess:
            assert "user" in sess
            assert sess["user"]["mail"] == "ymirliu@panjit.com.tw"
            assert sess["user"]["is_admin"] is True

        # 3. /api/auth/me should return user info
        me_response = client.get("/api/auth/me")
        assert me_response.status_code == 200
        me_data = me_response.get_json()
        assert me_data["data"]["is_admin"] is True

        # 4. Navigation shows admin
        nav = client.get("/api/portal/navigation")
        assert nav.status_code == 200
        assert nav.get_json()["is_admin"] is True

        # 5. Admin pages accessible
        response = client.get("/admin/pages")
        assert response.status_code == 200

        # 6. Logout
        response = client.post("/api/auth/logout")
        assert response.status_code == 200

        # 7. Verify logged out
        with client.session_transaction() as sess:
            assert "user" not in sess

        # 8. Admin pages should now be rejected
        response = client.get("/admin/pages", follow_redirects=False)
        assert response.status_code in (302, 401, 403)


class TestPageAccessControlFlow:
    """E2E tests for page access control flow."""

    def test_non_admin_cannot_access_dev_pages(self, client, temp_page_status):
        """Test non-admin users cannot access dev pages."""
        # 1. Access released page - should work
        response = client.get("/wip-overview")
        assert response.status_code != 403

        # 2. Access dev page - should get 403
        response = client.get("/production-history")
        assert response.status_code == 403
        content = response.data.decode("utf-8")
        assert "開發中" in content or "403" in content

    @patch('mes_dashboard.routes.user_auth_routes.is_admin', return_value=True)
    @patch('mes_dashboard.routes.user_auth_routes.authenticate')
    def test_admin_can_access_all_pages(self, mock_auth, _mock_is_admin, client, temp_page_status):
        """Test admin users can access all pages."""
        mock_auth.return_value = _mock_admin_user()

        # 1. Login as admin
        client.post(
            "/api/auth/login",
            data=json.dumps({"username": "92367", "password": "password123"}),
            content_type="application/json",
        )

        # 2. Access released page - should work
        response = client.get("/wip-overview")
        assert response.status_code != 403

        # 3. Access dev page - should work for admin
        response = client.get("/production-history")
        assert response.status_code != 403


class TestPageManagementFlow:
    """E2E tests for page management flow."""

    @patch('mes_dashboard.routes.user_auth_routes.is_admin', return_value=True)
    @patch('mes_dashboard.routes.user_auth_routes.authenticate')
    def test_admin_can_change_page_status(self, mock_auth, _mock_is_admin, client, temp_page_status):
        """Test admin can change page status via management interface."""
        mock_auth.return_value = _mock_admin_user()

        # 1. Login as admin
        client.post(
            "/api/auth/login",
            data=json.dumps({"username": "92367", "password": "password123"}),
            content_type="application/json",
        )

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
        client.post("/api/auth/logout")

        # 6. Now non-admin should get 403 on /wip-overview
        response = client.get("/wip-overview")
        assert response.status_code == 403

    @patch('mes_dashboard.routes.user_auth_routes.is_admin', return_value=True)
    @patch('mes_dashboard.routes.user_auth_routes.authenticate')
    def test_release_dev_page_makes_it_public(self, mock_auth, _mock_is_admin, client, temp_page_status):
        """Test releasing a dev page makes it publicly accessible."""
        mock_auth.return_value = _mock_admin_user()

        # 1. Verify /production-history is currently dev (403 for non-admin)
        response = client.get("/production-history")
        assert response.status_code == 403

        # 2. Login as admin
        client.post(
            "/api/auth/login",
            data=json.dumps({"username": "92367", "password": "password123"}),
            content_type="application/json",
        )

        # 3. Release the page
        response = client.put(
            "/admin/api/pages/production-history",
            data=json.dumps({"status": "released"}),
            content_type="application/json"
        )
        assert response.status_code == 200

        # 4. Logout
        client.post("/api/auth/logout")

        # 5. Clear cache and verify non-admin can access
        page_registry._cache = None
        response = client.get("/production-history")
        assert response.status_code != 403


class TestPortalDynamicTabs:
    """E2E tests for dynamic portal tabs based on page status."""

    def test_portal_hides_dev_tabs_for_non_admin(self, client, temp_page_status):
        """Test portal reports statuses for the frontend to hide dev tabs for non-admin.

        After nav-config-to-code, drawer/page structure and the admin-based
        dev-tab filtering both live client-side in navigationState.js
        (buildDynamicNavigationState). The backend's only remaining
        responsibility is to report each route's raw status and is_admin
        faithfully (unfiltered) — that's what this test verifies.
        """
        response = client.get("/api/portal/navigation")
        assert response.status_code == 200
        payload = response.get_json()
        statuses = payload.get("statuses", {})
        assert statuses.get("/wip-overview") == "released"
        assert statuses.get("/production-history") == "dev"
        assert payload.get("is_admin") is False

    @patch('mes_dashboard.routes.user_auth_routes.is_admin', return_value=True)
    @patch('mes_dashboard.routes.user_auth_routes.authenticate')
    def test_portal_shows_all_tabs_for_admin(self, mock_auth, _mock_is_admin, client, temp_page_status):
        """Test portal reports is_admin=True so the frontend shows all tabs.

        Same rationale as test_portal_hides_dev_tabs_for_non_admin — statuses
        are always returned unfiltered; only is_admin distinguishes the two
        cases at the backend layer.
        """
        mock_auth.return_value = _mock_admin_user()

        # Login as admin
        client.post(
            "/api/auth/login",
            data=json.dumps({"username": "92367", "password": "password123"}),
            content_type="application/json",
        )

        response = client.get("/api/portal/navigation")
        assert response.status_code == 200
        payload = response.get_json()
        statuses = payload.get("statuses", {})
        assert statuses.get("/wip-overview") == "released"
        assert statuses.get("/production-history") == "dev"
        assert payload.get("is_admin") is True


class TestSessionPersistence:
    """E2E tests for session persistence."""

    @patch('mes_dashboard.routes.user_auth_routes.is_admin', return_value=True)
    @patch('mes_dashboard.routes.user_auth_routes.authenticate')
    def test_session_persists_across_requests(self, mock_auth, _mock_is_admin, client):
        """Test user session persists across multiple requests."""
        mock_auth.return_value = _mock_admin_user()

        # Login
        client.post(
            "/api/auth/login",
            data=json.dumps({"username": "92367", "password": "password123"}),
            content_type="application/json",
        )

        # Make multiple requests
        for _ in range(5):
            response = client.get("/admin/pages")
            assert response.status_code == 200

        # Session should still be valid
        with client.session_transaction() as sess:
            assert "user" in sess


class TestSecurityScenarios:
    """E2E tests for security scenarios."""

    def test_cannot_access_admin_api_without_login(self, client):
        """Test admin APIs are protected."""
        # Try to get pages without login
        response = client.get("/admin/api/pages", follow_redirects=False)
        assert response.status_code in (302, 401, 403)

        # Try to update page without login
        response = client.put(
            "/admin/api/pages/wip-overview",
            data=json.dumps({"status": "dev"}),
            content_type="application/json",
            follow_redirects=False
        )
        assert response.status_code in (302, 401, 403)

    def test_login_with_wrong_credentials_fails(self, client):
        """Test login with wrong credentials returns error."""
        with patch('mes_dashboard.routes.user_auth_routes.authenticate', return_value=None):
            response = client.post(
                "/api/auth/login",
                data=json.dumps({"username": "99999", "password": "wrong"}),
                content_type="application/json",
            )
        assert response.status_code == 400
        data = response.get_json()
        assert data["success"] is False

        # Should NOT have user session
        with client.session_transaction() as sess:
            assert "user" not in sess

    def test_me_endpoint_returns_null_when_not_logged_in(self, client):
        """Test /api/auth/me returns null data when not authenticated."""
        response = client.get("/api/auth/me")
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["data"] is None

    def test_heartbeat_requires_login(self, client):
        """Test heartbeat endpoint requires authentication."""
        response = client.patch("/api/auth/heartbeat")
        assert response.status_code == 401


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
