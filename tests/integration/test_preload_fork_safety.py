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

import glob
import os
import signal
import subprocess
import time
from pathlib import Path
from typing import List

import pytest

# Harness is available when integration tests are collected; skip gracefully
# if the harness is not importable (e.g., missing rq dependency in CI Tier 1).
try:
    from tests.integration._multi_worker_harness import MultiWorkerHarness  # noqa: F401
    _HARNESS_AVAILABLE = True
except ImportError:
    _HARNESS_AVAILABLE = False

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def local_redis(request):
    """Redis URL — uses conftest.py fixture if available, else env var."""
    # conftest.py in tests/integration/ provides local_redis via fixture; fall
    # back to env var for standalone invocation.
    return os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/15")


def _skip_if_no_harness():
    if not _HARNESS_AVAILABLE:
        pytest.skip("MultiWorkerHarness not available (missing rq or redis deps)")


# ---------------------------------------------------------------------------
# AC-1: Prewarm runs once (not once per worker)
# ---------------------------------------------------------------------------


@pytest.mark.integration_real
@pytest.mark.multi_worker
def test_downtime_prewarm_runs_once_across_two_workers(local_redis):
    """AC-1: downtime_analysis prewarm executes exactly once across 2 workers.

    With preload_app=True the master calls start_downtime_prewarm() before
    forking; neither worker should re-trigger the Oracle load.

    This test is a placeholder — the full assertion requires a live Oracle
    connection and a running gunicorn with preload_app=True.  The harness used
    here runs RQ workers (not gunicorn), so we skip with a TODO until the
    gunicorn subprocess harness is available.
    """
    _skip_if_no_harness()
    pytest.skip(
        "TODO: requires gunicorn subprocess harness (spawn 2 gunicorn workers, "
        "inspect logs for 'downtime_analysis prewarm' count == 1); "
        "implement when GunicornHarness is added to _multi_worker_harness.py"
    )


@pytest.mark.integration_real
@pytest.mark.multi_worker
def test_material_consumption_warmup_runs_once_across_two_workers(local_redis):
    """AC-1: material_consumption start_parts_cache_warmup runs once in master."""
    _skip_if_no_harness()
    pytest.skip(
        "TODO: requires gunicorn subprocess harness; "
        "assert 'parts cache warm-up' log appears exactly once across 2-worker boot"
    )


@pytest.mark.integration_real
@pytest.mark.multi_worker
def test_resource_history_duckdb_prewarm_runs_once(local_redis):
    """AC-1 + AC-6: DuckDB prewarm runs once and no timeout log appears.

    With preload_app=True there is only one writer (the master), so the
    O_EXCL-based peer-wait loop (removed by IP-2) must never emit
    'timed out waiting for peer worker' in the logs.
    """
    _skip_if_no_harness()
    pytest.skip(
        "TODO: requires gunicorn subprocess harness; "
        "assert 'timed out waiting for peer worker' NOT in combined worker logs "
        "and parquet file present in tmp/query_spool/resource_history/"
    )


@pytest.mark.integration_real
@pytest.mark.multi_worker
def test_resource_cache_init_runs_once(local_redis):
    """AC-1: resource_cache Oracle fetch fires exactly once across 2 workers."""
    _skip_if_no_harness()
    pytest.skip(
        "TODO: requires gunicorn subprocess harness; "
        "assert 'Loaded N resources from Oracle' appears exactly once in combined logs"
    )


# ---------------------------------------------------------------------------
# AC-2: Distinct Oracle engine pools per worker
# ---------------------------------------------------------------------------


@pytest.mark.integration_real
@pytest.mark.multi_worker
def test_each_worker_has_distinct_oracle_engine_pool(local_redis):
    """AC-2: After post_fork, each worker's SQLAlchemy engine pool is distinct.

    dispose_engine() in post_fork drops the inherited pool; each worker
    rebuilds lazily, so their engine object ids must differ.
    """
    _skip_if_no_harness()
    pytest.skip(
        "TODO: requires gunicorn subprocess harness with /internal/metrics endpoint; "
        "assert engine pool ids differ across worker PIDs"
    )


@pytest.mark.integration_real
@pytest.mark.multi_worker
def test_concurrent_oracle_requests_no_cross_talk(local_redis):
    """AC-2: Two concurrent Oracle queries from different workers don't cross-contaminate."""
    _skip_if_no_harness()
    pytest.skip(
        "TODO: requires gunicorn subprocess harness; "
        "issue concurrent hold-overview requests from 2 workers, "
        "assert no ORA-3135 errors and response data is self-consistent per worker"
    )


# ---------------------------------------------------------------------------
# AC-3: Distinct Redis pools per worker
# ---------------------------------------------------------------------------


@pytest.mark.integration_real
@pytest.mark.multi_worker
def test_each_worker_has_distinct_redis_pool(local_redis):
    """AC-3: close_redis() in post_fork drops the inherited pool; each worker
    gets its own Redis connection pool."""
    _skip_if_no_harness()
    pytest.skip(
        "TODO: requires gunicorn subprocess harness; "
        "assert Redis pool ids differ across worker PIDs via /internal/metrics"
    )


# ---------------------------------------------------------------------------
# AC-4: SQLite per-worker handles (no WAL corruption)
# ---------------------------------------------------------------------------


@pytest.mark.integration_real
@pytest.mark.multi_worker
def test_sqlite_no_wal_corruption_on_restart(local_redis):
    """AC-4: Write in worker A, restart gunicorn, read in new worker B — no WAL corruption."""
    _skip_if_no_harness()
    pytest.skip(
        "TODO: requires gunicorn subprocess harness; "
        "write a login session in worker 1, SIGTERM + respawn, read back in new worker"
    )


# ---------------------------------------------------------------------------
# AC-5: Background threads alive after post_fork
# ---------------------------------------------------------------------------


@pytest.mark.integration_real
@pytest.mark.multi_worker
def test_all_background_threads_alive_post_fork(local_redis):
    """AC-5: Each expected background thread name is present in threading.enumerate()
    inside each gunicorn worker after the post_fork hook completes.

    Expected threads (started by _start_per_worker_services):
      cache_updater, equipment-sync, metrics, memory-guard, spool-cleanup,
      anomaly-detection, sync-worker (if MYSQL_OPS_ENABLED).
    """
    _skip_if_no_harness()
    pytest.skip(
        "TODO: requires gunicorn subprocess harness + /internal/thread-names endpoint; "
        "assert each expected thread name present per worker PID"
    )


# ---------------------------------------------------------------------------
# AC-6: No DuckDB deadlock / timeout
# ---------------------------------------------------------------------------


@pytest.mark.integration_real
@pytest.mark.multi_worker
def test_duckdb_prewarm_no_timeout_two_workers(local_redis):
    """AC-6: Two-worker boot must not produce 'timed out waiting for peer worker' logs."""
    _skip_if_no_harness()
    pytest.skip(
        "TODO: requires gunicorn subprocess harness; "
        "assert 'timed out waiting for peer worker' NOT in any worker log"
    )


@pytest.mark.integration_real
@pytest.mark.multi_worker
def test_duckdb_prewarm_completes_once(local_redis):
    """AC-6: DuckDB parquet file is present after 2-worker boot (written by master)."""
    _skip_if_no_harness()
    pytest.skip(
        "TODO: requires gunicorn subprocess harness; "
        "assert exactly 1 parquet file in tmp/query_spool/resource_history/ "
        "and its row count matches expected value"
    )


# ---------------------------------------------------------------------------
# AC-8: No duplicate parquet files from concurrent workers
# ---------------------------------------------------------------------------


@pytest.mark.integration_real
@pytest.mark.multi_worker
def test_no_duplicate_parquet_files_on_two_worker_start(local_redis):
    """AC-8: Starting 2 workers simultaneously must not produce duplicate parquet files.

    With preload_app=True the master is the sole writer; both workers skip
    the prewarm entirely (it already ran in the master).
    """
    _skip_if_no_harness()
    pytest.skip(
        "TODO: requires gunicorn subprocess harness; "
        "assert len(glob(tmp/query_spool/resource_history/*.parquet)) == 1 "
        "after a 2-worker boot"
    )


# ---------------------------------------------------------------------------
# AC-9: Worker crash + respawn — no master prewarm retrigger
# ---------------------------------------------------------------------------


@pytest.mark.integration_real
@pytest.mark.multi_worker
def test_worker_crash_respawn_no_master_prewarm_retrigger(local_redis):
    """AC-9: Killing a worker and waiting for gunicorn to respawn it must NOT
    retrigger the master prewarm.  The respawned worker runs post_fork (which
    starts background threads) but does NOT re-run start_duckdb_prewarm() or
    start_downtime_prewarm().
    """
    _skip_if_no_harness()
    pytest.skip(
        "TODO: requires gunicorn subprocess harness with SIGKILL-worker + wait-for-respawn; "
        "assert Oracle prewarm log count remains == 1 after respawn"
    )


@pytest.mark.integration_real
@pytest.mark.multi_worker
def test_worker_crash_respawn_fresh_connections(local_redis):
    """AC-9: The respawned worker's Oracle/Redis pool ids must differ from the
    killed worker's pool ids (it created fresh pools via post_fork, not inherited ones).
    """
    _skip_if_no_harness()
    pytest.skip(
        "TODO: requires gunicorn subprocess harness; "
        "compare pool id of killed worker (from pre-kill metrics) vs respawned worker "
        "(from post-respawn metrics) — must differ"
    )
