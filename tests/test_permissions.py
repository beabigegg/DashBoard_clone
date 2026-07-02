# -*- coding: utf-8 -*-
"""Unit tests for permissions module."""

import pytest
from flask import Flask

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from mes_dashboard.core.permissions import (
    is_admin_logged_in,
    is_user_logged_in,
    get_current_user,
    admin_required,
    login_required,
    can_edit_targets,
    targets_edit_required,
)


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
        """Test when admin user is logged in."""
        with app.test_request_context():
            from flask import session
            session["user"] = {"username": "admin", "mail": "admin@test.com", "is_admin": True}
            assert is_admin_logged_in() is True

    def test_non_admin_user_not_admin(self, app):
        """Test when regular user is logged in but not admin."""
        with app.test_request_context():
            from flask import session
            session["user"] = {"username": "user", "mail": "user@test.com", "is_admin": False}
            assert is_admin_logged_in() is False

    def test_admin_not_logged_in(self, app):
        """Test when no user is logged in."""
        with app.test_request_context():
            assert is_admin_logged_in() is False


class TestIsUserLoggedIn:
    """Tests for is_user_logged_in function."""

    def test_user_logged_in(self, app):
        """Test when a user is logged in."""
        with app.test_request_context():
            from flask import session
            session["user"] = {"username": "user", "is_admin": False}
            assert is_user_logged_in() is True

    def test_user_not_logged_in(self, app):
        """Test when no user is logged in."""
        with app.test_request_context():
            assert is_user_logged_in() is False


class TestGetCurrentUser:
    """Tests for get_current_user function."""

    def test_get_user_when_logged_in(self, app):
        """Test getting user info when logged in."""
        with app.test_request_context():
            from flask import session
            user_data = {"username": "user", "mail": "user@test.com", "is_admin": False}
            session["user"] = user_data
            result = get_current_user()
            assert result == user_data

    def test_get_user_when_not_logged_in(self, app):
        """Test getting user info when not logged in."""
        with app.test_request_context():
            result = get_current_user()
            assert result is None


class TestAdminRequired:
    """Tests for admin_required decorator."""

    def test_admin_required_when_admin_logged_in(self, app):
        """Test decorator allows access when admin is logged in."""
        @app.route("/test-admin")
        @admin_required
        def test_route():
            return "success"

        with app.test_client() as client:
            with client.session_transaction() as sess:
                sess["user"] = {"username": "admin", "is_admin": True}

            response = client.get("/test-admin")
            assert response.status_code == 200
            assert response.data == b"success"

    def test_admin_required_when_not_logged_in(self, app):
        """Test decorator returns 401 when not logged in."""
        @app.route("/test-admin-noauth")
        @admin_required
        def test_route():
            return "success"

        with app.test_client() as client:
            response = client.get("/test-admin-noauth")
            assert response.status_code == 401

    def test_admin_required_when_regular_user(self, app):
        """Test decorator returns 403 when logged in as non-admin."""
        @app.route("/test-admin-forbidden")
        @admin_required
        def test_route():
            return "success"

        with app.test_client() as client:
            with client.session_transaction() as sess:
                sess["user"] = {"username": "user", "is_admin": False}

            response = client.get("/test-admin-forbidden")
            assert response.status_code == 403


class TestLoginRequired:
    """Tests for login_required decorator."""

    def test_login_required_when_logged_in(self, app):
        """Test decorator allows access when any user is logged in."""
        @app.route("/test-login")
        @login_required
        def test_route():
            return "success"

        with app.test_client() as client:
            with client.session_transaction() as sess:
                sess["user"] = {"username": "user", "is_admin": False}

            response = client.get("/test-login")
            assert response.status_code == 200

    def test_login_required_when_not_logged_in(self, app):
        """Test decorator returns 401 when not logged in."""
        @app.route("/test-login-noauth")
        @login_required
        def test_route():
            return "success"

        with app.test_client() as client:
            response = client.get("/test-login-noauth")
            assert response.status_code == 401


class TestCanEditTargetsIndependentGate:
    """New independent single-flag gate (production-achievement-kanban).

    Additive to this module -- see tests/test_production_achievement_permissions.py
    for the full allow/deny/fail-closed unit-test surface. These cases only
    confirm the gate is distinct from is_admin_logged_in/admin_required.
    """

    def test_can_edit_targets_denied_for_non_admin_non_whitelisted(self, app):
        from unittest.mock import patch
        with app.test_request_context():
            from flask import session
            session["user"] = {"username": "user", "is_admin": False}
            with patch(
                "mes_dashboard.services.production_achievement_permission_service.is_user_whitelisted",
                return_value=False,
            ):
                assert can_edit_targets() is False

    def test_targets_edit_required_returns_403_when_denied(self, app):
        from unittest.mock import patch

        @app.route("/test-targets-edit")
        @targets_edit_required
        def test_route():
            return "success"

        with patch(
            "mes_dashboard.core.permissions.can_edit_targets", return_value=False
        ):
            with app.test_client() as client:
                with client.session_transaction() as sess:
                    sess["user"] = {"username": "user", "is_admin": False}
                response = client.get("/test-targets-edit")
                assert response.status_code == 403

    def test_targets_edit_required_distinct_from_admin_required(self, app):
        """An admin user without a whitelist row is still denied -- the two
        gates are independent (design.md Key Decisions)."""
        from unittest.mock import patch

        @app.route("/test-targets-edit-admin")
        @targets_edit_required
        def test_route():
            return "success"

        with patch(
            "mes_dashboard.core.permissions.can_edit_targets", return_value=False
        ):
            with app.test_client() as client:
                with client.session_transaction() as sess:
                    sess["user"] = {"username": "admin", "is_admin": True}
                response = client.get("/test-targets-edit-admin")
                assert response.status_code == 403


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
