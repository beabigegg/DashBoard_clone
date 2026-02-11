# Migration Observability Dashboard/Report

Last updated: 2026-02-11

## Monitoring Scope

- Route errors: shell route 4xx/5xx, unknown-route fallback count, dynamic module load errors.
- Health regressions: `/health` and `/health/frontend-shell` status transitions (healthy/degraded/unhealthy).
- Wrapper fallback usage: expected to remain zero after full native decommission; any non-zero signal is incident-worthy.

## Key Metrics

1. `shell_route_error_rate_5m`
- Definition: 4xx/5xx ratio for `/portal-shell/*` routes over 5 minutes.
- Threshold: warning at 0.5%, critical at 1.0%.

2. `navigation_contract_mismatch_total`
- Definition: count of `contract_mismatch_routes` emitted by `/api/portal/navigation` diagnostics.
- Threshold: must be 0.

3. `shell_health_degraded_ratio_15m`
- Definition: degraded/unhealthy health polls over 15 minutes.
- Threshold: warning at 5%, critical at 10%.

4. `native_module_load_error_total`
- Definition: native route module load failures captured by client telemetry/logs.
- Threshold: must be 0 for stable rollout.

5. `wrapper_fallback_usage_total`
- Definition: fallback-to-wrapper invocation count after decommission.
- Threshold: must be 0.

## Dashboard Panels

- Panel A: Route errors by route id and render mode.
- Panel B: Health summary state timeline with error/warning counts.
- Panel C: Route contract mismatch and unknown-route fallback trend.
- Panel D: Wave A/Wave B smoke pass trend and gate pass/fail timeline.
- Panel E: Wrapper fallback usage (target line at zero).

## Operational Notes

- During canary/partial rollout, all panels must stay within threshold before progressing.
- Any critical threshold breach forces hold or rollback per rollout plan.
