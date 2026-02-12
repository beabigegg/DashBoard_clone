# Modernization Observability Checkpoints

## Route Governance Signals

1. `navigation_contract_mismatch_total`
- Source: `/api/portal/navigation` diagnostics.
- Alert condition: non-zero for in-scope routes.

2. `route_contract_missing_metadata_total`
- Source: route governance CI script.
- Alert condition: >0 in block mode.

## Quality Gate Signals

1. `quality_gate_failed_total{gate_id}`
- Source: quality gate report.
- Alert condition: any mandatory gate failed.

2. `manual_acceptance_pending_routes`
- Source: manual acceptance records.
- Alert condition: cutover attempted with pending sign-off.

## Fallback and Rollback Signals

1. `in_scope_runtime_fallback_served_total`
- Should remain zero after fallback retirement milestone.

2. `content_cutover_flag_rollbacks_total`
- Track frequency and route impact.

3. `legacy_bug_replay_failures_total`
- Any non-zero indicates carry-over risk and blocks sign-off.
