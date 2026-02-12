# Deferred Route Modernization Observability Checkpoints

## Route Governance Signals

1. `navigation_contract_mismatch_total`
- Source: `/api/portal/navigation` diagnostics.
- Alert condition: non-zero for deferred-promoted routes.

2. `route_contract_missing_metadata_total`
- Source: route governance CI script.
- Alert condition: >0 in block mode for `/tables`, `/excel-query`, `/query-tool`, `/mid-section-defect`.

## Quality Gate Signals

1. `quality_gate_failed_total{gate_id}`
- Source: quality gate report.
- Alert condition: any mandatory gate failed for deferred-promoted routes.

2. `manual_acceptance_pending_routes`
- Source: manual acceptance records.
- Alert condition: cutover attempted with pending sign-off for deferred routes.

3. `pre_change_confirmation_missing`
- Source: pre-change confirmation records.
- Alert condition: implementation started without recorded confirmation.

## Fallback and Rollback Signals

1. `deferred_route_runtime_fallback_served_total`
- Should remain zero after fallback retirement milestone for each route.

2. `content_cutover_flag_rollbacks_total{route}`
- Track frequency per deferred route.

3. `legacy_bug_replay_failures_total{route}`
- Any non-zero indicates carry-over risk and blocks sign-off.

## Cutover Sequence Signals

1. `deferred_route_cutover_sequence_violation`
- Alert condition: route cutover attempted out of planned sequence.

2. `deferred_route_signoff_blocked_by_bug_replay`
- Alert condition: sign-off blocked due to reproduced legacy bug.
