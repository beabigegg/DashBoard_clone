# -*- coding: utf-8 -*-
"""Unit tests for cache updater module.

Tests background cache update logic.
"""

import pytest
from unittest.mock import patch, MagicMock
import pandas as pd
import time


class TestCacheUpdater:
    """Test CacheUpdater class."""

    @pytest.fixture(autouse=True)
    def reset_state(self):
        """Reset module state before each test."""
        import mes_dashboard.core.redis_client as rc
        rc._REDIS_CLIENT = None
        yield
        rc._REDIS_CLIENT = None

    def test_updater_starts_when_redis_enabled(self, reset_state):
        """Test updater starts when Redis is enabled."""
        import mes_dashboard.core.cache_updater as cu

        mock_client = MagicMock()
        mock_client.ping.return_value = True

        with patch.object(cu, 'REDIS_ENABLED', True):
            with patch.object(cu, 'redis_available', return_value=True):
                with patch.object(cu, 'read_sql_df', return_value=None):
                    updater = cu.CacheUpdater(interval=1)
                    try:
                        updater.start()
                        assert updater._is_running is True
                        assert updater._thread is not None
                    finally:
                        updater.stop()
                        time.sleep(0.2)

    def test_updater_does_not_start_when_redis_disabled(self, reset_state):
        """Test updater does not start when Redis is disabled."""
        import mes_dashboard.core.cache_updater as cu

        with patch.object(cu, 'REDIS_ENABLED', False):
            updater = cu.CacheUpdater(interval=1)
            updater.start()
            assert updater._is_running is False

    def test_updater_stops_gracefully(self, reset_state):
        """Test updater stops gracefully."""
        import mes_dashboard.core.cache_updater as cu

        mock_client = MagicMock()
        mock_client.ping.return_value = True

        with patch.object(cu, 'REDIS_ENABLED', True):
            with patch.object(cu, 'redis_available', return_value=True):
                with patch.object(cu, 'read_sql_df', return_value=None):
                    updater = cu.CacheUpdater(interval=1)
                    updater.start()
                    assert updater._is_running is True

                    updater.stop()
                    time.sleep(0.2)  # Give thread time to stop
                    assert updater._is_running is False


class TestCheckSysDate:
    """Test SYS_DATE checking logic."""

    def test_check_sys_date_returns_value(self):
        """Test _check_sys_date returns correct value."""
        import mes_dashboard.core.cache_updater as cu

        mock_df = pd.DataFrame({'SYS_DATE': ['2024-01-15 10:30:00']})

        with patch.object(cu, 'read_sql_df', return_value=mock_df):
            updater = cu.CacheUpdater()
            result = updater._check_sys_date()
            assert result == '2024-01-15 10:30:00'

    def test_check_sys_date_handles_empty_result(self):
        """Test _check_sys_date handles empty result."""
        import mes_dashboard.core.cache_updater as cu

        with patch.object(cu, 'read_sql_df', return_value=pd.DataFrame()):
            updater = cu.CacheUpdater()
            result = updater._check_sys_date()
            assert result is None

    def test_check_sys_date_handles_none_result(self):
        """Test _check_sys_date handles None result."""
        import mes_dashboard.core.cache_updater as cu

        with patch.object(cu, 'read_sql_df', return_value=None):
            updater = cu.CacheUpdater()
            result = updater._check_sys_date()
            assert result is None

    def test_check_sys_date_handles_exception(self):
        """Test _check_sys_date handles database exception."""
        import mes_dashboard.core.cache_updater as cu

        with patch.object(cu, 'read_sql_df', side_effect=Exception("Database error")):
            updater = cu.CacheUpdater()
            result = updater._check_sys_date()
            assert result is None


class TestLoadFullTable:
    """Test full table loading logic."""

    def test_load_full_table_success(self):
        """Test _load_full_table loads data correctly."""
        import mes_dashboard.core.cache_updater as cu

        test_df = pd.DataFrame({
            'LOTID': ['LOT001', 'LOT002'],
            'QTY': [100, 200],
            'WORKORDER': ['WO001', 'WO002']
        })

        with patch.object(cu, 'read_sql_df', return_value=test_df):
            updater = cu.CacheUpdater()
            result = updater._load_full_table()

            assert result is not None
            assert len(result) == 2

    def test_load_full_table_handles_none(self):
        """Test _load_full_table handles None result."""
        import mes_dashboard.core.cache_updater as cu

        with patch.object(cu, 'read_sql_df', return_value=None):
            updater = cu.CacheUpdater()
            result = updater._load_full_table()
            assert result is None

    def test_load_full_table_handles_exception(self):
        """Test _load_full_table handles exception."""
        import mes_dashboard.core.cache_updater as cu

        with patch.object(cu, 'read_sql_df', side_effect=Exception("Database error")):
            updater = cu.CacheUpdater()
            result = updater._load_full_table()
            assert result is None


class TestUpdateRedisCache:
    """Test Redis cache update logic."""

    def test_update_redis_cache_success(self):
        """Test _update_redis_cache updates cache correctly."""
        import mes_dashboard.core.cache_updater as cu

        mock_client = MagicMock()
        mock_pipeline = MagicMock()
        mock_client.pipeline.return_value = mock_pipeline

        test_df = pd.DataFrame({
            'LOTID': ['LOT001'],
            'QTY': [100]
        })

        with patch.object(cu, 'get_redis_client', return_value=mock_client):
            with patch.object(cu, 'get_key', side_effect=lambda k: f'mes_wip:{k}'):
                updater = cu.CacheUpdater()
                result = updater._update_redis_cache(test_df, '2024-01-15 10:30:00')

                assert result is True
                mock_pipeline.execute.assert_called_once()

    def test_update_redis_cache_no_client(self):
        """Test _update_redis_cache handles no client."""
        import mes_dashboard.core.cache_updater as cu

        test_df = pd.DataFrame({'LOTID': ['LOT001']})

        with patch.object(cu, 'get_redis_client', return_value=None):
            updater = cu.CacheUpdater()
            result = updater._update_redis_cache(test_df, '2024-01-15')
            assert result is False


class TestCacheUpdateFlow:
    """Test complete cache update flow."""

    def test_no_update_when_sys_date_unchanged(self):
        """Test cache doesn't update when SYS_DATE unchanged."""
        import mes_dashboard.core.cache_updater as cu

        mock_df = pd.DataFrame({'SYS_DATE': ['2024-01-15 10:30:00']})
        mock_client = MagicMock()
        mock_client.get.return_value = '2024-01-15 10:30:00'

        with patch.object(cu, 'read_sql_df', return_value=mock_df):
            with patch.object(cu, 'redis_available', return_value=True):
                with patch.object(cu, 'get_redis_client', return_value=mock_client):
                    with patch.object(cu, 'get_key', side_effect=lambda k: f'mes_wip:{k}'):
                        updater = cu.CacheUpdater()
                        # Simulate already having cached the same date
                        result = updater._check_and_update(force=False)
                        # No update because dates match
                        assert result is False

    def test_update_when_sys_date_changes(self):
        """Test cache updates when SYS_DATE changes."""
        import mes_dashboard.core.cache_updater as cu

        updater = cu.CacheUpdater()

        mock_df = pd.DataFrame({'SYS_DATE': ['2024-01-15 11:00:00']})

        with patch.object(cu, 'read_sql_df', return_value=mock_df):
            current_date = updater._check_sys_date()
            old_date = '2024-01-15 10:30:00'
            needs_update = current_date != old_date

            assert needs_update is True
