# CI/CD Gate Review

## Change ID
add-ts-toolchain

## Required Gates for This Change

| gate | tier | required | trigger | command/workflow | artifact |
|---|---:|---:|---|---|---|
| contract-validate | 0 | yes | local pre-PR | `cdd-kit validate` | — |
| lint | 0 | yes | local / PR | `ruff check .` | — |
| frontend-unit | 1 | yes | pull_request | `.github/workflows/frontend-tests.yml` — `Run vitest suite` + `Run legacy node --test suite` | vitest report |
| css-governance | 1 | yes | pull_request | `.github/workflows/frontend-tests.yml` (existing css:check step upstream) | governance report |
| frontend-type-check | 1 | informational | push / PR | `.github/workflows/frontend-tests.yml` — `Type check (vue-tsc --noEmit)` (`continue-on-error: true`) | — |

Gates not directly affected by this change (still apply):

| gate | tier | required | notes |
|---|---:|---:|---|
| unit-mock-integration | 1 | yes | no Python source changes in this change |
| playwright-resilience | 1 | yes | no UI component changes |
| playwright-data-boundary | 1 | yes | no UI component changes |
| playwright-critical-journeys | 1 | yes | no UI component changes |
| visual-regression | 2 | informational | no UI component changes |
| nightly-integration | 3 | yes (nightly) | no backend changes |
| stress-load | 4 | yes (weekly) | no backend changes |
| soak | 4 | yes (weekly) | no backend changes |

## Workflow Changes Applied

File: `.github/workflows/frontend-tests.yml`

A new step `Type check (vue-tsc --noEmit)` was inserted into the `frontend-unit-tests` job, between "Install frontend dependencies" and "Run vitest suite":

```yaml
- name: Type check (vue-tsc --noEmit)
  working-directory: frontend
  run: npm run type-check
  continue-on-error: true
```

`continue-on-error: true` is set because the gate is informational per `ci-gate-contract.md` schema-version 1.2.0 (gate row `frontend-type-check`, tier 1, required: informational). The step will report its outcome in the job summary without blocking merge.

The trigger paths already in the workflow (`frontend/src/**`, `frontend/package.json`, `.github/workflows/frontend-tests.yml`) cover `tsconfig.json` indirectly via `frontend/package.json` changes; `frontend/tsconfig.json` may be added to the path filter when the gate is promoted to required.

No new workflow file was created. No concurrency group change was needed (the job already has no concurrency key; adding one is deferred to the promotion milestone to avoid disrupting existing PR queues).

## Promotion Policy

The `frontend-type-check` gate starts as informational (`continue-on-error: true`). It is promoted to required when ALL of the following are met:

1. 20 calendar days or 60 PR runs have elapsed since the gate was introduced.
2. Pass rate is >= 95% over that window (failures triaged and documented).
3. All pre-existing `allowJs`-induced suppressions in `tsconfig.json` have been resolved or explicitly annotated with an exit date.
4. Median step runtime is <= 90 seconds (p95 <= 120 s).
5. An owner is assigned in `ci-gate-contract.md` (currently: application-team).

Promotion action: remove `continue-on-error: true` from the step and update the `required` column in `ci-gate-contract.md` from `informational` to `yes`. Add `frontend/tsconfig.json` to the workflow path filter at the same time.

## Rollback Policy

If the new step causes unexpected CI disruption (runner OOM, phantom exit-code from vue-tsc, etc.):

1. Set `continue-on-error: true` is already in place, so no merge blockage can occur from this step alone.
2. If the step itself hangs: add `timeout-minutes: 5` to the step as a fast follow.
3. If `vue-tsc` binary is missing after `npm ci` (package-lock drift): pin `vue-tsc` to an exact version in `package.json` devDependencies.
4. Full removal: revert the four-line step block in `.github/workflows/frontend-tests.yml`. The contract row in `ci-gate-contract.md` should be updated to `removed` with a dated comment.

No database migration, feature flag, or infrastructure change is involved; rollback is a single-commit revert of the workflow file.

## Merge Eligibility

**mergeable** — the new gate is informational (`continue-on-error: true`) and cannot block merge. All existing required Tier 1 gates are unmodified and must still pass before merge.
