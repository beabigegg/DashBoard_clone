# -*- coding: utf-8 -*-
"""Resource History async job service.

Bridges resource-history primary queries to the RQ background worker.

Public API:
  execute_resource_history_query_job(*, job_id: str, owner: str, **query_params)  <- RQ worker entry point
  should_use_async(params: dict) -> bool
  enqueue_resource_history_query(params: dict, owner: str) -> (job_id, err)

Mirrors hold_query_job_service.py pattern (hold-history-rq-async).
"""

from __future__ import annotations

import logging
import os
from typing import Any

from mes_dashboard.services.async_query_job_service import (
    complete_job,
    enqueue_job_dynamic,
    update_job_progress,
)

logger = logging.getLogger("mes_dashboard.resource_query_job_service")

# ---------------------------------------------------------------------------
# Configuration — all frozen at import time; tests must use monkeypatch.setattr
# ---------------------------------------------------------------------------

RESOURCE_ASYNC_ENABLED: bool = os.getenv(
    "RESOURCE_ASYNC_ENABLED", "true"
).strip().lower() in {"1", "true", "yes", "on"}

RESOURCE_WORKER_QUEUE: str = os.getenv("RESOURCE_WORKER_QUEUE", "resource-history-query")

RESOURCE_JOB_TIMEOUT_SECONDS: int = int(os.getenv("RESOURCE_JOB_TIMEOUT_SECONDS", "1800"))

RESOURCE_JOB_TTL_SECONDS: int = int(os.getenv("RESOURCE_JOB_TTL_SECONDS", "3600"))

# Prefix used for Redis meta keys: resource-history:job:{job_id}:meta
_JOB_PREFIX = "resource-history"


# ---------------------------------------------------------------------------
# Async gate
# ---------------------------------------------------------------------------

def should_use_async(params: dict) -> bool:
    """Return True when async dispatch is enabled and the date range meets the threshold.

    Called by the job registry's should_enqueue guard AND by the route's inline
    dispatch check.  Uses classify_query_cost (unified policy) instead of the
    removed RESOURCE_ASYNC_DAY_THRESHOLD env var (query-path-c-elimination-cleanup, IP-7).
    """
    if not RESOURCE_ASYNC_ENABLED:
        return False
    start_date = params.get("start_date", "")
    end_date = params.get("end_date", "")
    if not start_date or not end_date:
        return False
    from mes_dashboard.core.query_cost_policy import classify_query_cost
    return classify_query_cost(
        domain="resource",
        params={"date_from": start_date, "date_to": end_date},
    ) == "ASYNC"


# ---------------------------------------------------------------------------
# Enqueue helper
# ---------------------------------------------------------------------------

def enqueue_resource_history_query(params: dict, owner: str):
    """Enqueue a resource-history primary query to the RQ worker.

    Delegates to enqueue_job_dynamic("resource-history", ...) which picks up the
    JobTypeConfig registered at module bottom.

    Returns:
        (job_id, None) on success, (None, error_message) on failure.
    """
    return enqueue_job_dynamic(
        "resource-history",
        owner=owner,
        params=params,
    )


# ---------------------------------------------------------------------------
# RQ worker entry point
# ---------------------------------------------------------------------------

def execute_resource_history_query_job(*, job_id: str, owner: str, **query_params: Any) -> None:
    """RQ worker entry point: execute resource-history primary query and spool result.

    Runs in the dedicated resource-history worker process — outside Gunicorn —
    with its own DB connections and memory space.

    Milestone implementation: coarse bracket (lowest risk, per implementation-plan constraint).
    execute_primary_query() does NOT expose a progress_callback and must not
    be modified (out-of-scope per implementation plan constraint).  The worker
    therefore emits four coarse milestones that bracket the whole call:

      5   = starting  (job received, Oracle not yet issued)
      15  = querying  (about to call execute_primary_query)
      90  = returned  (execute_primary_query returned, about to complete)
      100 = complete  (result stored, job marked done)

    This satisfies AC-3: pct sequence is non-decreasing, first pct ≤ 5, last == 100.
    Note: execute_primary_query fans out base+OEE in ThreadPoolExecutor(max_workers=2);
    DB_POOL_SIZE=2 DB_MAX_OVERFLOW=1 is set in the worker launch command to tolerate this.
    Do NOT forward `owner` into execute_primary_query — it is not a query param.
    """
    from mes_dashboard.rq_worker_preload import ensure_rq_logging
    ensure_rq_logging()

    from mes_dashboard.services.resource_dataset_cache import execute_primary_query

    logger.info("resource-history job started job_id=%s owner=%s", job_id, owner)
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
        # owner is NOT forwarded — execute_primary_query takes no owner param.
        start_date = query_params["start_date"]
        end_date = query_params["end_date"]
        result = execute_primary_query(
            start_date=start_date,
            end_date=end_date,
            granularity=query_params.get("granularity", "day"),
            workcenter_groups=query_params.get("workcenter_groups"),
            families=query_params.get("families"),
            resource_ids=query_params.get("resource_ids"),
            is_production=query_params.get("is_production", False),
            is_key=query_params.get("is_key", False),
            is_monitor=query_params.get("is_monitor", False),
            package_groups=query_params.get("package_groups"),
        )

        update_job_progress(
            _JOB_PREFIX, job_id,
            status="running", progress="priming canonical spool", pct=70, stage="finalizing",
        )

        # Prime the canonical (unfiltered) spool for this date range so that
        # subsequent queries with different filter conditions can be served from
        # DuckDB without a second Oracle round-trip.  No-op if already cached.
        try:
            from mes_dashboard.services.resource_dataset_cache import ensure_canonical_spool
            ensure_canonical_spool(start_date, end_date)
        except Exception as _ce:
            logger.warning(
                "resource-history job_id=%s: canonical spool priming failed (non-fatal): %s",
                job_id, _ce,
            )

        update_job_progress(
            _JOB_PREFIX, job_id,
            status="running", progress="finalizing", pct=90, stage="finalizing",
        )

        query_id = result["query_id"]
        update_job_progress(
            _JOB_PREFIX, job_id,
            status="running", progress="complete", pct=100, stage="complete",
        )
        complete_job(_JOB_PREFIX, job_id, query_id=query_id)

    except Exception as exc:
        logger.error(
            "resource-history job failed job_id=%s: %s", job_id, exc, exc_info=True,
        )
        complete_job(_JOB_PREFIX, job_id, error=str(exc))
        raise


# ---------------------------------------------------------------------------
# Central job registry — register at import time (IP-1, IP-3)
# ---------------------------------------------------------------------------
from mes_dashboard.services.job_registry import JobTypeConfig, register_job_type  # noqa: E402

register_job_type(JobTypeConfig(
    job_type="resource-history",
    queue_name=RESOURCE_WORKER_QUEUE,
    worker_fn=execute_resource_history_query_job,
    timeout_seconds=RESOURCE_JOB_TIMEOUT_SECONDS,
    ttl_seconds=RESOURCE_JOB_TTL_SECONDS,
    should_enqueue=should_use_async,
))
