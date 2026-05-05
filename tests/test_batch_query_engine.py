# -*- coding: utf-8 -*-
"""Unit tests for BatchQueryEngine module."""

import json
from pathlib import Path
import pytest
from unittest.mock import patch, MagicMock

import pandas as pd

from mes_dashboard.services.batch_query_engine import (
    MergeChunksMaxRowsExceeded,
    compute_query_hash,
    decompose_by_ids,
    decompose_by_time_range,
    execute_plan,
    merge_chunks,
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

    def test_merge_raises_when_overflow_mode_error(self):
        import mes_dashboard.core.redis_df_store as rds

        mock_client = MagicMock()
        stored = {}
        mock_client.setex.side_effect = lambda k, t, v: stored.update({k: v})
        mock_client.get.side_effect = lambda k: stored.get(k)
        mock_client.hgetall.return_value = {"total": "2", "completed": "2", "failed": "0"}
        mock_client.exists.side_effect = lambda k: 1 if k in stored else 0

        with patch.object(rds, "REDIS_ENABLED", True), \
             patch.object(rds, "get_redis_client", return_value=mock_client):
            rds.redis_store_chunk("t", "strict", 0, pd.DataFrame({"A": [1, 2]}))
            rds.redis_store_chunk("t", "strict", 1, pd.DataFrame({"A": [3, 4]}))

        import mes_dashboard.services.batch_query_engine as bqe

        with patch.object(rds, "REDIS_ENABLED", True), \
             patch.object(rds, "get_redis_client", return_value=mock_client), \
             patch.object(bqe, "get_redis_client", return_value=mock_client):
            with pytest.raises(MergeChunksMaxRowsExceeded):
                merge_chunks(
                    "t",
                    "strict",
                    max_total_rows=3,
                    overflow_mode="error",
                )

    def test_merge_raises_when_cap_already_reached_and_next_chunk_exists(self):
        import mes_dashboard.core.redis_df_store as rds

        mock_client = MagicMock()
        stored = {}
        mock_client.setex.side_effect = lambda k, t, v: stored.update({k: v})
        mock_client.get.side_effect = lambda k: stored.get(k)
        mock_client.hgetall.return_value = {"total": "3", "completed": "3", "failed": "0"}
        mock_client.exists.side_effect = lambda k: 1 if k in stored else 0

        with patch.object(rds, "REDIS_ENABLED", True), \
             patch.object(rds, "get_redis_client", return_value=mock_client):
            rds.redis_store_chunk("t", "strict_cap", 0, pd.DataFrame({"A": [1, 2]}))
            rds.redis_store_chunk("t", "strict_cap", 1, pd.DataFrame({"A": [3]}))
            rds.redis_store_chunk("t", "strict_cap", 2, pd.DataFrame({"A": [4]}))

        import mes_dashboard.services.batch_query_engine as bqe

        with patch.object(rds, "REDIS_ENABLED", True), \
             patch.object(rds, "get_redis_client", return_value=mock_client), \
             patch.object(bqe, "get_redis_client", return_value=mock_client):
            with pytest.raises(MergeChunksMaxRowsExceeded):
                merge_chunks(
                    "t",
                    "strict_cap",
                    max_total_rows=3,
                    overflow_mode="error",
                )


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

        # One chunk retried once due retryable timeout pattern.
        assert call_count["n"] == 4
        # Final metadata should reflect partial failure
        last = hset_calls[-1]
        assert last["status"] == "partial"
        assert last["completed"] == "2"
        assert last["failed"] == "1"
        assert last["has_partial_failure"] == "True"
        assert last["failed_chunk_count"] == "1"

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
        assert not should_decompose_by_time("2025-01-01", "2025-01-11")

    def test_large_ids_true(self):
        assert should_decompose_by_ids(list(range(2000)))

    def test_small_ids_false(self):
        assert not should_decompose_by_ids(list(range(500)))


class TestRetryAndFailedRanges:
    def _mock_redis(self):
        mock_client = MagicMock()
        stored = {}
        hashes = {}

        mock_client.setex.side_effect = lambda k, t, v: stored.update({k: v})
        mock_client.get.side_effect = lambda k: stored.get(k)
        mock_client.exists.side_effect = lambda k: 1 if k in stored else 0
        mock_client.hset.side_effect = lambda k, mapping=None: hashes.setdefault(k, {}).update(mapping or {})
        mock_client.hgetall.side_effect = lambda k: hashes.get(k, {})
        mock_client.expire.return_value = None
        return mock_client

    def test_transient_failure_retried_once(self):
        import mes_dashboard.core.redis_df_store as rds
        import mes_dashboard.services.batch_query_engine as bqe

        mock_client = self._mock_redis()
        call_count = {"n": 0}

        def flaky_query_fn(chunk, max_rows_per_chunk=None):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise TimeoutError("connection timed out")
            return pd.DataFrame({"V": [1]})

        with patch.object(rds, "REDIS_ENABLED", True), \
             patch.object(rds, "get_redis_client", return_value=mock_client), \
             patch.object(bqe, "get_redis_client", return_value=mock_client):
            execute_plan(
                [{"chunk_start": "2025-01-01", "chunk_end": "2025-01-10"}],
                flaky_query_fn,
                query_hash="retryonce",
                cache_prefix="retry",
                skip_cached=False,
            )
            progress = bqe.get_batch_progress("retry", "retryonce")

        assert call_count["n"] == 2
        assert progress is not None
        assert progress.get("status") == "completed"
        assert progress.get("failed") == "0"

    def test_memory_guard_not_retried(self):
        import mes_dashboard.core.redis_df_store as rds
        import mes_dashboard.services.batch_query_engine as bqe

        mock_client = self._mock_redis()
        call_count = {"n": 0}

        def large_df_query_fn(chunk, max_rows_per_chunk=None):
            call_count["n"] += 1
            return pd.DataFrame({"V": [1]})

        with patch.object(rds, "REDIS_ENABLED", True), \
             patch.object(rds, "get_redis_client", return_value=mock_client), \
             patch.object(bqe, "get_redis_client", return_value=mock_client), \
             patch.object(bqe, "BATCH_CHUNK_MAX_MEMORY_MB", 0):
            execute_plan(
                [{"chunk_start": "2025-01-01", "chunk_end": "2025-01-10"}],
                large_df_query_fn,
                query_hash="memnoretry",
                cache_prefix="retry",
                skip_cached=False,
            )

        assert call_count["n"] == 1

    def test_failed_ranges_tracked(self):
        import mes_dashboard.core.redis_df_store as rds
        import mes_dashboard.services.batch_query_engine as bqe

        mock_client = self._mock_redis()

        def query_fn(chunk, max_rows_per_chunk=None):
            if chunk["chunk_start"] == "2025-01-11":
                raise RuntimeError("chunk failure")
            return pd.DataFrame({"V": [1]})

        chunks = [
            {"chunk_start": "2025-01-01", "chunk_end": "2025-01-10"},
            {"chunk_start": "2025-01-11", "chunk_end": "2025-01-20"},
            {"chunk_start": "2025-01-21", "chunk_end": "2025-01-30"},
        ]
        with patch.object(rds, "REDIS_ENABLED", True), \
             patch.object(rds, "get_redis_client", return_value=mock_client), \
             patch.object(bqe, "get_redis_client", return_value=mock_client):
            execute_plan(
                chunks,
                query_fn,
                query_hash="franges",
                cache_prefix="retry",
                skip_cached=False,
            )
            progress = bqe.get_batch_progress("retry", "franges")

        assert progress is not None
        assert progress.get("has_partial_failure") == "True"
        assert progress.get("failed") == "1"
        assert progress.get("failed_chunk_count") == "1"
        failed_ranges = json.loads(progress.get("failed_ranges", "[]"))
        assert failed_ranges == [{"start": "2025-01-11", "end": "2025-01-20"}]

    def test_id_batch_chunk_no_failed_ranges(self):
        import mes_dashboard.core.redis_df_store as rds
        import mes_dashboard.services.batch_query_engine as bqe

        mock_client = self._mock_redis()

        def query_fn(chunk, max_rows_per_chunk=None):
            if chunk.get("ids") == ["B"]:
                raise RuntimeError("id chunk failed")
            return pd.DataFrame({"V": [1]})

        chunks = [
            {"ids": ["A"]},
            {"ids": ["B"]},
        ]
        with patch.object(rds, "REDIS_ENABLED", True), \
             patch.object(rds, "get_redis_client", return_value=mock_client), \
             patch.object(bqe, "get_redis_client", return_value=mock_client):
            execute_plan(
                chunks,
                query_fn,
                query_hash="idfail",
                cache_prefix="retry",
                skip_cached=False,
            )
            progress = bqe.get_batch_progress("retry", "idfail")

        assert progress is not None
        assert progress.get("has_partial_failure") == "True"
        assert progress.get("failed") == "1"
        assert progress.get("failed_chunk_count") == "1"
        failed_ranges = json.loads(progress.get("failed_ranges", "[]"))
        assert failed_ranges == []

# ============================================================
# 6.1 merge_chunks_to_spool
# ============================================================


class TestMergeChunksToSpool:
    """Tests for the streaming spool merge path."""

    def test_normal_flow_writes_parquet_and_returns_path(self, tmp_path):
        """merge_chunks_to_spool writes parquet and returns (path, row_count)."""
        import mes_dashboard.services.batch_query_engine as bqe

        chunk1 = pd.DataFrame({"A": [1, 2, 3], "B": ["x", "y", "z"]})
        chunk2 = pd.DataFrame({"A": [4, 5], "B": ["a", "b"]})

        with patch.object(bqe, "iterate_chunks", return_value=iter([chunk1, chunk2])):
            spool_path, total_rows = bqe.merge_chunks_to_spool(
                "reject", "testhash", spool_dir=tmp_path
            )

        assert total_rows == 5
        assert spool_path is not None
        assert spool_path.exists()
        # Verify file is readable parquet
        result_df = pd.read_parquet(str(spool_path), engine="pyarrow")
        assert len(result_df) == 5
        assert list(result_df["A"]) == [1, 2, 3, 4, 5]

    def test_empty_result_returns_none_zero(self, tmp_path):
        """Empty chunks produce (None, 0) and no spool file."""
        import mes_dashboard.services.batch_query_engine as bqe

        with patch.object(bqe, "iterate_chunks", return_value=iter([])):
            spool_path, total_rows = bqe.merge_chunks_to_spool(
                "reject", "emptyhash", spool_dir=tmp_path
            )

        assert spool_path is None
        assert total_rows == 0
        # No stray parquet files
        assert not list(tmp_path.glob("*.parquet"))

    def test_overflow_error_raises_and_cleans_up(self, tmp_path):
        """overflow_mode='error' raises MergeChunksMaxRowsExceeded and deletes partial file."""
        import mes_dashboard.services.batch_query_engine as bqe

        chunk1 = pd.DataFrame({"V": range(100)})
        chunk2 = pd.DataFrame({"V": range(100)})

        with patch.object(bqe, "iterate_chunks", return_value=iter([chunk1, chunk2])):
            with pytest.raises(bqe.MergeChunksMaxRowsExceeded):
                bqe.merge_chunks_to_spool(
                    "reject",
                    "overhash",
                    spool_dir=tmp_path,
                    max_total_rows=150,
                    overflow_mode="error",
                )

        # Partial spool file must be cleaned up
        assert not list(tmp_path.glob("*overhash*.parquet"))

    def test_exception_deletes_partial_file(self, tmp_path):
        """Any unexpected exception cleans up the partial spool file."""
        import mes_dashboard.services.batch_query_engine as bqe

        def _bad_chunks(*_a, **_kw):
            yield pd.DataFrame({"V": [1, 2]})
            raise RuntimeError("simulated IO error")

        with patch.object(bqe, "iterate_chunks", side_effect=_bad_chunks):
            with pytest.raises(RuntimeError, match="simulated IO error"):
                bqe.merge_chunks_to_spool(
                    "reject", "badhash", spool_dir=tmp_path
                )

        assert not list(tmp_path.glob("*badhash*.parquet"))

    def test_precreates_temp_file_before_parquet_writer(self, tmp_path, monkeypatch):
        """The temp spool file must exist before PyArrow opens it."""
        import pyarrow.parquet as pq
        import mes_dashboard.services.batch_query_engine as bqe

        chunk = pd.DataFrame({"A": [1], "B": ["x"]})

        class FakeWriter:
            def __init__(self, path, schema):  # noqa: ANN001
                self.path = Path(path)
                assert self.path.exists()

            def write_table(self, table):  # noqa: ANN001
                return None

            def close(self):
                return None

        monkeypatch.setattr(pq, "ParquetWriter", FakeWriter)

        with patch.object(bqe, "iterate_chunks", return_value=iter([chunk])):
            spool_path, total_rows = bqe.merge_chunks_to_spool(
                "reject",
                "precreate",
                spool_dir=tmp_path,
            )

        assert total_rows == 1
        assert spool_path is not None
        assert spool_path.exists()

    def test_merge_chunks_to_spool_survives_cleanup_race(self, tmp_path, monkeypatch):
        """Shared spool writer must keep its target alive across cleanup passes."""
        import pyarrow.parquet as pq
        import mes_dashboard.services.batch_query_engine as bqe
        from mes_dashboard.core import query_spool_store as spool_store

        chunk = pd.DataFrame({"A": [1], "B": ["x"]})
        spool_dir = tmp_path / "reject"

        class FakeWriter:
            def __init__(self, path, schema):  # noqa: ANN001
                spool_store.cleanup_expired_spool(namespace=None)
                self.path = Path(path)
                assert self.path.exists()

            def write_table(self, table):  # noqa: ANN001
                return None

            def close(self):
                return None

        monkeypatch.setattr(spool_store, "QUERY_SPOOL_DIR", tmp_path)
        monkeypatch.setattr(pq, "ParquetWriter", FakeWriter)

        with patch.object(bqe, "iterate_chunks", return_value=iter([chunk])):
            spool_path, total_rows = bqe.merge_chunks_to_spool(
                "reject",
                "race-safe",
                spool_dir=spool_dir,
            )

        assert total_rows == 1
        assert spool_path is not None
        assert spool_path.exists()
        assert spool_path.parent == spool_dir

    def test_null_typed_column_in_first_chunk_succeeds(self, tmp_path):
        """Chunk 1 has all-None optional column (null type); chunk 2 has real strings.

        This reproduces the production crash in get_jobs_by_resources where
        columns like CAUSECODENAME are all-NULL in the first time-slice but
        carry real strings in a later slice.  PyArrow infers the column as
        ``null`` type from chunk 1; previously, casting ``string → null`` in
        chunk 2 raised ArrowNotImplementedError.
        """
        import mes_dashboard.services.batch_query_engine as bqe

        # Chunk 1: CAUSECODENAME is entirely None (all jobs undiagnosed)
        chunk1 = pd.DataFrame({
            "JOBID": ["J001", "J002"],
            "RESOURCENAME": ["EQP-A", "EQP-B"],
            "CAUSECODENAME": [None, None],       # all-null → PyArrow infers null type
            "REPAIRCODENAME": [None, None],       # same
        })
        # Chunk 2: CAUSECODENAME now has real string values
        chunk2 = pd.DataFrame({
            "JOBID": ["J003", "J004"],
            "RESOURCENAME": ["EQP-A", "EQP-C"],
            "CAUSECODENAME": ["電源異常", "機械故障"],  # real strings
            "REPAIRCODENAME": [None, "更換零件"],
        })

        with patch.object(bqe, "iterate_chunks", return_value=iter([chunk1, chunk2])):
            spool_path, total_rows = bqe.merge_chunks_to_spool(
                "job", "null-promo-test", spool_dir=tmp_path
            )

        assert total_rows == 4
        assert spool_path is not None and spool_path.exists()

        result = pd.read_parquet(str(spool_path), engine="pyarrow")
        assert len(result) == 4
        assert list(result["JOBID"]) == ["J001", "J002", "J003", "J004"]
        # Rows from chunk 1 keep their nulls; chunk 2 has real values
        assert pd.isna(result.loc[0, "CAUSECODENAME"])
        assert result.loc[2, "CAUSECODENAME"] == "電源異常"
        assert result.loc[3, "REPAIRCODENAME"] == "更換零件"

    def test_null_typed_column_all_chunks_null_still_works(self, tmp_path):
        """All chunks have null-typed optional column — should produce valid parquet."""
        import mes_dashboard.services.batch_query_engine as bqe

        chunk1 = pd.DataFrame({"JOBID": ["J001"], "CAUSECODENAME": [None]})
        chunk2 = pd.DataFrame({"JOBID": ["J002"], "CAUSECODENAME": [None]})

        with patch.object(bqe, "iterate_chunks", return_value=iter([chunk1, chunk2])):
            spool_path, total_rows = bqe.merge_chunks_to_spool(
                "job", "all-null-test", spool_dir=tmp_path
            )

        assert total_rows == 2
        result = pd.read_parquet(str(spool_path), engine="pyarrow")
        assert len(result) == 2
        assert pd.isna(result.loc[0, "CAUSECODENAME"])
        assert pd.isna(result.loc[1, "CAUSECODENAME"])

    def test_promote_null_schema_helper(self):
        """_promote_null_schema replaces null-typed fields with large_string."""
        import pyarrow as pa
        import mes_dashboard.services.batch_query_engine as bqe

        schema = pa.schema([
            pa.field("ID", pa.int64()),
            pa.field("NAME", pa.large_string()),
            pa.field("OPT_CODE", pa.null()),      # null-typed optional column
            pa.field("OPT_COMMENT", pa.null()),   # another null-typed column
        ])
        promoted = bqe._promote_null_schema(schema)

        assert promoted.field("ID").type == pa.int64()            # unchanged
        assert promoted.field("NAME").type == pa.large_string()   # unchanged
        assert promoted.field("OPT_CODE").type == pa.large_string()    # promoted
        assert promoted.field("OPT_COMMENT").type == pa.large_string() # promoted

    def test_promote_null_schema_noop_when_no_nulls(self):
        """_promote_null_schema returns the same object when no null-typed fields."""
        import pyarrow as pa
        import mes_dashboard.services.batch_query_engine as bqe

        schema = pa.schema([
            pa.field("ID", pa.int64()),
            pa.field("NAME", pa.large_string()),
        ])
        result = bqe._promote_null_schema(schema)
        assert result is schema  # identity — no copy needed
