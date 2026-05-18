# CI/CD Gate Plan — migrate-mid-section-defect-ts

## Change Summary

Phase 3 TypeScript migration of `frontend/src/mid-section-defect/`. Pure JS→TS rename; no behavior change. Only contract touched: `contracts/ci/ci-gate-contract.md` patch bump 1.3.13 → 1.3.14.

## Required Gates for This Change

| gate | tier | required | trigger | command/workflow | artifact |
|---|---:|:---:|---|---|---|
| frontend-type-check | 1 | yes | PR | `cd frontend && npm run type-check` | — |
| frontend-unit-tests | 1 | yes | PR | `cd frontend && npm run test` | vitest report |
| frontend-css-check | 1 | yes | PR | `cd frontend && npm run css:check` | governance report |
| backend-unit-tests | 1 | yes | PR | `pytest tests/ -m "not e2e"` | junit XML |
| cdd-validate | 1 | yes | PR | `cdd-kit validate` | — |
| grep-js-audit | 2 | informational | PR (reviewer) | `grep -r "mid-section-defect.*\.js" tests/` must return empty | — |
| nightly-e2e | 3 | nightly | schedule/dispatch | `pytest tests/ -m "e2e"` (live Oracle + Redis) | test report |

See test-plan.md rows AC-1 through AC-8 for the full acceptance-criteria-to-test mapping.

## CI/CD Workflow

Existing workflow files cover all gates above. No new workflow files are required for this change.

| workflow file | jobs covering this change |
|---|---|
| `.github/workflows/frontend-tests.yml` | `frontend-unit-tests`, `frontend-type-check`, `css-governance` |
| `.github/workflows/backend-tests.yml` | `unit-and-integration-tests` (pytest -m "not e2e") |
| `.github/workflows/contract-driven-gates.yml` | `contract-and-fast-tests` (cdd-kit validate) |
| `.github/workflows/nightly.yml` | `nightly-integration` (pytest -m "e2e") |

`frontend-type-check` is currently **informational** (`continue-on-error: true`) per ci-gate-contract.md §Required Check Policy. It is promoted to **required** for this change because the migration's primary acceptance criterion (AC-2) is zero type-check errors after `tsconfig.json include` gains `src/mid-section-defect/**/*`. The gate must exit 0 to merge.

No concurrency group changes needed; existing `concurrency: { group: ${{ github.ref }}, cancel-in-progress: true }` on PR workflows remains sufficient.

## Workflow Changes Applied

None. All required gates are covered by existing workflow jobs. No `.github/workflows/*.yml` files are modified by this change.

## Promotion Policy

This PR is eligible to merge to `main` when ALL of the following are true:

1. `frontend-type-check` exits 0 (zero vue-tsc errors after `tsconfig.json` include expansion — AC-2).
2. `frontend-unit-tests` exits 0 — AC-1, AC-3 (test-plan.md rows for both legacy test files).
3. `frontend-css-check` exits 0 — no CSS governance regression.
4. `backend-unit-tests` exits 0 (`pytest tests/ -m "not e2e"`) — AC-4 .js path audit confirmed clean.
5. `cdd-validate` exits 0 with `ci-gate-contract.md` at schema-version 1.3.14 — AC-5.
6. Reviewer confirms `grep -r "mid-section-defect.*\.js" tests/` returns empty — AC-4 (test-plan.md audit row).
7. `git diff HEAD -- frontend/src/mid-section-defect/index.html` shows no change — AC-8.

Tier 3 nightly e2e is not a merge blocker; failure must be triaged within 1 business day per ci-gate-contract.md §Required Check Policy.

## Rollback Policy

This is a pure type-system change with no runtime behavior delta.

Rollback procedure:
1. Revert the PR (`git revert <merge-commit>`).
2. No database migrations to undo.
3. No parquet cleanup required — `mid-section-defect` uses no persistent DuckDB spool (query-tool pattern).
4. No Redis key invalidation required.
5. Revert also rolls back the `contracts/ci/ci-gate-contract.md` patch bump (1.3.14 → 1.3.13) and the `contracts/CHANGELOG.md` entry. No separate contract cleanup needed.

## Merge Eligibility

**mergeable** — all Tier 1 gates are existing gates running identical commands; no new workflow infrastructure required. Informational grep audit is reviewer-executable in under 5 seconds.

