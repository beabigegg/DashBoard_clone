# CI/CD Gate Plan

## Change ID
fix-admin-dashboard

## Required Gates for This Change

| gate | tier | required | trigger | command/workflow | artifact |
|---|---:|:---:|---|---|---|
| ruff-lint | 1 | yes | pull_request | `ruff check .` | pass/fail |
| mypy-type-check | 1 | yes | pull_request | `mypy src/` | pass/fail |
| vue-tsc-type-check | 1 | yes | pull_request | `cd frontend && npm run type-check` | pass/fail |
| cdd-validate | 1 | yes | pull_request | `cdd-kit validate` | pass/fail |
| pytest-unit | 1 | yes | pull_request | `pytest tests/test_log_store.py tests/test_login_session_store.py tests/test_sync_worker.py -v --tb=short` | pass/fail |
| pytest-integration | 1 | yes | pull_request | `pytest tests/test_admin_routes_logs.py tests/test_admin_routes_perf.py tests/test_admin_routes.py -v --tb=short` | pass/fail |
| coverage-report | 2 | no | pull_request | `pytest tests/test_log_store.py tests/test_login_session_store.py tests/test_sync_worker.py tests/test_admin_routes_logs.py tests/test_admin_routes_perf.py tests/test_admin_routes.py --cov=src/mes_dashboard/core --cov=src/mes_dashboard/routes/admin_routes --cov-report=term-missing` | coverage summary (informational) |

Gates map directly to test-plan.md rows. Unit-tier tests (AC-1 through AC-3) are Tier 0 commands run as part of the Tier 1 PR job. Integration, contract, data-boundary, and resilience tests (AC-1, AC-4 through AC-7) are all pre-merge via the same pytest invocation.

No nightly, weekly, or manual gates are introduced. Real-MySQL and real-Redis tests are out of scope per test-plan.md "Out of Scope".

## CI/CD Workflow

No new workflow files are required. All gates are handled by the existing `.github/workflows/backend-tests.yml` `unit-and-integration-tests` job, which already triggers on `pull_request` for `src/mes_dashboard/core/**` and `src/mes_dashboard/routes/**` and `tests/**` path filters. The five affected files (`log_store.py`, `login_session_store.py`, `sync_worker.py`, `duckdb_runtime.py`, `admin_routes.py`) and new test files under `tests/` all fall within those path filters — no workflow edits needed.

The `contract-driven-gates.yml` `contract-and-fast-tests` job covers `cdd-kit validate` and runs on every PR unconditionally.

### Concurrency
Both workflows already cancel in-progress runs per `github.ref` via GitHub's default behavior. No additional concurrency group is needed.

### Artifact retention
Hypothesis failure examples: `retention-days: 7` (set in the existing backend-tests.yml artifact upload step). No new artifacts are produced by this change.

## Promotion Policy

Merge to `main` is permitted when all Tier 1 required gates pass (green):
- `unit-and-integration-tests` job in `backend-tests.yml`
- `contract-and-fast-tests` job in `contract-driven-gates.yml`

The coverage-report gate (Tier 2) is informational. A failing or low-coverage result does not block merge but must be noted in the PR description.

No staging or canary promotion step is required; this change is backend monitoring and bug-fix only, with no new external dependencies or env vars.

## Rollback Policy

Revert the merge commit (`git revert <sha>`) and redeploy. No additional cleanup is required:

- No parquet or spool files are created (admin monitoring endpoints; no DuckDB query spool).
- No new env vars or config keys are introduced; reverting code is sufficient.
- No database schema changes; SQLite schema is append-compatible and the TRUNCATE guard only affects MySQL at SyncWorker startup.
- If the revert is needed due to a regression in `/admin/api/logs` pagination, the previous merge commit restores the prior offset logic immediately on redeploy.

## Merge Eligibility
mergeable — all required Tier 1 gates are covered by existing workflows with no workflow changes needed.
