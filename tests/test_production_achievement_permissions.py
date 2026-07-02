# -*- coding: utf-8 -*-
"""Unit tests for the can_edit_targets permission primitive (IP-1/IP-2).

data-shape §3.27 / design.md: fail-closed semantics -- deny when no
whitelist row exists, MYSQL_OPS_ENABLED=false, or any MySQL exception is
raised. Independent of the existing admin_required/is_admin_logged_in gate.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from flask import Flask, session

from mes_dashboard.core.permissions import can_edit_targets, is_admin_logged_in


@pytest.fixture
def app():
    app = Flask(__name__)
    app.secret_key = "test-secret-key"
    app.config["TESTING"] = True
    return app


class TestCanEditTargets:
    @patch(
        "mes_dashboard.services.production_achievement_permission_service.is_user_whitelisted",
        return_value=True,
    )
    def test_whitelisted_user_allowed(self, mock_lookup, app):
        with app.test_request_context():
            session["user"] = {"username": "alice", "is_admin": False}
            assert can_edit_targets() is True
        mock_lookup.assert_called_once_with("alice")

    @patch(
        "mes_dashboard.services.production_achievement_permission_service.is_user_whitelisted",
        return_value=False,
    )
    def test_non_whitelisted_user_denied(self, mock_lookup, app):
        with app.test_request_context():
            session["user"] = {"username": "bob", "is_admin": False}
            assert can_edit_targets() is False

    @patch(
        "mes_dashboard.services.production_achievement_permission_service.is_user_whitelisted",
        side_effect=RuntimeError("MySQL unreachable"),
    )
    def test_mysql_unreachable_fails_closed_deny(self, mock_lookup, app):
        with app.test_request_context():
            session["user"] = {"username": "alice", "is_admin": False}
            assert can_edit_targets() is False

    @patch(
        "mes_dashboard.services.production_achievement_permission_service.is_user_whitelisted",
        return_value=False,
    )
    def test_ops_disabled_fails_closed_deny(self, mock_lookup, app):
        """is_user_whitelisted itself returns False when MYSQL_OPS_ENABLED=false
        (service-layer responsibility) -- can_edit_targets must still deny."""
        with app.test_request_context():
            session["user"] = {"username": "alice", "is_admin": False}
            assert can_edit_targets() is False

    @patch(
        "mes_dashboard.services.production_achievement_permission_service.is_user_whitelisted",
        return_value=True,
    )
    def test_explicit_identifier_bypasses_session(self, mock_lookup, app):
        with app.test_request_context():
            assert can_edit_targets(user_identifier="carol") is True
        mock_lookup.assert_called_once_with("carol")

    @patch(
        "mes_dashboard.services.production_achievement_permission_service.is_user_whitelisted",
        return_value=True,
    )
    def test_distinct_from_admin_required(self, mock_lookup, app):
        """can_edit_targets whitelisting is independent of is_admin_logged_in."""
        with app.test_request_context():
            session["user"] = {"username": "alice", "is_admin": False}
            assert can_edit_targets() is True
            assert is_admin_logged_in() is False
