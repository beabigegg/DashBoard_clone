# Portal No-Iframe Migration Rollback Rehearsal Runbook

## Objective

Validate that navigation can be restored to pre-cutover stable behavior within target SLO.

- Target recovery SLO: <= 15 minutes

## Trigger Conditions

Execute rollback when any of the following occur after cutover:

- P0 route unavailable or broken workflow.
- Drawer visibility parity mismatch.
- Critical API payload contract mismatch causing page failure.
- Severe runtime JS errors on critical user paths.

## Preconditions

- Feature-flag/env toggle path for shell cutover is in place.
- Latest baseline snapshots are available under `docs/migration/portal-no-iframe/`.
- On-call owner and rollback owner are assigned.

## Rehearsal Steps

1. Enable new navigation mode in staging/canary.
2. Execute parity checklist (`parity_checklist.md`) on critical routes.
3. Force simulated rollback trigger (toggle off new mode).
4. Re-run critical smoke checks:
   - portal load
   - drawer visibility
   - wip overview/detail flow
   - resource history query path
5. Record elapsed recovery time and failures.

## Verification Criteria

- Toggle change takes effect without manual code rollback.
- Critical routes recover to expected behavior.
- Recovery time is within SLO.
- No residual hard-failure state remains.

## Post-Rehearsal Record

- Date:
- Environment:
- Operator:
- Trigger reason:
- Recovery duration:
- Issues found:
- Follow-up actions:
