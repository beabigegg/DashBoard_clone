---
change-id: migrate-resource-status-ts
contract-version: 1.3.7
last-updated: 2026-05-13
---

# CI/CD Gate Plan — migrate-resource-status-ts

Governed by `contracts/ci/ci-gate-contract.md` schema 1.3.7.

## Pre-merge Gates (Tier 1 — block merge)

| gate | command | pass criteria | status |
|---|---|---|---|
| frontend-unit | `cd frontend && npm run test` | all Vitest tests green (302 tests) | PASSED |
| frontend-legacy | `cd frontend && npm run test:legacy` | all legacy node --test assertions pass (incl. `resource-status.test.js`) | PASSED |
| css-governance | `cd frontend && npm run css:check` | 0 new violations | PASSED |
| frontend-build | `cd frontend && npm run build` | Vite exits 0; no resolution failures | PENDING |
| contract-validate | `cdd-kit validate` | 0 contract violations | PENDING |
| cdd-strict-gate | `cdd-kit gate migrate-resource-status-ts --strict` | 0 open tasks, all AC green | PENDING |

## Informational Gates (Tier 0/2 — run, do not block merge)

| gate | command | pass criteria | status |
|---|---|---|---|
| frontend-type-check | `cd frontend && npm run type-check` | 0 type errors; scope expanded to include `src/resource-status/**/*` in this phase | PASSED |
| lint (Python) | `ruff check .` | 0 lint errors | N/A (no Python changes) |
| mypy | `mypy src/` | informational; no Python changes in this migration | N/A |

## Nightly / Weekly Gates

| gate | trigger | command | applicability |
|---|---|---|---|
| nightly-integration | weekly schedule / dispatch | `pytest tests/integration/ --run-integration-real -m "integration_real or multi_worker" -x` | N/A — no backend changes |
| stress-load | weekly schedule / dispatch | `pytest tests/stress/ -m "stress or load"` | N/A — no backend changes |
| soak | weekly schedule / dispatch | `pytest tests/integration/test_soak_workload.py --run-integration-real -m "soak"` | N/A — no backend changes |

## Gates Not Required for This Change

- **E2E / Playwright**: no Playwright spec exists for `resource-status`; no behavior change in this Tier 4 refactor
- **Visual regression**: pure TypeScript annotation, no template or style changes
- **Data-boundary / resilience**: no new API surface, no data contract changes
- **Backend gates (pytest, mypy, ruff)**: zero Python files modified

## Gate Status Summary

- **PASSED (local verification)**: frontend-unit, frontend-legacy, css-governance, frontend-type-check
- **PENDING (CI run required)**: frontend-build, contract-validate, cdd-strict-gate
- **N/A**: lint (Python), mypy, nightly-integration, stress-load, soak, E2E

## Required Gates Statement

PR is eligible to merge once all required Tier 1 PENDING gates pass in CI: `frontend-unit`, `frontend-legacy`, `css-governance`, `frontend-build`, `contract-validate`, `cdd-strict-gate`. The `frontend-type-check` gate remains **informational** per contract 1.3.7 — its scope expanded to include `src/resource-status/**/*` in this PR.

## Workflow

Governed by `.github/workflows/frontend-tests.yml` (frontend-unit, frontend-legacy, css-governance, frontend-type-check, frontend-build) and `.github/workflows/contract-driven-gates.yml` (contract-validate, cdd-strict-gate).

## Promotion Policy

Informational gates follow the standard Informational Gate Promotion Policy documented in `contracts/ci/ci-gate-contract.md`. Promotion requires:
1. Three consecutive passing runs on `main`.
2. A `contracts/ci/ci-gate-contract.md` PR updating the gate row's status to `required`.

No gate introduced in this change is a candidate for promotion — all gates already exist project-wide; this change only extends the scope of `frontend-type-check` to `src/resource-status/**/*`.

## Rollback Policy

This change is a pure TypeScript annotation refactor with no runtime behaviour change. Rollback is a revert of the PR. No DB migration, no feature flag, no data mutation — standard revert suffices per ci-gate-contract.md §Rollback Policy.
