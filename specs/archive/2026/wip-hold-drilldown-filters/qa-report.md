---
change-id: wip-hold-drilldown-filters
report-date: 2026-05-13
reviewer: qa-reviewer (automated)
verdict: approved-with-risk
---

# QA Report — wip-hold-drilldown-filters

## Verdict

**approved-with-risk**

All ten acceptance criteria are implemented correctly in source code and have meaningful test coverage. Two planned test files identified in the test-plan are absent (`wip-url-params.test.js`, `wip-matrix-drilldown.spec.js`), resulting in gaps for AC-9 (URL param pre-population) and the Playwright critical-journey gate for WIP matrix drilldown. The implementation is sound and the gaps are low-risk for merge, but they must be tracked as known deficiencies against the test-plan contract and the Playwright gate listed in ci-gates.md.

---

## AC-by-AC Findings

### AC-1: Cell click navigates with workcenter+package — PASS

`MatrixTable.vue` `onCellClick(workcenter, pkg)` emits `drilldown` with `{ workcenter, package: pkg }`. In `wip-overview/App.vue` `navigateToDetail()`, when both dimensions are present the router call includes `package` in the URL and `matrixPackage` is stored via `storeWipNavigationState`. `wip-detail/App.vue` `initializePage()` reads `navState.matrixPackage` and pre-populates `filters.package` when the package filter is still empty. Logic is correct end-to-end.

Test coverage: `MatrixTable.test.js` — "emits drilldown with { workcenter, package } payload" covers the emit; wip-navigation-state round-trip is covered implicitly by the implementation path. **PASS (unit)**.

### AC-2: Row-header click navigates workcenter-only — PASS

`onWorkcenterClick(workcenter)` emits `{ workcenter, package: null }`. `navigateToDetail()` sends only `workcenter` to the URL when `pkg` is empty. Test: "emits drilldown with { workcenter, package: null } on row header click" in `MatrixTable.test.js`. **PASS (unit)**.

### AC-3: Active-cell CSS class + toggle semantics — PASS

`isCellActive()` checks `filter.workcenter === workcenter && filter.package === pkg`. The template binds `:class="{ active: isCellActive(workcenter, pkg) }"`. Toggle-off is handled by `isSameFilter()` emitting `null`. Tests cover: active class applied to correct cell, not applied to other cells, toggle-off emits null for both cell and row. **PASS (unit)**.

### AC-4: Type column in LotTable, sortable, null→'-' — PASS

`LotTable.vue` header: `Type` `<th>` is at index 1 (immediately after `LOT ID`), wired to `toggleSort('pjType')`, with `aria-sort` and sort indicators. Cell: `{{ lot.pjType != null ? lot.pjType : '-' }}`. `useSortableTable` sorts by `pjType` key, so the column is sortable.

Tests in `LotDetailTable.test.js`: position (index LOT ID + 1), value rendering, null→'-', undefined→'-', clickable with sort indicators, sort order correctness, all-null crash resistance. **PASS (unit)**.

### AC-5: 9-field 3×3 FilterPanel on all three pages — PASS

`wip-overview/components/FilterPanel.vue` declares `fields` array with 9 entries in the correct 3×3 order (WORKORDER, LOT ID, PACKAGE / WORKFLOW, BOP, TYPE / FUNCTION, Wafer LOT, Wafer Type). `wip-detail/components/FilterPanel.vue` has an independent but identical 9-field definition with the same order. `hold-overview/App.vue` imports from `../wip-overview/components/FilterPanel.vue` directly.

Tests in `FilterPanel.test.js`: `.filter-group` count = 9, label presence (WORKFLOW, BOP, FUNCTION), label order across all 9 positions. **PASS (unit)**.

Note: `FilterPanel.test.js` targets `wip-overview/components/FilterPanel.vue`. `hold-overview` re-uses the same component, so that page gets the same coverage. `wip-detail` has a local `FilterPanel.vue` that is not separately Vitest-tested for field count/order, but a visual inspection confirms it is identical in structure. This is a minor coverage gap but not an AC failure.

### AC-6: workflow/bop/pj_function params filter backend correctly — PASS

`wip_routes.py` extracts `workflow`, `bop`, `pj_function` from request args on all four WIP endpoints (`/api/wip/overview/summary`, `/api/wip/overview/matrix`, `/api/wip/detail/<wc>`, `/api/wip/meta/filter-options`) and passes them as keyword args to the service layer. `wip_service.py` applies `WORKFLOWNAME`, `BOP`, `PJ_FUNCTION` column conditions in both the cache-path and Oracle-fallback path for both summary and detail.

Tests in `test_wip_routes.py`: `test_summary_forwards_workflow_bop_pj_function`, `test_matrix_forwards_workflow_bop_pj_function`, `test_detail_forwards_workflow_bop_pj_function`, plus `test_passes_new_filter_params` for filter-options. **PASS (backend unit)**.

### AC-7: filter-options returns workflows/bops/pjFunctions arrays — PASS

`wip_service.py` populates `workflows`, `bops`, `pjFunctions` keys in the filter-options response for both cache path (line 2098–2100, 2284–2286) and Oracle fallback path (line 2323–2325). Route passes them through unchanged.

Tests: `test_filter_options_includes_new_keys` asserts all three keys are present with non-empty values; `test_returns_success_with_options` asserts their presence in the 200 response. **PASS (backend unit)**.

### AC-8: No cross-page state leak between hold-overview and wip-overview — PARTIAL PASS

Architecture analysis: `hold-overview/App.vue` maintains its own `filters` reactive object (`workflow`, `bop`, `pjFunction` all initialised to `[]`) that is entirely independent of `wip-overview/App.vue` state. No shared module-level state exists between the two apps (they are separate Vite entry points / SPAs). The `wip-navigation-state` sessionStorage key is consumed-on-read (`sessionStorage.removeItem` immediately after `getItem`), so it cannot leak from hold-overview to wip-overview.

The test-plan called for a Vitest test: "hold-overview WORKFLOW selection does not propagate to wip FilterPanel state". This test is **absent** — it was not added to `FilterPanel.test.js`. However, the architecture inherently prevents the leak (separate app instances, no shared reactive state), so this is a documentation gap, not a functional defect. **PASS (architectural); test coverage gap**.

### AC-9: URL param pre-population (workflow=X&bop=Y&pj_function=Z) — IMPLEMENTED, NOT TESTED IN ISOLATION

Both `wip-overview/App.vue` `initializePage()` and `wip-detail/App.vue` `initializePage()` call `parseCsvParam('workflow')`, `parseCsvParam('bop')`, `parseCsvParam('pj_function')` in the URL-fallback branch. `hold-overview/App.vue` also reads these three params in `initializePage()` via `parseCsvParam`.

The test-plan specified a new file `frontend/tests/validation/wip-url-params.test.js` covering these four cases. **This file does not exist.** AC-9 is not covered by automated tests. The implementation is correct by code inspection, but the pre-merge gate is incomplete.

**Risk: LOW** — the URL param reading pattern is identical to the existing `workorder`/`lotid`/`package` params which are proven by existing code. The risk is regression detection, not correctness.

### AC-10: pjType in lot rows for Redis-cache and Oracle-fallback paths; null not absent — PASS

`wip_service.py` line 1680: cache path includes `'pjType': _safe_value(row.get('PJ_TYPE'))`. Line 1887: Oracle fallback path includes `'pjType': _safe_value(row['PJ_TYPE']) if 'PJ_TYPE' in row.index else None`. The key is always present (None when absent from DB, not omitted).

Test `test_pj_type_appears_in_lot_rows` in `test_wip_routes.py` asserts: `pjType` key present, value `'PJA'` for non-null, value `None` (not absent) for null. This test validates the route pass-through; the cache/Oracle path distinction is not mocked separately but the service paths both set the key. **PASS (backend unit)**.

---

## Gate Coverage Assessment

| Gate | Status | Notes |
|---|---|---|
| Vitest 295/295 | Confirmed in ci-gates.md | 29 test files, 25 new tests (2 new files: MatrixTable.test.js, LotDetailTable.test.js) |
| type-check 0 errors | Confirmed in ci-gates.md | |
| css:check 0 errors | Confirmed in ci-gates.md | 47 pre-existing warnings unchanged |
| cdd-kit validate | Confirmed in ci-gates.md | 141 endpoints pass |
| pytest test_wip_routes.py 40/40 | Confirmed in ci-gates.md | |
| playwright-critical-journeys | **GAP** | `hold-overview.spec.js` and `reject-history.spec.js` exist but `wip-matrix-drilldown.spec.js` listed in test-plan is absent |
| playwright-resilience | Not assessed (out of scope) | |
| playwright-data-boundary | Not assessed (out of scope) | |

---

## Deficiency Summary

Two deficiencies against the test-plan contract:

1. **`frontend/tests/validation/wip-url-params.test.js` absent** (AC-9 test coverage). The test-plan requires four test cases covering `workflow`, `bop`, `pj_function` URL param pre-population. Implementation is correct by inspection; risk is regression detection only.

2. **`frontend/tests/playwright/wip-matrix-drilldown.spec.js` absent** (Playwright critical-journey for WIP matrix cell drilldown). The ci-gates.md lists `playwright-critical-journeys` as a required pre-merge gate; the test-plan lists this spec as a required new Playwright test. The existing `hold-overview.spec.js` guards the hold-overview regression, but the new WIP cell-drilldown-to-detail navigation path is not covered by any E2E test.

---

## Implementation Quality Notes

- `wip-navigation-state.ts` correctly gates `matrixPackage` storage to a string value and degrades gracefully on `sessionStorage` unavailability.
- `LotTable.vue` null-guard `lot.pjType != null ? lot.pjType : '-'` is correct (catches both `null` and `undefined`).
- `FilterPanel.vue` (wip-overview) uses the same `fields` pattern as `FilterPanel.vue` (wip-detail); both independently implement the 9-field 3×3 layout without shared state.
- `wip-derive.ts` `buildWipOverviewQueryParams` emits `pj_function` as the URL/body key (not `pjFunction`), matching the backend expectation.
- `hold-overview/App.vue` `updateUrlState()` serialises all three new filters to URL correctly (`workflow`, `bop`, `pj_function`), and `initializePage()` reads them back via `parseCsvParam('pj_function')`.

---

## Conditions for Unconditional Approval

The change may be upgraded to **approved** if either:

(a) Both missing test files are added before merge: `wip-url-params.test.js` (AC-9 unit) and `wip-matrix-drilldown.spec.js` (Playwright); or

(b) The team explicitly accepts and documents the test-plan divergence (update `test-plan.md` to mark these as deferred with a follow-up issue reference, and confirm that the playwright gate will pass without the new spec file).

The implementation itself is correct and the missing tests do not indicate a functional defect.
