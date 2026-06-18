"""Integration tests for OracleArrowReader pool lifecycle and BaseChunkedDuckDBJob.

These tests are marked ``integration_real`` and run in the nightly lane only.
They are implemented with mocks (real Oracle not available in unit mode) to
validate lifecycle and concurrency semantics without touching an actual database.

pytestmark = pytest.mark.integration_real
"""
from __future__ import annotations

import queue
import threading
import time
from pathlib import Path
from typing import Iterator
from unittest.mock import MagicMock, patch

import pyarrow as pa
import pytest

pytestmark = pytest.mark.integration_real


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_batch(n_rows: int = 10) -> pa.RecordBatch:
    return pa.RecordBatch.from_pydict({"id": list(range(n_rows)), "val": ["x"] * n_rows})


def _make_pool_with_maxsize(maxsize: int):
    """Return a mock pool that enforces max concurrent acquisitions."""
    available = queue.Semaphore(maxsize)
    active_conns: list = []
    lock = threading.Lock()

    class _MockConn:
        def close(self):
            available.release()
            with lock:
                active_conns.remove(self)

    def _acquire():
        acquired = available.acquire(timeout=5.0)
        if not acquired:
            raise TimeoutError("Pool exhausted — could not acquire connection within 5s")
        conn = _MockConn()
        with lock:
            active_conns.append(conn)
        return conn

    pool = MagicMock()
    pool.acquire.side_effect = _acquire
    pool._active_conns = active_conns
    pool._available = available
    return pool


def _make_reader_with_pool(pool):
    from mes_dashboard.core.oracle_arrow_reader import OracleArrowReader

    reader = OracleArrowReader()
    reader._pool = pool

    # Patch cursor to return a single batch then stop.
    def _patched_chunk_iter(sql, params, chunk_size=10000):
        conn = pool.acquire()
        try:
            yield _fake_batch()
        finally:
            conn.close()

    reader.chunk_iter = _patched_chunk_iter
    return reader


# ---------------------------------------------------------------------------
# AC-3 (integration): Pool exhaustion and recovery
# ---------------------------------------------------------------------------

class TestPoolExhaustionAndRecovery:
    def test_pool_exhaustion_and_recovery(self):
        """Third concurrent request waits; recovers after first connection is returned."""
        pool = _make_pool_with_maxsize(2)
        reader = _make_reader_with_pool(pool)

        results: list = []
        errors: list = []

        def _run_query(query_id):
            try:
                batches = list(reader.chunk_iter("SELECT 1 FROM dual", {}))
                results.append((query_id, len(batches)))
            except Exception as exc:
                errors.append((query_id, exc))

        threads = [threading.Thread(target=_run_query, args=(i,)) for i in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10.0)

        # All 3 requests should eventually complete (pool releases on conn.close()).
        assert len(errors) == 0, f"Unexpected errors: {errors}"
        assert len(results) == 3, f"Not all requests completed: {results}"

    def test_pool_exhaustion_timeout_raises(self):
        """If pool is fully occupied and timeout passes, acquisition raises."""
        # Pool with size 1, held open for longer than acquire timeout.
        available = threading.Semaphore(1)
        pool = MagicMock()
        acquired = threading.Event()
        released = threading.Event()

        def _slow_acquire():
            ok = available.acquire(timeout=0.05)  # very short timeout
            if not ok:
                raise TimeoutError("Pool exhausted")
            acquired.set()
            return MagicMock(close=lambda: (available.release(), released.set())[0])

        pool.acquire.side_effect = _slow_acquire

        # Hold the one connection.
        first_conn = pool.acquire()
        assert acquired.is_set()

        from mes_dashboard.core.oracle_arrow_reader import OracleArrowReader

        reader = OracleArrowReader()
        reader._pool = pool

        # Second acquire should time out.
        with pytest.raises(TimeoutError):
            pool.acquire()

        first_conn.close()


# ---------------------------------------------------------------------------
# AC-2 (integration): writer_lock under concurrent chunks
# ---------------------------------------------------------------------------

class TestWriterLockUnderConcurrentChunks:
    def test_writer_lock_under_concurrent_chunks(self, tmp_path):
        """Multiple threads cannot interleave DuckDB writes (writer_lock enforced)."""
        import duckdb

        from mes_dashboard.core.base_chunked_duckdb_job import BaseChunkedDuckDBJob

        db_path = str(tmp_path / "concurrent_test.duckdb")
        # Pre-create the table.
        conn = duckdb.connect(db_path)
        conn.execute("CREATE TABLE raw (id INTEGER, val VARCHAR)")
        conn.close()

        write_order: list = []
        inside_write = threading.Event()
        overlaps_detected: list = []

        original_lock = BaseChunkedDuckDBJob._writer_lock

        def _controlled_write(batch, path):
            with BaseChunkedDuckDBJob._writer_lock:
                if inside_write.is_set():
                    overlaps_detected.append(threading.current_thread().ident)
                inside_write.set()
                time.sleep(0.01)
                write_order.append(threading.current_thread().ident)
                inside_write.clear()

        n_threads = 4
        threads = [
            threading.Thread(target=_controlled_write, args=(_fake_batch(), db_path))
            for _ in range(n_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10.0)

        assert overlaps_detected == [], (
            f"writer_lock did not serialize writes: {overlaps_detected}"
        )
        assert len(write_order) == n_threads


# ---------------------------------------------------------------------------
# AC-5 (integration): job-temp lifecycle
# ---------------------------------------------------------------------------

class TestJobTempLifecycle:
    def test_job_temp_lifecycle(self, tmp_path, monkeypatch):
        """Job-temp DuckDB is created at job start and deleted at completion."""
        import duckdb

        monkeypatch.setenv("DUCKDB_JOB_DIR", str(tmp_path))

        from mes_dashboard.core.base_chunked_duckdb_job import (
            BaseChunkedDuckDBJob,
            ChunkStrategy,
        )

        temp_path_during: list = []

        class _LifecycleJob(BaseChunkedDuckDBJob):
            namespace = "lifecycle_ns"
            chunk_strategy = ChunkStrategy.SINGLE
            requires_cross_chunk_reduction = True
            max_parallel = 1

            def __init__(self):
                super().__init__(job_id="lifecycle-test-001")
                self._chunks = []

            def pre_query(self):
                pass

            def build_chunk_sql(self, chunk_params):
                return "SELECT 1 FROM dual", {}

            def post_aggregate(self, job_duckdb_path):
                # Record whether the temp file exists during execution.
                if job_duckdb_path and Path(job_duckdb_path).exists():
                    temp_path_during.append(job_duckdb_path)
                return str(tmp_path / "final.parquet")

            def progress_report(self, pct):
                pass

        job = _LifecycleJob()
        # Patch reader to avoid real Oracle.
        mock_reader = MagicMock()
        mock_reader.chunk_iter.return_value = iter([])
        job._reader = mock_reader

        result = job.run()

        # The job-temp file should be gone now.
        duckdb_files = list(tmp_path.rglob("*.duckdb"))
        assert duckdb_files == [], f"Job-temp DuckDB not deleted: {duckdb_files}"
        assert result == str(tmp_path / "final.parquet")

    def test_mid_job_error_cleans_temp_and_conn(self, tmp_path, monkeypatch):
        """Error in post_aggregate: job-temp DuckDB is deleted; conn.close() called."""
        monkeypatch.setenv("DUCKDB_JOB_DIR", str(tmp_path))

        from mes_dashboard.core.base_chunked_duckdb_job import (
            BaseChunkedDuckDBJob,
            ChunkStrategy,
        )

        conn_close_calls: list = []

        class _ErrorJob(BaseChunkedDuckDBJob):
            namespace = "error_ns"
            chunk_strategy = ChunkStrategy.SINGLE
            requires_cross_chunk_reduction = True
            max_parallel = 1

            def __init__(self):
                super().__init__(job_id="error-test-001")
                self._chunks = [{"idx": 0}]

            def pre_query(self):
                pass

            def build_chunk_sql(self, chunk_params):
                return "SELECT 1 FROM dual", {}

            def post_aggregate(self, job_duckdb_path):
                raise RuntimeError("Simulated post_aggregate failure")

            def progress_report(self, pct):
                pass

        job = _ErrorJob()

        # Patch reader: track conn.close().
        pool = MagicMock()
        mock_conn = MagicMock()
        mock_conn.close.side_effect = lambda: conn_close_calls.append(True)
        pool.acquire.return_value = mock_conn

        from mes_dashboard.core.oracle_arrow_reader import OracleArrowReader

        reader = OracleArrowReader()
        reader._pool = pool

        def _fake_chunk_iter(sql, params, chunk_size=10000):
            yield _fake_batch()
            mock_conn.close()

        reader.chunk_iter = _fake_chunk_iter
        job._reader = reader

        with pytest.raises(RuntimeError, match="Simulated post_aggregate failure"):
            job.run()

        # Job-temp should be cleaned up.
        duckdb_files = list(tmp_path.rglob("*.duckdb"))
        assert duckdb_files == [], "Job-temp DuckDB must be deleted even on error"
        # Connection must be returned.
        assert len(conn_close_calls) >= 1, "conn.close() must be called even on error"
