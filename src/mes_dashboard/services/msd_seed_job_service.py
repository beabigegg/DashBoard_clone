# -*- coding: utf-8 -*-
"""Async job service for MSD seed-resolve (date_range mode).

Long date-range seed queries drive BatchQueryEngine and can exceed the openresty
proxy_read_timeout (~60 s).  This service routes those queries through the
msd-analysis RQ worker queue so the HTTP response returns immediately (202)
and the frontend polls /seed/job/<id> until done.

Result is stored as JSON in control-plane Redis (not parquet) because seed
payloads are small (<1 MB) and do not warrant disk I/O.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from typing import Any, Dict, Optional, Tuple

from mes_dashboard.core.redis_client import get_control_redis_client, get_key
from mes_dashboard.services.async_query_job_service import (
    complete_job,
    enqueue_job,
    get_job_status as _get_job_status,
    update_job_progress,
)

logger = logging.getLogger("mes_dashboard.msd_seed_job_service")

MSD_SEED_QUEUE = os.getenv("MSD_WORKER_QUEUE", "msd-analysis")
MSD_SEED_JOB_TIMEOUT_SECONDS = int(os.getenv("MSD_SEED_JOB_TIMEOUT_SECONDS", "1800"))
MSD_SEED_JOB_TTL_SECONDS = int(os.getenv("MSD_JOB_TTL_SECONDS", "3600"))

_JOB_PREFIX = "msd-seed"


def _result_redis_key(job_id: str) -> str:
    return get_key(f"{_JOB_PREFIX}:job:{job_id}:result")


def enqueue_msd_seed_resolve(
    *,
    seed_cache_key: str,
    params: Dict[str, Any],
    owner: str,
) -> Tuple[Optional[str], Optional[str]]:
    """Enqueue a date_range seed-resolve to the msd-analysis worker queue.

    Returns (job_id, None) on success, (None, error_message) on failure.
    """
    job_id = f"msd-seed-{uuid.uuid4().hex[:12]}"
    return enqueue_job(
        queue_name=MSD_SEED_QUEUE,
        worker_fn=_execute_msd_seed_resolve_job,
        owner=owner,
        job_id=job_id,
        kwargs={"job_id": job_id, "seed_cache_key": seed_cache_key, "params": params},
        prefix=_JOB_PREFIX,
        job_timeout=MSD_SEED_JOB_TIMEOUT_SECONDS,
        result_ttl=MSD_SEED_JOB_TTL_SECONDS,
    )


def get_msd_seed_job_status(job_id: str) -> Optional[Dict[str, Any]]:
    return _get_job_status(_JOB_PREFIX, job_id)


def get_msd_seed_job_result(job_id: str) -> Optional[Dict[str, Any]]:
    """Read seed result JSON from control-plane Redis."""
    status = _get_job_status(_JOB_PREFIX, job_id)
    if not status or status.get("status") not in ("completed", "finished"):
        return None
    conn = get_control_redis_client()
    if conn is None:
        return None
    raw = conn.get(_result_redis_key(job_id))
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# RQ worker entry point
# ---------------------------------------------------------------------------

def _execute_msd_seed_resolve_job(
    *,
    job_id: str,
    seed_cache_key: str,
    params: Dict[str, Any],
) -> None:
    """Executed in the msd-analysis RQ worker process."""
    from mes_dashboard.rq_worker_preload import ensure_rq_logging
    ensure_rq_logging()

    update_job_progress(_JOB_PREFIX, job_id, status="running", progress="querying detection station")

    # Resolve date range from params (mirrors _extract_date_range in trace_routes)
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    date_range = params.get("date_range")
    if isinstance(date_range, list) and len(date_range) == 2:
        start_date = str(date_range[0] or "").strip() or None
        end_date = str(date_range[1] or "").strip() or None
    if not start_date:
        start_date = str(params.get("start_date") or "").strip() or None
    if not end_date:
        end_date = str(params.get("end_date") or "").strip() or None

    if not start_date or not end_date:
        complete_job(_JOB_PREFIX, job_id, error="missing start_date/end_date in params")
        return

    station = str(params.get("station") or "測試").strip()

    try:
        from mes_dashboard.services.mid_section_defect_service import resolve_trace_seed_lots
        result = resolve_trace_seed_lots(start_date, end_date, station=station)
    except Exception as exc:
        logger.error("msd seed job failed job_id=%s: %s", job_id, exc, exc_info=True)
        complete_job(_JOB_PREFIX, job_id, error=str(exc))
        return

    if result is None:
        complete_job(_JOB_PREFIX, job_id, error="seed resolve service unavailable")
        return
    if "error" in result:
        complete_job(_JOB_PREFIX, job_id, error=str(result["error"]))
        return

    # Format response identical to the sync path in trace_routes.seed_resolve()
    seeds = result.get("seeds", []) if isinstance(result.get("seeds"), list) else []
    seen: set = set()
    cids = []
    for row in seeds:
        if not isinstance(row, dict):
            continue
        cid = str(row.get("container_id") or "").strip()
        if cid and cid not in seen:
            seen.add(cid)
            cids.append(cid)

    response: Dict[str, Any] = {
        "stage": "seed-resolve",
        "seed_count": int(result.get("seed_count", 0)),
        "cache_key": seed_cache_key,
        "seed_container_ids": cids,
    }
    not_found = result.get("not_found")
    if isinstance(not_found, list) and not_found:
        response["not_found"] = [str(v).strip() for v in not_found if str(v or "").strip()]

    # Store result in control-plane Redis (accessible from this worker process)
    conn = get_control_redis_client()
    if conn is not None:
        try:
            conn.setex(_result_redis_key(job_id), MSD_SEED_JOB_TTL_SECONDS, json.dumps(response))
        except Exception as exc:
            logger.warning("msd seed: failed to persist result job_id=%s: %s", job_id, exc)

    complete_job(_JOB_PREFIX, job_id, query_id=seed_cache_key)
    logger.info("msd seed job completed job_id=%s seed_count=%d", job_id, response["seed_count"])


# ---------------------------------------------------------------------------
# Central job registry — job-registry-central
# ---------------------------------------------------------------------------
from mes_dashboard.services.job_registry import JobTypeConfig, register_job_type  # noqa: E402

register_job_type(JobTypeConfig(
    job_type="msd-seed",
    queue_name="msd-analysis",
    worker_fn=_execute_msd_seed_resolve_job,
))
