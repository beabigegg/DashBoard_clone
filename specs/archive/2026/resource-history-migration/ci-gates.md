# CI/CD Gate Review — resource-history-migration

## Required Gates for This Change

| gate | tier | required | trigger | command/workflow | artifact |
|---|---:|:---:|---|---|---|
| lint | 0 | yes | local pre-PR | `ruff check .` | — |
| contract-validate | 0 | yes | local pre-PR | `cdd-kit validate` | — |
| response-shape-validate | 1 | yes | push/PR | `cdd-kit validate --contracts` (contract-driven-gates.yml) | — |
| unit-mock-integration | 1 | yes | push/PR | `pytest -m "not (e2e or integration_real or stress or load or soak or multi_worker)" --ignore=tests/integration --ignore=tests/stress --ignore=tests/e2e --ignore=tests/manual -x` (backend-tests.yml) | junit XML |
| frontend-unit | 1 | yes | push/PR | `cd frontend && npm run test` (frontend-tests.yml) | vitest report |
| css-governance | 1 | yes | push/PR | `cd frontend && npm run css:check` (frontend-tests.yml) | governance report |
| playwright-resilience | 1 | yes | PR | `cd frontend && npx playwright test tests/playwright/resilience/` (frontend-tests.yml) | playwright trace |
| playwright-critical-journeys | 1 | yes | PR | `cd frontend && npx playwright test tests/playwright/hold-overview.spec.js tests/playwright/reject-history.spec.js tests/playwright/query-tool.spec.js tests/playwright/eap-alarm.spec.js` (frontend-tests.yml) | playwright trace |
| nightly-integration (parity) | 3 | yes (nightly, required before flag promotion) | schedule / dispatch | `pytest tests/integration/ --run-integration-real -m "integration_real or multi_worker" -x` (nightly-integration workflow) | test report |
| stress-load | 4 | yes (weekly, required before flag promotion) | schedule / dispatch | `pytest tests/stress/ -m "stress or load"` (scheduled-stress-soak workflow) | perf report |

## Workflow Changes

No new workflow files are introduced. All new test files (`tests/test_resource_history_unified_job.py`, `tests/test_resource_history_job_service.py`, extensions to `tests/test_resource_history_service.py`, `tests/test_query_cost_policy.py`, `tests/test_async_query_job_service.py`) are auto-discovered by existing `backend-tests.yml` `unit-and-integration-tests` job via glob over `tests/`. The new integration test (`tests/integration/test_resource_history_rq_async.py` extensions) is auto-discovered by the `nightly-integration` job and skipped pre-merge (`integration_real` marker). No gate tier, command, or required-check status is changed. CI unit tests must mock `is_async_available()` (not spool-hit) when testing async-gated routes — `backend-tests.yml` has no Redis service.

## Promotion Policy

The feature flag `RESOURCE_HISTORY_USE_UNIFIED_JOB` defaults `off`. Before promoting the flag to `on` in any environment ALL of the following must pass:

1. All Tier 1 required gates pass on the PR that introduces the worker files.
2. Tier 3 nightly-integration gate passes (`test_resource_history_rq_async.py` parity tests: `TestUnifiedJobParity::test_base_job_parity_vs_legacy_spool`, `TestUnifiedJobParity::test_oee_job_parity_vs_legacy_spool`) — see test-plan.md §AC-3.
3. Tier 4 stress-load gate passes for the resource-history query path (two RQ jobs per export doubles queue traffic; stress budget must be validated before production enablement).
4. OEE ±30d reject seam parity confirmed green at Tier 3 (test-plan.md §Data-Boundary Strategy).

No partial flag promotion (e.g., enabling only the base job) is permitted; both jobs must be validated together.

## Rollback Policy

Instant rollback: set `RESOURCE_HISTORY_USE_UNIFIED_JOB=off`. Because this is a module-level constant frozen at boot, a **full restart** of gunicorn and the resource-history workers is required — `kill -HUP` (graceful reload) is insufficient. Worker env-var parity: the `resource-history-query` RQ worker systemd unit must export `RESOURCE_HISTORY_USE_UNIFIED_JOB` so the flag value is consistent between gunicorn and workers. No spool cleanup is required on rollback: the spool schema is identical between the unified and legacy paths (design.md §Migration/Rollback Strategy, AC-6). No parquet `_SCHEMA_VERSION` bump is needed.

## Deploy Checklist

1. Ensure `RESOURCE_HISTORY_USE_UNIFIED_JOB` is absent (or explicitly `off`) on all nodes before first deploy — flag defaults `off` so no action is needed on fresh installs.
2. Confirm both `resource_history_base_worker` and `resource_history_oee_worker` job types appear in `async_query_job_service` registry after gunicorn start (checked by AC-9; `test_async_query_job_service.py` asserts registration).
3. Confirm `_APPROVED_CALLERS` in `test_query_cost_policy.py` includes both new worker modules; cost-policy gate must be green before worker files ship.
4. When promoting flag to `on`: verify `resource-history-query` RQ worker queue shows ≥ 1 worker in Admin Dashboard → Worker Status before setting flag.
5. Worker unit env-var parity: the `resource-history-query` systemd unit (existing) must export `RESOURCE_HISTORY_USE_UNIFIED_JOB` before flag-on promotion.

## Merge Eligibility

**Mergeable** when all Tier 1 required gates pass (unit-mock-integration, response-shape-validate, frontend-unit, css-governance, playwright-resilience, playwright-critical-journeys). Flag defaults `off`; no production behavior change on merge. Tier 3/4 gates are prerequisites for flag promotion, not for merge.
