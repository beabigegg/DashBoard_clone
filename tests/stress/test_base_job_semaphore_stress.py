# -*- coding: utf-8 -*-
"""Stress tests for base-job-semaphore-wiring: N=20 burst, no leak, no deadlock.

Companion to tests/stress/test_rq_semaphore_stress.py, which covers the
*legacy* per-domain workers. This suite covers the *unified* job core
(BaseChunkedDuckDBJob.run()) — the path EAP_ALARM/DOWNTIME/MATERIAL_TRACE/
PRODUCTION_HISTORY/REJECT_HISTORY/RESOURCE_HISTORY take when
`*_USE_UNIFIED_JOB=on` (the production default), which never wired
heavy_query_slot before base-job-semaphore-wiring.

Marked @pytest.mark.stress — excluded from Tier-1 pre-merge gate.
Weekly/nightly schedule per ci-gates.md, same as test_rq_semaphore_stress.py.

AC coverage (Tier-4):
  AC-1..AC-3 (burst N=20): test_burst_peak_bounded_no_leak
  AC-4 (mixed fault):      test_burst_no_deadlock_with_mixed_success_failure
"""

from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from typing import List, Tuple

import pytest

from mes_dashboard.core.base_chunked_duckdb_job import BaseChunkedDuckDBJob, ChunkStrategy

pytestmark = pytest.mark.stress


class _StressJob(BaseChunkedDuckDBJob):
    """Minimal concrete job — Oracle fan-out replaced by a sleep to force overlap."""

    namespace = "stress_ns"
    chunk_strategy = ChunkStrategy.SINGLE
    requires_cross_chunk_reduction = False

    def pre_query(self) -> None:
        self._chunks = [{"i": 0}]

    def build_chunk_sql(self, chunk_params):  # pragma: no cover - fan-out mocked
        return ("SELECT 1 FROM dual", {})

    def post_aggregate(self, job_duckdb_path):
        return f"/tmp/{self.namespace}/{self.job_id}.parquet"


def _recording_cm_factory(events: List[Tuple[float, str, str]], lock: threading.Lock):
    """Return a contextmanager factory recording entry/exit and a real sleep."""

    @contextmanager
    def _slot(owner: str):
        with lock:
            events.append((time.monotonic(), "enter", owner))
        try:
            time.sleep(0.02)  # simulate Oracle I/O so windows genuinely overlap
            yield True
        finally:
            with lock:
                events.append((time.monotonic(), "exit", owner))

    return _slot


def _compute_peak_concurrent(events: List[Tuple[float, str, str]]) -> int:
    sorted_events = sorted(events, key=lambda e: e[0])
    current = 0
    peak = 0
    for _ts, kind, _owner in sorted_events:
        if kind == "enter":
            current += 1
            peak = max(peak, current)
        else:
            current -= 1
    return peak


@pytest.mark.stress
class TestBaseJobSemaphoreStress:
    """N=20 burst stress tests for BaseChunkedDuckDBJob.run() slot wiring."""

    _N = 20

    def test_burst_peak_bounded_no_leak(self, monkeypatch):
        """N=20 concurrent job.run() calls: every one enters/exits the slot CM once;
        no leak; all complete.

        Uses a recording CM (not the real Redis semaphore — CI has no Redis). This
        verifies the WIRING (CM entered once per job and exits cleanly), not the
        Redis cap enforcement itself (unchanged infra, covered by
        global_concurrency's own tests).
        """
        import mes_dashboard.core.base_chunked_duckdb_job as base_mod

        events: List[Tuple[float, str, str]] = []
        lock = threading.Lock()
        monkeypatch.setattr(base_mod, "heavy_query_slot", _recording_cm_factory(events, lock))

        completed: List[str] = []
        errors: List[Tuple[str, str]] = []
        result_lock = threading.Lock()

        def _run_job(job_id: str):
            try:
                job = _StressJob(job_id)
                job._fan_out_append = lambda chunks: None
                job._cleanup_chunk_parquet_dir = lambda jid: None
                job.progress_report = lambda pct: None
                job.run()
                with result_lock:
                    completed.append(job_id)
            except Exception as exc:
                with result_lock:
                    errors.append((job_id, str(exc)))

        threads = [
            threading.Thread(target=_run_job, args=(f"stress-{i:03d}",))
            for i in range(self._N)
        ]
        t_start = time.monotonic()
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60.0)
        elapsed = time.monotonic() - t_start

        assert len(errors) == 0, f"Jobs faulted: {errors}"
        assert len(completed) == self._N, (
            f"Expected {self._N} completions; got {len(completed)} in {elapsed:.2f}s"
        )

        enters = [e for e in events if e[1] == "enter"]
        exits = [e for e in events if e[1] == "exit"]
        assert len(enters) == self._N, f"Expected {self._N} slot enters; got {len(enters)}"
        assert len(enters) == len(exits), f"Slot leak: {len(enters)} enters vs {len(exits)} exits"

        peak = _compute_peak_concurrent(events)
        assert peak <= self._N, f"Peak {peak} exceeds total jobs {self._N}"
        print(f"\n[stress] N={self._N} peak_concurrent={peak} elapsed={elapsed:.2f}s "
              f"enters={len(enters)} exits={len(exits)}")

    def test_burst_no_deadlock_with_mixed_success_failure(self, monkeypatch):
        """N=20 jobs, every 5th faults in the Oracle fan-out: no deadlock; every
        slot released even when _fan_out_append raises."""
        import mes_dashboard.core.base_chunked_duckdb_job as base_mod

        events: List[Tuple[float, str, str]] = []
        lock = threading.Lock()
        monkeypatch.setattr(base_mod, "heavy_query_slot", _recording_cm_factory(events, lock))

        completed: List[str] = []
        faults: List[str] = []
        result_lock = threading.Lock()

        def _run_job(job_id: str, should_fault: bool):
            job = _StressJob(job_id)
            if should_fault:
                def _boom(chunks):
                    raise RuntimeError("oracle stress fault")
                job._fan_out_append = _boom
            else:
                job._fan_out_append = lambda chunks: None
            job._cleanup_chunk_parquet_dir = lambda jid: None
            job.progress_report = lambda pct: None
            try:
                job.run()
                with result_lock:
                    completed.append(job_id)
            except RuntimeError:
                with result_lock:
                    faults.append(job_id)
            except Exception as exc:
                with result_lock:
                    faults.append(f"{job_id}:{exc}")

        threads = [
            threading.Thread(target=_run_job, args=(f"mixfault-{i:03d}", i % 5 == 0))
            for i in range(self._N)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60.0)

        enters = [e for e in events if e[1] == "enter"]
        exits = [e for e in events if e[1] == "exit"]

        total = len(completed) + len(faults)
        assert total == self._N, f"Not all jobs finished: {total}/{self._N}"
        assert len(faults) == 4, f"Expected 4 injected faults (every 5th); got {len(faults)}"
        assert len(enters) == len(exits), (
            f"Slot leak after mixed failure: {len(enters)} enters vs {len(exits)} exits"
        )
        print(f"\n[stress-mixed] N={self._N} completed={len(completed)} faulted={len(faults)} "
              f"enters={len(enters)} exits={len(exits)}")
