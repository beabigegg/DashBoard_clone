---
change-id: wip-hold-drilldown-filters
schema-version: 0.1.0
---

# Test Plan — wip-hold-drilldown-filters

## Acceptance Criteria → Test Mapping

| Criterion | Test family | Test file | Test name | Tier |
|---|---|---|---|---|
| AC-1 | Vitest | `frontend/tests/components/MatrixTable.test.js` | cell click emits workcenter+package; nav-state carries both | 1 |
| AC-2 | Vitest | `frontend/tests/components/MatrixTable.test.js` | row-header click emits workcenter only; no package key | 1 |
| AC-3 | Vitest | `frontend/tests/components/MatrixTable.test.js` | cell click toggles `active` class; second click removes it | 1 |
| AC-4 | Vitest | `frontend/tests/components/LotDetailTable.test.js` | Type column present right of LOT ID; sorted; null → `-` | 1 |
| AC-5 | Vitest | `frontend/tests/components/FilterPanel.test.js` | renders 9 filter-groups in 3×3; labels match spec | 1 |
| AC-6 | pytest | `tests/test_wip_routes.py` | POST /api/wip/detail/<wc> with workflow/bop/pj_function filters | 1 |
| AC-7 | pytest | `tests/test_wip_routes.py` | GET /api/wip/meta/filter-options returns workflows/bops/pjFunctions | 1 |
| AC-8 | Vitest | `frontend/tests/components/FilterPanel.test.js` | hold→wip navigation: WORKFLOW not leaked to wip FilterPanel | 1 |
| AC-9 | Vitest | `frontend/tests/validation/wip-url-params.test.js` | query params workflow/bop/pj_function pre-populate FilterPanel and auto-submit | 1 |
| AC-10 | pytest | `tests/test_wip_routes.py` | pjType present in Redis-cache and Oracle-fallback paths; null when DB value NULL | 1 |

## Test Families

### Unit / Vitest (Tier 1, pre-merge)

**`frontend/tests/components/MatrixTable.test.js`** (new)
- `cell click emits { workcenter, package } payload`
- `row-header click emits { workcenter } only — no package key`
- `clicked cell gains active class; second click removes active class`

**`frontend/tests/components/LotDetailTable.test.js`** (new)
- `Type column exists at index 1 (after LOT ID)`
- `Type column is sortable`
- `null pjType renders dash`

**`frontend/tests/components/FilterPanel.test.js`** (update)
- `renders exactly 9 .filter-group elements` (was 6)
- `row 1 labels: WORKORDER, LOT ID, PACKAGE`
- `row 2 labels: WORKFLOW, BOP, TYPE`
- `row 3 labels: FUNCTION, Wafer LOT, Wafer Type`
- `hold-overview WORKFLOW selection does not propagate to wip FilterPanel state`

**`frontend/tests/validation/wip-url-params.test.js`** (new)
- `workflow query param pre-populates filter and triggers submit`
- `bop query param pre-populates filter and triggers submit`
- `pj_function query param pre-populates filter and triggers submit`
- `unknown query params are ignored`

### Backend Route Tests / pytest (Tier 1, pre-merge)

**`tests/test_wip_routes.py`** (update)
- `test_filter_options_returns_workflows_bops_pj_functions`
- `test_detail_filter_by_workflow`
- `test_detail_filter_by_bop`
- `test_detail_filter_by_pj_function`
- `test_detail_pj_type_present_redis_path`
- `test_detail_pj_type_present_oracle_fallback`
- `test_detail_pj_type_null_when_db_null`

### Playwright Critical Journeys (Tier 1, pre-merge, non-blocking)

**`frontend/tests/playwright/hold-overview.spec.js`** (existing — regression guard)
- Existing hold-overview matrix drill-down journeys must pass unchanged

**`frontend/tests/playwright/wip-matrix-drilldown.spec.js`** (new)
- `matrix cell click navigates to wip-detail with workcenter and package in URL`
- `row-header click navigates to wip-detail with workcenter only`

## Out of Scope

- e2e-resilience, monkey, stress, and soak tests — Tier 3 not required per classifier
- HoldMatrix unit tests beyond regression (no new hold-overview logic introduced)
- CSS token / authored-CSS tests (css-contract read-only; no new tokens added)
- Oracle integration tests for new filter params (mock coverage in pytest is sufficient; real-DB nightly, not pre-merge)
