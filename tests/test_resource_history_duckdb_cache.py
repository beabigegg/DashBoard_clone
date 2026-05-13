# -*- coding: utf-8 -*-
"""Tests for resource_history_duckdb_cache module (resource-history-perf).

Tests cover:
  - should_use_duckdb routing logic
  - query functions return empty DataFrame when cache not ready
  - start_duckdb_prewarm respects RESOURCE_HISTORY_PREWARM_MONTHS=0
"""
import os
import sys
from datetime import date, timedelta
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


class TestShouldUseDuckdb:
    def test_returns_false_when_not_ready(self):
        from mes_dashboard.services.resource_history_duckdb_cache import should_use_duckdb
        assert should_use_duckdb(date.today().isoformat()) is False

    def test_returns_false_for_today_even_when_ready(self):
        from mes_dashboard.services import resource_history_duckdb_cache as m
        with patch.object(m, "_duckdb_ready", True):
            assert m.should_use_duckdb(date.today().isoformat()) is False

    def test_returns_false_for_future_date(self):
        from mes_dashboard.services import resource_history_duckdb_cache as m
        with patch.object(m, "_duckdb_ready", True):
            future = (date.today() + timedelta(days=1)).isoformat()
            assert m.should_use_duckdb(future) is False

    def test_returns_true_for_yesterday_when_ready(self):
        from mes_dashboard.services import resource_history_duckdb_cache as m
        with patch.object(m, "_duckdb_ready", True):
            yesterday = (date.today() - timedelta(days=1)).isoformat()
            assert m.should_use_duckdb(yesterday) is True

    def test_returns_false_for_date_older_than_window(self):
        from mes_dashboard.services import resource_history_duckdb_cache as m
        with patch.object(m, "_duckdb_ready", True), \
             patch.object(m, "_PREWARM_MONTHS", 3):
            old_date = (date.today() - timedelta(days=3 * 31 + 10)).isoformat()
            assert m.should_use_duckdb(old_date) is False


class TestQueryFunctionsWhenNotReady:
    def test_query_base_returns_empty_when_not_ready(self):
        from mes_dashboard.services.resource_history_duckdb_cache import query_base_from_duckdb
        df = query_base_from_duckdb(["RES001"], "2026-01-01", "2026-03-31")
        assert df.empty

    def test_query_oee_returns_empty_when_not_ready(self):
        from mes_dashboard.services.resource_history_duckdb_cache import query_oee_from_duckdb
        df = query_oee_from_duckdb("2026-01-01", "2026-03-31")
        assert df.empty

    def test_query_base_returns_empty_for_empty_hist_ids(self):
        from mes_dashboard.services import resource_history_duckdb_cache as m
        with patch.object(m, "_duckdb_ready", True):
            df = m.query_base_from_duckdb([], "2026-01-01", "2026-03-31")
            assert df.empty


class TestStartDuckdbPrewarm:
    def test_disabled_when_prewarm_months_zero(self):
        from mes_dashboard.services import resource_history_duckdb_cache as m
        with patch.object(m, "_PREWARM_MONTHS", 0), \
             patch("threading.Thread") as mock_thread:
            m.start_duckdb_prewarm()
            mock_thread.assert_not_called()

    def test_starts_background_thread_when_enabled(self):
        from mes_dashboard.services import resource_history_duckdb_cache as m
        import threading
        with patch.object(m, "_PREWARM_MONTHS", 3), \
             patch("mes_dashboard.core.redis_client.REDIS_ENABLED", True), \
             patch.object(threading, "Thread") as mock_thread:
            mock_thread.return_value = MagicMock()
            m.start_duckdb_prewarm()
            mock_thread.assert_called_once()
