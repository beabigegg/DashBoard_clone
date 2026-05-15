# CI/CD Gate Plan

## Change ID

query-tool-partial-trackout

## Required Gates

| gate | tier | required | trigger | command/workflow | artifact |
|---|---:|---:|---|---|---|
| contract-validate | 0 | yes | local pre-PR | `cdd-kit validate` | — |
| lint | 0 | yes | local / PR | `ruff check .` | — |
| unit-mock-integration | 1 | yes | PR / push main | `pytest -m "not (e2e or integration_real or stress or load or soak or multi_worker)" --ignore=tests/integration --ignore=tests/stress --ignore=tests/e2e --ignore=tests/manual -x` via `backend-tests.yml` job `unit-and-integration-tests` | junit XML (30 days) |
| nightly-integration | 3 | informational | nightly schedule / dispatch | `pytest tests/integration/ --run-integration-real -m "integration_real or multi_worker" -x` via `backend-tests.yml` job `nightly-integration-real` | test report (30 days) |

### Gate scoping notes

- **unit-mock-integration** covers all new tests in `test-plan.md`:
  - `tests/test_query_tool_partial_trackout.py` — all AC-1 through AC-8 test classes (SQL structure, aggregation, strict-guard, decrementing-TRACKINQTY, API response shape, contract file presence)
  - `tests/test_query_tool_sql_runtime.py` — extended `TestTryComputePageFromSpool::test_partial_count_present_in_returned_data`
  - No Oracle connection required; DuckDB in-process parquet fixtures suffice.
- **nightly-integration** — no existing `integration_real`-marked query-tool test files exist (`grep -l integration_real tests/test_query_tool_*.py` returns empty). Gate applies if such tests are added in a follow-on change; it does not block this PR.
- **Excluded gates** (not applicable to this change):
  - `frontend-unit`, `css-governance`, `frontend-type-check` — no frontend files modified.
  - `playwright-*` — no UI change; test-plan.md §Out of Scope confirms E2E excluded.
  - `stress-load`, `soak` — test-plan.md §Out of Scope confirms stress/soak excluded.
  - `visual-regression` — no UI change.

## CI/CD Workflow

No new workflow files are required. The two existing workflows that cover this change are:

| workflow file | job | what it covers |
|---|---|---|
| `.github/workflows/backend-tests.yml` | `unit-and-integration-tests` | Tier 1 unit + mock-integration; triggers on PR and push to main when `src/mes_dashboard/sql/**` or `tests/**` change |
| `.github/workflows/backend-tests.yml` | `nightly-integration-real` | Tier 3 nightly; schedule / dispatch only |

The `backend-tests.yml` path filter already includes `src/mes_dashboard/sql/**`, which covers the three modified SQL files (`lot_history.sql`, `equipment_lots.sql`, `adjacent_lots.sql`). No path-filter amendment is needed.

The `contract-driven-gates.yml` `contract-and-fast-tests` job runs `cdd-kit validate` on every push and PR, covering the contract-validate gate.

## Promotion Policy

This change introduces no new gates and does not alter the tier of any existing gate. The standard Tier 2 promotion policy from `contracts/ci/ci-gate-contract.md` applies:

- No informational gate is added by this change; all required gates are already in Tier 1.
- If a future change adds `integration_real`-marked query-tool tests, the nightly-integration gate already covers them under the existing `backend-tests.yml` `nightly-integration-real` job — no promotion action needed at that point.

## Rollback Policy

- **No spool parquet cleanup required.** The query-tool executes on-demand Oracle SQL and does not persist DuckDB parquet files (unlike production-history or resource-history). No `rm tmp/query_spool/query_tool/*.parquet` step is needed in any deploy or rollback runbook.
- **No cache namespace conflict.** The partial-trackout fix is purely SQL / Python runtime logic; it writes no new Redis keys and changes no cache schema version.
- **Revert path.** If regressions appear post-deploy, revert the three SQL files (`lot_history.sql`, `equipment_lots.sql`, `adjacent_lots.sql`) and `query_tool_sql_runtime.py` to their pre-change state. No data migration, sentinel file, or parquet cleanup is required after revert.
- **Branch protection.** If any Tier 1 gate turns red on main, no additional PRs may merge until the gate is green, per `contracts/ci/ci-gate-contract.md §Rollback Policy`.

## Artifact Retention

| artifact | retention |
|---|---|
| pytest / junit XML | 30 days |

## Merge Eligibility Decision

mergeable — existing Tier 1 gate (`unit-and-integration-tests` in `backend-tests.yml`) is sufficient. No new workflow files required. No frontend, no env, no new workers, no parquet cleanup.
