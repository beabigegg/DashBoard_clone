# -*- coding: utf-8 -*-
"""Reject query async job service.

Bridges reject-history primary queries to the RQ background worker.

Public API:
  should_use_async(mode, start_date, end_date) -> bool
  enqueue_reject_query(mode, params) -> (job_id, error)
  execute_reject_query_job(job_id, mode, params)   ← RQ worker entry point
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import date
from typing import Any, Dict, Optional, Tuple
try:
    from rq import Retry
except Exception:  # pragma: no cover - optional dependency path
    Retry = None  # type: ignore[assignment]
from mes_dashboard.services.async_query_job_service import (
    complete_job,
    enqueue_job,
    is_async_available,
    update_job_progress,
)

logger = logging.getLogger("mes_dashboard.reject_query_job_service")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
REJECT_ASYNC_ENABLED = os.getenv("REJECT_ASYNC_ENABLED", "true").strip().lower() in {
    "1", "true", "yes", "on",
}
REJECT_ASYNC_DAY_THRESHOLD = int(os.getenv("REJECT_ASYNC_DAY_THRESHOLD", "10"))
REJECT_WORKER_QUEUE = os.getenv("REJECT_WORKER_QUEUE", "reject-query")
REJECT_JOB_TTL_SECONDS = int(os.getenv("REJECT_JOB_TTL_SECONDS", "3600"))
REJECT_JOB_TIMEOUT_SECONDS = int(os.getenv("REJECT_JOB_TIMEOUT_SECONDS", "1800"))

# Prefix used for Redis meta keys: reject:job:{job_id}:meta
_JOB_PREFIX = "reject"


def _build_retry():
    if Retry is None:
        return None
    return Retry(max=2, interval=[30, 60])


# ---------------------------------------------------------------------------
# Async decision
# ---------------------------------------------------------------------------

def should_use_async(mode: str, start_date: Optional[str], end_date: Optional[str]) -> bool:
    """Return True if this query should use the async RQ path.

    Conditions:
    - REJECT_ASYNC_ENABLED is True
    - mode is "date_range"
    - date range > REJECT_ASYNC_DAY_THRESHOLD (default 10 days)
    - is_async_available() returns True (workers are registered)
    """
    if not REJECT_ASYNC_ENABLED:
        return False
    if mode != "date_range":
        return False
    if not start_date or not end_date:
        return False
    try:
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
        days = (end - start).days
        if days <= REJECT_ASYNC_DAY_THRESHOLD:
            return False
    except (ValueError, TypeError):
        return False
    return is_async_available()


# ---------------------------------------------------------------------------
# Enqueue
# ---------------------------------------------------------------------------

def enqueue_reject_query(
    mode: str,
    params: Dict[str, Any],
) -> Tuple[Optional[str], Optional[str]]:
    """Enqueue a reject primary query to the RQ reject-query worker.

    Args:
        mode: "date_range" (container mode is not async).
        params: Full params dict passed through to execute_reject_query_job.

    Returns:
        (job_id, None) on success, (None, error_message) on failure.
    """
    job_id = f"reject-{uuid.uuid4().hex[:12]}"
    return enqueue_job(
        queue_name=REJECT_WORKER_QUEUE,
        worker_fn=execute_reject_query_job,
        job_id=job_id,
        kwargs={"job_id": job_id, "mode": mode, "params": params},
        prefix=_JOB_PREFIX,
        job_timeout=REJECT_JOB_TIMEOUT_SECONDS,
        result_ttl=REJECT_JOB_TTL_SECONDS,
        retry=_build_retry(),
    )


# ---------------------------------------------------------------------------
# RQ worker entry point
# ---------------------------------------------------------------------------

def execute_reject_query_job(
    job_id: str,
    mode: str,
    params: Dict[str, Any],
) -> None:
    """RQ worker entry point: execute reject primary query and spool result.

    Runs in the dedicated rq-worker-reject process — outside Gunicorn —
    with its own DB connections and memory space.
    """
    from mes_dashboard.rq_worker_preload import ensure_rq_logging
    ensure_rq_logging()

    from mes_dashboard.services.reject_dataset_cache import (
        _CACHE_SCHEMA_VERSION,
        _get_cached_df,
        _make_query_id,
        execute_primary_query,
    )

    logger.info("reject query job started job_id=%s mode=%s", job_id, mode)
    update_job_progress(_JOB_PREFIX, job_id, status="started", progress="initializing")

    try:
        start_date = params.get("start_date")
        end_date = params.get("end_date")
        container_input_type = params.get("container_input_type")
        container_values = params.get("container_values") or []

        # Compute deterministic query_id (same formula as execute_primary_query)
        query_id_input = {
            "cache_schema_version": _CACHE_SCHEMA_VERSION,
            "mode": mode,
            "start_date": start_date,
            "end_date": end_date,
            "container_input_type": container_input_type,
            "container_values": sorted(container_values),
        }
        query_id = _make_query_id(query_id_input)

        # Check cache — if a concurrent sync request already filled it, reuse
        cached_df = _get_cached_df(query_id)
        if cached_df is not None:
            logger.info("reject query job: cache hit, skipping Oracle query job_id=%s query_id=%s", job_id, query_id)
            complete_job(_JOB_PREFIX, job_id, query_id=query_id)
            return

        update_job_progress(_JOB_PREFIX, job_id, status="running", progress="querying Oracle")

        execute_primary_query(
            mode=mode,
            start_date=start_date,
            end_date=end_date,
            container_input_type=container_input_type,
            container_values=container_values,
            include_excluded_scrap=bool(params.get("include_excluded_scrap", False)),
            exclude_material_scrap=bool(params.get("exclude_material_scrap", True)),
            exclude_pb_diode=bool(params.get("exclude_pb_diode", True)),
        )

        complete_job(_JOB_PREFIX, job_id, query_id=query_id)

    except Exception as exc:
        logger.error(
            "reject query job failed job_id=%s: %s", job_id, exc, exc_info=True,
        )
        complete_job(_JOB_PREFIX, job_id, error=str(exc))
        raise
