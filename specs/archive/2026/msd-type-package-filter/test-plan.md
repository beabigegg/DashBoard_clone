---
change-id: msd-type-package-filter
schema-version: 0.1.0
last-changed: 2026-06-29
risk: medium
tier: 2
---

# Test Plan: msd-type-package-filter

## Acceptance Criteria → Test Mapping

| criterion id | test family | test file path | tier |
|---|---|---|---|
| AC-1 | unit | tests/test_mid_section_defect_routes.py::test_container_filter_options_returns_type_and_package_lists | 0 |
| AC-1 | integration | tests/test_mid_section_defect_routes.py::test_container_filter_options_does_not_call_read_sql_df | 1 |
| AC-1 | contract | tests/contract/test_capture_samples.py | 1 |
| AC-2 | unit | tests/test_mid_section_defect_service.py::test_query_analysis_filter_by_pj_type_reduces_rows | 0 |
| AC-2 | unit | tests/test_mid_section_defect_service.py::test_query_analysis_filter_by_package_reduces_rows | 0 |
| AC-2 | unit | tests/test_mid_section_defect_service.py::test_query_analysis_filter_pj_type_and_package_and_semantics | 0 |
| AC-2 | unit | tests/test_mid_section_defect_routes.py::test_analysis_forwards_pj_types_kwarg | 0 |
| AC-2 | unit | tests/test_mid_section_defect_routes.py::test_analysis_forwards_packages_kwarg | 0 |
| AC-3 | unit | frontend/tests/legacy/mid-section-defect-composables.test.js::test_app_filters_state_includes_pj_types_and_packages | 0 |
| AC-3 | e2e | frontend/tests/playwright/mid-section-defect.spec.ts::test_filter_bar_renders_type_multiselect | 1 |
| AC-3 | e2e | frontend/tests/playwright/mid-section-defect.spec.ts::test_filter_bar_renders_package_multiselect | 1 |
| AC-4 | unit | frontend/tests/legacy/mid-section-defect-composables.test.js::test_cross_filter_type_selection_narrows_package_options | 0 |
| AC-4 | e2e | frontend/tests/playwright/mid-section-defect.spec.ts::test_type_selection_narrows_package_options | 1 |
| AC-5 | unit | tests/test_mid_section_defect_service.py::test_query_analysis_no_pj_types_packages_output_unchanged | 0 |
| AC-5 | unit | tests/test_mid_section_defect_routes.py::test_analysis_absent_pj_types_forwards_unchanged | 0 |
| AC-6 | integration | tests/test_mid_section_defect_routes.py::test_container_filter_options_does_not_call_read_sql_df | 1 |
| AC-7 | unit | tests/test_mid_section_defect_service.py::test_query_analysis_unknown_pj_type_returns_empty_detection | 0 |
| AC-7 | unit | tests/test_mid_section_defect_service.py::test_query_analysis_empty_pj_types_list_no_filter | 0 |
| AC-7 | unit | tests/test_mid_section_defect_service.py::test_query_analysis_null_pj_type_column_no_crash | 0 |
| AC-7 | unit | tests/test_mid_section_defect_routes.py::test_analysis_malformed_pj_types_param_returns_no_5xx | 0 |

## Test Families Required

| family | tier | notes |
|---|---|---|
| unit | 0 | service post-query filter; route param forwarding per-kwarg via `call_args.kwargs[key]` (not assert_called_once_with); both selected and empty cases per filter kwarg |
| contract | 1 | targeted sample capture for new endpoint only; assert analysis response shape unchanged |
| integration | 1 | container-filter-options cache-hit path: `get_filter_options()` called, `read_sql_df` not called |
| e2e | 1 | Playwright: two new MultiSelects visible; Type narrows Package; pj_types sent in API call |
| data-boundary | 0 | tested within unit family — see table below |

## Data-Boundary Cases

| # | input | expected |
|---|---|---|
| 1 | pj_types=[], packages=[] | no filter; full detection_df rows returned |
| 2 | pj_types=["NONEXISTENT"] | empty df after filter; response shape unchanged; no 5xx |
| 3 | packages=["NONEXISTENT"] | empty df after filter; response shape unchanged; no 5xx |
| 4 | pj_types=["X"], packages=["Y"] with no co-occurrence rows | empty df; valid response shape |
| 5 | pj_types absent from request | baseline behavior unchanged (AC-5) |
| 6 | packages absent from request | baseline behavior unchanged (AC-5) |
| 7 | detection_df is empty before filter is applied | empty result; no 5xx |
| 8 | PJ_TYPE column contains NULL values in df | NULLs excluded from filter match; no crash |
| 9 | PRODUCTLINENAME column contains NULL values | NULLs excluded from filter match; no crash |
| 10 | pj_types=["X","X"] (duplicate values in param) | same result as pj_types=["X"] |
| 11 | container-filter-options: Redis unavailable / miss | falls back gracefully; no 5xx |
| 12 | container-filter-options: cache returns empty lists | empty arrays in response; no 5xx |
| 13 | malformed pj_types query param (non-list form) | 400 or graceful empty result; no 5xx |
| 14 | pj_types selected, packages absent → partial filter | only pj_types filter applied; packages unconstrained |

## Test Update Contract

| existing test | action | reason |
|---|---|---|
| frontend/tests/playwright/mid-section-defect.spec.ts::installBaseRoutes | update | add mock for `**/api/mid-section-defect/container-filter-options**` so new MultiSelects resolve options |

## Out of Scope

- Oracle SQL changes (none; filter is Python-only on detection_df)
- New Redis cache namespace or key structure (reuses existing 24h TTL path)
- Stress / soak tests (in-memory filtering; no new load surface)
- `test_container_filter_cache.py` cross-filter internals (already covered; no duplication)
- Full `test_capture_samples.py` suite re-run (targeted capture only per contract-reviewer log)

## Notes

- Route forwarding assertions must use `call_args.kwargs[key]` per-kwarg, not `assert_called_once_with()` whitelist.
- AC-5 parity: assert route `call_args` unchanged when pj_types/packages absent, not byte-level response diff.
- E2E: Playwright `installBaseRoutes` must register `container-filter-options` BEFORE specific overrides (LIFO rule).
- Contract sample capture is targeted to `get_mid_section_defect_container_filter_options` only; run `git checkout tests/contract/samples/` for unrelated churn.
