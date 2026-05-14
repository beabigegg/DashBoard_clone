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
import subprocess
import sys
import threading
import time
import uuid
from typing import List

import pytest
import redis as redis_lib

from tests.integration._multi_worker_harness import MultiWorkerHarness
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


# ---------------------------------------------------------------------------
# 4.7  container_filter_cache rebuild lock under 4 workers (AC-6)
# ---------------------------------------------------------------------------
#
# The container_filter_cache rebuild lock is process-local (file-based
# O_CREAT|O_EXCL at ``tmp/container_filter_cache.loading``) and *not* an RQ
# job — it runs synchronously inside each gunicorn worker's startup path.
# We therefore exercise it by spawning multiple subprocesses that each
# import the cache module and call _load(force=True), sharing the same
# Redis L2 backend.


_CACHE_WORKER_SCRIPT = r"""
import os, sys, json, time
project_root = os.environ["MWT_PROJECT_ROOT"]
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, "src"))

# Force a unique lock path per test invocation.
lock_path = os.environ["MWT_LOCK_PATH"]
os.environ["CONTAINER_FILTER_CACHE_LOCK_PATH"] = lock_path
os.environ["REDIS_URL"] = os.environ["MWT_REDIS_URL"]
os.environ["REDIS_ENABLED"] = "true"

# Reset Redis client globals so they pick up our test URL.
import mes_dashboard.core.redis_client as rc  # noqa: E402
rc.REDIS_URL = os.environ["MWT_REDIS_URL"]
rc.REDIS_ENABLED = True
rc._REDIS_CLIENT = None

import mes_dashboard.services.container_filter_cache as cache_mod  # noqa: E402
from pathlib import Path  # noqa: E402

# Point lock at our test path.
cache_mod._LOCK_PATH = Path(lock_path)

# Patch read_sql_df with a slow Oracle stub controlled via a Redis flag.
# Each call to the patched stub increments a Redis counter so the parent
# test can count Oracle hits.  The stub sleeps for `oracle_delay_s` seconds
# (default 2) to give losing workers time to enter the polling branch.
import pandas as pd  # noqa: E402

_redis = rc.get_redis_client()

def _fake_read_sql_df(sql, caller=""):
    _redis.incr(os.environ["MWT_HIT_COUNTER_KEY"])
    time.sleep(float(os.environ.get("MWT_ORACLE_DELAY_S", "2.0")))
    return pd.DataFrame([
        {"PJ_TYPE": "A", "PRODUCTLINENAME": "PKG-1", "PJ_BOP": "BOP-A", "PJ_FUNCTION": "FN-X"},
        {"PJ_TYPE": "B", "PRODUCTLINENAME": "PKG-2", "PJ_BOP": "BOP-B", "PJ_FUNCTION": "FN-Y"},
    ])

cache_mod.read_sql_df = _fake_read_sql_df

# Optional: barrier-style start so workers race genuinely.
barrier_key = os.environ.get("MWT_BARRIER_KEY")
expected_n = int(os.environ.get("MWT_BARRIER_N", "1"))
if barrier_key:
    n = _redis.incr(barrier_key)
    _redis.expire(barrier_key, 60)
    if n == expected_n:
        for _ in range(expected_n):
            _redis.rpush(barrier_key + ":go", "1")
        _redis.expire(barrier_key + ":go", 60)
    _redis.blpop(barrier_key + ":go", timeout=30)

# Run the cache load (this is what every gunicorn worker does at startup).
success = cache_mod._load(force=True)

# Emit our payload so the test can verify equivalence.
result = {
    "success": success,
    "pj_types": list(cache_mod._CACHE.get("pj_types") or []),
    "packages": list(cache_mod._CACHE.get("packages") or []),
    "indices": dict(cache_mod._CACHE.get("indices") or {}),
}
out_key = os.environ["MWT_RESULT_KEY"] + ":" + os.environ["MWT_WORKER_ID"]
_redis.set(out_key, json.dumps(result), ex=120)
print(f"WORKER_{os.environ['MWT_WORKER_ID']}_DONE", flush=True)
"""


def _spawn_cache_workers(
    redis_url: str,
    n: int,
    lock_path: str,
    hit_key: str,
    result_key: str,
    barrier_key: str | None = None,
    oracle_delay_s: float = 2.0,
    project_root: str | None = None,
):
    import subprocess
    from pathlib import Path as _Path

    if project_root is None:
        project_root = str(_Path(__file__).resolve().parents[2])

    procs = []
    for i in range(n):
        env = os.environ.copy()
        env.update({
            "MWT_REDIS_URL": redis_url,
            "MWT_LOCK_PATH": lock_path,
            "MWT_HIT_COUNTER_KEY": hit_key,
            "MWT_RESULT_KEY": result_key,
            "MWT_WORKER_ID": str(i),
            "MWT_PROJECT_ROOT": project_root,
            "MWT_ORACLE_DELAY_S": str(oracle_delay_s),
        })
        if barrier_key:
            env["MWT_BARRIER_KEY"] = barrier_key
            env["MWT_BARRIER_N"] = str(n)
        proc = subprocess.Popen(
            [sys.executable, "-c", _CACHE_WORKER_SCRIPT],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        procs.append(proc)
    return procs


def test_container_filter_cache_lock_under_4_workers(mw_redis, tmp_path):
    """4 workers race to rebuild the cache; only one hits Oracle (AC-6, PHF-05).

    Verifies the file-based ``O_CREAT|O_EXCL`` lock at
    ``tmp/container_filter_cache.loading`` ensures exactly one process
    queries Oracle while the others poll Redis L2 and reuse the result.
    All four must end up with identical payloads.
    """
    redis_url, r = mw_redis
    lock_path = str(tmp_path / "container_filter_cache.loading")
    hit_key = f"mwt:cache:hit:{uuid.uuid4().hex[:6]}"
    result_key = f"mwt:cache:result:{uuid.uuid4().hex[:6]}"
    barrier_key = f"mwt:cache:barrier:{uuid.uuid4().hex[:6]}"

    r.delete(hit_key, result_key, barrier_key, barrier_key + ":go")

    procs = _spawn_cache_workers(
        redis_url=redis_url,
        n=4,
        lock_path=lock_path,
        hit_key=hit_key,
        result_key=result_key,
        barrier_key=barrier_key,
        oracle_delay_s=2.0,
    )

    try:
        # Workers should all finish within 120 s (2 s Oracle + up to 90 s lock wait).
        for proc in procs:
            try:
                proc.wait(timeout=120)
            except subprocess.TimeoutExpired:
                proc.kill()
                pytest.fail(
                    f"Worker {procs.index(proc)} timed out after 120 s; "
                    f"stderr={proc.stderr.read() if proc.stderr else ''}"
                )
            assert proc.returncode == 0, (
                f"Worker {procs.index(proc)} exited non-zero ({proc.returncode}); "
                f"stderr={proc.stderr.read() if proc.stderr else ''}"
            )
    finally:
        for proc in procs:
            if proc.poll() is None:
                proc.kill()

    # Exactly one worker should have hit Oracle.
    hits = int(r.get(hit_key) or 0)
    assert hits == 1, f"Expected exactly 1 Oracle hit, got {hits}"

    # All four workers must have reported a successful load with the same payload.
    payloads = []
    for i in range(4):
        raw = r.get(f"{result_key}:{i}")
        assert raw, f"Worker {i} did not record a result"
        payloads.append(json.loads(raw))
    for p in payloads:
        assert p["success"] is True, f"Worker reported failure: {p}"
    canonical = payloads[0]["indices"]
    for i, p in enumerate(payloads[1:], start=1):
        assert p["indices"] == canonical, (
            f"Worker {i} indices diverge from worker 0:\n"
            f"worker_0={canonical}\nworker_{i}={p['indices']}"
        )


def test_lock_holder_crash_releases_lock(mw_redis, tmp_path):
    """When the lock holder crashes, contenders fall through after 90 s timeout.

    The current D4 design does NOT include a stale-sentinel reaper — instead,
    losers poll Redis L2 for up to 90 s, then fall through to direct Oracle in
    "degraded mode" (still query Oracle without holding the lock).

    This test:
      1. Pre-creates the lock file (simulates a crashed holder that never
         released the sentinel)
      2. Spawns a single worker — it must NOT acquire the lock and must
         either reuse a pre-populated L2 entry or fall through to Oracle
      3. Verifies the worker completes (does not hang forever) and returns a
         successful payload

    Since polling 90 s would make the test slow, we monkey-patch the lock-poll
    constants down to 1 s × 2 iterations (2 s total) inside the spawned worker
    script.
    """
    redis_url, r = mw_redis
    lock_path = tmp_path / "container_filter_cache.loading"
    # Pre-create the stale lock file BEFORE the worker starts.
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.touch()
    assert lock_path.exists()

    hit_key = f"mwt:cache:hit:{uuid.uuid4().hex[:6]}"
    result_key = f"mwt:cache:result:{uuid.uuid4().hex[:6]}"

    # Patch the poll constants down for fast test execution by appending a
    # snippet to the worker script's env-based override.  We do this by
    # spawning a custom script that imports cache_mod then overrides the
    # constants before calling _load.
    custom_script = (
        _CACHE_WORKER_SCRIPT.replace(
            "cache_mod._LOCK_PATH = Path(lock_path)",
            (
                "cache_mod._LOCK_PATH = Path(lock_path)\n"
                "cache_mod._LOCK_POLL_INTERVAL_S = 1\n"
                "cache_mod._LOCK_MAX_POLL_ITERATIONS = 2\n"
            ),
        )
    )

    env = os.environ.copy()
    env.update({
        "MWT_REDIS_URL": redis_url,
        "MWT_LOCK_PATH": str(lock_path),
        "MWT_HIT_COUNTER_KEY": hit_key,
        "MWT_RESULT_KEY": result_key,
        "MWT_WORKER_ID": "0",
        "MWT_PROJECT_ROOT": str(__import__('pathlib').Path(__file__).resolve().parents[2]),
        "MWT_ORACLE_DELAY_S": "0.1",
    })

    import subprocess as _sub
    proc = _sub.Popen(
        [sys.executable, "-c", custom_script],
        env=env,
        stdout=_sub.PIPE,
        stderr=_sub.PIPE,
        text=True,
    )
    try:
        stdout, stderr = proc.communicate(timeout=30)
    except _sub.TimeoutExpired:
        proc.kill()
        pytest.fail("Worker hung waiting on stale lock — fall-through path broken")

    assert proc.returncode == 0, (
        f"Worker exited non-zero (rc={proc.returncode}); stderr={stderr}"
    )
    raw = r.get(f"{result_key}:0")
    assert raw, "Worker did not write a result payload"
    payload = json.loads(raw)
    assert payload["success"] is True, f"Worker reported failure: {payload}"
    # Oracle must have been hit at least once — the worker fell through to
    # direct Oracle in degraded mode because the lock was held by a phantom.
    hits = int(r.get(hit_key) or 0)
    assert hits >= 1, "Worker should have hit Oracle in degraded fall-through mode"
