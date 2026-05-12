---
change-id: migrate-admin-shared-ts
contract-version: 1.3.2
last-updated: 2026-05-12
---

# CI/CD Gate Plan — migrate-admin-shared-ts

Governed by `contracts/ci/ci-gate-contract.md` schema 1.3.2.

## Pre-merge Gates (Tier 1 — block merge)

| gate | command | pass criteria | status |
|---|---|---|---|
| frontend-unit | `cd frontend && npm run test` | all Vitest tests green (incl. `tests/legacy/admin-dashboard.test.js`, `admin-performance.test.js`, `admin-user-usage-kpi.test.js`) | PASSED |
| frontend-legacy | `cd frontend && npm run test:legacy` | 35 legacy node --test assertions pass | PASSED |
| css-governance | `cd frontend && npm run css:check` | governance report: 0 violations | PASSED |
| frontend-build | `cd frontend && npm run build` | Vite exits 0; no resolution failures | PASSED |
| contract-validate | `cdd-kit validate` | 0 contract violations | PENDING |
| cdd-strict-gate | `cdd-kit gate migrate-admin-shared-ts --strict` | 0 open tasks, all AC green | PENDING |
| playwright-resilience | `cd frontend && npx playwright test tests/playwright/resilience/` | all traces pass | PENDING |
| playwright-data-boundary | `cd frontend && npx playwright test tests/playwright/data-boundary/` | all traces pass | PENDING |
| playwright-critical-journeys | `cd frontend && npx playwright test tests/playwright/hold-overview.spec.js tests/playwright/reject-history.spec.js tests/playwright/query-tool.spec.js` | all critical-journey specs pass | PENDING |

## Informational Gates (Tier 0/2 — run, do not block merge)

| gate | command | pass criteria | status |
|---|---|---|---|
| frontend-type-check | `cd frontend && npm run type-check` | 0 type errors across `src/core/**/*`, `src/shared-composables/**/*`, `src/shared-ui/**/*`, `src/admin-shared/**/*` (scope expanded in Phase 1d) | PASSED |
| lint (Python) | `ruff check .` | 0 lint errors | N/A (no Python changes) |
| mypy | `mypy src/` | informational; no Python changes in this migration | N/A |

## Nightly / Weekly Gates

| gate | trigger | command | applicability |
|---|---|---|---|
| nightly-integration | weekly schedule / dispatch | `pytest tests/integration/ --run-integration-real -m "integration_real or multi_worker" -x` | N/A — no backend changes |
| stress-load | weekly schedule / dispatch | `pytest tests/stress/ -m "stress or load"` | N/A — no backend changes |
| soak | weekly schedule / dispatch | `pytest tests/integration/test_soak_workload.py --run-integration-real -m "soak"` | N/A — no backend changes |

## Gate Status Summary

- **PASSED (local verification)**: frontend-unit, frontend-legacy, css-governance, frontend-build, frontend-type-check
- **PENDING (CI run required)**: contract-validate, cdd-strict-gate, playwright-resilience, playwright-data-boundary, playwright-critical-journeys
- **N/A**: lint (Python), mypy, nightly-integration, stress-load, soak

## Merge Eligibility Decision

PR is eligible to merge once all required gates (Tier 1 PENDING) pass in CI. The `frontend-type-check` gate remains **informational** per contract 1.3.2 — its scope expanded to include `src/admin-shared/**/*` in this PR but promotion to required follows the standard Informational Gate Promotion Policy (20 days / 60 runs).

## Workflow

Governed by `.github/workflows/frontend-tests.yml` (frontend-unit, css-governance, frontend-type-check, frontend-build) and `.github/workflows/contract-driven-gates.yml` (contract-validate, cdd-strict-gate, playwright gates).

## Rollback Policy

This change is a pure TypeScript annotation refactor with no runtime behaviour change. Rollback is a revert of the PR. No DB migration, no feature flag, no data mutation — standard revert suffices per ci-gate-contract.md §Rollback Policy.
