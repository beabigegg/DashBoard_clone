# -*- coding: utf-8 -*-
"""Warm-cache module for Production Achievement DailyView (今日/前日),
production-achievement-overhaul Phase 5 (business-rules.md PA-14).

Directly reuses ``ProductionAchievementJob`` (the SAME worker class as the
spool-miss async path, ``workers/production_achievement_worker.py``) via a
``progress_report()``-overriding subclass -- NOT a hand-written parallel
Oracle path (design.md Key Decisions: that would duplicate ADR-0016's
seam-safe chunk/``post_aggregate`` correctness into a drift-prone twin).

Covers BOTH the 產出 (output) source (``ensure_today_loaded`` /
``ensure_yesterday_loaded``, this module's original scope) and the 轉出
(move-out) source (``ensure_moveout_today_loaded`` /
``ensure_moveout_yesterday_loaded``, PA-18) -- the two sources have
identical today/yesterday warm-cache characteristics (today = growing
window needs hourly staleness re-checks; yesterday = closed day is fresh
forever once cached), so the moveout functions mirror the 產出 ones
1:1 against ``ProductionAchievementMoveoutJob`` and
``PRODUCTION_ACHIEVEMENT_MOVEOUT_SPOOL_NAMESPACE`` instead.

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

Today-staleness (bug fix, blank 當日產出): unlike a CLOSED day (yesterday and
earlier, whose data never changes once the day is over), "today" keeps
gaining new Oracle rows all day as each shift produces output. The hourly
``_warmup_achievement_today_job`` (spool_warmup_scheduler.py,
``WARMUP_INTERVAL_SECONDS``) is supposed to keep today's spool current, but
``_ensure_day_loaded`` used to short-circuit on ANY non-expired spool
regardless of age -- so the FIRST warmup run of the day (e.g. right at/just
after midnight, or right as a shift starts) would freeze that early,
near-empty snapshot in place for the spool's entire multi-hour Redis TTL
(cache-spool-patterns.md), and every subsequent hourly warmup became a
no-op. ``_is_today_spool_stale`` below re-checks the spool's own
``created_at`` against ``WARMUP_INTERVAL_SECONDS`` so "today" gets rebuilt
roughly every warmup cycle, while "yesterday" (``is_today=False``) keeps the
original exists-means-fresh short-circuit -- a closed day never needs a
rebuild once cached.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import date, timedelta
from typing import Optional

from mes_dashboard.core.query_spool_store import (
    get_inflight_state,
    get_spool_file_path,
    get_spool_metadata,
)
from mes_dashboard.services.production_achievement_service import (
    PRODUCTION_ACHIEVEMENT_MOVEOUT_SPOOL_NAMESPACE,
    PRODUCTION_ACHIEVEMENT_SPOOL_NAMESPACE,
    make_canonical_pa_spool_id,
)

logger = logging.getLogger("mes_dashboard.production_achievement_daily_cache")

_DEFAULT_TODAY_STALE_SECONDS = 3600


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


def _today_stale_threshold_seconds() -> int:
    """Reuse ``WARMUP_INTERVAL_SECONDS`` (spool_warmup_scheduler.py) as the
    staleness bound for "today" -- the hourly warmup cycle can only pick up
    newly-arrived Oracle rows if today's cached spool is treated as stale by
    the time the NEXT cycle fires, not just at its multi-hour Redis TTL
    horizon."""
    raw = os.getenv("WARMUP_INTERVAL_SECONDS", str(_DEFAULT_TODAY_STALE_SECONDS))
    try:
        return max(int(raw), 60)
    except (TypeError, ValueError):
        return _DEFAULT_TODAY_STALE_SECONDS


def _is_today_spool_stale(query_id: str) -> bool:
    """True when today's already-registered spool was created long enough
    ago that it may be missing Oracle rows produced since (today keeps
    growing until midnight, unlike a closed day -- see module docstring).

    Treated as stale whenever the metadata can't be read at all (missing or
    unparsable ``created_at``) -- that state is already anomalous by the
    time this is called (``get_spool_file_path`` just resolved a path from
    this same metadata store), so rebuilding is the safe default.
    """
    metadata = get_spool_metadata(PRODUCTION_ACHIEVEMENT_SPOOL_NAMESPACE, query_id)
    if not metadata:
        return True
    created_at = int(metadata.get("created_at") or 0)
    if not created_at:
        return True
    age_seconds = int(time.time()) - created_at
    return age_seconds >= _today_stale_threshold_seconds()


def _ensure_day_loaded(day: date, *, is_today: bool = False) -> Optional[str]:
    """Check the spool first; on miss -- or, for "today" only, on a stale
    hit -- (and only when the flag is on) build+run the warm-cache subclass
    for a single-day range (``start_date == end_date == day``).

    Args:
        is_today: When True, an existing spool is rebuilt if
            ``_is_today_spool_stale`` says it may be missing newly-arrived
            rows. ``ensure_yesterday_loaded`` never sets this -- a closed day
            is fresh forever once cached.

    Returns:
        The spool path if already warm (and, for today, still fresh) or
        after a successful run; the existing (possibly stale) spool path, or
        None on a true miss, if the flag is off (falls through to the
        existing 202-poll path, PA-14).
    """
    date_str = day.strftime("%Y-%m-%d")
    query_id = make_canonical_pa_spool_id(date_str, date_str)

    spool_path = get_spool_file_path(PRODUCTION_ACHIEVEMENT_SPOOL_NAMESPACE, query_id)
    if spool_path is not None and not (is_today and _is_today_spool_stale(query_id)):
        return spool_path

    if not _is_unified_job_enabled():
        logger.debug(
            "production_achievement_daily_cache: flag off, skipping warmup for %s",
            date_str,
        )
        return spool_path

    if spool_path is not None:
        logger.info(
            "production_achievement_daily_cache: today's spool %s is stale, rebuilding",
            query_id,
        )

    # Race-condition fix companion (query_spool_store's CAS write in
    # workers/production_achievement_worker.py): this scheduler-only guard
    # skips STARTING a new warmup job for a query_id that already has one
    # inflight (either a previous warmup cycle still running, or a
    # user-triggered force_refresh job) -- it never blocks/short-circuits
    # force_refresh itself (routes.py enqueues unconditionally, on purpose;
    # the CAS write is what protects its result from being clobbered by a
    # stale warmup, not this check).
    if get_inflight_state(PRODUCTION_ACHIEVEMENT_SPOOL_NAMESPACE, query_id) is not None:
        logger.info(
            "production_achievement_daily_cache: skipped duplicate warmup for %s, "
            "already inflight",
            query_id,
        )
        return spool_path

    job = _build_warmup_job(
        job_id=f"warmup-pa-{date_str}",
        params={"start_date": date_str, "end_date": date_str},
    )
    return job.run()


def ensure_today_loaded() -> Optional[str]:
    """Ensure today's DailyView (今日) spool is warm AND fresh (rebuilt if
    stale per ``_is_today_spool_stale``). Returns the spool path, or None if
    the flag is off and the spool is missing."""
    return _ensure_day_loaded(date.today(), is_today=True)


def ensure_yesterday_loaded() -> Optional[str]:
    """Ensure yesterday's DailyView (前日) spool is warm. Returns the spool
    path, or None if the flag is off and the spool is missing."""
    return _ensure_day_loaded(date.today() - timedelta(days=1))


# ---------------------------------------------------------------------------
# 轉出 (move-out) source -- same today/yesterday warm-cache shape as 產出
# above, applied to ``ProductionAchievementMoveoutJob``
# (workers/production_achievement_moveout_worker.py, PA-18) instead of
# ``ProductionAchievementJob``. Kept as parallel functions (not a shared
# parametrized helper) so the existing 產出 functions/tests above -- which
# patch ``_build_warmup_job``/``_is_today_spool_stale`` by name -- are left
# completely untouched.
# ---------------------------------------------------------------------------


def _build_warmup_moveout_job(job_id: str, params: dict):
    """Lazily import the moveout worker module and instantiate the
    progress-report-suppressing subclass. Only ever called AFTER
    ``_is_unified_job_enabled()`` has already returned True -- see
    ``_build_warmup_job`` above for the full rationale (identical here,
    just for ``ProductionAchievementMoveoutJob``).
    """
    from mes_dashboard.workers.production_achievement_moveout_worker import (
        ProductionAchievementMoveoutJob,
    )

    class _WarmupProductionAchievementMoveoutJob(ProductionAchievementMoveoutJob):
        """``progress_report()``-suppressing subclass (PA-14/PA-18).

        See module docstring for the Redis-orphan-key trap this override
        prevents. Must NEVER call ``update_job_progress`` -- a complete
        no-op is required, not merely a cheaper implementation.
        """

        def progress_report(self, pct: int) -> None:
            pass

    return _WarmupProductionAchievementMoveoutJob(job_id=job_id, params=params)


def _is_moveout_today_spool_stale(query_id: str) -> bool:
    """Moveout counterpart of ``_is_today_spool_stale`` -- reads spool
    metadata from ``PRODUCTION_ACHIEVEMENT_MOVEOUT_SPOOL_NAMESPACE`` instead
    of the 產出 namespace. Same staleness threshold
    (``_today_stale_threshold_seconds``) and same fail-open-to-stale
    behavior on missing/unparsable metadata."""
    metadata = get_spool_metadata(PRODUCTION_ACHIEVEMENT_MOVEOUT_SPOOL_NAMESPACE, query_id)
    if not metadata:
        return True
    created_at = int(metadata.get("created_at") or 0)
    if not created_at:
        return True
    age_seconds = int(time.time()) - created_at
    return age_seconds >= _today_stale_threshold_seconds()


def _ensure_moveout_day_loaded(day: date, *, is_today: bool = False) -> Optional[str]:
    """Moveout counterpart of ``_ensure_day_loaded`` -- identical control
    flow, but resolves the spool via
    ``PRODUCTION_ACHIEVEMENT_MOVEOUT_SPOOL_NAMESPACE``, keys the query id
    with ``source="moveout"``, and (on miss/stale) builds+runs
    ``ProductionAchievementMoveoutJob`` via ``_build_warmup_moveout_job``."""
    date_str = day.strftime("%Y-%m-%d")
    query_id = make_canonical_pa_spool_id(date_str, date_str, source="moveout")

    spool_path = get_spool_file_path(PRODUCTION_ACHIEVEMENT_MOVEOUT_SPOOL_NAMESPACE, query_id)
    if spool_path is not None and not (is_today and _is_moveout_today_spool_stale(query_id)):
        return spool_path

    if not _is_unified_job_enabled():
        logger.debug(
            "production_achievement_daily_cache: flag off, skipping moveout warmup for %s",
            date_str,
        )
        return spool_path

    if spool_path is not None:
        logger.info(
            "production_achievement_daily_cache: today's moveout spool %s is stale, rebuilding",
            query_id,
        )

    # Race-condition fix companion, moveout counterpart -- see
    # _ensure_day_loaded above for the full rationale (identical here, just
    # against PRODUCTION_ACHIEVEMENT_MOVEOUT_SPOOL_NAMESPACE).
    if get_inflight_state(PRODUCTION_ACHIEVEMENT_MOVEOUT_SPOOL_NAMESPACE, query_id) is not None:
        logger.info(
            "production_achievement_daily_cache: skipped duplicate moveout warmup for %s, "
            "already inflight",
            query_id,
        )
        return spool_path

    job = _build_warmup_moveout_job(
        job_id=f"warmup-pa-moveout-{date_str}",
        params={"start_date": date_str, "end_date": date_str},
    )
    return job.run()


def ensure_moveout_today_loaded() -> Optional[str]:
    """Ensure today's DailyView (今日) 轉出 spool is warm AND fresh (rebuilt
    if stale per ``_is_moveout_today_spool_stale``). Returns the spool path,
    or None if the flag is off and the spool is missing."""
    return _ensure_moveout_day_loaded(date.today(), is_today=True)


def ensure_moveout_yesterday_loaded() -> Optional[str]:
    """Ensure yesterday's DailyView (前日) 轉出 spool is warm. Returns the
    spool path, or None if the flag is off and the spool is missing."""
    return _ensure_moveout_day_loaded(date.today() - timedelta(days=1))
