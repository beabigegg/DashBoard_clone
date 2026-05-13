---
change-id: wip-hold-drilldown-filters
classifier-version: 1
tier: 3
---

# Change Classification — wip-hold-drilldown-filters

## Tier
- 3

## Change Type
enhancement

## Architecture Review Required
no

## Affected Surfaces

**Backend**
- `src/mes_dashboard/services/wip_service.py` — add `pjType` to lot rows; add `workflows`/`bops`/`pjFunctions` to filter-options; accept `workflow`/`bop`/`pj_function` filter params across detail, summary, matrix, and filter-options endpoints
- `src/mes_dashboard/sql/wip/detail.sql` — add `PJ_TYPE`, `WORKFLOWNAME`, `BOP`, `PJ_FUNCTION` to SELECT
- `src/mes_dashboard/routes/wip_routes.py` — parse and forward three new filter params on `api_detail`, `api_overview_summary`, `api_overview_matrix`, `api_meta_filter_options`

**Frontend — wip-overview**
- `frontend/src/wip-overview/components/FilterPanel.vue` — add `workflow`, `bop`, `pjFunction` fields; reorder into 3×3 grid
- `frontend/src/wip-overview/App.vue` — extend filters/filterOptions/orchestrator; update `navigateToDetail` to pass `workcenter+package` on cell click
- `frontend/src/wip-overview/components/MatrixTable.vue` — upgrade from workcenter-only drilldown to cell drilldown; active-cell highlight; toggle semantics

**Frontend — wip-detail**
- `frontend/src/wip-detail/components/FilterPanel.vue` — same 3×3 reorder as wip-overview FilterPanel
- `frontend/src/wip-detail/App.vue` — extend filters/filterOptions/orchestrator; accept `package` from URL/nav-state
- `frontend/src/wip-detail/components/LotTable.vue` — add `Type` (pjType) column adjacent to LOT ID

**Frontend — hold-overview**
- `frontend/src/hold-overview/App.vue` — extend filters/filterOptions/orchestrator to wire three new fields; FilterPanel is already shared from wip-overview so it auto-propagates

**Shared core**
- `frontend/src/core/wip-navigation-state.ts` — add `workflow`, `bop`, `pjFunction`, `matrixPackage` to WipNavigationState/WipNavigationFilters interfaces
- `frontend/src/core/wip-derive.ts` — extend WipFilters and `buildWipOverviewQueryParams` to serialize new fields

**Contracts**
- `contracts/api/api-contract.md` — document three new query-param filters
- `contracts/api/api-inventory.md` — update WIP-01 rule; note filter-options new arrays
- `contracts/data/data-shape-contract.md` — document `pjType` in lot-list rows; `workflows`/`bops`/`pjFunctions` in filter-options shape

## Required Agents
1. contract-reviewer — update api-contract.md, api-inventory.md, data-shape-contract.md before implementation
2. test-strategist — write test-plan.md
3. backend-engineer — SQL, service layer, route layer; backend route tests
4. frontend-engineer — MatrixTable cell drilldown, navigation state, FilterPanel 3×3, LotTable Type column, hold-overview wiring; Vitest tests
5. ci-cd-gatekeeper — write ci-gates.md; confirm all gates pass
6. qa-reviewer — release readiness verdict

## Tasks Not Applicable
- 2.2 (CSS/UI contract — no design token or authored CSS change; enforced by css:check)
- 2.3 (Env contract — no env var changes)
- 2.5 (Business logic contract — additive filter params; no business decision rule changes)
- 3.3 (E2E/resilience tests — Tier 3; no e2e-resilience-engineer)
- 3.4 (Data-boundary/monkey tests — Tier 3; no monkey-test-engineer)
- 3.5 (Stress/soak tests — additive filter params; no new query pattern)
- 4.3 (Env/deploy — no env or infrastructure changes)
- 5.1 (UI/UX review — additive filter fields following established pattern; not a new UX paradigm)
- 5.2 (Visual review — no new visual design components)
- 6.4 (Nightly/weekly gates — Tier 3; not required)

## Optional Artifacts
- current-behavior.md: yes
- proposal.md: no
- spec.md: yes
- design.md: no
- qa-report.md: yes
- regression-report.md: no

## Inferred Acceptance Criteria

AC-1: Clicking a non-zero data cell at row `workcenter=W` / column `pkg=P` in the Workcenter × Package Matrix navigates to `/wip-detail?workcenter=W&package=P`, and `wip-navigation-state` sessionStorage contains both `workcenter=W` and the package filter pre-set so wip-detail FilterPanel renders with that package pre-selected on arrival.

AC-2: Clicking the workcenter name in the matrix row header still navigates to `/wip-detail?workcenter=W` with no package pre-filter — existing behaviour is preserved.

AC-3: After a matrix cell click, that cell receives the `active` CSS class; clicking the same cell a second time deselects it (toggle semantics matching HoldMatrix pattern).

AC-4: The wip-detail Lot Details table renders a `Type` column immediately to the right of `LOT ID`, sourced from `lot.pjType`; the column is sortable; rows where `pjType` is null render `-`.

AC-5: The FilterPanel on wip-overview, wip-detail, and hold-overview renders exactly nine filter fields in three rows of three: Row 1: WORKORDER / LOT ID / PACKAGE; Row 2: WORKFLOW / BOP / TYPE; Row 3: FUNCTION / Wafer LOT / Wafer Type — each backed by a MultiSelect with cross-filter options from `/api/wip/meta/filter-options`.

AC-6: A POST to `/api/wip/detail/<workcenter>` with body `{"workflow": "WF-A"}` returns only lots whose `WORKFLOWNAME = 'WF-A'`; similarly for `bop` → `BOP` and `pj_function` → `PJ_FUNCTION`; confirmed by backend route-level mock tests.

AC-7: `GET /api/wip/meta/filter-options` returns `workflows`, `bops`, and `pjFunctions` arrays (distinct non-empty values) alongside existing arrays; each is an empty list when no data matches rather than absent.

AC-8: After selecting WORKFLOW filter on hold-overview and navigating to wip-overview, the wip-overview WORKFLOW filter is empty — no cross-page state leak; each page manages its own reactive `filters` object.

AC-9: Navigating to `/wip-overview?workflow=WF-A&bop=B1&pj_function=FN` sets those three filters in the FilterPanel and submits them on initial data load without requiring the user to click "套用篩選".

AC-10: The `/api/wip/detail/<workcenter>` response `lots` array items include `pjType` field for both the Redis-cache code path and the Oracle-direct fallback code path; value is `null` (not absent) when `PJ_TYPE` is NULL in the DB.

## Contract Impact

| Contract | Change |
|---|---|
| `contracts/api/api-contract.md` | Add `workflow`, `bop`, `pj_function` query-param docs for WIP detail/summary/matrix/filter-options endpoints |
| `contracts/api/api-inventory.md` | Update WIP-01 rule; note filter-options new arrays |
| `contracts/data/data-shape-contract.md` | Document `pjType: string\|null` in lot-list item shape; `workflows: string[]`, `bops: string[]`, `pjFunctions: string[]` in filter-options response shape |

No API endpoint paths, HTTP methods, or auth rules are altered. All changes are additive.

## Clarifications or Assumptions

- FilterPanel in hold-overview is already imported from `frontend/src/wip-overview/components/FilterPanel.vue` — no separate hold-overview FilterPanel component exists. Updating wip-overview FilterPanel propagates to hold-overview automatically.
- The `wip-navigation-state.ts` already handles cross-app navigation via sessionStorage; extending it for the new fields follows the same pattern.
- All four new DB columns (PJ_TYPE, WORKFLOWNAME, BOP, PJ_FUNCTION) are available in DWH.DW_MES_LOT_V and already returned by the individual lot detail endpoint — no schema migration required.
- Filter sharing is UI-component-level only; each page has independent reactive state (no cross-page state sync was requested).
- `FilterPanel.test.js` currently asserts `.filter-group` count = 6; this test must be updated to 9.

## Context Manifest Draft

### Affected Surfaces
- `src/mes_dashboard/routes/wip_routes.py`
- `src/mes_dashboard/services/wip_service.py`
- `src/mes_dashboard/sql/wip/detail.sql`
- `frontend/src/wip-overview/`
- `frontend/src/wip-detail/`
- `frontend/src/hold-overview/`
- `frontend/src/core/wip-navigation-state.ts`
- `frontend/src/core/wip-derive.ts`
- `contracts/api/api-contract.md`
- `contracts/api/api-inventory.md`
- `contracts/data/data-shape-contract.md`

### Allowed Paths
- specs/changes/wip-hold-drilldown-filters/
- specs/context/project-map.md
- specs/context/contracts-index.md
- src/mes_dashboard/routes/
- src/mes_dashboard/services/
- src/mes_dashboard/sql/wip/
- src/mes_dashboard/core/
- frontend/src/wip-overview/
- frontend/src/wip-detail/
- frontend/src/hold-overview/
- frontend/src/core/
- frontend/src/shared-composables/
- frontend/src/shared-ui/
- frontend/src/wip-shared/
- frontend/tests/components/
- frontend/tests/playwright/
- frontend/tests/legacy/
- frontend/tests/validation/
- contracts/api/
- contracts/data/
- contracts/css/
- contracts/ci/
- tests/

### Agent Work Packets

#### contract-reviewer
- specs/changes/wip-hold-drilldown-filters/
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/data/data-shape-contract.md
- src/mes_dashboard/routes/wip_routes.py
- src/mes_dashboard/services/wip_service.py

#### backend-engineer
- specs/changes/wip-hold-drilldown-filters/
- src/mes_dashboard/routes/wip_routes.py
- src/mes_dashboard/services/wip_service.py
- src/mes_dashboard/sql/wip/
- src/mes_dashboard/core/
- tests/

#### frontend-engineer
- specs/changes/wip-hold-drilldown-filters/
- frontend/src/wip-overview/
- frontend/src/wip-detail/
- frontend/src/hold-overview/
- frontend/src/core/
- frontend/src/shared-composables/
- frontend/src/shared-ui/
- frontend/src/wip-shared/
- frontend/tests/components/
- frontend/tests/legacy/
- frontend/tests/validation/

#### ci-cd-gatekeeper
- specs/changes/wip-hold-drilldown-filters/
- contracts/api/api-contract.md
- contracts/data/data-shape-contract.md
- contracts/ci/ci-gate-contract.md
- frontend/tests/components/
- frontend/tests/playwright/
- tests/

#### qa-reviewer
- specs/changes/wip-hold-drilldown-filters/
- frontend/src/wip-overview/
- frontend/src/wip-detail/
- frontend/src/hold-overview/
- frontend/src/core/
- frontend/tests/components/
- frontend/tests/playwright/
- tests/
