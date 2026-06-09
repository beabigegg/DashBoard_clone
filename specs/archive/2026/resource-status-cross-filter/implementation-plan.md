---
change-id: resource-status-cross-filter
schema-version: 0.1.0
last-changed: 2026-06-09
---

# Implementation Plan: resource-status-cross-filter

## Objective

Deliver a single client-side cross-filter orchestrator (`useCrossFilter.ts`) for the resource-status page that holds all in-memory selection state with AND-intersection semantics, and wire 4 chart contributors (WorkcenterOuRings, OuHeatmap, MatrixSection, MaintenanceAlerts) plus SummaryCardGroup and EquipmentGrid to it. This replaces the parallel `matrixFilter[]` / `summaryStatusFilter` refs in `App.vue` (design D2). No backend change: `/api/resource/status` payload is unchanged; all filtering is in-memory. Owner: `frontend-engineer`.

## Execution Scope

### In Scope
- New composable `frontend/src/resource-status/composables/useCrossFilter.ts`: selection store, AND-intersection reducer, exclude-self input-set builder, toggle/clearAll, active-filter label, null-package normalisation.
- Unify `matrixFilter[]` + `summaryStatusFilter` state in `App.vue` into the composable (design D2) and re-bind all charts + EquipmentGrid to its output.
- Click-to-select wiring on WorkcenterOuRings (VChart `@click`), OuHeatmap (cell `@click`), MaintenanceAlerts (row `@click`); re-point MatrixSection + SummaryCard handlers (emit shapes unchanged).
- Clear-on-reclick, clear-all control, and ESC-clears-with-focus-return (design D3, AC-4/AC-8).
- `.theme-resource`-scoped selection-highlight + clear-control CSS in existing `style.css`.
- Contract updates: business-rules cross-filter rule, css-contract scoping note, CHANGELOG version entries.
- New tests: `useCrossFilter.test.ts`, `App.cross-filter.test.ts` (TDD, written first).

### Out of Scope
- Phase 2 dim/opacity affordance on non-selected elements (design D5 — explicitly forbidden this change).
- Any change to `/api/resource/status` request/response shape; no backend, SQL, service, or worker edits.
- Any change to top FilterBar / `useFilterOrchestrator` behavior (must keep composing independently — AC-5).
- Modifying `frontend/tests/legacy/resource-status.test.js` (must pass unmodified — test-plan §Regression).
- New authored `.css` source file or `css-inventory.md` update.
- Altering MatrixSection's `cell-filter` emit shape or the `MatrixFilter` interface.
- E2E / Playwright spec; CI workflow edits.

## Required Changes

| id | area | required action | owner agent |
|---|---|---|---|
| IP-1 | tests (TDD) | Create `frontend/tests/resource-status/useCrossFilter.test.ts` (RED) per test-plan §Unit — composable | frontend-engineer |
| IP-2 | tests (TDD) | Create `frontend/tests/resource-status/App.cross-filter.test.ts` (RED) per test-plan §Unit-wiring + §Integration | frontend-engineer |
| IP-3 | composable | Implement `composables/useCrossFilter.ts` (state, AND-intersection, exclude-self, toggle/clearAll, null-package norm) | frontend-engineer |
| IP-4 | App.vue | Delete 7 legacy symbols; re-derive all bindings from composable; wire clear-all + ESC | frontend-engineer |
| IP-5 | WorkcenterOuRings | Add `<VChart>` `@click` emit + `:selection` highlight (design D4) | frontend-engineer |
| IP-6 | OuHeatmap | Add cell `@click` emit + null `'—'` normalisation + active-cell highlight | frontend-engineer |
| IP-7 | MatrixSection | Re-point handler to composable; keep `cell-filter` emit + `MatrixFilter` shape unchanged | frontend-engineer |
| IP-8 | MaintenanceAlerts | Add row `@click` selection emit distinct from `show-job`; active-row highlight | frontend-engineer |
| IP-9 | EquipmentGrid | Consume intersection subset; keep `clear-filter` emit (minimal) | frontend-engineer |
| IP-10 | CSS | Add `.theme-resource`-scoped selection/clear rules in `style.css`; pass `css:check` Rule 6 | frontend-engineer |
| IP-11 | contracts | Update business-rules + css-contract; add version entries to `contracts/CHANGELOG.md` only | frontend-engineer |

## Source Artifact Pointers

| source | relevant pointer | used for |
|---|---|---|
| design.md | D1 (intersection), D2 (unification), D3 (clear/ESC), D4 (ECharts), D5 (no dim) | implementation constraints |
| design.md | ## Open Risks (exclude-self, null package, legacy coupling) | edge-case verification |
| test-plan.md | §Unit / §Integration / §Regression | tests to write/run |
| test-plan.md | §Notes | composable-surface assertion rule; fixture discipline |
| ci-gates.md | ## Required Gates for This Change | verification commands |
| change-classification.md | Inferred Acceptance Criteria AC-1..AC-8 | acceptance mapping |
| contracts/business/business-rules.md | ## Resource Rules (L105) | new business rule location |
| contracts/css/css-contract.md | ## Resource-Status UI Surface Rules (L113) | CSS scoping rule + correct `.theme-resource` root |

## File-Level Plan

| path or glob | action | notes |
|---|---|---|
| `frontend/tests/resource-status/useCrossFilter.test.ts` | create (FIRST) | failing unit tests per test-plan §Unit — composable. Assert composable surface, not internal refs. |
| `frontend/tests/resource-status/App.cross-filter.test.ts` | create (FIRST) | failing wiring + integration tests per test-plan §Unit-wiring + §Integration. |
| `frontend/src/resource-status/composables/useCrossFilter.ts` | create | ordered string-keyed selection store; AND-intersection reducer; exclude-self input-set builder; toggle/clearAll; active-filter label; null-package `'—'` norm. Dimension descriptors per design D1. Exposes `activeSelections` + `filteredEquipment`. |
| `frontend/src/resource-status/App.vue` | edit | Remove `matrixFilter` (L162), `summaryStatusFilter` (L163), `displayedEquipment` (L387), `activeFilterText` (L400), `applyMatrixFilter` (L423), `clearAllEquipmentFilters` (L432), `toggleSummaryStatus` (L437). Re-point: reset on load (L335-336), `@cell-filter` (L634), SummaryCard `:active`/`@click` (L605-606), EquipmentGrid `v-if`/`:equipment`/`:active-filter-text`/`@clear-filter` (L638-641), and the 4 charts at `:equipment="allEquipment"` (L622/L624/L626/L629) → composable subset / exclude-self subset. |
| `frontend/src/resource-status/components/WorkcenterOuRings.vue` | edit | Add `@click` on `<VChart>` (L104) → emit `{source:'ring', group, status}` from `params.name`/`params.data` (design D4 — no `chart.on()`/`onMounted`). Add `:selection` prop for highlight. |
| `frontend/src/resource-status/components/OuHeatmap.vue` | edit | Add native `@click` on `<td class="heatmap-cell">` (L102-108) → emit `{source:'heatmap', group: row.group, package}`. Normalise null/empty PACKAGEGROUPNAME to `'—'` exactly as grouping at L44. Active-cell highlight. |
| `frontend/src/resource-status/components/MatrixSection.vue` | edit (minimal) | Keep `cell-filter` emit (L130) + `MatrixFilter` interface (L46) unchanged; keep `:matrix-filter` row highlight (L277-298). Only App-side handler re-points. |
| `frontend/src/resource-status/components/MaintenanceAlerts.vue` | edit | Add alert-row `@click` (near L110) → emit `{source:'alert', resource: item.eq.RESOURCEID}`, distinct from `show-job` (L26/L31). Active-row highlight. |
| `frontend/src/resource-status/components/EquipmentGrid.vue` | edit (minimal) | Consume intersection via `:equipment`; keep `clear-filter` emit (L52-53, L69). |
| `frontend/src/resource-status/style.css` | edit | Add `.theme-resource`-scoped selection-highlight + clear-control rules. Scope is `.theme-resource` (see Known Risks). |
| `contracts/business/business-rules.md` | edit | Add cross-filter rule under `## Resource Rules` (L105). |
| `contracts/css/css-contract.md` | edit | Extend `## Resource-Status UI Surface Rules` (L113) with selection-highlight scoping note. |
| `contracts/CHANGELOG.md` | edit | Add `## [business x.y.z]` and `## [css x.y.z]` entries HERE ONLY (CLAUDE.md cdd-kit note). |

## Contract Updates

- API: none (payload unchanged).
- CSS/UI: `contracts/css/css-contract.md` `## Resource-Status UI Surface Rules` (L113) — add that selection-highlight + clear-control styles are scoped under `.theme-resource` and pass `css:check` Rule 6 (§37 / Rule 4.2). Reference Rule 4.4 (L45) only if any selection element is teleported (not expected). No `css-inventory.md` update (no new `.css` file).
- Env: none.
- Data shape: none.
- Business logic: `contracts/business/business-rules.md` `## Resource Rules` (L105) — add cross-filter intersection rule: AND-intersection across charts, exclude-self ("selecting A narrows B but not A"), clear-on-reclick/ESC (design D1/D3; AC-2/AC-3/AC-4). State normatively; do not copy design prose.
- CI/CD: none. All version entries go to `contracts/CHANGELOG.md` only (`cdd-kit validate --versions` scans only that file).

## Test Execution Plan

| acceptance criterion | test file / command | expected signal |
|---|---|---|
| AC-1 | `App.cross-filter.test.ts` via `cd frontend && npm test` | single-chart click narrows grid to matching subset |
| AC-2 | `useCrossFilter.test.ts` via `npm test` | two/three active selections → AND-intersection rows |
| AC-3 | `useCrossFilter.test.ts` via `npm test` | exclude-self: chart's own dimension still shows all values |
| AC-4 | `useCrossFilter.test.ts` + `App.cross-filter.test.ts` via `npm test` | reclick/clearAll/ESC removes dimension; subset restored |
| AC-5 | `frontend/tests/legacy/resource-status.test.js` via `npm run test:legacy` | FilterBar + cross-filter compose; legacy 22 tests pass unmodified |
| AC-6 | `useCrossFilter.test.ts` + `resource-status.test.js` via `npm test` / `npm run test:legacy` | matrix + summary-card dimensions narrow identically post-unification |
| AC-7 | `cd frontend && npm run css:check` | Rule 6: zero unscoped top-level rules |
| AC-8 | `App.cross-filter.test.ts` via `npm test` | active highlight class present; ESC calls `el.focus()` after `nextTick` |

Order: (1) `npm test` RED before impl, GREEN after; (2) `npm run test:legacy` GREEN throughout; (3) `npm run css:check`; (4) `npm run type-check` (informational, ci-gates row 4). New tests assert composable surface (`activeSelections`/`filteredEquipment`), never internal ref names (test-plan §Notes). Exclude-self + null-package boundary fixtures required (test-plan §Unit, §Notes).

## Implementation Order

1. Write `useCrossFilter.test.ts` (test-plan §Unit — composable) — confirm RED.
2. Write `App.cross-filter.test.ts` (test-plan §Unit-wiring + §Integration) — confirm RED.
3. Implement `useCrossFilter.ts` (state, AND-intersection, exclude-self, toggle/clearAll, active label, null-package norm). Run `npm test` until §Unit composable cases pass.
4. Wire `MatrixSection` (re-point App handler; emit shape unchanged) + `SummaryCardGroup` (status dimension); re-prove via legacy + new tests.
5. Wire `WorkcenterOuRings` (`<VChart>` `@click`, `:selection`) and `OuHeatmap` (cell `@click`, null `'—'` norm, active-cell highlight).
6. Wire `MaintenanceAlerts` row `@click` (distinct from `show-job`); confirm `EquipmentGrid` consumes intersection + `clear-filter`.
7. Refactor `App.vue`: delete the 7 legacy symbols; re-bind charts to `filteredEquipment`/exclude-self subsets; wire clear-all + ESC handler. Run `npm test` + `npm run test:legacy` until GREEN.
8. Add `.theme-resource`-scoped selection/clear CSS to `style.css`; run `npm run css:check` until clean.
9. Update `business-rules.md` (Resource Rules) + `css-contract.md` (Resource-Status UI Surface Rules); add both version entries to `contracts/CHANGELOG.md`.
10. Run `npm test`, `npm run test:legacy`, `npm run css:check`, `npm run type-check`; then `cdd-kit validate`.

## Constraints

- **TDD order is mandatory**: write `useCrossFilter.test.ts` and `App.cross-filter.test.ts` (RED) before implementing the composable and wiring. Do not implement first.
- **D2 unification, not parallel state**: delete exactly `matrixFilter` (L162), `summaryStatusFilter` (L163), `displayedEquipment` (L387), `activeFilterText` (L400), `applyMatrixFilter` (L423), `clearAllEquipmentFilters` (L432), `toggleSummaryStatus` (L437). All downstream bindings re-derive from the composable. Leave none of these in place.
- **D1 exclude-self**: a chart's own input set omits its contributed dimension (Ring→`{WORKCENTER_GROUP,status}`, Heatmap→`{WORKCENTER_GROUP,PACKAGEGROUPNAME}`, Matrix→`{WORKCENTER_GROUP,status,family?,resource?}`, Alerts→`{RESOURCEID}`, SummaryCard→`{status}`). AC-3 must hold.
- **D4 ECharts binding**: bind `@click` on `<VChart>` (WorkcenterOuRings L104). No `chart.on()`, `onMounted`, `onUnmounted`, or ECharts `select` mode.
- **Heatmap null boundary**: normalise `PACKAGEGROUPNAME` to `'—'` with the SAME expression as OuHeatmap grouping at L44 in both the cell-click emit and the composable predicate.
- **MatrixSection emit/`MatrixFilter` shape frozen**: do not alter `cell-filter` signature (L130) or the `MatrixFilter` interface (L46).
- **shared-ui additive-only**: `SummaryCard`/`SummaryCardGroup` are in `frontend/src/shared-ui/components/`. Prefer routing selection through App.vue handlers without touching shared-ui surfaces. If a prop/emit must change, make it additive (optional) and grep all consumers first (CLAUDE.md shared-ui note).
- **ESC focus return** (design D3 / CLAUDE.md Accessibility): ESC on a focused selected element clears that element's selection and calls `nextTick(() => el.focus())`; ESC with no focused selection is a no-op.
- **Contract versions in `contracts/CHANGELOG.md` only.**

## Handoff Constraints

- Implementation agents must not infer missing requirements from chat history.
- Do not re-copy full design, test strategy, CI policy, or contract prose into this plan; follow the source pointers above.
- If this plan omits a required file, behavior, contract, or test, stop and report `blocked`.
- Keep implementation within the file-level plan unless a Context Expansion Request is approved.

## Known Risks

- **Scope-root mismatch**: the scope root is `.theme-resource` (confirmed in existing `frontend/src/resource-status/style.css` and css-contract L113-123), NOT `.theme-resource-status`. Authoring rules under `.theme-resource-status` would silently fail to apply. Use `.theme-resource`.
- **Exclude-self regression**: a reducer that applies all selections uniformly hides a chart's own dimension values; the per-chart input set must omit the chart's own predicate (AC-3).
- **Heatmap null divergence**: if cell-click emit and composable predicate normalise `PACKAGEGROUPNAME` differently, null/'—' rows silently drop from the intersection.
- **Legacy test coupling**: if a legacy assertion references the old `matrixFilter` ref, fix the composable surface to satisfy intent — do not modify the legacy test (test-plan §Notes).
