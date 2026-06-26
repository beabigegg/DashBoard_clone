---
change-id: rh-remove-supplementary-filter
schema-version: 0.1.0
last-changed: 2026-06-25
risk: medium
tier: 2
---

# Test Plan: rh-remove-supplementary-filter

## Acceptance Criteria → Test Mapping

| criterion id | test family | test file path | tier | command |
|---|---|---|---|---|
| AC-1 (supplementary panel absent from rendered UI) | e2e | frontend/tests/playwright/reject-history-filter.spec.ts | 2 | `npx playwright test frontend/tests/playwright/reject-history-filter.spec.ts` |
| AC-1 (no supplementary state/emits in composable) | unit | frontend/tests/validation/useRejectHistory.validation.test.js | 0 | `npx vitest run frontend/tests/validation/useRejectHistory.validation.test.js` |
| AC-2 (報廢原因 4th column visible in primary-prefilter; populated from /options) | e2e | frontend/tests/playwright/reject-history-filter.spec.ts | 2 | `npx playwright test frontend/tests/playwright/reject-history-filter.spec.ts` |
| AC-2 (reasons[] in POST body when 報廢原因 selected) | e2e | frontend/tests/playwright/reject-history-filter.spec.ts | 2 | `npx playwright test frontend/tests/playwright/reject-history-filter.spec.ts` |
| AC-2 (reasons field present in /options response shape) | unit | frontend/tests/validation/useRejectHistory.validation.test.js | 0 | `npx vitest run frontend/tests/validation/useRejectHistory.validation.test.js` |
| AC-3 (_build_base_where emits NVL(TRIM(r.LOSSREASONNAME),'(未填寫)') IN with reason_N binds) | unit | tests/test_reject_history_service.py | 0 |
| AC-3 (empty reasons[] produces no additional restriction in base_where) | unit | tests/test_reject_history_service.py | 0 |
| AC-3 ((未填寫) sentinel value appears verbatim in bind params for NULL mapping) | unit | tests/test_reject_history_service.py | 0 |
| AC-3 (route forwards reasons[] per-kwarg to execute_primary_query) | unit | tests/test_reject_history_routes.py | 0 |
| AC-4 (reasons[] forwarded through legacy-async path; mock is_async_available=True) | integration | tests/test_reject_history_async_routes.py | 1 |
| AC-4 (reasons[] forwarded through unified-job path) | integration | tests/test_reject_history_unified_job.py | 1 |
| AC-4 (reasons[] in query_id_input; distinct selections produce distinct cache keys) | unit | tests/test_reject_dataset_cache.py | 0 |
| AC-4 (reasons[] in job enqueue params via reject_query_job_service) | unit | tests/test_reject_query_job_service.py | 0 |
| AC-5 (workcenter_groups absent from query route kwarg extraction) | unit | tests/test_reject_history_routes.py | 0 |
| AC-5 (workcenter_groups absent from queryDetail/queryBatchPareto/getAvailableFilters call kwargs) | unit | tests/test_reject_history_routes.py | 0 |
| AC-5 (getAvailableFilters not callable on useRejectHistoryDuckDB) | unit | frontend/tests/validation/useRejectHistory.validation.test.js | 0 |
| AC-6 (Pareto cross-filter paretoSelections still passes correctly) | unit | tests/test_reject_history_routes.py | 0 |
| AC-6 (detail pagination contract preserved) | unit | tests/test_reject_history_routes.py | 0 |
| AC-6 (CSV export still returns streaming response) | unit | tests/test_reject_history_routes.py | 0 |
| AC-7 (BASE_WHERE reasons prefilter result equivalence including (未填寫) bucket) | data-boundary | tests/test_reject_history_service.py | 1 |
| AC-8 (contract samples reflect reasons[] added / workcenter_groups removed) | contract | tests/contract/samples/ | 1 |
| AC-8 (css:check passes after supplementary CSS removal and grid change) | contract | frontend/tests/validation/useRejectHistory.validation.test.js | 0 |

## Test Families Required

| family | tier | notes |
|---|---|---|
| unit | 0 | _build_base_where reasons[]; route per-kwarg forwarding; cache-key boundary; removal assertions |
| contract | 1 | Regen affected samples only (POST /query shape); git checkout unaffected samples |
| integration | 1 | Legacy-async and unified-job paths; mock is_async_available()=True (CI has no Redis) |
| e2e | 2 | Playwright: supplementary panel absent; 4th column present; reasons[] in captured POST body |
| data-boundary | 1 | (未填寫) bucket vs NULL; empty-selection default must not collide with prior cache entries |

## Test Update Contract

| existing test | action | reason |
|---|---|---|
| test_reject_history_routes.py::test_options_passes_full_draft_filters | update | remove workcenter_groups assertion; assert workcenter_groups kwarg is absent from call |
| test_reject_history_routes.py::test_summary_passes_filters_and_meta | update | remove workcenter_groups assertion |
| test_reject_history_routes.py::test_list_route_preserves_pagination_contract | update | remove workcenter_groups kwarg from GET params; assert absent from call kwargs |
| test_reject_history_service.py::test_get_filter_options_reads_from_caches | update | remove workcenter_groups from expected result contract if removed from service return |
| reject-history-filter.spec.ts::test_workcenter_filter_options | update or delete | supplementary workcenter panel removed; replace with 報廢原因 primary column test |

## Out of Scope

- Stress, soak, monkey, resilience tests: not required per change-classification.md.
- Cross-app workcenter_groups in downtime/yield-alert/resource tests: unaffected by this change.
- Visual layout regression beyond css:check: covered by agent-log/visual-reviewer.yml unless blocking.

## Notes

- **Pre-push grep required**: `grep -r "workcenter_groups\|getAvailableFilters\|supplementary" tests/ frontend/tests/` — confirm no reject-history references survive; stale assertions pass the bounded gate but fail CI `unit-and-integration-tests`.
- All route-forwarding assertions must use `call_args.kwargs[key]` per-kwarg pattern; no `assert_called_once_with()` whitelists.
- AC-5 removal tests must assert the kwarg is **absent** from `call_args.kwargs`, not merely falsy or default.
- Contract sample regeneration: run `pytest tests/contract/test_capture_samples.py` then `git checkout tests/contract/samples/` and re-stage only entries affected by the POST /api/reject-history/query shape change.
- Tests extend existing files in Allowed Paths; do not create new test files.
