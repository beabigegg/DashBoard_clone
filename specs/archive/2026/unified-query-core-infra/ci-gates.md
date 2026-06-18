# CI/CD Gate Plan

## Change ID
unified-query-core-infra

## Required Gates for This Change
| gate | tier | required | trigger | command/workflow | artifact |
|---|---:|---:|---|---|---|
| unit-mock-integration | 1 | yes | pull_request | `pytest tests/ --ignore=tests/e2e --ignore=tests/stress -v` (backend-tests.yml · unit-and-integration-tests) | junit XML, 30 days |
| contract-validate | 1 | yes | push / pull_request | `cdd-kit validate --contracts` (contract-driven-gates.yml · contract-and-fast-tests) | — |
| cdd-kit-gate | 1 | yes | pull_request | `cdd-kit gate unified-query-core-infra` (contract-driven-gates.yml · contract-and-fast-tests) | — |
| lint | 0 | yes | local / pull_request | `ruff check .` | — |
| type-check | 2 | informational | pull_request | `mypy src/` (continue-on-error) | — |
| nightly-oracle-pool | 3 | yes (nightly) | schedule / dispatch | `pytest tests/integration/test_oracle_arrow_pool_lifecycle.py --run-integration-real` (backend-tests.yml · nightly-integration-real) | test report, 30 days |

### Confirmed Workflow Coverage

`backend-tests.yml` job `unit-and-integration-tests` runs:

```
python -m pytest tests/ --ignore=tests/e2e --ignore=tests/stress
```

This glob picks up all new root-level test files without any workflow edit:
- `tests/test_oracle_arrow_reader.py`
- `tests/test_query_cost_policy.py`
- `tests/test_base_chunked_duckdb_job.py`
- `tests/contract/test_env_duckdb_job_dir.py` (collected via `tests/` root include)

The trigger path filter already includes `src/mes_dashboard/core/**` and `tests/**`
(backend-tests.yml lines 11, 15), so this PR will trigger the workflow correctly.

`tests/integration/test_oracle_arrow_pool_lifecycle.py` carries `pytestmark =
pytest.mark.integration_real` and is therefore excluded from the pre-merge sweep
(ignored by `--ignore=tests/integration` convention in ci-gate-contract.md §Test markers).
It runs under `nightly-integration-real` only.

No new workflow files are required.

## Workflow Changes Applied

No workflow file was modified. Existing workflow coverage is sufficient:
- `.github/workflows/backend-tests.yml` — picks up new `tests/` root files via wildcard
  `tests/ --ignore=tests/e2e --ignore=tests/stress`; path filter covers `core/**` and
  `tests/**`; `nightly-integration-real` job covers `tests/integration/` on schedule.
- `.github/workflows/contract-driven-gates.yml` — `cdd-kit validate --contracts` step
  validates env and data-shape contract additions; no step changes needed.

## Promotion Policy

PR merges when all Tier 1 required gates pass (`unit-mock-integration`,
`contract-validate`, `cdd-kit-gate`, `lint`).

The `nightly-oracle-pool` (Tier 3) integration gate is informational pre-merge
(no real Oracle in PR runners) and required post-merge: it must pass within 24 h
of merge. A red nightly within that window blocks the next PR to `main` until
triaged.

`type-check` (Tier 2, informational) follows the standard 20-day / 60-run
promotion criteria in ci-gate-contract.md §Informational Gate Promotion Policy.

## Rollback Policy

Pure new-module addition — no existing route, service, worker, or frontend
module was modified (AC-7). Rollback steps:

1. Delete the 3 new `core/` files:
   `oracle_arrow_reader.py`, `query_cost_policy.py`, `base_chunked_duckdb_job.py`.
2. Revert `contracts/env/env-contract.md`, `.env.example.template`,
   `contracts/env/env.schema.json` to pre-change state (remove `DUCKDB_JOB_DIR`
   additions; remove deprecation notices on `*_ASYNC_DAY_THRESHOLD` rows).
3. Revert `contracts/data/data-shape-contract.md` to pre-change state.
4. The canonical parquet spool is unaffected — no callers exist yet, so no
   spool cleanup is required.
5. No gunicorn restart side-effects; modules are not imported by any existing
   route or worker.

## Merge Eligibility

mergeable when: `unit-mock-integration` green, `contract-validate` green,
`cdd-kit-gate` green, `lint` green. Nightly `nightly-oracle-pool` is
informational pre-merge.
