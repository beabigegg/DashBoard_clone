# -*- coding: utf-8 -*-
"""Unit tests for query_timeout_error() helper in mes_dashboard.core.response."""

import pytest

from mes_dashboard.core.response import query_timeout_error, QUERY_TIMEOUT


class TestQueryTimeoutError:
    """query_timeout_error() must return an envelope with 504 status."""

    def test_status_code_is_504(self, app):
        with app.app_context():
            resp, status = query_timeout_error("查詢逾時，請縮小範圍")
        assert status == 504

    def test_envelope_success_is_false(self, app):
        with app.app_context():
            resp, status = query_timeout_error("msg")
        data = resp.get_json()
        assert data["success"] is False

    def test_envelope_error_code(self, app):
        with app.app_context():
            resp, status = query_timeout_error("msg")
        data = resp.get_json()
        assert data["error"]["code"] == QUERY_TIMEOUT

    def test_envelope_message(self, app):
        with app.app_context():
            resp, status = query_timeout_error("查詢逾時，請縮小範圍")
        data = resp.get_json()
        assert data["error"]["message"] == "查詢逾時，請縮小範圍"

    def test_meta_present(self, app):
        with app.app_context():
            resp, status = query_timeout_error("msg")
        data = resp.get_json()
        assert "meta" in data
        assert "timestamp" in data["meta"]
