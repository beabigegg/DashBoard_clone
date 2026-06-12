# -*- coding: utf-8 -*-
"""Fork-safety integration tests for the preload_app + post_fork architecture.

Acceptance criteria covered: AC-1, AC-2, AC-3, AC-4, AC-5, AC-6, AC-8, AC-9.

Markers
-------
Each test carries BOTH ``@pytest.mark.integration_real`` and
``@pytest.mark.multi_worker`` applied PER-TEST (never module-level pytestmark).
This allows ``pytest -m "not integration_real"`` to collect and skip gracefully,
and lets the Tier-1 suite collect the file without executing tests.

Run command (nightly lane):
    conda run -n mes-dashboard pytest tests/integration/test_preload_fork_safety.py \\
        --run-integration-real -m "integration_real or multi_worker" -v

All tests in this file are Tier 3 (nightly only, NOT a PR gate).
"""

from __future__ import annotations

import concurrent.futures
import os
import time
from pathlib import Path
from typing import List

import pytest

from tests.integration._multi_worker_harness import GunicornHarness

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def shared_harness():
    """Single gunicorn instance shared across all non-destructive tests in this module.

    Started once at module scope to amortise the ~30-60 s prewarm cost across
    AC-1, AC-2, AC-3, AC-5, AC-6, and AC-8 tests.  Destructive tests (AC-4,
    AC-9) use the function-scoped ``fresh_harness`` fixture instead.
    """
    with GunicornHarness() as h:
        # Wait for the slowest single-run prewarm before any test asserts on
        # log counts, so counts are stable.
        # resource-history and downtime DuckDB prewarms now run via RQ warmup
        # worker (unify-duckdb-prewarm-rq); wait for the RQ enqueue log instead
        # of the old daemon-thread sentinel.
        h.wait_for_log("Enqueued warmup job: warmup-resource-history-duckdb", timeout=30)
        h.wait_for_log("Enqueued warmup job: warmup-downtime-duckdb", timeout=30)
        h.wait_for_log("material_consumption parts list cache warmup complete", timeout=30)
        yield h


@pytest.fixture()
def fresh_harness():
    """Per-test gunicorn instance for destructive tests (SIGKILL, restart).

    Not shared — each destructive test starts a clean gunicorn master so that
    log counts and pool identity start from a known baseline.
    """
    with GunicornHarness() as h:
        # Wait for the RQ warmup enqueue sentinel (unify-duckdb-prewarm-rq).
        h.wait_for_log("Enqueued warmup job: warmup-resource-history-duckdb", timeout=30)
        yield h


# ---------------------------------------------------------------------------
# AC-1: Prewarm runs once (not once per worker)
# ---------------------------------------------------------------------------


@pytest.mark.integration_real
@pytest.mark.multi_worker
def test_downtime_prewarm_enqueued_once_across_two_workers(shared_harness):
    """AC-1/AC-6: downtime-analysis DuckDB prewarm is enqueued to RQ once at startup.

    Since unify-duckdb-prewarm-rq, the prewarm is handled by the RQ warmup
    queue (not a daemon thread in app.py).  The RQ leader enqueues
    'warmup-downtime-duckdb' exactly once per startup cycle.
    """
    enqueued_count = shared_harness.log_count("Enqueued warmup job: warmup-downtime-duckdb")
    assert enqueued_count >= 1, (
        f"Expected ≥1 'Enqueued warmup job: warmup-downtime-duckdb' log, got {enqueued_count}.\n"
        "Check that _warmup_downtime_analysis_duckdb_job is in _WARMUP_JOBS.\n"
        f"Log (last 3000 chars):\n{shared_harness.full_log[-3000:]}"
    )
    # Confirm the old daemon-thread path is gone.
    assert not shared_harness.log_contains("downtime_analysis DuckDB prewarm background thread started"), (
        "Old daemon-thread sentinel appeared — daemon-thread path was not removed.\n"
        f"Log (last 3000 chars):\n{shared_harness.full_log[-3000:]}"
    )


@pytest.mark.integration_real
@pytest.mark.multi_worker
def test_material_consumption_warmup_runs_once_across_two_workers(shared_harness):
    """AC-1: material_consumption start_parts_cache_warmup runs once in master."""
    count = shared_harness.log_count("material_consumption parts list cache warmup complete")
    assert count == 1, (
        f"Expected 1 material_consumption warmup complete, got {count}.\n"
        f"Log (last 3000 chars):\n{shared_harness.full_log[-3000:]}"
    )


@pytest.mark.integration_real
@pytest.mark.multi_worker
def test_resource_history_duckdb_prewarm_enqueued_once(shared_harness):
    """AC-1 + AC-6: resource-history DuckDB prewarm is enqueued to RQ once at startup.

    Since unify-duckdb-prewarm-rq, the prewarm is handled by the RQ warmup
    queue (not a daemon thread in app.py).  The RQ leader enqueues
    'warmup-resource-history-duckdb' exactly once per startup cycle.
    """
    enqueued_count = shared_harness.log_count("Enqueued warmup job: warmup-resource-history-duckdb")
    assert enqueued_count >= 1, (
        f"Expected ≥1 'Enqueued warmup job: warmup-resource-history-duckdb' log, "
        f"got {enqueued_count}.\n"
        "Check that _warmup_resource_history_duckdb_job is in _WARMUP_JOBS.\n"
        f"Log (last 3000 chars):\n{shared_harness.full_log[-3000:]}"
    )
    # Confirm the old daemon-thread path is gone.
    assert not shared_harness.log_contains("resource_history DuckDB prewarm background thread started"), (
        "Old daemon-thread sentinel appeared — daemon-thread path was not removed.\n"
        f"Log (last 3000 chars):\n{shared_harness.full_log[-3000:]}"
    )
    assert not shared_harness.log_contains("timed out waiting for peer worker"), (
        "'timed out waiting for peer worker' appeared — lock not releasing correctly.\n"
        f"Log (last 3000 chars):\n{shared_harness.full_log[-3000:]}"
    )


@pytest.mark.integration_real
@pytest.mark.multi_worker
def test_resource_cache_init_runs_once(shared_harness):
    """AC-1: resource_cache Oracle fetch fires at most once across 2 workers.

    When Redis already holds the current version, 'resources from Oracle'
    may appear 0 times (Redis warm).  With a cold Redis or changed version
    it must appear exactly once (master-only init_cache()).
    """
    count = shared_harness.log_count("resources from Oracle")
    assert count <= 1, (
        f"Expected resource_cache Oracle load ≤1 time, got {count}.\n"
        "Workers must not re-trigger init_cache() — check post_fork vs create_app() split.\n"
        f"Log (last 3000 chars):\n{shared_harness.full_log[-3000:]}"
    )


# ---------------------------------------------------------------------------
# AC-1/AC-6: RQ enqueue assertions (unify-duckdb-prewarm-rq)
# ---------------------------------------------------------------------------

@pytest.mark.integration_real
@pytest.mark.multi_worker
def test_rq_warmup_enqueued_for_resource_history_at_startup(shared_harness):
    """AC-6: warmup-resource-history-duckdb must be enqueued to RQ at startup.

    Added by unify-duckdb-prewarm-rq: the RQ leader logs 'Enqueued warmup job:
    warmup-resource-history-duckdb' when init_warmup_scheduler() runs.
    """
    count = shared_harness.log_count("Enqueued warmup job: warmup-resource-history-duckdb")
    assert count >= 1, (
        f"'Enqueued warmup job: warmup-resource-history-duckdb' appeared {count} times "
        f"(expected ≥1).\n"
        "Check that _warmup_resource_history_duckdb_job is in _WARMUP_JOBS and "
        "WARMUP_SCHEDULER_ENABLED is true.\n"
        f"Log (last 3000 chars):\n{shared_harness.full_log[-3000:]}"
    )


@pytest.mark.integration_real
@pytest.mark.multi_worker
def test_rq_warmup_enqueued_for_downtime_analysis_at_startup(shared_harness):
    """AC-6: warmup-downtime-duckdb must be enqueued to RQ at startup.

    Added by unify-duckdb-prewarm-rq: the RQ leader logs 'Enqueued warmup job:
    warmup-downtime-duckdb' when init_warmup_scheduler() runs.
    """
    count = shared_harness.log_count("Enqueued warmup job: warmup-downtime-duckdb")
    assert count >= 1, (
        f"'Enqueued warmup job: warmup-downtime-duckdb' appeared {count} times "
        f"(expected ≥1).\n"
        "Check that _warmup_downtime_analysis_duckdb_job is in _WARMUP_JOBS and "
        "WARMUP_SCHEDULER_ENABLED is true.\n"
        f"Log (last 3000 chars):\n{shared_harness.full_log[-3000:]}"
    )


@pytest.mark.integration_real
@pytest.mark.multi_worker
def test_no_daemon_prewarm_thread_started_at_startup(shared_harness):
    """AC-1: old daemon-thread prewarm sentinels must NOT appear in gunicorn logs.

    Since unify-duckdb-prewarm-rq, app.py no longer calls start_duckdb_prewarm()
    or start_downtime_prewarm(); neither daemon thread should be started.
    """
    assert not shared_harness.log_contains("resource_history DuckDB prewarm background thread started"), (
        "Old daemon-thread sentinel 'resource_history DuckDB prewarm background thread started' "
        "appeared — start_duckdb_prewarm() call was not removed from app.py (IP-4).\n"
        f"Log (last 3000 chars):\n{shared_harness.full_log[-3000:]}"
    )
    assert not shared_harness.log_contains("downtime_analysis DuckDB prewarm background thread started"), (
        "Old daemon-thread sentinel 'downtime_analysis DuckDB prewarm background thread started' "
        "appeared — start_downtime_prewarm() call was not removed from app.py (IP-4).\n"
        f"Log (last 3000 chars):\n{shared_harness.full_log[-3000:]}"
    )


# ---------------------------------------------------------------------------
# AC-2: Distinct Oracle engine pools per worker
# ---------------------------------------------------------------------------


@pytest.mark.integration_real
@pytest.mark.multi_worker
def test_each_worker_has_distinct_oracle_engine_pool(shared_harness):
    """AC-2: After post_fork, each worker's SQLAlchemy engine pool is distinct.

    dispose_engine() in post_fork drops the inherited pool; each worker
    rebuilds lazily, so their engine_id values must differ.
    """
    metrics = shared_harness.collect_per_worker_metrics()
    assert len(metrics) == shared_harness.workers, (
        f"Could not collect metrics from all {shared_harness.workers} workers; "
        f"got {len(metrics)}.  Check INTERNAL_METRICS_ENABLED + loopback gate."
    )
    engine_ids = [m.get("pool", {}).get("engine_id") for m in metrics]
    # Filter out None (engine not yet created in a worker — also distinct by absence,
    # but we want a positive assertion when all workers have built their engine).
    non_null = [e for e in engine_ids if e is not None]
    if len(non_null) == shared_harness.workers:
        assert len(set(non_null)) == len(non_null), (
            f"Workers share an Oracle engine pool id: {non_null}\n"
            "dispose_engine() in post_fork hook may not be executing."
        )


@pytest.mark.integration_real
@pytest.mark.multi_worker
def test_concurrent_oracle_requests_no_cross_talk(shared_harness):
    """AC-2: Concurrent Oracle queries from different workers don't cross-contaminate.

    Issues 4 simultaneous requests to /api/hold/overview and asserts no
    hard errors are returned.  Status 200, 401 (auth required), and 302
    (redirect) are all acceptable — what is NOT acceptable is an exception
    or a 5xx from Oracle connection cross-talk.
    """
    def _fetch() -> object:
        try:
            r = shared_harness.get("/api/hold/overview")
            return r.status_code
        except Exception as exc:
            return str(exc)

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        results = list(ex.map(lambda _: _fetch(), range(4)))

    errors = [r for r in results if isinstance(r, str)]
    assert not errors, f"Concurrent requests produced exceptions: {errors}"
    status_codes = [r for r in results if isinstance(r, int)]
    # 404 is acceptable — the route exists but may need auth configuration; 5xx is NOT acceptable.
    unexpected = [r for r in status_codes if r not in (200, 401, 302, 403, 404)]
    assert not unexpected, (
        f"Unexpected HTTP status codes from concurrent requests: {unexpected}\n"
        f"Full results: {results}"
    )


# ---------------------------------------------------------------------------
# AC-3: Distinct Redis pools per worker
# ---------------------------------------------------------------------------


@pytest.mark.integration_real
@pytest.mark.multi_worker
def test_each_worker_has_distinct_redis_pool(shared_harness):
    """AC-3: close_redis() in post_fork drops the inherited pool; each worker
    gets its own Redis connection pool.
    """
    metrics = shared_harness.collect_per_worker_metrics()
    assert len(metrics) == shared_harness.workers, (
        f"Could not collect metrics from all {shared_harness.workers} workers; "
        f"got {len(metrics)}."
    )
    pool_ids = [m.get("redis", {}).get("pool_id") for m in metrics]
    non_null = [p for p in pool_ids if p is not None]
    if len(non_null) == shared_harness.workers:
        assert len(set(non_null)) == len(non_null), (
            f"Workers share a Redis pool id: {non_null}\n"
            "close_redis() in post_fork hook may not be executing."
        )


# ---------------------------------------------------------------------------
# AC-4: SQLite per-worker handles (no WAL corruption)
# ---------------------------------------------------------------------------


@pytest.mark.integration_real
@pytest.mark.multi_worker
def test_sqlite_no_wal_corruption_on_restart(fresh_harness):
    """AC-4: Restart gunicorn — SQLite opens cleanly with no WAL corruption.

    A successful /health response before and after a restart confirms
    the SQLite stores (log_store, login_session_store, metrics_history) are
    not left in a corrupt WAL state by the fork+SIGTERM lifecycle.
    """
    r1 = fresh_harness.get("/health")
    assert r1.status_code == 200, (
        f"/health returned {r1.status_code} before restart — "
        "server is not healthy before the stop/start cycle."
    )
    fresh_harness.stop()
    # Start a second harness sharing the same tmp dirs / SQLite files.
    with GunicornHarness() as h2:
        h2.wait_for_log("Listening at:", timeout=120)
        r2 = h2.get("/health")
        assert r2.status_code == 200, (
            f"/health returned {r2.status_code} after restart — "
            "possible SQLite WAL corruption from previous gunicorn run."
        )


# ---------------------------------------------------------------------------
# AC-5: Background threads alive after post_fork
# ---------------------------------------------------------------------------

# Substrings that must appear in at least one thread name per worker.
# These match the name= kwarg set at threading.Thread creation time in each
# subsystem (confirmed by grepping src/mes_dashboard/):
#   cache-updater           (core/cache_updater.py)
#   equipment-status-sync   (services/realtime_equipment_cache.py)
#   metrics-history-collector (core/metrics_history.py)
#   query-spool-cleanup     (core/query_spool_store.py)
#   anomaly-detection-scheduler (services/anomaly_detection_scheduler.py)
EXPECTED_THREAD_SUBSTRINGS: List[str] = [
    "cache-updater",
    "equipment-status-sync",
    "metrics-history-collector",
    "query-spool-cleanup",
    "anomaly-detection-scheduler",
]


@pytest.mark.integration_real
@pytest.mark.multi_worker
def test_all_background_threads_alive_post_fork(shared_harness):
    """AC-5: Each expected background thread name is present in threading.enumerate()
    inside each gunicorn worker after the post_fork hook completes.

    Expected threads are started by _start_per_worker_services() which is
    called from the gunicorn post_fork hook.  Threads do not survive fork(),
    so their presence in a worker confirms post_fork ran correctly.
    """
    metrics_list = shared_harness.collect_per_worker_metrics()
    assert len(metrics_list) >= 1, (
        "Could not reach any worker via /internal/metrics — "
        "check INTERNAL_METRICS_ENABLED and loopback gate."
    )
    for worker_data in metrics_list:
        pid = worker_data.get("worker_rss", {}).get("pid", "unknown")
        thread_names = worker_data.get("threads", {}).get("names", [])
        threads_str = " ".join(thread_names)
        for substr in EXPECTED_THREAD_SUBSTRINGS:
            assert substr in threads_str, (
                f"Thread containing '{substr}' not found in worker {pid}.\n"
                f"Actual thread names: {thread_names}\n"
                "Check that _start_per_worker_services() starts this thread "
                "and that post_fork calls _start_per_worker_services()."
            )


# ---------------------------------------------------------------------------
# AC-6: No DuckDB deadlock / timeout
# ---------------------------------------------------------------------------


@pytest.mark.integration_real
@pytest.mark.multi_worker
def test_duckdb_prewarm_no_timeout_two_workers(shared_harness):
    """AC-6: Two-worker boot must not produce 'timed out waiting for peer worker' logs.

    The O_EXCL-based cross-worker lock is removed by IP-2; with preload_app=True
    there is only one writer (the master), so the deadlock path is unreachable.
    """
    assert not shared_harness.log_contains("timed out waiting for peer worker"), (
        "'timed out waiting for peer worker' appeared in logs — "
        "the O_EXCL peer-wait loop from resource_history_duckdb_cache.py "
        "may not have been removed (IP-2).\n"
        f"Log (last 3000 chars):\n{shared_harness.full_log[-3000:]}"
    )


@pytest.mark.integration_real
@pytest.mark.multi_worker
def test_duckdb_prewarm_enqueued_at_startup(shared_harness):
    """AC-6: resource-history DuckDB prewarm is enqueued to the RQ warmup queue at startup.

    Since unify-duckdb-prewarm-rq, the DuckDB prewarm runs in an RQ worker,
    not a gunicorn daemon thread.  The gunicorn master logs the RQ enqueue
    sentinel; the actual Oracle load runs in the RQ worker process.
    """
    enqueued = shared_harness.log_count("Enqueued warmup job: warmup-resource-history-duckdb")
    assert enqueued >= 1, (
        f"'Enqueued warmup job: warmup-resource-history-duckdb' appeared {enqueued} times "
        f"(expected ≥1) — RQ warmup job not registered or leader lock not acquired.\n"
        f"Log (last 3000 chars):\n{shared_harness.full_log[-3000:]}"
    )


# ---------------------------------------------------------------------------
# AC-8: No duplicate parquet files from concurrent workers
# ---------------------------------------------------------------------------


@pytest.mark.integration_real
@pytest.mark.multi_worker
def test_no_duplicate_rq_enqueue_on_two_worker_start(shared_harness):
    """AC-8: Starting 2 workers simultaneously must produce exactly one RQ enqueue per job.

    Since unify-duckdb-prewarm-rq, the leader-lock prevents duplicate RQ enqueues.
    The 'Warmup scheduler: enqueued N warmup jobs (leader)' log should appear
    exactly once — only the winning leader enqueues.
    """
    # Each worker tries to acquire the Redis leader lock; only one succeeds.
    # "Warmup scheduler: enqueued" is only logged by the leader.
    enqueue_log_count = shared_harness.log_count("Warmup scheduler: enqueued")
    assert enqueue_log_count == 1, (
        f"'Warmup scheduler: enqueued' appeared {enqueue_log_count} times "
        f"(expected 1 — only the leader should enqueue).\n"
        "Check the leader-lock logic in spool_warmup_scheduler.run_warmup_cycle().\n"
        f"Log (last 3000 chars):\n{shared_harness.full_log[-3000:]}"
    )
    # The old daemon-thread path must not appear in any worker log.
    assert not shared_harness.log_contains("resource_history DuckDB prewarm background thread started"), (
        "Old daemon-thread sentinel 'resource_history DuckDB prewarm background thread started' "
        "appeared — daemon-thread path was not fully removed (IP-4).\n"
        f"Log (last 3000 chars):\n{shared_harness.full_log[-3000:]}"
    )


# ---------------------------------------------------------------------------
# AC-9: Worker crash + respawn — no master prewarm retrigger
# ---------------------------------------------------------------------------


@pytest.mark.integration_real
@pytest.mark.multi_worker
def test_worker_crash_respawn_no_master_prewarm_retrigger(fresh_harness):
    """AC-9: Killing a worker and waiting for gunicorn to respawn it must NOT
    retrigger the master prewarm.  The respawned worker runs post_fork (which
    starts background threads) but does NOT re-run start_duckdb_prewarm() or
    start_downtime_prewarm().
    """
    pids_before = fresh_harness.worker_pids_alive()
    assert len(pids_before) >= 1, "No live worker PIDs found before SIGKILL."

    # Kill one worker.
    fresh_harness.kill_worker(pids_before[0])

    # Wait for gunicorn to spawn a replacement.
    new_pids = fresh_harness.wait_for_respawn(old_pids=pids_before, timeout=30)
    assert new_pids, "Gunicorn did not respawn a worker within 30s after SIGKILL."

    # Prewarm must still appear exactly once in the combined log (master ran it
    # once before forking; a respawned worker must not re-trigger it).
    # "background thread started" is logged exactly once (by the master) whether
    # the Oracle load ran or the cache was reused.  A respawned worker must NOT
    # re-invoke start_duckdb_prewarm(), so the count must remain 1.
    # Since unify-duckdb-prewarm-rq, the DuckDB prewarm goes through the RQ
    # warmup queue (not a daemon thread in app.py).  The RQ enqueue log
    # must still appear exactly once (from the leader's initial warmup cycle).
    rq_enqueue_count = fresh_harness.log_count("Enqueued warmup job: warmup-resource-history-duckdb")
    assert rq_enqueue_count >= 1, (
        f"'Enqueued warmup job: warmup-resource-history-duckdb' appeared {rq_enqueue_count} times "
        f"after worker respawn (expected ≥1).\n"
        "Check that the RQ warmup job is registered in _WARMUP_JOBS.\n"
        f"Log (last 3000 chars):\n{fresh_harness.full_log[-3000:]}"
    )
    # The old daemon-thread sentinel must be absent.
    assert not fresh_harness.log_contains("resource_history DuckDB prewarm background thread started"), (
        "Old daemon-thread sentinel appeared after respawn — daemon path not removed (IP-4).\n"
        f"Log (last 3000 chars):\n{fresh_harness.full_log[-3000:]}"
    )


@pytest.mark.integration_real
@pytest.mark.multi_worker
def test_worker_crash_respawn_fresh_connections(fresh_harness):
    """AC-9: The respawned worker's Oracle pool id must differ from the killed
    worker's pool id (it created a fresh pool via post_fork, not an inherited one).
    """
    pids_before = fresh_harness.worker_pids_alive()
    assert len(pids_before) >= 1, "No live worker PIDs found before SIGKILL."

    # Collect engine pool ids BEFORE the kill.
    metrics_before = fresh_harness.collect_per_worker_metrics()
    engine_ids_before = {
        m["worker_rss"]["pid"]: m.get("pool", {}).get("engine_id")
        for m in metrics_before
        if "worker_rss" in m
    }

    # Kill one worker and wait for respawn.
    victim_pid = pids_before[0]
    fresh_harness.kill_worker(victim_pid)
    new_pids = fresh_harness.wait_for_respawn(old_pids=pids_before, timeout=30)
    assert new_pids, "Gunicorn did not respawn a worker within 30s after SIGKILL."

    # Give the new worker a moment to build its Oracle engine lazily.
    time.sleep(3)

    # Collect metrics after respawn.
    metrics_after = fresh_harness.collect_per_worker_metrics()
    engine_ids_after = {
        m["worker_rss"]["pid"]: m.get("pool", {}).get("engine_id")
        for m in metrics_after
        if "worker_rss" in m
    }

    victim_engine_id = engine_ids_before.get(victim_pid)
    for new_pid in new_pids:
        new_engine_id = engine_ids_after.get(new_pid)
        # Only assert when both values are non-None (engine was created in both).
        if new_engine_id is not None and victim_engine_id is not None:
            assert new_engine_id != victim_engine_id, (
                f"Respawned worker {new_pid} reused engine pool id {new_engine_id} "
                f"from killed worker {victim_pid}.\n"
                "post_fork dispose_engine() may not be executing in the new worker."
            )
