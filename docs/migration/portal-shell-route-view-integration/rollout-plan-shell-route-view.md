# Shell Route-View Cutover Rollout Plan

Last updated: 2026-02-11

## Objectives

- Complete no-iframe shell cutover with zero P0 regressions.
- Keep rollback recovery under 15 minutes.
- Enforce G1~G7 gate pass before each promotion step.

## Phased Rollout

1. Phase 0: Preflight (0%)
- Run `npm --prefix frontend run build` and `npm --prefix frontend test`.
- Run gate suite: `pytest tests/test_cutover_gates.py tests/test_route_view_migration_baseline.py -q`.
- Validate `cutover-gates-report.json` is all-pass.

2. Phase 1: Canary (10%)
- Enable `PORTAL_SPA_ENABLED=true` on one canary instance.
- Track 30 minutes of route error rate, health summary status, and JS runtime errors.
- Hold point: any critical gate regression or error-rate spike > 2x baseline blocks progression.

3. Phase 2: Partial (50%)
- Expand SPA shell to half of instances.
- Monitor dashboard metrics for at least 60 minutes.
- Hold point: unresolved P0/P1 on Wave A/B smoke pages.

4. Phase 3: Full (100%)
- Enable SPA shell on all instances.
- Keep heightened monitoring window for 24 hours.
- Keep rollback kill-switch ready during the full window.

## Thresholds

- HTTP 5xx on shell routes: < 1.0% (5-min window).
- `/health` degraded/unhealthy ratio: < 5% of polls.
- JS runtime errors (`pageerror`/uncaught): zero critical occurrences.
- Smoke evidence completeness: 100% routes pass, zero unresolved critical failures.

## Hold Points

- H1: Preflight gate mismatch.
- H2: Canary route errors exceed threshold.
- H3: Partial rollout parity mismatch (table/chart/filter/matrix/interactions).
- H4: Health summary or admin entry regression.
