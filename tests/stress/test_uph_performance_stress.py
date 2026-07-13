# -*- coding: utf-8 -*-
"""Stress tests for add-uph-performance-page: UphPerformanceJob
(BaseChunkedDuckDBJob unified path) contending on the SHARED heavy_query_slot
semaphore + the SHARED query_spool_store with sibling worker types.

Companion to tests/stress/test_base_job_semaphore_stress.py (generic unified-job
wiring) and tests/stress/test_production_achievement_stress.py (the template
this suite mirrors class-for-class). This suite is uph-performance-specific: it
exercises the REAL UphPerformanceJob class (not a generic stub) so the
family-conditional-JOIN-aware pre_query / post_aggregate machinery genuinely
runs under concurrency, and it specifically targets the classification's/
design.md's blast-radius risk -- a new worker becoming the 4TH consumer of the
SAME global `heavy_query_slot` semaphore (MAX_CONCURRENT=3) already shared by
eap_alarm/downtime/material_trace/production_history/reject_history/
resource_history/production_achievement.

Marked @pytest.mark.stress -- excluded from Tier-1 pre-merge gate. Weekly/manual
schedule per ci-gates.md (`stress-load` row), same tier as
test_rq_semaphore_stress.py, test_base_job_semaphore_stress.py, and
test_production_achievement_stress.py.

No live server, Oracle, or Redis required -- Oracle fan-out is replaced with a
no-op (`_fan_out_append`), and Redis-dependent calls (`register_spool_file`,
`update_job_progress`, `complete_job`) fail open/no-op gracefully when Redis is
unavailable (same design as the rest of the unified-job stress suite). All
DuckDB/filesystem I/O is real (tmp_path spool dir) -- only the Oracle network
call and the Redis round-trip are avoided. Per this session's security
boundary, NO test in this module performs a real/sustained Oracle load run --
see specs/changes/add-uph-performance-page/stress-soak-report.md for the
residual real-Oracle-load gap this leaves (pre-existing, cross-cutting, not
something this change can close).

AC / risk coverage:
  R-0 (structural: no second heavy_query_slot acquisition) -> TestNoSecondSlotAcquisition
  R-1 (semaphore wiring, no leak)      -> TestSemaphoreWiringStress
  R-2 (no deadlock under mixed fault)  -> TestMixedFaultNoDeadlock
  R-3 (no starvation of sibling types) -> TestCrossWorkerFairness
  R-4 (fail-open when Redis down)      -> TestFailOpenNoRedis
  R-5 (spool key collision safety)     -> TestSpoolKeyCollision
  R-6 (live-server async queue saturation, deferred) -> TestUphPerformanceQueueSaturationLive
"""

from __future__ import annotations

import ast
import concurrent.futures
import inspect
import os
import threading
import time
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Tuple

import duckdb
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from mes_dashboard.core.base_chunked_duckdb_job import BaseChunkedDuckDBJob, ChunkStrategy

pytestmark = pytest.mark.stress


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

# Raw chunk parquet columns produced by sql/uph_performance.sql (pre-enrichment,
# events_raw table) -- see uph_performance_worker.py's empty-frame fallback list.
_CHUNK_COLUMNS = [
    "LOT_ID", "EQUIPMENT_ID", "EQUIPMENT_FAMILY", "EVENT_TIME",
    "PARAMETER_NAME", "UPH_VALUE_RAW",
]

# Final post_aggregate parquet columns (data-shape-contract.md §3.29 schema_version 1).
_SPOOL_COLUMNS = {
    "LOT_ID", "EQUIPMENT_ID", "EQUIPMENT_FAMILY", "EVENT_TIME", "PARAMETER_NAME",
    "UPH_VALUE", "WORKCENTERNAME", "DB_WB_LABEL", "PACKAGE", "PJ_TYPE",
    "PJ_BOP", "PJ_FUNCTION", "coarse_filter_hash",
}


def _write_chunk_parquet(chunk_dir: Path, name: str, rows: list[dict]) -> None:
    """Write a fake per-chunk parquet using the raw Oracle-cursor column names
    (LOT_ID, EQUIPMENT_ID, EQUIPMENT_FAMILY, EVENT_TIME, PARAMETER_NAME,
    UPH_VALUE_RAW) that OracleArrowReader/sql/uph_performance.sql would
    actually produce for one <=6h chunk window."""
    table = pa.table({
        "LOT_ID": pa.array([r["LOT_ID"] for r in rows], type=pa.string()),
        "EQUIPMENT_ID": pa.array([r["EQUIPMENT_ID"] for r in rows], type=pa.string()),
        "EQUIPMENT_FAMILY": pa.array([r["EQUIPMENT_FAMILY"] for r in rows], type=pa.string()),
        "EVENT_TIME": pa.array([r["EVENT_TIME"] for r in rows], type=pa.timestamp("us")),
        "PARAMETER_NAME": pa.array([r["PARAMETER_NAME"] for r in rows], type=pa.string()),
        "UPH_VALUE_RAW": pa.array([r["UPH_VALUE_RAW"] for r in rows], type=pa.float64()),
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
    UphPerformanceJob.post_aggregate() / uph_performance_cache.get_uph_
    performance_spool_path() (re-evaluated on each call), so patching the
    module attribute takes effect immediately -- os.environ patching would
    NOT (module-level constant frozen at import, per CLAUDE.md "Module-level
    constants" convention). DUCKDB_JOB_DIR is read via os.environ.get(...) at
    call time in BaseChunkedDuckDBJob, so setenv works for it.
    """
    import mes_dashboard.core.query_spool_store as spool_store_mod

    monkeypatch.setattr(spool_store_mod, "QUERY_SPOOL_DIR", tmp_path / "spool")
    monkeypatch.setenv("DUCKDB_JOB_DIR", str(tmp_path / "duckdb_jobs"))


def _stub_dim_bridges(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neutralize the two Oracle enrichment bridges (LOT_ID->DW_MES_CONTAINER,
    EQUIPMENT_ID->DW_MES_RESOURCE) so post_aggregate never issues a real Oracle
    round-trip in this mock-based stress suite -- these bridges only fire when
    events_df is non-empty (see _safe_lot_product_df/_safe_workcenter_df),
    which happens in the R-5 spool-collision tests below (real chunk rows are
    written there to force a genuine COPY...TO race)."""
    import mes_dashboard.workers.uph_performance_worker as uph_mod

    monkeypatch.setattr(
        uph_mod, "_safe_lot_product_df",
        lambda events_df, timeout_seconds: pd.DataFrame(columns=uph_mod._LOT_PRODUCT_COLUMNS),
    )
    monkeypatch.setattr(
        uph_mod, "_safe_workcenter_df",
        lambda events_df, timeout_seconds: pd.DataFrame(
            columns=uph_mod._RESOURCE_WORKCENTER_COLUMNS + ["DB_WB_LABEL"]
        ),
    )


def _make_uph_job(job_id: str, date_from: str, date_to: str):
    from mes_dashboard.workers.uph_performance_worker import UphPerformanceJob
    return UphPerformanceJob(
        job_id=job_id, params={"date_from": date_from, "date_to": date_to}
    )


def _date_range_for_index(i: int) -> Tuple[str, str]:
    """Distinct 1-day date range per index -- distinct canonical spool keys."""
    base = date(2024, 1, 1) + timedelta(days=i)
    return base.strftime("%Y-%m-%d"), base.strftime("%Y-%m-%d")


class _SiblingStressJob(BaseChunkedDuckDBJob):
    """Generic BaseChunkedDuckDBJob stand-in for ANY of the OTHER SIX sibling
    domains sharing heavy_query_slot (eap_alarm/downtime/material_trace/
    production_history/reject_history/resource_history/production_achievement).
    All seven subclasses execute the IDENTICAL run() slot-wiring code path
    (base_chunked_duckdb_job.py is domain-agnostic) -- exercising one stub
    validates the shared mechanism that every sibling (now including
    uph_performance as the 4th-in-practice heavy consumer per design.md Open
    Risks) relies on, mirroring _SiblingStressJob in
    test_production_achievement_stress.py."""

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
# R-0: Structural -- worker must NEVER re-acquire heavy_query_slot itself
# (design.md Open Risks explicitly forbids a second acquisition; the slot is
# already bracketed once by BaseChunkedDuckDBJob.run()).
# ---------------------------------------------------------------------------


class TestNoSecondSlotAcquisition:
    """Structural proof (not behavioral) that uph_performance_worker.py never
    calls acquire_heavy_query_slot/release_heavy_query_slot/heavy_query_slot
    itself -- per CLAUDE.md's "Use ast.parse() + walk ast.Call to prove
    absence of removed startup calls" promoted learning, applied here to
    prove absence of an ADDED second-acquisition call site instead."""

    def test_worker_source_never_calls_heavy_query_slot_directly(self):
        import mes_dashboard.workers.uph_performance_worker as uph_mod

        src = inspect.getsource(uph_mod)
        tree = ast.parse(src)

        forbidden_names = {"acquire_heavy_query_slot", "release_heavy_query_slot", "heavy_query_slot"}
        found: List[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                name = None
                if isinstance(func, ast.Name):
                    name = func.id
                elif isinstance(func, ast.Attribute):
                    name = func.attr
                if name in forbidden_names:
                    found.append(name)

        assert not found, (
            f"uph_performance_worker.py calls {found} directly -- the heavy-query "
            "slot must be acquired EXACTLY ONCE, inside BaseChunkedDuckDBJob.run(); "
            "a second acquisition here would double-count this job against "
            "HEAVY_QUERY_MAX_CONCURRENT (design.md Open Risks)."
        )

    def test_semaphore_wiring_module_is_not_imported_for_manual_use(self):
        """Companion sanity check: global_concurrency IS imported (transitively,
        via BaseChunkedDuckDBJob), but uph_performance_worker.py's own top-level
        import list does not import it directly -- reinforces that the module
        has no code path capable of a manual second acquisition."""
        import mes_dashboard.workers.uph_performance_worker as uph_mod

        src = inspect.getsource(uph_mod)
        tree = ast.parse(src)
        direct_imports: List[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "mes_dashboard.core.global_concurrency":
                direct_imports.extend(alias.name for alias in node.names)
            if isinstance(node, ast.Import):
                direct_imports.extend(
                    alias.name for alias in node.names
                    if alias.name == "mes_dashboard.core.global_concurrency"
                )

        assert not direct_imports, (
            f"uph_performance_worker.py directly imports global_concurrency "
            f"symbols {direct_imports} at module scope -- this module should "
            "rely entirely on the inherited BaseChunkedDuckDBJob.run() bracket."
        )


# ---------------------------------------------------------------------------
# R-1: Semaphore wiring -- burst N=20 real UphPerformanceJob instances
# ---------------------------------------------------------------------------


@pytest.mark.stress
class TestSemaphoreWiringStress:
    """N=20 burst of the REAL UphPerformanceJob: every job.run() enters/exits
    the shared heavy_query_slot exactly once; no leak; no deadlock."""

    _N = 20

    def test_burst_peak_bounded_no_leak(self, monkeypatch, tmp_path):
        import mes_dashboard.core.base_chunked_duckdb_job as base_mod

        _patch_spool_dirs(monkeypatch, tmp_path)
        _stub_dim_bridges(monkeypatch)

        events: List[Tuple[float, str, str]] = []
        lock = threading.Lock()
        monkeypatch.setattr(base_mod, "heavy_query_slot", _recording_cm_factory(events, lock))

        completed: List[str] = []
        errors: List[Tuple[str, str]] = []
        result_lock = threading.Lock()

        def _run_job(idx: int):
            job_id = f"uph-stress-{idx:03d}"
            date_from, date_to = _date_range_for_index(idx)
            try:
                job = _make_uph_job(job_id, date_from, date_to)
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
        assert len(enters) == self._N, (
            f"Expected {self._N} slot enters (exactly ONE per job.run() call); "
            f"got {len(enters)}. A count of {2 * self._N} would indicate the "
            "worker is re-acquiring the slot a second time (see "
            "TestNoSecondSlotAcquisition for the structural companion check)."
        )
        assert len(enters) == len(exits), f"Slot leak: {len(enters)} enters vs {len(exits)} exits"

        peak = _compute_peak_concurrent(events)
        assert peak <= self._N, f"Peak {peak} exceeds total jobs {self._N}"
        print(
            f"\n[uph-stress] N={self._N} peak_concurrent={peak} elapsed={elapsed:.2f}s "
            f"enters={len(enters)} exits={len(exits)}"
        )


# ---------------------------------------------------------------------------
# R-2: Mixed success/failure -- no deadlock, slot always released
# ---------------------------------------------------------------------------


@pytest.mark.stress
class TestMixedFaultNoDeadlock:
    """N=20 real UPH jobs, every 5th faults in the Oracle fan-out mock: no
    deadlock; every slot released even when _fan_out_append raises."""

    _N = 20

    def test_burst_no_deadlock_with_mixed_success_failure(self, monkeypatch, tmp_path):
        import mes_dashboard.core.base_chunked_duckdb_job as base_mod

        _patch_spool_dirs(monkeypatch, tmp_path)
        _stub_dim_bridges(monkeypatch)

        events: List[Tuple[float, str, str]] = []
        lock = threading.Lock()
        monkeypatch.setattr(base_mod, "heavy_query_slot", _recording_cm_factory(events, lock))

        completed: List[str] = []
        faults: List[str] = []
        result_lock = threading.Lock()

        def _run_job(idx: int, should_fault: bool):
            job_id = f"uph-mixfault-{idx:03d}"
            date_from, date_to = _date_range_for_index(idx)
            job = _make_uph_job(job_id, date_from, date_to)
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
            f"\n[uph-stress-mixed] N={self._N} completed={len(completed)} faulted={len(faults)} "
            f"enters={len(enters)} exits={len(exits)}"
        )


# ---------------------------------------------------------------------------
# R-3: Cross-worker contention -- does UPH-Performance starve/get-starved by
# sibling job types on the shared semaphore? (the 4th-consumer risk itself)
# ---------------------------------------------------------------------------


@pytest.mark.stress
class TestCrossWorkerFairness:
    """Mix N UPH jobs with M sibling-domain stub jobs sharing ONE recording CM.

    heavy_query_slot's `with heavy_query_slot(owner):` block never binds/
    branches on the yielded `acquired` bool (base_chunked_duckdb_job.py run()),
    so the Oracle fan-out proceeds regardless of slot outcome -- there is no
    blocking/queueing at this layer, and therefore no lock-based starvation is
    structurally possible here. This test verifies that empirically: UPH jobs
    do not systematically monopolize completion order or measurably delay
    sibling completion when both types race for the shared CM concurrently --
    the concrete, mock-level proxy for design.md's "4th heavy consumer"
    contention risk (real-Oracle-scale contention is NOT reproducible here;
    see stress-soak-report.md residual risk).
    """

    _N_UPH = 10
    _N_SIBLING = 10

    def test_uph_and_sibling_jobs_interleave_no_monopolization(self, monkeypatch, tmp_path):
        import mes_dashboard.core.base_chunked_duckdb_job as base_mod

        _patch_spool_dirs(monkeypatch, tmp_path)
        _stub_dim_bridges(monkeypatch)

        events: List[Tuple[float, str, str]] = []
        lock = threading.Lock()
        monkeypatch.setattr(base_mod, "heavy_query_slot", _recording_cm_factory(events, lock))

        completed: List[str] = []
        errors: List[str] = []
        result_lock = threading.Lock()

        def _run_uph(idx: int):
            job_id = f"uph-fair-{idx:03d}"
            date_from, date_to = _date_range_for_index(idx)
            try:
                job = _make_uph_job(job_id, date_from, date_to)
                job._fan_out_append = lambda chunks: None
                job.run()
                with result_lock:
                    completed.append("uph")
            except Exception as exc:
                with result_lock:
                    errors.append(f"uph-{idx}: {exc}")

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

        # Interleave thread CREATION order (uph, sibling, uph, sibling, ...) so
        # the starvation signal isn't confounded by "all UPH threads happened
        # to be started first" -- Python's GIL tends to schedule threads
        # roughly in start order for short-lived work.
        threads: List[threading.Thread] = []
        for i in range(max(self._N_UPH, self._N_SIBLING)):
            if i < self._N_UPH:
                threads.append(threading.Thread(target=_run_uph, args=(i,)))
            if i < self._N_SIBLING:
                threads.append(threading.Thread(target=_run_sibling, args=(i,)))

        t_start = time.monotonic()
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60.0)
        elapsed = time.monotonic() - t_start

        assert not errors, f"Jobs faulted under cross-worker contention: {errors}"
        total = self._N_UPH + self._N_SIBLING
        assert len(completed) == total, (
            f"Expected {total} completions; got {len(completed)} in {elapsed:.2f}s "
            "(possible starvation/hang)"
        )

        enters = [e for e in events if e[1] == "enter"]
        exits = [e for e in events if e[1] == "exit"]
        assert len(enters) == total, f"Expected {total} slot enters; got {len(enters)}"
        assert len(enters) == len(exits), f"Slot leak: {len(enters)} enters vs {len(exits)} exits"

        # No-monopolization check on SLOT ENTRY order (not completion order) --
        # see test_production_achievement_stress.py's TestCrossWorkerFairness
        # for why completion order is the wrong signal (real-I/O post_aggregate
        # vs trivial stub post_aggregate durations differ for reasons unrelated
        # to the semaphore itself).
        owner_type = lambda owner: "uph" if owner.startswith("uph_performance:") else "sibling"
        entries_sorted = sorted(enters, key=lambda e: e[0])
        first_half_entries = entries_sorted[: total // 2]
        first_half_types = {owner_type(e[2]) for e in first_half_entries}
        assert first_half_types == {"uph", "sibling"}, (
            f"One job type was entirely excluded from the first half of slot "
            f"ENTRIES (possible acquisition-order bias in the shared CM): "
            f"first_half_types={first_half_types}, "
            f"full entry order={[owner_type(e[2]) for e in entries_sorted]}"
        )
        print(
            f"\n[uph-fairness] N_uph={self._N_UPH} N_sibling={self._N_SIBLING} elapsed={elapsed:.2f}s "
            f"first_half_entry_types={first_half_types} "
            f"completion_type_counts={{'uph': {completed.count('uph')}, 'sibling': {completed.count('sibling')}}}"
        )


# ---------------------------------------------------------------------------
# R-4: Fail-open when Redis is down
# ---------------------------------------------------------------------------


@pytest.mark.stress
class TestFailOpenNoRedis:
    """global_concurrency fails open (acquired=True, no block) when Redis is
    unavailable -- UphPerformanceJob.run() must still complete quickly."""

    def test_acquire_heavy_query_slot_fails_open_when_redis_down(self, monkeypatch):
        """Direct unit check of the REAL global_concurrency module (no worker
        involved) -- Redis down -> acquire returns True immediately."""
        import mes_dashboard.core.global_concurrency as gc_mod

        monkeypatch.setattr(gc_mod, "get_redis_client", lambda: None)

        start = time.monotonic()
        acquired = gc_mod.acquire_heavy_query_slot("stress-test:uph_performance:redis-down")
        elapsed = time.monotonic() - start

        assert acquired is True, "acquire_heavy_query_slot must fail OPEN (return True) when Redis is down"
        assert elapsed < 1.0, f"fail-open acquire took {elapsed:.3f}s -- should be near-instant, no retry/backoff"

        # release_heavy_query_slot must also no-op cleanly (no exception) when Redis is down.
        gc_mod.release_heavy_query_slot("stress-test:uph_performance:redis-down")

    def test_job_run_completes_when_redis_down(self, monkeypatch, tmp_path):
        """End-to-end: run() -- which internally calls heavy_query_slot() from
        global_concurrency, unmocked -- completes without hanging when Redis is
        unavailable. Only get_redis_client is patched; the rest of the unified-
        job pipeline (pre_query/_fan_out_append(mocked)/post_aggregate/
        progress_report/register_spool_file) runs for real."""
        import mes_dashboard.core.global_concurrency as gc_mod

        _patch_spool_dirs(monkeypatch, tmp_path)
        _stub_dim_bridges(monkeypatch)
        monkeypatch.setattr(gc_mod, "get_redis_client", lambda: None)

        job = _make_uph_job("uph-redis-down-001", "2024-05-01", "2024-05-01")
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
            cols = {
                r[0] for r in con.execute(
                    f"DESCRIBE SELECT * FROM read_parquet('{spool_path}')"
                ).fetchall()
            }
        finally:
            con.close()
        assert cols == _SPOOL_COLUMNS, f"Unexpected empty-chunk parquet schema: {cols}"


# ---------------------------------------------------------------------------
# R-5: Spool-key collision safety under concurrent identical/near-identical
# date ranges (canonical-key dedup)
# ---------------------------------------------------------------------------


@pytest.mark.stress
class TestSpoolKeyCollision:
    """async_query_job_service.enqueue_query_job has no inflight dedup by
    canonical query_id (confirmed by reading enqueue_query_job/
    enqueue_job_dynamic) -- N simultaneous browser requests for the IDENTICAL
    (date_from, date_to [, coarse filters]) that all miss the spool before the
    first job completes will each independently enqueue a full RQ job. Every
    one of those N jobs computes the SAME make_uph_performance_spool_key() key
    and -- exactly like production_achievement_worker.py's post_aggregate --
    writes its DuckDB `COPY ... TO` output DIRECTLY to the spool-key path (no
    job-scoped staging file + atomic rename before register_spool_file() moves
    it). This test proves whether N concurrent writers targeting the identical
    destination path corrupt or truncate the final parquet."""

    def test_identical_date_range_concurrent_jobs_no_spool_corruption(
        self, monkeypatch, tmp_path
    ):
        """N=5 threads barrier-synchronized to call ``post_aggregate()`` for
        the IDENTICAL canonical key at the same instant -- the tightest
        possible reproduction of a thundering-herd of identical requests.

        Real chunk rows (non-empty events_df) are written here specifically so
        the two enrichment-bridge functions actually execute their DataFrame
        code path -- but they are monkeypatched to short-circuit (no Oracle
        round-trip; `_stub_dim_bridges`), so this remains a mock-based stress
        check, not a live-Oracle one.

        Mirrors the SAME reproducible finding documented in
        test_production_achievement_stress.py's equivalent test (DuckDB's
        ``COPY ... TO`` uses a deterministic ``tmp_<final-name>`` staging file
        in the same directory; concurrent identical-path writers race on that
        staging name, so every writer but the winner sees a loud IO/rename
        error, never silent corruption) -- this is pre-existing
        infrastructure shared by every BaseChunkedDuckDBJob subclass with
        requires_cross_chunk_reduction=False, not newly introduced by this
        worker. See stress-soak-report.md Finding 1 (carried forward, not
        re-investigated here).

        This test does NOT assert zero errors -- it asserts the
        SAFE-DEGRADATION invariants: no hang, every raised error is the
        SPECIFIC known rename-race class, at least one writer succeeds, and
        the surviving parquet is fully valid with the correct schema.
        """
        _patch_spool_dirs(monkeypatch, tmp_path)
        _stub_dim_bridges(monkeypatch)

        N = 5
        date_from, date_to = "2024-06-01", "2024-06-01"
        barrier = threading.Barrier(N, timeout=10.0)

        errors: List[str] = []
        successes: List[str] = []
        lock = threading.Lock()

        def _run_one(idx: int):
            job = _make_uph_job(f"uph-collide-{idx:03d}", date_from, date_to)
            job.pre_query()
            chunk_dir = job._make_chunk_parquet_dir(job.job_id)
            _write_chunk_parquet(chunk_dir, "chunk-0000-0000.parquet", [
                {
                    "LOT_ID": f"LOT{idx:04d}",
                    "EQUIPMENT_ID": "GDBA01",
                    "EQUIPMENT_FAMILY": "GDBA",
                    "EVENT_TIME": pd.Timestamp("2024-06-01 08:00:00"),
                    "PARAMETER_NAME": "BondUPH",
                    "UPH_VALUE_RAW": 100.0 + idx,
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

        assert successes, (
            f"ALL {N} concurrent identical-key writers failed -- the spool was "
            f"never written: {errors}"
        )

        unexpected_errors = [
            e for e in errors if "IO Error" not in e and "rename" not in e.lower()
        ]
        assert not unexpected_errors, (
            f"Unexpected (non-rename-race) errors under concurrent identical-key "
            f"writers: {unexpected_errors}"
        )

        final_path = successes[0]
        assert os.path.exists(final_path), f"final spool file missing: {final_path}"
        con = duckdb.connect()
        try:
            cols = {
                r[0] for r in con.execute(
                    f"DESCRIBE SELECT * FROM read_parquet('{final_path}')"
                ).fetchall()
            }
            row_count = con.execute(
                f"SELECT COUNT(*) FROM read_parquet('{final_path}')"
            ).fetchone()[0]
        finally:
            con.close()

        assert cols == _SPOOL_COLUMNS, (
            f"Final spool file has corrupted/unexpected schema after concurrent writers: {cols}"
        )
        assert row_count >= 0
        print(
            f"\n[uph-collision] N={N} identical-key writers (barrier-synchronized) -> "
            f"{len(successes)} succeeded, {len(errors)} raised the known rename-race "
            f"IOError, final file valid (row_count={row_count}). "
            "See stress-soak-report.md Finding 1 (carried forward from "
            "production-achievement-async-spool) for remediation options."
        )

    def test_distinct_date_range_concurrent_jobs_stay_isolated(self, monkeypatch, tmp_path):
        """Companion check: DISTINCT date ranges must resolve to DISTINCT
        canonical spool keys and never cross-contaminate each other's spool file."""
        _patch_spool_dirs(monkeypatch, tmp_path)
        _stub_dim_bridges(monkeypatch)

        N = 5
        errors: List[str] = []
        results: Dict[int, str] = {}
        lock = threading.Lock()

        def _run_one(idx: int):
            date_from, date_to = _date_range_for_index(idx)
            job = _make_uph_job(f"uph-isolated-{idx:03d}", date_from, date_to)
            job.pre_query()
            chunk_dir = job._make_chunk_parquet_dir(job.job_id)
            _write_chunk_parquet(chunk_dir, "chunk-0000-0000.parquet", [
                {
                    "LOT_ID": f"LOT{idx:04d}",
                    "EQUIPMENT_ID": "GWBA02",
                    "EQUIPMENT_FAMILY": "GWBA",
                    "EVENT_TIME": pd.Timestamp(date_from) + pd.Timedelta(hours=1),
                    "PARAMETER_NAME": "fHCM_UPH",
                    "UPH_VALUE_RAW": 200.0 + idx,
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
                    f"SELECT LOT_ID, UPH_VALUE FROM read_parquet('{path}')"
                ).fetchall()
            finally:
                con.close()
            assert rows == [(f"LOT{idx:04d}", 200.0 + idx)], (
                f"Spool file for job {idx} contains unexpected/cross-contaminated rows: {rows}"
            )


# ---------------------------------------------------------------------------
# R-6: Live-server async queue saturation (mirrors test_production_achievement
# _stress.py's TestProductionAchievementQueueSaturationLive)
#
# NOT executed in this sandbox -- no live server / Oracle / Redis available,
# and per this session's security boundary this stress-soak pass performs NO
# real/sustained Oracle load run. Included so the weekly/manual stress-tests.yml
# dispatch (which DOES target a running instance via STRESS_TEST_URL) exercises
# the HTTP-level 200/202/503 async contract under real concurrency,
# complementing the mock-level classes above. Gracefully skips
# ("Server unreachable") exactly like its siblings in test_async_job_stress.py
# and test_production_achievement_stress.py.
# ---------------------------------------------------------------------------

from async_helpers import AsyncJobPoller, AsyncJobResult, AsyncJobTimeout  # noqa: E402


def _uph_spool_payload() -> Dict[str, str]:
    end = date.today()
    start = end - timedelta(days=1)  # keep the window small (<=6h chunking, UPH-01)
    return {"date_from": start.strftime("%Y-%m-%d"), "date_to": end.strftime("%Y-%m-%d")}


@pytest.mark.stress
class TestUphPerformanceQueueSaturationLive:
    """5 concurrent identical-date-range POST /api/uph-performance/spool
    requests against a REAL deployed instance. Verifies the AC-5/UPH-ASYNC
    async contract (200 spool-hit / 202 enqueue / 503 no-worker) holds under
    concurrency and that no request is silently dropped (connection error)
    while contending on the shared heavy_query_slot + spool store alongside
    whatever other domains are also live on that instance.

    Deliberately NOT run as part of this change's mock-based stress pass (no
    live server/Oracle/Redis available in this environment, and sustained
    Oracle load requires explicit user authorization) -- see
    stress-soak-report.md for the residual gap this leaves.
    """

    def _submit_one(self, base_url: str) -> AsyncJobResult:
        poller = AsyncJobPoller(base_url, max_wait=300, poll_interval=2.0)
        try:
            return poller.submit_and_wait(
                "POST", "/api/uph-performance/spool", payload=_uph_spool_payload()
            )
        except AsyncJobTimeout as exc:
            return AsyncJobResult(
                job_id=exc.job_id, status="timeout", elapsed=exc.elapsed, poll_count=0,
                error=str(exc),
            )

    def test_uph_performance_5_concurrent(self, base_url: str):
        """5 concurrent identical-date-range UPH spool requests must all
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
            f"{len(dropped)}/5 uph-performance jobs were silently dropped "
            "(connection error)"
        )
        assert not timeouts, f"{len(timeouts)}/5 uph-performance jobs timed out"

        completed = [r for r in results if r.status in ("completed", "sync_hit")]
        print(f"\n  UPH statuses: {[r.status for r in results]}")
        print(f"  Completed: {len(completed)}/5")
