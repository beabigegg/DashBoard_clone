# Deferred Route Modernization Governance Milestones

## Upstream Reference

- Phase 1: `full-modernization-architecture-blueprint`
- Handoff: `docs/migration/full-modernization-architecture-blueprint/deferred_route_handoff.md`

## Phase Completion Criteria

A phase is complete only when all criteria below are true:

1. Route governance: 100% of in-scope deferred routes in `route_scope_matrix.json` have valid shell contract metadata and ownership with scope promoted to `in-scope`.
2. Style governance: deferred route-local styles do not introduce page-global selectors (`:root`, `body`) unless recorded in exception registry.
3. Quality governance: functional parity, visual checkpoints, accessibility checks, and performance budgets pass at configured gate severity.
4. Content safety governance: page-content parity evidence + manual acceptance sign-off exist for each migrated deferred route.
5. Bug carry-over governance: known-bug replay checks for migrated scope do not reproduce legacy defects.
6. Pre-change confirmation: each deferred route has an approved pre-change confirmation record before implementation begins.

## Legacy Deprecation Milestones

- 2026-02-19: deferred route contract CI completeness gate enabled in `warn` mode.
- 2026-02-26: deferred route contract CI completeness gate promoted to `block` mode.
- 2026-03-05: deferred route asset readiness gate promoted to `block` mode.
- 2026-03-12: runtime fallback posture retired for deferred routes in production policy.
- 2026-03-19: unresolved style exceptions past milestone fail modernization review.

## Route Cutover Sequence

Routes are cut over one at a time in the following planned order:

1. `/tables`
2. `/excel-query`
3. `/query-tool`
4. `/mid-section-defect`

Next route cutover is blocked until current route has:
- Parity pass (golden fixtures + interaction checks)
- Manual acceptance sign-off
- Known-bug replay pass
