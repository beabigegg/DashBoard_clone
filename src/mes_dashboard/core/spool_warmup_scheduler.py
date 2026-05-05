# -*- coding: utf-8 -*-
"""Spool warmup scheduler with distributed leader lock.

Runs inside each gunicorn worker on startup, but only the worker that wins the
Redis leader lock will enqueue warmup jobs to the RQ warmup queue.  Periodic
refresh also goes through the same leader lock so jobs are never duplicated.

Warmup coverage (this change):
  - reject_dataset       — canonical date-range dataset, 90 days
  - yield_alert_dataset  — canonical date-range dataset
  - hold_dataset         — query_id primarily determined by date
  - resource_dataset     — canonical base dataset (date-range only, task 2.2/3.3)

Explicitly excluded from warmup — do NOT add without a design review:
  - production-history   — high data volume + pj_types variation (on-demand only)

GUARD: test_warmup_scheduler::test_production_history_not_in_warmup_jobs
enforces that production_history never appears in _WARMUP_JOBS (tasks 3.4/10.5).
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Optional

from mes_dashboard.core.exceptions import LockUnavailableError
from mes_dashboard.core.redis_client import (
    REDIS_ENABLED,
    get_redis_client,
    try_acquire_lock,
    release_lock,
)

logger = logging.getLogger("mes_dashboard.spool_warmup_scheduler")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
WARMUP_SCHEDULER_ENABLED = os.getenv("WARMUP_SCHEDULER_ENABLED", "true").strip().lower() in {
    "1", "true", "yes", "on"
}
WARMUP_QUEUE_NAME = os.getenv("WARMUP_QUEUE_NAME", "warmup")
WARMUP_LEADER_LOCK_NAME = "spool_warmup_leader"
WARMUP_LEADER_LOCK_TTL = int(os.getenv("WARMUP_LEADER_LOCK_TTL", "120"))
WARMUP_INTERVAL_SECONDS = max(int(os.getenv("WARMUP_INTERVAL_SECONDS", "3600")), 60)
WARMUP_JOB_TIMEOUT = int(os.getenv("WARMUP_JOB_TIMEOUT", "1800"))

# ---------------------------------------------------------------------------
# RQ worker functions (executed inside RQ worker process)
# ---------------------------------------------------------------------------


def _warmup_reject_dataset_job() -> None:
    """RQ worker function: warm reject dataset spool."""
    try:
        from mes_dashboard.services import reject_dataset_cache
        result = reject_dataset_cache.ensure_dataset_loaded()
        logger.info(
            "Warmup [reject_dataset] complete query_id=%s cache_hit=%s",
            result.get("query_id") if result else None,
            result.get("cache_hit") if result else None,
        )
    except Exception as exc:
        logger.warning("Warmup [reject_dataset] failed: %s", exc)


def _warmup_yield_alert_dataset_job() -> None:
    """RQ worker function: warm yield-alert dataset spool."""
    try:
        from mes_dashboard.services import yield_alert_dataset_cache
        result = yield_alert_dataset_cache.ensure_dataset_loaded()
        logger.info(
            "Warmup [yield_alert_dataset] complete query_id=%s cache_hit=%s",
            result.get("query_id") if result else None,
            result.get("cache_hit") if result else None,
        )
    except Exception as exc:
        logger.warning("Warmup [yield_alert_dataset] failed: %s", exc)


def _warmup_hold_dataset_job() -> None:
    """RQ worker function: warm hold dataset spool."""
    try:
        from mes_dashboard.services import hold_dataset_cache
        result = hold_dataset_cache.ensure_dataset_loaded()
        logger.info(
            "Warmup [hold_dataset] complete query_id=%s cache_hit=%s",
            result.get("query_id") if result else None,
            result.get("cache_hit") if result else None,
        )
    except Exception as exc:
        logger.warning("Warmup [hold_dataset] failed: %s", exc)


def _warmup_resource_dataset_job() -> None:
    """RQ worker function: warm resource canonical base dataset spool.

    Only called once resource-history canonical base dataset design is complete
    (task 2.2 / 3.3).  Do not add to _WARMUP_JOBS until that task is done.
    """
    try:
        from mes_dashboard.services import resource_dataset_cache
        result = resource_dataset_cache.ensure_dataset_loaded()
        logger.info(
            "Warmup [resource_dataset] complete query_id=%s cache_hit=%s",
            result.get("query_id") if result else None,
            result.get("cache_hit") if result else None,
        )
    except Exception as exc:
        logger.warning("Warmup [resource_dataset] failed: %s", exc)


# ---------------------------------------------------------------------------
# Warmup job registry
# production-history is intentionally absent — it must NOT be added here.
# ---------------------------------------------------------------------------
_WARMUP_JOBS = [
    ("warmup-reject-dataset", _warmup_reject_dataset_job),
    ("warmup-yield-alert-dataset", _warmup_yield_alert_dataset_job),
    ("warmup-hold-dataset", _warmup_hold_dataset_job),
    # resource-history canonical base dataset design is complete (task 2.2);
    # warmup enabled per task 3.3:
    ("warmup-resource-dataset", _warmup_resource_dataset_job),
    # production-history intentionally absent — do NOT add here (task 3.4).
]

# ---------------------------------------------------------------------------
# Enqueue helpers
# ---------------------------------------------------------------------------


def _enqueue_warmup_jobs() -> int:
    """Enqueue all warmup jobs to the warmup RQ queue.  Returns number enqueued."""
    try:
        from rq import Queue
    except ImportError:
        logger.debug("rq not installed; skipping warmup enqueue")
        return 0

    conn = get_redis_client()
    if conn is None:
        return 0

    try:
        queue = Queue(WARMUP_QUEUE_NAME, connection=conn)
    except Exception as exc:
        logger.warning("Cannot create warmup RQ queue: %s", exc)
        return 0

    enqueued = 0
    for job_id_prefix, worker_fn in _WARMUP_JOBS:
        try:
            queue.enqueue(
                worker_fn,
                job_timeout=WARMUP_JOB_TIMEOUT,
                result_ttl=300,
                failure_ttl=300,
            )
            enqueued += 1
            logger.debug("Enqueued warmup job: %s", job_id_prefix)
        except Exception as exc:
            logger.warning("Failed to enqueue warmup job %s: %s", job_id_prefix, exc)

    return enqueued


def run_warmup_cycle() -> bool:
    """Try to acquire leader lock and enqueue warmup jobs.

    Returns True if this worker became the leader and enqueued jobs.
    Multiple workers call this on startup; only the leader enqueues.
    """
    if not WARMUP_SCHEDULER_ENABLED:
        return False

    if not REDIS_ENABLED:
        return False

    try:
        if not try_acquire_lock(WARMUP_LEADER_LOCK_NAME, ttl_seconds=WARMUP_LEADER_LOCK_TTL, fail_mode="raise"):
            logger.debug("Warmup scheduler: another worker holds the leader lock, skipping")
            return False
    except LockUnavailableError as exc:
        logger.warning("Warmup scheduler: Redis unavailable, skipping leader election (%s)", exc)
        return False

    try:
        count = _enqueue_warmup_jobs()
        logger.info("Warmup scheduler: enqueued %d warmup jobs (leader)", count)
        return True
    finally:
        release_lock(WARMUP_LEADER_LOCK_NAME)


# ---------------------------------------------------------------------------
# Background scheduler thread
# ---------------------------------------------------------------------------

_SCHEDULER_THREAD: Optional[threading.Thread] = None
_STOP_EVENT = threading.Event()


def _scheduler_loop() -> None:
    logger.info(
        "Spool warmup scheduler started (interval=%ss queue=%s)",
        WARMUP_INTERVAL_SECONDS,
        WARMUP_QUEUE_NAME,
    )
    while not _STOP_EVENT.wait(WARMUP_INTERVAL_SECONDS):
        try:
            run_warmup_cycle()
        except Exception as exc:
            logger.warning("Warmup scheduler cycle failed: %s", exc)
    logger.info("Spool warmup scheduler stopped")


def init_warmup_scheduler(app=None) -> None:
    """Start the warmup scheduler background thread and run initial warmup cycle.

    Safe to call from every gunicorn worker — the leader lock prevents duplicate
    job enqueueing.
    """
    if not WARMUP_SCHEDULER_ENABLED:
        return

    if not REDIS_ENABLED:
        return

    # Run initial warmup immediately (leader-elected)
    try:
        run_warmup_cycle()
    except Exception as exc:
        logger.warning("Initial warmup cycle failed: %s", exc)

    global _SCHEDULER_THREAD
    if app is not None and app.config.get("TESTING"):
        return
    if _SCHEDULER_THREAD and _SCHEDULER_THREAD.is_alive():
        return

    _STOP_EVENT.clear()
    _SCHEDULER_THREAD = threading.Thread(
        target=_scheduler_loop,
        daemon=True,
        name="spool-warmup-scheduler",
    )
    _SCHEDULER_THREAD.start()


def stop_warmup_scheduler(timeout: int = 5) -> None:
    global _SCHEDULER_THREAD
    if _SCHEDULER_THREAD is None:
        return
    _STOP_EVENT.set()
    _SCHEDULER_THREAD.join(timeout=timeout)
    _SCHEDULER_THREAD = None
