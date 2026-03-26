## 1. OpenSpec Scope and Parity Baseline

- [x] 1.1 Confirm report parity target pages and interaction scope (WIP overview/detail, resource status/history, query pages).
- [x] 1.2 Capture concrete parity defects in current Vite modules (runtime errors, KPI/matrix mismatch, API path inconsistency).

## 2. WIP Pages Vite Modularization

- [x] 2.1 Add Vite entries for `wip-overview` and `wip-detail`.
- [x] 2.2 Update templates to load `frontend_asset(...)` module bundles with inline fallback retention.
- [x] 2.3 Preserve legacy global handler compatibility for existing inline-triggered actions.

## 3. Report Behavior and Compute Fixes

- [x] 3.1 Fix `resource-history` module initialization/export scope error.
- [x] 3.2 Fix `resource-status` matrix selection logic and KPI zero-value rendering parity.
- [x] 3.3 Align report JSON API calls to MesApi-compatible paths for degraded retry behavior.

## 4. Field Contract and Rendering Hardening

- [x] 4.1 Patch dynamic table/query rendering to escape untrusted values.
- [x] 4.2 Verify UI table headers and export header naming consistency for touched report flows.
- [x] 4.3 Fix missing report style tokens affecting visual consistency.

## 5. Validation and Regression Guard

- [x] 5.1 Build frontend bundles and ensure new entries are emitted into backend static dist.
- [x] 5.2 Extend/update template integration tests for WIP module/fallback behavior.
- [x] 5.3 Run focused pytest suite for template/frontend/report regressions and record outcomes.
