---
change-id: fix-matrix-distinct-count
schema-version: 0.1.0
last-changed: 2026-05-14
risk: medium
tier: 2
---

# CI/CD Gate Plan: fix-matrix-distinct-count

Tier 2 backend-only bug fix (matrix distinct-count rollup, Option C). No CI
workflow/pipeline change. Existing gates fully cover this change.

## Local Gates (pre-PR)

| gate | command |
|---|---|
| lint | `ruff check .` |
| backend tests | `pytest tests/test_production_history_sql_runtime.py tests/test_production_history_routes.py tests/test_api_contract.py` |
| contract-validate | `cdd-kit validate --contracts` |
| gate-readiness | `cdd-kit gate fix-matrix-distinct-count` |

Local sweep verified green: 97 passed.

## PR Required Gates (block merge)

**Trigger:** all gates below run on `pull_request` to `main` (push / PR triggers
per ci-gate-contract.md §Workflow Configuration).

| gate | tier | workflow file / job | required | notes |
|---|---:|---|---:|---|
| lint | 0 | `.github/workflows/backend-tests.yml` | yes | `ruff check .` |
| contract-validate | 0 | `.github/workflows/contract-driven-gates.yml` | yes | `cdd-kit validate` — picks up data 1.3.0 / business 1.5.0 |
| unit-mock-integration | 1 | `.github/workflows/backend-tests.yml` → `unit-and-integration-tests` | yes | the 15 new tests in `tests/test_production_history_sql_runtime.py` land here (TestMatrixDistinctCountRollup, TestMatrixTreeNodeShape, TestMatrixDualPathParity, TestMatrixDataBoundary) |

No frontend gate is exercised — matrix node shape unchanged, no UI/route change.

## Informational Gates

| gate | tier | command | notes |
|---|---:|---|---|
| type-check (mypy) | 0/2 | `mypy src/` | informational per ci-gate-contract. mypy is not pinned in `environment.yml` and not installed in the `mes-dashboard` conda env (per backend-engineer); status unchanged — non-blocking. |

## Rollback Policy

Pure code fix confined to three functions in
`src/mes_dashboard/services/production_history_sql_runtime.py`. Rollback is a
mechanical `git revert` of the service-file commit. Contract updates (data-shape
1.2.0→1.3.0 §3.5, business 1.4.0→1.5.0 PH-05) are additive precision updates —
they tighten the spec of an existing field with no removal. No SQL template
change (matrix SQL is inline; `sql/production_history/` untouched), no spool
parquet schema change (Option C only changes the in-DuckDB aggregation grain over
the existing row source — **no parquet cleanup required**), no Oracle DDL, no env
change. The matrix endpoint holds no persisted state; the next request recomputes
from spool. No cache invalidation, no post-deploy step.

## Promotion Policy

No new gate is introduced. The 15 new tests are absorbed by the existing
`unit-mock-integration` (Tier 1, required) gate via its current `pytest` command —
no command edit needed. The informational `type-check` (mypy) gate continues to
follow the existing ci-gate-contract Informational Gate Promotion Policy
unchanged. No gate promotion or demotion in this change.

## Gate Compatibility Notes

- Gate tiers unchanged; no gate added, removed, or modified.
- No new workflow file. No edit to `.github/workflows/*.yml`, `Makefile`, or CI
  config.
- No ci-gate-contract schema-version bump required — gate inventory, tiers,
  commands, and triggers are all unchanged.
