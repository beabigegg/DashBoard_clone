---
change-id: wip-hold-drilldown-filters
archived-date: 2026-05-13
tier: 3
verdict: approved-with-risk (all CI gates pass)
---

# Archive — wip-hold-drilldown-filters

## Change Summary

Added three interconnected features to the WIP/Hold reporting pages. First, the WIP-Overview matrix table now supports cell-level drilldown: clicking a cell navigates to WIP-Detail with `workcenter` + `package` pre-populated in the URL; clicking a row header navigates with `workcenter` only. Second, the WIP-Detail Lot Details table gained a `Type` column rendering the `PJ_TYPE` field (null → `'-'`, sortable). Third, all three pages (WIP-Overview, WIP-Detail, Hold-Overview) received three new filter fields — WORKFLOW, BOP, FUNCTION — backed by new `workflow`, `bop`, `pj_function` backend params on all four WIP API endpoints. A bug discovered during QA (and again during post-merge acceptance testing) was also fixed: `_get_wip_search_index`'s full-rebuild fallback called `_materialize_search_payload` directly, which never included `workflows/bops/pjFunctions`; the dead function `_build_wip_search_index` (which had the correct logic) was identified, its fix was ported to the live path, and the dead function was removed.

## Final Behavior

- **WIP-Overview matrix cell click**: navigates to `/wip-detail?workcenter=X&package=Y`; active cell is highlighted; second click on same cell deselects.
- **WIP-Overview matrix row-header click**: navigates to `/wip-detail?workcenter=X` (no package).
- **WIP-Detail URL pre-population**: on load, reads `workcenter`, `package` (and `workflow`, `bop`, `pj_function`) from URL params or sessionStorage navigation state.
- **WIP-Detail Lot Details table**: `Type` column at position 2 (after LOT ID), sortable, renders `pjType` from API; null/undefined → `'-'`.
- **Filter dropdowns on all three pages**: WORKFLOW, BOP, FUNCTION fields populated from `/api/wip/meta/filter-options` response keys `workflows`, `bops`, `pjFunctions`; applied as backend filter params on all WIP summary/matrix/detail/filter-options endpoints.
- **Filter dropdown initial load (bug fix)**: `_get_wip_search_index` now correctly populates `workflows`, `bops`, `pjFunctions` on first request after service restart (full-rebuild path). Previously these were always empty until an incremental sync ran.
- **UI spacing**: 28 px gap between summary card group and the content section below it on all three pages (was ~16 px).

## Final Contracts Updated

- `contracts/api/api-contract.md` — added `workflow`, `bop`, `pj_function` query params to `/api/wip/overview/summary`, `/api/wip/overview/matrix`, `/api/wip/detail/{workcenter}`, `/api/wip/meta/filter-options`; added `pjType` field to lot-row response schema; added `workflows`, `bops`, `pjFunctions` arrays to filter-options response.
- `contracts/api/api-inventory.md` — updated endpoint summaries to reflect new params.
- `contracts/data/data-shape-contract.md` — added `PJ_TYPE`, `WORKFLOWNAME`, `BOP`, `PJ_FUNCTION` columns to the WIP DataFrame contract.
- `contracts/CHANGELOG.md` — version bump with summary of all contract additions.

## Final Tests Added / Updated

**Frontend (Vitest):**
- `frontend/tests/components/MatrixTable.test.js` (new) — AC-1/AC-2/AC-3 coverage: cell drilldown emit, row-header emit, active-cell CSS class, toggle-off.
- `frontend/tests/components/LotDetailTable.test.js` (new) — AC-4 coverage: Type column position, value rendering, null/undefined → `'-'`, sortability, all-null crash resistance.
- `frontend/tests/components/FilterPanel.test.js` (updated) — AC-5 coverage: 9-field count, label presence (WORKFLOW, BOP, FUNCTION), label order.
- `frontend/tests/validation/wip-url-params.test.js` (new) — AC-9 coverage: URL param pre-population for `workflow`, `bop`, `pj_function`.
- `frontend/tests/playwright/wip-matrix-drilldown.spec.js` (new) — Playwright critical-journey for WIP matrix cell drilldown (AC-1/AC-2/AC-3/AC-4).

**Backend (pytest):**
- `tests/test_wip_routes.py` (updated) — AC-6/AC-7/AC-10 coverage: workflow/bop/pj_function forwarded to service layer on all endpoints; filter-options returns three new keys; pjType present in lot rows for null and non-null cases.
- `tests/test_wip_hold_pages_integration.py` (updated) — integration mock assertions updated to include `workflow=''`, `bop=''`, `pj_function=''` in four existing tests.

## Final CI/CD Gates

All Tier 1 required gates passed on CI (GitHub Actions run 25774375355):
- frontend-unit (Vitest) — PASS
- css-governance — PASS (0 errors; 47 pre-existing warnings)
- contract-validate (`cdd-kit validate`) — PASS
- backend-unit (pytest) — PASS (3576 passed, 185 skipped)
- playwright-critical-journeys — PASS
- playwright-resilience — PASS
- playwright-data-boundary — PASS

## Production Reality Findings

1. **Dead code masked a live bug**: `_build_wip_search_index` was added as the correct implementation of the filter-index builder (with `workflows/bops/pjFunctions`) but was never wired into `_get_wip_search_index`. The live path had a silent fallback that omitted the new fields every time the process restarted. Deleting Redis and restarting the service alone was insufficient to surface the fix — the bug was in the fallback path of the in-process search index, not in the Redis cache. Discovered during post-merge acceptance testing.

2. **`mock_opts` assertion gap in integration tests**: The `test_wip_overview_post_avoids_url_length_limit` integration test asserts on `get_wip_filter_options` as well as `get_wip_summary` and `get_wip_matrix`. The CI failure initially listed only the first two mocks; the `mock_opts` assertion failure was masked because pytest stops at the first `AssertionError` in a test body. A second CI run revealed the third failure.

3. **QA verdict was approved-with-risk**: Two test gaps noted (AC-9 `wip-url-params.test.js` absent at QA time; Playwright `wip-matrix-drilldown.spec.js` absent at QA time). Both files were subsequently created and CI confirmed all Playwright specs pass.

## Lessons Promoted to Standards

- **Promoted to `CLAUDE.md` § WIP Service Architecture Notes**: When adding a new field to `_get_wip_search_index`'s filter-options response, the field must be appended in the full-rebuild branch (`if index_payload is None:`) AND carried forward in the incremental branch. A helper function that is never called from `_get_wip_search_index` will silently omit the field after every service restart.
  - Evidence: `wip_service.py` `_build_wip_search_index` was defined but never called; `_get_wip_search_index` full-rebuild path omitted `workflows/bops/pjFunctions` on every restart.

## Follow-up Work

None. All AC items implemented and tested. QA deficiencies resolved before merge.

---

> **Cold Data Warning**: This archive is historical evidence. Current requirements live in `contracts/` and active project guidance.
