# CI/CD Gate Plan — job-registry-central

## Change ID
job-registry-central

## Required Gates

| gate | tier | required | trigger | command/workflow | artifact |
|---|---:|:---:|---|---|---|
| unit-and-integration-tests | 1 | yes | pull_request | `.github/workflows/backend-tests.yml` / `pytest tests/test_job_registry.py tests/test_async_query_job_service.py -v --tb=short` | GHA job result |
| contract-validate | 1 | yes | pull_request | `.github/workflows/contract-driven-gates.yml` / `cdd-kit validate` | GHA job result |
| ruff-lint | 1 | yes | pull_request | `ruff check src/mes_dashboard/services/job_registry.py src/mes_dashboard/services/async_query_job_service.py` | exit 0 |
| nightly-real-infra | 3 | yes | schedule (nightly) | `.github/workflows/backend-tests.yml` / `nightly-integration-real` job | GHA job result |
| multi-worker-concurrency | 3 | yes | schedule (nightly) | `.github/workflows/backend-tests.yml` / `multi-worker-concurrency` job | GHA job result |

## Workflow

No new workflow files are required. The existing `backend-tests.yml` already triggers on `pull_request` for
`src/mes_dashboard/services/**` and `tests/**`, which covers every file this change touches. The existing
`contract-driven-gates.yml` covers `cdd-kit validate`.

The `ruff-lint` gate is satisfied by the `ruff check .` step already expected in the developer local flow
(test-plan.md §Test Execution Ladder); no workflow step addition is needed because `backend-tests.yml` does
not currently run ruff — developers must run it locally as Tier 0 before pushing.

Tier 0 local fast gate (pre-push, not enforced by CI):
```
pytest tests/test_job_registry.py tests/test_async_query_job_service.py --collect-only -q
pytest tests/test_job_registry.py -v
ruff check src/mes_dashboard/services/job_registry.py src/mes_dashboard/services/async_query_job_service.py
```

## Promotion Policy

No gate promotions required for this change. All gates remain at their existing tiers. If `real-infra-smoke`
(currently informational per its inline comment in `backend-tests.yml`) is promoted to required before this PR
merges, it applies automatically; no action needed from this change.

## Rollback Policy

This change is purely additive (new module + declarative registrations; no route changes, no Redis schema
changes, no env vars). Rollback = revert the commit. The 8 `register_job_type()` calls are module-level
side-effects with no persistent state; a revert leaves all pre-existing `enqueue_xxx()` dispatch paths fully
intact per AC-5.

## Merge Eligibility

Mergeable when:
- `unit-and-integration-tests` passes (AC-6 + AC-7)
- `contract-validate` passes (AC-8)
- `ruff-lint` passes locally (Tier 0)
- All 5 tests in `tests/test_job_registry.py` are green
- `tests/test_async_query_job_service.py` zero regressions
