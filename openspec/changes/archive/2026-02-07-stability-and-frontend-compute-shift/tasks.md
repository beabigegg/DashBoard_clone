## 1. P0 Runtime Resilience Baseline

- [x] 1.1 Make `database.py` read and enforce runtime pool/timeouts from settings/env instead of hardcoded constants.
- [x] 1.2 Add explicit degraded error mapping for pool exhaustion and circuit-open states (stable error codes + retry metadata).
- [x] 1.3 Update API response handling so degraded errors are returned consistently across WIP/Resource/Dashboard endpoints.
- [x] 1.4 Extend frontend `MesApi` retry/backoff policy to respect degraded error codes and avoid aggressive retries under pool exhaustion.

## 2. P0 Observability and Recovery Controls

- [x] 2.1 Extend `/health` and `/health/deep` payloads with pool configuration, saturation indicators, and degradation reason classification.
- [x] 2.2 Expose runtime-resilience diagnostics in admin status API for operations triage.
- [x] 2.3 Ensure hot-reload/restart controls preserve single-port availability and return actionable status for watchdog-driven recovery.

## 3. P1 Cache and Query Efficiency (Keep Full-Table Cache)

- [x] 3.1 Preserve `resource/wip` full-table cache as authoritative baseline while introducing indexed lookup helpers for high-frequency access paths.
- [x] 3.2 Reduce repeated full-array merge cost in resource status composition by using prebuilt lookup/index structures.
- [x] 3.3 Add cache version-coupled rebuild/update flow for derived indices and expose telemetry for index freshness.

## 4. P1 Frontend Compute Shift Expansion

- [x] 4.1 Refactor compute-heavy display transformations into reusable frontend core modules.
- [x] 4.2 Add parity fixtures/tests for newly shifted computations with explicit tolerance contracts.
- [x] 4.3 Ensure migrated pages preserve existing tab/drill-down behavior while consuming shared Vite modules.

## 5. P2 Conda/Systemd/Watchdog Runtime Alignment

- [x] 5.1 Align systemd service templates and runtime paths with conda-based execution model.
- [x] 5.2 Align startup/deploy scripts, watchdog config, and documentation to a single runtime contract.
- [x] 5.3 Define and document alert thresholds for sustained degraded state, restart churn, and retry pressure.

## 6. Validation and Migration Gates

- [x] 6.1 Add/extend tests for pool exhaustion semantics, circuit-breaker fail-fast behavior, and degraded response contracts.
- [x] 6.2 Add/extend tests for indexed cache access and frontend compute parity.
- [x] 6.3 Update migration gate/runbook docs to include resilience checks, conda-systemd rehearsal, and rollback verification.
