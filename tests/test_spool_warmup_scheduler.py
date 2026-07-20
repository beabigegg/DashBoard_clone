# -*- coding: utf-8 -*-
"""Unit tests for spool_warmup_scheduler.

Covers:
  - Leader lock prevents duplicate enqueue (task 3.5)
  - Skip warmup when valid spool already exists (task 3.5)
  - Sequential execution of warmup jobs (task 3.5)
  - Interval-based refresh (task 3.5)
  - production-history is never in _WARMUP_JOBS (task 3.4 / 10.5)
"""

from __future__ import annotations

import time
from typing import List
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_scheduler_state():
    """Stop scheduler between tests."""
    from mes_dashboard.core import spool_warmup_scheduler as sched
    yield
    sched.stop_warmup_scheduler(timeout=1)
    sched._STOP_EVENT.clear()
    sched._SCHEDULER_THREAD = None


# ---------------------------------------------------------------------------
# Test: production-history guard (task 3.4 / 10.5)
# ---------------------------------------------------------------------------

def test_production_history_not_in_warmup_jobs():
    """production-history must never appear in _WARMUP_JOBS.

    If this test fails, a warmup job for production-history was added without
    completing the required design review (see scheduler module docstring).
    """
    from mes_dashboard.core import spool_warmup_scheduler as sched

    job_fn_names = [fn.__name__ for _, fn in sched._WARMUP_JOBS]
    for name in job_fn_names:
        assert "production" not in name.lower(), (
            f"production-history warmup job found in _WARMUP_JOBS: {name!r}. "
            "This is prohibited without a design review (task 3.4)."
        )

    job_id_prefixes = [jid for jid, _ in sched._WARMUP_JOBS]
    for prefix in job_id_prefixes:
        assert "production" not in prefix.lower(), (
            f"production-history warmup job id found: {prefix!r}"
        )


# ---------------------------------------------------------------------------
# Test: leader lock prevents duplicate enqueue
# ---------------------------------------------------------------------------

def test_leader_lock_prevents_duplicate_enqueue():
    """Only the worker that acquires the leader lock should enqueue jobs."""
    from mes_dashboard.core import spool_warmup_scheduler as sched

    enqueue_calls: List[str] = []

    def fake_enqueue_jobs():
        enqueue_calls.append("enqueued")
        return len(sched._WARMUP_JOBS)

    lock_holder = [False]

    def fake_try_acquire_lock(name, ttl_seconds=60, *, fail_mode=None):
        if not lock_holder[0]:
            lock_holder[0] = True
            return True
        return False  # second worker fails

    with patch.object(sched, "_enqueue_warmup_jobs", side_effect=fake_enqueue_jobs):
        with patch("mes_dashboard.core.spool_warmup_scheduler.try_acquire_lock", side_effect=fake_try_acquire_lock):
            with patch("mes_dashboard.core.spool_warmup_scheduler.release_lock"):
                with patch("mes_dashboard.core.spool_warmup_scheduler.REDIS_ENABLED", True):
                    # Worker 1 — should become leader
                    result1 = sched.run_warmup_cycle()
                    # Worker 2 — should not enqueue
                    result2 = sched.run_warmup_cycle()

    assert result1 is True
    assert result2 is False
    assert len(enqueue_calls) == 1, "Only leader should enqueue warmup jobs"


# ---------------------------------------------------------------------------
# Test: enqueue-cooldown dedupes near-simultaneous leader-lock winners
#
# Reproduces the observed bug: multiple gunicorn worker processes each call
# run_warmup_cycle() close together (e.g. all at boot). Because the leader
# lock is only held for the brief acquire-enqueue-release window (not the
# full WARMUP_INTERVAL_SECONDS cycle), each worker can win the SAME lock in
# rapid sequential succession and each enqueue its own duplicate batch of
# warmup jobs. The cooldown key (_claim_enqueue_cooldown) must ensure only
# ONE of them actually enqueues.
# ---------------------------------------------------------------------------

class _FakeCooldownRedis:
    """Minimal in-memory stand-in for the control-plane Redis client --
    just enough SET NX EX semantics to exercise the cooldown gate without a
    real Redis server. Clock is injectable so tests can simulate time
    passing (a later cycle) without sleeping."""

    def __init__(self, clock):
        self._clock = clock
        self._expire_at = {}  # key -> expire timestamp (float) or None (no TTL)

    def set(self, key, value, nx=False, ex=None):
        now = self._clock()
        expire_at = self._expire_at.get(key)
        if nx and expire_at is not None and expire_at > now:
            return None  # key still present and not yet expired -- NX fails
        self._expire_at[key] = (now + ex) if ex else None
        return True


def test_cooldown_allows_only_one_enqueue_among_near_simultaneous_workers():
    """N gunicorn workers each independently winning the (fast-lived) leader
    lock in rapid succession must still result in exactly ONE enqueue batch
    within a WARMUP_INTERVAL_SECONDS window."""
    from mes_dashboard.core import spool_warmup_scheduler as sched

    call_log: List[str] = []

    def fake_enqueue():
        call_log.append("enqueue")
        return len(sched._WARMUP_JOBS)

    fake_clock = {"t": 1_000_000.0}
    fake_redis = _FakeCooldownRedis(clock=lambda: fake_clock["t"])

    with patch.object(sched, "_enqueue_warmup_jobs", side_effect=fake_enqueue):
        with patch("mes_dashboard.core.spool_warmup_scheduler.try_acquire_lock", return_value=True):
            with patch("mes_dashboard.core.spool_warmup_scheduler.release_lock"):
                with patch("mes_dashboard.core.spool_warmup_scheduler.REDIS_ENABLED", True):
                    with patch("mes_dashboard.core.spool_warmup_scheduler.get_redis_client", return_value=fake_redis):
                        # 3 gunicorn workers, each independently winning the
                        # leader lock (mocked to always succeed, mirroring
                        # how the real lock behaves once the previous holder
                        # has already released it) within the same instant.
                        results = [sched.run_warmup_cycle() for _ in range(3)]

    assert len(call_log) == 1, (
        f"Expected exactly one enqueue batch across 3 near-simultaneous "
        f"leader-lock winners, got {len(call_log)}"
    )
    assert results == [True, False, False]


def test_cooldown_allows_enqueue_again_after_interval_elapses():
    """A genuine next cycle roughly WARMUP_INTERVAL_SECONDS later must still
    enqueue -- the cooldown guard must not become a permanent one-shot."""
    from mes_dashboard.core import spool_warmup_scheduler as sched

    call_log: List[str] = []

    def fake_enqueue():
        call_log.append("enqueue")
        return len(sched._WARMUP_JOBS)

    fake_clock = {"t": 1_000_000.0}
    fake_redis = _FakeCooldownRedis(clock=lambda: fake_clock["t"])

    with patch.object(sched, "_enqueue_warmup_jobs", side_effect=fake_enqueue):
        with patch("mes_dashboard.core.spool_warmup_scheduler.try_acquire_lock", return_value=True):
            with patch("mes_dashboard.core.spool_warmup_scheduler.release_lock"):
                with patch("mes_dashboard.core.spool_warmup_scheduler.REDIS_ENABLED", True):
                    with patch("mes_dashboard.core.spool_warmup_scheduler.get_redis_client", return_value=fake_redis):
                        first = sched.run_warmup_cycle()
                        second_immediate = sched.run_warmup_cycle()
                        # Simulate real time passing well past the cooldown window
                        # (the next hourly tick, or a later boot).
                        fake_clock["t"] += sched.WARMUP_INTERVAL_SECONDS + 1
                        third_after_interval = sched.run_warmup_cycle()

    assert first is True
    assert second_immediate is False
    assert third_after_interval is True
    assert len(call_log) == 2, "Both the first and the post-interval cycle must enqueue"


def test_cooldown_check_fails_open_when_redis_client_unavailable():
    """If the cooldown key specifically cannot be checked (Redis client
    unavailable at that instant), enqueueing must still proceed rather than
    silently disabling warmup -- the leader lock remains the primary
    correctness guarantee. (This mirrors the default test environment where
    REDIS_ENABLED is false at the redis_client module level and
    get_redis_client() returns None, which is exactly what every other test
    in this file already relies on implicitly.)"""
    from mes_dashboard.core import spool_warmup_scheduler as sched

    call_log: List[str] = []

    def fake_enqueue():
        call_log.append("enqueue")
        return len(sched._WARMUP_JOBS)

    with patch.object(sched, "_enqueue_warmup_jobs", side_effect=fake_enqueue):
        with patch("mes_dashboard.core.spool_warmup_scheduler.try_acquire_lock", return_value=True):
            with patch("mes_dashboard.core.spool_warmup_scheduler.release_lock"):
                with patch("mes_dashboard.core.spool_warmup_scheduler.REDIS_ENABLED", True):
                    with patch("mes_dashboard.core.spool_warmup_scheduler.get_redis_client", return_value=None):
                        result = sched.run_warmup_cycle()

    assert result is True
    assert len(call_log) == 1


# ---------------------------------------------------------------------------
# Test: all expected warmup jobs are present
# ---------------------------------------------------------------------------

def test_warmup_jobs_include_expected_reports():
    from mes_dashboard.core import spool_warmup_scheduler as sched

    job_fn_names = {fn.__name__ for _, fn in sched._WARMUP_JOBS}
    assert "_warmup_reject_dataset_job" in job_fn_names
    assert "_warmup_yield_alert_dataset_job" in job_fn_names
    assert "_warmup_hold_dataset_job" in job_fn_names
    assert "_warmup_resource_dataset_job" in job_fn_names


# ---------------------------------------------------------------------------
# Test: scheduler disabled when WARMUP_SCHEDULER_ENABLED=false
# ---------------------------------------------------------------------------

def test_run_warmup_cycle_returns_false_when_disabled():
    from mes_dashboard.core import spool_warmup_scheduler as sched

    with patch.object(sched, "WARMUP_SCHEDULER_ENABLED", False):
        result = sched.run_warmup_cycle()

    assert result is False


# ---------------------------------------------------------------------------
# Test: sequential execution — enqueue is called once per cycle
# ---------------------------------------------------------------------------

def test_enqueue_called_sequentially():
    from mes_dashboard.core import spool_warmup_scheduler as sched

    call_log: List[str] = []

    def fake_enqueue():
        call_log.append("enqueue")
        return 4

    with patch.object(sched, "_enqueue_warmup_jobs", side_effect=fake_enqueue):
        with patch("mes_dashboard.core.spool_warmup_scheduler.try_acquire_lock", return_value=True):
            with patch("mes_dashboard.core.spool_warmup_scheduler.release_lock"):
                with patch("mes_dashboard.core.spool_warmup_scheduler.REDIS_ENABLED", True):
                    sched.run_warmup_cycle()
                    sched.run_warmup_cycle()

    assert len(call_log) == 2


# ---------------------------------------------------------------------------
# Test: init_warmup_scheduler starts thread and runs initial cycle
# ---------------------------------------------------------------------------

def test_init_warmup_scheduler_starts_thread():
    from mes_dashboard.core import spool_warmup_scheduler as sched

    with patch.object(sched, "run_warmup_cycle", return_value=True) as mock_cycle:
        with patch("mes_dashboard.core.spool_warmup_scheduler.WARMUP_SCHEDULER_ENABLED", True):
            with patch("mes_dashboard.core.spool_warmup_scheduler.REDIS_ENABLED", True):
                # Use a large interval so thread doesn't loop in test
                with patch("mes_dashboard.core.spool_warmup_scheduler.WARMUP_INTERVAL_SECONDS", 9999):
                    sched.init_warmup_scheduler(app=None)
                    time.sleep(0.05)

    assert mock_cycle.called
    assert sched._SCHEDULER_THREAD is not None
    assert sched._SCHEDULER_THREAD.is_alive()


# ---------------------------------------------------------------------------
# AC-3: new DuckDB prewarm entries in _WARMUP_JOBS (unify-duckdb-prewarm-rq)
# ---------------------------------------------------------------------------

def test_resource_history_duckdb_in_warmup_jobs():
    """_WARMUP_JOBS must contain a resource-history DuckDB entry (AC-3)."""
    from mes_dashboard.core import spool_warmup_scheduler as sched

    job_id_prefixes = [jid for jid, _ in sched._WARMUP_JOBS]
    assert any("resource-history-duckdb" in prefix for prefix in job_id_prefixes), (
        "No 'resource-history-duckdb' entry found in _WARMUP_JOBS prefixes: "
        f"{job_id_prefixes!r}. Add it per IP-1."
    )


def test_downtime_analysis_duckdb_in_warmup_jobs():
    """_WARMUP_JOBS must contain a downtime-analysis DuckDB entry (AC-3)."""
    from mes_dashboard.core import spool_warmup_scheduler as sched

    job_id_prefixes = [jid for jid, _ in sched._WARMUP_JOBS]
    assert any("downtime-duckdb" in prefix for prefix in job_id_prefixes), (
        "No 'downtime-duckdb' entry found in _WARMUP_JOBS prefixes: "
        f"{job_id_prefixes!r}. Add it per IP-1."
    )


def test_warmup_jobs_total_count_after_duckdb_additions():
    """_WARMUP_JOBS must have exactly 10 entries after the two DuckDB
    additions, the two production-achievement 產出 today/yesterday additions
    (production-achievement-overhaul, PA-14), and the two production-achievement
    轉出 (move-out) today/yesterday additions (PA-18)."""
    from mes_dashboard.core import spool_warmup_scheduler as sched

    count = len(sched._WARMUP_JOBS)
    assert count == 10, (
        f"Expected 10 warmup jobs (4 existing + 2 DuckDB + 2 production-achievement "
        f"output + 2 production-achievement moveout), "
        f"got {count}: {[jid for jid, _ in sched._WARMUP_JOBS]!r}"
    )


# ---------------------------------------------------------------------------
# PA-14: production-achievement today/yesterday warmup jobs (production-achievement-overhaul)
#
# NOTE: job-id prefixes/fn names use "achievement" (not "production_achievement"
# / "production-achievement") -- test_production_history_not_in_warmup_jobs
# above does a coarse substring scan for "production" (meant to catch a real
# production-HISTORY warmup entry) and must stay unchanged/still pass; see
# spool_warmup_scheduler._warmup_achievement_today_job's docstring.
# ---------------------------------------------------------------------------

def test_warmup_jobs_include_production_achievement_today_and_yesterday():
    """_WARMUP_JOBS must contain both a production-achievement 'today' and
    'yesterday' entry (PA-14, Phase 5)."""
    from mes_dashboard.core import spool_warmup_scheduler as sched

    job_id_prefixes = [jid for jid, _ in sched._WARMUP_JOBS]
    assert any("achievement" in p and "today" in p for p in job_id_prefixes), (
        f"No production-achievement 'today' entry found in _WARMUP_JOBS prefixes: "
        f"{job_id_prefixes!r}"
    )
    assert any("achievement" in p and "yesterday" in p for p in job_id_prefixes), (
        f"No production-achievement 'yesterday' entry found in _WARMUP_JOBS prefixes: "
        f"{job_id_prefixes!r}"
    )


def test_production_achievement_warmup_jobs_call_ensure_today_yesterday_loaded():
    """The two new _WARMUP_JOBS entries must be thin wrappers around
    ensure_today_loaded()/ensure_yesterday_loaded() -- mirrors the existing
    6 entries' try/except-log shape (module docstring)."""
    from mes_dashboard.core import spool_warmup_scheduler as sched

    job_fns_by_prefix = dict(sched._WARMUP_JOBS)
    today_prefix = next(p for p in job_fns_by_prefix if "achievement" in p and "today" in p)
    yesterday_prefix = next(p for p in job_fns_by_prefix if "achievement" in p and "yesterday" in p)

    with patch(
        "mes_dashboard.services.production_achievement_daily_cache.ensure_today_loaded",
        return_value="/fake/today.parquet",
    ) as mock_today:
        job_fns_by_prefix[today_prefix]()
    mock_today.assert_called_once()

    with patch(
        "mes_dashboard.services.production_achievement_daily_cache.ensure_yesterday_loaded",
        return_value="/fake/yesterday.parquet",
    ) as mock_yesterday:
        job_fns_by_prefix[yesterday_prefix]()
    mock_yesterday.assert_called_once()


def test_production_achievement_warmup_job_failure_is_caught_and_logged():
    """Mirrors the existing 6 entries' try/except-log shape: an exception
    from ensure_today_loaded() must never propagate out of the warmup job
    wrapper (a scheduler-wide outage in one job must not block the others)."""
    from mes_dashboard.core import spool_warmup_scheduler as sched

    job_fns_by_prefix = dict(sched._WARMUP_JOBS)
    today_prefix = next(p for p in job_fns_by_prefix if "achievement" in p and "today" in p)

    with patch(
        "mes_dashboard.services.production_achievement_daily_cache.ensure_today_loaded",
        side_effect=RuntimeError("boom"),
    ):
        job_fns_by_prefix[today_prefix]()  # must not raise


# ---------------------------------------------------------------------------
# PA-18: production-achievement 轉出 (move-out) today/yesterday warmup jobs
#
# Mirrors the PA-14 產出 tests above 1:1, targeting the "moveout" entries.
# Job-id prefixes/fn names use "achievement-moveout" for the same
# substring-scan-avoidance reason as "achievement" above -- see
# _warmup_achievement_moveout_today_job's docstring.
# ---------------------------------------------------------------------------

def test_warmup_jobs_include_production_achievement_moveout_today_and_yesterday():
    """_WARMUP_JOBS must contain both a production-achievement moveout
    'today' and 'yesterday' entry (PA-18)."""
    from mes_dashboard.core import spool_warmup_scheduler as sched

    job_id_prefixes = [jid for jid, _ in sched._WARMUP_JOBS]
    assert any("achievement" in p and "moveout" in p and "today" in p for p in job_id_prefixes), (
        f"No production-achievement moveout 'today' entry found in _WARMUP_JOBS prefixes: "
        f"{job_id_prefixes!r}"
    )
    assert any("achievement" in p and "moveout" in p and "yesterday" in p for p in job_id_prefixes), (
        f"No production-achievement moveout 'yesterday' entry found in _WARMUP_JOBS prefixes: "
        f"{job_id_prefixes!r}"
    )


def test_production_achievement_moveout_warmup_jobs_call_ensure_today_yesterday_loaded():
    """The two new moveout _WARMUP_JOBS entries must be thin wrappers around
    ensure_moveout_today_loaded()/ensure_moveout_yesterday_loaded() -- mirrors
    the existing 8 entries' try/except-log shape (module docstring)."""
    from mes_dashboard.core import spool_warmup_scheduler as sched

    job_fns_by_prefix = dict(sched._WARMUP_JOBS)
    today_prefix = next(
        p for p in job_fns_by_prefix if "achievement" in p and "moveout" in p and "today" in p
    )
    yesterday_prefix = next(
        p for p in job_fns_by_prefix if "achievement" in p and "moveout" in p and "yesterday" in p
    )

    with patch(
        "mes_dashboard.services.production_achievement_daily_cache.ensure_moveout_today_loaded",
        return_value="/fake/moveout-today.parquet",
    ) as mock_today:
        job_fns_by_prefix[today_prefix]()
    mock_today.assert_called_once()

    with patch(
        "mes_dashboard.services.production_achievement_daily_cache.ensure_moveout_yesterday_loaded",
        return_value="/fake/moveout-yesterday.parquet",
    ) as mock_yesterday:
        job_fns_by_prefix[yesterday_prefix]()
    mock_yesterday.assert_called_once()


def test_production_achievement_moveout_warmup_job_failure_is_caught_and_logged():
    """Mirrors the existing entries' try/except-log shape: an exception from
    ensure_moveout_today_loaded() must never propagate out of the warmup job
    wrapper (a scheduler-wide outage in one job must not block the others)."""
    from mes_dashboard.core import spool_warmup_scheduler as sched

    job_fns_by_prefix = dict(sched._WARMUP_JOBS)
    today_prefix = next(
        p for p in job_fns_by_prefix if "achievement" in p and "moveout" in p and "today" in p
    )

    with patch(
        "mes_dashboard.services.production_achievement_daily_cache.ensure_moveout_today_loaded",
        side_effect=RuntimeError("boom"),
    ):
        job_fns_by_prefix[today_prefix]()  # must not raise


def test_production_history_guard_still_passes_with_moveout_entries():
    """Regression: the moveout job-id prefixes/fn names must not accidentally
    reintroduce the "production" substring that test_production_history_not_in_warmup_jobs
    scans for."""
    from mes_dashboard.core import spool_warmup_scheduler as sched

    job_fn_names = [fn.__name__ for _, fn in sched._WARMUP_JOBS]
    job_id_prefixes = [jid for jid, _ in sched._WARMUP_JOBS]
    for name in job_fn_names:
        assert "production" not in name.lower()
    for prefix in job_id_prefixes:
        assert "production" not in prefix.lower()
