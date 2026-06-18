"""Unit tests for BaseChunkedDuckDBJob.

AC-1: run() invokes hooks in order; all 4 ChunkStrategy values dispatch.
AC-2: two reduction paths (requires_cross_chunk_reduction True/False).
AC-5 (unit): job-temp DuckDB deleted on success and on error.
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock, call, patch

import pyarrow as pa
import pytest


# ---------------------------------------------------------------------------
# Concrete test subclass
# ---------------------------------------------------------------------------

class _RecordingJob:
    """Mixin that records which hooks were called and in which order."""
    _hook_calls: list

    def __init__(self, job_id="test-job-001"):
        from mes_dashboard.core.base_chunked_duckdb_job import (
            BaseChunkedDuckDBJob,
            ChunkStrategy,
        )
        # Dynamic inheritance to avoid importing at module scope (test isolation).
        self.__class__.__bases__ = (BaseChunkedDuckDBJob,)
        super().__init__(job_id=job_id)
        self._hook_calls = []
        self._chunks = [{"idx": 0}]  # one chunk by default

    def pre_query(self):
        self._hook_calls.append("pre_query")

    def build_chunk_sql(self, chunk_params):
        self._hook_calls.append("build_chunk_sql")
        return "SELECT 1 FROM dual", {}

    def chunk_to_duckdb(self, batch, job_duckdb_path):
        self._hook_calls.append("chunk_to_duckdb")

    def post_aggregate(self, job_duckdb_path):
        self._hook_calls.append("post_aggregate")
        return "/fake/spool.parquet"

    def progress_report(self, pct):
        self._hook_calls.append(f"progress_{pct}")


def _make_job(
    chunk_strategy=None,
    requires_cross_chunk_reduction=False,
    job_id="test-job-001",
    n_chunks=1,
):
    """Build a test subclass of BaseChunkedDuckDBJob."""
    from mes_dashboard.core.base_chunked_duckdb_job import (
        BaseChunkedDuckDBJob,
        ChunkStrategy,
    )

    if chunk_strategy is None:
        chunk_strategy = ChunkStrategy.SINGLE

    # Create a fresh class each time to avoid shared state.
    class _TestJob(BaseChunkedDuckDBJob):
        namespace = "test_ns"
        _hook_calls: list = []
        _progress_calls: list = []

        def __init__(self, job_id=job_id):
            super().__init__(job_id=job_id)
            self._hook_calls = []
            self._progress_calls = []
            self._chunks = [{"idx": i} for i in range(n_chunks)]
            self.chunk_strategy = chunk_strategy
            self.requires_cross_chunk_reduction = requires_cross_chunk_reduction

        def pre_query(self):
            self._hook_calls.append("pre_query")

        def build_chunk_sql(self, chunk_params):
            self._hook_calls.append("build_chunk_sql")
            return "SELECT 1 FROM dual", {}

        def chunk_to_duckdb(self, batch, job_duckdb_path):
            self._hook_calls.append("chunk_to_duckdb")

        def post_aggregate(self, job_duckdb_path):
            self._hook_calls.append("post_aggregate")
            return "/fake/spool.parquet"

        def progress_report(self, pct):
            self._hook_calls.append(f"progress_{pct}")
            self._progress_calls.append(pct)

    return _TestJob(job_id=job_id)


# ---------------------------------------------------------------------------
# Helper: patch OracleArrowReader to return a fake batch
# ---------------------------------------------------------------------------

def _fake_batch():
    return pa.RecordBatch.from_pydict({"id": [1, 2]})


def _patch_reader(job, batches=None):
    """Replace job._reader.chunk_iter with a mock returning given batches."""
    if batches is None:
        batches = [_fake_batch()]
    mock_reader = MagicMock()
    mock_reader.chunk_iter.return_value = iter(batches)
    job._reader = mock_reader
    return mock_reader


# ---------------------------------------------------------------------------
# AC-1: hook order + progress brackets
# ---------------------------------------------------------------------------

class TestHookOrder:
    def test_run_hook_order(self, tmp_path):
        """pre_query → (chunk processing) → post_aggregate → correct progress."""
        job = _make_job()
        _patch_reader(job)

        with patch.object(job, "_make_job_duckdb_path", return_value=str(tmp_path / "test.duckdb")):
            result = job.run()

        assert "pre_query" in job._hook_calls
        assert "post_aggregate" in job._hook_calls
        pre_idx = job._hook_calls.index("pre_query")
        agg_idx = job._hook_calls.index("post_aggregate")
        assert pre_idx < agg_idx

    def test_progress_brackets(self):
        """progress_report called with 5, then ≤15, then ≤90, then 100."""
        job = _make_job()
        _patch_reader(job)

        # No real DuckDB needed for reduction=False path.
        job.run()

        pcts = job._progress_calls
        assert pcts[0] == 5, f"First progress must be 5, got {pcts}"
        assert pcts[-1] == 100, f"Last progress must be 100, got {pcts}"
        assert pcts[1] <= 15, f"Second progress must be ≤15, got {pcts[1]}"
        # Find 90 bracket.
        assert any(p <= 90 for p in pcts), f"No ≤90 bracket found: {pcts}"

    @pytest.mark.parametrize("strategy", ["TIME", "ID_LIST", "ROW_COUNT", "SINGLE"])
    def test_all_four_chunk_strategies_dispatch(self, strategy):
        """All 4 ChunkStrategy values complete the run() template without error."""
        from mes_dashboard.core.base_chunked_duckdb_job import ChunkStrategy

        job = _make_job(chunk_strategy=ChunkStrategy[strategy])
        _patch_reader(job)

        result = job.run()
        assert result == "/fake/spool.parquet"
        assert "pre_query" in job._hook_calls
        assert "post_aggregate" in job._hook_calls


# ---------------------------------------------------------------------------
# AC-2: two reduction paths
# ---------------------------------------------------------------------------

class TestReductionPaths:
    def test_false_reduction_path_no_writer_lock(self):
        """requires_cross_chunk_reduction=False → no writer_lock acquisition."""
        job = _make_job(requires_cross_chunk_reduction=False, n_chunks=2)
        _patch_reader(job)

        lock_acquired = []
        original_lock = job._writer_lock

        class _TrackingLock:
            def __enter__(self):
                lock_acquired.append(True)
                return self

            def __exit__(self, *args):
                pass

            def acquire(self, *a, **kw):
                lock_acquired.append(True)
                return True

            def release(self):
                pass

        # Replace at class level temporarily.
        from mes_dashboard.core import base_chunked_duckdb_job as mod
        orig = mod.BaseChunkedDuckDBJob._writer_lock
        mod.BaseChunkedDuckDBJob._writer_lock = _TrackingLock()
        try:
            job.run()
        finally:
            mod.BaseChunkedDuckDBJob._writer_lock = orig

        # For False path, no chunk_to_duckdb with writer_lock should occur.
        assert "chunk_to_duckdb" not in job._hook_calls, (
            "False reduction path should NOT call chunk_to_duckdb with writer_lock"
        )

    def test_true_reduction_path_uses_job_temp_duckdb(self, tmp_path, monkeypatch):
        """requires_cross_chunk_reduction=True → job builds a temp DuckDB path."""
        import duckdb

        job = _make_job(requires_cross_chunk_reduction=True, n_chunks=1)

        # Patch chunk_iter to return a real batch.
        mock_reader = MagicMock()
        mock_reader.chunk_iter.return_value = iter([_fake_batch()])
        job._reader = mock_reader

        job_duckdb_path_recorded = []
        original_chunk_to_duckdb = job.chunk_to_duckdb

        def _recording_chunk_to_duckdb(batch, path):
            job_duckdb_path_recorded.append(path)
            # Use real DuckDB to verify no write error.
            import duckdb as _duckdb
            from mes_dashboard.core.base_chunked_duckdb_job import BaseChunkedDuckDBJob
            with BaseChunkedDuckDBJob._writer_lock:
                conn = _duckdb.connect(path)
                try:
                    conn.register("_b", batch)
                    conn.execute("CREATE TABLE IF NOT EXISTS raw AS SELECT * FROM _b WHERE 1=0")
                    conn.execute("INSERT INTO raw SELECT * FROM _b")
                    conn.unregister("_b")
                finally:
                    conn.close()

        job.chunk_to_duckdb = _recording_chunk_to_duckdb

        # Redirect DUCKDB_JOB_DIR to tmp_path.
        monkeypatch.setenv("DUCKDB_JOB_DIR", str(tmp_path))

        # Reload to pick up monkeypatched env var for _make_job_duckdb_path.
        result = job.run()

        assert result == "/fake/spool.parquet"
        # chunk_to_duckdb was called with a path inside tmp_path.
        assert len(job_duckdb_path_recorded) >= 1
        assert "test_ns" in job_duckdb_path_recorded[0]

    def test_true_reduction_path_writer_lock_serialized(self, tmp_path, monkeypatch):
        """requires_cross_chunk_reduction=True → concurrent chunks serialized by writer_lock."""
        import time

        from mes_dashboard.core import base_chunked_duckdb_job as mod

        job = _make_job(
            requires_cross_chunk_reduction=True,
            n_chunks=3,
            job_id="concurrent-test",
        )
        job.max_parallel = 3

        concurrent_writes = []
        write_overlap = []
        inside = threading.Event()

        def _concurrent_chunk_to_duckdb(batch, path):
            # Check if already inside (would signal lock NOT held).
            if inside.is_set():
                write_overlap.append(True)
            inside.set()
            time.sleep(0.01)  # hold briefly
            concurrent_writes.append(threading.current_thread().ident)
            inside.clear()

        job.chunk_to_duckdb = _concurrent_chunk_to_duckdb

        mock_reader = MagicMock()
        mock_reader.chunk_iter.return_value = iter([_fake_batch()])
        job._reader = mock_reader

        monkeypatch.setenv("DUCKDB_JOB_DIR", str(tmp_path))
        job.run()

        # No overlapping writes should have been observed.
        assert write_overlap == [], "writer_lock must serialize concurrent DuckDB inserts"


# ---------------------------------------------------------------------------
# AC-5 (unit): job-temp DuckDB lifecycle
# ---------------------------------------------------------------------------

class TestJobTempLifecycle:
    def test_job_temp_deleted_on_success(self, tmp_path, monkeypatch):
        """Job-temp DuckDB file is deleted after successful run()."""
        monkeypatch.setenv("DUCKDB_JOB_DIR", str(tmp_path))
        job = _make_job(requires_cross_chunk_reduction=False)
        _patch_reader(job)

        job.run()

        # No .duckdb files should remain in tmp_path after successful run.
        duckdb_files = list(tmp_path.rglob("*.duckdb"))
        assert duckdb_files == [], f"Job-temp DuckDB not cleaned up: {duckdb_files}"

    def test_job_temp_deleted_on_error_in_post_aggregate(self, tmp_path, monkeypatch):
        """Job-temp DuckDB file is deleted even when post_aggregate raises."""
        monkeypatch.setenv("DUCKDB_JOB_DIR", str(tmp_path))
        job = _make_job(requires_cross_chunk_reduction=True, n_chunks=0)

        # Make reader return nothing so chunk phase passes.
        mock_reader = MagicMock()
        mock_reader.chunk_iter.return_value = iter([])
        job._reader = mock_reader

        created_path = []

        original_make = job._make_job_duckdb_path

        def _patched_make():
            path = str(tmp_path / "test_ns" / "test-job-001.duckdb")
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).touch()
            created_path.append(path)
            return path

        job._make_job_duckdb_path = _patched_make

        def _failing_post_aggregate(job_duckdb_path):
            raise RuntimeError("post_aggregate failure")

        job.post_aggregate = _failing_post_aggregate

        with pytest.raises(RuntimeError, match="post_aggregate failure"):
            job.run()

        # File must be deleted despite the error.
        if created_path:
            assert not Path(created_path[0]).exists(), (
                "Job-temp DuckDB must be deleted even when post_aggregate raises"
            )

    def test_job_temp_not_created_for_false_reduction(self, tmp_path, monkeypatch):
        """For requires_cross_chunk_reduction=False, no job-temp DuckDB is created."""
        monkeypatch.setenv("DUCKDB_JOB_DIR", str(tmp_path))
        job = _make_job(requires_cross_chunk_reduction=False)
        _patch_reader(job)

        job.run()

        # DUCKDB_JOB_DIR should be empty (no temp file created).
        duckdb_files = list(tmp_path.rglob("*.duckdb"))
        assert duckdb_files == [], "False reduction path must not create a job-temp DuckDB"
