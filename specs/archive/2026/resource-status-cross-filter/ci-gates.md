# CI/CD Gate Plan — resource-status-cross-filter

## Required Gates for This Change

| gate | tier | required | trigger | command/workflow | artifact |
|---|---:|:---:|---|---|---|
| frontend-unit | 1 | yes | pull_request | `cd frontend && npm test` | vitest report |
| css-governance | 1 | yes | pull_request | `cd frontend && npm run css:check` | governance report |
| frontend-legacy | 1 | yes | pull_request | `cd frontend && npm run test:legacy` | node:test report |
| frontend-type-check | 2 | informational | pull_request | `cd frontend && npm run type-check` | — |

Gates not applicable to this change (frontend-only, no backend, no E2E spec, no DB, no env, no new npm deps):
`unit-mock-integration`, `playwright-critical-journeys`, `playwright-resilience`, `playwright-data-boundary`, `nightly-integration`, `stress-load`, `soak`.

## CI/CD Workflow

No new workflow files or steps are needed. The three required Tier 1 gates are already executed by `.github/workflows/frontend-tests.yml` (`frontend-unit-tests` job):

- `npm test` — Vitest picks up `frontend/tests/resource-status/useCrossFilter.test.ts` and `App.cross-filter.test.ts` via the existing `src/**/*.test.ts` glob in `frontend/vitest.config.js`. Covers test-plan.md AC-2, AC-3, AC-4, AC-6 (unit) and AC-1, AC-4, AC-8 (integration mount).
- `npm run css:check` — Rule 6 scoping assertion. Covers test-plan.md AC-7.
- `npm run test:legacy` — runs `frontend/tests/legacy/resource-status.test.js` unmodified. Covers test-plan.md AC-5, AC-6 (regression).

Workflow trigger paths (`frontend/src/**`, `frontend/tests/**`) already match all files touched by this change.

## Promotion Policy

`frontend-type-check` is informational for this change (consistent with ci-gate-contract.md §Informational Gate Promotion Policy). Promote to required after: 20 calendar days or 60 runs; pass rate above threshold; failures triaged; runtime within limit; owner assigned.

No new gates are introduced; no existing gate tier changes.

## Rollback Policy

This change is frontend-only with no backend state, no DB migration, no parquet spool, and no persistent cache writes.

Rollback procedure: revert the PR via GitHub. No additional deploy or cleanup steps are required. The composable (`useCrossFilter.ts`) and component wiring are purely client-side; reverting the commit removes all cross-filter behaviour and restores the prior state of `matrixFilter[]` / `summaryStatusFilter`.

If any Tier 1 gate turns red on `main`, no further PRs may merge until fixed (ci-gate-contract.md §Rollback Policy).

## Merge Eligibility

**mergeable** — all three Tier 1 gates (`frontend-unit`, `css-governance`, `frontend-legacy`) must be green. `frontend-type-check` is informational and does not block merge.
