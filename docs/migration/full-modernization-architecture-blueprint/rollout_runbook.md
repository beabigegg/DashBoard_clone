# Full Modernization Rollout Runbook

## Phase Sequence

1. Governance freeze
- Confirm `route_scope_matrix.json` has no pending route-scope changes.
- Confirm exception registry entries include owner + milestone.

2. Route governance enforcement
- Run route contract completeness checks in warn mode.
- Fix all in-scope metadata gaps.
- Promote route governance checks to block mode.

3. Style/content hardening
- Apply style isolation checks for in-scope routes.
- Execute parity checks and manual acceptance route-by-route.
- Run known-bug replay checks per route.

4. Asset/gate enforcement
- Validate in-scope asset readiness.
- Run quality gate suite (functional, visual, accessibility, performance).
- Promote gate severity from warn to block according to policy.

## Hold Points

- Hold-1: Any in-scope route missing contract metadata.
- Hold-2: Any unresolved style exception past milestone.
- Hold-3: Any parity failure or known-bug replay failure.
- Hold-4: Any mandatory quality gate failure in block mode.

## Promotion Rule

Promotion is allowed only when all hold points are clear and no deferred-route checks were incorrectly included as blockers.
