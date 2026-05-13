---
change-id: wip-hold-drilldown-filters
spec-version: 1
---

# Spec — wip-hold-drilldown-filters

## Problem

Engineers using the WIP-Overview report face three workflow gaps:

1. **Matrix drill-down loses the package dimension.** When an engineer clicks a matrix cell at row `ASSY-1` / column `QFN-8`, the WIP-Detail page opens filtered by `ASSY-1` only — showing all packages for that workcenter. The engineer must then manually re-filter by package, adding an extra step.

2. **Lot Details is missing Project Type.** The `Type` / `PJ_Type` field identifies the project category of a lot (e.g., standard, new-product introduction, qualification). It is available in the DB and in the individual lot-detail endpoint but absent from the lot-list view — engineers cannot see it without drilling further into each lot.

3. **WORKFLOW / BOP / FUNCTION filters are missing.** Engineers routinely filter WIP queries by workflow (process flow name), BOP (bill of process), and project function. These dimensions exist in the Oracle DB but are not exposed as filter options on any WIP or Hold-Overview page.

## What Changes

### 1. Matrix Cell Drill-Down (WIP-Overview → WIP-Detail)

Clicking a data cell in the Workcenter × Package Matrix sends BOTH the workcenter and package dimensions to WIP-Detail. The package is pre-populated in the FilterPanel on arrival. Clicking a row header (workcenter name) continues to drill by workcenter only, preserving existing behaviour. Active-cell highlight with toggle semantics is added, matching the Hold-Overview HoldMatrix UX.

### 2. Type Column in Lot Details (WIP-Detail)

A `Type` column sourced from `lot.pjType` is added immediately to the right of the `LOT ID` column in the Lot Details table. It is sortable. Null values render as `-`. The backend detail.sql and service layer are updated to include `PJ_TYPE` in the lot-list response.

### 3. WORKFLOW / BOP / FUNCTION Filters (WIP-Overview, WIP-Detail, Hold-Overview)

Three new MultiSelect filter fields — WORKFLOW (from `WORKFLOWNAME`), BOP (from `BOP`), and FUNCTION (from `PJ_FUNCTION`) — are added to the FilterPanel on all three pages. The filter-options endpoint is extended to return distinct values for each.

The filter layout is reorganised into a 3×3 grid replacing the former 3×2 layout:

| Row | Col 1 | Col 2 | Col 3 |
|---|---|---|---|
| 1 | WORKORDER | LOT ID | PACKAGE |
| 2 | WORKFLOW | BOP | TYPE |
| 3 | FUNCTION | Wafer LOT | Wafer Type |

Cross-filter behaviour (options narrow dynamically as other filters are set) is retained unchanged.

Since the FilterPanel component is already shared (hold-overview imports from wip-overview), updating the single `wip-overview/components/FilterPanel.vue` propagates to all three pages. Each page wires its own independent reactive state — no cross-page filter sync is introduced.

## Why This Approach

- **Shared FilterPanel re-use**: The existing architecture already imports FilterPanel from wip-overview into hold-overview. Extending one file propagates to both pages without code duplication or a new shared component.
- **Extend wip-navigation-state**: The existing `wip-navigation-state.ts` + sessionStorage pattern already handles cross-app navigation parameters. Adding `matrixPackage` to the interface follows the same pattern without new infrastructure.
- **Additive backend change**: All four new DB fields are already selected in the lot-detail SQL; extending `detail.sql` SELECT and the service filter logic avoids schema migration or new DB views.

## Out of Scope

- Cross-page filter state sync (user requested independent state per page)
- Hold-Detail filter changes (not mentioned in the request)
- HOLD data filter-options endpoint extension (hold-overview would reuse wip filter-options where applicable, or this can be deferred)
- echarts typing improvements (separate concern)
- TypeScript migration of wip-overview/wip-detail/hold-overview (completed in migrate-wip-hold-ts)
