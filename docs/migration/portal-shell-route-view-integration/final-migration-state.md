# Final Migration State: No-Iframe Full Cutover

Last updated: 2026-02-11

## Final State Summary

- Shell navigation runs as Vue Router SPA under `/portal-shell`.
- All target routes are `render_mode=native`:
  - `/wip-overview`, `/wip-detail`, `/hold-overview`, `/hold-detail`, `/hold-history`, `/resource`, `/resource-history`, `/qc-gate`, `/job-query`, `/excel-query`, `/query-tool`, `/tmtt-defect`.
- Shell content path does not use iframe embedding.
- `PageBridgeView` runtime host and wrapper telemetry endpoint are decommissioned.

## Contract State

- Source of truth remains:
  - `docs/migration/portal-shell-route-view-integration/route_migration_contract.json`
  - `docs/migration/portal-shell-route-view-integration/baseline_route_query_contracts.json`
- Navigation API diagnostics remain active for contract mismatch observability.

## Evidence Index

- Wave A smoke evidence: `wave-a-smoke-evidence.json`
- Wave B smoke evidence: `wave-b-native-smoke-evidence.json`
- Wave B parity evidence: `wave-b-parity-evidence.json`
- Gate report: `cutover-gates-report.json`
- Visual snapshots: `visual-regression-snapshots.json`
