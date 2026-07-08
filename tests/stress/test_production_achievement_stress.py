# -*- coding: utf-8 -*-
"""Stress tests for production-achievement-async-spool: ProductionAchievementJob
(BaseChunkedDuckDBJob unified path) contending on the SHARED heavy_query_slot
semaphore + the SHARED query_spool_store with sibling worker types.

Companion to tests/stress/test_base_job_semaphore_stress.py (generic unified-job
wiring) and tests/stress/test_async_job_stress.py (async-lifecycle probes). This
suite is production-achievement-specific: it exercises the REAL
ProductionAchievementJob class (not a generic stub) so the chunk-seam-safe
post_aggregate / canonical-spool-key machinery genuinely runs under concurrency,
and it specifically targets the classification's blast-radius risk -- a new
worker contending on the SAME global semaphore + spool store used by five
existing sibling domains (eap_alarm/downtime/material_trace/production_history/
reject_history/resource_history).

Marked @pytest.mark.stress -- excluded from Tier-1 pre-merge gate. Weekly/manual
schedule per ci-gates.md (`stress-load` row), same tier as test_rq_semaphore_stress.py
and test_base_job_semaphore_stress.py.

No live server, Oracle, or Redis required -- Oracle fan-out is replaced with a
no-op (`_fan_out_append`), and Redis-dependent calls (`register_spool_file`,
`update_job_progress`, `complete_job`) fail open/no-op gracefully when Redis is
unavailable (same design as the rest of the unified-job stress suite). All
DuckDB/filesystem I/O is real (tmp_path spool dir) -- only the Oracle network
call and the Redis round-trip are avoided.

AC / risk coverage:
  R-1 (semaphore wiring, no leak)      -> TestSemaphoreWiringStress
  R-2 (no deadlock under mixed fault)  -> TestMixedFaultNoDeadlock
  R-3 (no starvation of sibling types) -> TestCrossWorkerFairness
  R-4 (fail-open when Redis down)      -> TestFailOpenNoRedis
  R-5 (spool key collision safety)     -> TestSpoolKeyCollision
  R-6 (live-server async queue saturation, deferred) -> TestProductionAchievementQueueSaturationLive
"""

from __future__ import annotations

import concurrent.futures
import os
import threading
import time
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Tuple

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from mes_dashboard.core.base_chunked_duckdb_job import BaseChunkedDuckDBJob, ChunkStrategy

pytestmark = pytest.mark.stress


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _write_chunk_parquet(chunk_dir: Path, name: str, rows: list[dict]) -> None:
    """Write a fake per-chunk parquet using the raw Oracle-cursor column names
    (SHIFT_CODE, OUTPUT_DATE, SPECNAME, ACTUAL_OUTPUT_QTY) that
    OracleArrowReader/production_achievement.sql would actually produce."""
    table = pa.table({
        "OUTPUT_DATE": pa.array([r["OUTPUT_DATE"] for r in rows], type=pa.date32()),
        "SHIFT_CODE": pa.array([r["SHIFT_CODE"] for r in rows], type=pa.string()),
        "SPECNAME": pa.array([r["SPECNAME"] for r in rows], type=pa.string()),
        "ACTUAL_OUTPUT_QTY": pa.array([r["ACTUAL_OUTPUT_QTY"] for r in rows], type=pa.int64()),
    })
    pq.write_table(table, str(chunk_dir / name))


def _recording_cm_factory(events: List[Tuple[float, str, str]], lock: threading.Lock):
    """Return a contextmanager factory recording entry/exit and a real sleep.

    Mirrors tests/stress/test_base_job_semaphore_stress.py -- this verifies
    WIRING (the CM is entered/exited exactly once per job.run() call), not the
    live Redis Lua-CAS cap (Redis absent in CI; see docs/architecture/
    base-job-semaphore-wiring-stress-soak-report.md "Note on peak_concurrent").
    """

    @contextmanager
    def _slot(owner: str):
        with lock:
            events.append((time.monotonic(), "enter", owner))
        try:
            time.sleep(0.02)  # simulate Oracle I/O so windows genuinely overlap
            yield True
        finally:
            with lock:
                events.append((time.monotonic(), "exit", owner))

    return _slot


def _compute_peak_concurrent(events: List[Tuple[float, str, str]]) -> int:
    sorted_events = sorted(events, key=lambda e: e[0])
    current = 0
    peak = 0
    for _ts, kind, _owner in sorted_events:
        if kind == "enter":
            current += 1
            peak = max(peak, current)
        else:
            current -= 1
    return peak


def _patch_spool_dirs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Point QUERY_SPOOL_DIR / DUCKDB_JOB_DIR at tmp_path for this test.

    QUERY_SPOOL_DIR is read via a *local* import inside
    ProductionAchievementJob.pre_query()/post_aggregate() (re-evaluated on each
    call), so patching the module attribute takes effect immediately --
    os.environ patching would NOT (module-level constant frozen at import,
    per CLAUDE.md "Module-level constants" convention). DUCKDB_JOB_DIR is read
    via os.environ.get(...) at call time in BaseChunkedDuckDBJob, so setenv
    works for it.
    """
    import mes_dashboard.core.query_spool_store as spool_store_mod

    monkeypatch.setattr(spool_store_mod, "QUERY_SPOOL_DIR", tmp_path / "spool")
    monkeypatch.setenv("DUCKDB_JOB_DIR", str(tmp_path / "duckdb_jobs"))


def _make_pa_job(job_id: str, start_date: str, end_date: str):
    from mes_dashboard.workers.production_achievement_worker import ProductionAchievementJob
    return ProductionAchievementJob(
        job_id=job_id, params={"start_date": start_date, "end_date": end_date}
    )


def _date_range_for_index(i: int) -> Tuple[str, str]:
    """Distinct 1-day date range per index -- distinct canonical spool keys."""
    base = date(2024, 1, 1) + timedelta(days=i)
    return base.strftime("%Y-%m-%d"), base.strftime("%Y-%m-%d")


class _SiblingStressJob(BaseChunkedDuckDBJob):
    """Generic BaseChunkedDuckDBJob stand-in for ANY of the five other sibling
    domains sharing heavy_query_slot (eap_alarm/downtime/material_trace/
    production_history/reject_history/resource_history). All six subclasses
    execute the IDENTICAL run() slot-wiring code path (base_chunked_duckdb_job.py
    is domain-agnostic) -- exercising one stub validates the shared mechanism
    that every sibling relies on, mirroring _StressJob in
    test_base_job_semaphore_stress.py."""

    namespace = "sibling_stress_ns"
    chunk_strategy = ChunkStrategy.SINGLE
    requires_cross_chunk_reduction = False

    def pre_query(self) -> None:
        self._chunks = [{"i": 0}]

    def build_chunk_sql(self, chunk_params):  # pragma: no cover - fan-out mocked
        return ("SELECT 1 FROM dual", {})

    def post_aggregate(self, job_duckdb_path):
        return f"/tmp/{self.namespace}/{self.job_id}.parquet"


# ---------------------------------------------------------------------------
# R-1: Semaphore wiring -- burst N=20 real ProductionAchievementJob instances
# ---------------------------------------------------------------------------


@pytest.mark.stress
class TestSemaphoreWiringStress:
    """N=20 burst of the REAL ProductionAchievementJob: every job.run() enters/
    exits the shared heavy_query_slot exactly once; no leak; no deadlock."""

    _N = 20

    def test_burst_peak_bounded_no_leak(self, monkeypatch, tmp_path):
        import mes_dashboard.core.base_chunked_duckdb_job as base_mod

        _patch_spool_dirs(monkeypatch, tmp_path)

        events: List[Tuple[float, str, str]] = []
        lock = threading.Lock()
        monkeypatch.setattr(base_mod, "heavy_query_slot", _recording_cm_factory(events, lock))

        completed: List[str] = []
        errors: List[Tuple[str, str]] = []
        result_lock = threading.Lock()

        def _run_job(idx: int):
            job_id = f"pa-stress-{idx:03d}"
            start_date, end_date = _date_range_for_index(idx)
            try:
                job = _make_pa_job(job_id, start_date, end_date)
                job._fan_out_append = lambda chunks: None
                job.run()
                with result_lock:
                    completed.append(job_id)
            except Exception as exc:
                with result_lock:
                    errors.append((job_id, str(exc)))

        threads = [threading.Thread(target=_run_job, args=(i,)) for i in range(self._N)]
        t_start = time.monotonic()
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60.0)
        elapsed = time.monotonic() - t_start

        assert len(errors) == 0, f"Jobs faulted: {errors}"
        assert len(completed) == self._N, (
            f"Expected {self._N} completions; got {len(completed)} in {elapsed:.2f}s"
        )

        enters = [e for e in events if e[1] == "enter"]
        exits = [e for e in events if e[1] == "exit"]
        assert len(enters) == self._N, f"Expected {self._N} slot enters; got {len(enters)}"
        assert len(enters) == len(exits), f"Slot leak: {len(enters)} enters vs {len(exits)} exits"

        peak = _compute_peak_concurrent(events)
        assert peak <= self._N, f"Peak {peak} exceeds total jobs {self._N}"
        print(
            f"\n[pa-stress] N={self._N} peak_concurrent={peak} elapsed={elapsed:.2f}s "
            f"enters={len(enters)} exits={len(exits)}"
        )


# ---------------------------------------------------------------------------
# R-2: Mixed success/failure -- no deadlock, slot always released
# ---------------------------------------------------------------------------


@pytest.mark.stress
class TestMixedFaultNoDeadlock:
    """N=20 real PA jobs, every 5th faults in the Oracle fan-out mock: no
    deadlock; every slot released even when _fan_out_append raises."""

    _N = 20

    def test_burst_no_deadlock_with_mixed_success_failure(self, monkeypatch, tmp_path):
        import mes_dashboard.core.base_chunked_duckdb_job as base_mod

        _patch_spool_dirs(monkeypatch, tmp_path)

        events: List[Tuple[float, str, str]] = []
        lock = threading.Lock()
        monkeypatch.setattr(base_mod, "heavy_query_slot", _recording_cm_factory(events, lock))

        completed: List[str] = []
        faults: List[str] = []
        result_lock = threading.Lock()

        def _run_job(idx: int, should_fault: bool):
            job_id = f"pa-mixfault-{idx:03d}"
            start_date, end_date = _date_range_for_index(idx)
            job = _make_pa_job(job_id, start_date, end_date)
            if should_fault:
                def _boom(chunks):
                    raise RuntimeError("oracle stress fault")
                job._fan_out_append = _boom
            else:
                job._fan_out_append = lambda chunks: None
            try:
                job.run()
                with result_lock:
                    completed.append(job_id)
            except RuntimeError:
                with result_lock:
                    faults.append(job_id)
            except Exception as exc:
                with result_lock:
                    faults.append(f"{job_id}:{exc}")

        threads = [
            threading.Thread(target=_run_job, args=(i, i % 5 == 0)) for i in range(self._N)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60.0)

        enters = [e for e in events if e[1] == "enter"]
        exits = [e for e in events if e[1] == "exit"]

        total = len(completed) + len(faults)
        assert total == self._N, f"Not all jobs finished: {total}/{self._N}"
        assert len(faults) == 4, f"Expected 4 injected faults (every 5th); got {len(faults)}"
        assert len(enters) == len(exits), (
            f"Slot leak after mixed failure: {len(enters)} enters vs {len(exits)} exits"
        )
        print(
            f"\n[pa-stress-mixed] N={self._N} completed={len(completed)} faulted={len(faults)} "
            f"enters={len(enters)} exits={len(exits)}"
        )


# ---------------------------------------------------------------------------
# R-3: Cross-worker contention -- does PA starve sibling job types?
# ---------------------------------------------------------------------------


@pytest.mark.stress
class TestCrossWorkerFairness:
    """Mix N PA jobs with M sibling-domain stub jobs sharing ONE recording CM.

    heavy_query_slot's `with heavy_query_slot(owner):` block never binds/
    branches on the yielded `acquired` bool (base_chunked_duckdb_job.py run()),
    so the Oracle fan-out proceeds regardless of slot outcome -- there is no
    blocking/queueing at this layer, and therefore no lock-based starvation is
    structurally possible here. This test verifies that empirically: PA jobs do
    not systematically monopolize completion order or measurably delay sibling
    completion when both types race for the shared CM concurrently.
    """

    _N_PA = 10
    _N_SIBLING = 10

    def test_pa_and_sibling_jobs_interleave_no_monopolization(self, monkeypatch, tmp_path):
        import mes_dashboard.core.base_chunked_duckdb_job as base_mod

        _patch_spool_dirs(monkeypatch, tmp_path)

        events: List[Tuple[float, str, str]] = []
        lock = threading.Lock()
        monkeypatch.setattr(base_mod, "heavy_query_slot", _recording_cm_factory(events, lock))

        completed: List[str] = []
        errors: List[str] = []
        result_lock = threading.Lock()

        def _run_pa(idx: int):
            job_id = f"pa-fair-{idx:03d}"
            start_date, end_date = _date_range_for_index(idx)
            try:
                job = _make_pa_job(job_id, start_date, end_date)
                job._fan_out_append = lambda chunks: None
                job.run()
                with result_lock:
                    completed.append("pa")
            except Exception as exc:
                with result_lock:
                    errors.append(f"pa-{idx}: {exc}")

        def _run_sibling(idx: int):
            job_id = f"sibling-fair-{idx:03d}"
            try:
                job = _SiblingStressJob(job_id)
                job._fan_out_append = lambda chunks: None
                job._cleanup_chunk_parquet_dir = lambda jid: None
                job.progress_report = lambda pct: None
                job.run()
                with result_lock:
                    completed.append("sibling")
            except Exception as exc:
                with result_lock:
                    errors.append(f"sibling-{idx}: {exc}")

        # Interleave thread CREATION order (pa, sibling, pa, sibling, ...) so
        # the starvation signal isn't confounded by "all PA threads happened
        # to be started first" -- Python's GIL tends to schedule threads
        # roughly in start order for short-lived work.
        threads: List[threading.Thread] = []
        for i in range(max(self._N_PA, self._N_SIBLING)):
            if i < self._N_PA:
                threads.append(threading.Thread(target=_run_pa, args=(i,)))
            if i < self._N_SIBLING:
                threads.append(threading.Thread(target=_run_sibling, args=(i,)))

        t_start = time.monotonic()
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60.0)
        elapsed = time.monotonic() - t_start

        assert not errors, f"Jobs faulted under cross-worker contention: {errors}"
        total = self._N_PA + self._N_SIBLING
        assert len(completed) == total, (
            f"Expected {total} completions; got {len(completed)} in {elapsed:.2f}s "
            "(possible starvation/hang)"
        )

        enters = [e for e in events if e[1] == "enter"]
        exits = [e for e in events if e[1] == "exit"]
        assert len(enters) == total, f"Expected {total} slot enters; got {len(enters)}"
        assert len(enters) == len(exits), f"Slot leak: {len(enters)} enters vs {len(exits)} exits"

        # No-monopolization check on SLOT ENTRY order (not completion order).
        # Entry timestamps are recorded the instant each thread reaches
        # `with heavy_query_slot(owner):`, BEFORE any domain-specific
        # post-slot work runs -- this isolates "did the shared CM itself
        # introduce an ordering bias between domains" from "PA's real
        # post_aggregate (DuckDB parquet write) simply takes longer per-job
        # than the trivial sibling stub's post_aggregate (a one-line return,
        # no I/O)". The latter is an expected, benign workload-duration
        # difference -- not semaphore starvation -- and is exactly why this
        # check must NOT be based on completion order (an earlier version of
        # this test asserted on completion order and produced a false
        # positive: all 10 zero-I/O sibling stubs completed before any of the
        # 10 real-I/O PA jobs, purely because of that duration difference,
        # not because the CM favoured either type).
        owner_type = lambda owner: "pa" if owner.startswith("production_achievement:") else "sibling"
        entries_sorted = sorted(enters, key=lambda e: e[0])
        first_half_entries = entries_sorted[: total // 2]
        first_half_types = {owner_type(e[2]) for e in first_half_entries}
        assert first_half_types == {"pa", "sibling"}, (
            f"One job type was entirely excluded from the first half of slot "
            f"ENTRIES (possible acquisition-order bias in the shared CM): "
            f"first_half_types={first_half_types}, "
            f"full entry order={[owner_type(e[2]) for e in entries_sorted]}"
        )
        print(
            f"\n[pa-fairness] N_pa={self._N_PA} N_sibling={self._N_SIBLING} elapsed={elapsed:.2f}s "
            f"first_half_entry_types={first_half_types} "
            f"completion_type_counts={{'pa': {completed.count('pa')}, 'sibling': {completed.count('sibling')}}}"
        )


# ---------------------------------------------------------------------------
# R-4: Fail-open when Redis is down
# ---------------------------------------------------------------------------


@pytest.mark.stress
class TestFailOpenNoRedis:
    """global_concurrency fails open (acquired=True, no block) when Redis is
    unavailable -- ProductionAchievementJob.run() must still complete quickly."""

    def test_acquire_heavy_query_slot_fails_open_when_redis_down(self, monkeypatch):
        """Direct unit check of the REAL global_concurrency module (no worker
        involved) -- Redis down -> acquire returns True immediately."""
        import mes_dashboard.core.global_concurrency as gc_mod

        monkeypatch.setattr(gc_mod, "get_redis_client", lambda: None)

        start = time.monotonic()
        acquired = gc_mod.acquire_heavy_query_slot("stress-test:production_achievement:redis-down")
        elapsed = time.monotonic() - start

        assert acquired is True, "acquire_heavy_query_slot must fail OPEN (return True) when Redis is down"
        assert elapsed < 1.0, f"fail-open acquire took {elapsed:.3f}s -- should be near-instant, no retry/backoff"

        # release_heavy_query_slot must also no-op cleanly (no exception) when Redis is down.
        gc_mod.release_heavy_query_slot("stress-test:production_achievement:redis-down")

    def test_job_run_completes_when_redis_down(self, monkeypatch, tmp_path):
        """End-to-end: run() -- which internally calls heavy_query_slot() from
        global_concurrency, unmocked -- completes without hanging when Redis is
        unavailable. Only get_redis_client is patched; the rest of the unified-
        job pipeline (pre_query/_fan_out_append(mocked)/post_aggregate/
        progress_report/register_spool_file) runs for real."""
        import mes_dashboard.core.global_concurrency as gc_mod

        _patch_spool_dirs(monkeypatch, tmp_path)
        monkeypatch.setattr(gc_mod, "get_redis_client", lambda: None)

        job = _make_pa_job("pa-redis-down-001", "2024-05-01", "2024-05-01")
        job._fan_out_append = lambda chunks: None

        start = time.monotonic()
        spool_path = job.run()
        elapsed = time.monotonic() - start

        assert spool_path, "run() must return a non-empty spool path"
        assert Path(spool_path).exists(), f"spool parquet not written: {spool_path}"
        assert elapsed < 10.0, (
            f"job.run() took {elapsed:.2f}s with Redis down -- fail-open should not "
            "introduce any material delay"
        )

        con = duckdb.connect()
        try:
            cols = [
                r[0] for r in con.execute(
                    f"DESCRIBE SELECT * FROM read_parquet('{spool_path}')"
                ).fetchall()
            ]
        finally:
            con.close()
        assert set(cols) == {"output_date", "shift_code", "SPECNAME", "actual_output_qty"}


# ---------------------------------------------------------------------------
# R-5: Spool-key collision safety under concurrent identical/near-identical
# date ranges (canonical-key dedup)
# ---------------------------------------------------------------------------


@pytest.mark.stress
class TestSpoolKeyCollision:
    """async_query_job_service.enqueue_query_job has no inflight dedup by
    canonical query_id (confirmed by reading enqueue_query_job/
    enqueue_job_dynamic) -- N simultaneous browser requests for the IDENTICAL
    date range that all miss the spool before the first job completes will
    each independently enqueue a full RQ job. Every one of those N jobs
    computes the SAME make_canonical_pa_spool_id() key and -- exactly like the
    reference resource_history_base_worker.py post_aggregate -- writes its
    DuckDB `COPY ... TO` output DIRECTLY to the canonical spool path (no
    job-scoped staging file + atomic rename). This test proves whether N
    concurrent writers targeting the identical destination path corrupt or
    truncate the final parquet."""

    def test_identical_date_range_concurrent_jobs_no_spool_corruption(
        self, monkeypatch, tmp_path
    ):
        """N=5 threads barrier-synchronized to call ``post_aggregate()`` for
        the IDENTICAL canonical key at the same instant -- the tightest
        possible reproduction of a thundering-herd of identical requests.

        FINDING (reproduced deterministically via the barrier -- see
        stress-soak-report.md Finding 1): DuckDB's
        ``COPY ... TO '<path>' (FORMAT PARQUET, ...)`` writes to a temp file
        with a DETERMINISTIC name derived from the final path
        (``tmp_<final-name>``) in the same directory, then atomically
        renames it into place. Because every concurrent writer here targets
        the IDENTICAL final path, they also collide on the IDENTICAL temp
        filename: the first writer to finish renames ``tmp_X.parquet`` ->
        ``X.parquet``; every OTHER writer's subsequent rename of its (now
        vanished, because it was the same name) ``tmp_X.parquet`` then
        raises ``IO Error: ... No such file or directory``. This race is
        inherited from the same write-directly-to-the-canonical-path
        pattern already used by resource_history_base_worker.py's
        post_aggregate (not newly introduced by this worker) -- see
        stress-soak-report.md Finding 1 for severity/remediation options.

        This test does NOT assert zero errors -- that would misrepresent
        the reproducible behaviour discovered here. It asserts the
        SAFE-DEGRADATION invariants that actually matter operationally: no
        hang, every raised error is the SPECIFIC known rename-race class
        (loud and catchable, not a silent/unrelated crash), at least one
        writer succeeds, and whichever writer "wins" the rename leaves
        behind a FULLY VALID, readable parquet with the correct schema --
        never a silently truncated/corrupted shared spool file that other
        concurrent readers could be downloading mid-write.
        """
        _patch_spool_dirs(monkeypatch, tmp_path)

        N = 5
        start_date, end_date = "2024-06-01", "2024-06-02"
        barrier = threading.Barrier(N, timeout=10.0)

        errors: List[str] = []
        successes: List[str] = []
        lock = threading.Lock()

        def _run_one(idx: int):
            job = _make_pa_job(f"pa-collide-{idx:03d}", start_date, end_date)
            job.pre_query()
            chunk_dir = job._make_chunk_parquet_dir(job.job_id)
            _write_chunk_parquet(chunk_dir, "chunk-0000-0000.parquet", [
                {
                    "OUTPUT_DATE": date(2024, 6, 1),
                    "SHIFT_CODE": "D",
                    "SPECNAME": f"SPEC-{idx}",
                    "ACTUAL_OUTPUT_QTY": 10 + idx,
                },
            ])
            barrier.wait()  # force maximal simultaneity on the COPY...TO race
            try:
                path = job.post_aggregate(None)
                with lock:
                    successes.append(path)
            except Exception as exc:
                with lock:
                    errors.append(f"{idx}: {type(exc).__name__}: {exc}")

        threads = [threading.Thread(target=_run_one, args=(i,)) for i in range(N)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30.0)

        total = len(successes) + len(errors)
        assert total == N, (
            f"Not all {N} writers reached a terminal state (possible hang): "
            f"{len(successes)} succeeded, {len(errors)} errored, {N - total} unaccounted"
        )

        # Safe-degradation invariant 1: at least one writer must succeed --
        # a burst of identical requests must not leave the spool permanently
        # unwritten.
        assert successes, (
            f"ALL {N} concurrent identical-key writers failed -- the spool was "
            f"never written: {errors}"
        )

        # Safe-degradation invariant 2: every error must be the SPECIFIC
        # known IO/rename race (loud, catchable, RQ sees it as a failed
        # job) -- never a silent corruption or an unrelated crash class.
        unexpected_errors = [
            e for e in errors if "IO Error" not in e and "rename" not in e.lower()
        ]
        assert not unexpected_errors, (
            f"Unexpected (non-rename-race) errors under concurrent identical-key "
            f"writers: {unexpected_errors}"
        )

        # Safe-degradation invariant 3: the file left standing is a VALID,
        # readable parquet with the correct schema -- never truncated/garbage.
        final_path = successes[0]
        assert os.path.exists(final_path), f"final spool file missing: {final_path}"
        con = duckdb.connect()
        try:
            cols = [
                r[0] for r in con.execute(
                    f"DESCRIBE SELECT * FROM read_parquet('{final_path}')"
                ).fetchall()
            ]
            row_count = con.execute(
                f"SELECT COUNT(*) FROM read_parquet('{final_path}')"
            ).fetchone()[0]
        finally:
            con.close()

        assert set(cols) == {"output_date", "shift_code", "SPECNAME", "actual_output_qty"}, (
            f"Final spool file has corrupted/unexpected schema after concurrent writers: {cols}"
        )
        assert row_count >= 0
        print(
            f"\n[pa-collision] N={N} identical-key writers (barrier-synchronized) -> "
            f"{len(successes)} succeeded, {len(errors)} raised the known rename-race "
            f"IOError, final file valid (row_count={row_count}). "
            "See stress-soak-report.md Finding 1 for remediation options."
        )

    def test_distinct_date_range_concurrent_jobs_stay_isolated(self, monkeypatch, tmp_path):
        """Companion check: DISTINCT date ranges must resolve to DISTINCT
        canonical keys and never cross-contaminate each other's spool file."""
        _patch_spool_dirs(monkeypatch, tmp_path)

        N = 5
        errors: List[str] = []
        results: Dict[int, str] = {}
        lock = threading.Lock()

        def _run_one(idx: int):
            start_date, end_date = _date_range_for_index(idx)
            job = _make_pa_job(f"pa-isolated-{idx:03d}", start_date, end_date)
            job.pre_query()
            chunk_dir = job._make_chunk_parquet_dir(job.job_id)
            _write_chunk_parquet(chunk_dir, "chunk-0000-0000.parquet", [
                {
                    "OUTPUT_DATE": date(2024, 1, 1) + timedelta(days=idx),
                    "SHIFT_CODE": "D",
                    "SPECNAME": f"SPEC-{idx}",
                    "ACTUAL_OUTPUT_QTY": 100 + idx,
                },
            ])
            try:
                path = job.post_aggregate(None)
                with lock:
                    results[idx] = path
            except Exception as exc:
                with lock:
                    errors.append(f"{idx}: {exc}")

        threads = [threading.Thread(target=_run_one, args=(i,)) for i in range(N)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30.0)

        assert not errors, f"post_aggregate raised under distinct-key concurrency: {errors}"
        assert len(results) == N
        assert len(set(results.values())) == N, (
            f"Distinct date ranges must resolve to DISTINCT canonical spool paths; "
            f"got {len(set(results.values()))} unique paths for {N} jobs: {results}"
        )

        for idx, path in results.items():
            con = duckdb.connect()
            try:
                rows = con.execute(
                    f"SELECT SPECNAME, actual_output_qty FROM read_parquet('{path}')"
                ).fetchall()
            finally:
                con.close()
            assert rows == [(f"SPEC-{idx}", 100 + idx)], (
                f"Spool file for job {idx} contains unexpected/cross-contaminated rows: {rows}"
            )


# ---------------------------------------------------------------------------
# R-6: Live-server async queue saturation (mirrors test_async_job_stress.py)
#
# NOT executed in this sandbox -- no live server / Oracle / Redis available.
# Included so the weekly/manual stress-tests.yml dispatch (which DOES target
# a running instance via STRESS_TEST_URL) exercises the HTTP-level 200/202/
# 503 async contract under real concurrency, complementing the mock-level
# classes above. Gracefully skips ("Server unreachable") exactly like its
# siblings TestProductionHistoryQueueSaturation / TestYieldAlertQueueSaturation
# in test_async_job_stress.py -- see that file for the shared AsyncJobPoller
# helper and the "not silently dropped" assertion convention.
# ---------------------------------------------------------------------------

from async_helpers import AsyncJobPoller, AsyncJobResult, AsyncJobTimeout  # noqa: E402


def _pa_report_params() -> Dict[str, str]:
    end = date.today()
    start = end - timedelta(days=7)
    return {"start_date": start.strftime("%Y-%m-%d"), "end_date": end.strftime("%Y-%m-%d")}


@pytest.mark.stress
class TestProductionAchievementQueueSaturationLive:
    """5 concurrent identical-date-range /api/production-achievement/report
    requests against a REAL deployed instance. Verifies the AC-1/AC-2/AC-8
    async contract (200 spool-hit / 202 enqueue / 503 no-worker) holds under
    concurrency and that no request is silently dropped (connection error)
    while contending on the shared heavy_query_slot + spool store alongside
    whatever other domains are also live on that instance."""

    def _submit_one(self, base_url: str) -> AsyncJobResult:
        poller = AsyncJobPoller(base_url, max_wait=300, poll_interval=2.0)
        try:
            return poller.submit_and_wait(
                "GET", "/api/production-achievement/report", params=_pa_report_params()
            )
        except AsyncJobTimeout as exc:
            return AsyncJobResult(
                job_id=exc.job_id, status="timeout", elapsed=exc.elapsed, poll_count=0,
                error=str(exc),
            )

    def test_production_achievement_5_concurrent(self, base_url: str):
        """5 concurrent identical-date-range PA report requests must all
        reach a terminal state; none silently dropped (connection error).

        A 401 (no auth session in the stress harness) or 503 (no worker /
        Redis unavailable) is a legitimate terminal HTTP response, not a
        "drop" -- only a connection-level failure (``http_status is None``)
        counts as dropped, matching the sibling probes' convention.
        """
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(self._submit_one, base_url) for _ in range(5)]
            results: List[AsyncJobResult] = [
                f.result() for f in concurrent.futures.as_completed(futures)
            ]

        if all(r.status == "error" and r.http_status is None for r in results):
            pytest.skip("Server unreachable")

        dropped = [r for r in results if r.status == "error" and r.http_status is None]
        timeouts = [r for r in results if r.status == "timeout"]

        assert not dropped, (
            f"{len(dropped)}/5 production-achievement jobs were silently dropped "
            "(connection error)"
        )
        assert not timeouts, f"{len(timeouts)}/5 production-achievement jobs timed out"

        completed = [r for r in results if r.status in ("completed", "sync_hit")]
        print(f"\n  PA statuses: {[r.status for r in results]}")
        print(f"  Completed: {len(completed)}/5")
