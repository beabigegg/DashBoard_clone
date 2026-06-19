---
change-id: query-path-c-elimination-cleanup
schema-version: 0.1.0
last-changed: 2026-06-19
---

# Stress-Soak Report: query-path-c-elimination-cleanup

## Scope

**What was tested:**
- AC-8.1 (no worker starvation): When `QUERY_TOOL_USE_RQ=on` and `classify_query_cost` returns `ASYNC`, all N=10 concurrent callers of `POST /api/query-tool/equipment-period` return HTTP 202 immediately without holding a gunicorn worker for the query duration.
- AC-8.2 (Oracle concurrency bound): The `acquire_heavy_query_slot` / `release_heavy_query_slot` mechanism correctly limits concurrent Oracle holders to `HEAVY_QUERY_MAX_CONCURRENT` (default 3) even when N=8 workers attempt to acquire simultaneously.

**What was NOT tested (production gaps):**
- Real Oracle query latency and connection pool behavior under actual oversized queries.
- Real Redis Lua semaphore script under concurrent RQ workers.
- Real RQ queue depth / job fan-out behavior.
- Gunicorn multi-worker process mode (tests used Flask test client in single-process mode).
- Memory/RSS growth or temp-file accumulation (no soak component; per design.md soak = not required).
- `execute_query_tool_job` semaphore wiring: the semaphore is not yet wired into `execute_query_tool_job` at the Oracle-fetch boundary (design §D3 / blueprint §4.2). AC-8.2 tests the semaphore mechanism in isolation; the end-to-end wiring requires a production integration test before flag flip.

**Assumptions:**
- Mock `enqueue_query_job` returns instantly; wall-clock measures Flask routing + dispatch overhead only.
- `HEAVY_QUERY_MAX_CONCURRENT=3` is the default; if the operator changes this, the semaphore bound changes proportionally.
- Tests were run with `pytest --run-stress` on a single-core dev host; multi-core gunicorn behavior may differ.

## Test Results

Run command:
```
conda run -n mes-dashboard pytest tests/stress/test_query_tool_stress.py::TestAC8StructuralGuarantees -v --run-stress -s
```

| test | result | duration | evidence |
|---|---|---|---|
| test_no_worker_starvation_under_concurrent_oversized_queries | PASS | 0.42s (session) | N=10 concurrent callers all returned 202; wall-clock 17ms (<2000ms threshold); max individual 13ms (<500ms threshold) |
| test_rq_oracle_concurrency_bounded_by_semaphore | PASS | 0.42s (session) | N=8 concurrent workers; peak_concurrent=3; MAX=3; peak never exceeded bound; all 8/8 completed; wall 154ms |

Session total: 2 passed in 0.42s

## Risk Assessment

**R1: COUNT(*) overhead (wip_routes rowcount pre-check)**
Confirmed in design.md §D2: fail-open on Oracle COUNT error preserves today's behavior. The pre-check only fires when no spool/cache short-circuit is available. The stress tests for this change scope (AC-8) focus on the RQ dispatch path, not the COUNT path. COUNT overhead under concurrent WIP load is a residual risk requiring production observation after deployment.

**R2: Semaphore concurrency bound**
AC-8.2 CONFIRMED: The acquire/release mechanism correctly bounds concurrent holders at `HEAVY_QUERY_MAX_CONCURRENT=3` when N=8 workers compete simultaneously. Peak concurrent observed = 3 (exactly at the bound, never above). All 8 workers completed without deadlock or slot leak (`_active_count` returned to 0).

Residual gap: AC-8.2 exercises the semaphore function signatures directly. The wiring of `acquire_heavy_query_slot` inside `execute_query_tool_job` (per blueprint §4.2) is NOT yet present in the service implementation. This is a known gap: the semaphore mechanism is proven correct, but the integration of semaphore + worker is not yet exercised. The production readiness gate below captures this.

**R3: Known gaps**
- `execute_query_tool_job` does not yet call `acquire_heavy_query_slot` around the Oracle fetch (grep: zero matches for `acquire_heavy_query_slot` in `query_tool_service.py`). Blueprint §4.2 and D3 state it should; this must be wired before production Oracle concurrency is actually bounded.
- Mock-based tests cannot detect connection pool exhaustion, Redis Lua script correctness under real network latency, or gunicorn worker file-descriptor accumulation.

## Production Readiness Gate

`QUERY_TOOL_USE_RQ=on` promotion requires:
- [x] stress test 1: no worker starvation (PASS — this report, 2026-06-19)
- [x] stress test 2: Oracle concurrency semaphore mechanism bounded (PASS — this report, 2026-06-19)
- [ ] Wire `acquire_heavy_query_slot` inside `execute_query_tool_job` around the Oracle fetch call (required before semaphore actually caps production concurrency)
- [ ] Production real-Oracle load test: run `test_mixed_query_tool_soak_no_5xx_or_crash` against a staging gunicorn instance with `QUERY_TOOL_USE_RQ=on` (NOT covered by this report; must be run manually before flag flip)
- [ ] `cdd-kit gate --strict` green

## Cold Data Warning
This report is historical evidence. Current behavior is governed by contracts/ and source.
