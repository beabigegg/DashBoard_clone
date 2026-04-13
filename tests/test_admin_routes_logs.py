# -*- coding: utf-8 -*-
"""Unit tests for admin routes log API: merged-sort correctness.

Coverage:
  - GET /admin/api/logs merged sort across SQLite + MySQL sources
  - Verifies datetime-based sort produces correct interleaving
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

import pytest

from mes_dashboard.app import create_app


@pytest.fixture
def app():
    app = create_app("testing")
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth_patches():
    with patch("mes_dashboard.app.is_admin_logged_in", return_value=True), \
         patch("mes_dashboard.app.is_user_logged_in", return_value=True), \
         patch("mes_dashboard.core.permissions.is_admin_logged_in", return_value=True), \
         patch("mes_dashboard.core.permissions.is_user_logged_in", return_value=True):
        yield


class TestApiLogsMergedSort:
    """Verify that /admin/api/logs sorts by parsed datetime, not string."""

    def test_same_minute_rows_interleave_by_datetime(self, client, auth_patches):
        """MySQL row at :45 appears before SQLite row at :30 in merged response."""
        sqlite_row = {
            "id": 1,
            "timestamp": "2026-04-13T03:48:30.000000+00:00",
            "level": "INFO",
            "logger_name": "test.sqlite",
            "message": "sqlite log",
            "request_id": None,
            "user": None,
            "ip": None,
            "extra": None,
            "sync_id": "host_logs_1",
            "synced": 0,
        }
        mysql_row = {
            "sync_id": "host_logs_2",
            "timestamp": "2026-04-13T03:48:45.000000+00:00",
            "level": "INFO",
            "logger_name": "test.mysql",
            "message": "mysql log",
            "request_id": None,
            "user": None,
            "ip": None,
            "extra": None,
        }

        mock_store = MagicMock()
        mock_store.query_logs_all.return_value = [sqlite_row]
        mock_store.get_stats.return_value = {"enabled": True, "count": 1}

        with patch(
            "mes_dashboard.core.log_store.LOG_STORE_ENABLED", True
        ), patch(
            "mes_dashboard.core.log_store.get_log_store",
            return_value=mock_store,
        ), patch(
            "mes_dashboard.core.mysql_client.MYSQL_OPS_ENABLED", True
        ), patch(
            "mes_dashboard.routes.admin_routes._query_mysql_logs",
            return_value=[mysql_row],
        ):
            resp = client.get("/admin/api/logs?limit=10")

        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload["success"] is True
        logs = payload["data"]["logs"]
        assert len(logs) == 2
        # MySQL row (03:48:45) should appear first (more recent)
        assert logs[0]["logger_name"] == "test.mysql"
        assert logs[1]["logger_name"] == "test.sqlite"

    def test_unparseable_timestamp_falls_to_bottom(self, client, auth_patches):
        """Row with unparseable timestamp is ordered after all parseable rows."""
        good_row = {
            "id": 1,
            "timestamp": "2026-04-13T03:48:30.000000+00:00",
            "level": "INFO",
            "logger_name": "test.good",
            "message": "good log",
            "request_id": None,
            "user": None,
            "ip": None,
            "extra": None,
            "sync_id": "host_logs_1",
            "synced": 0,
        }
        bad_row = {
            "id": 2,
            "timestamp": "not-a-date",
            "level": "INFO",
            "logger_name": "test.bad",
            "message": "bad ts log",
            "request_id": None,
            "user": None,
            "ip": None,
            "extra": None,
            "sync_id": "host_logs_2",
            "synced": 0,
        }

        mock_store = MagicMock()
        mock_store.query_logs_all.return_value = [good_row, bad_row]
        mock_store.get_stats.return_value = {"enabled": True, "count": 2}

        with patch(
            "mes_dashboard.core.log_store.LOG_STORE_ENABLED", True
        ), patch(
            "mes_dashboard.core.log_store.get_log_store",
            return_value=mock_store,
        ), patch(
            "mes_dashboard.core.mysql_client.MYSQL_OPS_ENABLED", True
        ), patch(
            "mes_dashboard.routes.admin_routes._query_mysql_logs",
            return_value=[],
        ):
            resp = client.get("/admin/api/logs?limit=10")

        assert resp.status_code == 200
        payload = resp.get_json()
        logs = payload["data"]["logs"]
        assert len(logs) == 2
        # Good row (parseable) should appear first
        assert logs[0]["logger_name"] == "test.good"
        assert logs[1]["logger_name"] == "test.bad"
