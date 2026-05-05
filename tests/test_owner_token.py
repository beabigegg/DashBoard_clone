# -*- coding: utf-8 -*-
"""Unit tests for get_owner_token() in core/permissions.py."""

from __future__ import annotations

import pytest

from mes_dashboard.app import create_app
from mes_dashboard.core.permissions import get_owner_token


@pytest.fixture
def app():
    app = create_app("testing")
    app.config["TESTING"] = True
    return app


class TestGetOwnerToken:
    def test_logged_in_returns_username(self, app):
        """Logged-in user: returns session["user"]["username"]."""
        with app.test_request_context():
            from flask import session
            session["user"] = {"username": "alice", "is_admin": False}
            token = get_owner_token()
        assert token == "alice"

    def test_anonymous_lazy_mints_token(self, app):
        """Anonymous user: lazily mints a uuid4 hex token."""
        with app.test_request_context():
            from flask import session
            assert "user" not in session
            token = get_owner_token()
            assert token  # non-empty
            assert len(token) == 32  # uuid4().hex is 32 hex chars
            assert token == session["mes_owner_token"]

    def test_anonymous_re_read_returns_same_value(self, app):
        """Anonymous user: second call returns same token as first."""
        with app.test_request_context():
            first = get_owner_token()
            second = get_owner_token()
        assert first == second

    def test_token_is_hex_shaped(self, app):
        """Minted token should be a 32-character lowercase hex string."""
        with app.test_request_context():
            token = get_owner_token()
        assert len(token) == 32
        assert all(c in "0123456789abcdef" for c in token)

    def test_logged_in_does_not_mint_anonymous_token(self, app):
        """Logged-in path must not write mes_owner_token into session."""
        with app.test_request_context():
            from flask import session
            session["user"] = {"username": "bob", "is_admin": True}
            get_owner_token()
            assert "mes_owner_token" not in session
