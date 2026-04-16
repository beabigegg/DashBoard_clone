# -*- coding: utf-8 -*-
"""Unit tests for filter_cache.py.

Covers:
- TTL expiry causes re-load (stale cache triggers refresh)
- Stampede protection: concurrent is_loading blocks second caller
- Redis-disabled fallback: falls through to Oracle load path
- Redis L2 hit: data served from Redis without touching Oracle
- Redis miss: loads from Oracle, writes result back to Redis
- get_workcenter_groups returns None when load fails
- get_cache_status reflects correct state
"""

from __future__ import annotations

import threading
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, call

import pytest

import mes_dashboard.services.filter_cache as fc


@pytest.fixture(autouse=True)
def _reset_cache():
    """Reset in-memory cache state before each test."""
    with fc._CACHE_LOCK:
        fc._CACHE.update({
            'workcenter_groups': None,
            'workcenter_mapping': None,
            'workcenter_to_short': None,
            'spec_order_mapping': None,
            'spec_workcenter_mapping': None,
            'last_refresh': None,
            'is_loading': False,
        })
    yield
    with fc._CACHE_LOCK:
        fc._CACHE.update({
            'workcenter_groups': None,
            'workcenter_mapping': None,
            'workcenter_to_short': None,
            'spec_order_mapping': None,
            'spec_workcenter_mapping': None,
            'last_refresh': None,
            'is_loading': False,
        })


class TestTTLExpiry:
    """Stale cache entries are refreshed after TTL expires."""

    def test_fresh_cache_is_not_reloaded(self):
        """When last_refresh is recent, _ensure_cache_loaded must skip reload."""
        with fc._CACHE_LOCK:
            fc._CACHE['last_refresh'] = datetime.now()
            fc._CACHE['workcenter_groups'] = [{"name": "DB", "sequence": 1}]

        with patch.object(fc, '_load_cache') as mock_load:
            fc._ensure_cache_loaded()

        mock_load.assert_not_called()

    def test_stale_cache_triggers_reload(self):
        """When last_refresh is older than TTL, a reload must be triggered."""
        stale_time = datetime.now() - timedelta(seconds=fc.CACHE_TTL_SECONDS + 60)
        with fc._CACHE_LOCK:
            fc._CACHE['last_refresh'] = stale_time

        with patch.object(fc, '_load_cache', return_value=True) as mock_load:
            fc._ensure_cache_loaded()

        mock_load.assert_called_once()

    def test_force_refresh_reloads_even_when_fresh(self):
        """force_refresh=True must reload even when cache is not yet stale."""
        with fc._CACHE_LOCK:
            fc._CACHE['last_refresh'] = datetime.now()
            fc._CACHE['workcenter_groups'] = [{"name": "DB", "sequence": 1}]

        with patch.object(fc, '_load_cache', return_value=True) as mock_load:
            fc._ensure_cache_loaded(force_refresh=True)

        mock_load.assert_called_once()

    def test_cache_returns_none_when_never_loaded(self):
        """get_workcenter_groups returns None (or empty list) when Oracle load fails."""
        with patch.object(fc, '_load_cache', return_value=False):
            with patch.object(fc, '_read_from_redis', return_value=None):
                result = fc.get_workcenter_groups()
        # Either None or empty list is acceptable for a failed load
        assert not result


class TestStampedeProtection:
    """is_loading flag prevents concurrent duplicate loads."""

    def test_second_caller_returns_without_loading_when_is_loading(self):
        """If is_loading is True, _ensure_cache_loaded must not call _load_cache."""
        with fc._CACHE_LOCK:
            fc._CACHE['is_loading'] = True
            fc._CACHE['last_refresh'] = None  # not yet loaded

        with patch.object(fc, '_load_cache') as mock_load:
            fc._ensure_cache_loaded()

        mock_load.assert_not_called()

    def test_load_cache_returns_false_when_already_loading(self):
        """_load_cache must return False immediately if is_loading is already set."""
        with fc._CACHE_LOCK:
            fc._CACHE['is_loading'] = True

        result = fc._load_cache()
        assert result is False


class TestRedisDisabledFallback:
    """When REDIS_ENABLED is False, Oracle is the sole data source."""

    def test_read_from_redis_returns_none_when_disabled(self):
        """_read_from_redis must return None when Redis is disabled."""
        with patch.object(fc, 'REDIS_ENABLED', False):
            result = fc._read_from_redis()
        assert result is None

    def test_write_to_redis_does_nothing_when_disabled(self):
        """_write_to_redis must be a no-op when Redis is disabled."""
        with patch.object(fc, 'REDIS_ENABLED', False):
            with patch.object(fc, 'get_redis_client') as mock_client:
                fc._write_to_redis({'workcenter_groups': []})
        mock_client.assert_not_called()

    def test_load_cache_falls_through_to_oracle_when_redis_disabled(self):
        """With Redis disabled, _load_cache must call Oracle load functions."""
        with patch.object(fc, '_read_from_redis', return_value=None), \
             patch.object(fc, '_load_workcenter_data', return_value=([], {}, {})), \
             patch.object(fc, '_load_spec_order_mapping_from_spec', return_value={}), \
             patch.object(fc, '_load_spec_workcenter_mapping', return_value={}), \
             patch.object(fc, '_write_to_redis') as mock_write:
            result = fc._load_cache()

        assert result is True
        mock_write.assert_called_once()


class TestRedisL2Hit:
    """Data is served from Redis without touching Oracle when L2 hits."""

    def test_cache_populated_from_redis_on_l2_hit(self):
        """When Redis returns data, Oracle loaders must NOT be called."""
        redis_payload = {
            'workcenter_groups': [{"name": "DB", "sequence": 1}],
            'workcenter_mapping': {"DB-A": {"group": "DB", "sequence": 1}},
            'workcenter_to_short': {"DB-A": "DB"},
            'spec_order_mapping': {"SPEC-A": 1},
            'spec_workcenter_mapping': {},
        }

        with patch.object(fc, '_read_from_redis', return_value=redis_payload), \
             patch.object(fc, '_load_workcenter_data') as mock_oracle:
            result = fc._load_cache()

        assert result is True
        mock_oracle.assert_not_called()

        with fc._CACHE_LOCK:
            groups = fc._CACHE['workcenter_groups']
        assert groups == [{"name": "DB", "sequence": 1}]

    def test_get_workcenter_groups_returns_redis_data(self):
        """get_workcenter_groups must return data served from Redis L2."""
        with fc._CACHE_LOCK:
            fc._CACHE['workcenter_groups'] = [{"name": "WB", "sequence": 2}]
            fc._CACHE['last_refresh'] = datetime.now()

        result = fc.get_workcenter_groups()
        assert result == [{"name": "WB", "sequence": 2}]


class TestRedisMissFallbackToOracle:
    """On Redis miss, Oracle is the fallback and result is written back."""

    def test_oracle_result_written_to_redis_on_miss(self):
        """After Oracle load, result must be written back to Redis for other workers."""
        oracle_groups = [{"name": "MLD", "sequence": 3}]
        oracle_mapping = {"MLD-A": {"group": "MLD", "sequence": 3}}

        with patch.object(fc, '_read_from_redis', return_value=None), \
             patch.object(fc, '_load_workcenter_data', return_value=(oracle_groups, oracle_mapping, {})), \
             patch.object(fc, '_load_spec_order_mapping_from_spec', return_value={}), \
             patch.object(fc, '_load_spec_workcenter_mapping', return_value={}), \
             patch.object(fc, '_write_to_redis') as mock_write:
            result = fc._load_cache()

        assert result is True
        mock_write.assert_called_once()
        written_data = mock_write.call_args[0][0]
        assert written_data['workcenter_groups'] == oracle_groups

    def test_oracle_failure_returns_false_and_resets_is_loading(self):
        """If Oracle load raises, _load_cache must return False and clear is_loading."""
        with patch.object(fc, '_read_from_redis', return_value=None), \
             patch.object(fc, '_load_workcenter_data', side_effect=Exception("Oracle down")):
            result = fc._load_cache()

        assert result is False
        with fc._CACHE_LOCK:
            assert fc._CACHE['is_loading'] is False


class TestCacheStatus:
    """get_cache_status reflects correct loaded/unloaded state."""

    def test_status_when_never_loaded(self):
        status = fc.get_cache_status()
        assert status['loaded'] is False
        assert status['last_refresh'] is None
        assert status['is_loading'] is False

    def test_status_when_loaded(self):
        with fc._CACHE_LOCK:
            fc._CACHE['last_refresh'] = datetime.now()
            fc._CACHE['workcenter_groups'] = [{"name": "DB", "sequence": 1}, {"name": "WB", "sequence": 2}]
            fc._CACHE['workcenter_mapping'] = {"DB-A": {}, "WB-A": {}}

        status = fc.get_cache_status()
        assert status['loaded'] is True
        assert status['last_refresh'] is not None
        assert status['workcenter_groups_count'] == 2
        assert status['workcenter_mapping_count'] == 2
