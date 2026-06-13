# -*- coding: utf-8 -*-
"""Production History async job service.

Bridges production-history primary queries to the RQ background worker.

Public API:
  enqueue_production_history_query(params) -> (job_id, error)
  execute_production_history_job(job_id, params)   <- RQ worker entry point
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
    update_job_progress,
)

logger = logging.getLogger("mes_dashboard.production_history_job_service")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
PRODUCTION_HISTORY_ASYNC_ENABLED = os.getenv(
    "PRODUCTION_HISTORY_ASYNC_ENABLED", "true"
).strip().lower() in {"1", "true", "yes", "on"}

PRODUCTION_HISTORY_WORKER_QUEUE = os.getenv(
    "PRODUCTION_HISTORY_WORKER_QUEUE", "production-history-query"
)
PRODUCTION_HISTORY_JOB_TTL_SECONDS = int(
    os.getenv("PRODUCTION_HISTORY_JOB_TTL_SECONDS", "3600")
)
PRODUCTION_HISTORY_JOB_TIMEOUT_SECONDS = int(
    os.getenv("PRODUCTION_HISTORY_JOB_TIMEOUT_SECONDS", "1800")
)

# Prefix used for Redis meta keys: production_history:job:{job_id}:meta
_JOB_PREFIX = "production_history"


def _build_retry():
    if Retry is None:
        return None
    return Retry(max=2, interval=[30, 60])


# ---------------------------------------------------------------------------
# Enqueue
# ---------------------------------------------------------------------------

def enqueue_production_history_query(
    params: Dict[str, Any],
    owner: str,
) -> Tuple[Optional[str], Optional[str]]:
    """Enqueue a production-history primary query to the RQ worker.

    Args:
        params: Full raw params dict passed through to execute_production_history_job.
        owner: Caller identity from the Flask session (see get_owner_token).

    Returns:
        (job_id, None) on success, (None, error_message) on failure.
    """
    job_id = f"prod-hist-{uuid.uuid4().hex[:12]}"
    return enqueue_job(
        queue_name=PRODUCTION_HISTORY_WORKER_QUEUE,
        worker_fn=execute_production_history_job,
        owner=owner,
        job_id=job_id,
        kwargs={"job_id": job_id, "params": params},
        prefix=_JOB_PREFIX,
        job_timeout=PRODUCTION_HISTORY_JOB_TIMEOUT_SECONDS,
        result_ttl=PRODUCTION_HISTORY_JOB_TTL_SECONDS,
        retry=_build_retry(),
    )


# ---------------------------------------------------------------------------
# RQ worker entry point
# ---------------------------------------------------------------------------

def execute_production_history_job(
    job_id: str,
    params: Dict[str, Any],
) -> None:
    """RQ worker entry point: execute production-history primary query and spool result.

    Runs in the dedicated rq-worker-production-history process — outside Gunicorn —
    with its own DB connections and memory space.
    """
    from mes_dashboard.rq_worker_preload import ensure_rq_logging
    ensure_rq_logging()

    from mes_dashboard.core.query_spool_store import get_spool_file_path
    from mes_dashboard.services.production_history_service import (
        make_canonical_spool_id,
        query_production_history,
    )

    logger.info("production_history job started job_id=%s", job_id)
    update_job_progress(_JOB_PREFIX, job_id, status="started", progress="initializing", pct=0)

    try:
        # Compute deterministic dataset_id from params
        dataset_id = make_canonical_spool_id(params)

        # Check spool — if already filled (e.g. concurrent sync request), reuse
        if get_spool_file_path("production_history", dataset_id) is not None:
            logger.info(
                "production_history job: spool hit, skipping Oracle query job_id=%s dataset_id=%s",
                job_id, dataset_id,
            )
            complete_job(_JOB_PREFIX, job_id, query_id=dataset_id)
            return

        update_job_progress(_JOB_PREFIX, job_id, status="running", progress="querying Oracle", pct=30)

        query_production_history(params)

        update_job_progress(_JOB_PREFIX, job_id, status="running", progress="complete", pct=100, stage="complete")
        complete_job(_JOB_PREFIX, job_id, query_id=dataset_id)

    except Exception as exc:
        logger.error(
            "production_history job failed job_id=%s: %s", job_id, exc, exc_info=True,
        )
        complete_job(_JOB_PREFIX, job_id, error=str(exc))
        raise
