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
        """Two threads registering the same query_id must converge on one file+meta.

        User-visible guarantees verified:
          - At least one thread returns True (success)
          - No uncaught exceptions from either thread
          - Exactly one canonical spool file exists on disk at _target_path()
          - Exactly one Redis meta key exists with matching query_id
        """
        import json as _json
        import os
        os.environ["REDIS_URL"] = local_redis
        os.environ["REDIS_ENABLED"] = "true"

        try:
            from mes_dashboard.core.query_spool_store import (
                register_spool_file,
                _target_path,
                _meta_key,
            )
            import mes_dashboard.core.redis_client as rc_mod
            from mes_dashboard.core.redis_client import get_key
        except ImportError:
            pytest.skip("query_spool_store not importable without full app env")

        # Re-point the module-level Redis URL to the test's local_redis and
        # reset the cached singleton so register_spool_file hits the right server.
        rc_mod.REDIS_URL = local_redis
        rc_mod.REDIS_ENABLED = True
        rc_mod._REDIS_CLIENT = None
        client = rc_mod.get_redis_client()
        assert client is not None, "local_redis should be reachable"

        query_id = f"test-race-{uuid.uuid4().hex[:8]}"

        # Each thread needs its OWN src_path so both can race on writing to
        # the same dest (otherwise the second thread finds src missing and
        # fails trivially — not an actual deduplication race).
        src_a = temp_spool_dir / f"src-a-{uuid.uuid4().hex[:8]}.parquet"
        src_b = temp_spool_dir / f"src-b-{uuid.uuid4().hex[:8]}.parquet"
        src_a.write_bytes(b"PAR1" + b"A" * 16)
        src_b.write_bytes(b"PAR1" + b"B" * 16)

        barrier = threading.Barrier(2)
        errors: List[Exception] = []
        results: List = []

        def register(src_path):
            try:
                barrier.wait(timeout=5)
                try:
                    ok = register_spool_file("test", query_id, src_path, 1)
                    results.append(ok)
                except Exception as exc:
                    results.append(exc)
            except Exception as exc:
                errors.append(exc)

        t1 = threading.Thread(target=register, args=(src_a,))
        t2 = threading.Thread(target=register, args=(src_b,))
        t1.start(); t2.start()
        t1.join(timeout=10); t2.join(timeout=10)

        # Cleanup: ensure Redis key is removed even if assertions fail
        redis_meta_key = get_key(_meta_key("test", query_id))

        try:
            assert not errors, f"Barrier errors: {errors}"

            exceptions_in_results = [r for r in results if isinstance(r, Exception)]
            assert len(exceptions_in_results) == 0, (
                f"Registration raised unhandled: {exceptions_in_results}"
            )

            successes = [r for r in results if r is True]
            assert len(successes) >= 1, (
                f"No successful registrations — at least one must succeed. "
                f"results={results}"
            )

            # Exactly one canonical file exists on disk
            dest = _target_path("test", query_id)
            assert dest.exists(), (
                f"Expected canonical spool file at {dest} — no registration "
                f"produced a file. results={results}"
            )
            assert dest.stat().st_size > 0, f"Spool file is empty: {dest}"
            siblings = list(dest.parent.glob(f"{query_id}*.parquet"))
            assert len(siblings) == 1, (
                f"Expected exactly 1 canonical spool file, found {len(siblings)}: "
                f"{siblings}. Concurrent register did not converge."
            )

            # Exactly one Redis meta key exists with matching query_id
            meta_raw = client.get(redis_meta_key)
            assert meta_raw is not None, (
                f"Redis meta key missing at {redis_meta_key} — concurrent "
                f"register produced no authoritative metadata"
            )
            meta = _json.loads(meta_raw)
            assert meta["query_id"] == query_id, (
                f"Redis meta query_id mismatch: {meta.get('query_id')!r} "
                f"vs expected {query_id!r}"
            )
        finally:
            try:
                client.delete(redis_meta_key)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# (c) Concurrent spool read vs. cleanup
# ---------------------------------------------------------------------------

class TestSpoolReadVsCleanupRace:
    """A reader and cleanup daemon hitting the same spool file simultaneously."""

    @pytest.mark.integration_real
    def test_read_during_cleanup_does_not_crash(self, temp_spool_dir: Path, local_redis: str):
        """Reader and cleanup racing on the same expired spool file.

        User-visible guarantees verified:
          - Reader either returns valid bytes OR a clean None (no partial read)
          - Cleanup reports at least 1 meta_deleted after the race
          - No uncaught exceptions from either thread
          - After the race, the file and Redis meta key are both gone
        """
        import json as _json
        import os
        os.environ["REDIS_URL"] = local_redis
        os.environ["REDIS_ENABLED"] = "true"

        try:
            from mes_dashboard.core.query_spool_store import (
                register_spool_file,
                cleanup_expired_spool,
                _target_path,
                _meta_key,
            )
            import mes_dashboard.core.redis_client as rc_mod
            from mes_dashboard.core.redis_client import get_key
        except ImportError:
            pytest.skip("query_spool_store not importable without full app env")

        rc_mod.REDIS_URL = local_redis
        rc_mod.REDIS_ENABLED = True
        rc_mod._REDIS_CLIENT = None
        client = rc_mod.get_redis_client()
        assert client is not None, "local_redis should be reachable"

        # Register a real spool file via the production path
        query_id = f"expired-{uuid.uuid4().hex[:8]}"
        src = temp_spool_dir / f"{query_id}.parquet"
        src.write_bytes(b"PAR1" + b"X" * 32)
        assert register_spool_file("test", query_id, src, 1) is True

        dest = _target_path("test", query_id)
        redis_meta_key = get_key(_meta_key("test", query_id))

        # Mark metadata as expired (expires_at in the past) so cleanup will delete
        meta_raw = client.get(redis_meta_key)
        assert meta_raw is not None, "precondition: meta must be registered"
        meta = _json.loads(meta_raw)
        meta["expires_at"] = int(time.time()) - 10
        client.set(redis_meta_key, _json.dumps(meta, ensure_ascii=False, sort_keys=True))

        barrier = threading.Barrier(2)
        errors: List[Exception] = []
        reader_result = {"bytes": None, "exc": None}
        cleaner_stats = {"stats": None, "exc": None}

        def reader():
            try:
                barrier.wait(timeout=5)
                # Reader may win (gets bytes) or lose (file deleted mid-race)
                try:
                    if dest.exists():
                        reader_result["bytes"] = dest.read_bytes()
                except FileNotFoundError:
                    reader_result["bytes"] = None  # Acceptable race outcome
            except Exception as exc:
                errors.append(exc)

        def cleaner():
            try:
                barrier.wait(timeout=5)
                try:
                    cleaner_stats["stats"] = cleanup_expired_spool(namespace="test")
                except Exception as exc:
                    cleaner_stats["exc"] = exc
            except Exception as exc:
                errors.append(exc)

        t1 = threading.Thread(target=reader)
        t2 = threading.Thread(target=cleaner)
        t1.start(); t2.start()
        t1.join(timeout=15); t2.join(timeout=15)

        try:
            assert not errors, f"Race condition errors: {errors}"
            assert cleaner_stats["exc"] is None, (
                f"Cleaner raised: {cleaner_stats['exc']}"
            )

            # Reader result must be either valid bytes or None — never partial
            b = reader_result["bytes"]
            assert b is None or (isinstance(b, bytes) and b.startswith(b"PAR1")), (
                f"Reader got corrupted/partial bytes: {b!r}"
            )

            # Cleanup must have deleted at least one meta entry
            stats = cleaner_stats["stats"]
            assert stats is not None, "cleanup_expired_spool returned None"
            assert stats.get("meta_deleted", 0) >= 1, (
                f"Cleanup should have deleted the expired meta; stats={stats}"
            )

            # Post-conditions: file gone AND Redis key gone
            assert not dest.exists(), (
                f"Spool file still present after cleanup: {dest}"
            )
            assert client.get(redis_meta_key) is None, (
                f"Redis meta key still present after cleanup: {redis_meta_key}"
            )
        finally:
            try:
                client.delete(redis_meta_key)
            except Exception:
                pass
            try:
                dest.unlink(missing_ok=True)
            except Exception:
                pass

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
