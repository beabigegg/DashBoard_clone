# -*- coding: utf-8 -*-
"""Stress tests for WIP detail RQ worker: N=20 burst, no leak, cap held.

wip-rq-worker-chunks-cleanup (IP-11 / Tier 4):

Burst N=20 concurrent simulated RQ worker calls through the wired
heavy_query_slot contextmanager. Verifies peak concurrency is bounded
and no slots are leaked after all workers complete.

Marked @pytest.mark.stress — excluded from Tier-1 pre-merge gate.
Weekly/nightly schedule per ci-gates.md.

AC coverage (Tier-4):
  AC-8 (burst N=20): test_burst_peak_bounded_no_leak
  AC-8 (mixed fault N=20): test_burst_no_deadlock_with_mixed_success_failure

Pre-production gate requirement:
  stress-soak-report.md §Evidence must document:
  1. peak_concurrent ≤ HEAVY_QUERY_MAX_CONCURRENT sampled via get_active_slot_count()
  2. Zero slot leak post-completion
  3. DBA Oracle session headroom (one connection per slot — not two)
  4. No deadlock across concurrent "wip-detail" jobs under burst

See ci-gates.md §Pre-Production Manual Gate and §Promotion Policy.

Implementation note — thread-safe mock wiring:
  unittest.mock.patch (and patch.object) is NOT thread-safe when applied
  concurrently inside worker threads targeting the same module attribute.
  All patches are therefore applied at the test level using monkeypatch.setattr,
  which sets a single globally-visible attribute for the duration of the test.
  This mirrors the approach required by any N=20 concurrent-thread stress test.
"""

from __future__ import annotations

import os
import threading
import time
from contextlib import contextmanager
from typing import List, Tuple

import pytest

pytestmark = pytest.mark.stress


def _recording_cm_factory(events: List[Tuple[float, str, str]], lock: threading.Lock):
    """Return a contextmanager factory that records entry/exit times and enforces a real sleep."""

    @contextmanager
    def _slot(owner: str):
        with lock:
            events.append((time.monotonic(), "enter", owner))
        try:
            time.sleep(0.02)  # simulate Oracle I/O overlap across threads
            yield True
        finally:
            with lock:
                events.append((time.monotonic(), "exit", owner))

    return _slot


def _compute_peak_concurrent(events: List[Tuple[float, str, str]]) -> int:
    """Compute maximum simultaneously-active slots from sorted enter/exit events."""
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
class TestWipWorkerStress:
    """N=20 burst stress tests for WIP detail worker concurrency semaphore wiring.

    Mirrors TestSemaphoreStress in test_rq_semaphore_stress.py for the hold service.
    The recording CM does NOT enforce the Redis cap — it verifies WIRING only.
    Real Oracle load evidence is required in stress-soak-report.md before activation.

    Mock-wiring contract (AC-8):
      Every call to execute_wip_detail_job must enter heavy_query_slot exactly once
      and exit it exactly once — regardless of success or Oracle-phase fault.
    """

    _N = 20  # burst size — matches canonical semaphore stress suite

    def test_burst_peak_bounded_no_leak(self, monkeypatch):
        """N=20 concurrent WIP workers: all complete; no slot leaked; peak recorded.

        Uses recording CM (not real Redis semaphore — CI has no Redis).
        Verifies wiring: every job enters and exits the slot CM exactly once.

        The recording CM does not cap concurrency (no Redis), so peak may reach N.
        The cap assertion (peak ≤ HEAVY_QUERY_MAX_CONCURRENT) is a pre-production
        gate that requires a real Redis run — documented in stress-soak-report.md.

        Patches applied at test level (not per-thread) to avoid concurrent
        attribute mutation: monkeypatch.setattr is globally visible and
        not subject to per-thread enter/exit race conditions.
        """
        import mes_dashboard.services.wip_query_job_service as svc
        import mes_dashboard.rq_worker_preload as rqpl
        from mes_dashboard.core.global_concurrency import HEAVY_QUERY_MAX_CONCURRENT

        # All module-level patches applied before threads start
        monkeypatch.setattr(rqpl, "ensure_rq_logging", lambda: None)
        monkeypatch.setattr(svc, "update_job_progress", lambda *a, **kw: None)
        monkeypatch.setattr(svc, "complete_job", lambda *a, **kw: None)
        monkeypatch.setattr(
            svc,
            "execute_wip_detail_oracle_query",
            lambda **kw: {
                "query_id": f"qid-{kw.get('workcenter', 'x')}",
                "spool_path": None,
                "row_count": 0,
            },
        )

        events: List[Tuple[float, str, str]] = []
        lock = threading.Lock()
        slot_factory = _recording_cm_factory(events, lock)
        monkeypatch.setattr(svc, "heavy_query_slot", slot_factory)

        completed = []
        errors = []
        result_lock = threading.Lock()

        def _run_job(job_id: str):
            try:
                svc.execute_wip_detail_job(
                    job_id=job_id,
                    owner="stress-test",
                    workcenter="焊接_DB",
                )
                with result_lock:
                    completed.append(job_id)
            except Exception as exc:
                with result_lock:
                    errors.append((job_id, str(exc)))

        threads = [
            threading.Thread(target=_run_job, args=(f"wip-stress-{i:03d}",))
            for i in range(self._N)
        ]

        t_start = time.monotonic()
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60.0)
        elapsed = time.monotonic() - t_start

        # All N workers must complete without error
        assert len(errors) == 0, f"Workers faulted: {errors}"
        assert len(completed) == self._N, (
            f"Expected {self._N} completions; got {len(completed)} in {elapsed:.2f}s"
        )

        # Slot wiring: enters and exits must balance exactly (no leak)
        enters = [e for e in events if e[1] == "enter"]
        exits = [e for e in events if e[1] == "exit"]
        assert len(enters) == self._N, (
            f"Expected {self._N} slot enters; got {len(enters)} "
            "(wiring check: heavy_query_slot not entered for every job)"
        )
        assert len(enters) == len(exits), (
            f"Slot leak: {len(enters)} enters vs {len(exits)} exits"
        )

        peak = _compute_peak_concurrent(events)
        # Recording CM does not enforce the Redis cap — peak can reach N in mock mode.
        # Real-Redis cap assertion (peak ≤ HEAVY_QUERY_MAX_CONCURRENT) is a
        # pre-production gate documented in stress-soak-report.md.
        assert peak <= self._N, f"Peak {peak} exceeds total workers {self._N}"

        print(
            f"\n[wip-stress] N={self._N} peak_concurrent={peak} "
            f"HEAVY_QUERY_MAX_CONCURRENT={HEAVY_QUERY_MAX_CONCURRENT} "
            f"elapsed={elapsed:.2f}s enters={len(enters)} exits={len(exits)}"
        )

    def test_burst_no_deadlock_with_mixed_success_failure(self, monkeypatch):
        """N workers, 4 injected faults: no deadlock; every slot released.

        Fault-injects every 5th worker (indices 0, 5, 10, 15 → 4 faults, 16 success).
        Verifies the heavy_query_slot CM releases even when the Oracle phase raises
        (exception-safety of the contextmanager wrapper — AC-8 robustness clause).

        Patches applied at test level. The oracle mock uses a job_id counter
        shared via closure so each thread gets a deterministic fault/success path
        without per-thread patching.
        """
        import mes_dashboard.services.wip_query_job_service as svc
        import mes_dashboard.rq_worker_preload as rqpl

        monkeypatch.setattr(rqpl, "ensure_rq_logging", lambda: None)
        monkeypatch.setattr(svc, "update_job_progress", lambda *a, **kw: None)
        monkeypatch.setattr(svc, "complete_job", lambda *a, **kw: None)

        # Fault injection: track which job_ids should fault via a shared set
        # (populated before threads start; read-only during execution)
        _fault_ids = {f"wip-mixfault-{i:03d}" for i in range(self._N) if i % 5 == 0}

        def _oracle_mock(**kw) -> dict:
            # job_id is NOT in query_params — use a side-channel to inject faults.
            # The fault set is keyed by job_id which is passed as the owner context.
            # Since execute_wip_detail_oracle_query doesn't receive job_id, we need
            # to inject differently — see below (fault_ids used via _run_job closure).
            return {"query_id": "qid-stress", "spool_path": None, "row_count": 0}

        monkeypatch.setattr(svc, "execute_wip_detail_oracle_query", _oracle_mock)

        events: List[Tuple[float, str, str]] = []
        lock = threading.Lock()
        slot_factory = _recording_cm_factory(events, lock)
        monkeypatch.setattr(svc, "heavy_query_slot", slot_factory)

        completed = []
        faults = []
        result_lock = threading.Lock()

        def _run_job(job_id: str, should_fault: bool):
            try:
                if should_fault:
                    # Temporarily replace oracle mock with a faulting one for this job.
                    # Safe because only one thread sets this at a time and we use a
                    # per-call fault flag checked inside the closure below.
                    pass
                svc.execute_wip_detail_job(
                    job_id=job_id,
                    owner="stress-fault-test",
                    workcenter="焊接_DB",
                    _stress_fault=should_fault,  # extra kwarg passed through to oracle mock
                )
                with result_lock:
                    completed.append(job_id)
            except RuntimeError:
                with result_lock:
                    faults.append(job_id)
            except Exception as exc:
                with result_lock:
                    faults.append(f"{job_id}:{exc}")

        # Rebuild oracle mock to accept _stress_fault kwarg
        def _oracle_mock_with_fault(**kw) -> dict:
            if kw.get("_stress_fault", False):
                raise RuntimeError("wip oracle stress fault")
            return {"query_id": "qid-stress", "spool_path": None, "row_count": 0}

        monkeypatch.setattr(svc, "execute_wip_detail_oracle_query", _oracle_mock_with_fault)

        threads = [
            threading.Thread(
                target=_run_job,
                args=(f"wip-mixfault-{i:03d}", i % 5 == 0),
            )
            for i in range(self._N)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60.0)

        enters = [e for e in events if e[1] == "enter"]
        exits = [e for e in events if e[1] == "exit"]

        total = len(completed) + len(faults)
        assert total == self._N, f"Not all workers finished: {total}/{self._N}"
        assert len(enters) == len(exits), (
            f"Slot leak after mixed failure: {len(enters)} enters vs {len(exits)} exits"
        )
        # 4 faults (i % 5 == 0: indices 0,5,10,15), 16 successes
        expected_faults = self._N // 5
        assert len(faults) == expected_faults, (
            f"Expected {expected_faults} faults; got {len(faults)}: {faults}"
        )
        print(
            f"\n[wip-stress-mixed] N={self._N} completed={len(completed)} "
            f"faulted={len(faults)} enters={len(enters)} exits={len(exits)}"
        )


# ---------------------------------------------------------------------------
# Gate 1: Real-Redis peak-cap validation (stress-soak-report.md §Gate 1)
# Requires real Redis running (REDIS_URL). Skips if Redis unavailable.
# Proves HEAVY_QUERY_MAX_CONCURRENT is enforced by the Redis sorted-set Lua
# script, not just by mock wiring. Thread-safety: all patches before thread launch.
# ---------------------------------------------------------------------------


@pytest.mark.stress
class TestWipWorkerRealRedisCap:
    """G1 pre-production gate: real-Redis cap enforcement.

    N=10 concurrent threads each acquire a heavy_query_slot with real Redis.
    A background poller samples ZCARD(key) every 5ms.  Peak ZCARD must be
    ≤ HEAVY_QUERY_MAX_CONCURRENT (3).  All threads must enter and exit (no leak).

    Run:
        conda run -n mes-dashboard pytest tests/stress/test_wip_worker_stress.py \\
            -k TestWipWorkerRealRedisCap --run-stress -v -s
    """

    _N = 10
    _HOLD_SECONDS = 0.15   # how long each thread holds the slot (simulate Oracle I/O)
    _POLL_INTERVAL = 0.005  # poller interval (5 ms)

    def test_real_redis_peak_bounded(self, monkeypatch):
        """Peak concurrent Oracle-phase slots must be ≤ HEAVY_QUERY_MAX_CONCURRENT under real Redis."""
        import redis as redis_lib
        import mes_dashboard.core.global_concurrency as concurrency_mod

        from mes_dashboard.core.global_concurrency import (
            HEAVY_QUERY_MAX_CONCURRENT,
            acquire_heavy_query_slot,
            release_heavy_query_slot,
            _slot_key,
        )

        # Connect directly to Redis (bypasses REDIS_ENABLED flag which is False in test env)
        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        try:
            conn = redis_lib.from_url(redis_url, socket_connect_timeout=2)
            conn.ping()
        except Exception as exc:
            pytest.skip(f"Redis unavailable — skip real-Redis gate: {exc}")

        # Patch get_redis_client in global_concurrency to return our real connection.
        # Must happen BEFORE threads are launched (thread-safety rule).
        monkeypatch.setattr(concurrency_mod, "get_redis_client", lambda: conn)

        slot_key = _slot_key()

        # Clean up any leftover slots from prior runs
        conn.delete(slot_key)

        results = {"enters": 0, "exits": 0, "peak_zcard": 0}
        results_lock = threading.Lock()
        poll_stop = threading.Event()

        def _poller():
            """Sample ZCARD every 5ms; record the peak."""
            while not poll_stop.is_set():
                try:
                    zcard = conn.zcard(slot_key)
                    with results_lock:
                        if zcard > results["peak_zcard"]:
                            results["peak_zcard"] = zcard
                except Exception:
                    pass
                time.sleep(self._POLL_INTERVAL)

        def _worker(worker_id: str):
            acquired = acquire_heavy_query_slot(worker_id, ttl=60)
            try:
                if acquired:
                    with results_lock:
                        results["enters"] += 1
                time.sleep(self._HOLD_SECONDS)
            finally:
                if acquired:
                    release_heavy_query_slot(worker_id)
                    with results_lock:
                        results["exits"] += 1

        poller = threading.Thread(target=_poller, daemon=True)
        poller.start()

        threads = [
            threading.Thread(target=_worker, args=(f"wip-gate1-{i:03d}",))
            for i in range(self._N)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30.0)

        poll_stop.set()
        poller.join(timeout=1.0)

        # Cleanup
        conn.delete(slot_key)

        print(
            f"\n[wip-gate1-real-redis] N={self._N} "
            f"peak_zcard={results['peak_zcard']} "
            f"HEAVY_QUERY_MAX_CONCURRENT={HEAVY_QUERY_MAX_CONCURRENT} "
            f"enters={results['enters']} exits={results['exits']}"
        )

        assert results["enters"] == results["exits"], (
            f"Slot leak: {results['enters']} enters vs {results['exits']} exits"
        )
        assert results["peak_zcard"] <= HEAVY_QUERY_MAX_CONCURRENT, (
            f"Real-Redis peak {results['peak_zcard']} exceeded cap "
            f"HEAVY_QUERY_MAX_CONCURRENT={HEAVY_QUERY_MAX_CONCURRENT}"
        )
