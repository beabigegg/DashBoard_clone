# -*- coding: utf-8 -*-
"""Unit tests for permissions module."""

import pytest
from flask import Flask

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from mes_dashboard.core.permissions import is_admin_logged_in, get_current_admin, admin_required


@pytest.fixture
def app():
    """Create a test Flask app."""
    app = Flask(__name__)
    app.secret_key = "test-secret-key"
    app.config["TESTING"] = True
    return app


class TestIsAdminLoggedIn:
    """Tests for is_admin_logged_in function."""

    def test_admin_logged_in(self, app):
        """Test when admin is logged in."""
        with app.test_request_context():
            from flask import session
            session["admin"] = {"username": "admin", "mail": "admin@test.com"}
            assert is_admin_logged_in() is True

    def test_admin_not_logged_in(self, app):
        """Test when admin is not logged in."""
        with app.test_request_context():
            assert is_admin_logged_in() is False


class TestGetCurrentAdmin:
    """Tests for get_current_admin function."""

    def test_get_admin_when_logged_in(self, app):
        """Test getting admin info when logged in."""
        with app.test_request_context():
            from flask import session
            admin_data = {"username": "admin", "mail": "admin@test.com"}
            session["admin"] = admin_data
            result = get_current_admin()
            assert result == admin_data

    def test_get_admin_when_not_logged_in(self, app):
        """Test getting admin info when not logged in."""
        with app.test_request_context():
            result = get_current_admin()
            assert result is None


class TestAdminRequired:
    """Tests for admin_required decorator."""

    def test_admin_required_when_logged_in(self, app):
        """Test decorator allows access when admin is logged in."""
        @app.route("/test")
        @admin_required
        def test_route():
            return "success"

        with app.test_client() as client:
            with client.session_transaction() as sess:
                sess["admin"] = {"username": "admin"}

            response = client.get("/test")
            assert response.status_code == 200
            assert response.data == b"success"

    def test_admin_required_when_not_logged_in(self, app):
        """Test decorator redirects when admin is not logged in."""
        from flask import Blueprint

        # Register auth blueprint first with correct endpoint name
        auth_bp = Blueprint("auth", __name__, url_prefix="/admin")

        @auth_bp.route("/login", endpoint="login")
        def login_view():
            return "login"

        app.register_blueprint(auth_bp)

        # Now add the protected route
        @app.route("/test")
        @admin_required
        def test_route():
            return "success"

        with app.test_client() as client:
            response = client.get("/test")
            assert response.status_code == 302
            assert "/admin/login" in response.location


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
