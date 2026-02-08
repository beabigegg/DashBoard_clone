# -*- coding: utf-8 -*-
"""Unit tests for auth_service module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from mes_dashboard.services import auth_service


@pytest.fixture(autouse=True)
def _ldap_defaults(monkeypatch):
    """Keep LDAP auth tests deterministic regardless of host env vars."""
    monkeypatch.setattr(auth_service, "LDAP_API_BASE", "https://ldap.panjit.example")
    monkeypatch.setattr(auth_service, "LDAP_CONFIG_ERROR", None)


class TestAuthenticate:
    """Tests for authenticate function via LDAP."""

    @patch('mes_dashboard.services.auth_service.LOCAL_AUTH_ENABLED', False)
    @patch('mes_dashboard.services.auth_service.requests.post')
    def test_authenticate_success(self, mock_post):
        """Test successful authentication via LDAP."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "success": True,
            "user": {
                "username": "92367",
                "displayName": "Test User",
                "mail": "test@panjit.com.tw",
                "department": "Test Dept"
            }
        }
        mock_post.return_value = mock_response

        result = auth_service.authenticate("92367", "password123")

        assert result is not None
        assert result["username"] == "92367"
        assert result["mail"] == "test@panjit.com.tw"
        mock_post.assert_called_once()

    @patch('mes_dashboard.services.auth_service.LOCAL_AUTH_ENABLED', False)
    @patch('mes_dashboard.services.auth_service.requests.post')
    def test_authenticate_invalid_credentials(self, mock_post):
        """Test authentication with invalid credentials via LDAP."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"success": False}
        mock_post.return_value = mock_response

        result = auth_service.authenticate("wrong", "wrong")

        assert result is None

    @patch('mes_dashboard.services.auth_service.LOCAL_AUTH_ENABLED', False)
    @patch('mes_dashboard.services.auth_service.requests.post')
    def test_authenticate_timeout(self, mock_post):
        """Test authentication timeout handling."""
        import requests
        mock_post.side_effect = requests.Timeout()

        result = auth_service.authenticate("user", "pass")

        assert result is None

    @patch('mes_dashboard.services.auth_service.LOCAL_AUTH_ENABLED', False)
    @patch('mes_dashboard.services.auth_service.requests.post')
    def test_authenticate_connection_error(self, mock_post):
        """Test authentication connection error handling."""
        import requests
        mock_post.side_effect = requests.ConnectionError()

        result = auth_service.authenticate("user", "pass")

        assert result is None

    @patch('mes_dashboard.services.auth_service.LOCAL_AUTH_ENABLED', False)
    @patch('mes_dashboard.services.auth_service.requests.post')
    def test_authenticate_invalid_json(self, mock_post):
        """Test authentication with invalid JSON response."""
        mock_response = MagicMock()
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_post.return_value = mock_response

        result = auth_service.authenticate("user", "pass")

        assert result is None

    @patch('mes_dashboard.services.auth_service.LOCAL_AUTH_ENABLED', False)
    @patch('mes_dashboard.services.auth_service.requests.post')
    def test_authenticate_rejects_invalid_ldap_config_without_outbound_call(self, mock_post):
        """Unsafe LDAP config should block auth and skip outbound request."""
        with patch.object(auth_service, "LDAP_CONFIG_ERROR", "invalid LDAP API URL"):
            result = auth_service.authenticate("user", "pass")

        assert result is None
        mock_post.assert_not_called()


class TestLdapConfigValidation:
    """Validate LDAP base URL hardening rules."""

    def test_accepts_https_allowlisted_host(self):
        api_base, error = auth_service._validate_ldap_api_url(
            "https://ldap.panjit.example",
            ("ldap.panjit.example",),
        )

        assert error is None
        assert api_base == "https://ldap.panjit.example"

    def test_rejects_non_https_url(self):
        api_base, error = auth_service._validate_ldap_api_url(
            "http://ldap.panjit.example",
            ("ldap.panjit.example",),
        )

        assert api_base is None
        assert error is not None
        assert "HTTPS" in error

    def test_rejects_non_allowlisted_host(self):
        api_base, error = auth_service._validate_ldap_api_url(
            "https://evil.example",
            ("ldap.panjit.example",),
        )

        assert api_base is None
        assert error is not None
        assert "allowlisted" in error


class TestLocalAuthenticate:
    """Tests for local authentication."""

    @patch('mes_dashboard.services.auth_service.LOCAL_AUTH_ENABLED', True)
    @patch('mes_dashboard.services.auth_service.LOCAL_AUTH_USERNAME', 'testuser')
    @patch('mes_dashboard.services.auth_service.LOCAL_AUTH_PASSWORD', 'testpass')
    def test_local_auth_success(self):
        """Test successful local authentication."""
        result = auth_service.authenticate("testuser", "testpass")

        assert result is not None
        assert result["username"] == "testuser"

    @patch('mes_dashboard.services.auth_service.LOCAL_AUTH_ENABLED', True)
    @patch('mes_dashboard.services.auth_service.LOCAL_AUTH_USERNAME', 'testuser')
    @patch('mes_dashboard.services.auth_service.LOCAL_AUTH_PASSWORD', 'testpass')
    def test_local_auth_wrong_password(self):
        """Test local authentication with wrong password."""
        result = auth_service.authenticate("testuser", "wrongpass")

        assert result is None


class TestLocalAuthSafetyGuard:
    """Tests for production guard on local auth toggle."""

    def test_resolve_local_auth_enabled_blocks_production(self):
        result = auth_service._resolve_local_auth_enabled(
            raw_value="true",
            flask_env="production",
        )
        assert result is False

    def test_resolve_local_auth_enabled_allows_development(self):
        result = auth_service._resolve_local_auth_enabled(
            raw_value="true",
            flask_env="development",
        )
        assert result is True


class TestIsAdmin:
    """Tests for is_admin function."""

    def test_is_admin_with_admin_email(self):
        """Test admin check with admin email."""
        original = auth_service.ADMIN_EMAILS

        try:
            auth_service.ADMIN_EMAILS = ["admin@panjit.com.tw"]
            user = {"mail": "admin@panjit.com.tw"}
            assert auth_service.is_admin(user) is True
        finally:
            auth_service.ADMIN_EMAILS = original

    def test_is_admin_with_non_admin_email(self):
        """Test admin check with non-admin email."""
        original = auth_service.ADMIN_EMAILS

        try:
            auth_service.ADMIN_EMAILS = ["admin@panjit.com.tw"]
            user = {"mail": "user@panjit.com.tw"}
            assert auth_service.is_admin(user) is False
        finally:
            auth_service.ADMIN_EMAILS = original

    def test_is_admin_case_insensitive(self):
        """Test admin check is case insensitive."""
        original = auth_service.ADMIN_EMAILS

        try:
            auth_service.ADMIN_EMAILS = ["admin@panjit.com.tw"]
            user = {"mail": "ADMIN@PANJIT.COM.TW"}
            assert auth_service.is_admin(user) is True
        finally:
            auth_service.ADMIN_EMAILS = original

    def test_is_admin_with_missing_mail(self):
        """Test admin check with missing mail field."""
        user = {}
        assert auth_service.is_admin(user) is False

    def test_is_admin_with_empty_mail(self):
        """Test admin check with empty mail field."""
        user = {"mail": ""}
        assert auth_service.is_admin(user) is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
