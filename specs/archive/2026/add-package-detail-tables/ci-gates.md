# CI Gates: add-package-detail-tables

## Required Gates for This Change

| gate | tier | required | trigger | command / workflow | artifact |
|---|---:|:---:|---|---|---|
| backend-unit | 1 | yes | pull_request | `conda run -n mes-dashboard pytest` / `backend-tests.yml` job `unit-and-integration-tests` | pytest exit 0 |
| frontend-unit | 1 | yes | pull_request | `cd frontend && npm run test` / `frontend-tests.yml` job `frontend-unit-tests` | vitest exit 0 |
| type-check | 1 | yes | pull_request | `cd frontend && npm run type-check` / `frontend-tests.yml` step "Type check" | vue-tsc exit 0 |
| css-governance | 1 | yes | pull_request | `cd frontend && npm run css:check` / `frontend-tests.yml` step "CSS governance check" | css:check exit 0 |
| contract-validate | 1 | yes | pull_request | `cdd-kit validate` / `contract-driven-gates.yml` step "Validate contracts and gates" | cdd-kit exit 0 |
| python-lint | 2 | no | pull_request | `ruff check .` / `backend-tests.yml` (advisory) | ruff report |

Test plan rows covered: AC-1 through AC-8 (see `test-plan.md`).

## CI/CD Workflow

No new workflow files are required. All gates above are served by existing workflows:

- `backend-tests.yml` — triggers on PR when `src/mes_dashboard/**` or `tests/**` change; runs `pytest` against the backend test suite.
- `frontend-tests.yml` — triggers on PR when `frontend/src/**` changes; runs Vitest, vue-tsc, and css:check.
- `contract-driven-gates.yml` — triggers on every PR; runs `cdd-kit validate`.

This change touches `src/mes_dashboard/services/`, `src/mes_dashboard/sql/`, `tests/`, and `frontend/src/` — all three path filters fire on PR. No workflow edits needed.

## Promotion Policy

All Tier 1 gates (backend-unit, frontend-unit, type-check, css-governance, contract-validate) must be green before merge. The python-lint Tier 2 gate is informational and does not block promotion.

## Rollback Policy

If a post-deploy regression is detected, revert the merge commit on `main` and redeploy the previous artifact.

**Required parquet cleanup on both deploy and rollback** (material-consumption spool schema change — `PRODUCTLINENAME` column added to `detail_rows.sql`):

```
rm -f tmp/query_spool/material_consumption/detail-*.parquet
```

Run this command on the server after each deploy or rollback before restarting gunicorn. Existing parquet files lack the new column and will cause schema-mismatch errors at the next `read_parquet` call if not cleared.

No other cleanup is required: hold-history and query-tool do not use persistent spool parquet files.

## Merge Eligibility

Mergeable when all Tier 1 required gates are green and the parquet cleanup step is confirmed in the deploy runbook.
