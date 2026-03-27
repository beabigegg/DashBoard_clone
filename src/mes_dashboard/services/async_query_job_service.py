# -*- coding: utf-8 -*-
"""Shared async query job service using RQ (Redis Queue).

Provides generic enqueue/status/progress/complete functions for long-running queries.
Used by reject_query_job_service and trace_job_service (after refactor).

Redis key schema:
  {prefix}:job:{job_id}:meta  — HSET with job metadata
"""

from __future__ import annotations

import logging
import os
import time
import uuid
import threading
from typing import Any, Dict, Optional, Tuple

from mes_dashboard.core.redis_client import get_key, get_redis_client
try:
    from rq import Retry
except Exception:  # pragma: no cover - optional dependency path
    Retry = None  # type: ignore[assignment]

logger = logging.getLogger("mes_dashboard.async_query_job_service")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
ASYNC_JOB_DEFAULT_TTL_SECONDS = int(os.getenv("ASYNC_JOB_TTL_SECONDS", "3600"))
ASYNC_JOB_DEFAULT_TIMEOUT_SECONDS = int(os.getenv("ASYNC_JOB_TIMEOUT_SECONDS", "600"))
_RQ_HEALTH_TTL_SECONDS = 60
_FAILED_JOB_COUNT = 0
_FAILED_JOB_LOCK = threading.Lock()
_DEFAULT_RETRY_SENTINEL = object()

# ---------------------------------------------------------------------------
# RQ availability cache
# ---------------------------------------------------------------------------
_RQ_AVAILABLE: Optional[bool] = None
_rq_health_cache: Dict[str, Any] = {"available": None, "checked_at": 0.0}


def _check_rq_installed() -> bool:
    global _RQ_AVAILABLE
    if _RQ_AVAILABLE is None:
        try:
            import rq  # noqa: F401
            _RQ_AVAILABLE = True
        except ImportError:
            _RQ_AVAILABLE = False
    return _RQ_AVAILABLE


def is_async_available() -> bool:
    """Return True if RQ is installed, Redis is reachable, and workers exist.

    Results are cached for 60 seconds.  Falls back gracefully: if any check
    fails, returns False.
    """
    if not _check_rq_installed():
        return False

    now = time.monotonic()
    if (
        _rq_health_cache["available"] is not None
        and (now - _rq_health_cache["checked_at"]) < _RQ_HEALTH_TTL_SECONDS
    ):
        return bool(_rq_health_cache["available"])

    conn = get_redis_client()
    if conn is None:
        _rq_health_cache["available"] = False
        _rq_health_cache["checked_at"] = now
        return False

    try:
        conn.ping()
    except Exception:
        logger.warning("async_query_job_service: Redis ping failed — async unavailable")
        _rq_health_cache["available"] = False
        _rq_health_cache["checked_at"] = now
        return False

    try:
        import rq
        workers = rq.Worker.all(connection=conn)
        if not workers:
            logger.warning("async_query_job_service: no RQ workers found — async unavailable")
            _rq_health_cache["available"] = False
            _rq_health_cache["checked_at"] = now
            return False
    except Exception:
        logger.warning("async_query_job_service: RQ worker query failed — async unavailable")
        _rq_health_cache["available"] = False
        _rq_health_cache["checked_at"] = now
        return False

    _rq_health_cache["available"] = True
    _rq_health_cache["checked_at"] = now
    return True


# ---------------------------------------------------------------------------
# Redis key helpers
# ---------------------------------------------------------------------------

def _meta_key(prefix: str, job_id: str) -> str:
    return get_key(f"{prefix}:job:{job_id}:meta")


def _build_default_retry():
    if Retry is None:
        return None
    return Retry(max=2, interval=[30, 60])


# ---------------------------------------------------------------------------
# Core API
# ---------------------------------------------------------------------------

def enqueue_job(
    *,
    queue_name: str,
    worker_fn,
    job_id: Optional[str] = None,
    kwargs: Optional[Dict[str, Any]] = None,
    prefix: str = "async",
    job_timeout: int = ASYNC_JOB_DEFAULT_TIMEOUT_SECONDS,
    result_ttl: int = ASYNC_JOB_DEFAULT_TTL_SECONDS,
    retry: Any = _DEFAULT_RETRY_SENTINEL,
) -> Tuple[Optional[str], Optional[str]]:
    """Enqueue a callable to a named RQ queue.

    Returns:
        (job_id, None) on success, (None, error_message) on failure.
    """
    if not _check_rq_installed():
        return None, "async queue unavailable (RQ not installed)"

    conn = get_redis_client()
    if conn is None:
        return None, "async queue unavailable (Redis unreachable)"

    if job_id is None:
        job_id = f"{queue_name}-{uuid.uuid4().hex[:12]}"

    # Write initial metadata before enqueue so status is visible immediately
    meta = {
        "status": "queued",
        "queue_name": queue_name,
        "created_at": str(time.time()),
        "completed_at": "",
        "progress": "",
        "pct": "",
        "stage": "",
        "completed_stages": "",
        "query_id": "",
        "dataset_id": "",
        "error": "",
    }
    key = _meta_key(prefix, job_id)
    conn.hset(key, mapping=meta)
    conn.expire(key, result_ttl)

    try:
        if retry is _DEFAULT_RETRY_SENTINEL:
            retry = _build_default_retry()
        from rq import Queue
        queue = Queue(queue_name, connection=conn)
        queue.enqueue(
            worker_fn,
            kwargs=kwargs or {},
            job_id=job_id,
            job_timeout=job_timeout,
            result_ttl=result_ttl,
            failure_ttl=result_ttl,
            retry=retry,
        )
    except Exception as exc:
        logger.error("async_query_job_service: enqueue failed job_id=%s: %s", job_id, exc, exc_info=True)
        try:
            conn.hset(key, mapping={"status": "failed", "error": str(exc)})
        except Exception:
            pass
        return None, f"enqueue failed: {exc}"

    logger.info(
        "async_query_job_service: enqueued job_id=%s queue=%s",
        job_id, queue_name,
    )
    return job_id, None


def get_job_status(prefix: str, job_id: str) -> Optional[Dict[str, Any]]:
    """Get job status from Redis metadata.  Returns None if not found."""
    conn = get_redis_client()
    if conn is None:
        return None

    key = _meta_key(prefix, job_id)
    meta = conn.hgetall(key)
    if not meta:
        return None

    created_at = float(meta.get("created_at", 0) or 0)
    elapsed = time.time() - created_at if created_at > 0 else 0

    result: Dict[str, Any] = {
        "job_id": job_id,
        "status": meta.get("status", "unknown"),
        "progress": meta.get("progress") or "",
        "created_at": created_at,
        "elapsed_seconds": round(elapsed, 1),
        "error": meta.get("error") or None,
    }

    # Include pct if present
    raw_pct = meta.get("pct")
    if raw_pct:
        try:
            result["pct"] = int(raw_pct)
        except (TypeError, ValueError):
            pass

    # Stage-aware progress fields (task 4.1)
    stage = meta.get("stage")
    if stage:
        result["stage"] = stage

    completed_stages_raw = meta.get("completed_stages")
    if completed_stages_raw:
        stages = [s.strip() for s in completed_stages_raw.split(",") if s.strip()]
        if stages:
            result["completed_stages"] = stages

    # Include query_id / dataset_id if present (completed jobs)
    query_id = meta.get("query_id")
    if query_id:
        result["query_id"] = query_id

    dataset_id = meta.get("dataset_id")
    if dataset_id:
        result["dataset_id"] = dataset_id

    completed_at_raw = meta.get("completed_at")
    if completed_at_raw:
        try:
            result["completed_at"] = float(completed_at_raw)
        except (TypeError, ValueError):
            pass

    return result


def update_job_progress(prefix: str, job_id: str, **fields) -> None:
    """Update Redis HSET fields for a running job."""
    conn = get_redis_client()
    if conn is None:
        return
    key = _meta_key(prefix, job_id)
    try:
        conn.hset(key, mapping={k: str(v) for k, v in fields.items()})
    except Exception as exc:
        logger.warning("async_query_job_service: progress update failed job_id=%s: %s", job_id, exc)


def complete_job(
    prefix: str,
    job_id: str,
    query_id: Optional[str] = None,
    dataset_id: Optional[str] = None,
    error: Optional[str] = None,
) -> None:
    """Mark a job as completed or failed.

    ``query_id`` is the canonical spool key for the completed result.
    ``dataset_id`` is an optional alternative identifier (e.g. for multi-stage
    pipelines where query_id and dataset_id differ).
    """
    global _FAILED_JOB_COUNT
    conn = get_redis_client()
    if conn is None:
        return

    key = _meta_key(prefix, job_id)
    if error is not None:
        logger.warning(
            "Job failed: prefix=%s job_id=%s error=%s",
            prefix,
            job_id,
            error,
        )
        with _FAILED_JOB_LOCK:
            _FAILED_JOB_COUNT += 1
        fields = {
            "status": "failed",
            "error": str(error),
            "completed_at": str(time.time()),
        }
    else:
        fields = {
            "status": "completed",
            "query_id": str(query_id or ""),
            "completed_at": str(time.time()),
        }
        if dataset_id:
            fields["dataset_id"] = str(dataset_id)

    try:
        conn.hset(key, mapping=fields)
    except Exception as exc:
        logger.warning("async_query_job_service: complete_job failed job_id=%s: %s", job_id, exc)


def get_failed_job_count() -> int:
    with _FAILED_JOB_LOCK:
        return int(_FAILED_JOB_COUNT)
