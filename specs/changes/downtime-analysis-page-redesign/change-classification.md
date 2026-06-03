# Change Classification

## Change Types
- primary: `ui-redesign` (layout restructure: three-tab → single-page, three-tier expandable table, chart cross-filter), `api-only-change` (additive optional filter params on two endpoints)
- secondary: `feature-enhancement` (chart interactivity / cross-filter behavior)

## Risk Level
- medium

Rationale: Behavior change to an existing page, additive API surface change, and modification touching shared-ui (`DataTable`) consumed by 12+ feature apps. Not high — no Oracle query changes, no auth, no env/secret changes, backend changes are additive-only. The shared-ui blast radius and portal-shell CSS bleed risk push it above low.

## Impact Radius
- cross-module

Touches downtime-analysis frontend module, downtime-analysis backend route/service, and shared-ui components (read-only verification of additive non-breaking impact).

## Tier
- 2

## Architecture Review Required
- yes
- reason: The three-tier table introduces a new data-flow design (Tier 1 status group → Tier 2 machine → Tier 3 lazy-loaded events), with a non-obvious decision about where filtering happens (in-memory parquet spool, no new Oracle queries) and how the lazy-load boundary maps to existing endpoints. Cross-filter event wiring between two ECharts components and a shared three-tier table is a module-boundary/data-flow decision that must be settled before implementation. ADR-0002 (spool namespace) and ADR-0003 (rowcount-chunking exclusion) constrain the downtime-analysis backend; design must confirm additive filtering stays within those constraints.

## Required Artifacts
Always required: change-request.md, change-classification.md, implementation-plan.md, test-plan.md, ci-gates.md, tasks.yml, context-manifest.md

## Optional Artifacts

| artifact | create? | reason |
|---|---|---|
| current-behavior.md | no | Existing three-tab behavior captured in change-request.md §Known Context |
| proposal.md | no | Scope and direction decided by user; no open product decision |
| spec.md | no | No separate user-facing behavior decision beyond what design.md + implementation-plan hold |
| design.md | yes | Architecture Review Required = yes (three-tier data-flow, cross-filter wiring, lazy-load boundary, in-memory filtering decision within ADR-0002/0003) |
| qa-report.md | no | Routine evidence goes in agent-log/*.yml; promote only if blocking findings or approved-with-risk |
| regression-report.md | no | Promote if shared-ui/other-page regression confirmed |
| visual-review-report.md | no | Evidence in agent-log/ui-ux-reviewer.yml; promote if before/after screenshots needed as durable proof |
| monkey-test-report.md | no | Not a fuzz/monkey-critical surface |
| stress-soak-report.md | no | No new high-load path; filtering is in existing in-memory spool |

## Required Contracts
- API: yes — additive optional query params (`big_category`, `status_types`, `resource_id`) on `/api/downtime-analysis/equipment-detail` and `/api/downtime-analysis/event-detail`. Update `contracts/api/api-contract.md` + `contracts/api/api-inventory.md`, version entry in `contracts/CHANGELOG.md`.
- CSS/UI: yes — new components + layout; all rules scoped under `.theme-downtime-analysis`. Update `contracts/css/css-contract.md` if new authored CSS sources are added.
- Env: no
- Data shape: yes (verify) — confirm filtered `equipment-detail` / `event-detail` response shape is unchanged (additive params, no new JSON key or wrapper)
- Business logic: no — filter semantics (UDT/SDT/EGT grouping) reflect existing classification; no new business rule
- CI/CD: pending — if new Playwright spec requires `npx playwright install --with-deps chromium` step in `frontend-tests.yml`, this becomes a ci-cd-change (see CLAUDE.md CI Workflow Notes); ci-cd-gatekeeper determines

## Required Tests
- unit: yes — StatusMachineJobTable.vue, MachineEventRows.vue (expand/collapse, lazy-load trigger, cross-filter prop reactivity); backend filter-param application in downtime_analysis_service for big_category / status_types / resource_id on in-memory spool path
- contract: yes — route forwarding per-kwarg with non-default values, asserting `mock_service.call_args.kwargs[...]`; additive params default to no-op (backward compatible)
- integration: yes — equipment-detail / event-detail endpoint filtering end-to-end against spool fixture; assert response wrapper key matches route's `success_response(...)` call
- E2E: yes — Playwright downtime-analysis spec: BigCategoryChart click filters table; DailyTrendChart legend click filters by status; three-tier expand to Tier 3 lazy-load; verify CI browser-install step
- visual: yes — UI/UX + visual review of single-page layout, three-tier table, `.theme-downtime-analysis` scoping (no CSS bleed)
- data-boundary: yes — assert filtered response key/shape unchanged; empty/malformed filter values handled gracefully
- resilience: no
- fuzz/monkey: no
- stress: no
- soak: no

## Required Agents
(in order)
1. `spec-architect` — write `design.md` (Task 1.3)
2. `contract-reviewer` — update/create contracts in `contracts/` before implementation
3. `test-strategist` — write `test-plan.md` directly
4. `ci-cd-gatekeeper` — write `ci-gates.md` directly
5. `implementation-planner` — write `implementation-plan.md` directly
6. `backend-engineer` — additive filter params, in-memory spool filtering
7. `frontend-engineer` — single-page layout, new components, ECharts wiring
8. `ui-ux-reviewer` — visual + accessibility review
9. `qa-reviewer` — release readiness decision

## Inferred Acceptance Criteria
- AC-1: Clicking a sector in BigCategoryChart emits the selected big-category and filters the three-tier table to rows matching that category; clicking the same sector again (or a "clear" chip) restores the unfiltered table.
- AC-2: Clicking a legend entry in DailyTrendChart toggles filtering of the three-tier table by status type (UDT / SDT / EGT), and multiple status types combine as a union.
- AC-3: The page renders as a single page (charts above, three-tier table below) with the previous Charts/Equipment/Events tab switcher removed, and no previously-available information from the Equipment and Events tabs is lost.
- AC-4: The three-tier table expands Tier 1 (status group) → Tier 2 (machine within status) → Tier 3 (events/JOB per machine), where Tier 3 rows are lazy-loaded only when a machine row is expanded.
- AC-5: `/api/downtime-analysis/equipment-detail` and `/api/downtime-analysis/event-detail` accept optional `big_category`, `status_types`, and `resource_id` params, apply them as in-memory parquet-spool filters, and trigger no new Oracle query; omitting all three returns the pre-existing unfiltered response unchanged (backward compatible).
- AC-6: All authored CSS for the redesigned page is scoped under `.theme-downtime-analysis` and `npm run css:check` passes with zero unscoped top-level rules; switching to another page after viewing downtime-analysis shows no style bleed.
- AC-7: The `DataTable` and any other shared-ui components touched retain unchanged emit/prop surfaces for the other 11+ consumer apps (additive-only); existing shared-ui component tests still pass.
- AC-8: Lazy-loaded Tier 3 rows resolve the correct backend JSON wrapper key (read from the route's `success_response(...)`), so a populated dataset renders rows rather than a silent empty table.

## Tasks Not Applicable
- not-applicable: 2.3, 2.5, 3.5, 4.3

## Clarifications or Assumptions
- Assumption: Redesigned page reuses existing downtime-analysis spool/namespace (ADR-0002) and stays excluded from rowcount chunking (ADR-0003); design must confirm additive filtering does not re-introduce chunking.
- Assumption: `status_types` is a CSV/multi-value param (e.g., `UDT,SDT`) consistent with other multi-value filter params; design.md pins the exact serialization.
- Assumption: No new page is added, no route or `drawer_id` changes; `data/page_status.json`, `asset_readiness_manifest.json`, `route_scope_matrix.json` are NOT touched.
- Clarification: Whether new Playwright spec is added vs. extending existing `downtime-analysis.spec.js` — ci-cd-gatekeeper confirms if `frontend-tests.yml` browser-install step is needed (task 2.6 pending until then).

## Context Manifest Draft

### Affected Surfaces
- downtime-analysis frontend module (`frontend/src/downtime-analysis/`)
- downtime-analysis backend (`src/mes_dashboard/routes/downtime_analysis_routes.py`, `src/mes_dashboard/services/downtime_analysis_service.py`, `downtime_analysis_cache.py`)
- shared-ui (`frontend/src/shared-ui/components/`) — read-only verification of additive non-breaking impact
- downtime-analysis SQL spool directory (`src/mes_dashboard/sql/downtime_analysis/`) — read-only confirmation no new query is added

### Allowed Paths
- specs/changes/downtime-analysis-page-redesign/
- specs/context/project-map.md
- specs/context/contracts-index.md
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/css/css-contract.md
- contracts/css/css-inventory.md
- contracts/data/data-shape-contract.md
- contracts/CHANGELOG.md
- docs/adr/0002-downtime-analysis-spool-namespace.md
- docs/adr/0003-downtime-rowcount-chunking-exclusion.md
- frontend/src/downtime-analysis/
- frontend/src/shared-ui/components/
- frontend/src/core/
- frontend/tests/playwright/
- frontend/tests/components/
- src/mes_dashboard/routes/downtime_analysis_routes.py
- src/mes_dashboard/services/downtime_analysis_service.py
- src/mes_dashboard/services/downtime_analysis_cache.py
- src/mes_dashboard/services/event_fetcher.py
- src/mes_dashboard/sql/downtime_analysis/
- .github/workflows/frontend-tests.yml
