---
change-id: wip-hold-drilldown-filters
recorded-date: 2026-05-13
---

# Current Behavior — wip-hold-drilldown-filters

## WIP-Overview Matrix Drill-Down (Before)

The Workcenter × Package Matrix currently emits only a `workcenter` string when any cell or row header is clicked (`MatrixTable.vue` `emit('drilldown', workcenter)`). Clicking any cell in a workcenter row navigates to WIP-Detail with only `workcenter` as the URL/nav-state parameter — the package dimension is discarded. There is no active-cell highlight state; the entire row responds to any click uniformly.

## WIP-Detail Lot Details Table (Before)

The `LotTable.vue` renders these columns: LOT ID, Status (tag), Equipment, WIP Status, Package, Specs / QTY. There is no Type (PJ_Type) column. The `pjType` field is not included in the `/api/wip/detail/<workcenter>` API response or the `detail.sql` SELECT.

## FilterPanel Layout (Before — applies to wip-overview, wip-detail, hold-overview)

The FilterPanel renders **6 filter fields** (`FilterPanel.test.js` asserts `.filter-group` count = 6):

| Row | Col 1 | Col 2 |
|---|---|---|
| 1 | WORKORDER | LOT ID |
| 2 | PACKAGE | TYPE |
| 3 | WAFER LOT | WAFER TYPE |

(Approximate layout — 3 rows × 2 columns or equivalent.)

Fields present: WORKORDER (`workorder`), LOT ID (`lotid`), PACKAGE (`package`), TYPE (`type` — from TYPENAME/lot type, not PJ_Type), Wafer LOT (`firstname`), Wafer Type (`wafer_desc`).

The FilterPanel component is **shared**: `hold-overview/App.vue` imports `FilterPanel` directly from `'../wip-overview/components/FilterPanel.vue'`. There is no separate hold-overview FilterPanel file.

## Backend Filter Options (Before)

`GET /api/wip/meta/filter-options` returns 6 arrays:
- `workorders`, `lotids`, `packages`, `types`, `firstnames`, `waferdescs`

WORKFLOWNAME, BOP, and PJ_FUNCTION are not included in this response.

## Backend WIP Detail (Before)

`/api/wip/detail/<workcenter>` response `lots` items include:
- `lotId`, `status`, `equipment`, `wipStatus`, `package`, `specName`, `qty`

`pjType` is absent from all lot list responses; it is only available from `/api/wip/lot/<lotid>` (individual lot detail endpoint).

## Hold-Overview Matrix Drill-Down (Reference — working correctly)

`HoldMatrix.vue` in hold-overview already supports cell-level selection: clicking a cell emits `{workcenter, package}`, clicking a row header emits `{workcenter}`, clicking a column header emits `{package}`. Active-cell state is tracked via `activeCell` reactive with toggle semantics. WIP-Overview MatrixTable does not yet match this behaviour.
