# Stress / Soak Report

## Workload Model

**System under test:** `heavy_query_slot(owner)` context-manager wiring in
`execute_hold_history_query_job` (hold worker), representing the pattern applied identically
to query-tool and resource workers.

**Test approach:** Mock-based; no real Oracle or Redis required.
- The recording CM replaces the real `heavy_query_slot` to count enter/exit events and
  measure peak overlap by timestamp.
- Oracle I/O simulated with `time.sleep(0.02)` inside the CM to create genuine thread overlap.
- Redis cap enforcement is NOT asserted by these tests (Redis absent in CI → fail-open).
  The tests assert: (a) wiring completeness (CM entered/exited exactly once per worker),
  (b) no slot leak (enters == exits after all workers finish), (c) no deadlock (all N
  workers reach terminal state within wall-clock timeout).

**Design constraints driving this model (from design.md):**
- D1: Slot brackets Oracle phase only, between pct=15 and pct=90 emits.
- D2: `heavy_query_slot(owner)` is a `@contextmanager` wrapper around the bool-returning
  `acquire_heavy_query_slot` / `release_heavy_query_slot` pair; release guarded by `acquired`
  so fail-open does not double-release.
- D3: Reject worker excluded (already wired at cache layer); no job-level acquire added.
- D4: No `progress_callback` interaction — Oracle call is opaque; blocking acquire does not
  stall any callback chain.

## Duration

| test suite | wall time | timeout budget |
|---|---|---|
| Stress (N=20 burst): 2 tests | 0.34 s total | 60 s per thread |
| Integration (N=8 multi-worker): 4 tests | 0.25 s total | 30 s per thread |

## Metrics

### Stress suite (`tests/stress/test_rq_semaphore_stress.py`, `@pytest.mark.stress`)

| metric | test_burst_peak_bounded_no_leak | test_burst_no_deadlock_with_mixed_success_failure |
|---|---|---|
| N (workers) | 20 | 20 |
| completed | 20 | 17 |
| faulted | 0 | 3 (every 5th, injected) |
| elapsed | 0.13 s | — |
| enters (recording CM) | 20 | 20 |
| exits (recording CM) | 20 | 20 |
| slot leak (enters == exits) | NONE | NONE |
| peak_concurrent (recording CM) | 20 | — |
| deadlock | NONE | NONE |

**Note on peak_concurrent = 20:** The recording CM does not enforce the Redis semaphore cap;
all 20 threads freely overlap inside the mock CM. This is the intended behavior of a
recording-only harness — it verifies that every worker entered and exited the CM exactly
once (wiring completeness), not that the real Redis Lua-CAS cap was applied. Real cap
enforcement occurs at production time when Redis is available and `acquire_heavy_query_slot`
performs the Lua-CAS decrement. The peak cap test against a live Redis semaphore is a
pre-production gate item (see Known Gaps below).

### Integration suite (`tests/integration/test_rq_semaphore_wiring.py`, `@pytest.mark.multi_worker`)

| test | N | outcome | enters | exits | notes |
|---|---|---|---|---|---|
| test_peak_oracle_concurrent_bounded | 8 | PASS | 8 | — | wiring: CM entered exactly N=8 times |
| test_all_jobs_complete_no_deadlock | 8 | PASS | — | — | all 8 reached terminal state, no stall |
| test_semaphore_fully_released_after_run | 8 | PASS | 8 | 8 | enters == exits; zero leak |
| test_slot_released_after_oracle_exception_in_worker | 4 | PASS | 4 | 4 | 1 faulted slot; enters == exits; no leak |

## Thresholds

| criterion | threshold | result |
|---|---|---|
| AC-1: peak Oracle-phase concurrency ≤ MAX_CONCURRENT (3) | ≤ 3 with real Redis | DEFERRED to production gate (recording CM only; real Redis absent in CI) |
| AC-1 (wiring): CM entered exactly once per worker | N enters in N-worker run | PASS — integration N=8: enter_count == 8; stress N=20: enters==20 |
| AC-2: all N jobs complete, no deadlock | 0 stalled within timeout | PASS — 8/8 integration, 20/20 stress (within 30s/60s budgets) |
| AC-3: zero slot leak post-run | enters == exits | PASS — all suites: enters == exits == N |
| AC-4: exception releases slot | faulted worker exits CM | PASS — integration 1/4 fault: 4 enters == 4 exits; stress 3/20 fault: 20 enters == 20 exits |
| error budget (non-injected faults) | 0 unexpected errors | PASS — no unexpected errors in any run |

## Commands / Workflows

```bash
# Stress tests (Tier-4 weekly gate; requires --run-stress):
conda run -n mes-dashboard pytest tests/stress/test_rq_semaphore_stress.py -m stress -v --run-stress -s

# Integration concurrency tests (Tier-3 post-merge; multi_worker marker):
conda run -n mes-dashboard pytest tests/integration/test_rq_semaphore_wiring.py -v

# Combined with full unit suite (pre-merge):
conda run -n mes-dashboard pytest tests/test_rq_semaphore_wiring.py tests/test_global_concurrency.py -v
```

## Results

| suite | tests run | passed | failed | skipped |
|---|---|---|---|---|
| `tests/stress/test_rq_semaphore_stress.py` | 2 | 2 | 0 | 0 |
| `tests/integration/test_rq_semaphore_wiring.py` | 4 | 4 | 0 | 0 |

All 6 mock-based stress and integration concurrency tests pass. No slot leaks detected.
No deadlocks observed. Exception-safety confirmed (faulted workers release their CM entry).

## Failure Triage

No failures in this run. Pre-production gate items that would surface as failures are
documented below under Known Gaps.

## Known Gaps / Pre-Production Gate Items

1. **AC-1 real-Redis cap enforcement not exercised here.** The recording CM bypasses the
   Redis Lua-CAS semaphore. Before any `*_USE_RQ=on` flag promotion to production:
   - Run the integration test suite against a real Redis instance with
     `HEAVY_QUERY_MAX_CONCURRENT=3` and confirm peak simultaneous slot holders ≤ 3 under
     N=8 concurrent workers.
   - Gate command: `conda run -n mes-dashboard pytest tests/integration/test_rq_semaphore_wiring.py -v --run-integration-real` (requires Redis).

2. **Resource worker 2-connection-per-slot fan-out: DBA headroom not validated.**
   `execute_resource_history_query_job` fans base+OEE over `ThreadPoolExecutor(max_workers=2)`,
   consuming 2 Oracle connections per slot. Effective Oracle connection count at MAX_CONCURRENT=3
   is `3 × 2 = 6 + overhead`. DBA must confirm `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` for the
   resource worker can absorb 6 simultaneous Oracle connections before `RESOURCE_ASYNC_ENABLED`
   is turned on. This is an operational gate, not a code change (per design.md Open Risks and
   implementation-plan.md Known Risks).

3. **Soak workload (24h+ leak detection) not yet run.** Weekly nightly gate per ci-gates.md.
   The soak suite (`@pytest.mark.soak`) requires a long-running scheduler target. Slow permit
   leak under sustained dispatch is not detectable from the current 0.13s / 0.25s burst runs.
   Schedule: weekly lane after production promotion.

4. **query-tool and resource wiring not independently exercised in stress harness.**
   The stress harness exercises the hold worker only (as the pattern representative).
   Before flag-on for query-tool or resource, run analogous N=20 burst probes against
   `execute_query_tool_job` and `execute_resource_history_query_job` using the same
   recording-CM approach.
