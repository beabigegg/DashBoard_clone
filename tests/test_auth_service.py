# -*- coding: utf-8 -*-
"""Unit tests for auth_service module."""

import pytest
from unittest.mock import patch, MagicMock

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from mes_dashboard.services import auth_service


class TestAuthenticate:
    """Tests for authenticate function."""

    @patch('mes_dashboard.services.auth_service.requests.post')
    def test_authenticate_success(self, mock_post):
        """Test successful authentication."""
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

    @patch('mes_dashboard.services.auth_service.requests.post')
    def test_authenticate_invalid_credentials(self, mock_post):
        """Test authentication with invalid credentials."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"success": False}
        mock_post.return_value = mock_response

        result = auth_service.authenticate("wrong", "wrong")

        assert result is None

    @patch('mes_dashboard.services.auth_service.requests.post')
    def test_authenticate_timeout(self, mock_post):
        """Test authentication timeout handling."""
        import requests
        mock_post.side_effect = requests.Timeout()

        result = auth_service.authenticate("user", "pass")

        assert result is None

    @patch('mes_dashboard.services.auth_service.requests.post')
    def test_authenticate_connection_error(self, mock_post):
        """Test authentication connection error handling."""
        import requests
        mock_post.side_effect = requests.ConnectionError()

        result = auth_service.authenticate("user", "pass")

        assert result is None

    @patch('mes_dashboard.services.auth_service.requests.post')
    def test_authenticate_invalid_json(self, mock_post):
        """Test authentication with invalid JSON response."""
        mock_response = MagicMock()
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_post.return_value = mock_response

        result = auth_service.authenticate("user", "pass")

        assert result is None


class TestIsAdmin:
    """Tests for is_admin function."""

    def test_is_admin_with_admin_email(self):
        """Test admin check with admin email."""
        # Save original ADMIN_EMAILS
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
