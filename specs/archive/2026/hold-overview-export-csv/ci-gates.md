# CI/CD Gate Plan

## Change ID: hold-overview-export-csv

## Required Gates for This Change

| gate | tier | required | trigger | command/workflow | artifact |
|---|---:|:---:|---|---|---|
| python-lint | 1 | yes | pull_request | `ruff check .` | pass/fail |
| type-check | 1 | yes | pull_request | `cd frontend && npm run type-check` | pass/fail |
| backend-unit | 1 | yes | pull_request | `pytest tests/test_hold_overview_routes.py` | pytest XML |
| frontend-unit | 1 | yes | pull_request | `cd frontend && npm run test` (covers `frontend/tests/hold-overview/csv-export.test.js` and `useHoldOverview.validation.test.js`) | vitest JSON |
| contract-validation | 1 | yes | pull_request | `pip install jsonschema && cdd-kit validate --contracts` (validates `get_hold_overview_lots_export.json` sample — see test-plan.md AC-3 contract row) | pass/fail |
| backend-integration | 1 | yes | pull_request | `pytest tests/test_hold_overview_routes.py` (export-flag per-kwarg + paginated-path-unaffected — see test-plan.md AC-2/AC-6 integration rows) | pytest XML |
| data-boundary-e2e | 1 | yes | pull_request | `npx playwright test frontend/tests/playwright/data-boundary/hold-overview-export-csv.spec.js` (see test-plan.md AC-5 data-boundary row) | playwright report |
| e2e-hold-overview | 1 | yes | pull_request | `npx playwright test frontend/tests/playwright/hold-overview.spec.js` (button loading/disabled/re-enable, Blob download — see test-plan.md AC-8 rows) | playwright report |
| export-stress | 3 | yes | nightly schedule | `pytest tests/stress/test_hold_overview_export_stress.py` (row cap ≤ `HOLD_OVERVIEW_EXPORT_MAX_ROWS` — see test-plan.md AC-7 stress row) | pytest XML |

## Workflow Changes Applied

No new workflow files are required. All Tier-1 gates map to existing PR jobs; the Tier-3 stress gate maps to the existing nightly schedule job. The existing nightly workflow must include `tests/stress/test_hold_overview_export_stress.py` in its pytest invocation — verify the nightly job uses a glob or explicit path that covers `tests/stress/`.

No new secrets or OIDC trust changes are needed. `HOLD_OVERVIEW_EXPORT_MAX_ROWS` has a code-level default and does not require a CI secret.

## Promotion Policy

A PR is eligible for merge only when all Tier-1 required checks pass on the same commit SHA:
- `python-lint`, `type-check`
- `backend-unit`, `backend-integration`
- `frontend-unit`
- `contract-validation`
- `data-boundary-e2e`, `e2e-hold-overview`

The `export-stress` (Tier 3) gate runs nightly after merge; a stress failure blocks the next release candidate, not the PR itself.

## Rollback Policy

The `export` parameter is additive to `/api/hold-overview/lots`. To roll back:
1. Revert the backend commit adding the `export` parameter and row-cap guard.
2. Revert the frontend commit adding the CSV button and composable flag.
3. The existing paginated query path is unaffected by rollback (AC-6); no data migration or cache invalidation is needed.
4. Remove `contracts/api/openapi.json` regeneration and the `get_hold_overview_lots_export.json` contract sample in the same revert PR.

## Merge Eligibility

mergeable — all required gates are covered by existing CI infrastructure; no new workflows needed; stress gate is correctly deferred to Tier 3 nightly per test-plan.md.
