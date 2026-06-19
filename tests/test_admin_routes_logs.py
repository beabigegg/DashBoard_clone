# -*- coding: utf-8 -*-
"""Unit tests for admin routes log API: merged-sort correctness.

Coverage:
  - GET /admin/api/logs merged sort across SQLite + MySQL sources
  - Verifies datetime-based sort produces correct interleaving
"""

from __future__ import annotations

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


def _make_log_row(ts: str, source: str) -> dict:
    """Return a minimal log row dict for test fixtures."""
    return {
        "id": hash(ts + source),
        "timestamp": ts,
        "level": "INFO",
        "logger_name": f"test.{source}",
        "message": f"{source} message",
        "request_id": None,
        "user": None,
        "ip": None,
        "extra": None,
        "sync_id": f"{source}_{ts}",
        "synced": 0,
    }


class TestApiLogsSqliteIncludesSynced:
    """AC-1: /admin/api/logs (SQLite-only) must return synced rows."""

    def test_api_logs_sqlite_only_includes_synced(self, client, auth_patches):
        """When MySQL is disabled, synced rows must appear in the response."""
        from mes_dashboard.core.log_store import LogStore
        import tempfile
        import os

        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            store = LogStore(db_path=db_path)
            store.initialize()
            store.write_log(level="INFO", logger_name="test.synced", message="synced_row")
            unsynced = store.get_unsynced()
            store.mark_synced([unsynced[0]["id"]])

            with patch(
                "mes_dashboard.core.log_store.LOG_STORE_ENABLED", True
            ), patch(
                "mes_dashboard.core.log_store.get_log_store",
                return_value=store,
            ), patch(
                "mes_dashboard.core.mysql_client.MYSQL_OPS_ENABLED", False
            ):
                resp = client.get("/admin/api/logs?limit=10")

            assert resp.status_code == 200
            payload = resp.get_json()
            assert payload["success"] is True
            logs = payload["data"]["logs"]
            messages = [l["message"] for l in logs]
            assert "synced_row" in messages, (
                "Synced rows must appear in /admin/api/logs when MySQL is disabled"
            )
        finally:
            try:
                os.unlink(db_path)
            except OSError:
                pass


class TestMergePagination:
    """AC-4: data-boundary matrix for merged pagination."""

    def _run_paginated(self, client, auth_patches, sqlite_rows, mysql_rows,
                       sqlite_count, mysql_count, offset, limit):
        """Helper: run GET /admin/api/logs with mocked sources and return payload."""
        mock_store = MagicMock()
        mock_store.query_logs_all.return_value = sqlite_rows
        mock_store.count_logs.return_value = sqlite_count
        mock_store.get_stats.return_value = {"enabled": True, "count": sqlite_count}

        with patch(
            "mes_dashboard.core.log_store.LOG_STORE_ENABLED", True
        ), patch(
            "mes_dashboard.core.log_store.get_log_store",
            return_value=mock_store,
        ), patch(
            "mes_dashboard.core.mysql_client.MYSQL_OPS_ENABLED", True
        ), patch(
            "mes_dashboard.routes.admin_routes._query_mysql_logs",
            return_value=mysql_rows,
        ), patch(
            "mes_dashboard.routes.admin_routes._count_mysql_logs",
            return_value=mysql_count,
        ):
            resp = client.get(
                f"/admin/api/logs?offset={offset}&limit={limit}"
            )
        assert resp.status_code == 200
        return resp.get_json()["data"]

    def _make_rows(self, n: int, prefix: str, start_hour: int = 0) -> list:
        """Generate n log rows with distinct timestamps."""
        rows = []
        for i in range(n):
            ts = f"2026-05-01T{(start_hour + i):02d}:00:00.000000+00:00"
            rows.append(_make_log_row(ts, f"{prefix}_{i}"))
        return rows

    def test_merge_pagination_offset_zero(self, client, auth_patches):
        """Normal page 1: offset=0, limit=5, 5 sqlite + 5 mysql => len=5, total=10."""
        sqlite_rows = self._make_rows(5, "sqlite", start_hour=10)
        mysql_rows = self._make_rows(5, "mysql", start_hour=0)
        data = self._run_paginated(
            client, auth_patches, sqlite_rows, mysql_rows,
            sqlite_count=5, mysql_count=5, offset=0, limit=5,
        )
        assert len(data["logs"]) == 5
        assert data["total"] == 10

    def test_merge_pagination_across_source_boundary(self, client, auth_patches):
        """Across merge boundary: offset=3, limit=5 => len=5, total=10."""
        sqlite_rows = self._make_rows(5, "sqlite", start_hour=10)
        mysql_rows = self._make_rows(5, "mysql", start_hour=0)
        data = self._run_paginated(
            client, auth_patches, sqlite_rows, mysql_rows,
            sqlite_count=5, mysql_count=5, offset=3, limit=5,
        )
        assert len(data["logs"]) == 5
        assert data["total"] == 10

    def test_merge_pagination_offset_exceeds_total(self, client, auth_patches):
        """Offset > total: offset=20, limit=5, total=6 => len=0."""
        sqlite_rows = self._make_rows(3, "sqlite", start_hour=5)
        mysql_rows = self._make_rows(3, "mysql", start_hour=0)
        data = self._run_paginated(
            client, auth_patches, sqlite_rows, mysql_rows,
            sqlite_count=3, mysql_count=3, offset=20, limit=5,
        )
        assert len(data["logs"]) == 0
        assert data["total"] == 6

    def test_merge_pagination_total_is_combined(self, client, auth_patches):
        """Total reflects combined count from both sources."""
        sqlite_rows = self._make_rows(5, "sqlite", start_hour=5)
        mysql_rows = self._make_rows(5, "mysql", start_hour=0)
        data = self._run_paginated(
            client, auth_patches, sqlite_rows, mysql_rows,
            sqlite_count=5, mysql_count=5, offset=10, limit=5,
        )
        assert data["total"] == 10

    def test_merge_pagination_mysql_empty(self, client, auth_patches):
        """MySQL empty, SQLite has rows: offset=0, limit=5 => len=5, total=5."""
        sqlite_rows = self._make_rows(5, "sqlite", start_hour=0)
        data = self._run_paginated(
            client, auth_patches, sqlite_rows, [],
            sqlite_count=5, mysql_count=0, offset=0, limit=5,
        )
        assert len(data["logs"]) == 5
        assert data["total"] == 5

    def test_merge_pagination_sqlite_empty(self, client, auth_patches):
        """SQLite empty, MySQL has rows: offset=0, limit=5 => len=5, total=5."""
        mysql_rows = self._make_rows(5, "mysql", start_hour=0)
        data = self._run_paginated(
            client, auth_patches, [], mysql_rows,
            sqlite_count=0, mysql_count=5, offset=0, limit=5,
        )
        assert len(data["logs"]) == 5
        assert data["total"] == 5

    def test_merge_pagination_both_empty(self, client, auth_patches):
        """Both sources empty: offset=0, limit=5 => len=0, total=0."""
        data = self._run_paginated(
            client, auth_patches, [], [],
            sqlite_count=0, mysql_count=0, offset=0, limit=5,
        )
        assert len(data["logs"]) == 0
        assert data["total"] == 0


class TestApiLogsNoMysql:
    """AC-7: /admin/api/logs returns 200 when MySQL is not configured."""

    def test_api_logs_no_500_mysql_not_configured(self, client, auth_patches):
        """When MySQL is unavailable, endpoint returns 200 with valid envelope."""
        mock_store = MagicMock()
        mock_store.query_logs_all.return_value = []
        mock_store.count_logs.return_value = 0
        mock_store.get_stats.return_value = {"enabled": True, "count": 0}

        with patch(
            "mes_dashboard.core.log_store.LOG_STORE_ENABLED", True
        ), patch(
            "mes_dashboard.core.log_store.get_log_store",
            return_value=mock_store,
        ), patch(
            "mes_dashboard.core.mysql_client.MYSQL_OPS_ENABLED", False
        ):
            resp = client.get("/admin/api/logs?limit=10")

        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload["success"] is True
        assert "logs" in payload["data"]


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
        mock_store.count_logs.return_value = 1
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
        ), patch(
            "mes_dashboard.routes.admin_routes._count_mysql_logs",
            return_value=1,
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
        mock_store.count_logs.return_value = 2
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
        ), patch(
            "mes_dashboard.routes.admin_routes._count_mysql_logs",
            return_value=0,
        ):
            resp = client.get("/admin/api/logs?limit=10")

        assert resp.status_code == 200
        payload = resp.get_json()
        logs = payload["data"]["logs"]
        assert len(logs) == 2
        # Good row (parseable) should appear first
        assert logs[0]["logger_name"] == "test.good"
        assert logs[1]["logger_name"] == "test.bad"
