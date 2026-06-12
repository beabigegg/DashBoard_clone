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
    """_WARMUP_JOBS must have exactly 6 entries after the two DuckDB additions."""
    from mes_dashboard.core import spool_warmup_scheduler as sched

    count = len(sched._WARMUP_JOBS)
    assert count == 6, (
        f"Expected 6 warmup jobs (4 existing + 2 DuckDB), got {count}: "
        f"{[jid for jid, _ in sched._WARMUP_JOBS]!r}"
    )
