# Deferred Route Modernization Rollout Runbook

## Upstream Reference

- Phase 1 runbook: `docs/migration/full-modernization-architecture-blueprint/rollout_runbook.md`

## Phase Sequence

1. Governance freeze
- Confirm `route_scope_matrix.json` has deferred routes promoted to in-scope.
- Confirm pre-change confirmations recorded for all 4 routes.
- Confirm exception registry has no unresolved blocking entries.

2. Route governance enforcement
- Run route contract completeness checks in warn mode.
- Fix all deferred-route metadata gaps.
- Promote route governance checks to block mode.

3. Per-route content modernization (sequential)
- Enable content cutover flag for first route (`/tables`).
- Execute parity checks and manual acceptance.
- Run known-bug replay checks.
- On pass: sign off and proceed to next route.
- On fail: rollback flag and investigate.

4. Cutover sequence
- `/tables` -> `/excel-query` -> `/query-tool` -> `/mid-section-defect`
- Next route blocked until current route has approved sign-off.

5. Asset/gate enforcement
- Validate deferred route asset readiness.
- Run quality gate suite (functional, visual, accessibility, performance).
- Promote gate severity from warn to block per milestones.

6. Fallback retirement
- Retire runtime fallback for deferred routes after all acceptance gates pass.

## Hold Points

- Hold-1: Any deferred route missing contract metadata or pre-change confirmation.
- Hold-2: Any parity failure or known-bug replay failure.
- Hold-3: Any mandatory quality gate failure in block mode.
- Hold-4: Cutover attempted before previous route sign-off complete.

## Promotion Rule

Promotion is allowed only when all hold points are clear for the current route in sequence.
