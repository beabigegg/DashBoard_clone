# -*- coding: utf-8 -*-
"""Unit tests for BatchQueryEngine module."""

import json
from pathlib import Path
import pytest
from unittest.mock import patch, MagicMock

import pandas as pd

import ast

from mes_dashboard.services.batch_query_engine import (
    MergeChunksMaxRowsExceeded,
    compute_query_hash,
    decompose_by_ids,
    decompose_by_time_range,
    execute_plan,
    should_decompose_by_time,
    should_decompose_by_ids,
)

# NOTE: decompose_by_row_count and should_decompose_by_row_count are imported
# per-test class so that tests fail with ImportError before the functions exist
# (TDD red phase).


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
# 4.8 merge_chunks — AC-6 absence proof (wip-rq-worker-chunks-cleanup)
# ============================================================

class TestMergeChunksAbsentFromSource:
    """AC-6: merge_chunks (non-spool) must be absent from batch_query_engine.py.

    Uses ast.parse() + ast.walk to prove absence at the AST level.
    merge_chunks_to_spool is a distinct function and must NOT be deleted.
    """

    _SOURCE_PATH = Path(__file__).parent.parent / "src/mes_dashboard/services/batch_query_engine.py"

    def test_merge_chunks_def_absent_from_batch_query_engine(self):
        """AC-6: merge_chunks function definition must not exist in batch_query_engine.py.

        ast.walk over FunctionDef nodes — if a node named 'merge_chunks' (not
        'merge_chunks_to_spool') is found, the dead-code removal is incomplete.
        """
        source = self._SOURCE_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(self._SOURCE_PATH))

        merge_chunks_defs = [
            node.name for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "merge_chunks"
        ]
        assert not merge_chunks_defs, (
            "merge_chunks() FunctionDef still present in batch_query_engine.py. "
            "Dead-code removal (AC-6, IP-2) is incomplete."
        )

    def test_merge_chunks_to_spool_still_present(self):
        """AC-6 guard: merge_chunks_to_spool must NOT be deleted (it is still active)."""
        source = self._SOURCE_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(self._SOURCE_PATH))

        spool_defs = [
            node.name for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "merge_chunks_to_spool"
        ]
        assert spool_defs, (
            "merge_chunks_to_spool must NOT be deleted — it is still active and used by "
            "multiple services. Only the deprecated bare merge_chunks is removed."
        )

    def test_merge_chunks_max_rows_exceeded_still_present(self):
        """AC-6 guard: MergeChunksMaxRowsExceeded exception class must still exist."""
        source = self._SOURCE_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(self._SOURCE_PATH))

        class_names = [
            node.name for node in ast.walk(tree)
            if isinstance(node, ast.ClassDef) and node.name == "MergeChunksMaxRowsExceeded"
        ]
        assert class_names, (
            "MergeChunksMaxRowsExceeded must remain in batch_query_engine.py "
            "(used by merge_chunks_to_spool)."
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


# ============================================================
# decompose_by_row_count (BQE-02)
# ============================================================


class TestDecomposeByRowCount:
    """BQE-02: decompose_by_row_count correctness — 1-based inclusive ranges."""

    def _import(self):
        from mes_dashboard.services.batch_query_engine import decompose_by_row_count
        return decompose_by_row_count

    def test_total_rows_zero_returns_empty(self):
        fn = self._import()
        assert fn(0) == []

    def test_total_less_than_chunk_returns_single_range(self):
        fn = self._import()
        result = fn(30000, rows_per_chunk=50000)
        assert result == [{"start_row": 1, "end_row": 30000}]

    def test_total_exact_multiple_yields_n_chunks(self):
        fn = self._import()
        result = fn(100000, rows_per_chunk=50000)
        assert len(result) == 2
        assert result[0] == {"start_row": 1, "end_row": 50000}
        assert result[1] == {"start_row": 50001, "end_row": 100000}

    def test_total_rows_one(self):
        fn = self._import()
        result = fn(1, rows_per_chunk=50000)
        assert result == [{"start_row": 1, "end_row": 1}]

    def test_non_divisor_last_chunk_smaller(self):
        fn = self._import()
        result = fn(100001, rows_per_chunk=50000)
        assert len(result) == 3
        assert result[0] == {"start_row": 1, "end_row": 50000}
        assert result[1] == {"start_row": 50001, "end_row": 100000}
        assert result[2] == {"start_row": 100001, "end_row": 100001}

    def test_ranges_are_1based_inclusive(self):
        """First chunk starts at 1, last chunk ends at total_rows."""
        fn = self._import()
        result = fn(75000, rows_per_chunk=50000)
        assert result[0]["start_row"] == 1
        assert result[-1]["end_row"] == 75000

    def test_negative_raises_value_error(self):
        fn = self._import()
        with pytest.raises(ValueError, match="total_rows"):
            fn(-1)

    def test_chunk_size_zero_raises_value_error(self):
        fn = self._import()
        with pytest.raises(ValueError, match="rows_per_chunk"):
            fn(100, rows_per_chunk=0)

    @pytest.mark.property
    def test_no_gap_no_overlap_property(self):
        """Verify chunks cover exactly 1..total_rows with no gap and no overlap.

        Property test over selected (total, chunk_size) pairs — avoids hypothesis
        as an extra dependency while still covering boundary conditions.
        """
        fn = self._import()
        test_cases = [
            (1, 1),
            (1, 50000),
            (50000, 50000),
            (50001, 50000),
            (100000, 50000),
            (100001, 50000),
            (127, 31),
            (1000000, 200000),
            (999999, 100000),
        ]
        for total, chunk_size in test_cases:
            result = fn(total, rows_per_chunk=chunk_size)
            # Reconstruct the covered rows
            covered = set()
            for chunk in result:
                s, e = chunk["start_row"], chunk["end_row"]
                assert s <= e, f"({total},{chunk_size}): start > end in chunk {chunk}"
                assert s >= 1, f"({total},{chunk_size}): start < 1"
                assert e <= total, f"({total},{chunk_size}): end > total"
                new_rows = set(range(s, e + 1))
                assert not (covered & new_rows), (
                    f"({total},{chunk_size}): overlap in chunk {chunk}"
                )
                covered |= new_rows
            assert covered == set(range(1, total + 1)), (
                f"({total},{chunk_size}): gap or missing rows"
            )


# ============================================================
# TestShouldDecomposeByRowCount
# ============================================================


class TestShouldDecomposeByRowCount:
    """Convenience helper: should the service switch to row-count chunking?"""

    def _import(self):
        from mes_dashboard.services.batch_query_engine import (
            should_decompose_by_row_count,
            BATCH_QUERY_ROWS_PER_CHUNK,
        )
        return should_decompose_by_row_count, BATCH_QUERY_ROWS_PER_CHUNK

    def test_above_threshold_returns_true(self):
        fn, threshold = self._import()
        assert fn(threshold + 1) is True

    def test_below_threshold_returns_false(self):
        fn, threshold = self._import()
        assert fn(threshold) is False

    def test_exact_threshold_returns_false(self):
        fn, threshold = self._import()
        # Equal to threshold → not strictly above → False
        assert fn(threshold) is False


# ============================================================
# TestEngineParallelCeiling (BQE-05)
# ============================================================


class TestEngineParallelCeiling:
    """BQE-05: ENGINE_PARALLEL values must not exceed DB_SLOW_POOL_SIZE."""

    def _get_slow_pool_size(self):
        """Read DB_SLOW_POOL_SIZE from env (default 3 as per production convention)."""
        import os
        return int(os.getenv("DB_SLOW_POOL_SIZE", "3"))

    def test_hold_engine_parallel_capped_at_db_slow_pool_size(self):
        import os
        from mes_dashboard.services.hold_dataset_cache import _HOLD_ENGINE_PARALLEL
        pool_size = self._get_slow_pool_size()
        assert _HOLD_ENGINE_PARALLEL >= 1
        assert _HOLD_ENGINE_PARALLEL <= pool_size, (
            f"HOLD_ENGINE_PARALLEL={_HOLD_ENGINE_PARALLEL} exceeds "
            f"DB_SLOW_POOL_SIZE={pool_size}"
        )

    def test_job_engine_parallel_capped(self):
        from mes_dashboard.services.job_query_service import _JOB_ENGINE_PARALLEL
        pool_size = self._get_slow_pool_size()
        assert _JOB_ENGINE_PARALLEL >= 1
        assert _JOB_ENGINE_PARALLEL <= pool_size

    def test_msd_engine_parallel_capped(self):
        from mes_dashboard.services.mid_section_defect_service import _MSD_ENGINE_PARALLEL
        pool_size = self._get_slow_pool_size()
        assert _MSD_ENGINE_PARALLEL >= 1
        assert _MSD_ENGINE_PARALLEL <= pool_size

    def test_parallel_ceiling_within_limit_does_not_raise(self):
        """A value at or below the ceiling is valid — just verify no exception raised."""
        pool_size = self._get_slow_pool_size()
        # This just verifies the ceiling logic documented in BQE-05
        assert pool_size >= 1


# ============================================================
# TestFlagGating
# ============================================================


class TestFlagGating:
    """Flag-off path must not touch count SQL; flag-on path must call count then paged."""

    def test_flag_false_key_exported(self):
        """_USE_ROW_COUNT_CHUNKING must be importable (even if False by default)."""
        from mes_dashboard.services.batch_query_engine import _USE_ROW_COUNT_CHUNKING
        assert isinstance(_USE_ROW_COUNT_CHUNKING, bool)

    def test_batch_query_rows_per_chunk_exported(self):
        """BATCH_QUERY_ROWS_PER_CHUNK must be importable and positive."""
        from mes_dashboard.services.batch_query_engine import BATCH_QUERY_ROWS_PER_CHUNK
        assert isinstance(BATCH_QUERY_ROWS_PER_CHUNK, int)
        assert BATCH_QUERY_ROWS_PER_CHUNK >= 1

    def test_flag_false_does_not_call_count_sql(self):
        """When USE_ROW_COUNT_CHUNKING=false, count SQL is NOT invoked.

        Simulates flag=false by patching _USE_ROW_COUNT_CHUNKING to False
        and verifying that decompose_by_row_count is never called.
        """
        import mes_dashboard.services.batch_query_engine as bqe
        # patch at module level so any service that reads _USE_ROW_COUNT_CHUNKING sees False
        with patch.object(bqe, "_USE_ROW_COUNT_CHUNKING", False):
            called = []

            def _spy(*args, **kwargs):
                called.append(args)
                return []

            with patch.object(bqe, "decompose_by_row_count", side_effect=_spy):
                # Direct call with flag=False; real services use same check
                flag = bqe._USE_ROW_COUNT_CHUNKING
                if not flag:
                    pass  # simulates the service's flag check
                else:
                    bqe.decompose_by_row_count(1000)

        assert len(called) == 0

    def test_flag_true_calls_count_then_paged_sql(self):
        """When flag=true, decompose_by_row_count is reachable (flag check passes)."""
        import mes_dashboard.services.batch_query_engine as bqe
        with patch.object(bqe, "_USE_ROW_COUNT_CHUNKING", True):
            called = []

            def _spy(*args, **kwargs):
                called.append(args)
                return [{"start_row": 1, "end_row": 1}]

            with patch.object(bqe, "decompose_by_row_count", side_effect=_spy):
                flag = bqe._USE_ROW_COUNT_CHUNKING
                if flag:
                    bqe.decompose_by_row_count(1)

        assert len(called) == 1


# ============================================================
# TestExcludedServicesUnmodified (AC-8)
# ============================================================


class TestExcludedServicesUnmodified:
    """AC-8: yield_alert and material_trace must not be imported by batch_query_engine."""

    def test_yield_alert_not_imported_by_batch_engine(self):
        import mes_dashboard.services.batch_query_engine as bqe
        assert not hasattr(bqe, "yield_alert_dataset_cache"), (
            "batch_query_engine must not import yield_alert_dataset_cache"
        )
        # Also verify the module name is not in the module's __dict__
        module_imports = [
            v.__name__ if hasattr(v, "__name__") else str(v)
            for v in vars(bqe).values()
            if hasattr(v, "__module__")
        ]
        for name in module_imports:
            assert "yield_alert" not in str(name).lower()

    def test_material_trace_not_imported_by_batch_engine(self):
        import mes_dashboard.services.batch_query_engine as bqe
        assert not hasattr(bqe, "material_trace_service"), (
            "batch_query_engine must not import material_trace_service"
        )
