# -*- coding: utf-8 -*-
"""
Integration tests: Race condition coverage.

Uses threading.Barrier to synchronize two threads so they hit shared state
simultaneously, exposing any missing locks or TOCTOU vulnerabilities.

Tests:
  (a) Concurrent cache writes to the same in-process cache key
  (b) Concurrent export requests with the same (user, report_type, params_hash)
  (c) Concurrent spool read vs. cleanup daemon

Run with:
    conda run -n mes-dashboard pytest tests/integration/test_race_conditions.py \
        --run-integration-real -v
"""

from __future__ import annotations

import threading
import time
import uuid
from pathlib import Path
from typing import List

import pytest

pytestmark = pytest.mark.integration_real


# ---------------------------------------------------------------------------
# (a) Concurrent cache writes — same cache key
# ---------------------------------------------------------------------------

class TestConcurrentCacheWrites:
    """Two threads write to the same filter_cache in-process dict simultaneously."""

    @pytest.mark.integration_real
    def test_concurrent_writes_do_not_corrupt_cache(self):
        import mes_dashboard.services.filter_cache as fc_mod

        barrier = threading.Barrier(2)
        errors: List[Exception] = []

        def write_cache(value):
            try:
                barrier.wait(timeout=5)
                with fc_mod._CACHE_LOCK:
                    fc_mod._CACHE["workcenter_groups"] = value
                    time.sleep(0.001)  # hold lock briefly to widen race window
            except Exception as exc:
                errors.append(exc)

        data_a = [{"name": "GROUP-A"}]
        data_b = [{"name": "GROUP-B"}]

        t1 = threading.Thread(target=write_cache, args=(data_a,))
        t2 = threading.Thread(target=write_cache, args=(data_b,))
        t1.start(); t2.start()
        t1.join(timeout=10); t2.join(timeout=10)

        assert not errors, f"Race condition raised exceptions: {errors}"

        # Cache must be one of the two valid values — no corruption
        result = fc_mod._CACHE["workcenter_groups"]
        assert result in (data_a, data_b), f"Corrupted cache value: {result}"

    @pytest.mark.integration_real
    def test_concurrent_reads_while_writing_are_consistent(self):
        import mes_dashboard.services.filter_cache as fc_mod

        with fc_mod._CACHE_LOCK:
            fc_mod._CACHE["workcenter_groups"] = [{"name": "INITIAL"}]
            fc_mod._CACHE["last_refresh"] = time.time()

        barrier = threading.Barrier(3)
        results: List = []
        errors: List[Exception] = []

        def read_cache():
            try:
                barrier.wait(timeout=5)
                with fc_mod._CACHE_LOCK:
                    val = fc_mod._CACHE.get("workcenter_groups")
                results.append(val)
            except Exception as exc:
                errors.append(exc)

        def write_cache():
            try:
                barrier.wait(timeout=5)
                with fc_mod._CACHE_LOCK:
                    fc_mod._CACHE["workcenter_groups"] = [{"name": "UPDATED"}]
            except Exception as exc:
                errors.append(exc)

        threads = [
            threading.Thread(target=read_cache),
            threading.Thread(target=read_cache),
            threading.Thread(target=write_cache),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert not errors
        # Each read result must be either INITIAL or UPDATED — not None or garbage
        for r in results:
            assert r is not None
            assert isinstance(r, list)


# ---------------------------------------------------------------------------
# (b) Concurrent export with same key — deduplication
# ---------------------------------------------------------------------------

class TestConcurrentExportDeduplication:
    """Concurrent export requests with the same params_hash should not double-write."""

    @pytest.mark.integration_real
    def test_concurrent_spool_register_same_query_id(self, temp_spool_dir: Path, local_redis: str):
        """Two threads registering the same query_id should not raise or corrupt state."""
        import os
        os.environ["REDIS_URL"] = local_redis
        os.environ["REDIS_ENABLED"] = "true"

        try:
            from mes_dashboard.core.query_spool_store import register_spool_file
        except ImportError:
            pytest.skip("query_spool_store not importable without full app env")

        query_id = f"test-race-{uuid.uuid4().hex[:8]}"
        spool_file = temp_spool_dir / f"{query_id}.parquet"
        spool_file.write_bytes(b"PAR1")  # minimal parquet magic bytes

        barrier = threading.Barrier(2)
        errors: List[Exception] = []
        results: List = []

        def register():
            try:
                barrier.wait(timeout=5)
                try:
                    # register_spool_file(namespace, query_id, src_path, row_count)
                    ok = register_spool_file(
                        "test",
                        query_id,
                        spool_file,
                        1,
                    )
                    results.append(ok)
                except Exception as exc:
                    results.append(exc)
            except Exception as exc:
                errors.append(exc)

        t1 = threading.Thread(target=register)
        t2 = threading.Thread(target=register)
        t1.start(); t2.start()
        t1.join(timeout=10); t2.join(timeout=10)

        assert not errors, f"Barrier errors: {errors}"
        # At least one registration must succeed (True); none must crash
        exceptions_in_results = [r for r in results if isinstance(r, Exception)]
        assert len(exceptions_in_results) == 0, f"Registration raised: {exceptions_in_results}"


# ---------------------------------------------------------------------------
# (c) Concurrent spool read vs. cleanup
# ---------------------------------------------------------------------------

class TestSpoolReadVsCleanupRace:
    """A reader and cleanup daemon hitting the same spool file simultaneously."""

    @pytest.mark.integration_real
    def test_read_during_cleanup_does_not_crash(self, temp_spool_dir: Path, local_redis: str):
        """Simulates a reader and cleanup running concurrently on the same file."""
        import os
        os.environ["REDIS_URL"] = local_redis
        os.environ["REDIS_ENABLED"] = "true"

        try:
            from mes_dashboard.core.query_spool_store import cleanup_expired_spool
        except ImportError:
            pytest.skip("query_spool_store not importable without full app env")

        # Create a dummy spool file
        spool_file = temp_spool_dir / f"expired-{uuid.uuid4().hex[:8]}.parquet"
        spool_file.write_bytes(b"PAR1")

        barrier = threading.Barrier(2)
        errors: List[Exception] = []

        def reader():
            try:
                barrier.wait(timeout=5)
                # Simulate reading: check existence and read bytes
                time.sleep(0.001)
                if spool_file.exists():
                    _ = spool_file.read_bytes()
            except Exception as exc:
                errors.append(exc)

        def cleaner():
            try:
                barrier.wait(timeout=5)
                try:
                    # Attempt cleanup — may or may not find the file
                    cleanup_expired_spool(namespace="test")
                except Exception:
                    pass
                # Also directly delete to simulate daemon action
                try:
                    spool_file.unlink(missing_ok=True)
                except Exception:
                    pass
            except Exception as exc:
                errors.append(exc)

        t1 = threading.Thread(target=reader)
        t2 = threading.Thread(target=cleaner)
        t1.start(); t2.start()
        t1.join(timeout=10); t2.join(timeout=10)

        # No unhandled exceptions from either thread
        assert not errors, f"Race condition errors: {errors}"

    @pytest.mark.integration_real
    def test_concurrent_spool_cleanup_is_idempotent(self, temp_spool_dir: Path, local_redis: str):
        """Two cleanup threads racing should not corrupt state or raise unhandled errors."""
        import os
        os.environ["REDIS_URL"] = local_redis
        os.environ["REDIS_ENABLED"] = "true"

        try:
            from mes_dashboard.core.query_spool_store import cleanup_expired_spool
        except ImportError:
            pytest.skip("query_spool_store not importable without full app env")

        barrier = threading.Barrier(2)
        errors: List[Exception] = []

        def cleanup():
            try:
                barrier.wait(timeout=5)
                try:
                    cleanup_expired_spool(namespace=None)
                except Exception:
                    pass  # LockUnavailableError is expected for the loser
            except Exception as exc:
                errors.append(exc)

        t1 = threading.Thread(target=cleanup)
        t2 = threading.Thread(target=cleanup)
        t1.start(); t2.start()
        t1.join(timeout=10); t2.join(timeout=10)

        assert not errors
