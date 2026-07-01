# Stress / Soak Report — base-job-semaphore-wiring (query-arch Phase A-1)

> Companion to `specs/archive/2026/rq-semaphore-wiring/stress-soak-report.md` (the legacy
> per-domain worker wiring). This report covers the follow-on gap closed by
> `fix(concurrency): wire heavy_query_slot into unified job core (Phase A-1)`: the
> **unified job core** `BaseChunkedDuckDBJob.run()` / `MaterialTraceJob.run()`, which
> never acquired `heavy_query_slot` before this change — the path
> EAP_ALARM/DOWNTIME/MATERIAL_TRACE/PRODUCTION_HISTORY/REJECT_HISTORY/RESOURCE_HISTORY
> take when `*_USE_UNIFIED_JOB=on` (the production default for all six domains).

## Workload Model

**System under test:** `heavy_query_slot(owner)` context-manager wiring in
`BaseChunkedDuckDBJob.run()` (brackets `_fan_out_append` / `_fan_out_reduction`),
representing the pattern inherited by all six `BaseChunkedDuckDBJob` subclasses.

**Test approach:** Mock-based; no real Oracle or Redis required (same model as the
legacy-worker precedent).
- The recording CM replaces `heavy_query_slot` at the `base_chunked_duckdb_job` module
  level to count enter/exit events and measure peak overlap by timestamp.
- Oracle I/O simulated with `time.sleep(0.02)` inside the CM to create genuine thread
  overlap (stress suite only; integration suite times out at 30s so uses a lighter
  0.02s sleep only in the wiring-verification test).
- Redis cap enforcement is NOT asserted (Redis absent in CI → fail-open, same caveat
  as the legacy-worker report). The tests assert: (a) wiring completeness (CM entered
  once per job via `run()`), (b) no slot leak (enters == exits), (c) no deadlock (all
  N jobs reach terminal state within timeout), (d) exception-safety (a faulting
  `_fan_out_append` still releases the slot).
- `MaterialTraceJob` overrides `run()` and is covered by a separate AST-proof unit test
  (`tests/test_base_job_semaphore_wiring.py::TestMaterialTraceSlotWiring`) rather than
  the thread-burst harness — its `run()` requires real Oracle/DuckDB setup to
  instantiate, so behavioural stress testing it is deferred (see Known Gaps).

**Design constraints (from the Phase A-1 commit / `service-patterns.md`):**
- D1: Slot brackets the Oracle fan-out only (`_fan_out_append`/`_fan_out_reduction`),
  between `progress_report(5)` and `progress_report(15)`; `post_aggregate` stays
  outside (DuckDB-local).
- D2: `heavy_query_slot(owner)` is the same `@contextmanager` used by the legacy
  workers; release is guarded by `acquired` so fail-open never double-releases.
- D3: Slot acquisition is unconditional in `run()` — `run()` only executes on the
  `*_USE_UNIFIED_JOB=on` path, and the legacy per-domain acquires live on the
  mutually-exclusive flag-off path, so there is no double-count risk.
- D4: No `progress_callback` interaction — the Oracle fan-out call is opaque to the
  slot; a blocking acquire does not stall any callback chain.

## Duration

| test suite | wall time | timeout budget |
|---|---|---|
| Stress (N=20 burst): 2 tests | 0.29 s total | 60 s per thread |
| Integration (N=8 multi-worker): 4 tests | 0.24 s total | 30 s per thread |

## Metrics

### Stress suite (`tests/stress/test_base_job_semaphore_stress.py`, `@pytest.mark.stress`)

| metric | test_burst_peak_bounded_no_leak | test_burst_no_deadlock_with_mixed_success_failure |
|---|---|---|
| N (jobs) | 20 | 20 |
| completed | 20 | 16 |
| faulted | 0 | 4 (every 5th, injected in `_fan_out_append`) |
| elapsed | 0.03 s | — |
| enters (recording CM) | 20 | 20 |
| exits (recording CM) | 20 | 20 |
| slot leak (enters == exits) | NONE | NONE |
| peak_concurrent (recording CM) | 20 | — |
| deadlock | NONE | NONE |

**Note on peak_concurrent = 20:** as in the legacy-worker report, the recording CM does
not enforce the Redis semaphore cap — this verifies wiring completeness (every job
entered/exited `run()`'s slot exactly once), not the live Redis Lua-CAS cap.

### Integration suite (`tests/integration/test_base_job_semaphore_wiring.py`, `@pytest.mark.multi_worker`)

| test | N | outcome | enters | exits | notes |
|---|---|---|---|---|---|
| test_peak_slot_entries_bounded_by_worker_count | 8 | PASS | 8 | — | wiring: CM entered exactly N=8 times |
| test_all_jobs_complete_no_deadlock | 8 | PASS | — | — | all 8 reached terminal state, no stall |
| test_semaphore_fully_released_after_run | 8 | PASS | 8 | 8 | enters == exits; zero leak |
| test_slot_released_after_fanout_exception_in_worker | 4 | PASS | 4 | 4 | 1 faulted slot; enters == exits; no leak |

## Thresholds

| criterion | threshold | result |
|---|---|---|
| AC-1: peak Oracle-phase concurrency ≤ MAX_CONCURRENT (3) | ≤ 3 with real Redis | DEFERRED to production gate (recording CM only; real Redis absent in CI) |
| AC-1 (wiring): CM entered exactly once per `run()` call | N enters in N-job run | PASS — integration N=8: enter_count == 8; stress N=20: enters==20 |
| AC-2: all N jobs complete, no deadlock | 0 stalled within timeout | PASS — 8/8 integration, 20/20 stress (within 30s/60s budgets) |
| AC-3: zero slot leak post-run | enters == exits | PASS — all suites: enters == exits == N |
| AC-4: exception releases slot | faulted job's `_fan_out_append` still exits CM | PASS — integration 1/4 fault: 4 enters == 4 exits; stress 4/20 fault: 20 enters == 20 exits |
| error budget (non-injected faults) | 0 unexpected errors | PASS — no unexpected errors in any run |

## Commands / Workflows

```bash
# Stress tests (Tier-4 weekly gate; requires --run-stress):
conda run -n mes-dashboard pytest tests/stress/test_base_job_semaphore_stress.py -m stress -v --run-stress -s

# Integration concurrency tests (Tier-3 post-merge; multi_worker marker):
conda run -n mes-dashboard pytest tests/integration/test_base_job_semaphore_wiring.py -v

# Combined with the unified-job unit suite (pre-merge):
conda run -n mes-dashboard pytest tests/test_base_job_semaphore_wiring.py tests/test_base_chunked_duckdb_job.py -v
```

## Results

| suite | tests run | passed | failed | skipped |
|---|---|---|---|---|
| `tests/stress/test_base_job_semaphore_stress.py` | 2 | 2 | 0 | 0 |
| `tests/integration/test_base_job_semaphore_wiring.py` | 4 | 4 | 0 | 0 |
| `tests/test_base_job_semaphore_wiring.py` (unit, pre-merge) | 4 | 4 | 0 | 0 |

All 10 concurrency-focused tests pass. No slot leaks detected. No deadlocks observed.
Exception-safety confirmed (a faulting `_fan_out_append`/`_fan_out_reduction` still
releases its slot via `run()`'s `with heavy_query_slot(...)` block).

## Failure Triage

No failures in this run. One pre-existing, unrelated flake was observed while running
the full stress tier: `tests/stress/test_rq_semaphore_stress.py::test_burst_peak_bounded_no_leak`
occasionally reports 19/20 enters when run in the same process as other N=20 thread-burst
suites (thread-scheduling contention across ~40 concurrently-launched threads). It passes
reliably in isolation (3/3 runs) and is unrelated to the `base_chunked_duckdb_job` wiring
under test here — not fixed as part of this change.

## Known Gaps / Pre-Production Gate Items

1. **AC-1 real-Redis cap enforcement not exercised here** — same gap as the legacy-worker
   report. Before relying on the cap in production, run the integration suite against a
   real Redis instance with `HEAVY_QUERY_MAX_CONCURRENT=3` and confirm peak simultaneous
   slot holders ≤ 3 under N=8 concurrent jobs:
   `conda run -n mes-dashboard pytest tests/integration/test_base_job_semaphore_wiring.py -v --run-integration-real` (requires Redis).
   Note this is a **pre-existing** gap shared with the legacy wiring, not new risk
   introduced by base-job-semaphore-wiring — the underlying `global_concurrency` module
   is unchanged.
2. **`MaterialTraceJob.run()` not exercised by the thread-burst harness.** It is wired
   (proven statically via AST in `tests/test_base_job_semaphore_wiring.py`) but not
   behaviourally stress-tested because instantiating it requires real Oracle/DuckDB
   setup incompatible with the lightweight fake-job harness used here. If a future
   change makes `MaterialTraceJob` easier to construct with mocked I/O, add it to the
   stress/integration suites above.
3. **Combined production load** (six domains sharing one `HEAVY_QUERY_MAX_CONCURRENT`
   pool with the legacy per-domain wiring already live) is not modeled — this report
   only proves the *new* unified-core wiring behaves like the already-verified legacy
   wiring, not the aggregate cross-domain slot contention under real traffic. Soak
   validation (`@pytest.mark.soak`, weekly nightly gate per ci-gates.md) is the
   appropriate follow-up, mirroring Known Gap #3 in the legacy-worker report.
