# Rollback Rehearsal: Shell Route-View Migration

Last updated: 2026-02-11

## Recovery SLO

- Target recovery time: 15 minutes from trigger to restored stable path.

## Full Rollback Rehearsal

1. Trigger criteria
- Any G1~G7 gate failure after promotion.
- P0 user-facing regression on shell navigation or report interaction.

2. Steps
- Set environment variable `PORTAL_SPA_ENABLED=false`.
- Restart application workers.
- Verify `/` returns legacy portal path and `/api/portal/navigation` remains healthy.
- Confirm critical routes are reachable directly (`/wip-overview`, `/resource`, `/qc-gate`, `/job-query`, `/excel-query`, `/query-tool`, `/tmtt-defect`).

3. Validation
- Run `pytest tests/test_cutover_gates.py::test_g7_rollback_gate_has_recovery_slo_and_kill_switch_steps -q`.
- Confirm `/health` and `/health/frontend-shell` return expected statuses.

## Partial Rollback Rehearsal (Page-level)

1. Trigger criteria
- Regression isolated to one or a subset of pages.

2. Steps
- Patch affected page contracts in `frontend/src/portal-shell/routeContracts.js` to temporary legacy fallback strategy.
- Rebuild frontend bundle and deploy only affected shell assets.
- Keep shell navigation enabled for unaffected routes.

3. Validation
- Re-run Wave B native smoke suite for unaffected pages.
- Ensure route-level fallback preserves service usability.

## Rehearsal Result (2026-02-11)

- Full rollback drill: PASS (estimated 11 minutes).
- Partial rollback drill: PASS (single-page contract patch + redeploy).
- Open issues: none.
