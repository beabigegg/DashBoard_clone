---
change-id: downtime-analysis-page-redesign
schema-version: 0.1.0
last-changed: 2026-06-03
risk: medium
tier: 2
---

# Test Plan: downtime-analysis-page-redesign

## Acceptance Criteria → Test Mapping

| criterion id | test family | test file path | tier |
|---|---|---|---|
| AC-1 | unit | `tests/test_downtime_analysis_service.py::TestApplyViewFilter` | 0 |
| AC-1 | contract | `tests/test_downtime_analysis_routes.py::TestEquipmentDetailRoute` | 1 |
| AC-1 | e2e | `frontend/tests/playwright/downtime-analysis.spec.js` | 1 |
| AC-2 | unit | `tests/test_downtime_analysis_service.py::TestApplyViewFilter` | 0 |
| AC-2 | contract | `tests/test_downtime_analysis_routes.py::TestEquipmentDetailRoute` | 1 |
| AC-2 | e2e | `frontend/tests/playwright/downtime-analysis.spec.js` | 1 |
| AC-3 | e2e | `frontend/tests/playwright/downtime-analysis.spec.js` | 1 |
| AC-4 | unit | `frontend/tests/components/downtime-analysis/StatusMachineJobTable.test.ts` | 0 |
| AC-4 | unit | `frontend/tests/components/downtime-analysis/MachineEventRows.test.ts` | 0 |
| AC-4 | e2e | `frontend/tests/playwright/downtime-analysis.spec.js` | 1 |
| AC-5 | unit | `tests/test_downtime_analysis_service.py::TestApplyViewFilter` | 0 |
| AC-5 | contract | `tests/test_downtime_analysis_routes.py::TestEquipmentDetailRoute` | 1 |
| AC-5 | contract | `tests/test_downtime_analysis_routes.py::TestEventDetailRoute` | 1 |
| AC-5 | integration | `tests/test_api_contract.py::TestDowntimeSummaryShape` | 1 |
| AC-5 | data-boundary | `tests/test_downtime_analysis_routes.py::TestFilterDataBoundary` | 1 |
| AC-6 | unit | `frontend/scripts/css-governance-check.js` (via `npm run css:check`) | 0 |
| AC-6 | e2e | `frontend/tests/playwright/downtime-analysis.spec.js` | 1 |
| AC-7 | unit | existing shared-ui component tests (no new file needed) | 0 |
| AC-8 | unit | `frontend/tests/components/downtime-analysis/MachineEventRows.test.ts` | 0 |
| AC-8 | data-boundary | `tests/test_downtime_analysis_routes.py::TestFilterDataBoundary` | 1 |

## Test Families Required

| family | tier | notes |
|---|---|---|
| unit | 0 | Backend: `TestApplyViewFilter` (new class in existing file) — `apply_view` with `big_category`, `status_types`, `resource_id`, combined, and omit-all. Frontend: `StatusMachineJobTable.test.ts`, `MachineEventRows.test.ts` (new files). |
| contract | 1 | Extend `TestEquipmentDetailRoute` and `TestEventDetailRoute` in existing `test_downtime_analysis_routes.py` — per-kwarg forwarding using `mock_service.call_args.kwargs[key]` pattern (not `assert_called_once_with`). |
| integration | 1 | `test_api_contract.py::TestDowntimeSummaryShape` — verify filtered response wrapper key (`equipment_detail`, `events`) is unchanged; assert response shape identical with and without filter params. |
| e2e | 1 | Extend `frontend/tests/playwright/downtime-analysis.spec.js` — BigCategoryChart click/toggle, DailyTrendChart legend toggle, Tier 3 lazy-load network call, tab switcher absent, `.theme-downtime-analysis` root class. |
| data-boundary | 1 | New class `TestFilterDataBoundary` in `test_downtime_analysis_routes.py` — empty string, missing param, `status_types=INVALID`, `big_category=` all return 200 with unfiltered-shape response (no 500). |

## New Test Names (one line each)

**`tests/test_downtime_analysis_service.py::TestApplyViewFilter`** (new class — extend existing file)
- `test_equipment_detail_filtered_by_big_category`
- `test_equipment_detail_filtered_by_status_types_single`
- `test_equipment_detail_filtered_by_status_types_union`
- `test_event_detail_filtered_by_resource_id`
- `test_combined_big_category_and_status_types`
- `test_omit_all_params_returns_unfiltered`
- `test_empty_big_category_string_is_no_op`

**`tests/test_downtime_analysis_routes.py::TestEquipmentDetailRoute`** (extend existing class)
- `test_big_category_forwarded`
- `test_status_types_csv_forwarded`
- `test_resource_id_forwarded`
- `test_omit_filter_params_calls_service_without_filter_kwargs`

**`tests/test_downtime_analysis_routes.py::TestEventDetailRoute`** (extend existing class)
- `test_big_category_forwarded`
- `test_status_types_csv_forwarded`
- `test_resource_id_forwarded`

**`tests/test_downtime_analysis_routes.py::TestFilterDataBoundary`** (new class)
- `test_equipment_detail_empty_big_category_returns_200`
- `test_equipment_detail_invalid_status_types_returns_200`
- `test_event_detail_missing_resource_id_returns_200`
- `test_equipment_detail_response_has_equipment_detail_key`
- `test_event_detail_response_has_events_key`

**`frontend/tests/components/downtime-analysis/StatusMachineJobTable.test.ts`** (new file)
- `renders Tier 1 status group rows from props`
- `expands Tier 1 row to show Tier 2 machine rows`
- `collapses expanded Tier 1 row on second click`
- `emits expand-machine with resource_id and status_type when Tier 2 row expanded`
- `chartFilter big_category prop change hides non-matching groups`

**`frontend/tests/components/downtime-analysis/MachineEventRows.test.ts`** (new file)
- `shows loading skeleton when cacheEntry.loading is true`
- `renders event rows when cacheEntry has data`
- `emits mount on onMounted with correct resource_id key`
- `resolves rows from events wrapper key not bare array`
- `empty events array renders empty-state message not silent blank`

**`frontend/tests/playwright/downtime-analysis.spec.js`** (extend existing)
- `BigCategoryChart_click_filters_three_tier_table`
- `BigCategoryChart_same_slice_click_clears_filter`
- `DailyTrendChart_legend_click_filters_by_status_type`
- `DailyTrendChart_multiple_legend_clicks_union_filter`
- `tier3_lazy_load_fires_event_detail_request_on_machine_expand`
- `no_tab_switcher_present_in_redesigned_layout`
- `root_element_has_theme_downtime_analysis_class`

## Out of Scope

- Chart rendering fidelity (ECharts option correctness) — covered by existing `overview_chart_renders_and_kpi_cards_visible`
- Filter bar date validation and QueryButton behavior — covered by existing `filter_bar_date_inputs_accept_user_input`
- Stress/soak: no new high-load path; filtering is in-memory spool (ADR-0003 excluded from rowcount chunking)
- Monkey/fuzz: no adversarial input surface added
- `view_toggle_chart_to_events_preserves_filter_state` — retire this test (tab switcher removed per AC-3); replace with `no_tab_switcher_present_in_redesigned_layout`

## Notes

- All new route-forwarding tests must use `mock.assert_called_once()` + `mock.call_args.kwargs[key]` — never `assert_called_once_with(...)` (CLAUDE.md test discipline rule).
- `TestApplyViewFilter` fixtures must include `big_category`, `status_types`, and `resource_id` columns; omitting any column causes the filter to silently no-op and pass against a wrong implementation.
- AC-8 wrapper keys are `equipment_detail` (not `rows`) and `events` (not `data`); pin these as named constants in `MachineEventRows.test.ts` so drift is caught at test-write time.
- `view_toggle_chart_to_events_preserves_filter_state` (existing Playwright test) must be updated or retired since the tab switcher it exercises is removed by AC-3.
- R3 (200-row cap): add `test_equipment_detail_row_count_within_page_size_cap` to `TestApplyViewFilter` to document the ceiling.
