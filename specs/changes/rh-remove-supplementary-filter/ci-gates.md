# CI/CD Gate Plan

## Change ID
rh-remove-supplementary-filter

## Required Gates
| gate | tier | required | trigger | command/workflow | artifact |
|---|---:|---:|---|---|---|
| unit-and-integration-tests | 1 | yes | pull_request | `backend-tests.yml` / `pytest tests/ --ignore=tests/e2e --ignore=tests/stress` | pytest exit 0 |
| data-boundary tests | 1 | yes | pull_request | `backend-tests.yml` / `pytest tests/stress/test_chunk_boundary.py -k "TestChunkSeam or TestOrderByTieStability"` | pytest exit 0 |
| contract-validators | 1 | yes | pull_request | `cdd-kit validate` (includes `--versions`); requires `pip install jsonschema` first | validator exit 0 |
| openapi-sync | 1 | yes | pull_request (paths: api-contract.md, openapi.json) | `openapi-sync.yml` / `cdd-kit openapi export --check --out contracts/openapi.json` | sync exit 0 |
| css-governance | 1 | yes | pull_request | `frontend-tests.yml` / `cd frontend && npm run css:check` | css:check exit 0 |
| frontend-unit-vitest | 1 | yes | pull_request | `frontend-tests.yml` / `cd frontend && npm test` | vitest exit 0 |
| reject-history-e2e | 1 | yes | pull_request | `frontend-tests.yml` / `npx playwright test tests/playwright/reject-history.spec.ts` | playwright exit 0 |
| type-check | 2 | informational | pull_request | `frontend-tests.yml` / `cd frontend && npm run type-check` (`continue-on-error: true`) | tsc report |
| changelog-versions | 1 | yes | pull_request | `cdd-kit validate --versions` — api 1.29.0, data 1.26.0, business 1.31.0, css 1.10.0 must appear in `contracts/CHANGELOG.md` | validator exit 0 |

## Workflow Changes Applied

No new workflow files are needed. All gates run under existing workflows:

- `backend-tests.yml` — covers unit-and-integration-tests and data-boundary (already triggers on `src/mes_dashboard/routes/**` and `tests/**`)
- `openapi-sync.yml` — triggers on `contracts/api/api-contract.md` and `contracts/openapi.json` path changes; catches both export files via the `--check` flag (see CLAUDE.md: regen BOTH `contracts/openapi.json` AND `contracts/api/openapi.json` after any endpoint-table or schema edit)
- `frontend-tests.yml` — covers vitest, css:check, type-check, and Playwright (already triggers on `frontend/src/**`)
- `contract-driven-gates.yml` — covers `cdd-kit validate` including `--versions` check

Pre-merge local commands (Tier 0):
```
pytest tests/ --ignore=tests/e2e --ignore=tests/stress -q
cd frontend && npm test && npm run css:check && npm run type-check
cdd-kit validate
cdd-kit openapi export --check --out contracts/openapi.json
```

## Promotion Policy

- All Tier 1 gates must be green before requesting review.
- `type-check` (Tier 2, informational) failures require a comment in the PR explaining the residual and a follow-up issue; they do not block merge.
- Nightly gates (`nightly-integration-real`, `oracle-fault-injection`, `multi-worker-concurrency`) are Tier 3 and do not gate this PR. Failures surfaced post-merge are addressed in the next sprint cycle.

## Rollback Policy

This change removes a UI section and moves a filter from DuckDB post-materialization to Oracle BASE_WHERE. Rolling back requires reverting both the frontend CSS/markup removal and the backend `_build_base_where()` change in the same commit. No Parquet schema change is introduced, so no `_SCHEMA_VERSION` bump or spool purge is needed on rollback. Cache keys will differ (reasons[] absent from `query_id_input`), so existing cache entries from the new code are stale after rollback but harmless (TTL-expiry clears them).

## Merge Eligibility

**mergeable** when:
1. `unit-and-integration-tests` green
2. `data-boundary tests` green
3. `contract-validators` green (all four version bumps in `contracts/CHANGELOG.md`)
4. `openapi-sync` green (both `contracts/openapi.json` and `contracts/api/openapi.json` regenerated)
5. `css-governance` green (Rule 6 passes after `.supplementary-*` removal and `.primary-prefilter-row` grid change)
6. `frontend-unit-vitest` green
7. `reject-history-e2e` green (supplementary panel absent, 報廢原因 4th column present, Pareto cross-filter and CSV export pass)
