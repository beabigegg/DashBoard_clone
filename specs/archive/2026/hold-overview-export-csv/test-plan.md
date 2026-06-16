---
change-id: hold-overview-export-csv
schema-version: 0.1.0
last-changed: 2026-06-16
risk: medium
tier: 1
---

# Test Plan: hold-overview-export-csv

## Acceptance Criteria → Test Mapping

| criterion id | test family | test file path | tier |
|---|---|---|---|
| AC-1 (button renders with `ui-btn ui-btn--secondary`) | unit | `frontend/tests/hold-overview/csv-export.test.js` | 0 |
| AC-2 (export=true fetch, pagination bypassed in composable) | unit | `frontend/tests/validation/useHoldOverview.validation.test.js` | 0 |
| AC-2 (route forwards `export` flag to service, per-kwarg) | integration | `tests/test_hold_overview_routes.py` | 1 |
| AC-3 (13 columns present, header row, display order) | unit | `frontend/tests/hold-overview/csv-export.test.js` | 0 |
| AC-3 (column set matches data-shape-contract) | contract | `tests/contract/samples/get_hold_overview_lots_export.json` | 1 |
| AC-4 (UTF-8 BOM prefix `﻿`) | unit | `frontend/tests/hold-overview/csv-export.test.js` | 0 |
| AC-5 (RFC 4180 escaping: comma, quote, newline in values) | unit | `frontend/tests/hold-overview/csv-export.test.js` | 0 |
| AC-5 (null/missing fields → empty string; empty result → header-only) | data-boundary | `frontend/tests/playwright/data-boundary/hold-overview-export-csv.spec.js` | 1 |
| AC-6 (paginated query path unaffected when export absent) | integration | `tests/test_hold_overview_routes.py` | 1 |
| AC-7 (row cap enforced: `HOLD_OVERVIEW_EXPORT_MAX_ROWS` env var) | unit | `tests/test_hold_overview_routes.py` | 0 |
| AC-7 (bounded large-result does not exceed cap) | stress | `tests/stress/test_hold_overview_export_stress.py` | 3 |
| AC-8 (button disabled + loading class during in-flight request) | E2E | `frontend/tests/playwright/hold-overview.spec.js` | 1 |
| AC-8 (button re-enables after response completes) | E2E | `frontend/tests/playwright/hold-overview.spec.js` | 1 |

## Test Families Required

| family | tier | notes |
|---|---|---|
| unit | 0 | Frontend: `csv-export.test.js` tests `_buildCsv`/`_downloadCsv` helpers extracted into hold-overview (BOM, columns, escaping, empty-result). Extend `useHoldOverview.validation.test.js` for export-mode composable flag. Backend: extend `TestHoldOverviewLotsRoute` with `test_lots_export_bypasses_pagination` and `test_lots_export_capped_at_max_rows`. |
| contract | 1 | New sample `get_hold_overview_lots_export.json` validates export-mode response envelope against `api-contract.md`. |
| integration | 1 | Extend `TestHoldOverviewLotsRoute` and `TestHoldOverviewNonIndexedFilterForwarding` in `tests/test_hold_overview_routes.py` — per-kwarg assertion on `export` flag; assert paginated path is unaffected when `export` absent. |
| E2E | 1 | Extend `frontend/tests/playwright/hold-overview.spec.js` — mock export endpoint, click button, assert Blob download triggers, assert disabled/loading during flight, assert enabled after. |
| data-boundary | 1 | `frontend/tests/playwright/data-boundary/hold-overview-export-csv.spec.js` — mocked payload with null/undefined field values; empty `lots` array. Assert no thrown error; assert header-only CSV download. |
| stress | 3 | Nightly only. `tests/stress/test_hold_overview_export_stress.py` — service returns exactly `HOLD_OVERVIEW_EXPORT_MAX_ROWS` rows; assert response row count ≤ cap, no timeout. |

## Test Update Contract

| existing test | action | reason |
|---|---|---|
| `tests/test_hold_overview_routes.py::TestHoldOverviewLotsRoute` | extend | Add export-flag and row-cap method variants; do not alter existing pagination tests. |
| `frontend/tests/validation/useHoldOverview.validation.test.js` | extend | Add export-mode fetch assertion alongside existing filter-forwarding tests. |
| `frontend/tests/playwright/hold-overview.spec.js` | extend | Add button loading-state and download-trigger assertions; preserve existing filter/render tests. |

## Out of Scope

- Server-side CSV generation (pattern decision: client-side only)
- New CSS contract tests (reuses `ui-btn` tokens; no new authored rules)
- Visual regression (agent-log confirmation per `change-classification.md`)
- Monkey / fuzz / soak tests
- i18n update tests (button label covered by E2E render assertion)

## Notes

- `csv-export.test.js` must import the CSV helper at its definition site, not through the Vue component template.
- Stress test is Tier 3 (nightly); it is not a PR gate and must not be listed as waived or skipped.
- Contract sample filename follows existing convention: `get_hold_overview_lots_export.json`.
- `call_args.kwargs[key]` per-kwarg style required per test-discipline rules (no `assert_called_once_with` whitelists).
