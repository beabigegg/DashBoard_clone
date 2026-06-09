# Archive — resource-status-cross-filter

> **Cold Data Warning**: This archive is historical evidence. Current requirements live in `contracts/` and active project guidance.

## Change Summary

Added PowerBI-style cross-chart filtering to the 設備及時概況 (resource-status) page. Engineers can now click any chart element (Ring segment, Heatmap cell, Matrix row, Alert item) to filter all other charts and the EquipmentGrid to the matching equipment subset. Multiple active selections are AND-intersected so engineers can drill into e.g. "UDT ∧ QFP" without touching the top FilterBar. The existing `matrixFilter[]` and `summaryStatusFilter` refs were unified into a new generic `useCrossFilter<T>` composable, eliminating the parallel-reducer ambiguity.

## Final Behavior

- Clicking a chart element adds a typed selection to `useCrossFilter`; `filteredData` (AND-intersection) is propagated to all charts and EquipmentGrid.
- Re-clicking toggles off the selection; ESC clears all and returns focus to the last clicked trigger (`lastClickedTrigger` + `nextTick(() => trigger.focus())`).
- A "清除全部篩選" button is visible whenever `hasActiveSelections` is true.
- Each chart's own selectable option set is derived from `getInputForChart(source)` (exclude-self), so selecting Ring "UDT" does not collapse the Ring's own visible groups.
- Heatmap cells and Alert rows are keyboard-accessible (`tabindex="0"`, `role="button"`, `aria-pressed`, Enter/Space).
- All new CSS is scoped under `.theme-resource` (confirmed scope root).

## Final Contracts Updated

- `contracts/business/business-rules.md` — added RS-CF-01 (cross-filter AND-intersection, exclude-self, re-click toggle, ESC focus-return, client-side only); schema-version → 1.14.0
- `contracts/css/css-contract.md` — added cross-filter scoping note confirming `.theme-resource`; schema-version → 1.7.0
- `contracts/CHANGELOG.md` — entries for `[business 1.14.0]` and `[css 1.7.0]`

## Final Tests Added / Updated

- `frontend/tests/resource-status/useCrossFilter.test.ts` (NEW) — 12 unit tests: initial state, add/remove/toggle, AND-intersection, exclude-self, null/`'—'` normalisation, empty intersection, matrixFilter-compatible dimensions
- `frontend/tests/resource-status/App.cross-filter.test.ts` (NEW) — 12 integration/wiring tests: ring click filters others, AND-intersection, re-click deselects, ESC focus-return (vi.spyOn on mock trigger), clear-all button, FilterBar compose, legacy matrixFilter dimensions via composable
- `frontend/vitest.config.js` (MODIFIED) — added `tests/**/*.test.ts` to `include` to pick up new test files
- `frontend/tests/legacy/resource-status.test.js` — unchanged and passing (no matrixFilter/summaryStatusFilter assertions)

## Final CI/CD Gates

| gate | tier | status |
|---|---|---|
| frontend-unit | 1 (required) | green (CI confirmed) |
| css-governance | 1 (required) | green (CI confirmed) |
| frontend-legacy | 1 (required) | green (CI confirmed) |
| frontend-type-check | 2 (informational) | green |

No new gates or workflow changes needed. Tests discovered via existing Vitest glob in `frontend-tests.yml`.

## Production Reality Findings

- **CSS scope root discrepancy**: `change-classification.md` AC-7 cited `.theme-resource-status` as the scope root, but the actual root in `style.css` is `.theme-resource`. Caught by `implementation-planner` during Allowed Paths preflight; frontend-engineer used the correct root.
- **`lastClickedTrigger` focus-return pattern**: ui-ux-reviewer flagged 3 close paths (ESC, re-click, clear-all button DOM removal) that dropped keyboard focus. Added `lastClickedTrigger = ref<HTMLElement|null>(null)` + `captureLastTrigger()` + `nextTick(() => trigger?.focus())` at all three close paths. This extends the CLAUDE.md Accessibility Notes combobox pattern to click-to-filter affordances.
- **vitest.config.js `include` gap**: `tests/**/*.test.ts` was not in the `include` array, so test files placed outside `src/` were not discovered. Fixed as part of implementation.

## Lessons Promoted to Standards

1. **vue-echarts `@click` binding** → promoted to `CLAUDE.md` §Vue-ECharts Notes  
   Evidence: `design.md` D4; `agent-log/architecture-reviewer.yml` decision-summary  
   Rule: use `<VChart @click="handler">` template binding; do not use `echartsInstance.on('click')` or ECharts `select` mode.

2. **resource-status CSS scope root (`.theme-resource` vs `.theme-resource-status`)** → not promoted (do-not-promote)  
   Rationale: already enforced by `contracts/css/css-contract.md` L113–L123; CLAUDE.md general rule covers it. One isolated near-miss does not meet the promotion bar.

## Follow-up Work

- **Phase 2 dim effect** (deferred): visual dimming of non-selected elements was explicitly out of scope (design.md D5). If added, requires ui-ux-reviewer visual-review-report.
- **Playwright E2E spec** (deferred): a Playwright spec covering the full cross-filter user journey. If added, requires `npx playwright install --with-deps chromium` in `.github/workflows/frontend-tests.yml` before the test step (per CLAUDE.md CI Workflow Notes).
