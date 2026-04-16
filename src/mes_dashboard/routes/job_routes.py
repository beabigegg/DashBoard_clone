# -*- coding: utf-8 -*-
"""Async job management API routes.

Provides endpoints for lifecycle management of background async jobs
spawned by reject-history, yield-alert, production-history, material-trace,
and other long-running query services.
"""

from __future__ import annotations

import logging

from flask import Blueprint, request

from mes_dashboard.core.rate_limit import configured_rate_limit
from mes_dashboard.core.response import (
    FORBIDDEN,
    NOT_FOUND,
    VALIDATION_ERROR,
    error_response,
    not_found_error,
    success_response,
    validation_error,
)
from mes_dashboard.core.permissions import get_owner_token
from mes_dashboard.services.async_query_job_service import (
    get_job_status,
    update_job_progress,
)

job_bp = Blueprint("job", __name__)
logger = logging.getLogger("mes_dashboard.job_routes")

# ============================================================
# Constants
# ============================================================

#: Job statuses that are still active and can be abandoned.
_ABANDONABLE_STATUSES = frozenset({"queued", "running", "started"})

#: Statuses that represent a terminal state — abandon is a no-op / conflict.
_TERMINAL_STATUSES = frozenset({"completed", "failed", "abandoned"})

# ============================================================
# Rate limit
# ============================================================

_JOB_ABANDON_RATE_LIMIT = configured_rate_limit(
    bucket="job-abandon",
    max_attempts_env="JOB_ABANDON_RATE_LIMIT_MAX_REQUESTS",
    window_seconds_env="JOB_ABANDON_RATE_LIMIT_WINDOW_SECONDS",
    default_max_attempts=30,
    default_window_seconds=60,
)


# ============================================================
# Routes
# ============================================================

@job_bp.route("/api/job/<job_id>", methods=["GET"])
def get_job(job_id: str):
    """Return the current status of an async job.

    Query parameters:
        prefix (required): The job namespace (e.g. ``"reject"``, ``"yield_alert"``).

    Returns 200 with ``{"job_id": ..., "status": ..., "progress": ...}`` on success.
    """
    prefix = request.args.get("prefix", "").strip()
    if not prefix:
        return validation_error("prefix query parameter is required")

    status_data = get_job_status(prefix, job_id)
    if status_data is None:
        return not_found_error(f"job {job_id!r} not found (prefix={prefix!r})")

    return success_response(status_data)


@job_bp.route("/api/job/<job_id>/abandon", methods=["POST"])
@_JOB_ABANDON_RATE_LIMIT
def abandon_job(job_id: str):
    """Mark an async job as abandoned.

    The caller must supply the job ``prefix`` (e.g. ``"reject"``,
    ``"yield_alert"``) so the correct Redis key namespace is resolved.

    Owner check: the caller's identity is derived from the server-side Flask
    session via ``get_owner_token()`` (username for logged-in users; a
    uuid4 hex token stored in the session cookie for anonymous users).  The
    stored ``meta["owner"]`` must match the session-derived token, otherwise
    403 is returned.  If ``meta["owner"]`` is absent (legacy job created before
    this auth was introduced) the call is fail-closed: 403 is returned.

    Returns 200 on success (even if the job was already abandoned — idempotent
    via a separate ``already_abandoned`` flag in the response).  Returns 409
    if the job is in a non-abandonable terminal state (completed / failed).
    """
    body = request.get_json(silent=True) or {}
    prefix = body.get("prefix", "")
    if not prefix:
        return validation_error("prefix is required")

    # ------------------------------------------------------------------
    # Look up job
    # ------------------------------------------------------------------
    status_data = get_job_status(prefix, job_id)
    if status_data is None:
        return not_found_error(f"job {job_id!r} not found (prefix={prefix!r})")

    current_status = status_data.get("status", "unknown")

    # ------------------------------------------------------------------
    # Owner check — session-derived, fail-closed
    # ------------------------------------------------------------------
    caller_owner = get_owner_token()
    stored_owner = status_data.get("owner")
    if not stored_owner or caller_owner != stored_owner:
        return error_response(
            FORBIDDEN,
            "job does not belong to the current user",
            status_code=403,
        )

    # ------------------------------------------------------------------
    # Already abandoned — idempotent success
    # ------------------------------------------------------------------
    if current_status == "abandoned":
        logger.info("job already abandoned: job_id=%s prefix=%s", job_id, prefix)
        return success_response(
            {"job_id": job_id, "status": "abandoned", "already_abandoned": True}
        )

    # ------------------------------------------------------------------
    # Terminal non-abandonable states — conflict
    # ------------------------------------------------------------------
    if current_status in _TERMINAL_STATUSES:
        return error_response(
            "JOB_ALREADY_TERMINAL",
            f"job is already in terminal state: {current_status!r}",
            status_code=409,
        )

    # ------------------------------------------------------------------
    # Mark abandoned
    # ------------------------------------------------------------------
    try:
        update_job_progress(prefix, job_id, status="abandoned")
    except Exception as exc:
        logger.error(
            "job_routes: abandon failed job_id=%s prefix=%s: %s", job_id, prefix, exc
        )
        from mes_dashboard.core.response import internal_error
        return internal_error(str(exc))

    logger.info("job abandoned: job_id=%s prefix=%s", job_id, prefix)
    return success_response(
        {"job_id": job_id, "status": "abandoned", "already_abandoned": False}
    )
