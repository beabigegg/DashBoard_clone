## 1. Program Governance Baseline

- [x] 1.1 Publish a frozen in-scope/out-of-scope route matrix for this phase (include `/admin/pages`, `/admin/performance`; exclude `/tables`, `/excel-query`, `/query-tool`, `/mid-section-defect`)
- [x] 1.2 Add modernization governance documentation for phase completion criteria and legacy deprecation milestones
- [x] 1.3 Create an exception registry format for temporary route/style exceptions (owner + milestone)

## 2. Shell Route Contract Expansion (In Scope)

- [x] 2.1 Extend shell route contract metadata to cover all in-scope routes for this phase
- [x] 2.2 Add governed navigation target definitions for `/admin/pages` and `/admin/performance`
- [x] 2.3 Ensure route visibility/access policy metadata is validated for in-scope routes
- [x] 2.4 Add CI contract checks that fail on missing in-scope route metadata

## 3. Canonical Routing and Compatibility Policy

- [x] 3.1 Define canonical shell entry behavior for in-scope report routes
- [x] 3.2 Implement explicit compatibility policy for direct non-canonical route entry
- [x] 3.3 Verify query-semantics compatibility for in-scope routes under canonical/compatibility paths

## 4. Admin Surface Modernization Integration

- [x] 4.1 Integrate `/admin/pages` and `/admin/performance` into shell-governed navigation flow
- [x] 4.2 Preserve backend auth/session authority while modernizing shell navigation governance
- [x] 4.3 Add admin visibility/access behavior tests for shell-governed admin targets

## 5. Style Isolation and Token Enforcement

- [x] 5.1 Inventory in-scope route styles for page-global selector usage (`:root`, `body`) and classify required refactors
- [x] 5.2 Refactor in-scope route-local styles to scoped/container-based ownership
- [x] 5.3 Move shared visual semantics to token-backed Tailwind/shared layers
- [x] 5.4 Add style-governance lint/check rules for in-scope routes and exception handling

## 6. Page-Content Modernization Safety (Charts/Filters/Interactions)

- [x] 6.1 Define route-level content contracts for in-scope pages (filter input semantics, query payload structure, chart data shape, state transitions)
- [x] 6.2 Build golden fixtures and parity assertions for chart/filter critical states before cutover
- [x] 6.3 Add interaction parity checks for critical flows (filter apply/reset, chart drill/selection, empty/error states)
- [x] 6.4 Add route-scoped feature flags and immediate rollback controls for content cutover
- [x] 6.5 Define a per-route manual acceptance checklist for chart/filter/page-content migration
- [x] 6.6 Require manual acceptance sign-off for each route before moving to the next route
- [x] 6.7 Require parity pass + manual acceptance sign-off before legacy content path retirement
- [x] 6.8 Create route-level known-bug baselines for migrated scope before implementation begins
- [x] 6.9 Add mandatory "BUG revalidation during migration" checklist items to manual acceptance for each route
- [x] 6.10 Block route sign-off and legacy retirement if known legacy bugs are reproduced in the modernized route

## 7. Asset Readiness and Fallback Retirement (In Scope)

- [x] 7.1 Define required in-scope asset readiness checks for build/release pipeline
- [x] 7.2 Enforce fail-fast release behavior when required in-scope assets are missing
- [x] 7.3 Retire runtime fallback posture for in-scope routes per governance milestones
- [x] 7.4 Keep deferred route fallback posture unchanged in this phase and document follow-up linkage

## 8. Frontend Quality Gate Modernization

- [x] 8.1 Define mandatory functional parity checks for in-scope modernization routes
- [x] 8.2 Define visual regression checkpoints for critical states in in-scope routes
- [x] 8.3 Define accessibility checks (keyboard flows, aria semantics, reduced-motion behavior)
- [x] 8.4 Define performance budgets and measurement points for shell/route behavior
- [x] 8.5 Configure gate severity policy (warn mode rollout -> blocking mode promotion)

## 9. Test and CI Wiring

- [x] 9.1 Extend frontend test suite for new route governance/admin scenarios
- [x] 9.2 Extend backend/integration tests for canonical routing and compatibility behavior
- [x] 9.3 Add CI jobs for route-governance completeness, quality-gate execution, and asset readiness checks
- [x] 9.4 Ensure deferred routes are excluded from this phase blocking criteria

## 10. Migration and Rollback Runbook

- [x] 10.1 Update runbook with phased rollout steps and hold points for modernization gates
- [x] 10.2 Document rollback controls for gate false positives and route-level reversion
- [x] 10.3 Add operational observability checkpoints for route governance and gate outcomes

## 11. Follow-up Change Preparation (Deferred Routes)

- [x] 11.1 Create a linked follow-up modernization change for `/tables`, `/excel-query`, `/query-tool`, `/mid-section-defect`
- [x] 11.2 Transfer deferred-route requirements and acceptance criteria into the follow-up change
- [x] 11.3 Record explicit handoff from this phase to the deferred-route phase
