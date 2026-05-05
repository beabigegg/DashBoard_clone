# -*- coding: utf-8 -*-
"""Task 6.2 — Cache miss → refill → hit and stampede across simulated workers.

Integration tests covering the ProcessLevelCache and MemoryTTLCache lifecycle:
  - miss → refill → hit
  - stampede protection (expensive function called only once)
  - REDIS_ENABLED=false graceful no-op behaviour
"""

import threading
import time
from unittest.mock import patch

import pytest

from mes_dashboard.core.cache import MemoryTTLCache, ProcessLevelCache
from mes_dashboard.core.redis_client import redis_available


@pytest.mark.integration
class TestCacheLifecycle:
    """Task 6.2 — Cache miss → refill → hit and stampede across simulated workers."""

    # ------------------------------------------------------------------
    # ProcessLevelCache — in-process L1 cache
    # ------------------------------------------------------------------

    def test_cache_miss_then_refill_then_hit(self):
        """get() returns None (miss), set() stores the value, second get() returns it (hit)."""
        import pandas as pd

        cache = ProcessLevelCache(ttl_seconds=60, max_size=4)
        key = "test:miss_refill_hit"

        # Miss
        assert cache.get(key) is None

        # Refill
        df = pd.DataFrame({"a": [1, 2, 3]})
        cache.set(key, df)

        # Hit
        result = cache.get(key)
        assert result is not None
        assert list(result["a"]) == [1, 2, 3]

    def test_cache_entry_expires_after_ttl(self):
        """Entry should be evicted after TTL elapses."""
        import pandas as pd

        cache = ProcessLevelCache(ttl_seconds=1, max_size=4)
        key = "test:expiry"
        cache.set(key, pd.DataFrame({"x": [9]}))

        time.sleep(1.1)

        assert cache.get(key) is None

    def test_stampede_protection_serializes_refills(self):
        """Under concurrent read requests, the expensive factory function is called only once.

        Simulates 4 threads all discovering a cache miss simultaneously and racing
        to refill.  The caller is responsible for using a lock around the miss→fill
        path; we verify the pattern works correctly when using a shared threading.Lock.
        """
        import pandas as pd

        cache = ProcessLevelCache(ttl_seconds=60, max_size=4)
        key = "test:stampede"
        fill_lock = threading.Lock()
        call_count = {"n": 0}

        def expensive_fetch():
            call_count["n"] += 1
            time.sleep(0.05)
            return pd.DataFrame({"v": [42]})

        def worker():
            result = cache.get(key)
            if result is None:
                with fill_lock:
                    # Double-check under lock (classic double-checked locking)
                    result = cache.get(key)
                    if result is None:
                        result = expensive_fetch()
                        cache.set(key, result)

        threads = [threading.Thread(target=worker) for _ in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Expensive function should have been called exactly once
        assert call_count["n"] == 1
        assert cache.get(key) is not None

    # ------------------------------------------------------------------
    # MemoryTTLCache — route-level API response cache
    # ------------------------------------------------------------------

    def test_memory_ttl_cache_miss_returns_none(self):
        """MemoryTTLCache returns None for unknown keys."""
        cache = MemoryTTLCache(max_size=16)
        assert cache.get("nonexistent") is None

    def test_memory_ttl_cache_set_and_get(self):
        """MemoryTTLCache stores and retrieves values before TTL."""
        cache = MemoryTTLCache(max_size=16)
        cache.set("k1", {"rows": 5}, ttl=60)
        assert cache.get("k1") == {"rows": 5}

    # ------------------------------------------------------------------
    # Redis-disabled fallback
    # ------------------------------------------------------------------

    def test_redis_disabled_fallback_does_not_raise(self):
        """With REDIS_ENABLED=false, ProcessLevelCache and MemoryTTLCache work without exception."""
        import pandas as pd

        with patch(
            "mes_dashboard.core.redis_client.REDIS_ENABLED", False
        ):
            # ProcessLevelCache is entirely in-process — should be unaffected
            cache = ProcessLevelCache(ttl_seconds=30, max_size=4)
            cache.set("safe", pd.DataFrame({"c": [1]}))
            result = cache.get("safe")
            assert result is not None

            # MemoryTTLCache also in-process
            ttl_cache = MemoryTTLCache(max_size=8)
            ttl_cache.set("safe2", "value", ttl=30)
            assert ttl_cache.get("safe2") == "value"

    def test_redis_json_cache_returns_none_when_redis_disabled(self):
        """RedisJSONCache.get() returns None gracefully when Redis is disabled."""
        from mes_dashboard.core.cache import RedisJSONCache

        with patch("mes_dashboard.core.cache.REDIS_ENABLED", False):
            rc = RedisJSONCache(namespace="test_ns")
            result = rc.get("any_key")
            assert result is None

        with patch("mes_dashboard.core.cache.REDIS_ENABLED", False):
            rc = RedisJSONCache(namespace="test_ns")
            # set should not raise either
            rc.set("any_key", {"foo": "bar"}, ttl=60)

    def test_real_redis_cache_miss_then_hit(self):
        """Using real Redis: set key, expire it, refill, confirm hit (skip if unavailable)."""
        if not redis_available():
            pytest.skip("Redis not available")

        from mes_dashboard.core.redis_client import get_redis_client, get_key

        client = get_redis_client()
        test_key = get_key("test:integration:miss_refill")
        client.delete(test_key)

        # Miss
        assert client.get(test_key) is None

        # Refill
        client.setex(test_key, 30, '{"value": "hello"}')

        # Hit
        raw = client.get(test_key)
        assert raw is not None
        import json
        payload = json.loads(raw)
        assert payload["value"] == "hello"

        # Cleanup
        client.delete(test_key)
