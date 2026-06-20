# -*- coding: utf-8 -*-
"""Downtime analysis async job service.

Bridges downtime primary queries to the RQ background worker.

Public API:
  execute_downtime_query_job(*, job_id, owner, **query_params)  <- RQ worker entry point (legacy)

Feature flag: DOWNTIME_USE_UNIFIED_JOB (default off, env-contract 1.x.x).
  OFF → legacy execute_downtime_query_job path (AC-8 preserved byte-for-byte).
  ON  → DowntimeJob (BaseChunkedDuckDBJob) unified path.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from mes_dashboard.core.feature_flags import resolve_bool_flag
from mes_dashboard.services.async_query_job_service import (
    complete_job,
    update_job_progress,
)

logger = logging.getLogger("mes_dashboard.downtime_query_job_service")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DOWNTIME_ASYNC_ENABLED = os.getenv(
    "DOWNTIME_ASYNC_ENABLED", "true"
).strip().lower() in {"1", "true", "yes", "on"}

DOWNTIME_WORKER_QUEUE = os.getenv(
    "DOWNTIME_WORKER_QUEUE", "downtime-query"
)
DOWNTIME_JOB_TTL_SECONDS = int(os.getenv("DOWNTIME_JOB_TTL_SECONDS", "3600"))
DOWNTIME_JOB_TIMEOUT_SECONDS = int(
    os.getenv("DOWNTIME_JOB_TIMEOUT_SECONDS", "1800")
)

# Feature flag: frozen at import time.
# Tests must use monkeypatch.setattr(downtime_query_job_service, '_DOWNTIME_USE_UNIFIED_JOB', ...)
# rather than monkeypatch.setenv (env vars are read at import; setenv after-the-fact has no effect).
_DOWNTIME_USE_UNIFIED_JOB: bool = resolve_bool_flag(
    "DOWNTIME_USE_UNIFIED_JOB", default=True
)

# Prefix used for Redis meta keys: downtime:job:{job_id}:meta
_JOB_PREFIX = "downtime"


# ---------------------------------------------------------------------------
# RQ worker entry point
# ---------------------------------------------------------------------------

def execute_downtime_query_job(*, job_id: str, owner: str, **query_params: Any) -> None:
    """RQ worker entry point: execute downtime analysis raw query and spool result.

    Runs in the dedicated downtime worker process — outside Gunicorn —
    with its own DB connections and memory space.

    pct milestones (ASYNC-05 / design.md D2):
      5  = starting (job received, Oracle not yet issued)
      15 = querying (BQE in progress)
      60 = writing (base_events parquet write starting)
      90 = finalizing (job_bridge write + atomic commit)
      100 = complete (result.query_id available)

    DA-11 atomicity: complete_job() only called after both parquets written
    (handled inside query_downtime_dataset_raw via store_downtime_base_events
    then store_downtime_job_bridge).  If either store fails, the exception
    propagates and the job fails loudly.

    ADR-0003: no BatchQueryEngine ROW_NUMBER chunking.
    query_downtime_dataset_raw() uses one whole-dataset BQE chunk only.
    """
    from mes_dashboard.rq_worker_preload import ensure_rq_logging
    ensure_rq_logging()

    from mes_dashboard.services.downtime_analysis_service import (
        query_downtime_dataset_raw,
    )

    logger.info("downtime job started job_id=%s owner=%s", job_id, owner)
    update_job_progress(
        _JOB_PREFIX, job_id,
        status="started", progress="initializing", pct=5, stage="starting",
    )

    try:
        update_job_progress(
            _JOB_PREFIX, job_id,
            status="running", progress="querying Oracle", pct=15, stage="querying",
        )

        # Delegate entirely to query_downtime_dataset_raw — no chunking here (ADR-0003).
        # It writes base_events then job_bridge atomically (DA-11, D3).
        result = query_downtime_dataset_raw(**query_params)

        # Both parquets written; update milestones.
        update_job_progress(
            _JOB_PREFIX, job_id,
            status="running", progress="writing spool", pct=60, stage="writing",
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
            "downtime job failed job_id=%s: %s", job_id, exc, exc_info=True,
        )
        complete_job(_JOB_PREFIX, job_id, error=str(exc))
        raise


# ---------------------------------------------------------------------------
# Central job registry — register at import time
# ---------------------------------------------------------------------------
from mes_dashboard.services.job_registry import JobTypeConfig, register_job_type  # noqa: E402

register_job_type(JobTypeConfig(
    job_type="downtime",
    queue_name="downtime-query",
    worker_fn=execute_downtime_query_job,
    timeout_seconds=DOWNTIME_JOB_TIMEOUT_SECONDS,
    ttl_seconds=DOWNTIME_JOB_TTL_SECONDS,
))
