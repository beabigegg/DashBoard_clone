# Full Modernization Governance Milestones

## Phase Completion Criteria

A phase is complete only when all criteria below are true:

1. Route governance: 100% of in-scope routes in `route_scope_matrix.json` have valid shell contract metadata and ownership.
2. Style governance: in-scope route-local styles do not introduce page-global selectors (`:root`, `body`) unless recorded in exception registry.
3. Quality governance: functional parity, visual checkpoints, accessibility checks, and performance budgets pass at configured gate severity.
4. Content safety governance: page-content parity evidence + manual acceptance sign-off exist for each migrated in-scope route.
5. Bug carry-over governance: known-bug replay checks for migrated scope do not reproduce legacy defects.

## Legacy Deprecation Milestones

- 2026-02-20: route contract CI completeness gate enabled in `warn` mode.
- 2026-02-27: route contract CI completeness gate promoted to `block` mode.
- 2026-03-05: in-scope asset readiness gate promoted to `block` mode.
- 2026-03-12: runtime fallback posture retired for in-scope routes in production policy.
- 2026-03-19: unresolved style exceptions past milestone fail modernization review.

## Deferred Route Linkage

Deferred routes are not pass/fail criteria in this phase and are handed over to a follow-up change:

- `/tables`
- `/excel-query`
- `/query-tool`
- `/mid-section-defect`

Follow-up change handoff is recorded in `openspec/changes/deferred-route-modernization-follow-up/`.
