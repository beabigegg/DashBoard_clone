## 1. Runtime Resilience Diagnostics Hardening

- [x] 1.1 Add shared resilience threshold/recommendation helpers for health/admin payloads.
- [x] 1.2 Extend watchdog restart state to include bounded restart history and churn summary.
- [x] 1.3 Expose thresholds/churn/recommendation fields in `/health`, `/health/deep`, `/admin/api/system-status`, and `/admin/api/worker/status`.

## 2. Frontend WIP Module Reuse

- [x] 2.1 Add shared Vite core autocomplete/filter utility module.
- [x] 2.2 Refactor WIP overview/detail modules to consume shared autocomplete utilities while preserving behavior.
- [x] 2.3 Verify Vite build output remains valid for single-port backend delivery.

## 3. Validation Coverage

- [x] 3.1 Add backend tests for resilience diagnostics and restart churn telemetry contracts.
- [x] 3.2 Add frontend tests for shared autocomplete request parameter behavior.
- [x] 3.3 Run focused backend/frontend validation commands and record pass results.

## 4. Documentation Alignment

- [x] 4.1 Update `README.md` architecture/operations sections to reflect latest resilience and frontend-governance model.
- [x] 4.2 Add/update `README.mdj` to mirror latest architecture contract for your requested documentation path.
- [x] 4.3 Update migration runbook notes to include documentation-alignment gate.
