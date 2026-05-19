# CI/CD Gate Plan

## Change ID
admin-perf-detail-ui

## Required Gates for This Change

| gate | tier | required | trigger | command / workflow | artifact |
|---|---:|:---:|---|---|---|
| vue-tsc type-check | 2 | informational | pull_request | `cd frontend && npm run type-check` / `frontend-tests.yml` job `frontend-unit-tests` | step result (continue-on-error: true) |
| vitest unit tests | 1 | yes | pull_request | `cd frontend && npm run test -- --run` / `frontend-tests.yml` job `frontend-unit-tests` | none (pass/fail) |
| css:check | 1 | yes | pull_request | `cd frontend && npm run css:check` / local only — see note | none (pass/fail) |
| cdd-kit validate | 1 | yes | pull_request | `cdd-kit validate` / `contract-driven-gates.yml` job `contract-and-fast-tests` | none (pass/fail) |
| contracts/ diff check | 1 | yes | pull_request | PR diff: assert no files under `contracts/` are modified (AC-8 in test-plan.md) | reviewer check |

Gates not applicable to this change (frontend-only, no Python touched):

| gate | reason not required |
|---|---|
| ruff (Python lint) | no Python files in changeset |
| backend unit / integration | no backend changes |
| E2E / Playwright | pure additive rendering; no routing or auth changes |
| nightly real-infra (Tier 3) | no real-infra dependency |
| weekly soak / stress (Tier 4) | not applicable for Tier 3 UI change |
| manual production-like dispatch (Tier 5) | not applicable |

## CI/CD Workflow

All required Tier 1 gates are already covered by existing workflows. No new workflow files are required for this change.

**`frontend-tests.yml`** (existing) — triggers on `pull_request` for paths under `frontend/src/**`:
- Job `frontend-unit-tests` runs `npm run type-check` (informational, `continue-on-error: true`) then `npm test`.
- The `src/**/*.test.ts` glob in `vitest.config.js` automatically discovers `frontend/src/admin-pages/__tests__/PerfDetail.test.ts` without config change.
- This job's name `frontend-unit-tests` must remain unchanged to satisfy branch protection.

**`contract-driven-gates.yml`** (existing) — triggers on `pull_request` for all paths:
- Job `contract-and-fast-tests` runs `cdd-kit validate`.

**`css:check` gap note**: No existing workflow runs `npm run css:check`. The contract-reviewer confirmed that `admin-pages/style.css` was added to `contracts/css/css-inventory.md` (version 1.2.1 to 1.2.2), confirming new authored CSS is present. This gate is therefore required. A `css:check` step is added to `frontend-tests.yml` `frontend-unit-tests` job as part of this change (see Workflow Changes Applied below).

Concurrency: `frontend-tests.yml` and `contract-driven-gates.yml` should be evaluated for adding a `concurrency` group on `pull_request` triggers to cancel stale runs. This is a follow-up improvement, not a blocker for this change.

## Workflow Changes Applied

**`.github/workflows/frontend-tests.yml`** — added `css:check` step to existing `frontend-unit-tests` job, after the `Run vitest suite` step. The step runs `npm run css:check` and is required (no `continue-on-error`). No new workflow file was created.

## Promotion Policy

This is a Tier 3 (low-risk, module-level) frontend-only change. No gate tier promotions are required.

- Vitest unit-test gate (`frontend-unit-tests`) is already Tier 1 required.
- `vue-tsc type-check` remains Tier 2 informational (`continue-on-error: true`) consistent with the existing project-wide policy until the type-check pass rate is confirmed stable.
- If `css:check` is activated for this PR (authored CSS present), it is Tier 1 required for this PR and must pass before merge.

No gate moves to a higher tier as a result of this change.

## Rollback Policy

Revert the merge commit (`git revert <merge-sha>`). No additional cleanup is required:

- No parquet files written (frontend rendering only; no spool changes).
- No environment variable additions or removals.
- No backend schema changes.
- No contract file modifications (AC-8).

After reverting, re-run `cdd-kit validate` locally to confirm contract integrity.

## Artifact Retention

No new CI artifacts are produced by this change. The existing `frontend-tests.yml` produces no uploaded artifacts. Default retention applies to any GitHub Actions logs.

## Merge Eligibility

**Mergeable** when all of the following are green:

1. `frontend-unit-tests` job passes (all 10 test cases in `PerfDetail.test.ts`; see test-plan.md rows AC-1 through AC-7).
2. `contract-and-fast-tests` job passes (`cdd-kit validate`).
3. PR diff contains no files under `contracts/` (AC-8).
4. `css:check` passes (new authored CSS confirmed by contract-reviewer; see `contracts/css/css-inventory.md` v1.2.2).
5. `vue-tsc type-check` may remain yellow (informational) without blocking merge.

## Notes

- Test cases referenced by gate: test-plan.md rows AC-1 through AC-8.
- Gate command for local pre-commit Tier 0 run: `cd frontend && npm run type-check && npm run test -- --run && npm run css:check` (omit `css:check` if no new CSS).
- `cdd-kit gate` validation requires the literal section headers `## CI/CD Workflow`, `## Promotion Policy`, and `## Rollback Policy` — all three are present above.
