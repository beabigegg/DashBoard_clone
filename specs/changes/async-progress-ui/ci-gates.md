# CI/CD Gate Review — async-progress-ui

## Required Gates for This Change

| gate | tier | required | trigger | command / workflow | artifact |
|---|---:|:---:|---|---|---|
| frontend-unit-tests | 1 | yes | PR / push | `npm test` (Vitest) | `frontend-tests.yml` → job `frontend-unit-tests` |
| type-check | 1 | yes | PR / push | `npm run type-check` (vue-tsc --noEmit) | `frontend-tests.yml` → step "Type check" |
| css-governance | 1 | yes | PR / push | `npm run css:check` | `frontend-tests.yml` → step "CSS governance check" |
| backend-unit-tests | 1 | yes | PR / push | `pytest tests/test_yield_alert_job_service.py tests/test_production_history_job_service.py` | `backend-tests.yml` → job `unit-and-integration-tests` |
| cdd-gate | 1 | yes | PR / push | `cdd-kit gate async-progress-ui` | `contract-driven-gates.yml` → job `contract-and-fast-tests` |

## Informational Gates

| gate | tier | required | trigger | command / workflow | note |
|---|---:|:---:|---|---|---|
| full-backend-suite | 2 | no | PR / push | `pytest --ignore=tests/e2e --ignore=tests/stress` | `backend-tests.yml` — regression check, non-blocking |

## Nightly / Weekly / Manual Gates

Tier 3 (nightly real-infra), Tier 4 (weekly soak/stress), and Tier 5 (manual
production-like dispatch) are n/a for this change. No new env vars, no DB
migration, no new infra paths requiring real-Oracle validation.

## Workflow

| gate | workflow file | job / step |
|---|---|---|
| frontend-unit-tests | `.github/workflows/frontend-tests.yml` | job `frontend-unit-tests` |
| type-check | `.github/workflows/frontend-tests.yml` | step "Type check (vue-tsc --noEmit)" |
| css-governance | `.github/workflows/frontend-tests.yml` | step "CSS governance check" |
| backend-unit-tests | `.github/workflows/backend-tests.yml` | job `unit-and-integration-tests` |
| cdd-gate | `.github/workflows/contract-driven-gates.yml` | job `contract-and-fast-tests` |
| full-backend-suite | `.github/workflows/backend-tests.yml` | job `unit-and-integration-tests` (full run) |

No workflow file changes are required. All required gates are already triggered
on `pull_request` by existing path filters (`frontend/src/**`,
`frontend/tests/**`, `src/mes_dashboard/services/**`, `tests/**`).

Note: `type-check` step currently has `continue-on-error: true` in the
workflow. AC-2 type-safety compliance is enforced by the test-plan contract;
if this gate turns red it must be fixed before merge regardless of the
workflow-level flag.

## Promotion Policy

The PR may be merged when all five Tier-1 required gates are green:
- `frontend-unit-tests` — new `AsyncQueryProgress` unit tests pass
- `type-check` — `pct?`/`stage?` additions to `JobStatusResponse` are type-safe
- `css-governance` — `<style scoped>` in `AsyncQueryProgress.vue` is compliant
- `backend-unit-tests` — pct milestones 0/30/100 verified in both job services
- `cdd-gate async-progress-ui` — all contract and spec checks pass

The informational full-backend run (Tier 2) may be amber without blocking
merge; any failure must be triaged within one business day.

## Rollback Policy

No spool files, no new env vars, and no DB schema changes are introduced.
Rollback = `git revert <merge-commit>` on `main`. No cache purge, parquet
schema bump, or data migration is required after rollback.
