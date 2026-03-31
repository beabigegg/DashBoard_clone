# -*- coding: utf-8 -*-
"""On-demand RQ monitoring service for admin dashboard.

Provides worker status, queue depth, and heavy query slot utilization
data without background threads — all data is collected on-demand when
health or admin performance-detail APIs are called.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List

from mes_dashboard.core.redis_client import get_redis_client

logger = logging.getLogger("mes_dashboard.rq_monitor_service")

# ---------------------------------------------------------------------------
# Queue name configuration (same env vars as job services)
# ---------------------------------------------------------------------------
_QUEUE_NAMES: List[str] = [
    os.getenv("TRACE_WORKER_QUEUE", "trace-events"),
    os.getenv("REJECT_WORKER_QUEUE", "reject-query"),
    os.getenv("MSD_WORKER_QUEUE", "msd-analysis"),
    os.getenv("PRODUCTION_HISTORY_WORKER_QUEUE", "production-history-query"),
    os.getenv("YIELD_ALERT_WORKER_QUEUE", "yield-alert-query"),
]


def _check_rq_installed() -> bool:
    try:
        import rq  # noqa: F401
        return True
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# Worker details
# ---------------------------------------------------------------------------

def get_rq_worker_details() -> dict:
    """Enumerate all RQ workers with per-worker status.

    Returns:
        {
            "workers": [
                {"name": str, "state": str, "current_job": str|None,
                 "queues": [str], "birth_date": str|None,
                 "successful_job_count": int, "failed_job_count": int},
                ...
            ],
            "summary": {"total": int, "busy": int, "idle": int}
        }
    """
    empty = {"workers": [], "summary": {"total": 0, "busy": 0, "idle": 0}}
    if not _check_rq_installed():
        return empty

    conn = get_redis_client()
    if conn is None:
        return empty

    try:
        import rq
        workers = rq.Worker.all(connection=conn)
    except Exception as exc:
        logger.debug("rq_monitor: failed to enumerate workers: %s", exc)
        return empty

    result_workers: List[Dict[str, Any]] = []
    busy_count = 0
    for w in workers:
        try:
            state = w.get_state()
        except Exception:
            state = "unknown"
        if state == "busy":
            busy_count += 1

        current_job = None
        try:
            job = w.get_current_job()
            if job is not None:
                current_job = job.id
        except Exception:
            pass

        birth = None
        try:
            if w.birth_date:
                birth = w.birth_date.isoformat() if hasattr(w.birth_date, "isoformat") else str(w.birth_date)
        except Exception:
            pass

        queue_names = []
        try:
            queue_names = [q.name for q in w.queues]
        except Exception:
            pass

        result_workers.append({
            "name": w.name,
            "state": state,
            "current_job": current_job,
            "queues": queue_names,
            "birth_date": birth,
            "successful_job_count": getattr(w, "successful_job_count", 0),
            "failed_job_count": getattr(w, "failed_job_count", 0),
        })

    total = len(result_workers)
    return {
        "workers": result_workers,
        "summary": {
            "total": total,
            "busy": busy_count,
            "idle": total - busy_count,
        },
    }


# ---------------------------------------------------------------------------
# Queue details
# ---------------------------------------------------------------------------

def get_rq_queue_details() -> dict:
    """Per-queue depth and registry counts.

    Returns:
        {
            "queues": [
                {"name": str, "depth": int, "started": int, "failed": int},
                ...
            ],
            "total_queued": int, "total_started": int, "total_failed": int
        }
    """
    empty = {"queues": [], "total_queued": 0, "total_started": 0, "total_failed": 0}
    if not _check_rq_installed():
        return empty

    conn = get_redis_client()
    if conn is None:
        return empty

    try:
        from rq import Queue
    except ImportError:
        return empty

    queues_info: List[Dict[str, Any]] = []
    total_queued = 0
    total_started = 0
    total_failed = 0

    for qname in _QUEUE_NAMES:
        try:
            q = Queue(qname, connection=conn)
            depth = len(q)
            started = q.started_job_registry.count if hasattr(q, "started_job_registry") else 0
            failed = q.failed_job_registry.count if hasattr(q, "failed_job_registry") else 0
            queues_info.append({
                "name": qname,
                "depth": depth,
                "started": started,
                "failed": failed,
            })
            total_queued += depth
            total_started += started
            total_failed += failed
        except Exception as exc:
            logger.debug("rq_monitor: failed to read queue %s: %s", qname, exc)
            queues_info.append({"name": qname, "depth": 0, "started": 0, "failed": 0})

    return {
        "queues": queues_info,
        "total_queued": total_queued,
        "total_started": total_started,
        "total_failed": total_failed,
    }


# ---------------------------------------------------------------------------
# Heavy query slot status
# ---------------------------------------------------------------------------

def get_heavy_query_slot_status() -> dict:
    """Return heavy query concurrency slot utilization.

    Returns:
        {"active": int, "max": int, "utilization_pct": float}
    """
    from mes_dashboard.core.global_concurrency import (
        get_active_slot_count,
        HEAVY_QUERY_MAX_CONCURRENT,
    )
    active = get_active_slot_count()
    max_slots = HEAVY_QUERY_MAX_CONCURRENT
    pct = round(active / max_slots * 100, 1) if max_slots > 0 else 0.0
    return {"active": active, "max": max_slots, "utilization_pct": pct}


# ---------------------------------------------------------------------------
# Aggregated summary
# ---------------------------------------------------------------------------

def get_rq_monitor_summary() -> dict:
    """Aggregate workers + queues + slots into a single monitoring payload.

    Returns:
        {
            "rq_available": bool,
            "workers": {...},   # from get_rq_worker_details()
            "queues": {...},    # from get_rq_queue_details()
            "slots": {...},     # from get_heavy_query_slot_status()
        }
    """
    from mes_dashboard.services.async_query_job_service import is_async_available

    result: Dict[str, Any] = {"rq_available": False, "workers": {}, "queues": {}, "slots": {}}

    try:
        result["rq_available"] = is_async_available()
    except Exception:
        pass

    try:
        result["workers"] = get_rq_worker_details()
    except Exception as exc:
        logger.debug("rq_monitor: get_rq_worker_details failed: %s", exc)

    try:
        result["queues"] = get_rq_queue_details()
    except Exception as exc:
        logger.debug("rq_monitor: get_rq_queue_details failed: %s", exc)

    try:
        result["slots"] = get_heavy_query_slot_status()
    except Exception as exc:
        logger.debug("rq_monitor: get_heavy_query_slot_status failed: %s", exc)

    return result
