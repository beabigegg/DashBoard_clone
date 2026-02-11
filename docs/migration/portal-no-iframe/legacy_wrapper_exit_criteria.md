# Legacy Wrapper Exit Criteria (Rewrite-ready)

A wrapped page is rewrite-ready only when all criteria are met.

## Functional readiness

1. Core workflows are documented with at least one deterministic smoke script per workflow.
2. Route/query contract is frozen and covered by contract tests.
3. Export/upload side effects (if any) are reproducible in test or staging.

## Technical readiness

1. Shared UI and composables can cover at least 70% of page scaffolding (filters, cards, table shell, pagination).
2. Required API payload key/type contract is stable for two consecutive releases.
3. Wrapper telemetry shows no unresolved high-severity navigation failures in the last release cycle.

## Operational readiness

1. Rollback path for rewritten page is documented and rehearsed.
2. Error budget and success threshold for canary are defined before rewrite starts.
3. Product owner confirms parity acceptance checklist for the target page.
