# CI/CD Gate Review

Change ID: migrate-core-to-typescript

## Required Gates for This Change

| gate | tier | required | trigger | command/workflow | artifact |
|---|---:|---:|---|---|---|
| contract-validate | 0 | yes | local pre-PR | `cdd-kit validate` | — |
| frontend-type-check | 1 | informational | push / PR | `cd frontend && npm run type-check` (`.github/workflows/frontend-tests.yml`) | — |
| frontend-unit | 1 | yes | push / PR | `cd frontend && npm run test` (`.github/workflows/frontend-tests.yml`) | vitest report |
| frontend-build | 1 | yes | PR (e2e-critical job) | `cd frontend && npm run build` (`.github/workflows/contract-driven-gates.yml`) | — |
| css-governance | 1 | yes | push / PR | `cd frontend && npm run css:check` (`.github/workflows/contract-driven-gates.yml`) | governance report |

Gates not triggered by this change (no source, route, or Python changes):

| gate | tier | verdict | reason |
|---|---:|---|---|
| lint (ruff) | 0 | not applicable | no Python source changes |
| type-check (mypy) | 0 | not applicable | no Python source changes |
| unit-mock-integration (pytest) | 1 | not applicable | no Python source changes |
| playwright-resilience | 1 | not applicable | no UI component changes |
| playwright-data-boundary | 1 | not applicable | no UI component changes |
| playwright-critical-journeys | 1 | not applicable | no UI component changes |
| nightly-integration | 3 | not applicable | no Oracle/Redis path changes |
| stress-load | 4 | not applicable | no performance-critical path changes |
| soak | 4 | not applicable | no performance-critical path changes |

## Workflow Changes Applied

No new workflow files were added. Existing gates cover this change:

- `.github/workflows/frontend-tests.yml` — already runs `npm run type-check` (continue-on-error: true, informational), `npm run test` (Vitest), and `npm run test:legacy` (node --test) on every push/PR touching `frontend/`.
- `.github/workflows/contract-driven-gates.yml` — already runs `npm run test` and `npm run css:check` in `contract-and-fast-tests`; `npm run build` runs inside `e2e-critical` on PR.

The tsconfig.json `include` scope expansion (`src/core/index.ts` → `src/core/**/*`) is already in place from the frontend-engineer migration. The `frontend-type-check` step in `frontend-tests.yml` picks up the wider scope automatically — no workflow edit required.

## Promotion Policy

`frontend-type-check` remains **informational** (continue-on-error: true) for this PR. Promotion criteria per `ci-gate-contract.md`:

- 20 calendar days or 60 runs
- pass rate above agreed threshold
- failures triaged and documented
- runtime within acceptable limit
- owner assigned (application-team)

Promotion to required is a separate tracked change; it must not be bundled into this rename PR.

## Rollback Policy

This change is a rename-only migration with no runtime behavior change. Rollback is a revert of the PR. No DB migration, no feature flag, no lock file change required. If `npm run build` fails post-merge, revert immediately and file a new change.

## Merge Eligibility

**mergeable** — all Tier 1 required gates (frontend-unit, frontend-build, css-governance) must be green. `frontend-type-check` is informational and may remain yellow without blocking merge. Contract-validate (Tier 0) must pass locally before pushing.
