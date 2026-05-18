# CI/CD Gate Review — equipment-rejects-by-lots

## Required Gates for This Change

| gate | tier | required | trigger | command / workflow | artifact |
|---|---:|:---:|---|---|---|
| Python lint | 0 | yes | pre-commit / PR | `ruff check src/ tests/` | pass/fail |
| TypeScript type-check | 0 | yes | PR | `cd frontend && npm run type-check` | pass/fail |
| unit tests — backend (AC-1,2,3,4,5) | 0 | yes | pre-commit / PR | `pytest tests/test_query_tool_service.py tests/test_query_tool_sql_runtime.py -x -q` | pass/fail |
| Vitest component tests — AC-6 | 0 | yes | pre-commit / PR | `cd frontend && npm run test -- --run tests/query-tool/` | pass/fail |
| contract validation | 1 | yes | PR | `cdd-kit validate` | pass/fail |
| integration + data-shape contract (AC-2,3,5) | 1 | yes | PR | `pytest tests/test_query_tool_routes.py tests/test_query_tool_heavy_join.py -x -q` | pass/fail |
| E2E — rejects sub-tab columns + export (AC-6,8) | 3 | yes | nightly | `pytest tests/e2e/test_query_tool_e2e.py` + `npx playwright test query-tool.spec.js` | nightly report |

## CI/CD Workflow

No new workflow files are required. Existing gates are sufficient for this Tier 2 change.

- Tier 0 gates run via the existing pre-commit hook and PR `ci.yml` unit job.
- Tier 1 gates run via the existing PR `ci.yml` integration job and `cdd-kit validate`.
- Tier 3 E2E runs via the existing `nightly.yml` Playwright job; extend
  `tests/e2e/test_query_tool_e2e.py` and `frontend/tests/playwright/query-tool.spec.js`
  in-place — no new workflow file or job is needed.

Breaking-change note: aggregate fields `TOTAL_REJECT_QTY`, `TOTAL_DEFECT_QTY`, and
`AFFECTED_LOT_COUNT` are removed from the `query_type=rejects` response. Both consumers
(`EquipmentView`, `LotEquipmentView`) are updated in the same PR. The contract test in
`tests/test_query_tool_routes.py` asserts these fields are absent (see test-plan.md AC-2).

## Promotion Policy

- PR is mergeable when all Tier 0 and Tier 1 gates pass on the PR branch.
- `cdd-kit validate` must pass: api-contract, data-shape-contract, and business-rules
  diffs for this change must all be present and valid.
- The first nightly run on `main` after merge must produce a green Tier 3 E2E report
  before the branch is promoted to production.

## Rollback Policy

- Revert the PR commit; no parquet spool cleanup is required (query-tool has no
  persistent spool — queries are on-demand per request, per project CLAUDE.md).
- No DB migrations to reverse; no env-var changes to undo.
- After revert, confirm Tier 0 + Tier 1 gates pass on `main` before re-deploying.

## Merge Eligibility

mergeable when Tier 0 + Tier 1 gates are green; Tier 3 E2E is informational at merge time and required before production promotion.
