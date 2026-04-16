# -*- coding: utf-8 -*-
"""Unit tests for cache updater module.

Tests background cache update logic.
"""

import logging
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
        """Test _update_redis_cache updates cache correctly (Parquet-only path)."""
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
                with patch('mes_dashboard.core.redis_df_store.redis_store_df') as mock_store:
                    updater = cu.CacheUpdater()
                    result = updater._update_redis_cache(test_df, '2024-01-15 10:30:00')

                    assert result is True
                    mock_pipeline.execute.assert_called_once()
                    # Two metadata keys written via pipeline: meta:sys_date, meta:updated_at
                    assert mock_pipeline.set.call_count == 2
                    for call in mock_pipeline.set.call_args_list:
                        assert call.kwargs.get("ex") == updater.interval * 3
                    # Parquet write called with correct TTL
                    mock_store.assert_called_once()
                    _, store_kwargs = mock_store.call_args
                    assert store_kwargs.get("ttl") == updater.interval * 3

    def test_update_redis_cache_no_client(self):
        """Test _update_redis_cache handles no client."""
        import mes_dashboard.core.cache_updater as cu

        test_df = pd.DataFrame({'LOTID': ['LOT001']})

        with patch.object(cu, 'get_redis_client', return_value=None):
            updater = cu.CacheUpdater()
            result = updater._update_redis_cache(test_df, '2024-01-15')
            assert result is False

    def test_update_redis_cache_returns_false_on_pipeline_failure(self):
        """Failed pipeline execute should return False gracefully."""
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

    def test_update_redis_cache_ttl_override(self):
        """Configured TTL override should apply to metadata keys and Parquet write."""
        import mes_dashboard.core.cache_updater as cu

        mock_client = MagicMock()
        mock_pipeline = MagicMock()
        mock_client.pipeline.return_value = mock_pipeline
        test_df = pd.DataFrame({'LOTID': ['LOT001'], 'QTY': [100]})

        with patch.object(cu, 'WIP_CACHE_TTL_SECONDS', 42):
            with patch.object(cu, 'get_redis_client', return_value=mock_client):
                with patch.object(cu, 'get_key', side_effect=lambda k: f'mes_wip:{k}'):
                    with patch('mes_dashboard.core.redis_df_store.redis_store_df') as mock_store:
                        updater = cu.CacheUpdater(interval=600)
                        result = updater._update_redis_cache(test_df, '2024-01-15 10:30:00')

        assert result is True
        # Two metadata keys: meta:sys_date, meta:updated_at
        assert mock_pipeline.set.call_count == 2
        for call in mock_pipeline.set.call_args_list:
            assert call.kwargs.get("ex") == 42
        # Parquet write gets TTL=42
        mock_store.assert_called_once()
        _, store_kwargs = mock_store.call_args
        assert store_kwargs.get("ttl") == 42


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

    def test_run_dataset_warmups_calls_owned_tasks_only(self):
        import mes_dashboard.core.cache_updater as cu

        updater = cu.CacheUpdater(interval=1)
        with patch.object(updater, '_warmup_reject_dataset') as mock_reject, \
             patch.object(updater, '_warmup_yield_alert_dataset') as mock_yield, \
             patch.object(updater, '_warmup_reject_options') as mock_options:
            updater._run_dataset_warmups()

        mock_reject.assert_not_called()
        mock_yield.assert_not_called()
        mock_options.assert_called_once()

    def test_warmup_failure_is_swallowed(self):
        import mes_dashboard.core.cache_updater as cu

        updater = cu.CacheUpdater(interval=1)
        with patch.object(updater, '_warmup_reject_options', side_effect=RuntimeError('options failed')):
            updater._run_dataset_warmups()

    @patch('mes_dashboard.services.reject_dataset_cache.ensure_dataset_loaded', return_value={'query_id': 'qid-r', 'cache_hit': True})
    def test_warmup_reject_dataset_delegates(self, mock_ensure):
        import mes_dashboard.core.cache_updater as cu

        updater = cu.CacheUpdater(interval=1)
        updater._warmup_reject_dataset()
        mock_ensure.assert_called_once()

    @patch('mes_dashboard.services.yield_alert_dataset_cache.ensure_dataset_loaded', return_value={'query_id': 'qid-y', 'cache_hit': False})
    @patch('mes_dashboard.core.cache_updater.try_acquire_lock', return_value=True)
    def test_warmup_yield_alert_dataset_delegates(self, mock_lock, mock_ensure):
        import mes_dashboard.core.cache_updater as cu

        updater = cu.CacheUpdater(interval=1)
        updater._warmup_yield_alert_dataset()
        mock_ensure.assert_called_once()

    @patch('mes_dashboard.services.yield_alert_dataset_cache.ensure_dataset_loaded')
    @patch('mes_dashboard.core.cache_updater.try_acquire_lock', return_value=False)
    def test_warmup_yield_alert_dataset_skips_when_lock_held(self, mock_lock, mock_ensure):
        import mes_dashboard.core.cache_updater as cu

        updater = cu.CacheUpdater(interval=1)
        updater._warmup_yield_alert_dataset()
        mock_lock.assert_called_once_with("yield_alert_warmup", ttl_seconds=120, fail_mode="closed")
        mock_ensure.assert_not_called()

    @patch('mes_dashboard.services.yield_alert_dataset_cache.ensure_dataset_loaded', return_value={'query_id': 'qid-y', 'cache_hit': False})
    @patch('mes_dashboard.core.cache_updater.release_lock')
    @patch('mes_dashboard.core.cache_updater.try_acquire_lock', return_value=True)
    def test_warmup_yield_alert_dataset_releases_lock_on_success(self, mock_acquire, mock_release, mock_ensure):
        import mes_dashboard.core.cache_updater as cu

        updater = cu.CacheUpdater(interval=1)
        updater._warmup_yield_alert_dataset()
        mock_release.assert_called_once_with("yield_alert_warmup")

    @patch('mes_dashboard.services.yield_alert_dataset_cache.ensure_dataset_loaded', side_effect=RuntimeError('boom'))
    @patch('mes_dashboard.core.cache_updater.release_lock')
    @patch('mes_dashboard.core.cache_updater.try_acquire_lock', return_value=True)
    def test_warmup_yield_alert_dataset_releases_lock_on_error(self, mock_acquire, mock_release, mock_ensure):
        import mes_dashboard.core.cache_updater as cu

        updater = cu.CacheUpdater(interval=1)
        with pytest.raises(RuntimeError):
            updater._warmup_yield_alert_dataset()
        mock_release.assert_called_once_with("yield_alert_warmup")


# ── Task 3.3: WIP canonical key alignment (writer) ──────────────────────────

class TestWipCacheWriterCanonicalKey:
    """Verify cache_updater passes raw suffix 'data:parquet' to redis_store_df (no double prefix)."""

    def test_update_redis_cache_passes_raw_suffix_to_store_df(self):
        """redis_store_df must receive 'data:parquet' as the key, not a pre-prefixed string."""
        import mes_dashboard.core.cache_updater as cu

        mock_client = MagicMock()
        mock_pipeline = MagicMock()
        mock_client.pipeline.return_value = mock_pipeline

        test_df = pd.DataFrame({'LOTID': ['LOT001'], 'QTY': [100]})
        captured_key = {}

        def capture_store(key, df, **kwargs):
            captured_key["key"] = key
            return True

        with patch.object(cu, 'get_redis_client', return_value=mock_client):
            with patch.object(cu, 'get_key', side_effect=lambda k: f'mes_wip:{k}'):
                with patch('mes_dashboard.core.redis_df_store.redis_store_df', side_effect=capture_store):
                    updater = cu.CacheUpdater()
                    updater._update_redis_cache(test_df, '2024-01-15 10:30:00')

        assert captured_key.get("key") == "data:parquet", (
            f"Expected raw suffix 'data:parquet', got '{captured_key.get('key')}'. "
            "Double-prefix bug: did not remove get_key() pre-call from cache_updater."
        )


class TestStopCacheUpdater:
    """Test module-level stop_cache_updater() function."""

    @pytest.fixture(autouse=True)
    def reset_global(self):
        """Reset _CACHE_UPDATER global before and after each test."""
        import mes_dashboard.core.cache_updater as cu
        original = cu._CACHE_UPDATER
        cu._CACHE_UPDATER = None
        yield
        cu._CACHE_UPDATER = None

    def test_stop_cache_updater_stops_running_thread(self):
        """stop_cache_updater() stops a running thread within 5 seconds."""
        import mes_dashboard.core.cache_updater as cu

        with patch.object(cu, 'REDIS_ENABLED', True):
            with patch.object(cu, 'redis_available', return_value=True):
                with patch.object(cu, 'read_sql_df', return_value=None):
                    cu.start_cache_updater()
                    assert cu._CACHE_UPDATER is not None
                    assert cu._CACHE_UPDATER.is_running()

                    cu.stop_cache_updater()
                    assert not cu._CACHE_UPDATER.is_running()

    def test_stop_cache_updater_noop_when_not_started(self):
        """stop_cache_updater() is a no-op when thread was never started."""
        import mes_dashboard.core.cache_updater as cu

        assert cu._CACHE_UPDATER is None
        # Should not raise
        cu.stop_cache_updater()

    def test_stop_cache_updater_warns_when_thread_does_not_stop(self, caplog):
        """stop_cache_updater() logs WARNING when thread is still alive after join timeout."""
        import threading
        import mes_dashboard.core.cache_updater as cu

        updater = cu.CacheUpdater()
        # Simulate a hung thread: is_alive() always True, join() is a no-op
        hung_thread = patch.object(threading.Thread, 'join', return_value=None)
        alive = patch.object(threading.Thread, 'is_alive', return_value=True)

        with hung_thread, alive:
            updater._thread = threading.Thread(target=lambda: None, daemon=True)
            updater._thread.start()

            with caplog.at_level(logging.WARNING, logger="mes_dashboard.core.cache_updater"):
                updater.stop()

        warning_msgs = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert any("did not stop" in r.message for r in warning_msgs), (
            f"Expected WARNING about thread not stopping, got: {[r.message for r in caplog.records]}"
        )
