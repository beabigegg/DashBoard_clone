---
change-id: async-progress-ui
schema-version: 0.1.0
last-changed: 2026-06-13
risk: low
tier: 3
---

# Test Plan: async-progress-ui

## Acceptance Criteria → Test Mapping

| criterion id | test family | test file path | runner | tier |
|---|---|---|---|---|
| AC-1 | unit (component) | `frontend/tests/components/AsyncQueryProgress.test.js` | `cd frontend && npm run test -- AsyncQueryProgress` | 3 |
| AC-2 | contract (TypeScript) | `frontend/tests/shared-composables/useAsyncJobPolling.test.js` | `cd frontend && npm run test -- useAsyncJobPolling` | 3 |
| AC-3 | unit (component) | `frontend/tests/components/AsyncQueryProgress.test.js` | `cd frontend && npm run test -- AsyncQueryProgress` | 3 |
| AC-4 | unit (component) | `frontend/tests/components/AsyncQueryProgress.test.js` | `cd frontend && npm run test -- AsyncQueryProgress` | 3 |
| AC-5 | unit (backend) | `tests/test_yield_alert_job_service.py tests/test_production_history_job_service.py` | `conda run -n mes-dashboard pytest tests/test_yield_alert_job_service.py tests/test_production_history_job_service.py` | 3 |
| AC-6 | contract (CSS) | `frontend/tests/components/AsyncQueryProgress.test.js` | `cd frontend && npm run css:check` | 3 |
| AC-7 | unit (non-regression) | `frontend/tests/components/AsyncQueryProgress.test.js` | `cd frontend && npm run test -- AsyncQueryProgress` | 3 |

## Test Families Required

| family | tier | notes |
|---|---|---|
| unit — Vue component | 0 | New `AsyncQueryProgress.test.js`; `@vue/test-utils mount` pattern as in `LoadingSpinner.test.js` |
| unit — composable type | 0 | Extend `useAsyncJobPolling.test.js` lines 1-237 for `pct`/`stage` field forwarding |
| unit — backend service | 0 | Extend `TestExecuteYieldAlertJob` and `TestExecuteProductionHistoryJob` with pct-milestone call-order assertions |
| contract — TypeScript | 0 | `vue-tsc --noEmit`; `JobStatusResponse.pct?: number` and `.stage?: string` typed; gate: `npm run type-check` |
| contract — CSS governance | 0 | `css-inventory.md` entry for `.async-job-progress` present; no unscoped bleed; gate: `npm run css:check` |

## Test Names — new file: frontend/tests/components/AsyncQueryProgress.test.js

- `renders progress bar element with .async-job-progress base class`
- `bar fill width reflects pct prop (0, 30, 100)`
- `displays elapsed seconds from elapsedSeconds prop`
- `displays stage label from progress prop`
- `is hidden (not rendered) when active is false`
- `renders cancel button when canCancel is true`
- `does not render cancel button when canCancel is false or omitted`
- `emits cancel event on cancel button click`
- `no theme-* class present on root or children`
- `reject-history .async-job-status-bar is not affected (import guard: no reject-history import)`

## Test Names — extend: frontend/tests/shared-composables/useAsyncJobPolling.test.js

- `pollJobUntilComplete forwards pct field from job status response`
- `pollJobUntilComplete forwards stage field from job status response`

## Test Names — extend: tests/test_yield_alert_job_service.py::TestExecuteYieldAlertJob

- `test_update_job_progress_called_with_pct_0_at_start`
- `test_update_job_progress_called_with_pct_30_after_query`
- `test_update_job_progress_called_with_pct_100_before_complete`

## Test Names — extend: tests/test_production_history_job_service.py::TestExecuteProductionHistoryJob

- `test_update_job_progress_called_with_pct_0_at_start`
- `test_update_job_progress_called_with_pct_30_after_query`
- `test_update_job_progress_called_with_pct_100_before_complete`

## Test Update Contract

| existing test | action | reason |
|---|---|---|
| `tests/test_yield_alert_job_service.py::TestExecuteYieldAlertJob::test_cache_miss_calls_execute_primary_query_then_complete` | extend | add pct-milestone call assertions alongside existing flow assertions |
| `tests/test_production_history_job_service.py::TestExecuteProductionHistoryJob::test_spool_miss_calls_query_and_complete_job` | extend | add pct-milestone call assertions alongside existing flow assertions |

## Out of Scope

- E2E / Playwright tests (no new routes; progress bar is presentational only)
- Integration tests against real Redis/Oracle (pct milestones are fully unit-testable with mocks)
- Visual regression / snapshot tests (no design token dependency)
- Stress, soak, monkey tests

## Notes

- Backend pct-milestone assertions must use `call_args.kwargs['pct']` per-kwarg form, not `assert_called_once_with`, per test-discipline rules.
- AC-3/AC-4 consumer wiring is proven transitively by AC-1 component tests + `vue-tsc --noEmit`; no separate App.vue unit test required.
- AC-6 CSS gate depends on `css-inventory.md` entry existing; implementer must add the entry before `css:check` can pass.
- AC-7 non-regression is structural: `AsyncQueryProgress.test.js` must not import from `reject-history/` and must not touch lines 1478-1486 of reject-history `App.vue`.
