---
change-id: reject-material-flat-table
schema-version: 0.1.0
last-changed: 2026-05-14
risk: low
tier: 3
---

# Test Plan: reject-material-flat-table

## Acceptance Criteria → Test Mapping

| criterion id | test family | test name | file path | tier |
|---|---|---|---|---|
| AC-1 | static source audit | reject DetailTable.vue `.card-body` carries padding-0 override class (scoped) | reviewer checklist | 1 |
| AC-2 | static source audit | material-trace App.vue Result Card `.card-body` carries padding-0 override class (scoped) | reviewer checklist | 1 |
| AC-3 | contract | `npm run css:check` passes 0 errors | `frontend/` (existing script) | 1 |
| AC-4 | unit | all Vitest tests pass, 0 regressions | `frontend/` (existing suite) | 1 |
| AC-5 | static source audit | no API/route/service/backend file changed | git diff scope check | 1 |
| AC-6 | e2e | card header and toolbar remain visible after fix | `frontend/tests/playwright/reject-material-flat-table.spec.js` | 2 |
| AC-1 + AC-6 | e2e | reject-history flat DOM: no nested `.ui-card` inside `.card-body` | `frontend/tests/playwright/reject-material-flat-table.spec.js` | 2 |
| AC-2 + AC-6 | e2e | material-trace flat DOM: no nested `.ui-card` inside Result Card `.card-body` | `frontend/tests/playwright/reject-material-flat-table.spec.js` | 2 |

## Test Families Required

contract / unit / e2e / static source audit

## Test Families and File Paths

| family | file path | notes |
|---|---|---|
| static source audit | source files only | reviewer check; no runnable test file |
| contract | `frontend/` → `npm run css:check` | existing governance script |
| unit (Vitest) | `frontend/` → `npm run test` | existing suite; expect 331 pass, 0 fail |
| e2e (Playwright) | `frontend/tests/playwright/reject-material-flat-table.spec.js` | new file; pattern from `hold-history-flat-table.spec.js` |

## Tier Assignment

| family | tier | gate |
|---|---|---|
| static source audit | Tier 1 (pre-merge, manual) | reviewer checklist |
| contract | Tier 1 (pre-merge, automated) | `npm run css:check` must exit 0 |
| unit (Vitest) | Tier 1 (pre-merge, automated) | `npm run test` must exit 0 |
| e2e (Playwright) | Tier 2 (pre-merge, automated) | all 4 new tests must pass |

## Out of Scope

- Backend / API tests — AC-5 confirms zero backend change
- Vitest component unit tests — pure CSS presentational fix; no logic under test
- Visual regression screenshot diffing — delegated to ui-ux-reviewer and visual-reviewer agents
- Resilience / stress / soak / monkey — low-risk CSS fix; change-classification.md marks these N/A
- Other pages outside the change radius (wip-detail, hold-detail, hold-overview, etc.)

## New Playwright Spec

**File:** `frontend/tests/playwright/reject-material-flat-table.spec.js`

Pattern mirrors `hold-history-flat-table.spec.js`: `loginViaApi` + `navigateViaSidebar`, loading-overlay wait.

### 4 tests to create

1. **card structure — reject-history "明細列表" card is visible with exactly one `.ui-card` wrapper**
   Navigate to `reject-history` via sidebar; wait for `.ui-card`. Assert `.ui-card` filtered by
   text `明細列表` has `count === 1` (not nested).

2. **column presence — expected columns visible in the reject-history detail table**
   Locate the "明細列表" card's `<table>` first header row. Assert header text contains
   `LOT`, `WORKCENTER`, `原因`.

3. **flat DOM structure — `.card-body` does NOT contain a nested `.ui-card` (reject-history)**
   Locate `cardBody` inside the "明細列表" card. Assert `cardBody.locator('.ui-card').count() === 0`.

4. **pagination/info element present when reject-history results exist**
   Assert at least one of `.table-info`, `.pagination-control`, `[class*="pagination"]`,
   `.data-table-footer` is present inside the "明細列表" card.

> material-trace Result Card flat-DOM assertion (AC-2): covered in test 3 as a second `test.describe`
> block within the same spec file — navigates to `material-trace`, submits a minimal query, then
> asserts `cardBody.locator('.ui-card').count() === 0` inside the "查詢結果" card.

## Notes

Reference spec: `frontend/tests/playwright/hold-history-flat-table.spec.js`
Card title strings: reject-history → `明細列表`; material-trace Result Card → `查詢結果`
Columns confirmed from source: DetailTable.vue (LOT=`CONTAINERNAME`, `WORKCENTERNAME`, 原因=`LOSSREASONNAME`);
material-trace TABLE_COLUMNS (`CONTAINERNAME`, `PJ_WORKORDER`, `MATERIALPARTNAME`).
