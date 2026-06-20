---
change-id: wip-rq-worker-chunks-cleanup
schema-version: 0.1.0
last-changed: 2026-06-20
risk: high
tier: 1
---

# Test Plan: wip-rq-worker-chunks-cleanup

## Acceptance Criteria → Test Mapping

| criterion id | test family | test file path | tier |
|---|---|---|---|
| AC-1 | unit | `tests/test_job_registry.py` | 0 |
| AC-2 | integration | `tests/integration/test_wip_rowcount_rq_routing.py` | 1 |
| AC-3 | integration | `tests/integration/test_wip_rowcount_rq_routing.py` | 1 |
| AC-4 | unit | `tests/test_wip_query_job_service.py` | 0 |
| AC-5 | resilience | `tests/integration/test_wip_rowcount_rq_routing.py` | 1 |
| AC-6 | unit | `tests/test_batch_query_engine.py` | 0 |
| AC-6 | unit | `tests/test_wip_query_job_service.py` | 0 |
| AC-7 | integration | `tests/integration/test_wip_rowcount_rq_routing.py` | 1 |
| AC-7 | unit | `tests/test_spool_routes.py` | 0 |
| AC-8 | integration | `tests/integration/test_rq_semaphore_wiring.py` | 1 |
| AC-8 | stress | `tests/stress/test_rq_semaphore_stress.py` | 3 |

## Test Families Required

| family | tier | notes |
|---|---|---|
| unit | 0 | job registration count, slot-placement assertions, merge_chunks absence via ast.parse, wip_dataset namespace |
| integration | 1 | 202→poll→spool, sync-path unchanged, fail-open, schema parity, semaphore cap |
| e2e | 1 | lightweight Playwright: above-L3 202→poll→results; below-L3 sync path unchanged |
| resilience | 1 | Redis-down fail-open; COUNT error fail-open (never 503) |
| stress | 3 | WIP RQ slot contention under load; connection-pool exhaustion absent |
| soak | 4 | nightly/weekly — long-running WIP async job stability; informational |

## Test Execution Ladder

| phase | required | command source | max failures | result artifact |
|---|---:|---|---:|---|
| collect | yes | `pytest --collect-only -q tests/test_wip_query_job_service.py tests/test_job_registry.py tests/test_query_cost_policy.py tests/test_batch_query_engine.py tests/test_spool_routes.py tests/integration/test_wip_rowcount_rq_routing.py tests/integration/test_rq_semaphore_wiring.py` | 1 | test-runs/summary.json |
| targeted | yes | `pytest tests/test_wip_query_job_service.py tests/test_job_registry.py` | 1 | test-evidence.yml |
| changed-area | yes | `pytest tests/test_batch_query_engine.py tests/test_spool_routes.py tests/test_query_cost_policy.py tests/integration/test_wip_rowcount_rq_routing.py tests/integration/test_rq_semaphore_wiring.py` | 1 | test-evidence.yml |
| contract | if affected | `cdd-kit validate --contracts` | 1 | test-evidence.yml |
| quality | if configured | `ruff check . && cd frontend && npm run type-check` | 1 | test-evidence.yml |
| full | final/CI | `pytest` | 1 | test-evidence.yml |

## New Test Files to Create

- `tests/test_wip_query_job_service.py` — AC-4 (no Oracle at enqueue time; slot wraps only Oracle phase at milestones 15→90), AC-6 (merge_chunks absent from new module via ast.parse)

## Existing Test Files to Extend

| existing test file | action | AC |
|---|---|---|
| `tests/test_job_registry.py::TestJobServiceRegistrations::test_each_service_registers_exactly_one_job_type` | update — bump count +1, add `"wip-detail"` assertion | AC-1 |
| `tests/test_query_cost_policy.py::TestNoPandasAndNoCallers::test_no_caller_outside_tests` | update — add `wip_query_job_service` stem to `_APPROVED_CALLERS` | AC-1 |
| `tests/test_batch_query_engine.py::TestMergeChunks` (lines 345–495) | delete — entire class plus `merge_chunks` import on line 11; add `test_merge_chunks_absent_from_source` via ast.parse | AC-6 |
| `tests/test_spool_routes.py::test_allowed_namespaces_pass_namespace_validation` | update — add `"wip_dataset"` to `@pytest.mark.parametrize` list | AC-7 |
| `tests/integration/test_wip_rowcount_rq_routing.py::TestAboveL3Threshold` | extend — add `test_wip_above_l3_job_completes_and_spool_readable`; assert 202 + job_id + parquet retrievable | AC-2 |
| `tests/integration/test_wip_rowcount_rq_routing.py::TestBelowL3Threshold` | extend — add `test_async_row_schema_matches_sync_path`; compare spool parquet columns vs sync `lots[0]` keys | AC-3, AC-7 |
| `tests/integration/test_wip_rowcount_rq_routing.py::TestCountErrorFailOpen` | extend — add `test_wip_redis_down_fails_open_to_sync` (mock `is_async_available()=False`) | AC-5 |
| `tests/integration/test_rq_semaphore_wiring.py::TestConcurrencyCap` | extend — add `test_wip_detail_slot_respects_concurrency_cap` mirroring `test_peak_oracle_concurrent_bounded` | AC-8 |

## Test Update Contract

| existing test | action | reason |
|---|---|---|
| `tests/test_batch_query_engine.py::TestMergeChunks` (5 tests) | delete | `merge_chunks` dead-code removed by AC-6; tests have no impl to verify |

## Out of Scope

- Sync path internals (`wip_service.get_wip_detail` paged-dict logic) — unchanged
- WIP filter behavior, L1/L2 routing thresholds — unchanged
- Spool TTL values — operational tuning only
- `merge_chunks_to_spool`, `MergeChunksMaxRowsExceeded`, `ChunkSchemaMismatch` — must NOT be deleted; existing tests stay
- `WIP_DETAIL_USE_RQ` feature-flag tests — D1 confirms no routing flag introduced
- Env-contract tests for `WIP_WORKER_QUEUE` tuning var — operational only; no enum/default required

## Stop Rules

- Do not run broad pytest before targeted and changed-area phases pass.
- Do not investigate more than the first failure per phase.
- Do not classify any failure as known, pre-existing, waived, or allowed.
- If full suite fails, record the first failure and block the gate.

## Notes

- AC-7 open risk (design.md §Open Risks): sync path returns `summary + lots`; spool can only carry the row set. Backend-engineer must reconcile before AC-7 integration test can be written green. Use `pytest.mark.xfail(strict=True)` placeholder until implementation settles.
- `merge_chunks` absence: use `ast.parse()` + `ast.walk` on `batch_query_engine.py` source text — not grep — to prove absence at the AST level (test-discipline.md §ast.parse pattern).
- `tests/integration/` pytestmark: new standalone integration tests must add `@pytest.mark.integration` explicitly; methods added to existing classes inherit automatically.
- Stress-soak-report.md is a required artifact for this Tier 1 change; the stress gate must pass before PR is gate-ready.
