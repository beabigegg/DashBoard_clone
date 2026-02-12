# Deferred Route Modernization Rollback Controls

## Route-Level Reversion Controls

- **Content cutover feature flag**: Set `content_cutover_enabled: false` in `data/modernization_feature_flags.json` for the affected route to immediately revert to legacy content path.
- **PORTAL_SPA_ENABLED=false**: Disable shell-first navigation runtime globally (affects all routes).
- **Route-scoped contract fallback**: Mark route contract with fallback strategy and redeploy shell assets.

## Per-Route Rollback Procedure

1. Set `content_cutover_enabled: false` for the affected route in `modernization_feature_flags.json`.
2. Restart workers to pick up the flag change.
3. Verify legacy content path is serving correctly.
4. Record rollback in manual acceptance records with reason and timestamp.
5. Investigate root cause before re-enabling cutover.

## False-Positive Gate Handling

1. Capture failing gate output and route impact.
2. Confirm whether failure is test flake or product defect.
3. If false-positive and production risk is high:
- Temporarily switch gate severity from `block` to `warn`.
- Record waiver with owner, reason, expiry.
4. Restore `block` mode after corrective action.

## Required Rollback Evidence

- Incident timestamp and impacted route.
- Gate IDs that triggered rollback.
- Feature flag state before/after rollback.
- Manual acceptance and known-bug replay references.
