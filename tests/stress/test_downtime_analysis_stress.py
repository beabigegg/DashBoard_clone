# -*- coding: utf-8 -*-
"""Stress and soak tests for downtime-analysis browser-DuckDB migration.

Change: downtime-browser-duckdb (Tier 0, high-risk)
Gate:   stress-oom-elimination (ci-gates.md Tier 4, weekly)
        soak-memory-stable     (ci-gates.md Tier 4, weekly)

Purpose
-------
Prove that the new raw-parquet server path (DOWNTIME_BROWSER_DUCKDB=true)
does not reproduce the gunicorn OOM kills observed on the 6 GB/no-swap host.

The OOM source in the old path:
  _merge_cross_shift_events(base_df) calls df.copy() on a 184k-row DataFrame,
  then allocates several intermediate Series for sort/groupby.  Peak RAM per
  request reached roughly 2× the input frame size (~240+ MB for a 180-day
  range), and three concurrent wide-range queries exhausted the 6 GB host.

New path contract (AC-2, design.md §Service row):
  query_downtime_dataset_raw() writes the raw base_events and job_bridge
  parquets without running _merge_cross_shift_events, _bridge_jobid, or
  _enrich_events_df.  The server-side RAM cost is bounded by the BQE fetch
  buffer, which is much smaller than the doubled-copy peak of the old path.

Run commands
------------
# Stress (all TestDowntimeRawSpoolMemory tests):
    pytest tests/stress/test_downtime_analysis_stress.py -m stress -v

# Soak only:
    pytest tests/stress/test_downtime_analysis_stress.py -m soak -v

# Both:
    pytest tests/stress/test_downtime_analysis_stress.py -m "stress or soak" -v

All tests use a synthetic in-process Oracle mock so no live DB is needed.
"""

from __future__ import annotations

import concurrent.futures
import gc
import os
import sys
import time
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import psutil
import pytest

# ---------------------------------------------------------------------------
# Synthetic fixture factory
# ---------------------------------------------------------------------------

# Required columns for base_events parquet (design.md §Parquet Schema)
_BASE_EVENTS_COLS = [
    "HISTORYID",
    "OLDSTATUSNAME",
    "OLDREASONNAME",
    "OLDLASTSTATUSCHANGEDATE",
    "LASTSTATUSCHANGEDATE",
    "HOURS",
    "JOBID",
]

# Required columns for job_bridge parquet (design.md §Parquet Schema)
_JOB_BRIDGE_COLS = [
    "JOBID",
    "RESOURCEID",
    "CREATEDATE",
    "COMPLETEDATE",
    "SYMPTOMCODENAME",
    "CAUSECODENAME",
    "REPAIRCODENAME",
    "COMPLETE_FULLNAME",
    "FIRSTCLOCKONDATE",
    "LASTCLOCKOFFDATE",
    "JOBORDERNAME",
    "JOBMODELNAME",
    "ASSIGNED_DATE",
    "ACK_DATE",
    "INSPECT_START",
    "INSPECT_END",
]

_STATUS_POOL = ["E10", "EGT", "PM", "STDBY", "DOWN"]
_REASON_POOL = [
    "Idle",
    "TMTT_RECV",
    "Machine Down",
    "Programing",
    "Cleanning",
    "Chuck 吸附",
    None,
    "",
]
_RESOURCE_IDS = [f"EQ-{i:04d}" for i in range(1, 21)]  # 20 equipment IDs


def _make_base_events_df(n_rows: int = 100_000, seed: int = 42) -> pd.DataFrame:
    """Return a synthetic base_events DataFrame with n_rows rows.

    Includes cross-midnight events (OLDLASTSTATUSCHANGEDATE on day N,
    LASTSTATUSCHANGEDATE on day N+1) and duplicate HISTORYID fragments to
    exercise the merge path in parity tests.
    """
    rng = np.random.default_rng(seed)

    hist_ids = [f"EQ-{rng.integers(1, 21):04d}" for _ in range(n_rows)]
    statuses = [_STATUS_POOL[i % len(_STATUS_POOL)] for i in range(n_rows)]
    reasons = [_REASON_POOL[rng.integers(0, len(_REASON_POOL))] for _ in range(n_rows)]

    # Timestamps: spread over 180 days
    base_ts = pd.Timestamp("2025-12-01 00:00:00")
    duration_hours = rng.uniform(0.1, 8.0, size=n_rows)
    start_offsets_h = rng.uniform(0, 180 * 24, size=n_rows)

    old_start = [base_ts + pd.Timedelta(hours=float(o)) for o in start_offsets_h]
    old_end = [s + pd.Timedelta(hours=float(d)) for s, d in zip(old_start, duration_hours)]

    # Sprinkle a few cross-midnight events (first 200 rows)
    for i in range(min(200, n_rows)):
        # Force start at 23:30 on some day so end crosses midnight
        day_offset = int(start_offsets_h[i]) // 24
        old_start[i] = base_ts + pd.Timedelta(days=day_offset, hours=23, minutes=30)
        old_end[i] = old_start[i] + pd.Timedelta(hours=1.5)  # crosses midnight

    jobids = [f"JOB-{rng.integers(1, 500):05d}" if rng.random() > 0.4 else None
              for _ in range(n_rows)]

    df = pd.DataFrame({
        "HISTORYID": hist_ids,
        "OLDSTATUSNAME": statuses,
        "OLDREASONNAME": reasons,
        "OLDLASTSTATUSCHANGEDATE": old_start,
        "LASTSTATUSCHANGEDATE": old_end,
        "HOURS": duration_hours.tolist(),
        "JOBID": jobids,
    })
    return df


def _make_job_bridge_df(n_rows: int = 5_000, seed: int = 99) -> pd.DataFrame:
    """Return a synthetic job_bridge DataFrame."""
    rng = np.random.default_rng(seed)

    base_ts = pd.Timestamp("2025-12-01 00:00:00")
    create_offsets = rng.uniform(0, 180 * 24, size=n_rows)
    durations = rng.uniform(1.0, 48.0, size=n_rows)

    create_dates = [base_ts + pd.Timedelta(hours=float(o)) for o in create_offsets]
    complete_dates = [c + pd.Timedelta(hours=float(d)) for c, d in zip(create_dates, durations)]

    df = pd.DataFrame({
        "JOBID": [f"JOB-{i:05d}" for i in rng.integers(1, 500, size=n_rows)],
        "RESOURCEID": [_RESOURCE_IDS[i % len(_RESOURCE_IDS)] for i in range(n_rows)],
        "CREATEDATE": create_dates,
        "COMPLETEDATE": complete_dates,
        "SYMPTOMCODENAME": [f"SYM-{i % 20}" for i in range(n_rows)],
        "CAUSECODENAME": [f"CAUSE-{i % 15}" for i in range(n_rows)],
        "REPAIRCODENAME": [f"REPAIR-{i % 10}" for i in range(n_rows)],
        "COMPLETE_FULLNAME": [f"Tech-{i % 30}" for i in range(n_rows)],
        "FIRSTCLOCKONDATE": create_dates,
        "LASTCLOCKOFFDATE": complete_dates,
        "JOBORDERNAME": [f"JO-{i:06d}" for i in range(n_rows)],
        "JOBMODELNAME": [f"MODEL-{i % 5}" for i in range(n_rows)],
        "ASSIGNED_DATE": create_dates,
        "ACK_DATE": create_dates,
        "INSPECT_START": create_dates,
        "INSPECT_END": complete_dates,
    })
    return df


# ---------------------------------------------------------------------------
# Patch helpers
# ---------------------------------------------------------------------------

def _build_raw_service_patches(
    base_df: pd.DataFrame,
    job_df: pd.DataFrame,
) -> List[Any]:
    """Return a list of patch() context managers that wire query_downtime_dataset_raw
    to use the supplied DataFrames instead of hitting Oracle or DuckDB.

    The patches cover:
    1. Cache miss — force both spools to appear absent so the Oracle path runs.
    2. DuckDB unavailable — so the mock Oracle path is exercised.
    3. Oracle read_sql_df_slow — returns base_df / job_df.
    4. execute_plan / merge_chunks_to_spool — no-op (BQE internals).
    5. store_downtime_base_events / store_downtime_job_bridge — no-op (no FS writes).
    6. _apply_resource_filters — pass-through (returns df unchanged).
    7. QueryBuilder IN-list — returns an empty condition string (no bind params).

    This set of patches is sufficient to exercise the full raw-path hot code
    (the block that builds base_df/job_df and calls the store functions) without
    any external I/O.
    """
    call_counter = {"n": 0}

    def _mock_read_sql_df(sql, params, *, caller=""):
        n = call_counter["n"]
        call_counter["n"] += 1
        if n == 0:
            return base_df.copy()  # first call: base_events
        return job_df.copy()       # second call: job_bridge

    # Fake execute_plan writes nothing but doesn't raise
    def _noop_execute_plan(*args, **kwargs):
        return None

    # Fake merge_chunks_to_spool returns (None, 0) so base_df falls to empty-DF
    # branch; the mock _read_sql_df above is used directly via the job path.
    # We instead use a simpler strategy: patch the whole oracle fallback block
    # by making _should_use_duckdb return True and patching the DuckDB queries.
    return []  # populated below in _patch_for_raw_path


def _patch_for_raw_path(base_df: pd.DataFrame, job_df: pd.DataFrame):
    """Context-manager that stubs query_downtime_dataset_raw dependencies.

    Strategy: use the DuckDB fast path (not Oracle BQE) to avoid patching
    execute_plan/merge_chunks_to_spool internals.  We make should_use_duckdb
    return True and supply the synthetic DataFrames via _qbase/_qjob.
    The spool store writes are no-ops (to avoid FS activity).
    _apply_resource_filters is a pass-through.
    """
    from unittest.mock import patch as _patch

    class _MultiPatch:
        """Composite context manager for several patches."""

        def __enter__(self):
            # 1. Both spool slots absent → triggers full data acquisition
            self._p_base_hit = _patch(
                "mes_dashboard.services.downtime_analysis_cache.has_downtime_base_events",
                return_value=False,
            )
            self._p_job_hit = _patch(
                "mes_dashboard.services.downtime_analysis_cache.has_downtime_job_bridge",
                return_value=False,
            )
            # 2. DuckDB prewarm available → use fast path with synthetic DFs
            self._p_should = _patch(
                "mes_dashboard.services.downtime_analysis_duckdb_cache.should_use_duckdb",
                return_value=True,
            )
            self._p_qbase = _patch(
                "mes_dashboard.services.downtime_analysis_duckdb_cache.query_base_from_duckdb",
                return_value=base_df,
            )
            self._p_qjob = _patch(
                "mes_dashboard.services.downtime_analysis_duckdb_cache.query_job_from_duckdb",
                return_value=job_df,
            )
            # 3. Spool store writes are no-ops (no FS I/O)
            self._p_store_base = _patch(
                "mes_dashboard.services.downtime_analysis_cache.store_downtime_base_events",
            )
            self._p_store_job = _patch(
                "mes_dashboard.services.downtime_analysis_cache.store_downtime_job_bridge",
            )
            # 4. Resource filter cache — return all rows unfiltered
            self._p_filter = _patch(
                "mes_dashboard.services.downtime_analysis_service._apply_resource_filters",
                side_effect=lambda df, *a, **kw: df,
            )

            self._p_base_hit.start()
            self._p_job_hit.start()
            self._p_should.start()
            self._p_qbase.start()
            self._p_qjob.start()
            self._p_store_base.start()
            self._p_store_job.start()
            self._p_filter.start()
            return self

        def __exit__(self, *exc):
            self._p_base_hit.stop()
            self._p_job_hit.stop()
            self._p_should.stop()
            self._p_qbase.stop()
            self._p_qjob.stop()
            self._p_store_base.stop()
            self._p_store_job.stop()
            self._p_filter.stop()

    return _MultiPatch()


def _call_raw(base_df: pd.DataFrame, job_df: pd.DataFrame) -> Dict[str, Any]:
    """Call query_downtime_dataset_raw with fully mocked dependencies.

    Returns the dict {base_spool_url, jobs_spool_url, query_id, taxonomy}.
    Raises on any exception so callers can detect failures.
    """
    from mes_dashboard.services.downtime_analysis_service import query_downtime_dataset_raw

    with _patch_for_raw_path(base_df, job_df):
        result = query_downtime_dataset_raw(
            start_date="2025-12-01",
            end_date="2026-05-30",  # ~180-day range
        )
    return result


# ---------------------------------------------------------------------------
# Shared synthetic DataFrames (module-level, built once per test session)
# ---------------------------------------------------------------------------

_LARGE_BASE_DF: Optional[pd.DataFrame] = None
_LARGE_JOB_DF: Optional[pd.DataFrame] = None


def _get_large_dfs() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (base_df, job_df) built once per process.  Thread-safe because
    both DataFrames are immutable after construction and the GIL is held during
    the simple attribute reads.  Each caller receives a view, not a copy; the
    service under test does its own copy internally if needed.
    """
    global _LARGE_BASE_DF, _LARGE_JOB_DF
    if _LARGE_BASE_DF is None:
        _LARGE_BASE_DF = _make_base_events_df(n_rows=100_000)
        _LARGE_JOB_DF = _make_job_bridge_df(n_rows=5_000)
    return _LARGE_BASE_DF, _LARGE_JOB_DF


# ---------------------------------------------------------------------------
# Memory measurement helpers
# ---------------------------------------------------------------------------

def _rss_bytes() -> int:
    """Current RSS of this process in bytes."""
    return psutil.Process(os.getpid()).memory_info().rss


def _gc_collect() -> None:
    """Run two GC cycles to reduce noise from pending destructions."""
    gc.collect()
    gc.collect()


# ---------------------------------------------------------------------------
# @pytest.mark.stress — memory thresholds per request
# ---------------------------------------------------------------------------

@pytest.mark.stress
class TestDowntimeRawSpoolMemory:
    """In-process RSS tests for the raw-parquet server path.

    These tests call query_downtime_dataset_raw() directly (same call stack as
    a gunicorn worker handling the request) and measure RSS growth.  They do
    not start gunicorn — in-process measurement captures the same pandas
    allocation profile.

    Threshold rationale
    -------------------
    Old path peak:
      _merge_cross_shift_events on 100k rows does df.copy() (~40 MB) plus
      sort/cumsum/groupby temporaries (~80-100 MB) = ~120-160 MB working set
      on top of the input frame.  A 184k-row real dataset reached ~240 MB.

    New path peak:
      Server writes raw parquets without running any reduction.  The DuckDB
      fast path returns a DataFrame reference; the service applies a simple
      isin() filter and calls store_downtime_*() (mocked to no-op here).
      Expected working memory: ~10-40 MB for the filter mask on 100k rows.

    Conservative thresholds (with 2× safety headroom):
      Single query RSS delta < 150 MB  (vs old ~240+ MB)
      Three concurrent queries RSS delta < 400 MB  (vs old ~720+ MB)
    """

    def test_single_large_query_rss_delta(self, monkeypatch):
        """Single 180-day query: RSS growth must stay below 150 MB.

        Covers AC-7 (stress) + design.md §Open Risks (OOM elimination goal).
        """
        # Enable the browser-DuckDB path (module-level constant; must use setattr)
        monkeypatch.setattr(
            "mes_dashboard.services.downtime_analysis_service._BROWSER_DUCKDB_ENABLED",
            True,
        )

        base_df, job_df = _get_large_dfs()

        _gc_collect()
        rss_before = _rss_bytes()

        result = _call_raw(base_df, job_df)

        _gc_collect()
        rss_after = _rss_bytes()

        delta_bytes = rss_after - rss_before
        delta_mb = delta_bytes / 1_048_576

        print(
            f"\n[single-query RSS] before={rss_before/1_048_576:.1f} MB  "
            f"after={rss_after/1_048_576:.1f} MB  "
            f"delta={delta_mb:+.1f} MB"
        )

        # Verify the function returned the expected raw-path shape (not old shape)
        assert "base_spool_url" in result, "Expected raw-path response key base_spool_url"
        assert "jobs_spool_url" in result, "Expected raw-path response key jobs_spool_url"
        assert "taxonomy" in result, "Expected raw-path response key taxonomy"

        # Core OOM-elimination threshold
        assert delta_bytes < 150_000_000, (
            f"Single large query RSS delta {delta_mb:.1f} MB exceeded 150 MB threshold. "
            f"This indicates _merge_cross_shift_events or another high-copy reduction "
            f"is being called on the raw path — check AC-2 / design.md §Service row."
        )

    def test_concurrent_three_queries_no_oom(self, monkeypatch):
        """Three concurrent 180-day queries: all succeed; total RSS delta < 400 MB.

        Models three gunicorn workers handling concurrent wide-range requests
        simultaneously — the scenario that caused OOM kills on the 6 GB host.
        """
        monkeypatch.setattr(
            "mes_dashboard.services.downtime_analysis_service._BROWSER_DUCKDB_ENABLED",
            True,
        )

        base_df, job_df = _get_large_dfs()
        n_concurrent = 3
        errors: List[str] = []
        results: List[Dict[str, Any]] = []

        _gc_collect()
        rss_before = _rss_bytes()

        def _worker(_idx: int) -> Dict[str, Any]:
            return _call_raw(base_df, job_df)

        with concurrent.futures.ThreadPoolExecutor(max_workers=n_concurrent) as pool:
            futures = [pool.submit(_worker, i) for i in range(n_concurrent)]
            for fut in concurrent.futures.as_completed(futures):
                exc = fut.exception()
                if exc is not None:
                    errors.append(str(exc)[:200])
                else:
                    results.append(fut.result())

        _gc_collect()
        rss_after = _rss_bytes()

        delta_bytes = rss_after - rss_before
        delta_mb = delta_bytes / 1_048_576

        print(
            f"\n[concurrent-3 RSS] before={rss_before/1_048_576:.1f} MB  "
            f"after={rss_after/1_048_576:.1f} MB  "
            f"delta={delta_mb:+.1f} MB  "
            f"successes={len(results)}  errors={len(errors)}"
        )

        assert not errors, (
            f"One or more concurrent raw queries raised: {errors}"
        )
        assert len(results) == n_concurrent, (
            f"Expected {n_concurrent} successful results, got {len(results)}"
        )

        # All must have raw-path response shape
        for i, r in enumerate(results):
            assert "base_spool_url" in r, f"Result[{i}] missing base_spool_url"
            assert "jobs_spool_url" in r, f"Result[{i}] missing jobs_spool_url"

        # OOM-elimination threshold for concurrent scenario
        assert delta_bytes < 400_000_000, (
            f"Three concurrent queries RSS delta {delta_mb:.1f} MB exceeded 400 MB. "
            f"At this rate, 6 GB/no-swap hosts risk OOM on concurrent wide-range requests."
        )

    def test_raw_path_does_not_call_merge(self, monkeypatch):
        """Regression guard: _merge_cross_shift_events must NOT be invoked on raw path.

        This is the central behavioral contract of the migration.  The old path
        called merge on every request; the new path relocates it to the browser.
        A regression (re-adding a merge call server-side) would re-introduce the
        OOM risk and break AC-2.

        Note: we patch _merge_cross_shift_events (the old server-side reduction).
        _merge_cross_shift_events_from_parquet is a separate function used only
        in the deprecated flag-off fallback path; patching it here is not needed.
        """
        monkeypatch.setattr(
            "mes_dashboard.services.downtime_analysis_service._BROWSER_DUCKDB_ENABLED",
            True,
        )

        base_df, job_df = _get_large_dfs()
        merge_mock = MagicMock(name="_merge_cross_shift_events")

        with patch(
            "mes_dashboard.services.downtime_analysis_service._merge_cross_shift_events",
            merge_mock,
        ):
            _call_raw(base_df, job_df)

        assert merge_mock.call_count == 0, (
            f"_merge_cross_shift_events was called {merge_mock.call_count} time(s) "
            f"on the raw path — this is a regression; the reduction must not execute "
            f"server-side when DOWNTIME_BROWSER_DUCKDB=true (AC-2, design.md §Service)."
        )

    def test_raw_path_response_has_four_required_keys(self, monkeypatch):
        """Smoke: raw path response always contains all four contract keys.

        Verifies the shape defined in design.md §API Response Contract.
        Complements the route-level TestQueryRoute tests in test_downtime_analysis_routes.py.
        """
        monkeypatch.setattr(
            "mes_dashboard.services.downtime_analysis_service._BROWSER_DUCKDB_ENABLED",
            True,
        )

        base_df, job_df = _get_large_dfs()
        result = _call_raw(base_df, job_df)

        for key in ("base_spool_url", "jobs_spool_url", "query_id", "taxonomy"):
            assert key in result and result[key] is not None, (
                f"Raw-path response missing or null key: {key!r} "
                f"(design.md §API Response Contract)"
            )

    def test_concurrent_wide_range_queries_no_oom_kill(self, monkeypatch):
        """AC-7 stress: concurrent wide-range queries under 6 GB/no-swap profile.

        Named to match the test-plan.md AC-7 mapping.  Runs 5 concurrent queries
        (wider than the 3-worker default) to stress the memory profile more
        aggressively.  All must return without exception and total RSS delta
        must remain below 600 MB (5× the single-query 150 MB headroom, minus
        the GC-reclaim allowance of ~150 MB).
        """
        monkeypatch.setattr(
            "mes_dashboard.services.downtime_analysis_service._BROWSER_DUCKDB_ENABLED",
            True,
        )

        base_df, job_df = _get_large_dfs()
        n_concurrent = 5
        errors: List[str] = []
        results: List[Dict[str, Any]] = []

        _gc_collect()
        rss_before = _rss_bytes()

        def _worker(_idx: int) -> Dict[str, Any]:
            return _call_raw(base_df, job_df)

        with concurrent.futures.ThreadPoolExecutor(max_workers=n_concurrent) as pool:
            futures = [pool.submit(_worker, i) for i in range(n_concurrent)]
            for fut in concurrent.futures.as_completed(futures):
                exc = fut.exception()
                if exc is not None:
                    errors.append(str(exc)[:200])
                else:
                    results.append(fut.result())

        _gc_collect()
        rss_after = _rss_bytes()

        delta_bytes = rss_after - rss_before
        delta_mb = delta_bytes / 1_048_576

        print(
            f"\n[concurrent-5 RSS] before={rss_before/1_048_576:.1f} MB  "
            f"after={rss_after/1_048_576:.1f} MB  "
            f"delta={delta_mb:+.1f} MB  "
            f"successes={len(results)}  errors={len(errors)}"
        )

        assert not errors, (
            f"Concurrent wide-range queries raised: {errors}"
        )
        assert len(results) == n_concurrent, (
            f"Expected {n_concurrent} results, got {len(results)}"
        )

        assert delta_bytes < 600_000_000, (
            f"Five concurrent queries RSS delta {delta_mb:.1f} MB exceeded 600 MB. "
            f"OOM kill risk on 6 GB/no-swap host — investigate pandas allocation on the raw path."
        )


# ---------------------------------------------------------------------------
# @pytest.mark.soak — repeated queries, memory stability over 50 iterations
# ---------------------------------------------------------------------------

@pytest.mark.soak
class TestDowntimeSoakMemoryStability:
    """Memory leak / temp-file growth checks over 50 sequential raw queries.

    ci-gates.md names this gate 'soak-memory-stable' (Tier 4, weekly).

    Threshold rationale
    -------------------
    50 queries × zero server-side pandas reduction should produce near-zero
    net RSS growth once Python's allocator has warmed its pool (typically
    after the first 2-5 calls).  We allow 50 MB total growth as headroom for:
    - Python allocator pool expansion (permanent but bounded)
    - Log handler buffers
    - pytest + psutil measurement overhead

    A genuine leak (e.g., a list accumulating DataFrames, or a spool directory
    growing without TTL reclaim) would produce monotonically increasing RSS
    and breach 50 MB well before 50 iterations.

    The spool store writes are mocked to no-ops, so temp-file growth is not
    measured here; it is covered by the integration-level spool-TTL tests.
    """

    def test_fifty_repeated_queries_memory_stable(self, monkeypatch):
        """RSS must not grow by more than 50 MB across 50 sequential raw queries.

        'Sequential' models a single gunicorn worker handling requests one at a
        time — if there is a per-request leak it will compound and breach the
        threshold well within 50 iterations.
        """
        monkeypatch.setattr(
            "mes_dashboard.services.downtime_analysis_service._BROWSER_DUCKDB_ENABLED",
            True,
        )

        base_df, job_df = _get_large_dfs()

        # Warm up Python's allocator (2 pre-run calls excluded from measurement)
        for _ in range(2):
            _call_raw(base_df, job_df)

        _gc_collect()
        rss_initial = _rss_bytes()

        for i in range(50):
            result = _call_raw(base_df, job_df)
            # Verify each iteration returns valid shape (not silently failing)
            assert "base_spool_url" in result, (
                f"Iteration {i}: raw-path response missing base_spool_url"
            )

        _gc_collect()
        rss_final = _rss_bytes()

        growth_bytes = rss_final - rss_initial
        growth_mb = growth_bytes / 1_048_576

        print(
            f"\n[50-iter soak] initial={rss_initial/1_048_576:.1f} MB  "
            f"final={rss_final/1_048_576:.1f} MB  "
            f"growth={growth_mb:+.1f} MB"
        )

        assert growth_bytes < 50_000_000, (
            f"RSS grew by {growth_mb:.1f} MB across 50 sequential raw queries "
            f"(threshold: 50 MB). This indicates a per-request memory leak — "
            f"check for list/dict accumulation in query_downtime_dataset_raw() "
            f"or its callees, or for in-process spool objects not being released."
        )

    def test_rss_samples_show_no_monotonic_growth_trend(self, monkeypatch):
        """The per-query RSS sample sequence must not be monotonically increasing.

        A purely monotonic growth pattern (RSS[i+1] > RSS[i] for every i) is
        a strong signal of a genuine unbounded leak, even if the total stays
        below 50 MB.  This test fails only if every single sample grows —
        normal allocator behaviour produces non-monotonic series.
        """
        monkeypatch.setattr(
            "mes_dashboard.services.downtime_analysis_service._BROWSER_DUCKDB_ENABLED",
            True,
        )

        base_df, job_df = _get_large_dfs()

        # Warm up
        for _ in range(2):
            _call_raw(base_df, job_df)

        _gc_collect()

        samples: List[int] = []
        for _ in range(20):
            _call_raw(base_df, job_df)
            _gc_collect()
            samples.append(_rss_bytes())

        # Check that the series is NOT strictly monotonically increasing
        strictly_increasing = all(
            samples[i + 1] > samples[i] for i in range(len(samples) - 1)
        )

        rss_mb = [s / 1_048_576 for s in samples]
        print(
            f"\n[monotonic-growth check] RSS samples (MB): "
            + "  ".join(f"{v:.1f}" for v in rss_mb)
        )

        assert not strictly_increasing, (
            "RSS was strictly monotonically increasing across all 20 samples — "
            "this is a strong indicator of an unbounded memory leak in the raw path. "
            f"Samples (MB): {[f'{v:.1f}' for v in rss_mb]}"
        )
