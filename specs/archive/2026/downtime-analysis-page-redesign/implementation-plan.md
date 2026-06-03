---
change-id: downtime-analysis-page-redesign
schema-version: 0.1.0
last-changed: 2026-06-03
---

# Implementation Plan: downtime-analysis-page-redesign

## Objective
Restructure the downtime-analysis page from a three-tab switcher (Charts / Equipment / Events) into a single page: charts on top, a three-tier expandable table below (Tier 1 status group UDT/SDT/EGT -> Tier 2 machine -> Tier 3 lazy-loaded events). Wire `BigCategoryChart` sector-click and `DailyTrendChart` legend-click as cross-filters that forward `big_category`, `status_types`, and `resource_id` as additive optional query params to the existing `equipment-detail` / `event-detail` endpoints. Backend filtering is an in-memory pandas `.isin()` narrow on the already-assembled spool `events_df`; no new Oracle query, no spool-namespace change, no rowcount chunking (stays within ADR-0002 / ADR-0003). Deliver against the AC mapping in `test-plan.md` and the gates in `ci-gates.md`.

## Execution Scope

### In Scope
- Backend: extend `apply_view()` (and the `_build_equipment_detail_page` / `_build_event_detail_page` reducers) in `downtime_analysis_service.py` to accept `big_category`, `status_types`, `resource_id` and apply an in-memory filter before reduction (design.md DQ-1, DQ-4).
- Backend: parse the new optional params in `downtime_analysis_routes.py` `equipment-detail` / `event-detail` handlers (`status_types` via existing `_csv_param()`) and forward to `apply_view()`.
- Backend: raise the `equipment-detail` `page_size` cap so the full equipment set loads in one page (design.md DQ-2). Keep `event-detail` pagination as-is (default 50, max 200 per data-shape-contract.md §3.12.6).
- Frontend: single-page layout in `App.vue`, new `StatusMachineJobTable.vue` (Tier 1+2) and `MachineEventRows.vue` (Tier 3 lazy-load), cross-filter wiring on the two chart components, chartFilter + Tier 3 cache state, scoped CSS.
- Tests first (TDD): backend service/route/data-boundary tests, frontend component tests, extended Playwright spec, per test-plan.md §New Test Names.

### Out of Scope (non-goals — do NOT do these)
- Do NOT add any new Oracle query, SQL file, or backend date/per-day filter param. The only new params are the three named filters (design.md DQ-5 rejects bar-segment date filtering).
- Do NOT change the spool namespace, `DOWNTIME_BRIDGE_VERSION`, or parquet column schema; no parquet cleanup in the runbook (design.md Migration/Rollback; ADR-0002).
- Do NOT delete `EquipmentDetail.vue` or `EventDetail.vue` — only un-import them from `App.vue` (design.md DQ-6). They remain on disk for one-revert rollback.
- Do NOT modify the emit/prop surface of any `frontend/src/shared-ui/components/` file. If `DataTable` cannot express the three-tier nesting additively, build `StatusMachineJobTable.vue` as a standalone component (design.md R2, AC-7). shared-ui is read-only / verify-additive only.
- Do NOT change the response wrapper keys or per-row schemas of `equipment-detail` (`equipment_detail`) or `event-detail` (`events`). Filtering narrows the row set only (data-shape-contract.md §3.12.5 / §3.12.6, AC-5).
- Do NOT touch `data/page_status.json`, `asset_readiness_manifest.json`, or `route_scope_matrix.json` — no page add/remove, no route or `drawer_id` change.
- Do NOT opportunistically refactor the chart `option` builders, the `_merge_cross_shift_events` / `_bridge_jobid` reductions, or filter-bar/QueryButton behavior.
- Do NOT edit `.github/workflows/frontend-tests.yml` — ci-gates.md confirms the browser-install and Playwright steps already exist; no workflow change is needed.

## Required Changes
| id | area | required action | owner agent |
|---|---|---|---|
| IP-1 | backend service | Extend `apply_view()` + `_build_equipment_detail_page` / `_build_event_detail_page` with `big_category` / `status_types` / `resource_id`; apply `.isin()` narrow on `events_df` before reducers; default omit-all = unfiltered (AC-5, DQ-1/DQ-4) | backend-engineer |
| IP-2 | backend route | Parse new optional params in `equipment-detail` / `event-detail` handlers (`status_types` via `_csv_param()`); forward to `apply_view()`; raise equipment-detail `page_size` cap to load full set in one page (DQ-2) | backend-engineer |
| IP-3 | backend tests | Write failing tests first: `TestApplyViewFilter` (service), `TestEquipmentDetailRoute` / `TestEventDetailRoute` extensions + `TestFilterDataBoundary` (routes) per test-plan.md §New Test Names | backend-engineer |
| IP-4 | contract changelog | Confirm `contracts/CHANGELOG.md` has the `## [api 1.14.0]` entry (cdd-validate gate). If absent, add it; do not embed version entries in individual contract files | backend-engineer |
| IP-5 | frontend types + composable | Add `ChartFilter` / `TierThreeEntry` to `types.ts`; add `loadAllEquipmentDetail(filter)` (full page) and `loadMachineStatusEvents(resourceId, statusType, filter)` to `useDowntimeData.ts`; Tier 3 cache key `${resource_id}|${status_type}` (DQ-3) | frontend-engineer |
| IP-6 | frontend new components | Create `StatusMachineJobTable.vue` (Tier 1+2, standalone — not a shared-ui edit) and `MachineEventRows.vue` (Tier 3 lazy-load, reads `events` wrapper key) | frontend-engineer |
| IP-7 | frontend chart wiring | Add additive `selectedCategory` prop + `click-category` emit to `BigCategoryChart.vue`; `selectedStatusTypes` prop + `click-status` emit via `@legendselectchanged` to `DailyTrendChart.vue` (DQ-5) | frontend-engineer |
| IP-8 | frontend shell | Restructure `App.vue`: remove three-tab switcher, un-import `EquipmentDetail.vue` / `EventDetail.vue` (keep on disk, DQ-6), add `chartFilter` + `tierThreeCache` reactive state and handlers; clear Tier 3 cache on re-query AND on chartFilter change (DQ-3) | frontend-engineer |
| IP-9 | frontend CSS | Add `.theme-downtime-analysis`-scoped rules for status-group / machine / chart-filter chips / inner event table; remove `.view-tabs` / `.view-tab` rules; run `npm run build` so `dist/` updates (CLAUDE.md Portal-Shell CSS Notes) | frontend-engineer |
| IP-10 | frontend tests | Write failing tests first: `StatusMachineJobTable.test.ts`, `MachineEventRows.test.ts`; extend `downtime-analysis.spec.js` and retire `view_toggle_chart_to_events_preserves_filter_state` per test-plan.md | frontend-engineer |

## Source Artifact Pointers
| source | relevant pointer | used for |
|---|---|---|
| design.md | DQ-1..DQ-6, Affected Components table, Open Risks R1..R4 | architecture constraints, file map, cache-key + casing discipline |
| test-plan.md | §Acceptance Criteria -> Test Mapping, §New Test Names, §Notes | exact test classes/methods to write, fixture-column discipline, retired E2E test |
| ci-gates.md | §Required Gates table, §Promotion Policy, §Merge Eligibility | local + PR verification commands, blocked conditions |
| change-classification.md | AC-1..AC-8, §Required Contracts | acceptance criteria + contract update obligations |
| contracts/api/api-contract.md | rows 218-219; §CHANGELOG `downtime-analysis-page-redesign (2026-06-03)` (lines 352-357) | param surface; already updated to 1.14.0 |
| contracts/data/data-shape-contract.md | §3.12.5 (wrapper key `equipment_detail`), §3.12.6 (wrapper key `events`, page_size max 200), §3.12.7 (JobEnrichment null) | wrapper keys for AC-8; unchanged-shape assertion for AC-5 |
| contracts/css/css-contract.md | rule 4.4 (Teleport scope), Rule 6 (scoped feature CSS) | CSS scoping for AC-6 |
| docs/adr/0002 / 0003 | spool namespace; rowcount-chunking exclusion | confirms in-memory filter stays in bounds |

## File-Level Plan
| path | action | notes |
|---|---|---|
| `src/mes_dashboard/services/downtime_analysis_service.py` | edit | `apply_view()` (~L963) + `_build_equipment_detail_page` (~L1006) / `_build_event_detail_page` (~L1074) gain `big_category` / `status_types` / `resource_id` kwargs; apply `.isin()` filter on `events_df` before the existing reducers; omit-all path byte-for-byte unchanged |
| `src/mes_dashboard/routes/downtime_analysis_routes.py` | edit | `api_downtime_equipment_detail` (~L219) and `api_downtime_event_detail` (~L262): read `big_category` (string), `status_types` (CSV via `_csv_param`, ~L65), `resource_id` (string) from `request.args`; forward to `apply_view()`; raise equipment-detail `page_size` cap to load full equipment set in one page (DQ-2) |
| `tests/test_downtime_analysis_service.py` | edit (add class) | new `TestApplyViewFilter` with the 7 methods in test-plan.md + `test_equipment_detail_row_count_within_page_size_cap` (R3); fixtures MUST include `big_category`, `status_types`, `resource_id` columns (test-plan.md §Notes) |
| `tests/test_downtime_analysis_routes.py` | edit (add/extend) | extend `TestEquipmentDetailRoute` / `TestEventDetailRoute` with per-kwarg forwarding (`mock.call_args.kwargs[...]`, non-default values, never `assert_called_once_with`); new `TestFilterDataBoundary` class |
| `tests/test_api_contract.py` | edit | `TestDowntimeSummaryShape`: assert filtered response wrapper keys (`equipment_detail`, `events`) and per-row shape identical with vs without filter params (AC-5) |
| `contracts/CHANGELOG.md` | verify (edit only if missing) | confirm `## [api 1.14.0]` entry exists (cdd-validate gate); never write version entries into individual contract files |
| `frontend/src/downtime-analysis/types.ts` | edit | add `ChartFilter { big_category, status_types[] }` and `TierThreeEntry { loading, error, rows }` (additive) |
| `frontend/src/downtime-analysis/composables/useDowntimeData.ts` | edit | add `loadAllEquipmentDetail(filter)` (single full page) and `loadMachineStatusEvents(resourceId, statusType, filter)`; forward filter params; resolve `events` wrapper key; Tier 3 cache keyed `${resource_id}|${status_type}` |
| `frontend/src/downtime-analysis/components/StatusMachineJobTable.vue` | new | three-tier expandable table (Status groups -> Machine rows -> Tier 3 slot); props `equipmentRows`, `summaryData`, `tierThreeCache`, `chartFilter`; emits `expand-machine`, `export`; standalone (not a shared-ui edit) |
| `frontend/src/downtime-analysis/components/MachineEventRows.vue` | new | Tier 3 lazy-load display; `onMounted` emits `mount`; renders loading / error / rows / empty-state; reads `events` wrapper key (AC-8) |
| `frontend/src/downtime-analysis/components/BigCategoryChart.vue` | edit | add `selectedCategory` prop + `click-category` emit + `handleChartClick` toggle + opacity feedback (additive) |
| `frontend/src/downtime-analysis/components/DailyTrendChart.vue` | edit | add `selectedStatusTypes` prop + `click-status` emit via `@legendselectchanged` `handleLegendChange` (additive) |
| `frontend/src/downtime-analysis/App.vue` | edit | remove three-tab switcher; un-import (keep on disk) `EquipmentDetail.vue` / `EventDetail.vue`; add `chartFilter` + `tierThreeCache` state and `handleCategoryClick` / `handleStatusClick` / `handleExpandMachine` handlers; clear Tier 3 cache on re-query AND chartFilter change (DQ-3); wire new components |
| `frontend/src/downtime-analysis/style.css` | edit | add `.theme-downtime-analysis`-scoped rules for status-group / machine rows / chart-filter chips / inner event table; remove `.view-tabs` / `.view-tab`. After editing run `cd frontend && npm run build` |
| `frontend/src/downtime-analysis/EquipmentDetail.vue` | unchanged (on disk) | un-imported only; do NOT delete (DQ-6) |
| `frontend/src/downtime-analysis/EventDetail.vue` | unchanged (on disk) | un-imported only; do NOT delete (DQ-6) |
| `frontend/tests/components/downtime-analysis/StatusMachineJobTable.test.ts` | new | 5 tests per test-plan.md (Tier 1/2 render, expand/collapse, expand-machine emit, chartFilter prop reactivity) |
| `frontend/tests/components/downtime-analysis/MachineEventRows.test.ts` | new | 5 tests per test-plan.md; pin `events` wrapper key as named constant; assert empty array -> empty-state not silent blank (AC-8) |
| `frontend/tests/playwright/downtime-analysis.spec.js` | edit | add 7 specs per test-plan.md; retire `view_toggle_chart_to_events_preserves_filter_state` (tab switcher removed, AC-3) |

## Contract Updates

- API: already updated to 1.14.0 (api-contract.md rows 218-219, CHANGELOG lines 352-357). Implementation must match it exactly; do NOT re-edit param semantics. Verify `contracts/CHANGELOG.md` carries `## [api 1.14.0]` (IP-4).
- CSS/UI: new authored rules must be scoped under `.theme-downtime-analysis` per css-contract.md Rule 6. If new CSS sources are introduced, confirm css-inventory.md coverage.
- Env: none.
- Data shape: no change — verify only. Wrapper keys `equipment_detail` / `events` and per-row schemas stay identical (data-shape-contract.md §3.12.5 / §3.12.6); assert in `TestDowntimeSummaryShape` and `TestFilterDataBoundary`.
- Business logic: none — UDT/SDT/EGT grouping reflects existing classification.
- CI/CD: none — `.github/workflows/frontend-tests.yml` already has browser-install + Playwright steps (ci-gates.md §Workflow).

## Test Execution Plan
| acceptance criterion | test file / command | expected signal |
|---|---|---|
| AC-1 | `pytest tests/test_downtime_analysis_service.py::TestApplyViewFilter`; `tests/test_downtime_analysis_routes.py::TestEquipmentDetailRoute`; `downtime-analysis.spec.js::BigCategoryChart_click_filters_three_tier_table` / `..._same_slice_click_clears_filter` | table filters on category click; same-slice click clears; route forwards `big_category` |
| AC-2 | same service/route classes; `downtime-analysis.spec.js::DailyTrendChart_legend_click_filters_by_status_type` / `..._multiple_legend_clicks_union_filter` | legend click toggles status filter; multi-status union |
| AC-3 | `downtime-analysis.spec.js::no_tab_switcher_present_in_redesigned_layout` (retire `view_toggle_chart_to_events_preserves_filter_state`) | single-page layout; no tab switcher |
| AC-4 | `StatusMachineJobTable.test.ts`, `MachineEventRows.test.ts`; `downtime-analysis.spec.js::tier3_lazy_load_fires_event_detail_request_on_machine_expand` | Tier 1->2->3 expand; Tier 3 lazy-loads only on machine expand |
| AC-5 | `TestApplyViewFilter` (omit-all + combined); `TestEquipmentDetailRoute` / `TestEventDetailRoute`; `test_api_contract.py::TestDowntimeSummaryShape`; `TestFilterDataBoundary` | filters apply in-memory, no Oracle re-query; omit-all unchanged; shape identical |
| AC-6 | `cd frontend && npm run css:check`; `downtime-analysis.spec.js::root_element_has_theme_downtime_analysis_class` | zero unscoped top-level rules; root has theme class |
| AC-7 | `cd frontend && npm test` (existing shared-ui component tests) | shared-ui tests pass unchanged |
| AC-8 | `MachineEventRows.test.ts::resolves rows from events wrapper key not bare array` / `empty events array renders empty-state...`; `TestFilterDataBoundary::test_event_detail_response_has_events_key` | Tier 3 resolves `events` key; empty renders empty-state |
| all gates | `pytest`; `cd frontend && npm run type-check && npm test && npm run css:check && npm run build`; `npx playwright test tests/playwright/downtime-analysis.spec.js`; `cdd-kit validate`; `cdd-kit gate downtime-analysis-page-redesign --strict` | all exit 0 (ci-gates.md §Required Gates / §Merge Eligibility) |

## Implementation Sequence (TDD-first)
1. Backend tests FIRST (failing): write `TestApplyViewFilter`, `TestEquipmentDetailRoute` / `TestEventDetailRoute` extensions, `TestFilterDataBoundary`, `TestDowntimeSummaryShape` per test-plan.md. Then implement IP-1 / IP-2 until they pass. Verify `contracts/CHANGELOG.md` `## [api 1.14.0]` (IP-4).
2. Frontend types + composable (IP-5), then component tests FIRST (failing): `StatusMachineJobTable.test.ts`, `MachineEventRows.test.ts`. Then build the two new components (IP-6) and chart wiring (IP-7) until tests pass.
3. `App.vue` restructure (IP-8): remove tabs, un-import retired views, wire state/handlers/components; extend Playwright spec and retire `view_toggle_chart_to_events_preserves_filter_state`; run E2E to green.
4. CSS changes (IP-9): scope all rules under `.theme-downtime-analysis`, remove `.view-tabs` / `.view-tab`, then `cd frontend && npm run build` and confirm `npm run css:check` passes.
5. Final gate pass: `cdd-kit validate` and `cdd-kit gate ... --strict`.

## Handoff Constraints

- Implementation agents must not infer missing requirements from chat history.
- Do not re-copy full design, test strategy, CI policy, or contract prose into this plan; follow the source pointers above.
- Tests are TDD-first: write the failing test before the production code for each unit.
- Route-forwarding tests use `mock.assert_called_once()` + `mock.call_args.kwargs[key] == <non-default>`; never `assert_called_once_with(...)` (CLAUDE.md Test Coverage Discipline).
- `TestApplyViewFilter` fixtures must include `big_category`, `status_types`, and `resource_id` columns or the filter silently no-ops and passes a wrong implementation (test-plan.md §Notes).
- Tier 3 cache key `${resource_id}|${status_type}` and the chart-emitted status label (UDT/SDT/EGT) must match exactly — a casing/whitespace mismatch yields a silent empty Tier 3 (design.md R4). Resolve rows from the `events` wrapper key (data-shape-contract.md §3.12.6, AC-8).
- All authored CSS scoped under `.theme-downtime-analysis`; `<Teleport to="body">` content (if any) needs a thin `.theme-downtime-analysis` wrapper per css-contract.md rule 4.4.
- Any shared-ui change must be additive; prefer standalone `StatusMachineJobTable.vue` (design.md R2, AC-7).
- If this plan omits a required file, behavior, contract, or test, stop and report `blocked`.
- Keep implementation within the file-level plan unless a Context Expansion Request is approved.

## Known Risks

- R1 (CSS bleed, low): new component CSS must be scoped; enforced by `npm run css:check` Rule 6. After editing `style.css`, `npm run build` is mandatory (app serves from `dist/`, not the Vite dev server).
- R2 (shared-ui blast radius, low): `DataTable` is consumed by 12+ apps; do not alter its prop/emit surface — build the three-tier table standalone.
- R3 (200-row equipment cap, low): equipment list loads in one page; if a wide date range yields >200 machines the list truncates silently. Pinned by `test_equipment_detail_row_count_within_page_size_cap`; status-group-scoped fetch is the documented future fallback (design.md DQ-2 / R3).
- R4 (Tier 3 key mismatch, low): silent-empty-table class — see Handoff Constraints; verify against route `success_response(events=...)`.
- R5 (retired E2E test): `view_toggle_chart_to_events_preserves_filter_state` must be removed before `no_tab_switcher_present_in_redesigned_layout` becomes the authoritative AC-3 gate (ci-gates.md §Notes).
