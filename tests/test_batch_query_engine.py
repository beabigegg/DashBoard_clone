# -*- coding: utf-8 -*-
"""Unit tests for BatchQueryEngine module."""

import pytest
from unittest.mock import patch, MagicMock, call

import pandas as pd

from mes_dashboard.services.batch_query_engine import (
    compute_query_hash,
    decompose_by_ids,
    decompose_by_time_range,
    execute_plan,
    merge_chunks,
    iterate_chunks,
    should_decompose_by_time,
    should_decompose_by_ids,
)


# ============================================================
# 4.1 decompose_by_time_range
# ============================================================


class TestDecomposeByTimeRange:
    def test_90_days_yields_3_chunks(self):
        chunks = decompose_by_time_range("2025-01-01", "2025-03-31", grain_days=31)
        assert len(chunks) == 3
        # First chunk: Jan 1 – Jan 31
        assert chunks[0] == {"chunk_start": "2025-01-01", "chunk_end": "2025-01-31"}
        # Second chunk: Feb 1 – Mar 3
        assert chunks[1]["chunk_start"] == "2025-02-01"
        # Third chunk ends Mar 31
        assert chunks[2]["chunk_end"] == "2025-03-31"

    def test_31_days_yields_1_chunk(self):
        chunks = decompose_by_time_range("2025-01-01", "2025-01-31", grain_days=31)
        assert len(chunks) == 1
        assert chunks[0] == {"chunk_start": "2025-01-01", "chunk_end": "2025-01-31"}

    def test_single_day(self):
        chunks = decompose_by_time_range("2025-06-15", "2025-06-15")
        assert len(chunks) == 1
        assert chunks[0] == {"chunk_start": "2025-06-15", "chunk_end": "2025-06-15"}

    def test_contiguous_no_overlap_no_gap(self):
        """Verify closed-interval boundary semantics: no overlap, no gap."""
        chunks = decompose_by_time_range("2025-01-01", "2025-06-30", grain_days=31)
        for i in range(1, len(chunks)):
            prev_end = chunks[i - 1]["chunk_end"]
            cur_start = chunks[i]["chunk_start"]
            from datetime import datetime, timedelta
            prev_dt = datetime.strptime(prev_end, "%Y-%m-%d")
            cur_dt = datetime.strptime(cur_start, "%Y-%m-%d")
            assert cur_dt == prev_dt + timedelta(days=1), (
                f"Gap/overlap between chunk {i-1} end={prev_end} and chunk {i} start={cur_start}"
            )
        # First starts at start_date, last ends at end_date
        assert chunks[0]["chunk_start"] == "2025-01-01"
        assert chunks[-1]["chunk_end"] == "2025-06-30"

    def test_final_chunk_may_be_shorter(self):
        chunks = decompose_by_time_range("2025-01-01", "2025-02-10", grain_days=31)
        assert len(chunks) == 2
        # Second chunk: Feb 1 – Feb 10 (10 days < 31)
        assert chunks[1] == {"chunk_start": "2025-02-01", "chunk_end": "2025-02-10"}

    def test_inverted_range_raises(self):
        with pytest.raises(ValueError, match="must be <="):
            decompose_by_time_range("2025-12-31", "2025-01-01")

    def test_365_days(self):
        chunks = decompose_by_time_range("2025-01-01", "2025-12-31", grain_days=31)
        assert len(chunks) == 12  # roughly 365/31 ≈ 12


# ============================================================
# 4.2 decompose_by_ids
# ============================================================


class TestDecomposeByIds:
    def test_2500_ids_yields_3_batches(self):
        ids = list(range(2500))
        batches = decompose_by_ids(ids, batch_size=1000)
        assert len(batches) == 3
        assert len(batches[0]) == 1000
        assert len(batches[1]) == 1000
        assert len(batches[2]) == 500

    def test_500_ids_yields_1_batch(self):
        ids = list(range(500))
        batches = decompose_by_ids(ids, batch_size=1000)
        assert len(batches) == 1
        assert len(batches[0]) == 500

    def test_empty_ids(self):
        assert decompose_by_ids([]) == []

    def test_exact_batch_size(self):
        ids = list(range(1000))
        batches = decompose_by_ids(ids, batch_size=1000)
        assert len(batches) == 1


# ============================================================
# 4.3 execute_plan sequential
# ============================================================


class TestExecutePlanSequential:
    def _mock_redis(self):
        """Set up mock redis for chunk store/load/exists."""
        stored = {}
        mock_client = MagicMock()
        mock_client.setex.side_effect = lambda k, t, v: stored.update({k: v})
        mock_client.get.side_effect = lambda k: stored.get(k)
        mock_client.exists.side_effect = lambda k: 1 if k in stored else 0
        mock_client.hset.return_value = None
        mock_client.expire.return_value = None
        return mock_client, stored

    def test_sequential_execution_stores_chunks(self):
        import mes_dashboard.core.redis_df_store as rds
        import mes_dashboard.services.batch_query_engine as bqe

        mock_client, stored = self._mock_redis()

        call_log = []

        def fake_query_fn(chunk, max_rows_per_chunk=None):
            call_log.append(chunk)
            return pd.DataFrame({"V": [1, 2]})

        chunks = [
            {"chunk_start": "2025-01-01", "chunk_end": "2025-01-31"},
            {"chunk_start": "2025-02-01", "chunk_end": "2025-02-28"},
        ]

        with patch.object(rds, "REDIS_ENABLED", True), \
             patch.object(rds, "get_redis_client", return_value=mock_client), \
             patch.object(bqe, "get_redis_client", return_value=mock_client):
            qh = execute_plan(
                chunks, fake_query_fn,
                query_hash="testhash",
                cache_prefix="test",
                skip_cached=False,
            )

        assert qh == "testhash"
        assert len(call_log) == 2
        # Chunks should be stored in Redis
        assert any("chunk:0" in k for k in stored)
        assert any("chunk:1" in k for k in stored)


# ============================================================
# 4.4 execute_plan parallel
# ============================================================


class TestExecutePlanParallel:
    def test_parallel_uses_threadpool(self):
        import mes_dashboard.core.redis_df_store as rds
        import mes_dashboard.services.batch_query_engine as bqe

        mock_client = MagicMock()
        stored = {}
        mock_client.setex.side_effect = lambda k, t, v: stored.update({k: v})
        mock_client.get.side_effect = lambda k: stored.get(k)
        mock_client.exists.side_effect = lambda k: 1 if k in stored else 0
        mock_client.hset.return_value = None
        mock_client.expire.return_value = None

        call_count = {"n": 0}

        def fake_query_fn(chunk, max_rows_per_chunk=None):
            call_count["n"] += 1
            return pd.DataFrame({"V": [1]})

        chunks = [{"i": i} for i in range(4)]

        with patch.object(rds, "REDIS_ENABLED", True), \
             patch.object(rds, "get_redis_client", return_value=mock_client), \
             patch.object(bqe, "get_redis_client", return_value=mock_client), \
             patch.object(bqe, "_effective_parallelism", return_value=2):
            qh = execute_plan(
                chunks, fake_query_fn,
                parallel=2,
                query_hash="ptest",
                cache_prefix="p",
                skip_cached=False,
            )

        assert call_count["n"] == 4


# ============================================================
# 4.5 partial cache hit
# ============================================================


class TestPartialCacheHit:
    def test_skips_cached_chunks(self):
        import mes_dashboard.core.redis_df_store as rds
        import mes_dashboard.services.batch_query_engine as bqe

        mock_client = MagicMock()
        stored = {}
        mock_client.setex.side_effect = lambda k, t, v: stored.update({k: v})
        mock_client.get.side_effect = lambda k: stored.get(k)
        mock_client.hset.return_value = None
        mock_client.expire.return_value = None

        # Pre-populate chunks 0 and 1 as "cached"
        pre_cached_keys = set()

        def fake_exists(k):
            return 1 if k in pre_cached_keys else (1 if k in stored else 0)

        mock_client.exists.side_effect = fake_exists

        with patch.object(rds, "REDIS_ENABLED", True), \
             patch.object(rds, "get_redis_client", return_value=mock_client), \
             patch.object(bqe, "get_redis_client", return_value=mock_client):
            # Pre-store 2 chunks
            rds.redis_store_chunk("test", "hash5", 0, pd.DataFrame({"A": [1]}), ttl=60)
            rds.redis_store_chunk("test", "hash5", 1, pd.DataFrame({"A": [2]}), ttl=60)

        # Now mark those keys as existing
        pre_cached_keys.update(stored.keys())

        call_log = []

        def fake_query_fn(chunk, max_rows_per_chunk=None):
            call_log.append(chunk)
            return pd.DataFrame({"A": [99]})

        chunks = [{"i": i} for i in range(5)]

        with patch.object(rds, "REDIS_ENABLED", True), \
             patch.object(rds, "get_redis_client", return_value=mock_client), \
             patch.object(bqe, "get_redis_client", return_value=mock_client):
            execute_plan(
                chunks, fake_query_fn,
                query_hash="hash5",
                cache_prefix="test",
                skip_cached=True,
            )

        # Only chunks 2, 3, 4 should have been executed
        assert len(call_log) == 3


# ============================================================
# 4.6 memory guard
# ============================================================


class TestMemoryGuard:
    def test_oversized_chunk_discarded(self):
        import mes_dashboard.core.redis_df_store as rds
        import mes_dashboard.services.batch_query_engine as bqe

        mock_client = MagicMock()
        stored = {}
        mock_client.setex.side_effect = lambda k, t, v: stored.update({k: v})
        mock_client.get.side_effect = lambda k: stored.get(k)
        mock_client.exists.side_effect = lambda k: 1 if k in stored else 0
        mock_client.hset.return_value = None
        mock_client.expire.return_value = None

        def oversized_query_fn(chunk, max_rows_per_chunk=None):
            # Create DF that reports large memory
            df = pd.DataFrame({"X": [1]})
            return df

        chunks = [{"i": 0}]

        # Set memory limit to 0 MB so any DF exceeds it
        with patch.object(rds, "REDIS_ENABLED", True), \
             patch.object(rds, "get_redis_client", return_value=mock_client), \
             patch.object(bqe, "get_redis_client", return_value=mock_client), \
             patch.object(bqe, "BATCH_CHUNK_MAX_MEMORY_MB", 0):
            qh = execute_plan(
                chunks, oversized_query_fn,
                query_hash="memtest",
                cache_prefix="m",
                skip_cached=False,
            )

        # Chunk should NOT be stored (memory exceeded)
        assert not any("chunk:0" in k for k in stored)


# ============================================================
# 4.7 result row count limit
# ============================================================


class TestMaxRowsPerChunk:
    def test_max_rows_passed_to_query_fn(self):
        import mes_dashboard.core.redis_df_store as rds
        import mes_dashboard.services.batch_query_engine as bqe

        mock_client = MagicMock()
        mock_client.setex.return_value = None
        mock_client.get.return_value = None
        mock_client.exists.return_value = 0
        mock_client.hset.return_value = None
        mock_client.expire.return_value = None

        received_max_rows = []

        def capture_query_fn(chunk, max_rows_per_chunk=None):
            received_max_rows.append(max_rows_per_chunk)
            return pd.DataFrame({"V": [1]})

        with patch.object(rds, "REDIS_ENABLED", True), \
             patch.object(rds, "get_redis_client", return_value=mock_client), \
             patch.object(bqe, "get_redis_client", return_value=mock_client):
            execute_plan(
                [{"i": 0}], capture_query_fn,
                query_hash="rowtest",
                cache_prefix="r",
                max_rows_per_chunk=5000,
                skip_cached=False,
            )

        assert received_max_rows == [5000]


# ============================================================
# 4.8 merge_chunks
# ============================================================


class TestMergeChunks:
    def test_merge_produces_correct_df(self):
        import mes_dashboard.core.redis_df_store as rds

        mock_client = MagicMock()
        stored = {}
        mock_client.setex.side_effect = lambda k, t, v: stored.update({k: v})
        mock_client.get.side_effect = lambda k: stored.get(k)
        mock_client.hgetall.return_value = {"total": "3", "completed": "3", "failed": "0"}
        mock_client.exists.side_effect = lambda k: 1 if k in stored else 0

        with patch.object(rds, "REDIS_ENABLED", True), \
             patch.object(rds, "get_redis_client", return_value=mock_client):
            rds.redis_store_chunk("t", "h", 0, pd.DataFrame({"A": [1, 2]}))
            rds.redis_store_chunk("t", "h", 1, pd.DataFrame({"A": [3, 4]}))
            rds.redis_store_chunk("t", "h", 2, pd.DataFrame({"A": [5]}))

        import mes_dashboard.services.batch_query_engine as bqe

        with patch.object(rds, "REDIS_ENABLED", True), \
             patch.object(rds, "get_redis_client", return_value=mock_client), \
             patch.object(bqe, "get_redis_client", return_value=mock_client):
            merged = merge_chunks("t", "h")

        assert len(merged) == 5
        assert list(merged["A"]) == [1, 2, 3, 4, 5]

    def test_merge_respects_max_total_rows(self):
        import mes_dashboard.core.redis_df_store as rds

        mock_client = MagicMock()
        stored = {}
        mock_client.setex.side_effect = lambda k, t, v: stored.update({k: v})
        mock_client.get.side_effect = lambda k: stored.get(k)
        mock_client.hgetall.return_value = {"total": "3", "completed": "3", "failed": "0"}
        mock_client.exists.side_effect = lambda k: 1 if k in stored else 0

        with patch.object(rds, "REDIS_ENABLED", True), \
             patch.object(rds, "get_redis_client", return_value=mock_client):
            rds.redis_store_chunk("t", "cap", 0, pd.DataFrame({"A": [1, 2]}))
            rds.redis_store_chunk("t", "cap", 1, pd.DataFrame({"A": [3, 4]}))
            rds.redis_store_chunk("t", "cap", 2, pd.DataFrame({"A": [5, 6]}))

        import mes_dashboard.services.batch_query_engine as bqe

        with patch.object(rds, "REDIS_ENABLED", True), \
             patch.object(rds, "get_redis_client", return_value=mock_client), \
             patch.object(bqe, "get_redis_client", return_value=mock_client):
            merged = merge_chunks("t", "cap", max_total_rows=4)

        assert len(merged) == 4
        assert list(merged["A"]) == [1, 2, 3, 4]


# ============================================================
# 4.9 progress tracking
# ============================================================


class TestProgressTracking:
    def test_hset_updated_after_each_chunk(self):
        import mes_dashboard.core.redis_df_store as rds
        import mes_dashboard.services.batch_query_engine as bqe

        mock_client = MagicMock()
        mock_client.setex.return_value = None
        mock_client.get.return_value = None
        mock_client.exists.return_value = 0
        mock_client.hset.return_value = None
        mock_client.expire.return_value = None

        hset_calls = []
        original_hset = mock_client.hset

        def track_hset(key, mapping=None):
            hset_calls.append(mapping.copy() if mapping else {})
            return original_hset(key, mapping=mapping)

        mock_client.hset.side_effect = track_hset

        def fake_query_fn(chunk, max_rows_per_chunk=None):
            return pd.DataFrame({"V": [1]})

        chunks = [{"i": 0}, {"i": 1}, {"i": 2}]

        with patch.object(rds, "REDIS_ENABLED", True), \
             patch.object(rds, "get_redis_client", return_value=mock_client), \
             patch.object(bqe, "get_redis_client", return_value=mock_client):
            execute_plan(
                chunks, fake_query_fn,
                query_hash="progtest",
                cache_prefix="p",
                skip_cached=False,
            )

        # Should have initial + 3 per-chunk + final = 5 hset calls
        assert len(hset_calls) >= 4
        # Last call should show completed status
        last = hset_calls[-1]
        assert last["status"] == "completed"
        assert last["completed"] == "3"


# ============================================================
# 4.10 chunk failure resilience
# ============================================================


class TestChunkFailureResilience:
    def test_one_chunk_fails_others_complete(self):
        import mes_dashboard.core.redis_df_store as rds
        import mes_dashboard.services.batch_query_engine as bqe

        mock_client = MagicMock()
        stored = {}
        mock_client.setex.side_effect = lambda k, t, v: stored.update({k: v})
        mock_client.get.side_effect = lambda k: stored.get(k)
        mock_client.exists.side_effect = lambda k: 1 if k in stored else 0
        mock_client.hset.return_value = None
        mock_client.expire.return_value = None

        call_count = {"n": 0}

        def failing_query_fn(chunk, max_rows_per_chunk=None):
            call_count["n"] += 1
            if chunk.get("i") == 1:
                raise RuntimeError("Oracle timeout")
            return pd.DataFrame({"V": [chunk["i"]]})

        chunks = [{"i": 0}, {"i": 1}, {"i": 2}]

        hset_calls = []
        mock_client.hset.side_effect = lambda k, mapping=None: hset_calls.append(
            mapping.copy() if mapping else {}
        )

        with patch.object(rds, "REDIS_ENABLED", True), \
             patch.object(rds, "get_redis_client", return_value=mock_client), \
             patch.object(bqe, "get_redis_client", return_value=mock_client):
            qh = execute_plan(
                chunks, failing_query_fn,
                query_hash="failtest",
                cache_prefix="f",
                skip_cached=False,
            )

        # All 3 chunks attempted
        assert call_count["n"] == 3
        # Final metadata should reflect partial failure
        last = hset_calls[-1]
        assert last["status"] == "partial"
        assert last["completed"] == "2"
        assert last["failed"] == "1"
        assert last["has_partial_failure"] == "True"

    def test_chunk_store_failure_is_marked_partial(self):
        import mes_dashboard.core.redis_df_store as rds
        import mes_dashboard.services.batch_query_engine as bqe

        mock_client = MagicMock()
        stored = {}
        mock_client.setex.side_effect = lambda k, t, v: stored.update({k: v})
        mock_client.get.side_effect = lambda k: stored.get(k)
        mock_client.exists.side_effect = lambda k: 1 if k in stored else 0
        mock_client.hset.return_value = None
        mock_client.expire.return_value = None

        def query_fn(chunk, max_rows_per_chunk=None):
            return pd.DataFrame({"V": [chunk["i"]]})

        original_store_chunk = bqe.redis_store_chunk

        def fail_one_store(prefix, query_hash, idx, df, ttl=900):
            if idx == 1:
                return False
            return original_store_chunk(prefix, query_hash, idx, df, ttl=ttl)

        hset_calls = []
        mock_client.hset.side_effect = lambda k, mapping=None: hset_calls.append(
            mapping.copy() if mapping else {}
        )

        with patch.object(rds, "REDIS_ENABLED", True), \
             patch.object(rds, "get_redis_client", return_value=mock_client), \
             patch.object(bqe, "get_redis_client", return_value=mock_client), \
             patch.object(bqe, "redis_store_chunk", side_effect=fail_one_store):
            execute_plan(
                [{"i": 0}, {"i": 1}, {"i": 2}],
                query_fn,
                query_hash="storefail",
                cache_prefix="sf",
                skip_cached=False,
            )

        last = hset_calls[-1]
        assert last["status"] == "partial"
        assert last["completed"] == "2"
        assert last["failed"] == "1"


# ============================================================
# query_hash stability
# ============================================================


class TestQueryHash:
    def test_same_params_different_order(self):
        h1 = compute_query_hash({"a": 1, "b": [3, 1, 2]})
        h2 = compute_query_hash({"b": [2, 1, 3], "a": 1})
        assert h1 == h2

    def test_different_params_different_hash(self):
        h1 = compute_query_hash({"mode": "date_range", "start": "2025-01-01"})
        h2 = compute_query_hash({"mode": "date_range", "start": "2025-06-01"})
        assert h1 != h2

    def test_hash_is_16_chars(self):
        h = compute_query_hash({"x": 1})
        assert len(h) == 16


# ============================================================
# should_decompose helpers
# ============================================================


class TestShouldDecompose:
    def test_long_range_true(self):
        assert should_decompose_by_time("2025-01-01", "2025-12-31")

    def test_short_range_false(self):
        assert not should_decompose_by_time("2025-01-01", "2025-02-01")

    def test_large_ids_true(self):
        assert should_decompose_by_ids(list(range(2000)))

    def test_small_ids_false(self):
        assert not should_decompose_by_ids(list(range(500)))
