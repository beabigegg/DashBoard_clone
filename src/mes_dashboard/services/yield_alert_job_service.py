# -*- coding: utf-8 -*-
"""Yield Alert async job service.

Bridges yield-alert primary queries to the RQ background worker.

Public API:
  enqueue_yield_alert_query(params) -> (job_id, error)
  execute_yield_alert_job(job_id, params)   <- RQ worker entry point
"""

from __future__ import annotations

import logging
import os
import uuid
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

logger = logging.getLogger("mes_dashboard.yield_alert_job_service")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
YIELD_ALERT_ASYNC_ENABLED = os.getenv(
    "YIELD_ALERT_ASYNC_ENABLED", "true"
).strip().lower() in {"1", "true", "yes", "on"}

YIELD_ALERT_WORKER_QUEUE = os.getenv(
    "YIELD_ALERT_WORKER_QUEUE", "yield-alert-query"
)
YIELD_ALERT_JOB_TTL_SECONDS = int(
    os.getenv("YIELD_ALERT_JOB_TTL_SECONDS", "3600")
)
YIELD_ALERT_JOB_TIMEOUT_SECONDS = int(
    os.getenv("YIELD_ALERT_JOB_TIMEOUT_SECONDS", "1800")
)

# Prefix used for Redis meta keys: yield_alert:job:{job_id}:meta
_JOB_PREFIX = "yield_alert"


def _build_retry():
    if Retry is None:
        return None
    return Retry(max=2, interval=[30, 60])


# ---------------------------------------------------------------------------
# Enqueue
# ---------------------------------------------------------------------------

def enqueue_yield_alert_query(
    params: Dict[str, Any],
    owner: str,
) -> Tuple[Optional[str], Optional[str]]:
    """Enqueue a yield-alert primary query to the RQ worker.

    Args:
        params: Dict with at minimum start_date and end_date.
        owner: Caller identity from the Flask session (see get_owner_token).

    Returns:
        (job_id, None) on success, (None, error_message) on failure.
    """
    job_id = f"yield-alert-{uuid.uuid4().hex[:12]}"
    return enqueue_job(
        queue_name=YIELD_ALERT_WORKER_QUEUE,
        worker_fn=execute_yield_alert_job,
        owner=owner,
        job_id=job_id,
        kwargs={"job_id": job_id, "params": params},
        prefix=_JOB_PREFIX,
        job_timeout=YIELD_ALERT_JOB_TIMEOUT_SECONDS,
        result_ttl=YIELD_ALERT_JOB_TTL_SECONDS,
        retry=_build_retry(),
    )


# ---------------------------------------------------------------------------
# RQ worker entry point
# ---------------------------------------------------------------------------

def execute_yield_alert_job(
    job_id: str,
    params: Dict[str, Any],
) -> None:
    """RQ worker entry point: execute yield-alert primary query and spool result.

    Runs in the dedicated rq-worker-yield-alert process — outside Gunicorn —
    with its own DB connections and memory space.
    """
    from mes_dashboard.rq_worker_preload import ensure_rq_logging
    ensure_rq_logging()

    from mes_dashboard.services.yield_alert_dataset_cache import (
        _CACHE_SCHEMA_VERSION,
        _get_cached_payload,
        _make_query_id,
        execute_primary_query,
    )

    start_date = str(params.get("start_date", "")).strip()
    end_date = str(params.get("end_date", "")).strip()

    logger.info(
        "yield_alert job started job_id=%s start_date=%s end_date=%s",
        job_id, start_date, end_date,
    )
    update_job_progress(_JOB_PREFIX, job_id, status="started", progress="initializing")

    try:
        # Compute deterministic query_id (same formula as execute_primary_query)
        query_id = _make_query_id(
            {
                "cache_schema_version": _CACHE_SCHEMA_VERSION,
                "start_date": start_date,
                "end_date": end_date,
            }
        )

        # Check cache — if a concurrent sync request already filled it, reuse
        if _get_cached_payload(query_id) is not None:
            logger.info(
                "yield_alert job: cache hit, skipping Oracle query job_id=%s query_id=%s",
                job_id, query_id,
            )
            complete_job(_JOB_PREFIX, job_id, query_id=query_id)
            return

        update_job_progress(_JOB_PREFIX, job_id, status="running", progress="querying Oracle")

        execute_primary_query(start_date=start_date, end_date=end_date)

        complete_job(_JOB_PREFIX, job_id, query_id=query_id)

    except Exception as exc:
        logger.error(
            "yield_alert job failed job_id=%s: %s", job_id, exc, exc_info=True,
        )
        complete_job(_JOB_PREFIX, job_id, error=str(exc))
        raise
