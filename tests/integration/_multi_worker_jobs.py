# -*- coding: utf-8 -*-
"""
Mock RQ job functions for multi-worker concurrency tests.

Side-effect record schema
--------------------------
Every job records execution via RPUSH to ``mwt:sideeffect:{job_id}``.
Each entry is JSON with the following fields:

    {
        "pid":       int,    # os.getpid() inside the worker/horse process
        "worker_id": str,    # MWT_WORKER_ID env var (set per-worker by harness)
        "ts":        float,  # time.time() at recording
        "status":    str,    # "completed" | "started" | "dedup_executed"
        "job_id":    str     # mirrors the job_id argument for easy lookup
    }

Reading back
------------
    from tests.integration._multi_worker_jobs import read_side_effects
    effects = read_side_effects(r, job_id)   # list[dict]
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List

import redis as redis_lib


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _conn() -> redis_lib.Redis:
    url = os.environ.get("MWT_REDIS_URL", "redis://localhost:6379/15")
    return redis_lib.Redis.from_url(url, decode_responses=True)


def _worker_id() -> str:
    return os.environ.get("MWT_WORKER_ID", "?")


def _push_effect(r: redis_lib.Redis, job_id: str, status: str, **extra: Any) -> None:
    record: Dict[str, Any] = {
        "pid": os.getpid(),
        "worker_id": _worker_id(),
        "ts": time.time(),
        "status": status,
        "job_id": job_id,
        **extra,
    }
    r.rpush(f"mwt:sideeffect:{job_id}", json.dumps(record))


# ---------------------------------------------------------------------------
# Public helpers (usable in test assertions)
# ---------------------------------------------------------------------------


def read_side_effects(r: redis_lib.Redis, job_id: str) -> List[Dict[str, Any]]:
    """Load and parse all side-effect records for *job_id*."""
    raw = r.lrange(f"mwt:sideeffect:{job_id}", 0, -1)
    return [json.loads(x) for x in raw]


# ---------------------------------------------------------------------------
# Job functions
# ---------------------------------------------------------------------------


def job_simple(job_id: str) -> None:
    """Trivial job: records worker_id for distribution assertions.

    A 10 ms work simulation ensures multiple workers have time to compete
    for queue items during the fairness test (not a timing workaround).
    """
    time.sleep(0.01)
    _push_effect(_conn(), job_id, "completed")


def job_crashable(job_id: str) -> None:
    """Idempotent job used for crash-recovery tests.

    Execution flow:
      1. Idempotency gate: if "completed" already recorded, skip and signal done.
      2. Signal "ready" with this process PID (test reads PID to kill this worker).
      3. Wait for "continue" token (test pushes this before requeue).
      4. Record "completed" and signal "done".

    In the crash scenario, the worker is SIGKILL'd at step 3.
    On re-run, step 1 is satisfied (no completed yet) so the job finishes cleanly.
    """
    r = _conn()
    effects_key = f"mwt:sideeffect:{job_id}"

    # Idempotency gate
    existing = r.lrange(effects_key, 0, -1)
    if any(json.loads(e).get("status") == "completed" for e in existing):
        r.rpush(f"mwt:job_done:{job_id}", "1")
        return

    # Signal ready — test reads this PID to kill the worker
    r.rpush(f"mwt:job_ready:{job_id}", os.getpid())
    r.expire(f"mwt:job_ready:{job_id}", 60)

    # Wait for continue signal from test (or killed here in crash scenario)
    r.blpop(f"mwt:job_continue:{job_id}", timeout=30)

    # Record completion
    _push_effect(r, job_id, "completed")
    r.rpush(f"mwt:job_done:{job_id}", "1")


def job_write_result_loop(key: str, rounds: int, barrier_phase: str = "race_start") -> None:
    """Alternates between two valid JSON values on *key* for *rounds* iterations.

    Synchronises with a concurrent reader at *barrier_phase* so both run
    simultaneously.  Signals completion via ``mwt:race:done:{key}``.
    """
    r = _conn()
    url = os.environ.get("MWT_REDIS_URL", "redis://localhost:6379/15")
    from tests.integration._multi_worker_harness import WorkerBarrier  # type: ignore[import]

    value_a = json.dumps({"v": 1, "data": "alpha" * 64, "pid": os.getpid()})
    value_b = json.dumps({"v": 2, "data": "beta"  * 64, "pid": os.getpid()})

    WorkerBarrier(url).wait(barrier_phase, n=2)
    for _ in range(rounds):
        r.set(key, value_a)
        r.set(key, value_b)
    r.rpush(f"mwt:race:done:{key}", "writer")


def job_read_result_loop(key: str, rounds: int, barrier_phase: str = "race_start") -> None:
    """Reads *key* for *rounds* iterations and validates each value is complete JSON.

    Synchronises with a concurrent writer at *barrier_phase*.
    Pushes any structural violations to ``mwt:race:errors:{key}``.
    Signals completion via ``mwt:race:done:{key}``.
    """
    r = _conn()
    url = os.environ.get("MWT_REDIS_URL", "redis://localhost:6379/15")
    from tests.integration._multi_worker_harness import WorkerBarrier  # type: ignore[import]

    errors: list = []
    WorkerBarrier(url).wait(barrier_phase, n=2)
    for _ in range(rounds):
        raw = r.get(key)
        if raw is None:
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            errors.append(f"invalid JSON: {exc} — raw={raw[:60]!r}")
            continue
        if "v" not in parsed or "data" not in parsed:
            errors.append(f"partial value missing fields: {list(parsed.keys())}")
    if errors:
        r.rpush(f"mwt:race:errors:{key}", *[json.dumps(e) for e in errors[:10]])
    r.rpush(f"mwt:race:done:{key}", "reader")


def job_dedup_export(fingerprint: str, barrier_phase: str = "dedup_start") -> None:
    """Simulates export deduplication: only one of two concurrent workers executes.

    Both workers synchronise at *barrier_phase* to ensure simultaneous dedup-lock
    contention.  The lock winner executes (increments exec counter + stores result).
    The loser waits for the done signal, then reads the cached result.
    """
    r = _conn()
    url = os.environ.get("MWT_REDIS_URL", "redis://localhost:6379/15")

    from tests.integration._multi_worker_harness import WorkerBarrier  # type: ignore[import]

    barrier = WorkerBarrier(url)
    barrier.wait(barrier_phase, n=2)

    lock_key   = f"mwt:dedup:lock:{fingerprint}"
    exec_key   = f"mwt:dedup:exec:{fingerprint}"
    result_key = f"mwt:dedup:result:{fingerprint}"
    done_key   = f"mwt:dedup:done:{fingerprint}"

    acquired = r.set(lock_key, os.getpid(), nx=True, ex=10)
    if acquired:
        r.incr(exec_key)
        time.sleep(0.05)  # Simulate export work
        r.set(result_key, json.dumps({"fingerprint": fingerprint, "data": "export_result"}))
        r.rpush(done_key, "1")  # Release the waiting worker
    else:
        r.blpop(done_key, timeout=15)
        r.rpush(done_key, "1")  # Restore token for any additional waiters
