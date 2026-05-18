# CI/CD Gate Plan — migrate-material-trace-ts

## Change Summary

Pure TypeScript migration of `frontend/src/material-trace/` (`main.js → main.ts`,
`App.vue` gains `lang="ts"`, `tsconfig.json` gains `"src/material-trace/**/*"`).
No behavior change, no API change, no new dependencies.

## Required Gates for This Change

| gate | tier | required | trigger | command/workflow | artifact |
|---|---:|:---:|---|---|---|
| frontend-type-check | 1 | yes | pull_request | `cd frontend && npm run type-check` | — |
| frontend-build | 1 | yes | pull_request | `cd frontend && npm run build` | dist/ |
| frontend-unit | 1 | yes | pull_request | `cd frontend && npm run test` | vitest report |
| css-governance | 1 | yes | pull_request | `cd frontend && npm run css:check` | governance report |
| material-trace-e2e | 2 | no (informational) | pull_request | `pytest tests/e2e/test_material_trace_e2e.py -m local_e2e` | — |

All Tier 1 gates run via `.github/workflows/frontend-tests.yml` (`frontend-unit-tests` job).
See `contracts/ci/ci-gate-contract.md §Gate Compatibility Notes` for the tsconfig scope
expansion note (schema-version 1.3.12 → 1.3.13, `"src/material-trace/**/*"` added to include).

## CI/CD Workflow

No workflow file changes required. All four Tier 1 gates are already present in
`.github/workflows/frontend-tests.yml`:

- `npm run type-check` — step "Type check (vue-tsc --noEmit)", `continue-on-error: true`
- `npm run test` — step "Run vitest suite"
- `npm run build` — not an explicit step; verified locally as part of Tier 0 before PR
- `npm run css:check` — step present in the same job

The `frontend-tests.yml` path filter (`frontend/src/**`) already triggers on
`material-trace/` file changes. No new jobs, no new secrets, no new runners needed.

The material-trace e2e gate (`pytest ... -m local_e2e`) is informational (`continue-on-error: true`),
consistent with browser-driven tests that require a running server. It runs as a
best-effort check and does not block merge.

## Promotion Policy

`frontend-type-check` is currently informational (`continue-on-error: true`) per contract.
Promotion to required follows the standard Informational Gate Promotion Policy in
`contracts/ci/ci-gate-contract.md §Informational Gate Promotion Policy`
(20 calendar days or 60 runs, pass rate above threshold, failures triaged, runtime
within limit, owner assigned).

No other gate tier changes in this change.

## Rollback Policy

This is a source-file-only TypeScript migration. No DB schema changes, no parquet
spool files (query-tool pattern — on-demand Oracle, no persistent DuckDB parquet),
no cache key changes, no new API surface.

Rollback procedure:
1. Revert the PR (git revert or re-open previous commit).
2. No Redis flush, no parquet cleanup, no DB migration down-step required.
3. Tier 1 gates must be green on the reverted commit before re-merging main.

## Merge Eligibility

Mergeable when all four Tier 1 gates pass:
- `frontend-type-check` (zero vue-tsc errors under strict mode)
- `frontend-build` (Vite production build exits 0)
- `frontend-unit` (Vitest suite passes, including `useMaterialTrace.validation.test.js`)
- `css-governance` (no scoping violations introduced)

Informational gate failure (`material-trace-e2e`) does not block merge.
