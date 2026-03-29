# -*- coding: utf-8 -*-
"""Unit tests for cache module.

Tests cache read/write functionality and fallback mechanism.
"""

import pytest
from unittest.mock import patch, MagicMock
import pandas as pd
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor


class TestGetCachedWipData:
    """Test get_cached_wip_data function."""

    @pytest.fixture(autouse=True)
    def reset_redis(self):
        """Reset Redis client state and process-level cache."""
        import mes_dashboard.core.redis_client as rc
        import mes_dashboard.core.cache as cache
        rc._REDIS_CLIENT = None
        # Clear process-level cache to avoid test interference
        cache._wip_df_cache.clear()
        yield
        rc._REDIS_CLIENT = None
        cache._wip_df_cache.clear()

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
        """Test returns DataFrame when cache hit (Parquet path)."""
        import mes_dashboard.core.cache as cache

        test_data = [
            {'LOTID': 'LOT001', 'QTY': 100, 'WORKORDER': 'WO001'},
            {'LOTID': 'LOT002', 'QTY': 200, 'WORKORDER': 'WO002'}
        ]
        expected_df = pd.DataFrame(test_data)

        mock_client = MagicMock()

        with patch.object(cache, 'REDIS_ENABLED', True):
            with patch.object(cache, 'get_redis_client', return_value=mock_client):
                with patch.object(cache, 'get_key', return_value='mes_wip:data:parquet'):
                    with patch('mes_dashboard.core.redis_df_store.redis_load_df', return_value=expected_df):
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

    def test_concurrent_requests_parse_redis_once(self, reset_redis):
        """Concurrent misses should trigger Redis Parquet load exactly once."""
        import mes_dashboard.core.cache as cache

        test_data = [
            {'LOTID': 'LOT001', 'QTY': 100, 'WORKORDER': 'WO001'},
            {'LOTID': 'LOT002', 'QTY': 200, 'WORKORDER': 'WO002'}
        ]

        mock_client = MagicMock()

        load_count_lock = threading.Lock()
        load_count = 0

        def slow_load_df(*args, **kwargs):
            nonlocal load_count
            with load_count_lock:
                load_count += 1
            time.sleep(0.05)
            return pd.DataFrame(test_data)

        start_event = threading.Event()

        def call_cache():
            start_event.wait(timeout=1)
            return cache.get_cached_wip_data()

        with patch.object(cache, 'REDIS_ENABLED', True):
            with patch.object(cache, 'get_redis_client', return_value=mock_client):
                with patch.object(cache, 'get_key', return_value='mes_wip:data:parquet'):
                    with patch('mes_dashboard.core.redis_df_store.redis_load_df', side_effect=slow_load_df):
                        with ThreadPoolExecutor(max_workers=6) as pool:
                            futures = [pool.submit(call_cache) for _ in range(6)]
                            start_event.set()
                            results = [future.result(timeout=3) for future in futures]

        assert load_count == 1
        assert all(result is not None for result in results)
        assert all(len(result) == 2 for result in results)


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


class TestMemoryTTLCache:
    """Test in-memory TTL cache backend."""

    def test_set_and_get_value(self):
        from mes_dashboard.core.cache import MemoryTTLCache

        cache = MemoryTTLCache()
        cache.set('k1', {'v': 1}, 10)
        assert cache.get('k1') == {'v': 1}

    def test_expired_value_returns_none(self):
        from mes_dashboard.core.cache import MemoryTTLCache

        cache = MemoryTTLCache()
        cache.set('k2', {'v': 2}, 1)

        with patch('mes_dashboard.core.cache.time.time', return_value=10_000):
            cache._store['k2'] = ({'v': 2}, 9_999)
            assert cache.get('k2') is None

    def test_max_size_eviction_removes_least_recently_used(self):
        from mes_dashboard.core.cache import MemoryTTLCache

        cache = MemoryTTLCache(max_size=2)
        cache.set('k1', {'v': 1}, 60)
        cache.set('k2', {'v': 2}, 60)
        assert cache.get('k1') == {'v': 1}  # refresh recency
        cache.set('k3', {'v': 3}, 60)

        assert cache.get('k2') is None
        assert cache.get('k1') == {'v': 1}
        assert cache.get('k3') == {'v': 3}

    def test_default_max_size_is_256(self):
        from mes_dashboard.core.cache import MemoryTTLCache

        cache = MemoryTTLCache()
        assert cache._max_size == 256

    def test_hit_miss_counter_and_reset(self):
        from mes_dashboard.core.cache import MemoryTTLCache

        cache = MemoryTTLCache(max_size=4)
        cache.set('k1', {'v': 1}, 60)
        assert cache.get('k1') == {'v': 1}
        assert cache.get('missing') is None

        counts = cache.get_hit_miss_counts()
        assert counts == {'hits': 1, 'misses': 1}
        reset_counts = cache.reset_hit_miss_counts()
        assert reset_counts == {'hits': 1, 'misses': 1}
        assert cache.get_hit_miss_counts() == {'hits': 0, 'misses': 0}


class TestCreateDefaultCacheBackend:
    """Test default cache backend factory."""

    def test_returns_layered_cache_without_redis(self):
        import mes_dashboard.core.cache as cache

        with patch.object(cache, 'redis_available', return_value=False):
            backend = cache.create_default_cache_backend()
            backend.set('factory-key', {'x': 1}, 30)
            assert backend.get('factory-key') == {'x': 1}


class TestLayeredCacheTelemetry:
    """Telemetry behavior for layered route cache."""

    def test_l1_only_degraded_mode_visibility(self):
        from mes_dashboard.core.cache import MemoryTTLCache, LayeredCache

        backend = LayeredCache(l1=MemoryTTLCache(), l2=None, redis_expected=True)
        backend.set('k1', {'v': 1}, 30)
        assert backend.get('k1') == {'v': 1}  # L1 hit
        assert backend.get('missing') is None  # miss

        telemetry = backend.telemetry()
        assert telemetry['mode'] == 'l1-only'
        assert telemetry['degraded'] is True
        assert telemetry['l1_hits'] >= 1
        assert telemetry['misses'] >= 1

    def test_l1_l2_hit_and_rates(self):
        from mes_dashboard.core.cache import MemoryTTLCache, LayeredCache

        class FakeL2:
            def __init__(self):
                self.store = {'cold': {'from': 'l2'}}

            def get(self, key):
                return self.store.get(key)

            def set(self, key, value, ttl):
                self.store[key] = value

            def telemetry(self):
                return {'error_count': 0}

        backend = LayeredCache(l1=MemoryTTLCache(), l2=FakeL2(), redis_expected=True)
        assert backend.get('cold') == {'from': 'l2'}  # L2 hit then warm L1
        assert backend.get('cold') == {'from': 'l2'}  # L1 hit

        telemetry = backend.telemetry()
        assert telemetry['mode'] == 'l1+l2'
        assert telemetry['degraded'] is False
        assert telemetry['l2_hits'] >= 1
        assert telemetry['l1_hits'] >= 1
        assert telemetry['reads_total'] >= 2


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


class TestProcessLevelCache:
    """Test bounded process-level cache behavior."""

    def test_lru_eviction_prefers_recent_keys(self):
        from mes_dashboard.core.cache import ProcessLevelCache

        cache = ProcessLevelCache(ttl_seconds=60, max_size=2)
        df1 = pd.DataFrame([{"LOTID": "A"}])
        df2 = pd.DataFrame([{"LOTID": "B"}])
        df3 = pd.DataFrame([{"LOTID": "C"}])

        cache.set("a", df1)
        cache.set("b", df2)
        assert cache.get("a") is not None  # refresh recency for "a"
        cache.set("c", df3)  # should evict "b"

        assert cache.get("b") is None
        assert cache.get("a") is not None
        assert cache.get("c") is not None

    def test_wip_process_cache_uses_bounded_config(self):
        import mes_dashboard.core.cache as cache

        assert cache.WIP_PROCESS_CACHE_MAX_SIZE >= 1
        assert cache._wip_df_cache.max_size == cache.WIP_PROCESS_CACHE_MAX_SIZE

    def test_dataset_cache_max_size_configuration(self):
        from mes_dashboard.services import (
            hold_dataset_cache,
            resource_dataset_cache,
            reject_dataset_cache,
            yield_alert_dataset_cache,
        )

        assert hold_dataset_cache._dataset_cache.max_size == 1
        assert resource_dataset_cache._dataset_cache.max_size == 1
        assert reject_dataset_cache._dataset_cache.max_size == 1
        assert yield_alert_dataset_cache._dataset_cache.max_size == 1


# ── Task 3.3: WIP canonical key alignment ───────────────────────────────────

class TestWipCacheCanonicalKey:
    """Verify reader and availability probe use the canonical 'data:parquet' raw suffix."""

    def test_get_cached_wip_data_reads_raw_suffix(self):
        """get_cached_wip_data must call redis_load_df('data:parquet'), not get_key('data:parquet')."""
        import mes_dashboard.core.cache as cache

        captured = {}

        def fake_load_df(key):
            captured["key"] = key
            return None  # simulate miss

        test_df = pd.DataFrame({"LOTID": ["L1"]})

        with patch.object(cache, 'REDIS_ENABLED', True):
            with patch.object(cache, 'get_redis_client', return_value=MagicMock()):
                with patch('mes_dashboard.core.redis_df_store.redis_load_df', side_effect=fake_load_df):
                    cache._wip_df_cache._cache.clear()
                    cache.get_cached_wip_data()

        assert captured.get("key") == "data:parquet", (
            f"Expected raw suffix 'data:parquet', got '{captured.get('key')}'"
        )

    def test_is_cache_available_checks_parquet_key(self):
        """is_cache_available() must check the 'data:parquet' canonical key, not legacy 'data'."""
        import mes_dashboard.core.cache as cache

        checked_keys = []
        mock_client = MagicMock()
        mock_client.exists.side_effect = lambda k: checked_keys.append(k) or 1

        with patch.object(cache, 'REDIS_ENABLED', True):
            with patch.object(cache, 'get_redis_client', return_value=mock_client):
                with patch.object(cache, 'get_key', side_effect=lambda k: f"mes_wip:{k}"):
                    cache.is_cache_available()

        assert any("data:parquet" in k for k in checked_keys), (
            f"Expected check for 'data:parquet', checked: {checked_keys}"
        )
        assert not any(k.endswith(":data") for k in checked_keys), (
            f"Legacy 'mes_wip:data' key must not be checked, found: {checked_keys}"
        )
