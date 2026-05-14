---
change-id: hold-history-detail-flat-table
schema-version: 0.1.0
last-changed: 2026-05-14
risk: low
tier: 3
---

# Test Plan: hold-history-detail-flat-table

## Acceptance Criteria → Test Mapping

| criterion id | test family | test file path | tier |
|---|---|---|---|
| AC-1 | visual (playwright) | `frontend/tests/playwright/hold-history-flat-table.spec.js` (new) | 3 |
| AC-1 | e2e (API smoke) | `tests/e2e/test_hold_history_e2e.py` (existing — no selector changes needed; API-only) | 3 |
| AC-2 | visual (playwright) | `frontend/tests/playwright/hold-overview.spec.js` (update selector in "renders the Lot Details data table" test) | 3 |
| AC-2 | e2e (API smoke) | `tests/e2e/test_hold_overview_e2e.py` (existing — no selector changes needed; API-only) | 3 |
| AC-3 | visual (playwright) | `frontend/tests/playwright/hold-history-flat-table.spec.js` (column presence + pagination control) | 3 |
| AC-3 | visual (playwright) | `frontend/tests/playwright/hold-overview.spec.js` (column presence in lot details table) | 3 |
| AC-4 | e2e (API smoke) | `tests/e2e/test_hold_history_e2e.py` (existing — payload shape already asserted) | 3 |
| AC-4 | e2e (API smoke) | `tests/e2e/test_hold_overview_e2e.py` (existing — `lots` + `pagination` keys asserted) | 3 |
| AC-5 | visual (playwright) | `frontend/tests/playwright/hold-overview.spec.js` (existing hold-matrix table still renders) | 3 |
| AC-6 | lint / type | `npm run css:check` + `npm run type-check` (CI gate commands — no new test file) | 3 |
| AC-6 | unit (validation) | `frontend/tests/validation/useHoldOverview.validation.test.js` (existing — no changes needed) | 2 |

## Test Families Required

- visual (playwright)
- e2e (API smoke — existing, no structural changes)
- lint / type (css:check, type-check)

## New Test File

`frontend/tests/playwright/hold-history-flat-table.spec.js`

Purpose: verify the Hold / Release 明細 section in hold-history renders as a single flat table (no nested card wrappers), all expected columns are present, and pagination controls appear when data spans multiple pages.

Tests to include (one assertion per test, no bodies here):
1. `renders the Hold/Release 明細 section as a single top-level card` — assert exactly one `.ui-card` wrapping the detail table, no nested `.ui-card` inside it
2. `Hold/Release 明細 table contains expected columns` — assert column headers: Lot ID, WorkOrder, Product, 站別, Hold Reason, 數量, Hold 時間, Release 時間, 時長(hr)
3. `Hold/Release 明細 DataTable is a direct child of card-body` — assert `.ui-card .card-body > .data-table-scroll, .ui-card .card-body > [class*="data-table"]` exists without intermediate `.ui-card` ancestor
4. `Hold/Release 明細 pagination control renders` — trigger a date query that returns >20 rows; assert pagination buttons are visible

## Selector Update Required

`frontend/tests/playwright/hold-overview.spec.js` — test `'renders the Lot Details data table'`:

Current: asserts `tables.count() >= 1` (passes trivially from the matrix table).
After refactor: add a named-section locator check — assert the section with heading "Hold Lot Details" contains a `table` element directly inside `.card-body`, without an intermediate inner `.ui-card`.

No changes required to:
- `tests/e2e/test_hold_history_e2e.py` — all assertions are API/JSON only
- `tests/e2e/test_hold_overview_e2e.py` — all assertions are API/JSON only
- `frontend/tests/validation/useHoldOverview.validation.test.js` — tests guardResponse/assertShape logic; no DOM selectors

## Out of Scope

- DataTable.vue unit tests — component is not modified
- hold-detail and wip-detail pages — read-only reference; no changes to those apps
- Backend route and service tests — API payloads confirmed flat; no backend modification
- Resilience, monkey, stress, soak tests — not triggered by a CSS/template refactor
- hold-matrix section visual regression — HoldMatrix.vue is unchanged

## Notes

The existing `hold-overview.spec.js` pareto drilldown test (`clicking a pareto drilldown item navigates to hold-detail`) is unaffected — it interacts with `.pareto-section`, not the Lot Details table. No update needed.
