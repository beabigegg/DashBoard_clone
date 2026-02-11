# Wrapper Decommission Report

## Decision

Legacy shell wrapper mode has been decommissioned after rewrite milestone validation.

## Changes Applied

- Removed shell wrapper route branch:
  - `frontend/src/portal-shell/router.js`
  - `frontend/src/portal-shell/App.vue`
- Removed wrapper-specific frontend artifacts:
  - deleted `frontend/src/portal-shell/constants.js`
  - deleted `frontend/src/portal-shell/views/LegacyWrapperView.vue`
- Removed backend wrapper telemetry endpoint:
  - deleted `/api/portal/wrapper-telemetry` in `src/mes_dashboard/app.py`

## Operational Outcome

- Portal shell navigation now uses direct page-bridge behavior only.
- Legacy page access remains available via direct routes.
- Wrapper telemetry contract is retired.

## Validation

- Route and template integration tests updated and passing.
- Cutover gate tests remain green after wrapper removal.
