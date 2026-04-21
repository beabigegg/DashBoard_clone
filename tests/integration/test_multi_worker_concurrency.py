# -*- coding: utf-8 -*-
"""
Multi-worker RQ concurrency integration tests.

Scenarios covered
-----------------
4.1  job idempotence after worker crash
4.2  export deduplication under concurrent submission
4.3  stale lock not claimable before TTL
4.4  stale lock claimable after TTL expiry
4.5  result write/read race safety (100 rounds, no partial reads)
4.6  queue fairness — 30 jobs / 3 workers, every worker ≥ 1

Run with:
    conda run -n mes-dashboard pytest tests/integration/test_multi_worker_concurrency.py \\
        --run-integration-real -v

Or independently (marker-based):
    conda run -n mes-dashboard pytest -m multi_worker --run-integration-real -v
"""

from __future__ import annotations

import json
import os
import signal
import threading
import time
import uuid
from typing import List

import pytest
import redis as redis_lib

from tests.integration._multi_worker_harness import MultiWorkerHarness, WorkerBarrier
from tests.integration._multi_worker_jobs import (
    job_crashable,
    job_dedup_export,
    job_read_result_loop,
    job_simple,
    job_write_result_loop,
    read_side_effects,
)

pytestmark = [pytest.mark.integration_real, pytest.mark.multi_worker]


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def mw_redis(local_redis: str):
    """Clean Redis connection for multi-worker tests; flushes before and after."""
    r = redis_lib.Redis.from_url(local_redis, decode_responses=True)
    r.flushdb()
    yield local_redis, r
    r.flushdb()


# ---------------------------------------------------------------------------
# 4.1  Job idempotence after crash
# ---------------------------------------------------------------------------


def test_job_idempotence_after_crash(mw_redis):
    """Crash worker mid-job; re-pick produces exactly one terminal side-effect."""
    redis_url, r = mw_redis
    from rq import Queue as RQQueue
    from rq.job import Job as RQJob

    job_uid = uuid.uuid4().hex[:8]
    q = RQQueue("crash_q", connection=r)

    # Phase 1: start one worker, enqueue job, wait for it to start, kill it
    harness_a = MultiWorkerHarness(
        redis_url, worker_count=1, queue_name="crash_q",
        flush_on_start=False, flush_on_stop=False,
    )
    harness_a.start()
    rq_job = q.enqueue(job_crashable, job_uid)

    ready = r.blpop(f"mwt:job_ready:{job_uid}", timeout=20)
    assert ready, "Job did not start within 20 s"

    # Kill the worker process (SimpleWorker: job runs in same process)
    worker_pid = harness_a._processes[0].pid
    try:
        os.kill(worker_pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    harness_a.stop()

    # Phase 2: push continue token (for re-run), start second worker, requeue
    r.rpush(f"mwt:job_continue:{job_uid}", "1")

    harness_b = MultiWorkerHarness(
        redis_url, worker_count=1, queue_name="crash_q",
        flush_on_start=False, flush_on_stop=False,
    )
    harness_b.start()
    try:
        fetched = RQJob.fetch(rq_job.id, connection=r)
        fetched.requeue()
    except Exception:
        q.enqueue(job_crashable, job_uid)  # fallback: re-enqueue fresh

    done = r.blpop(f"mwt:job_done:{job_uid}", timeout=20)
    harness_b.stop()

    assert done, "Job did not complete within 20 s after requeue"
    effects = read_side_effects(r, job_uid)
    completed = [e for e in effects if e["status"] == "completed"]
    assert len(completed) == 1, (
        f"Expected exactly 1 'completed' side-effect, got {len(completed)}.\n"
        f"Full effects: {effects}\n"
        f"Worker A logs:\n{harness_a.worker_logs}\n"
        f"Worker B logs:\n{harness_b.worker_logs}"
    )


# ---------------------------------------------------------------------------
# 4.2  Export deduplication under concurrent submission
# ---------------------------------------------------------------------------


def test_export_deduplication_under_concurrent_submission(mw_redis):
    """Two workers with identical fingerprint → only one actual execution."""
    redis_url, r = mw_redis
    from rq import Queue as RQQueue

    fingerprint = f"fp-{uuid.uuid4().hex[:8]}"
    q = RQQueue("dedup_q", connection=r)

    with MultiWorkerHarness(redis_url, worker_count=2, queue_name="dedup_q",
                             flush_on_start=False) as harness:
        # Enqueue two jobs with the same fingerprint
        q.enqueue(job_dedup_export, fingerprint)
        q.enqueue(job_dedup_export, fingerprint)

        # Wait for done signal (executor pushes it, reader repushes it)
        done = r.blpop(f"mwt:dedup:done:{fingerprint}", timeout=30)
        assert done, "Dedup export jobs did not complete within 30 s"

        # Give second worker a moment to finish after reading the done token
        time.sleep(0.2)

        exec_count = int(r.get(f"mwt:dedup:exec:{fingerprint}") or 0)
        result = r.get(f"mwt:dedup:result:{fingerprint}")

        assert exec_count == 1, (
            f"Expected 1 execution, got {exec_count}.\n"
            f"Worker logs: {harness.worker_logs}"
        )
        assert result is not None, "Expected a cached result key"
        parsed = json.loads(result)
        assert parsed["fingerprint"] == fingerprint


# ---------------------------------------------------------------------------
# 4.3  Stale lock not claimable before TTL expiry
# ---------------------------------------------------------------------------


def test_stale_lock_not_claimable_before_ttl(mw_redis):
    """Lock held by a crashed holder cannot be acquired within its TTL.

    Redis-level smoke test: the holder's crash is simulated by simply not
    releasing the lock.  The underlying mechanism (SET NX EX) is process-agnostic,
    so this validates the same TTL guarantee that a real subprocess crash would
    exercise (the lock key persists unchanged regardless of whether the holder
    process is alive).
    """
    _, r = mw_redis
    lock_key = f"mwt:lock:test:{uuid.uuid4().hex[:6]}"
    ttl = 5  # seconds

    acquired = r.set(lock_key, "owner-1", nx=True, ex=ttl)
    assert acquired, "Initial lock acquisition failed"

    # Simulate crash: do NOT release.  Contender tries immediately.
    contender = r.set(lock_key, "owner-2", nx=True, ex=ttl)
    assert not contender, "Lock should not be acquirable while TTL is active"


# ---------------------------------------------------------------------------
# 4.4  Stale lock claimable after TTL expiry
# ---------------------------------------------------------------------------


def test_stale_lock_claimable_after_ttl(mw_redis):
    """After TTL expires the lock can be acquired by a new contender.

    Redis-level smoke test: same rationale as test_stale_lock_not_claimable_before_ttl.
    The lock's TTL expiry is process-agnostic — the Redis key expires regardless of
    whether the original holder process is still running or was killed.
    """
    _, r = mw_redis
    lock_key = f"mwt:lock:test:{uuid.uuid4().hex[:6]}"
    ttl = 2  # seconds — short TTL for test speed

    acquired = r.set(lock_key, "owner-1", nx=True, ex=ttl)
    assert acquired, "Initial lock acquisition failed"

    # Poll for TTL expiry (unavoidable — we are testing time-based behaviour)
    deadline = time.monotonic() + ttl + 1.0
    success = False
    while time.monotonic() < deadline:
        result = r.set(lock_key, "owner-2", nx=True, ex=ttl)
        if result:
            success = True
            break
        time.sleep(0.1)

    assert success, "Lock was not acquirable within TTL + 1 s grace period"
    assert r.get(lock_key) == "owner-2", "Expected owner-2 to hold the lock"


# ---------------------------------------------------------------------------
# 4.5  Result write/read race safety
# ---------------------------------------------------------------------------


def test_result_write_read_race_safety(mw_redis):
    """100 rounds of concurrent write/read — reader never sees a partial value."""
    _, r = mw_redis
    key = f"mwt:race:{uuid.uuid4().hex[:8]}"
    value_a = json.dumps({"data": "value-alpha", "version": 1, "padding": "x" * 512})
    value_b = json.dumps({"data": "value-beta",  "version": 2, "padding": "y" * 512})

    r.set(key, value_a)
    errors: List[str] = []
    rounds = 100

    def writer() -> None:
        for _ in range(rounds):
            r.set(key, value_b)
            r.set(key, value_a)

    def reader() -> None:
        for _ in range(rounds):
            raw = r.get(key)
            if raw is None:
                errors.append("got None")
                continue
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as exc:
                errors.append(f"invalid JSON: {exc} — raw={raw!r}")
                continue
            if "data" not in parsed or "version" not in parsed:
                errors.append(f"partial value: {parsed!r}")

    t_write = threading.Thread(target=writer)
    t_read  = threading.Thread(target=reader)
    t_write.start()
    t_read.start()
    t_write.join()
    t_read.join()

    assert not errors, f"Race safety violations ({len(errors)}): {errors[:5]}"


def test_result_write_read_race_safety_cross_process(mw_redis):
    """Cross-process result write/read race: real RQ subprocess workers, no partial reads.

    Complements the thread-based test above by verifying that concurrent reads and
    writes across real worker subprocess boundaries (the actual production deployment
    scenario) never expose partially-written values.  Both workers barrier-synchronise
    before starting their loops to ensure genuine overlap.
    """
    redis_url, r = mw_redis
    from rq import Queue as RQQueue

    key = f"mwt:race:cp:{uuid.uuid4().hex[:8]}"
    rounds = 50
    phase = f"race_start_{uuid.uuid4().hex[:6]}"

    # Seed an initial value so the reader never hits None before writer starts
    r.set(key, '{"v": 0, "data": "init"}')

    with MultiWorkerHarness(redis_url, worker_count=2, queue_name="race_cp_q",
                             flush_on_start=False) as harness:
        q = RQQueue("race_cp_q", connection=r)
        q.enqueue(job_write_result_loop, key, rounds, phase)
        q.enqueue(job_read_result_loop,  key, rounds, phase)

        done1 = r.blpop(f"mwt:race:done:{key}", timeout=30)
        done2 = r.blpop(f"mwt:race:done:{key}", timeout=30)

        assert done1 and done2, (
            f"Race jobs did not both complete within 30 s.\n"
            f"Worker logs: {harness.worker_logs}"
        )

    errors_raw = r.lrange(f"mwt:race:errors:{key}", 0, -1)
    errors = [json.loads(e) for e in errors_raw]
    assert not errors, (
        f"Cross-process race safety violations ({len(errors)}): {errors[:5]}"
    )


# ---------------------------------------------------------------------------
# 4.6  Queue fairness — no starvation
# ---------------------------------------------------------------------------


def test_queue_fairness_no_starvation(mw_redis):
    """30 jobs / 3 workers: every worker processes ≥ 1 job."""
    redis_url, r = mw_redis
    from rq import Queue as RQQueue

    n_jobs    = 30
    n_workers = 3
    q = RQQueue("fairness_q", connection=r)

    with MultiWorkerHarness(redis_url, worker_count=n_workers,
                             queue_name="fairness_q",
                             flush_on_start=False) as harness:
        job_ids = [uuid.uuid4().hex[:8] for _ in range(n_jobs)]
        for jid in job_ids:
            q.enqueue(job_simple, jid)

        # Poll until all jobs have recorded side-effects
        deadline = time.monotonic() + 60.0
        while time.monotonic() < deadline:
            total = sum(len(read_side_effects(r, jid)) for jid in job_ids)
            if total >= n_jobs:
                break
            time.sleep(0.5)

        all_effects = []
        for jid in job_ids:
            all_effects.extend(read_side_effects(r, jid))

    assert len(all_effects) >= n_jobs, (
        f"Only {len(all_effects)}/{n_jobs} jobs completed.\n"
        f"Worker logs: {harness.worker_logs}"
    )
    participating_workers = {e["worker_id"] for e in all_effects}
    assert len(participating_workers) == n_workers, (
        f"Expected {n_workers} workers to participate, "
        f"got {len(participating_workers)}: {participating_workers}.\n"
        f"Worker logs: {harness.worker_logs}"
    )
