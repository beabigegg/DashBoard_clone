# Phased Rollout Plan (Canary)

## Feature switch

- Primary switch: `PORTAL_SPA_ENABLED`
- Canary enabled users/groups are routed to `/portal-shell`; others remain on `/` route-based portal.

## Phases

1. Phase A (Internal): dev/admin users only, 1 day.
2. Phase B (Canary): 10-20% target users, 2-3 days.
3. Phase C (Broad): 50% users if gates are green for 24h.
4. Phase D (Full): 100% after cutover gates pass.

## Success thresholds

- Route availability (P0): >= 99.9% 2xx/3xx.
- Client runtime error rate on critical paths: 0 unhandled exceptions.
- Drawer parity drift: 0 mismatches (admin/non-admin route sets).
- Wrapper launch success (`launch` telemetry): >= 99%.

## Error thresholds (rollback trigger)

- P0 route availability < 99.5% in any 30-minute window.
- Any critical workflow smoke failure.
- Drawer parity mismatch count > 0 after deployment.
- Wrapper telemetry error rate >= 2% sustained 30 minutes.
