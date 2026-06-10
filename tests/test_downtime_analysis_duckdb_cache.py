# -*- coding: utf-8 -*-
"""Tests for downtime_analysis_duckdb_cache module.

Covers:
  - should_use_duckdb routing logic (same contract as resource_history_duckdb_cache)
  - query functions return empty DataFrame when cache not ready
  - start_duckdb_prewarm respects DOWNTIME_ANALYSIS_PREWARM_MONTHS=0
  - start_downtime_prewarm in downtime_analysis_cache delegates to DuckDB module
"""
import os
import sys
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


class TestShouldUseDuckdb:
    def test_returns_false_when_not_ready(self):
        from mes_dashboard.services.downtime_analysis_duckdb_cache import should_use_duckdb
        assert should_use_duckdb(date.today().isoformat()) is False

    def test_returns_false_for_today_even_when_ready(self):
        from mes_dashboard.services import downtime_analysis_duckdb_cache as m
        with patch.object(m, "_duckdb_ready", True):
            assert m.should_use_duckdb(date.today().isoformat()) is False

    def test_returns_false_for_future_date(self):
        from mes_dashboard.services import downtime_analysis_duckdb_cache as m
        with patch.object(m, "_duckdb_ready", True):
            future = (date.today() + timedelta(days=1)).isoformat()
            assert m.should_use_duckdb(future) is False

    def test_returns_true_for_yesterday_when_ready(self):
        from mes_dashboard.services import downtime_analysis_duckdb_cache as m
        with patch.object(m, "_duckdb_ready", True):
            yesterday = (date.today() - timedelta(days=1)).isoformat()
            assert m.should_use_duckdb(yesterday) is True

    def test_returns_false_for_date_older_than_window(self):
        from mes_dashboard.services import downtime_analysis_duckdb_cache as m
        with patch.object(m, "_duckdb_ready", True), \
             patch.object(m, "_PREWARM_MONTHS", 3):
            old_date = (date.today() - timedelta(days=3 * 31 + 10)).isoformat()
            assert m.should_use_duckdb(old_date) is False

    def test_returns_false_when_start_date_before_window(self):
        from mes_dashboard.services import downtime_analysis_duckdb_cache as m
        with patch.object(m, "_duckdb_ready", True), \
             patch.object(m, "_PREWARM_MONTHS", 3):
            yesterday = (date.today() - timedelta(days=1)).isoformat()
            start_too_old = (date.today() - timedelta(days=3 * 31 + 5)).isoformat()
            assert m.should_use_duckdb(yesterday, start_date=start_too_old) is False

    def test_returns_true_when_both_dates_inside_window(self):
        from mes_dashboard.services import downtime_analysis_duckdb_cache as m
        with patch.object(m, "_duckdb_ready", True), \
             patch.object(m, "_PREWARM_MONTHS", 3):
            end = (date.today() - timedelta(days=1)).isoformat()
            start = (date.today() - timedelta(days=30)).isoformat()
            assert m.should_use_duckdb(end, start_date=start) is True


class TestQueryFunctionsWhenNotReady:
    def test_query_base_returns_empty_when_not_ready(self):
        from mes_dashboard.services import downtime_analysis_duckdb_cache as m
        with patch.object(m, "_duckdb_ready", False):
            df = m.query_base_from_duckdb("2026-01-01", "2026-03-31")
            assert df.empty

    def test_query_job_returns_empty_when_not_ready(self):
        from mes_dashboard.services import downtime_analysis_duckdb_cache as m
        with patch.object(m, "_duckdb_ready", False):
            df = m.query_job_from_duckdb("2026-01-01", "2026-03-31")
            assert df.empty


class TestStartDuckdbPrewarm:
    def test_disabled_when_prewarm_months_zero(self):
        from mes_dashboard.services import downtime_analysis_duckdb_cache as m
        with patch.object(m, "_PREWARM_MONTHS", 0), \
             patch("threading.Thread") as mock_thread:
            m.start_duckdb_prewarm()
            mock_thread.assert_not_called()

    def test_starts_background_thread_when_enabled(self):
        from mes_dashboard.services import downtime_analysis_duckdb_cache as m
        import threading
        with patch.object(m, "_PREWARM_MONTHS", 3), \
             patch("mes_dashboard.core.redis_client.REDIS_ENABLED", True), \
             patch.object(threading, "Thread") as mock_thread:
            mock_thread.return_value = MagicMock()
            m.start_duckdb_prewarm()
            mock_thread.assert_called_once()

    def test_skipped_when_redis_disabled(self):
        from mes_dashboard.services import downtime_analysis_duckdb_cache as m
        import threading
        with patch.object(m, "_PREWARM_MONTHS", 3), \
             patch("mes_dashboard.core.redis_client.REDIS_ENABLED", False), \
             patch.object(threading, "Thread") as mock_thread:
            m.start_duckdb_prewarm()
            mock_thread.assert_not_called()


class TestStartDowntimePrewarmDelegates:
    def test_delegates_to_duckdb_module(self):
        """start_downtime_prewarm must call start_duckdb_prewarm from DuckDB module."""
        with patch(
            "mes_dashboard.services.downtime_analysis_duckdb_cache.start_duckdb_prewarm"
        ) as mock_ddb_start:
            from mes_dashboard.services.downtime_analysis_cache import start_downtime_prewarm
            start_downtime_prewarm()
            mock_ddb_start.assert_called_once()
