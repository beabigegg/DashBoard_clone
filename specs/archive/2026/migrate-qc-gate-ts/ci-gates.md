---
change-id: migrate-qc-gate-ts
contract-version: 1.3.8
last-updated: 2026-05-13
---

# CI Gates — migrate-qc-gate-ts

Pure TypeScript migration of one frontend feature app:
- `frontend/src/qc-gate/` (`main.js→main.ts`, `App.vue`, `composables/useQcGateData.js→.ts`, `components/LotTable.vue`, `components/QcGateChart.vue`)

No backend, API, or CSS changes. `tsconfig.json` scope expanded to cover `src/qc-gate/**/*` per `contracts/ci/ci-gate-contract.md` § 1.3.8.

## Pre-merge Gates (Tier 1 — block merge)

| Gate | Tier | Command | Local Status | CI Status |
|---|---|---|---|---|
| frontend-unit | 1 | `cd frontend && npm run test` | PASSED (302/302) | PENDING |
| frontend-legacy | 1 | `cd frontend && npm run test` | PASSED | PENDING |
| css-governance | 1 | `cd frontend && npm run css:check` | PASSED (0 violations) | PENDING |
| frontend-build | 1 | `cd frontend && npm run build` | to be verified in CI | PENDING |
| contract-validate | 0 | `cdd-kit validate` | — | PENDING |
| cdd-strict-gate | 0 | `cdd-kit gate migrate-qc-gate-ts --strict` | — | PENDING |

All six are **Tier 1 / Tier 0 PR Required** gates per `contracts/ci/ci-gate-contract.md`. They block merge.

## Informational Gates (Tier 0/2 — non-blocking)

| Gate | Tier | Command | Note |
|---|---|---|---|
| frontend-type-check | 1 | `cd frontend && npm run type-check` | PASSED locally (0 errors); scope expanded to include `src/qc-gate/**/*` per ci-gate-contract.md § 1.3.8; informational per Required Check Policy |

## Nightly / Weekly Gates

| Gate | Tier | Applicable? |
|---|---|---|
| nightly-integration | 3 | N/A — no backend changes |
| stress-load | 4 | N/A — no backend changes |
| soak | 4 | N/A — no backend changes |

## Gate Status Summary

| Gate | Status |
|---|---|
| frontend-unit | PASSED (local) |
| css-governance | PASSED (local) |
| frontend-type-check | PASSED (local) |
| frontend-build | PENDING (CI) |
| contract-validate | PENDING (CI) |
| cdd-strict-gate | PENDING (CI) |

## Required Gates Statement

A PR for this change is merge-eligible when **all pending CI gates pass**: `frontend-build`, `contract-validate`, and `cdd-strict-gate`, in addition to the locally verified `frontend-unit` and `css-governance` gates.

## Workflow

Governed by `.github/workflows/frontend-tests.yml` and `.github/workflows/contract-driven-gates.yml`. All pre-merge gates trigger automatically on every PR push against `main`. The informational `frontend-type-check` runs in the same pipeline but does not block merge.

## Promotion Policy

No gate introduced in this change is a candidate for promotion — all gates already exist project-wide; this change only extends the scope of `frontend-type-check` to `src/qc-gate/**/*`. Promotion of `frontend-type-check` from informational to required follows the standard Informational Gate Promotion Policy documented in `contracts/ci/ci-gate-contract.md` (20 calendar days or 60 runs, pass rate above threshold, failures triaged, runtime within limit, owner assigned).

## Rollback Policy

This is a pure TypeScript annotation refactor — no runtime behavior change, no API change, no database migration. If a post-merge regression is detected, revert the PR via GitHub revert button. No rollback of backend, database, or asset pipeline is required.
