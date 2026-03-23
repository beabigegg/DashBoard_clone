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
                mock_pipeline.rename.assert_called_once()
                mock_pipeline.execute.assert_called_once()
                assert mock_pipeline.set.call_count == 3
                for call in mock_pipeline.set.call_args_list:
                    assert call.kwargs.get("ex") == updater.interval * 3

    def test_update_redis_cache_no_client(self):
        """Test _update_redis_cache handles no client."""
        import mes_dashboard.core.cache_updater as cu

        test_df = pd.DataFrame({'LOTID': ['LOT001']})

        with patch.object(cu, 'get_redis_client', return_value=None):
            updater = cu.CacheUpdater()
            result = updater._update_redis_cache(test_df, '2024-01-15')
            assert result is False

    def test_update_redis_cache_cleans_staging_key_on_failure(self):
        """Failed publish should clean staged key and keep function safe."""
        import mes_dashboard.core.cache_updater as cu

        mock_client = MagicMock()
        mock_pipeline = MagicMock()
        mock_pipeline.execute.side_effect = RuntimeError("pipeline failed")
        mock_client.pipeline.return_value = mock_pipeline

        test_df = pd.DataFrame({'LOTID': ['LOT001'], 'QTY': [100]})

        with patch.object(cu, 'get_redis_client', return_value=mock_client):
            with patch.object(cu, 'get_key', side_effect=lambda k: f'mes_wip:{k}'):
                updater = cu.CacheUpdater()
                result = updater._update_redis_cache(test_df, '2024-01-15 10:30:00')

        assert result is False
        mock_client.delete.assert_called_once()
        staged_key = mock_client.delete.call_args.args[0]
        assert "staging" in staged_key

    def test_update_redis_cache_ttl_override(self):
        """Configured TTL override should apply to all Redis keys."""
        import mes_dashboard.core.cache_updater as cu

        mock_client = MagicMock()
        mock_pipeline = MagicMock()
        mock_client.pipeline.return_value = mock_pipeline
        test_df = pd.DataFrame({'LOTID': ['LOT001'], 'QTY': [100]})

        with patch.object(cu, 'WIP_CACHE_TTL_SECONDS', 42):
            with patch.object(cu, 'get_redis_client', return_value=mock_client):
                with patch.object(cu, 'get_key', side_effect=lambda k: f'mes_wip:{k}'):
                    updater = cu.CacheUpdater(interval=600)
                    result = updater._update_redis_cache(test_df, '2024-01-15 10:30:00')

        assert result is True
        assert mock_pipeline.set.call_count == 3
        for call in mock_pipeline.set.call_args_list:
            assert call.kwargs.get("ex") == 42


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


class TestWarmupTasks:
    """Test dataset warmup hooks in CacheUpdater."""

    def test_run_dataset_warmups_calls_all_tasks(self):
        import mes_dashboard.core.cache_updater as cu

        updater = cu.CacheUpdater(interval=1)
        with patch.object(updater, '_warmup_reject_dataset') as mock_reject, \
             patch.object(updater, '_warmup_yield_alert_dataset') as mock_yield, \
             patch.object(updater, '_warmup_reject_options') as mock_options:
            updater._run_dataset_warmups()

        mock_reject.assert_called_once()
        mock_yield.assert_called_once()
        mock_options.assert_called_once()

    def test_warmup_failure_does_not_block_other_tasks(self):
        import mes_dashboard.core.cache_updater as cu

        updater = cu.CacheUpdater(interval=1)
        with patch.object(updater, '_warmup_reject_dataset', side_effect=RuntimeError('reject failed')), \
             patch.object(updater, '_warmup_yield_alert_dataset') as mock_yield, \
             patch.object(updater, '_warmup_reject_options') as mock_options:
            updater._run_dataset_warmups()

        mock_yield.assert_called_once()
        mock_options.assert_called_once()

    @patch('mes_dashboard.services.reject_dataset_cache.ensure_dataset_loaded', return_value={'query_id': 'qid-r', 'cache_hit': True})
    def test_warmup_reject_dataset_delegates(self, mock_ensure):
        import mes_dashboard.core.cache_updater as cu

        updater = cu.CacheUpdater(interval=1)
        updater._warmup_reject_dataset()
        mock_ensure.assert_called_once()

    @patch('mes_dashboard.services.yield_alert_dataset_cache.ensure_dataset_loaded', return_value={'query_id': 'qid-y', 'cache_hit': False})
    def test_warmup_yield_alert_dataset_delegates(self, mock_ensure):
        import mes_dashboard.core.cache_updater as cu

        updater = cu.CacheUpdater(interval=1)
        updater._warmup_yield_alert_dataset()
        mock_ensure.assert_called_once()
