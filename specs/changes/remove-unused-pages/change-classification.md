# Change Classification

## Change Types
- primary: code-removal (dead-code cleanup)
- secondary: bug-fix (production-history vite config gap), contract-update (api-inventory / css-inventory pruning)

## Risk Level
- medium

## Impact Radius
- cross-module

## Tier
- 2

## Architecture Review Required
- no
- reason: n/a (reversal of existing wiring; no new design decisions, no module-boundary changes)

## Required Artifacts
Always required: change-request.md, change-classification.md, implementation-plan.md, test-plan.md, ci-gates.md, tasks.yml, context-manifest.md

## Optional Artifacts (default: no — set yes only with explicit reason)

| artifact | create? | reason |
|---|---|---|
| current-behavior.md | no | wiring state already captured in change-request "Pre-audit findings" |
| proposal.md | no | scope is mechanical removal; no product decision needed |
| spec.md | no | no new behavior to specify |
| design.md | no | no architecture review required |
| qa-report.md | no | routine cleanup; agent-log pointer sufficient |
| regression-report.md | no | regression scope captured in test-plan; agent-log sufficient unless failures found |
| visual-review-report.md | no | no UI surface changes (only removing pages and a build-config entry) |
| monkey-test-report.md | no | n/a |
| stress-soak-report.md | no | n/a |

## Required Contracts
- API: contracts/api/api-inventory.md — remove `tables` endpoints; confirm `admin-performance` / `admin-user-usage-kpi` are not listed (or remove if present)
- CSS/UI: contracts/css/css-inventory.md — remove `tables/style.css`, `admin-performance/style.css`, `admin-user-usage-kpi/style.css` entries
- Env: none
- Data shape: none
- Business logic: contracts/business/business-rules.md — review only; modify only if page-registry / navigation rules reference removed pages
- CI/CD: contracts/ci/ci-gate-contract.md — review only; patch bump if frontend-build gate inventory changes (vite config entry for production-history is additive, may warrant patch bump)

## Required Tests
- unit: delete legacy frontend tests for admin-performance, admin-user-usage-kpi, tables; verify suite stays green
- contract: cdd-kit validate passes after inventory pruning
- integration: backend tests for tables Flask route removal; audit test files for removed redirect handlers
- E2E: delete test_admin_performance_e2e.py, test_admin_user_usage_kpi_e2e.py, test_tables_e2e.py; audit playwright suite
- visual: none
- data-boundary: none
- resilience: none
- fuzz/monkey: none
- stress: none
- soak: none

## Required Agents
- contract-reviewer
- test-strategist
- ci-cd-gatekeeper
- implementation-planner
- backend-engineer
- frontend-engineer
- qa-reviewer

## Inferred Acceptance Criteria
- AC-1: After the change, `frontend/src/tables/`, `frontend/src/admin-performance/`, and `frontend/src/admin-user-usage-kpi/` directories no longer exist in the repo.
- AC-2: `frontend/vite.config.ts` `rollupOptions.input` no longer references `tables`, `admin-performance`, or `admin-user-usage-kpi`, AND now includes `production-history`.
- AC-3: Running `cd frontend && npm run build` produces a dist bundle that contains a `production-history` entry chunk and no `tables`, `admin-performance`, or `admin-user-usage-kpi` entry chunks.
- AC-4: Portal-shell router/navigation/sidebar no longer expose routes for the three removed pages; visiting their former URLs returns 404 (or the documented deprecated-redirect target if the Flask redirect is kept per scope).
- AC-5: Flask `tables` blueprint and routes are removed; `pytest` passes with no references to removed handlers.
- AC-6: `contracts/api/api-inventory.md` and `contracts/css/css-inventory.md` contain no entries for the three removed pages; both contracts have appropriate patch-version bumps and `contracts/CHANGELOG.md` entries.
- AC-7: All Vitest legacy tests and Python e2e tests for the three removed pages are deleted; full test suite (`pytest`, `cd frontend && npm run test`, `cd frontend && npm run type-check`) passes.
- AC-8: `cdd-kit validate` and `cdd-kit gate remove-unused-pages` pass on the final state.

## Tasks Not Applicable
- not-applicable: 1.3 (no architecture review / design.md), 2.3 (no env contract), 2.4 (no data-shape contract), 3.4 (no monkey tests), 3.5 (no stress/soak), 4.3 (no env/deploy change), 5.1 (no UI surface changes), 5.2 (no visual review), 6.4 (no nightly/weekly/manual gates defined)

## Clarifications or Assumptions
- Assumption: the `tables` Flask route lives in one of `admin_routes.py`, `dashboard_routes.py`, or `analytics_routes.py`; if it is registered elsewhere, backend-engineer should file a CER rather than search broadly.
- Assumption: `admin-performance` and `admin-user-usage-kpi` Flask deprecated redirects MAY be left in place per change-request Non-goals. Implementation-planner should make the keep-vs-remove call explicit in `implementation-plan.md`; default is keep to minimize bookmarked-URL breakage.
- Assumption: vite config fix for `production-history` is in-scope and required per change-request Business / User Goal.
- Assumption: `frontend/src/admin-performance/` and `frontend/src/admin-user-usage-kpi/` are truly orphaned (no imports from any kept module); frontend-engineer must grep for residual imports before deletion and file a CER if surprise references appear.
