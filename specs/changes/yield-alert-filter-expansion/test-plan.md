---
change-id: yield-alert-filter-expansion
schema-version: 0.1.0
last-changed: 2026-07-01
risk: medium
tier: 2
---

# Test Plan: yield-alert-filter-expansion

## Acceptance Criteria → Test Mapping

| criterion id | test family | test file path | tier |
|---|---|---|---|
| AC-1 | unit | frontend/tests/validation/useYieldAlert.validation.test.js::test_process_type_options_render_six_entries | 0 |
| AC-1 | e2e | frontend/tests/playwright/yield-alert-center.spec.ts::test_process_type_selector_shows_six_options | 1 |
| AC-2 | unit | tests/test_yield_alert_routes.py::test_query_accepts_each_new_process_type | 0 |
| AC-2 | unit | tests/test_yield_alert_routes.py::test_query_requires_valid_process_type | 0 |
| AC-2 | contract | tests/contract/test_capture_samples.py | 1 |
| AC-3 | unit | tests/test_yield_alert_dataset_cache.py::test_primary_query_id_differs_for_each_process_type | 0 |
| AC-3 | unit | tests/test_yield_alert_dataset_cache.py::test_process_type_like_patterns_mutually_exclusive | 0 |
| AC-3 | unit | tests/test_yield_alert_dataset_cache.py::test_process_type_f_uses_f_pattern | 0 |
| AC-4 | unit | frontend/tests/yield-alert/App.cross-filter.test.js::test_process_type_switch_clears_query_id_and_state | 0 |
| AC-4 | e2e | frontend/tests/playwright/yield-alert-center.spec.ts::test_process_type_filter | 1 |
| AC-4 | e2e | tests/e2e/test_yield_alert_e2e.py::TestYieldAlertProcessType::test_process_type_new_values_query_accepted | 1 |
| AC-5 | unit | tests/test_yield_alert_sql_runtime.py::TestQueryFilterOptions::test_query_filter_options_returns_departments_from_spool_distinct | 0 |
| AC-5 | unit | tests/test_yield_alert_sql_runtime.py::TestCrossFilterOptions::test_compute_cross_filter_options_includes_departments_dimension | 0 |
| AC-5 | unit | tests/test_yield_alert_sql_runtime.py::TestCrossFilterOptions::test_departments_use_raw_department_name_not_department_group | 0 |
| AC-5 | integration | tests/test_yield_alert_routes.py::test_view_workcenter_groups_sourced_from_spool_not_filter_cache | 1 |
| AC-5 | integration | tests/test_yield_alert_routes.py::test_cross_filter_options_workcenter_groups_from_spool | 1 |
| AC-6 | integration | tests/test_yield_alert_sql_runtime.py::TestCrossFilterOptions::test_selecting_department_narrows_lines_packages_types_functions | 1 |
| AC-6 | integration | tests/test_yield_alert_sql_runtime.py::TestCrossFilterOptions::test_selecting_line_narrows_departments | 1 |
| AC-6 | integration | tests/test_yield_alert_sql_runtime.py::TestCrossFilterOptions::test_workcenter_groups_change_with_process_type_query_id | 1 |
| AC-6 | unit | frontend/tests/yield-alert/useYieldAlertDuckDB.departments.test.js::test_query_filter_options_includes_departments | 0 |
| AC-7 | e2e | tests/e2e/test_yield_alert_e2e.py::TestYieldAlertProcessType::test_process_type_gd_f_w_d_return_valid_rows | 1 |
| AC-7 | data-boundary | tests/test_yield_alert_routes.py::test_view_new_process_type_zero_rows_returns_empty_not_error | 0 |
| AC-8 | integration | tests/test_yield_alert_routes.py::test_filter_options_still_uses_filter_cache | 1 |
| AC-8 | unit | tests/test_yield_alert_service.py (regression: no edits to filter_cache-consuming functions) | 0 |

## Test Families Required

| family | tier | notes |
|---|---|---|
| unit | 0 | process_type enum validation, query_id hash disjointness, LIKE-pattern mutual exclusivity, `_query_filter_options()`/`compute_cross_filter_options()` new `departments` dimension, raw `DEPARTMENT_NAME` vs `DEPARTMENT_GROUP` column assertion, `useYieldAlertDuckDB.ts` WASM parity (§3.16.6) |
| contract | 1 | expanded `process_type` enum + `workcenter_groups` shape sample re-capture per CLAUDE.md sample-churn procedure (`git checkout tests/contract/samples/` then re-stage only yield-alert samples) |
| integration | 1 | route-level `workcenter_groups` source swap (spool vs `filter_cache`) for `/view` and `/cross-filter-options` only; per-kwarg assertions (`call_args.kwargs[...]`), cross-filter narrowing tested both directions, `filter_cache` non-call assertion |
| e2e | 1 | Playwright: 6-option selector render, per-option query→spool round trip, force-requery watcher fires; py E2E: new `process_type` values against live-shaped fixtures |
| data-boundary | 0 | zero-row spool for a new `process_type` → empty `workcenter_groups`/result arrays not 500 (YA-12); null/whitespace `DEPARTMENT_NAME` handling (Oracle CHAR strip precedent) |

## Test Execution Ladder

| phase | required | command source | max failures | result artifact |
|---|---:|---|---:|---|
| collect | yes | cdd-kit test select | 1 | test-runs/<run-id>/summary.json |
| targeted | yes | cdd-kit test select | 1 | test-evidence.yml |
| changed-area | yes | cdd-kit test select | 1 | test-evidence.yml |
| contract | if affected | cdd-kit validate | 1 | test-evidence.yml |
| quality | if configured | ci-gates.md | 1 | test-evidence.yml |
| full | final/CI | cdd-kit test run --phase full | 1 | test-evidence.yml |

## Test Update Contract

| existing test | action | reason |
|---|---|---|
| tests/test_yield_alert_routes.py::test_query_requires_valid_process_type | update | extend invalid-value assertion so a near-miss like `"G%"` still 400s under the expanded 6-value enum (AC-2) |
| tests/test_yield_alert_dataset_cache.py::test_primary_query_id_differs_for_ga_and_gc | update | parametrize into a 6-way `process_type` comparison; rename to `test_primary_query_id_differs_for_each_process_type` (AC-3) |
| tests/test_yield_alert_routes.py::test_view_supports_workcenter_group_filters | update | add assertion that `filter_cache.get_workcenter_groups` is NOT called and spool-derived `DEPARTMENT_NAME` values are returned instead (AC-5, YA-10) |
| tests/test_yield_alert_routes.py::test_cross_filter_options_forwards_query_id_and_filters | update | add `departments` to per-kwarg forwarding assertions (AC-5, AC-6) |
| tests/test_yield_alert_routes.py::test_filter_options_returns_workcenter_groups | update | add explicit assertion that this endpoint (unlike `/view`) still calls `filter_cache.get_workcenter_groups` unchanged (AC-8, YA-11 regression guard) |
| tests/test_yield_alert_sql_runtime.py::TestCrossFilterOptions::test_compute_cross_filter_options_applies_other_dimension_filters | update | fixture currently has no `DEPARTMENT_NAME` column and no `departments` result-key assertion — add both (AC-5, AC-6) |
| frontend/tests/validation/useYieldAlert.validation.test.js (process_type block, lines 225-256) | update | `['GA%', 'GC%']` closed-list assertions must expand to the 6-value enum (AC-1, AC-2) |
| frontend/tests/yield-alert/App.cross-filter.test.js | update | extend watcher/force-requery coverage to the 4 new `PROCESS_TYPE_OPTIONS` values (AC-4) |
| frontend/tests/playwright/yield-alert-center.spec.ts::test_process_type_filter | update | parametrize the GC% radio-click case over GD%/F%/W%/D% (AC-1, AC-4) |
| tests/e2e/test_yield_alert_e2e.py::TestYieldAlertProcessType | update | add cases alongside `test_process_type_gc_percent_query_accepted` for the 4 new values, including a zero-row case (AC-4, AC-7) |

## Stop Rules

- Do not run broad pytest before targeted and changed-area phases pass.
- Do not investigate more than the first failure per phase.
- Do not classify any failure as known, pre-existing, waived, or allowed.
- If full suite fails, record the first failure and block the gate.

## Out of Scope

- `GET /api/yield-alert/filter-options` behavior change — explicitly unaffected (YA-11); covered only as a regression guard (AC-8).
- GA% sub-split by `WIP_CLASS_CODE` (YA-02a) — non-goal, no new tests.
- resilience/fuzz/stress/soak families — not required per change-classification.md (no new concurrency/queue wiring; reuses existing spool/query path).
- visual-review-report.md — selector is text-only options; evidence via ui-ux-reviewer agent-log pointer, not a test-plan item.
- "其他(D%)" label wording — ui-ux-reviewer/i18n concern, not a test assertion target.

## Notes

- "update" rows above are extensions of existing test files/functions, not new parallel files — confirmed present via `.cdd/code-map.yml`.
- Test-discipline: per-kwarg assertions (not `assert_called_once_with` whitelists), both spool and `filter_cache` paths tested, cross-filter narrowing tested both directions, fixtures must include `DEPARTMENT_NAME`.
- AC-7 zero-row boundary must assert a valid empty array, not an equal-to-cap false pass.
- `tests/property/test_cross_filter.py` read for reuse; no yield-alert content currently present — extend only if a generic property invariant applies, otherwise out of scope.
