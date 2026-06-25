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
    - date range meets classify_query_cost L2 threshold (unified CostPolicy)
    - is_async_available() returns True (workers are registered)

    NOTE: REJECT_ASYNC_DAY_THRESHOLD env var removed (query-path-c-elimination-cleanup, IP-7).
    Routing now uses classify_query_cost(domain="reject", ...) for unified policy.
    """
    if not REJECT_ASYNC_ENABLED:
        return False
    if mode != "date_range":
        return False
    if not start_date or not end_date:
        return False
    from mes_dashboard.core.query_cost_policy import classify_query_cost
    try:
        cost = classify_query_cost(
            domain="reject",
            params={"date_from": start_date, "date_to": end_date},
        )
    except (ValueError, TypeError):
        # Fail-open: invalid date strings → stay SYNC (same as original strptime guard)
        return False
    if cost != "ASYNC":
        return False
    return is_async_available()


# ---------------------------------------------------------------------------
# Enqueue
# ---------------------------------------------------------------------------

def enqueue_reject_query(
    mode: str,
    params: Dict[str, Any],
    owner: str,
) -> Tuple[Optional[str], Optional[str]]:
    """Enqueue a reject primary query to the RQ reject-query worker.

    Args:
        mode: "date_range" (container mode is not async).
        params: Full params dict passed through to execute_reject_query_job.
        owner: Caller identity from the Flask session (see get_owner_token).

    Returns:
        (job_id, None) on success, (None, error_message) on failure.
    """
    job_id = f"reject-{uuid.uuid4().hex[:12]}"
    return enqueue_job(
        queue_name=REJECT_WORKER_QUEUE,
        worker_fn=execute_reject_query_job,
        owner=owner,
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
        _has_cached_df,
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
        _pj_types = sorted({str(v).strip() for v in (params.get("pj_types") or []) if str(v).strip()})
        _packages = sorted({str(v).strip() for v in (params.get("packages") or []) if str(v).strip()})
        _pj_functions = sorted({str(v).strip() for v in (params.get("pj_functions") or []) if str(v).strip()})
        _reasons = sorted({str(v).strip() for v in (params.get("reasons") or []) if str(v).strip()})
        query_id_input = {
            "cache_schema_version": _CACHE_SCHEMA_VERSION,
            "mode": mode,
            "start_date": start_date,
            "end_date": end_date,
            "container_input_type": container_input_type,
            "container_values": sorted(container_values),
            "pj_types": _pj_types,
            "packages": _packages,
            "pj_functions": _pj_functions,
            "reasons": _reasons,
        }
        query_id = _make_query_id(query_id_input)

        # Check cache — if a concurrent sync request already filled it, reuse
        if _has_cached_df(query_id):
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
            build_response=False,
            pj_types=params.get("pj_types") or [],
            packages=params.get("packages") or [],
            pj_functions=params.get("pj_functions") or [],
            reasons=params.get("reasons") or [],
        )

        complete_job(_JOB_PREFIX, job_id, query_id=query_id)

    except Exception as exc:
        logger.error(
            "reject query job failed job_id=%s: %s", job_id, exc, exc_info=True,
        )
        complete_job(_JOB_PREFIX, job_id, error=str(exc))
        raise


# ---------------------------------------------------------------------------
# Central job registry — job-registry-central
# ---------------------------------------------------------------------------
from mes_dashboard.services.job_registry import JobTypeConfig, register_job_type  # noqa: E402

register_job_type(JobTypeConfig(
    job_type="reject",
    queue_name="reject-query",
    worker_fn=execute_reject_query_job,
))
