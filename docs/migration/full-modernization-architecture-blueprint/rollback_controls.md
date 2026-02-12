# Full Modernization Rollback Controls

## Route-Level Reversion Controls

- `PORTAL_SPA_ENABLED=false`:
  Disable shell-first navigation runtime globally.
- Route-scoped contract fallback:
  Mark route contract with fallback strategy and redeploy shell assets.
- Content cutover feature flag:
  Disable route-level modernized content path while keeping shell runtime up.

## False-Positive Gate Handling

1. Capture failing gate output and route impact.
2. Confirm whether failure is test flake or product defect.
3. If false-positive and production risk is high:
- Temporarily switch gate severity from `block` to `warn`.
- Record waiver with owner, reason, expiry.
4. Restore `block` mode after corrective action.

## Required Rollback Evidence

- Incident timestamp and impacted routes.
- Gate IDs that triggered rollback.
- Route contract state before/after rollback.
- Manual acceptance and known-bug replay references.
