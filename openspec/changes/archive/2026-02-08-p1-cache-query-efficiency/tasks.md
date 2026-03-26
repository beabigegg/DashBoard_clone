## 1. Cache Structure and Sync Refactor

- [x] 1.1 Define canonical per-domain cache representation and remove redundant parallel structures.
- [x] 1.2 Implement version/watermark-based incremental sync path for eligible non-full-snapshot datasets.
- [x] 1.3 Keep `resource` and `wip` full-table cache behavior while optimizing surrounding parse/index pipelines.

## 2. Indexed Query Acceleration

- [x] 2.1 Add index builders for high-frequency filter columns used by report endpoints.
- [x] 2.2 Refactor read paths to use indexed selection and reduce broad DataFrame copy operations.
- [x] 2.3 Add fallback and reconciliation logic to guarantee correctness under incremental/index drift.

## 3. Frontend Compute Reuse Expansion

- [x] 3.1 Extract shared Vite compute modules for KPI/filter/chart/table derivations.
- [x] 3.2 Refactor report pages to consume shared modules without changing user-visible behavior.
- [x] 3.3 Validate export/header field contract consistency after compute shift.

## 4. Performance Validation and Docs

- [x] 4.1 Add benchmark fixtures for baseline vs refactor latency/memory comparison.
- [x] 4.2 Surface cache memory amplification and index efficiency telemetry in health/admin outputs.
- [x] 4.3 Update README/README.mdj with cache strategy constraints and performance governance rules.
