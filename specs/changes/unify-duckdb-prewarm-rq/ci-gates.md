# CI/CD Gate Plan

## Change ID
unify-duckdb-prewarm-rq

## Required Gates
| gate | tier | required | trigger | command/workflow | artifact |
|---|---:|:---:|---|---|---|
| lint | 1 | yes | pull_request | `ruff check .` | pass/fail |
| type-check | 1 | yes | pull_request | `cd frontend && npm run type-check` | pass/fail |
| unit-mock-integration | 1 | yes | pull_request | `pytest tests/ -m "not integration_real"` | pass/fail |
| contract-validate | 1 | yes | pull_request | `cdd-kit validate` | pass/fail |
| resilience | 1 | yes | pull_request | `pytest tests/test_rq_warmup_resilience.py` | pass/fail |
| css-governance | 1 | yes | pull_request | `cd frontend && npm run css:check` | pass/fail |
| nightly-integration | 3 | yes | schedule (nightly) | `pytest tests/integration/ --run-integration-real` | pass/fail |

## CI/CD Workflow
No new workflow files are needed. All gates run inside the existing
`.github/workflows/ci.yml` (Tier 1) and `.github/workflows/nightly.yml`
(Tier 3) workflows unchanged.

The `unit-mock-integration` job covers all test families listed in
test-plan.md §Test Families: unit (Tier 0), contract, resilience (all Tier 1),
and the new test files `tests/test_app_startup.py`,
`tests/test_rq_warmup_resilience.py`, `tests/test_spool_warmup_scheduler.py`.

The `nightly-integration` job covers test-plan.md Tier 3 rows:
`test_rq_warmup_enqueued_for_*`, `test_no_daemon_prewarm_thread_*`,
`test_downtime_prewarm_runs_once_across_two_workers` (via GunicornHarness).

## Promotion Policy
A PR is eligible for merge when all Tier 1 required gates are green on the
head commit. The `nightly-integration` gate is blocking for the nightly run
immediately following merge; a red nightly triggers a revert or hotfix before
the next deploy window.

## Rollback Policy
Schema unchanged — no parquet cleanup required on rollback.

To revert: restore the `start_duckdb_prewarm()` daemon-thread call sites
removed from `app.py`, and revert the TTL constants in
`resource_history_duckdb_cache.py` and `downtime_analysis_duckdb_cache.py`
from 72000 s back to 7200 s. No spool file deletion or database migration is
needed.

## Merge Eligibility
mergeable when lint, type-check, unit-mock-integration, contract-validate,
resilience, and css-governance are all green; nightly-integration is informational
until the first post-merge nightly run completes.
