---
change-id: query-path-c-elimination-cleanup
schema-version: 0.1.0
last-changed: 2026-06-19
risk: high
tier: 1
---

# Test Plan: query-path-c-elimination-cleanup

## Acceptance Criteria → Test Mapping

| criterion id | test family | test file path | tier |
|---|---|---|---|
| AC-1 | unit | tests/integration/test_query_tool_rq_async.py | 1 |
| AC-1 | integration | tests/integration/test_query_tool_rq_async.py | 1 |
| AC-2 | integration | tests/integration/test_query_tool_rq_async.py | 1 |
| AC-2 | e2e | tests/e2e/test_query_tool_e2e.py | 1 |
| AC-3 | unit | tests/integration/test_wip_rowcount_rq_routing.py | 1 |
| AC-3 | e2e | tests/e2e/test_wip_hold_pages_e2e.py | 1 |
| AC-4 | unit | tests/test_batch_query_engine.py | 1 |
| AC-5 | contract | tests/contract/test_env_async_threshold_removal.py | 1 |
| AC-6 | contract | tests/contract/test_env_async_threshold_removal.py | 1 |
| AC-7 | contract | tests/contract/test_env_async_threshold_removal.py | 1 |
| AC-7 | unit | tests/test_query_cost_policy.py | 1 |
| AC-8 | stress | tests/stress/test_query_tool_stress.py | 4 |
| (registry) | unit | tests/test_job_registry.py | 1 |

## Test Families Required

| family | tier | notes |
|---|---|---|
| unit | 1 | dispatch threshold, deprecation warning, registry count, cost-policy cleanup |
| contract | 1 | env-pin: absence of 4 removed vars; QUERY_TOOL_USE_RQ default=off |
| integration | 1 | flag-on 202+job_id parity; flag-off no-regression; worker-blocking-elimination; wip L3 routing |
| e2e | 1 | small query stays inline; flag-off behavior identical to pre-change; sub-L3 WIP inline |
| stress | 4 | RQ Oracle concurrency <= semaphore bound; no gunicorn worker starvation under load |

## Test Execution Ladder

| phase | required | command source | max failures | result artifact |
|---|---:|---|---:|---|
| collect | yes | cdd-kit test select | 1 | test-runs/<run-id>/summary.json |
| targeted | yes | cdd-kit test select | 1 | test-evidence.yml |
| changed-area | yes | cdd-kit test select | 1 | test-evidence.yml |
| contract | yes | cdd-kit validate --contracts | 1 | test-evidence.yml |
| quality | if configured | ci-gates.md | 1 | test-evidence.yml |
| full | final/CI | cdd-kit test run --phase full | 1 | test-evidence.yml |

## Test Update Contract

| existing test | action | reason |
|---|---|---|
| tests/test_batch_query_engine.py::TestMergeChunks | extend | add `test_merge_chunks_emits_deprecation_warning` asserting `DeprecationWarning` is raised; result unchanged (AC-4) |
| tests/test_job_registry.py::TestJobServiceRegistrations::test_each_service_registers_exactly_one_job_type | update | bump expected count 10→11; add "query-tool" to expected_types set (D1, R3) |
| tests/test_query_cost_policy.py::TestDeprecationWarning | delete/update | remove `test_deprecation_warning_for_async_threshold_env` / `test_no_deprecation_warning_without_env_var` after `_check_deprecated_threshold_env` is removed (IP-7) |

## New Tests Required

- `tests/integration/test_query_tool_rq_async.py`
  - `test_flag_on_oversized_query_returns_202_with_job_id` (AC-1)
  - `test_flag_on_oversized_enqueues_rq_job_not_inline` (AC-1)
  - `test_flag_off_oversized_query_returns_inline_as_before` (AC-2)
  - `test_flag_off_small_query_identical_to_pre_change` (AC-2)

- `tests/integration/test_wip_rowcount_rq_routing.py`
  - `test_wip_above_l3_threshold_routes_to_rq` (AC-3)
  - `test_wip_below_l3_threshold_stays_inline` (AC-3)
  - `test_wip_count_error_fails_open_stays_inline` (AC-3, R1 fail-open)

- `tests/contract/test_env_async_threshold_removal.py`
  - `test_downtime_async_day_threshold_absent_from_schema` (AC-5, AC-7)
  - `test_hold_async_day_threshold_absent_from_schema` (AC-5, AC-7)
  - `test_resource_async_day_threshold_absent_from_schema` (AC-5, AC-7)
  - `test_reject_async_day_threshold_absent_from_schema` (AC-5, AC-7)
  - `test_query_tool_use_rq_present_with_default_off` (AC-7)
  - `test_semaphore_semantics_note_in_env_contract` (AC-6)

- `tests/stress/test_query_tool_stress.py` (extend existing)
  - `test_no_worker_starvation_under_concurrent_oversized_queries` (AC-8)
  - `test_rq_oracle_concurrency_bounded_by_semaphore` (AC-8)

## Stop Rules

- Do not run broad pytest before targeted and changed-area phases pass.
- Do not investigate more than the first failure per phase.
- Do not classify any failure as known, pre-existing, waived, or allowed.
- If full suite fails, record the first failure and block the gate.

## Out of Scope

- Domain RQ migrations (P1–P3 already complete; not re-tested here)
- `global_concurrency` runtime mechanics (D3: docs-only; no new runtime test)
- Frontend, CSS, spool/parquet schema (none changed)
- `merge_chunks` removal (non-goal; backward compat only)
- Nightly real-Oracle integration (integration_real marker; not pre-merge)
- Soak tests (not required per design.md)

## Notes

- `tests/integration/` already has `pytestmark` — check before adding mock tests (CLAUDE.md test-discipline).
- `test_query_tool_stress.py` exists in `tests/stress/`; extend rather than create new file.
- Stress (AC-8) is weekly/manual (Tier 4); requires `stress-soak-report.md` before gate closes (tier-floor-override already set per design due to new job type with zero initial callers).
- New `query-tool` worker file must NOT use `oracle_arrow_reader` / `base_chunked_duckdb_job` unless `_APPROVED_CALLERS` in `test_query_cost_policy.py` is updated in the same PR (R3).
