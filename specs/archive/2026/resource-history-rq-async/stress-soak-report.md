# Stress / Soak Report

## Workload Model

| Dimension | Value |
|---|---|
| Target | `execute_resource_history_query_job` (RQ worker entry point) |
| Oracle substitute | `mock.MagicMock(return_value={"query_id": "...", "rows": []})` |
| Concurrency | N=5 (pool exhaustion probe); N=10 (milestone probe) |
| Request mix | 100% long-span async worker invocations (no sync-path load) |
| Data volume | mocked — no real Parquet written |
| Cache hit/miss | not exercised (Oracle fully mocked) |
| Job timeout scenario | `RESOURCE_JOB_TIMEOUT_SECONDS` patched to 1 s; Oracle stub sleeps 2 s then raises |
| Runner | pytest `--run-stress` (unit-level, no live server) |

## Duration

- N=5 concurrency probe: 0.05 s
- N=10 milestone probe: 0.01 s
- Timeout enforcement probe: 2.00 s (driven by the 2 s sleep stub)
- Total session: 2.22 s

## Metrics

| Test | Workers | Result | Duration |
|---|---|---|---|
| `test_concurrent_async_jobs_complete_without_db_pool_exhaustion` | 5 | PASS | 0.05 s |
| `test_async_job_progress_milestones_under_load` | 10 | PASS | 0.01 s |
| `test_job_timeout_enforced_under_slow_oracle` | 1 | PASS | 2.00 s |

## Thresholds Asserted

- `DatabasePoolExhaustedError` count == 0 under N=5 concurrent worker calls.
- All 10 milestone sequences non-decreasing; every sequence ends at pct=100.
- `complete_job(error=...)` called with a non-empty error string on timeout-like failure.
- Worker re-raises after exception (RQ sees a failed job, not a silent swallow).
- Timeout scenario completes in < 10 s (no indefinite hang).

## Commands / Workflows

```bash
# Pre-merge (markers deselected; 3 skipped, no overhead):
pytest tests/stress/test_resource_history_stress.py::TestResourceHistoryAsyncStress -v

# Nightly / manual stress run:
pytest tests/stress/test_resource_history_stress.py::TestResourceHistoryAsyncStress -v --run-stress
```

Lane: nightly (per `test-plan.md` and `ci-gates.md` — stress not pre-merge).

## Results

All 3 tests passed in the `mes-dashboard` conda environment (Python 3.11.14,
pytest 9.0.2, Linux 6.17.0-1018-azure). No `DatabasePoolExhaustedError`,
no milestone inversions, no indefinite hangs.

## Failure Triage

**Initial failure during authoring** — `test_async_job_progress_milestones_under_load`
reported `stress-ms-09: no milestones recorded` on first run. Root cause: per-thread
`mock.patch` context managers sharing the same patch target (`update_job_progress`)
are not safe when 10 threads race to enter/exit simultaneously — the last thread to
start could enter the context after an earlier thread exited, seeing the un-patched
function. Fix: replaced per-thread `mock.patch` with a single `monkeypatch.setattr`
capturing pct per-`job_id` into a shared dict protected by `threading.Lock`. All
subsequent runs pass deterministically.

## Risk Assessment

**DB pool sizing (design Open Risk):** `execute_primary_query` runs a
`ThreadPoolExecutor(max_workers=2)` fan-out for base+OEE; the worker launch
pins `DB_POOL_SIZE=2 DB_MAX_OVERFLOW=1`. Under N=5 concurrent workers the
fan-out would need up to 10 connections simultaneously. With Oracle fully mocked,
no pool contention surfaces in these tests. The production risk remains open until
a live-Oracle integration run (nightly gate) confirms pool tolerance. The nightly
`test_resource_history_rq_async.py::test_job_timeout_produces_terminal_error_status`
integration test covers the live path.

**`RESOURCE_JOB_TIMEOUT_SECONDS` vs spool TTL:** timeout probe confirms the
exception path is wired correctly. The `< spool TTL` ordering is an operational
constraint verified by the default values (1800 s timeout < 3600 s TTL); no
test-level mechanism forces this ordering.

## Recommendation

Ready for production async load: **yes, with conditions.**

Conditions:
1. Nightly integration gate (`test_resource_history_rq_async.py`) must pass against
   a live Oracle + Redis environment before declaring full AC-3/AC-9 coverage.
2. Monitor `DB_POOL_TIMEOUT` errors in the worker process log during the first
   production soak week (watch for pool exhaustion under concurrent long-span queries).
3. Confirm `RESOURCE_JOB_TIMEOUT_SECONDS` (1800) < spool TTL (3600) in every
   deployment topology's `.env` before enabling `RESOURCE_ASYNC_ENABLED=true`.
