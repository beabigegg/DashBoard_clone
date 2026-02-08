## 1. Root Cutover Finalization

- [x] 1.1 Inventory all remaining runtime/test/deploy references to nested `DashBoard/` paths.
- [x] 1.2 Remove or replace nested-path dependencies so root scripts and app startup are self-contained.
- [x] 1.3 Define and execute root-only smoke startup checks.

## 2. Vite Full Page Modularization

- [x] 2.1 Create/standardize Vite entries for Portal, Resource Status, Resource History, Job Query, Excel Query, and Tables.
- [x] 2.2 Extract shared frontend core modules (API wrappers, table/tree helpers, field contract helpers).
- [x] 2.3 Replace targeted inline scripts with module bootstraps while preserving fallback behavior.
- [x] 2.4 Update template asset resolution to support per-page Vite bundles.

## 3. Frontend Compute Shift

- [x] 3.1 Identify display-layer computations eligible for frontend migration and document parity rules.
- [x] 3.2 Migrate selected calculations page by page with deterministic helper functions.
- [x] 3.3 Add parity fixtures/tests comparing baseline backend vs migrated frontend outputs.

## 4. Field Contract Governance

- [x] 4.1 Introduce shared field contract registry for UI/API/Export mapping.
- [x] 4.2 Apply the registry to Job Query and Resource History completely (including headers and semantic types).
- [x] 4.3 Extend consistency checks to additional pages and exports.

## 5. Cache Observability Hardening

- [x] 5.1 Expand cache telemetry fields in health/deep-health outputs.
- [x] 5.2 Add explicit degraded-mode visibility when Redis is unavailable.
- [x] 5.3 Validate cache behavior and telemetry under L1-only and L1+L2 modes.

## 6. Migration Gates and Rollout

- [x] 6.1 Define gate checklist for cutover readiness (tests, parity, build, health).
- [x] 6.2 Document rollout steps and operator runbook for the final cutover.
- [x] 6.3 Document rollback procedure and rehearse rollback validation.

## 7. Validation and Documentation

- [x] 7.1 Run focused unit/integration checks in root project and record evidence.
- [x] 7.2 Record known environment-dependent gaps (Oracle/Redis) and mitigation plan.
- [x] 7.3 Update README/docs to declare final root-first workflow and migration status.
