## Why

`full-modernization-architecture-blueprint` intentionally deferred these routes:

- `/tables`
- `/excel-query`
- `/query-tool`
- `/mid-section-defect`

Those routes still run on legacy posture (direct-entry-first + fallback continuity + mixed style ownership). A dedicated follow-up change is required to finish modernization without reopening scope in phase 1.

## What Changes

- Promote all deferred routes to first-class in-scope shell-governed targets.
- Apply canonical shell routing policy and explicit direct-entry compatibility behavior for each deferred route.
- Modernize deferred route page-content flow (filters/charts/interactions) with contract-first parity gates.
- Require route-by-route pre-change confirmation records before any implementation work starts on each deferred route.
- Apply the same mandatory manual acceptance + BUG revalidation blocking policy used in phase 1.
- Move deferred routes from fallback-era runtime posture to asset-readiness + governed retirement posture.

## Capabilities

### Modified Capabilities
- `unified-shell-route-coverage`: deferred routes become in-scope and CI-blocking for route contract completeness.
- `spa-shell-navigation`: deferred routes adopt canonical shell entry policy and governed compatibility behavior.
- `page-content-modernization-safety`: deferred routes require contract baselines, parity evidence, manual sign-off, and known-bug revalidation.
- `asset-readiness-and-fallback-retirement`: deferred routes adopt release-time asset checks and governed fallback retirement milestones.

## Impact

- Frontend route modules for `/tables`, `/excel-query`, `/query-tool`, `/mid-section-defect`.
- Shell contract and navigation governance in `frontend/src/portal-shell/**`.
- Backend route handlers serving deferred routes and compatibility behavior.
- Quality gate artifacts, runbook updates, and rollout/rollback policy for deferred-route cutover.
- Scope boundary clarification: this follow-up explicitly targets deferred routes (currently `dev` in page status) and does not require routes to already be `released` before modernization.
