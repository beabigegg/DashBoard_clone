# -*- coding: utf-8 -*-
"""Unit tests for user_usage_kpi_service.py — KPI aggregation logic."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from unittest.mock import patch, MagicMock


class TestDurationBuckets:
    """Tests for the duration bucketing constants."""

    def test_duration_buckets_imported(self):
        from mes_dashboard.services.user_usage_kpi_service import _DURATION_BUCKETS
        assert isinstance(_DURATION_BUCKETS, list)
        assert len(_DURATION_BUCKETS) > 0

    def test_duration_buckets_have_three_fields(self):
        from mes_dashboard.services.user_usage_kpi_service import _DURATION_BUCKETS
        for label, lo, hi in _DURATION_BUCKETS:
            assert isinstance(label, str)
            assert isinstance(lo, int)
            assert hi is None or isinstance(hi, int)

    def test_duration_buckets_start_at_zero(self):
        from mes_dashboard.services.user_usage_kpi_service import _DURATION_BUCKETS
        first = _DURATION_BUCKETS[0]
        assert first[1] == 0

    def test_duration_buckets_last_has_no_upper_bound(self):
        from mes_dashboard.services.user_usage_kpi_service import _DURATION_BUCKETS
        last = _DURATION_BUCKETS[-1]
        assert last[2] is None

    def test_duration_buckets_boundaries_are_contiguous(self):
        from mes_dashboard.services.user_usage_kpi_service import _DURATION_BUCKETS
        for i in range(len(_DURATION_BUCKETS) - 1):
            _label, _lo, hi = _DURATION_BUCKETS[i]
            _next_label, next_lo, _next_hi = _DURATION_BUCKETS[i + 1]
            assert hi == next_lo


class TestGetSqliteActiveSessionIds:
    """Tests for _get_sqlite_active_session_ids."""

    def test_returns_empty_set_on_store_error(self):
        from mes_dashboard.services.user_usage_kpi_service import _get_sqlite_active_session_ids
        with patch(
            "mes_dashboard.core.login_session_store.get_login_session_store",
            side_effect=Exception("store unavailable"),
        ):
            result = _get_sqlite_active_session_ids()
        assert isinstance(result, set)
        assert len(result) == 0

    def test_returns_set_of_session_ids(self):
        from mes_dashboard.services.user_usage_kpi_service import _get_sqlite_active_session_ids
        mock_store = MagicMock()
        mock_store._initialized = True
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [("sess-1",), ("sess-2",)]
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_store._get_connection.return_value.__enter__ = lambda s: mock_conn
        mock_store._get_connection.return_value.__exit__ = MagicMock(return_value=False)

        with patch(
            "mes_dashboard.core.login_session_store.get_login_session_store",
            return_value=mock_store,
        ):
            result = _get_sqlite_active_session_ids()
        assert result == {"sess-1", "sess-2"}


class TestGetUserUsageKpiRoutingLogic:
    """Tests for get_user_usage_kpi routing (MySQL vs SQLite fallback)."""

    def test_falls_back_to_sqlite_when_mysql_disabled(self):
        from mes_dashboard.services.user_usage_kpi_service import get_user_usage_kpi
        mock_result = {"overview": {}, "source": "sqlite"}
        with patch(
            "mes_dashboard.core.mysql_client.MYSQL_OPS_ENABLED",
            False,
        ), patch(
            "mes_dashboard.services.user_usage_kpi_service._query_sqlite",
            return_value=mock_result,
        ) as mock_sqlite:
            result = get_user_usage_kpi("2026-03-01", "2026-03-31")
        mock_sqlite.assert_called_once()
        assert result["source"] == "sqlite"

    def test_mysql_failure_falls_back_to_sqlite(self):
        from mes_dashboard.services.user_usage_kpi_service import get_user_usage_kpi
        mock_result = {"overview": {}, "source": "sqlite_fallback"}
        with patch(
            "mes_dashboard.core.mysql_client.MYSQL_OPS_ENABLED",
            True,
        ), patch(
            "mes_dashboard.services.user_usage_kpi_service._query_mysql",
            side_effect=Exception("MySQL connection failed"),
        ), patch(
            "mes_dashboard.services.user_usage_kpi_service._query_sqlite",
            return_value=mock_result,
        ) as mock_sqlite:
            result = get_user_usage_kpi("2026-03-01", "2026-03-31")
        mock_sqlite.assert_called_once()
        assert result == mock_result

    def test_uses_mysql_when_enabled(self):
        from mes_dashboard.services.user_usage_kpi_service import get_user_usage_kpi
        mock_result = {"overview": {}, "source": "mysql"}
        with patch(
            "mes_dashboard.core.mysql_client.MYSQL_OPS_ENABLED",
            True,
        ), patch(
            "mes_dashboard.services.user_usage_kpi_service._query_mysql",
            return_value=mock_result,
        ) as mock_mysql:
            result = get_user_usage_kpi("2026-03-01", "2026-03-31")
        mock_mysql.assert_called_once()
        assert result["source"] == "mysql"

    def test_end_date_exclusion_adds_one_day(self):
        """end_date is inclusive; service computes end_date + 1 day for SQL."""
        from mes_dashboard.services.user_usage_kpi_service import get_user_usage_kpi
        captured = {}
        def fake_sqlite(start_date, end_date_exclusive, department):
            captured["end"] = end_date_exclusive
            return {"overview": {}}
        with patch(
            "mes_dashboard.core.mysql_client.MYSQL_OPS_ENABLED",
            False,
        ), patch(
            "mes_dashboard.services.user_usage_kpi_service._query_sqlite",
            side_effect=fake_sqlite,
        ):
            get_user_usage_kpi("2026-03-01", "2026-03-31")
        assert captured["end"] == "2026-04-01"


class TestRecentSessionsFilters:
    """Recent session rows should respect the same date/department filters as KPI cards."""

    def test_sqlite_recent_sessions_uses_period_and_department_filters(self):
        from mes_dashboard.services.user_usage_kpi_service import _query_sqlite

        executed = []

        class Cursor:
            def execute(self, sql, params=()):
                executed.append((sql, tuple(params)))

            def fetchone(self):
                return (0, 0, None)

            def fetchall(self):
                return []

        class Conn:
            def cursor(self):
                return Cursor()

        class Store:
            _initialized = True
            def _get_connection(self):
                class CM:
                    def __enter__(self):
                        return Conn()
                    def __exit__(self, *_args):
                        return False
                return CM()
            def get_online_count(self):
                return 0
            def get_active_count(self):
                return 0

        with patch(
            "mes_dashboard.core.login_session_store.get_login_session_store",
            return_value=Store(),
        ):
            _query_sqlite("2026-03-01", "2026-04-01", "QA")

        recent_sql, recent_params = executed[-2]
        assert "WHERE login_time >= ? AND login_time < ?" in recent_sql
        assert "AND department = ?" in recent_sql
        assert recent_params == ("2026-03-01", "2026-04-01", "QA")
