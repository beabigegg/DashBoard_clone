# CI/CD Gate Review

change-id: resource-history-cache-fix
tier: 1
risk: high

## Required Gates for This Change

| gate | tier | required | trigger | command/workflow | artifact |
|---|---:|:---:|---|---|---|
| pytest — resource cache suite | 1 | yes | pull_request | `pytest tests/test_resource_dataset_cache.py tests/test_resource_cache_version_check.py tests/test_resource_history_routes.py tests/test_resource_history_sql_runtime.py tests/test_resource_cache.py -v --tb=short` | test-plan.md rows AC-1–AC-8 |
| pytest — full unit/mock-integration | 1 | yes | pull_request | `backend-tests.yml` job `unit-and-integration-tests` | pass/fail |
| contract validation | 1 | yes | pull_request | `contract-driven-gates.yml` job `contract-and-fast-tests` (`cdd-kit validate`) | pass/fail |
| real-infra smoke | 2 | informational | pull_request | `backend-tests.yml` job `real-infra-smoke` | informational — non-blocking |

Gates not applicable to this change (no new frontend, no UI, no stress/soak, no new E2E spec, no new Playwright install needed): visual, CSS governance, Playwright E2E, stress, soak, weekly/manual dispatch.

## CI/CD Workflow

No new workflow files required. Existing workflows cover all required gates:

- `backend-tests.yml` — job `unit-and-integration-tests` runs `pytest tests/ --ignore=tests/e2e --ignore=tests/stress` on every PR touching `src/mes_dashboard/services/**`, `src/mes_dashboard/routes/**`, `src/mes_dashboard/core/**`, `tests/**`. All new test files (`test_resource_dataset_cache.py`, `test_resource_cache_version_check.py`, `test_resource_history_sql_runtime.py`) fall under this glob automatically.
- `contract-driven-gates.yml` — job `contract-and-fast-tests` runs `cdd-kit validate` on every PR.
- `RESOURCE_VIEW_CACHE_TTL` has a safe default of 300; no CI env-var injection needed.

## Promotion Policy

PR is merge-eligible when ALL of the following pass:

1. `pytest tests/test_resource_dataset_cache.py tests/test_resource_cache_version_check.py tests/test_resource_history_routes.py tests/test_resource_history_sql_runtime.py tests/test_resource_cache.py` — all AC-1–AC-8 test-plan rows green.
2. `backend-tests.yml` job `unit-and-integration-tests` — full mock/unit suite passes.
3. `contract-driven-gates.yml` job `contract-and-fast-tests` — `cdd-kit validate` passes (env-contract entry for `RESOURCE_VIEW_CACHE_TTL` present; contracts/CHANGELOG.md updated if contract version bumped).
4. All five TDD pre-condition tests (test-plan.md §Tests That Must Fail Before Implementation) confirm green after implementation.

`real-infra-smoke` (Tier 2, informational) failure does not block merge but must be triaged before the next release cut.

## Rollback Policy

**Post-deploy (forward migration — schema_version 1 → 2):**
```
rm tmp/query_spool/resource_dataset/*.parquet
rm tmp/query_spool/resource_oee/*.parquet
```
Run immediately after gunicorn restart. Old v1 parquet files are never looked up by v2 key hashes (miss → Oracle), but disk files do not self-clean; orphaned files waste disk and must be removed manually. Redis pointers expire by TTL without manual intervention.

**Post-rollback (reverting to schema_version 1):**
```
rm tmp/query_spool/resource_dataset/*.parquet
rm tmp/query_spool/resource_oee/*.parquet
```
Same commands. v2 parquet files are never looked up by reverted v1 readers (miss → Oracle); remove to reclaim disk space.

If Redis is unavailable or parquet is schema-incompatible at any point, both the canonical and System-A paths fall back to Oracle with no `BinderException` — service continues without manual intervention.

## Merge Eligibility

blocked until gates 1–3 above pass; `real-infra-smoke` is informational-risk only.
