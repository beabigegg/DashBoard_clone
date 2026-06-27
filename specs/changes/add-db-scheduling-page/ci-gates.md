# CI/CD Gate Plan

## Change ID
add-db-scheduling-page

## Required Gates for This Change
| gate | tier | required | trigger | command/workflow | artifact |
|---|---:|:---:|---|---|---|
| unit-and-integration-tests | 1 | yes | pull_request | `backend-tests.yml` / `pytest tests/ --ignore=tests/e2e --ignore=tests/stress` | test report |
| type-check | 1 | yes | pull_request | `frontend-tests.yml` / `npm run type-check` | pass/fail |
| openapi-sync | 1 | yes | pull_request | `openapi-sync.yml` / `cdd-kit openapi export --check` | diff output |
| css:check | 1 | yes | pull_request | `frontend-tests.yml` / `npm run css:check` | pass/fail |
| frontend-unit-vitest | 1 | yes | pull_request | `frontend-tests.yml` / `npm test` | test report |
| e2e-db-scheduling | 2 | no (informational) | pull_request | `frontend-tests.yml` / `npx playwright test tests/playwright/db-scheduling.spec.ts` | trace/screenshot |

## Workflow Changes Applied
No new workflow files are required. All gates are covered by existing workflows:

- `backend-tests.yml` — path filters already cover `src/mes_dashboard/routes/**`, `src/mes_dashboard/services/**`, and `tests/**`; the new files `db_scheduling_routes.py`, `db_scheduling_service.py`, `test_db_scheduling_service.py`, `test_db_scheduling_routes.py`, `test_db_scheduling_navigation.py` fall within these globs without modification.
- `frontend-tests.yml` — path filter `frontend/src/**` covers the new `db-scheduling/` app and portal-shell navigation changes; path filter `frontend/tests/**` covers `db-scheduling.spec.ts`.
- `openapi-sync.yml` — path filter `contracts/api/api-contract.md` and `contracts/openapi.json` already triggers on the required regen of both OpenAPI export files.

**Required action before merge:** backend engineer must run `cdd-kit openapi export --out contracts/openapi.json` and also update `contracts/api/openapi.json` after adding the `GET /api/db-scheduling/queue` endpoint to `api-contract.md`. Both files must be committed in the same PR so `openapi-sync` passes. See `change-classification.md §Required Contracts`.

**Playwright step addition required in `frontend-tests.yml`:** add the following step after the existing `resource-history-async` step (chromium is already installed by the preceding `npx playwright install --with-deps chromium` step):

```yaml
      - name: Run db-scheduling e2e spec (informational)
        working-directory: frontend
        run: npx playwright test tests/playwright/db-scheduling.spec.ts
        continue-on-error: true
```

This step must use `continue-on-error: true` because this gate is Tier 2 informational and must not block merge.

## Promotion Policy
- `e2e-db-scheduling` may be promoted to Tier 1 (required) after 10 consecutive green PR runs with no flakes. Promotion requires removing `continue-on-error: true` and adding the job name to branch protection required status checks.
- No nightly (Tier 3) or weekly/soak (Tier 4) gates are introduced; the endpoint is read-only, sync-only, and backed by the existing 5-minute WIP cache. See `change-classification.md §Tasks Not Applicable`.

## Rollback Policy
- This change is additive (new route, new service, new Vue app, new drawer entry). Rollback is a revert of the feature PR; no data migration, no schema change, no env var to unset.
- If `openapi-sync` fails post-merge on main, run `cdd-kit openapi export --out contracts/openapi.json`, update `contracts/api/openapi.json`, and push a follow-up commit. No service restart required.
- Portal-shell navigation change (drawer entry) is a JS constant; removing it does not require a cache purge or Redis flush.

## Merge Eligibility
Mergeable when all Tier 1 required gates pass:
- `unit-and-integration-tests` (green)
- `type-check` (green)
- `openapi-sync` (green — requires both OpenAPI files regenerated and committed)
- `css:check` (green)
- `frontend-unit-vitest` (green)

`e2e-db-scheduling` is informational; a red result does not block merge but must have a linked issue created before close of the PR review cycle.

See `test-plan.md` for full test row coverage (unit, contract-sample, integration, data-boundary, E2E rows).
