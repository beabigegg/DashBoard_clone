# -*- coding: utf-8 -*-
"""Async job service for mid-section defect analysis."""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any, Dict, List, Optional, Tuple

from mes_dashboard.config.constants import CACHE_TTL_DETECTION
from mes_dashboard.core.cache import cache_get, cache_set, make_cache_key
from mes_dashboard.services.async_query_job_service import (
    complete_job,
    enqueue_job,
    get_job_status,
    update_job_progress,
)
from mes_dashboard.services.mid_section_defect_service import query_analysis

logger = logging.getLogger("mes_dashboard.msd_query_job_service")

MSD_WORKER_QUEUE = os.getenv("MSD_WORKER_QUEUE", "msd-analysis")
MSD_JOB_TIMEOUT_SECONDS = int(os.getenv("MSD_JOB_TIMEOUT_SECONDS", "600"))
MSD_JOB_TTL_SECONDS = int(os.getenv("MSD_JOB_TTL_SECONDS", "3600"))

_JOB_PREFIX = "msd"


def _analysis_cache_key(
    start_date: str,
    end_date: str,
    station: str,
    direction: str,
    loss_reasons: Optional[List[str]],
) -> str:
    return make_cache_key(
        "mid_section_defect",
        filters={
            "start_date": start_date,
            "end_date": end_date,
            "loss_reasons": sorted(loss_reasons) if loss_reasons else None,
            "station": station,
            "direction": direction,
        },
    )


def enqueue_msd_analysis(
    *,
    start_date: str,
    end_date: str,
    station: str,
    direction: str,
    loss_reasons: Optional[List[str]],
) -> Tuple[Optional[str], Optional[str]]:
    job_id = f"msd-{uuid.uuid4().hex[:12]}"
    return enqueue_job(
        queue_name=MSD_WORKER_QUEUE,
        worker_fn=_execute_msd_analysis,
        job_id=job_id,
        kwargs={
            "job_id": job_id,
            "start_date": start_date,
            "end_date": end_date,
            "station": station,
            "direction": direction,
            "loss_reasons": list(loss_reasons or []),
        },
        prefix=_JOB_PREFIX,
        job_timeout=MSD_JOB_TIMEOUT_SECONDS,
        result_ttl=MSD_JOB_TTL_SECONDS,
    )


def get_msd_job_status(job_id: str) -> Optional[Dict[str, Any]]:
    return get_job_status(_JOB_PREFIX, job_id)


def get_msd_job_result(job_id: str) -> Optional[Dict[str, Any]]:
    status = get_msd_job_status(job_id)
    if status is None:
        return None
    query_id = status.get("query_id")
    if not query_id:
        return None
    return cache_get(str(query_id))


def _execute_msd_analysis(
    *,
    job_id: str,
    start_date: str,
    end_date: str,
    station: str,
    direction: str,
    loss_reasons: Optional[List[str]] = None,
) -> None:
    from mes_dashboard.rq_worker_preload import ensure_rq_logging

    ensure_rq_logging()
    update_job_progress(
        _JOB_PREFIX,
        job_id,
        status="running",
        progress="querying",
    )

    cache_key = _analysis_cache_key(
        start_date=start_date,
        end_date=end_date,
        station=station,
        direction=direction,
        loss_reasons=loss_reasons,
    )

    try:
        result = query_analysis(
            start_date=start_date,
            end_date=end_date,
            loss_reasons=loss_reasons,
            station=station,
            direction=direction,
        )
        if result is None:
            raise RuntimeError("analysis query returned no result")
        if "error" in result:
            raise ValueError(str(result["error"]))

        cache_set(cache_key, result, ttl=CACHE_TTL_DETECTION)
        complete_job(_JOB_PREFIX, job_id, query_id=cache_key)
    except Exception as exc:
        logger.error(
            "msd analysis job failed job_id=%s: %s",
            job_id,
            exc,
            exc_info=True,
        )
        complete_job(_JOB_PREFIX, job_id, error=str(exc))
        raise
