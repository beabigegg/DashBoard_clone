# -*- coding: utf-8 -*-
"""Hold History async job service.

Bridges hold-history primary queries to the RQ background worker.

Public API:
  execute_hold_history_query_job(*, job_id, owner, **query_params)  <- RQ worker entry point
  should_use_async(params: dict) -> bool
  enqueue_hold_history_query(params: dict, owner: str) -> (job_id, err)

Phase 3-B of docs/dynamic-rq-migration-plan.md.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

from mes_dashboard.services.async_query_job_service import (
    complete_job,
    enqueue_job_dynamic,
    update_job_progress,
)

logger = logging.getLogger("mes_dashboard.hold_query_job_service")

# ---------------------------------------------------------------------------
# Configuration — all frozen at import time; tests must use monkeypatch.setattr
# ---------------------------------------------------------------------------

HOLD_ASYNC_ENABLED: bool = os.getenv(
    "HOLD_ASYNC_ENABLED", "true"
).strip().lower() in {"1", "true", "yes", "on"}

HOLD_ASYNC_DAY_THRESHOLD: int = int(os.getenv("HOLD_ASYNC_DAY_THRESHOLD", "90"))

HOLD_WORKER_QUEUE: str = os.getenv("HOLD_WORKER_QUEUE", "hold-history-query")

HOLD_JOB_TIMEOUT_SECONDS: int = int(os.getenv("HOLD_JOB_TIMEOUT_SECONDS", "1800"))

HOLD_JOB_TTL_SECONDS: int = int(os.getenv("HOLD_JOB_TTL_SECONDS", "3600"))

# Prefix used for Redis meta keys: hold-history:job:{job_id}:meta
_JOB_PREFIX = "hold-history"


# ---------------------------------------------------------------------------
# Async gate
# ---------------------------------------------------------------------------

def should_use_async(params: dict) -> bool:
    """Return True when async dispatch is enabled and the date range meets the threshold.

    Called by the job registry's should_enqueue guard AND by the route's inline
    dispatch check.  module-level constants are read at call time so that
    monkeypatch.setattr() overrides work in tests.
    """
    if not HOLD_ASYNC_ENABLED:
        return False
    start_date = params.get("start_date", "")
    end_date = params.get("end_date", "")
    if not start_date or not end_date:
        return False
    try:
        sd = datetime.strptime(start_date, "%Y-%m-%d")
        ed = datetime.strptime(end_date, "%Y-%m-%d")
        return (ed - sd).days >= HOLD_ASYNC_DAY_THRESHOLD
    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------------------------
# Enqueue helper
# ---------------------------------------------------------------------------

def enqueue_hold_history_query(params: dict, owner: str):
    """Enqueue a hold-history primary query to the RQ worker.

    Delegates to enqueue_job_dynamic("hold-history", ...) which picks up the
    JobTypeConfig registered at module bottom.

    Returns:
        (job_id, None) on success, (None, error_message) on failure.
    """
    return enqueue_job_dynamic(
        "hold-history",
        owner=owner,
        params=params,
    )


# ---------------------------------------------------------------------------
# RQ worker entry point
# ---------------------------------------------------------------------------

def execute_hold_history_query_job(*, job_id: str, owner: str, **query_params: Any) -> None:
    """RQ worker entry point: execute hold-history primary query and spool result.

    Runs in the dedicated hold-history worker process — outside Gunicorn —
    with its own DB connections and memory space.

    Milestone implementation: coarse bracket (recommended, lowest risk).
    execute_primary_query() does NOT expose a progress_callback and must not
    be modified (out-of-scope per implementation plan constraint).  The worker
    therefore emits four coarse milestones that bracket the whole call:

      5   = starting  (job received, Oracle not yet issued)
      15  = querying  (about to call execute_primary_query)
      90  = returned  (execute_primary_query returned, about to complete)
      100 = complete  (result stored, job marked done)

    This satisfies AC-4: pct sequence is non-decreasing, first pct ≤ 5, last == 100.
    """
    from mes_dashboard.rq_worker_preload import ensure_rq_logging
    ensure_rq_logging()

    from mes_dashboard.services.hold_dataset_cache import execute_primary_query

    logger.info("hold-history job started job_id=%s owner=%s", job_id, owner)
    update_job_progress(
        _JOB_PREFIX, job_id,
        status="started", progress="initializing", pct=5, stage="starting",
    )

    try:
        update_job_progress(
            _JOB_PREFIX, job_id,
            status="running", progress="querying Oracle", pct=15, stage="querying",
        )

        # Wrap execute_primary_query unmodified (IP constraint: do NOT add
        # progress_callback or alter signature/body).
        result = execute_primary_query(
            start_date=query_params["start_date"],
            end_date=query_params["end_date"],
            hold_type=query_params.get("hold_type", "quality"),
            record_type=query_params.get("record_type", "new"),
        )

        update_job_progress(
            _JOB_PREFIX, job_id,
            status="running", progress="finalizing", pct=90, stage="finalizing",
        )

        query_id = result["query_id"]

        # Prime the canonical spool for this date range so subsequent queries
        # (any hold_type / record_type combination) are served synchronously
        # by the route's spool-existence check without dispatching a new job.
        # Mirrors resource_query_job_service.ensure_canonical_spool() pattern.
        # This is a no-op (cheap Redis check) when execute_primary_query already
        # stored the spool — which is the normal case.
        try:
            from mes_dashboard.services.hold_dataset_cache import ensure_canonical_spool
            ensure_canonical_spool(
                query_params["start_date"],
                query_params["end_date"],
            )
        except Exception as _exc:
            logger.warning("hold-history canonical spool prime failed (non-fatal): %s", _exc)

        update_job_progress(
            _JOB_PREFIX, job_id,
            status="running", progress="complete", pct=100, stage="complete",
        )
        complete_job(_JOB_PREFIX, job_id, query_id=query_id)

    except Exception as exc:
        logger.error(
            "hold-history job failed job_id=%s: %s", job_id, exc, exc_info=True,
        )
        complete_job(_JOB_PREFIX, job_id, error=str(exc))
        raise


# ---------------------------------------------------------------------------
# Central job registry — register at import time (IP-1, IP-3)
# ---------------------------------------------------------------------------
from mes_dashboard.services.job_registry import JobTypeConfig, register_job_type  # noqa: E402

register_job_type(JobTypeConfig(
    job_type="hold-history",
    queue_name=HOLD_WORKER_QUEUE,
    worker_fn=execute_hold_history_query_job,
    timeout_seconds=HOLD_JOB_TIMEOUT_SECONDS,
    ttl_seconds=HOLD_JOB_TTL_SECONDS,
    should_enqueue=should_use_async,
))
