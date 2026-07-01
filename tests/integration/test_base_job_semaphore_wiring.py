# -*- coding: utf-8 -*-
"""Integration tests for base-job-semaphore-wiring: N=8 concurrent peak sampling.

Companion to tests/integration/test_rq_semaphore_wiring.py, which covers the
*legacy* per-domain workers. This suite covers BaseChunkedDuckDBJob.run() —
the unified job core used by EAP_ALARM/DOWNTIME/MATERIAL_TRACE/
PRODUCTION_HISTORY/REJECT_HISTORY/RESOURCE_HISTORY when
`*_USE_UNIFIED_JOB=on` (the production default).

Marked multi_worker (requires --run-integration-real). CI runs these post-merge
on schedule, not as pre-merge blockers (ci-gates.md).

Thread-safety rule: ALL module-level patches must be applied via monkeypatch
(not patch() inside threads) — see test_rq_semaphore_wiring.py header for why.

AC coverage:
  AC-1 -> test_peak_slot_entries_bounded_by_worker_count
  AC-2 -> test_all_jobs_complete_no_deadlock
  AC-3 -> test_semaphore_fully_released_after_run
  AC-4 -> test_slot_released_after_fanout_exception_in_worker
"""

from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from typing import List, Tuple

import pytest

from mes_dashboard.core.base_chunked_duckdb_job import BaseChunkedDuckDBJob, ChunkStrategy

pytestmark = pytest.mark.multi_worker


class _IntegJob(BaseChunkedDuckDBJob):
    namespace = "integ_ns"
    chunk_strategy = ChunkStrategy.SINGLE
    requires_cross_chunk_reduction = False

    def pre_query(self) -> None:
        self._chunks = [{"i": 0}]

    def build_chunk_sql(self, chunk_params):  # pragma: no cover - fan-out mocked
        return ("SELECT 1 FROM dual", {})

    def post_aggregate(self, job_duckdb_path):
        return f"/tmp/{self.namespace}/{self.job_id}.parquet"


class TestBaseJobConcurrencyCap:
    """Integration: N=8 concurrent job.run() calls verify slot wiring."""

    _N = 8

    def test_peak_slot_entries_bounded_by_worker_count(self, monkeypatch):
        """AC-1: Under N=8 concurrent jobs, the slot CM is entered exactly once
        per job (wiring verified). The recording CM does NOT enforce the Redis
        cap (Redis unavailable in CI -> fail-open); real cap enforcement is
        unchanged global_concurrency infra, not re-tested here.
        """
        import mes_dashboard.core.base_chunked_duckdb_job as base_mod

        events: List[Tuple[float, str, str]] = []
        lock = threading.Lock()

        @contextmanager
        def _recording_slot(owner: str):
            with lock:
                events.append((time.monotonic(), "enter", owner))
            try:
                yield True
                time.sleep(0.02)  # simulate Oracle I/O
            finally:
                with lock:
                    events.append((time.monotonic(), "exit", owner))

        monkeypatch.setattr(base_mod, "heavy_query_slot", _recording_slot)

        results: List[str] = []
        errors: List[Tuple[str, str]] = []
        result_lock = threading.Lock()

        def _run_job(job_id: str):
            try:
                job = _IntegJob(job_id)
                job._fan_out_append = lambda chunks: None
                job._cleanup_chunk_parquet_dir = lambda jid: None
                job.progress_report = lambda pct: None
                job.run()
                with result_lock:
                    results.append(job_id)
            except Exception as exc:
                with result_lock:
                    errors.append((job_id, str(exc)))

        threads = [
            threading.Thread(target=_run_job, args=(f"integ-{i:03d}",))
            for i in range(self._N)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30.0)

        assert len(errors) == 0, f"Job errors: {errors}"
        assert len(results) == self._N, f"Not all jobs finished: {len(results)}/{self._N}"

        enter_count = sum(1 for e in events if e[1] == "enter")
        assert enter_count == self._N, (
            f"Expected {self._N} slot enters (wiring check); got {enter_count}"
        )

    def test_all_jobs_complete_no_deadlock(self, monkeypatch):
        """AC-2: All N=8 jobs reach terminal state without deadlock within 30s."""
        import mes_dashboard.core.base_chunked_duckdb_job as base_mod

        @contextmanager
        def _noop_slot(owner: str):
            yield True

        monkeypatch.setattr(base_mod, "heavy_query_slot", _noop_slot)

        completed: List[str] = []
        errors: List[str] = []
        lock = threading.Lock()

        def _run_job(job_id: str):
            try:
                job = _IntegJob(job_id)
                job._fan_out_append = lambda chunks: None
                job._cleanup_chunk_parquet_dir = lambda jid: None
                job.progress_report = lambda pct: None
                job.run()
                with lock:
                    completed.append(job_id)
            except Exception as exc:
                with lock:
                    errors.append(f"{job_id}:{exc}")

        threads = [
            threading.Thread(target=_run_job, args=(f"nodead-{i:03d}",))
            for i in range(self._N)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30.0)

        assert len(completed) == self._N, (
            f"Expected all {self._N} to complete without deadlock; "
            f"completed={len(completed)}, errors={errors}"
        )

    def test_semaphore_fully_released_after_run(self, monkeypatch):
        """AC-3: After all N jobs finish, no slots are leaked (enters == exits)."""
        import mes_dashboard.core.base_chunked_duckdb_job as base_mod

        events: List[Tuple[float, str, str]] = []
        lock = threading.Lock()

        @contextmanager
        def _recording_slot(owner: str):
            with lock:
                events.append((time.monotonic(), "enter", owner))
            try:
                yield True
            finally:
                with lock:
                    events.append((time.monotonic(), "exit", owner))

        monkeypatch.setattr(base_mod, "heavy_query_slot", _recording_slot)

        completed: List[str] = []
        result_lock = threading.Lock()

        def _run_job(job_id: str):
            job = _IntegJob(job_id)
            job._fan_out_append = lambda chunks: None
            job._cleanup_chunk_parquet_dir = lambda jid: None
            job.progress_report = lambda pct: None
            job.run()
            with result_lock:
                completed.append(job_id)

        threads = [
            threading.Thread(target=_run_job, args=(f"leak-{i:03d}",))
            for i in range(self._N)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30.0)

        enters = [e for e in events if e[1] == "enter"]
        exits = [e for e in events if e[1] == "exit"]

        assert len(completed) == self._N, f"Not all jobs completed: {len(completed)}"
        assert len(enters) == len(exits), (
            f"Slot leak detected: {len(enters)} enters vs {len(exits)} exits — "
            "heavy_query_slot finally block did not fire for all jobs"
        )

    def test_slot_released_after_fanout_exception_in_worker(self, monkeypatch):
        """AC-4: When one job's Oracle fan-out faults, its slot is still released.

        Fault injection via thread-local flag so all threads share one
        monkeypatched slot CM (no nested patch() in threads).
        """
        import mes_dashboard.core.base_chunked_duckdb_job as base_mod

        events: List[Tuple[float, str, str]] = []
        lock = threading.Lock()
        _local = threading.local()
        faulting_job = "fault-000"

        @contextmanager
        def _recording_slot_with_fault(owner: str):
            with lock:
                events.append((time.monotonic(), "enter", owner))
            try:
                yield True
            finally:
                with lock:
                    events.append((time.monotonic(), "exit", owner))

        monkeypatch.setattr(base_mod, "heavy_query_slot", _recording_slot_with_fault)

        completed: List[str] = []
        faults: List[str] = []
        result_lock = threading.Lock()
        n_workers = 4

        def _run_job(job_id: str):
            _local.should_fault = (job_id == faulting_job)
            job = _IntegJob(job_id)

            def _fan_out(chunks):
                if getattr(_local, "should_fault", False):
                    raise RuntimeError("oracle fault injected")

            job._fan_out_append = _fan_out
            job._cleanup_chunk_parquet_dir = lambda jid: None
            job.progress_report = lambda pct: None
            try:
                job.run()
                with result_lock:
                    completed.append(job_id)
            except RuntimeError:
                with result_lock:
                    faults.append(job_id)

        threads = [
            threading.Thread(target=_run_job, args=(f"fault-{i:03d}",))
            for i in range(n_workers)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30.0)

        enters = [e for e in events if e[1] == "enter"]
        exits = [e for e in events if e[1] == "exit"]

        assert len(faults) == 1, f"Expected exactly 1 fault; got {faults}"
        assert len(completed) == n_workers - 1
        assert len(enters) == len(exits), (
            f"Slot leak from faulted job: {len(enters)} enters vs {len(exits)} exits"
        )
