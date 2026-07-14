# -*- coding: utf-8 -*-
"""Warm-cache module for Production Achievement DailyView (今日/前日),
production-achievement-overhaul Phase 5 (business-rules.md PA-14).

Directly reuses ``ProductionAchievementJob`` (the SAME worker class as the
spool-miss async path, ``workers/production_achievement_worker.py``) via a
``progress_report()``-overriding subclass -- NOT a hand-written parallel
Oracle path (design.md Key Decisions: that would duplicate ADR-0016's
seam-safe chunk/``post_aggregate`` correctness into a drift-prone twin).

Redis-orphan-key trap: ``ProductionAchievementJob.progress_report()``
(inherited) calls ``async_query_job_service.update_job_progress()``, which
does an UNCONDITIONAL Redis ``HSET`` with NO TTL and NO existence check
(verified against the real implementation, ``async_query_job_service.py``
lines ~272-281). Calling ``.run()`` directly from this module bypasses
``enqueue_query_job``'s registration -- which is what normally writes the
initial metadata AND sets the TTL via ``ctrl.expire(key, result_ttl)``
(``async_query_job_service.enqueue_job()``). Without the override below,
EVERY warmup cycle would create a brand-new, un-expiring Redis key that
never gets cleaned up -- one leaked key forever, per cycle. The subclass
no-ops ``progress_report()`` entirely to sever that.

Kill-switch independence: ``_is_unified_job_enabled()`` re-reads
``PRODUCTION_ACHIEVEMENT_USE_UNIFIED_JOB`` (env-contract.md) independently
of the route module's frozen-at-import-time flag, and ``_build_warmup_job()``
(which lazily imports the worker module) is ONLY called after that flag
check passes -- a disabled flag must never import the worker module (never
touch Oracle).

Fail-safe by construction (PA-14): a total scheduler outage degrades to the
existing 202-poll path -- DailyView issues the identical
``GET /report(start=end=<day>)`` request either way (no separate warm/cold
client code fork).
"""

from __future__ import annotations

import logging
import os
from datetime import date, timedelta
from typing import Optional

from mes_dashboard.core.query_spool_store import get_spool_file_path
from mes_dashboard.services.production_achievement_service import (
    PRODUCTION_ACHIEVEMENT_SPOOL_NAMESPACE,
    make_canonical_pa_spool_id,
)

logger = logging.getLogger("mes_dashboard.production_achievement_daily_cache")


def _is_unified_job_enabled() -> bool:
    """Independent re-read of PRODUCTION_ACHIEVEMENT_USE_UNIFIED_JOB.

    Must be re-checked HERE (not inherited from
    ``routes/production_achievement_routes.py``'s frozen-at-import-time
    flag) so this module's kill-switch can never be defeated by a stale
    import elsewhere.
    """
    return os.getenv("PRODUCTION_ACHIEVEMENT_USE_UNIFIED_JOB", "on").strip().lower() in (
        "on", "true", "1",
    )


def _build_warmup_job(job_id: str, params: dict):
    """Lazily import the worker module and instantiate the progress-report-
    suppressing subclass. Only ever called AFTER ``_is_unified_job_enabled()``
    has already returned True -- a disabled flag must never reach this
    function, so the worker module (and therefore Oracle) is never touched.
    """
    from mes_dashboard.workers.production_achievement_worker import (
        ProductionAchievementJob,
    )

    class _WarmupProductionAchievementJob(ProductionAchievementJob):
        """``progress_report()``-suppressing subclass (PA-14).

        See module docstring for the Redis-orphan-key trap this override
        prevents. Must NEVER call ``update_job_progress`` -- a complete
        no-op is required, not merely a cheaper implementation.
        """

        def progress_report(self, pct: int) -> None:
            pass

    return _WarmupProductionAchievementJob(job_id=job_id, params=params)


def _ensure_day_loaded(day: date) -> Optional[str]:
    """Check the spool first; on miss (and only when the flag is on),
    build+run the warm-cache subclass for a single-day range
    (``start_date == end_date == day``).

    Returns:
        The spool path if already warm or after a successful run; None if
        the spool is missing and the flag is off (falls through to the
        existing 202-poll path, PA-14).
    """
    date_str = day.strftime("%Y-%m-%d")
    query_id = make_canonical_pa_spool_id(date_str, date_str)

    spool_path = get_spool_file_path(PRODUCTION_ACHIEVEMENT_SPOOL_NAMESPACE, query_id)
    if spool_path is not None:
        return spool_path

    if not _is_unified_job_enabled():
        logger.debug(
            "production_achievement_daily_cache: flag off, skipping warmup for %s",
            date_str,
        )
        return None

    job = _build_warmup_job(
        job_id=f"warmup-pa-{date_str}",
        params={"start_date": date_str, "end_date": date_str},
    )
    return job.run()


def ensure_today_loaded() -> Optional[str]:
    """Ensure today's DailyView (今日) spool is warm. Returns the spool path,
    or None if the flag is off and the spool is missing."""
    return _ensure_day_loaded(date.today())


def ensure_yesterday_loaded() -> Optional[str]:
    """Ensure yesterday's DailyView (前日) spool is warm. Returns the spool
    path, or None if the flag is off and the spool is missing."""
    return _ensure_day_loaded(date.today() - timedelta(days=1))
