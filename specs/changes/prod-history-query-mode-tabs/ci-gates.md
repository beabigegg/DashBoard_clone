---
change-id: prod-history-query-mode-tabs
schema-version: 0.1.0
last-changed: 2026-05-14
risk: medium
tier: 2
---

# CI/CD Gate Plan: prod-history-query-mode-tabs

Tier 2 change. No CI workflow/pipeline change — the classifier marked the CI/CD
contract not-applicable. All new tests land in existing files absorbed by
existing gates. No new `.github/workflows/*.yml` file is introduced.

## Local Gates (pre-PR)

Run in conda env `mes-dashboard` (backend) / `frontend/` (frontend):

- `ruff check .`
- `pytest tests/test_production_history_service.py tests/test_production_history_routes.py tests/test_api_contract.py tests/test_production_history_sql_runtime.py`
- `cd frontend && npm run type-check`
- `cd frontend && npm run test`
- `cd frontend && npm run test:legacy`
- `cd frontend && npm run build`
- `cd frontend && npm run css:check`
- `cdd-kit validate --contracts`
- `cdd-kit gate prod-history-query-mode-tabs`

## PR Required Gates (Tier 1/2, block merge)

Trigger: every gate below runs automatically on `pull_request` to `main` (and on
push to the PR branch). No manual-dispatch or scheduled trigger is added by this
change — there are no nightly/weekly/manual gates for this change.

| gate | tier | workflow file | command | expected |
|---|---:|---|---|---|
| lint | 0 | contract-driven-gates.yml | `ruff check .` | pass |
| contract-validate | 0 | contract-driven-gates.yml | `cdd-kit validate` | pass |
| unit-mock-integration | 1 | backend-tests.yml (`unit-and-integration-tests`) | `pytest -m "not (e2e or integration_real or stress or load or soak or multi_worker)" ...` | green — incl. `TestValidateQueryParamsModeSplit` (8), `TestQueryModeSplitRoutes` (3), `TestProductionHistoryQueryModeContract` (2) |
| frontend-unit | 1 | frontend-tests.yml (`frontend-unit-tests`) | `cd frontend && npm run test` | green — `useProductionHistory.validation.test.js` 45/45 |
| css-governance | 1 | frontend-tests.yml | `cd frontend && npm run css:check` | 0 errors |
| playwright-critical-journeys | 1 | frontend-tests.yml (`e2e-critical`) | `npx playwright test ...` | green — new spec `production-history-query-mode-tabs.spec.ts` (4) + 4 reconciled specs: `production-history-wildcard-paste.spec.ts`, `-multi-line-input.spec.ts`, `-cross-filter.spec.ts`, `-filter-options-error.spec.ts` |
| playwright-resilience | 1 | frontend-tests.yml (`e2e-critical`) | `npx playwright test tests/playwright/resilience/` | unaffected — no new resilience surface |
| playwright-data-boundary | 1 | frontend-tests.yml (`e2e-critical`) | `npx playwright test tests/playwright/data-boundary/` | unaffected — data-boundary covered via route integration assertions |

## Informational Gates (non-blocking)

| gate | tier | workflow file | command | note |
|---|---:|---|---|---|
| frontend-type-check | 1 (informational) | frontend-tests.yml | `cd frontend && npm run type-check` | `vue-tsc --noEmit` clean; `production-history/` already migrated |
| type-check (mypy) | 0 (informational) | contract-driven-gates.yml | `mypy src/` | informational; `environment.yml` does not pin mypy |

## Rollback Policy

Mechanical `git revert` of the change commit(s). proposal.md Option B is a
conditional date-default inside `validate_query_params` — purely additive,
reached only when dates are absent *and* identifier tokens present. No SQL
template change, no spool parquet schema change (`main_query.sql` output columns
untouched → existing `tmp/query_spool/production_history/*.parquet` stay
compatible, no parquet cleanup), no Oracle DDL, no data migration. Frontend
revert + `npm run build` regenerates bundles. Production fallback knob without a
code change: lower the existing `PROD_HISTORY_MAX_DATE_RANGE_DAYS` env tunable if
the wide-window path proves too heavy. Per ci-gate-contract Rollback Policy, any
Tier 1 gate going red blocks new merges to main until fixed.

## Promotion Policy

This change introduces **no new gate** — all new backend/frontend/e2e tests land
in existing files under existing `unit-mock-integration`, `frontend-unit`, and
`playwright-critical-journeys` gates, so there is nothing tier-eligible for
promotion. The informational gates (`frontend-type-check`, `mypy`) continue under
the existing ci-contract Informational Gate Promotion Policy (20 days / 60 runs /
pass-rate threshold / triaged failures / owner) — unchanged by this change.

## Gate Compatibility Notes

Gate tiers, commands, and the workflow inventory are all unchanged. The new tests
are absorbed by existing gates: backend cases by `unit-mock-integration`, frontend
unit cases by `frontend-unit`, the new + 4 reconciled Playwright specs by
`playwright-critical-journeys`. No new workflow file, no ci-gate-contract gate
inventory edit required. A patch-level ci-contract schema bump documenting this
test-coverage absorption is optional and may be folded into the contract-reviewer
pass — gate tier/command/status stay identical either way.

## Merge Eligibility

mergeable — pending all Tier 1 PR gates green; no blocking workflow change needed.
