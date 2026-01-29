# -*- coding: utf-8 -*-
"""Unit tests for cache module.

Tests cache read/write functionality and fallback mechanism.
"""

import pytest
from unittest.mock import patch, MagicMock
import pandas as pd
import json


class TestGetCachedWipData:
    """Test get_cached_wip_data function."""

    @pytest.fixture(autouse=True)
    def reset_redis(self):
        """Reset Redis client state."""
        import mes_dashboard.core.redis_client as rc
        rc._REDIS_CLIENT = None
        yield
        rc._REDIS_CLIENT = None

    def test_returns_none_when_redis_disabled(self):
        """Test returns None when Redis is disabled."""
        import mes_dashboard.core.cache as cache

        with patch.object(cache, 'REDIS_ENABLED', False):
            result = cache.get_cached_wip_data()
            assert result is None

    def test_returns_none_when_client_unavailable(self):
        """Test returns None when Redis client is unavailable."""
        import mes_dashboard.core.cache as cache

        with patch.object(cache, 'REDIS_ENABLED', True):
            with patch.object(cache, 'get_redis_client', return_value=None):
                result = cache.get_cached_wip_data()
                assert result is None

    def test_returns_none_when_cache_miss(self, reset_redis):
        """Test returns None when cache key doesn't exist."""
        import mes_dashboard.core.cache as cache

        mock_client = MagicMock()
        mock_client.get.return_value = None

        with patch.object(cache, 'REDIS_ENABLED', True):
            with patch.object(cache, 'get_redis_client', return_value=mock_client):
                result = cache.get_cached_wip_data()
                assert result is None

    def test_returns_dataframe_from_cache(self, reset_redis):
        """Test returns DataFrame when cache hit."""
        import mes_dashboard.core.cache as cache

        # Create test data as JSON string (what Redis returns with decode_responses=True)
        test_data = [
            {'LOTID': 'LOT001', 'QTY': 100, 'WORKORDER': 'WO001'},
            {'LOTID': 'LOT002', 'QTY': 200, 'WORKORDER': 'WO002'}
        ]
        cached_json = json.dumps(test_data)

        mock_client = MagicMock()
        mock_client.get.return_value = cached_json  # String, not bytes

        with patch.object(cache, 'REDIS_ENABLED', True):
            with patch.object(cache, 'get_redis_client', return_value=mock_client):
                with patch.object(cache, 'get_key', return_value='mes_wip:data'):
                    result = cache.get_cached_wip_data()

                    assert result is not None
                    assert isinstance(result, pd.DataFrame)
                    assert len(result) == 2
                    assert 'LOTID' in result.columns

    def test_handles_invalid_json(self, reset_redis):
        """Test handles invalid JSON gracefully."""
        import mes_dashboard.core.cache as cache

        mock_client = MagicMock()
        mock_client.get.return_value = 'invalid json {'

        with patch.object(cache, 'REDIS_ENABLED', True):
            with patch.object(cache, 'get_redis_client', return_value=mock_client):
                with patch.object(cache, 'get_key', return_value='mes_wip:data'):
                    result = cache.get_cached_wip_data()
                    assert result is None


class TestGetCachedSysDate:
    """Test get_cached_sys_date function."""

    def test_returns_none_when_redis_disabled(self):
        """Test returns None when Redis is disabled."""
        import mes_dashboard.core.cache as cache

        with patch.object(cache, 'REDIS_ENABLED', False):
            result = cache.get_cached_sys_date()
            assert result is None

    def test_returns_sys_date_from_cache(self):
        """Test returns SYS_DATE when cache hit."""
        import mes_dashboard.core.cache as cache

        mock_client = MagicMock()
        mock_client.get.return_value = '2024-01-15 10:30:00'  # String, not bytes

        with patch.object(cache, 'REDIS_ENABLED', True):
            with patch.object(cache, 'get_redis_client', return_value=mock_client):
                with patch.object(cache, 'get_key', return_value='mes_wip:meta:sys_date'):
                    result = cache.get_cached_sys_date()
                    assert result == '2024-01-15 10:30:00'


class TestGetCacheUpdatedAt:
    """Test get_cache_updated_at function."""

    def test_returns_none_when_redis_disabled(self):
        """Test returns None when Redis is disabled."""
        import mes_dashboard.core.cache as cache

        with patch.object(cache, 'REDIS_ENABLED', False):
            result = cache.get_cache_updated_at()
            assert result is None

    def test_returns_updated_at_from_cache(self):
        """Test returns updated_at timestamp when cache hit."""
        import mes_dashboard.core.cache as cache

        mock_client = MagicMock()
        mock_client.get.return_value = '2024-01-15T10:30:00'  # String, not bytes

        with patch.object(cache, 'REDIS_ENABLED', True):
            with patch.object(cache, 'get_redis_client', return_value=mock_client):
                with patch.object(cache, 'get_key', return_value='mes_wip:meta:updated_at'):
                    result = cache.get_cache_updated_at()
                    assert result == '2024-01-15T10:30:00'


class TestWipDataWithFallback:
    """Test get_wip_data_with_fallback function."""

    def test_uses_cache_when_available(self):
        """Test uses cache when data is available."""
        import mes_dashboard.core.cache as cache

        cached_df = pd.DataFrame({
            'LOTID': ['LOT001'],
            'QTY': [100]
        })

        mock_fallback = MagicMock()

        with patch.object(cache, 'get_cached_wip_data', return_value=cached_df):
            result = cache.get_wip_data_with_fallback(mock_fallback)

            assert result is not None
            assert len(result) == 1
            # Fallback should NOT be called
            mock_fallback.assert_not_called()

    def test_fallback_when_cache_unavailable(self):
        """Test falls back when cache is unavailable."""
        import mes_dashboard.core.cache as cache

        oracle_df = pd.DataFrame({
            'LOTID': ['LOT001', 'LOT002'],
            'QTY': [100, 200]
        })

        mock_fallback = MagicMock(return_value=oracle_df)

        with patch.object(cache, 'get_cached_wip_data', return_value=None):
            result = cache.get_wip_data_with_fallback(mock_fallback)

            assert result is not None
            assert len(result) == 2
            mock_fallback.assert_called_once()


class TestNoOpCache:
    """Test NoOpCache fallback class."""

    def test_noop_cache_get(self):
        """Test NoOpCache.get returns None."""
        from mes_dashboard.core.cache import NoOpCache
        cache = NoOpCache()
        result = cache.get('any_key')
        assert result is None

    def test_noop_cache_set(self):
        """Test NoOpCache.set returns None."""
        from mes_dashboard.core.cache import NoOpCache
        cache = NoOpCache()
        result = cache.set('any_key', 'any_value', 300)
        assert result is None


class TestIsCacheAvailable:
    """Test is_cache_available function."""

    def test_returns_false_when_disabled(self):
        """Test returns False when Redis is disabled."""
        import mes_dashboard.core.cache as cache

        with patch.object(cache, 'REDIS_ENABLED', False):
            result = cache.is_cache_available()
            assert result is False

    def test_returns_false_when_no_client(self):
        """Test returns False when no Redis client."""
        import mes_dashboard.core.cache as cache

        with patch.object(cache, 'REDIS_ENABLED', True):
            with patch.object(cache, 'get_redis_client', return_value=None):
                result = cache.is_cache_available()
                assert result is False

    def test_returns_true_when_data_exists(self):
        """Test returns True when data exists in Redis."""
        import mes_dashboard.core.cache as cache

        mock_client = MagicMock()
        mock_client.exists.return_value = 1

        with patch.object(cache, 'REDIS_ENABLED', True):
            with patch.object(cache, 'get_redis_client', return_value=mock_client):
                with patch.object(cache, 'get_key', return_value='mes_wip:data'):
                    result = cache.is_cache_available()
                    assert result is True
