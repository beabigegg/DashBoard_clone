# CI/CD Gate Review

## Change ID: rh-primary-prefilter

## Required Gates for This Change

All gates listed below are **pre-existing** in `contracts/ci/ci-gate-contract.md`. No new
gate tier, workflow file, or command is introduced by this change.

| gate | tier | required | trigger | command/workflow | artifact |
|---|---:|:---:|---|---|---|
| contract-validate | 0 | yes | local pre-PR | `cdd-kit validate` | — |
| response-shape-validate | 1 | yes | push/PR | `cdd-kit validate --contracts` | — |
| lint | 0 | yes | local/PR | `ruff check .` | — |
| unit-mock-integration | 1 | yes | push/PR | `pytest -m "not (e2e or integration_real or stress or load or soak or multi_worker)" --ignore=tests/integration --ignore=tests/stress --ignore=tests/e2e --ignore=tests/manual -x` | junit XML |
| frontend-unit | 1 | yes | push/PR | `cd frontend && npm run test` | vitest report |
| css-governance | 1 | yes | push/PR | `cd frontend && npm run css:check` | governance report |
| playwright-data-boundary | 1 | yes | PR | `cd frontend && npx playwright test tests/playwright/data-boundary/` | playwright trace |
| playwright-critical-journeys | 1 | yes | PR | `cd frontend && npx playwright test tests/playwright/reject-history.spec.js` (among others) | playwright trace |
| nightly-integration | 3 | yes (nightly) | weekly schedule/dispatch | `pytest tests/integration/ --run-integration-real -m "integration_real or multi_worker" -x` | test report |

### Tests added per test-plan.md that land in existing gates

| gate | new test rows (see test-plan.md) |
|---|---|
| unit-mock-integration | AC-2/3/4/6 in `tests/test_reject_history_service.py`; AC-1/2/4 in `tests/test_reject_history_routes.py`; AC-7 in `tests/test_reject_history_async_routes.py` |
| response-shape-validate | AC-1 in `tests/contract/test_api_contract.py` (both openapi.json exports) |
| frontend-unit | AC-5 in `frontend/tests/validation/useRejectHistory.validation.test.js` |
| playwright-data-boundary | `(NA)` sentinel + NULL-container boundary cases (AC-3) |
| playwright-critical-journeys | AC-5/6/7 in `frontend/tests/playwright/reject-history-filter.spec.ts` |

## Informational Gates

| gate | tier | trigger | notes |
|---|---:|---|---|
| frontend-type-check | 2 | push/PR | `cd frontend && npm run type-check`; remains informational per ci-gate-contract.md §frontend-type-check scope |
| visual-regression | 2 | PR | TBD Playwright screenshot diff; not required — additive UI only |

## workflow

No workflow file changes required. All new test files are auto-discovered by existing
`contract-driven-gates.yml`, `backend-tests.yml`, and `frontend-tests.yml` workflows.
CI/CD contract classification: `no` (see `change-classification.md`).

## promotion policy

Non-breaking additive change (`deprecate-2-minors` policy; three new optional params).

1. All Tier 1 required gates pass on PR.
2. Nightly Tier 3 picks up async-path tests in `tests/test_reject_history_async_routes.py`
   on first run after merge.
3. No stress/soak report required (change is load-reducing; see `change-classification.md`).
4. Merge eligible once Tier 1 gates are green and both `contracts/openapi.json` and
   `contracts/api/openapi.json` carry the three new optional params.

## rollback policy

All new params are optional and additive — no data migration, no schema version bump, no
spool namespace change.

- **Flag-off rollback (preferred)**: deploy the previous commit. No spool cleanup, no
  Redis flush, no worker restart required. Oracle queries revert to pre-change BASE_WHERE
  (no prefilter injection).
- **Hard rollback**: `git revert <merge-commit>`; redeploy. Contract samples that were
  regenerated are restored by the code revert (git-tracked).
- **No parquet cleanup needed**: reject-history spool namespace and schema are unchanged.
- **No worker ops needed**: no new RQ queue, no new systemd unit introduced.

## Merge Eligibility

**mergeable** when:
- `unit-mock-integration` green (AC-1 through AC-7 unit/integration rows in test-plan.md)
- `response-shape-validate` green (both openapi.json exports carry new params)
- `frontend-unit` green (FilterPanel payload assertions)
- `playwright-critical-journeys` green (E2E FilterPanel render + payload)
- `playwright-data-boundary` green (`(NA)` sentinel boundary)
- `css-governance` green (additive MultiSelect usage; no new unscoped rules)

**informational-risk only**: `frontend-type-check`, `visual-regression`
