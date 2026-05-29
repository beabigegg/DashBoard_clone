# CI/CD Gate Plan: ai-pipeline-upgrade

## Required Gates for This Change

| gate | tier | required | trigger | command/workflow | artifact |
|---|---:|:---:|---|---|---|
| targeted-pytest | 1 | yes | pull_request | `pytest tests/test_ai_query_service.py tests/test_ai_function_registry.py tests/test_ai_query_understanding.py -v` | test-plan.md rows AC-1 through AC-7 (22 tests) |
| full-pytest | 1 | yes | pull_request | `pytest tests/ --ignore=tests/e2e --ignore=tests/stress -q` | no regressions across full suite |
| ruff-lint | 1 | yes | pull_request | `ruff check src/mes_dashboard/services/` | zero lint errors in affected services |
| cdd-validate | 1 | yes | pull_request | `cdd-kit validate` | contract schema-version bumps + required artifact presence |
| cdd-gate | 1 | yes | pull_request | `cdd-kit gate ai-pipeline-upgrade` | all required tasks done |

No new gates are introduced. All five gates run on the existing `backend-tests.yml`
(`unit-and-integration-tests` job) and `contract-driven-gates.yml`
(`contract-and-fast-tests` job) workflows, which already trigger on
`pull_request` for changes under `src/mes_dashboard/services/**` and `tests/**`.

## CI/CD Workflow

No workflow file changes are required. The affected paths
(`src/mes_dashboard/services/ai_query_service.py`,
`src/mes_dashboard/services/ai_function_registry.py`,
`tests/test_ai_query_service.py`, `tests/test_ai_function_registry.py`,
`tests/test_ai_query_understanding.py`) all fall within the existing
`pull_request` path filters in `.github/workflows/backend-tests.yml`.

Tier 3 nightly / Tier 4 weekly / Tier 5 manual gates: not introduced by this
change. Live-LLM E2E and `chat_history` soak are explicitly out of scope per
test-plan.md §Out of Scope.

## Promotion Policy

- All five required gates (targeted-pytest, full-pytest, ruff-lint,
  cdd-validate, cdd-gate) must be green before the PR is eligible for merge.
- The `unit-and-integration-tests` job name in `backend-tests.yml` is the
  required status check bound in branch protection. No new check name is added.
- If `TestCombinedCallMalformedJson` or `TestCombinedCallPartialJson` are
  quarantined due to flakiness, they must be moved to an informational job with
  an assigned owner and a 14-day exit date before merge is unblocked.

## Rollback Policy

- This change modifies Python service-layer code only (no migrations, no new
  env vars, no static assets, no spool schema changes).
- Rollback: revert the merge commit; no additional cleanup steps are required.
- No parquet spool files are affected (AI query pipeline does not use DuckDB
  spool storage).

## Merge Eligibility

mergeable when all five required gates are green and no Tier 1 tests are
quarantined without an owner + exit date.
