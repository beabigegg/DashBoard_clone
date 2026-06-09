---
change-id: resource-status-cross-filter
schema-version: 0.1.0
last-changed: 2026-06-09
risk: medium
tier: 1
---

# Test Plan — resource-status-cross-filter

## Acceptance Criteria → Test Mapping

| criterion id | test family | test file path | tier |
|---|---|---|---|
| AC-1 | integration | `frontend/tests/resource-status/App.cross-filter.test.ts` | 1 |
| AC-2 | unit | `frontend/tests/resource-status/useCrossFilter.test.ts` | 0 |
| AC-3 | unit | `frontend/tests/resource-status/useCrossFilter.test.ts` | 0 |
| AC-4 | unit + integration | `useCrossFilter.test.ts`, `App.cross-filter.test.ts` | 0 / 1 |
| AC-5 | regression | `frontend/tests/legacy/resource-status.test.js` | 0 |
| AC-6 | unit + regression | `useCrossFilter.test.ts`, `resource-status.test.js` | 0 |
| AC-7 | contract (lint) | `npm run css:check` Rule 6 | 0 |
| AC-8 | integration | `frontend/tests/resource-status/App.cross-filter.test.ts` | 1 |

## Test Families Required

unit, contract, integration, regression

---

### Unit — useCrossFilter composable
File: `frontend/tests/resource-status/useCrossFilter.test.ts`

- `initial_state_is_empty` — activeSelections is []; filteredEquipment equals allEquipment
- `select_ring_filters_by_workcenter_group_and_status` — `{group:'G1', status:'UDT'}` narrows filteredEquipment to matching rows only
- `and_intersection_two_active_selections` — ring=UDT AND heatmap=QFP returns rows satisfying both predicates
- `and_intersection_three_active_selections` — three simultaneous predicates all must hold
- `reclick_same_key_removes_selection` — second click on same chart+dimension removes entry; subset restored
- `clear_all_removes_every_selection` — clearAll() resets filteredEquipment to allEquipment
- `exclude_self_ring_dimension_unaffected_by_ring_selection` — ring chart's input set omits ring's own predicate; all ring values visible
- `exclude_self_heatmap_dimension_unaffected_by_heatmap_selection` — heatmap package list unaffected by heatmap selection
- `heatmap_null_packagegroupname_normalises_to_dash` — null/empty PACKAGEGROUPNAME treated as '—' in predicate (boundary from design risk)
- `matrix_dimension_via_composable` — matrix cell-filter produces same narrowing as old matrixFilter[] toggle
- `summary_card_status_dimension_via_composable` — summary-card status routes to status predicate in composable
- `alerts_resourceid_dimension_filters_to_single_resource` — Alerts row click; filteredEquipment contains only that RESOURCEID

### Unit — component click-emit wiring
File: `frontend/tests/resource-status/App.cross-filter.test.ts` (shallow-mount)

- `WorkcenterOuRings_emits_selection_on_echart_click` — VChart @click emits `{source:'ring', group, status}` with non-default values
- `OuHeatmap_emits_selection_on_cell_click` — cell click emits `{source:'heatmap', group, package}` with non-default values
- `MatrixSection_existing_cell_filter_emit_shape_unchanged` — emit shape identical to pre-change; handler routes to composable
- `MaintenanceAlerts_row_click_emits_selection_not_show_job` — selection emit is distinct from show-job emit

### Integration — App-level cross-filter orchestration
File: `frontend/tests/resource-status/App.cross-filter.test.ts` (mount with fixture data)

- `ring_click_UDT_narrows_grid_to_UDT_rows` — AC-1 single-chart narrowing
- `heatmap_click_QFP_narrows_ring_visible_rows` — selecting A narrows B
- `two_chart_selections_produce_and_intersection` — ring=UDT + heatmap=QFP; grid satisfies both
- `reclick_clears_one_dimension_restores_broader_subset` — partial clear after two selections
- `clear_all_button_shown_iff_active_selections_gt_0` — "清除全部" visibility tied to activeSelections length
- `selected_element_has_active_css_class` — active selection adds highlight class to chart element
- `esc_clears_selection_returns_focus_to_trigger` — ESC calls el.focus() after nextTick (AC-8)
- `filterbar_composes_with_cross_filter_independently` — FilterBar pkg_group and cross-filter both reduce grid (AC-5)

### Regression — existing resource-status tests
File: `frontend/tests/legacy/resource-status.test.js` (must pass without modification)

All 22 existing tests must pass. Coverage areas that must not regress:
- `normalizeStatus`, `resolveOuBadgeClass`, `getStatusDisplay` utility functions
- `MATRIX_STATUS_COLUMNS`, `OU_BADGE_THRESHOLDS`, `STATUS_AGGREGATION` constants
- `EquipmentCard` PACKAGEGROUPNAME show/hide
- `FilterBar` package-groups MultiSelect render and emit
- `MatrixSection` Package dimension column render and value isolation

## Out of Scope

- E2E / Playwright spec (deferred; no Chromium CI step added in this change)
- Visual dim/opacity affordance on non-selected elements (Phase 2, design D5)
- Backend API or contract-shape tests (payload unchanged; purely client-side)
- Property-based / fuzz testing of the intersection reducer
- Stress and soak testing (in-memory client-side filter; no load surface)

## Notes

Tier 0 = `npm run test` (Vitest unit, < 30 s); Tier 1 = same command, integration mount cases (still < 10 min).
`npm run css:check` Rule 6 is the AC-7 gate; runs as PR required lint step.
Exclude-self fixture must contain rows with mixed dimension values so both branches of the predicate are exercised.
Legacy test file must remain unmodified; if unification breaks a legacy assertion, fix the composable surface, not the test.
New tests must assert `activeSelections` / `filteredEquipment` from the composable surface — never assert internal ref names (`matrixFilter`, `summaryStatusFilter`).
