# CI/CD Gate Review

change-id: prod-history-detail-partial-merge
tier: 2
last-changed: 2026-05-15

## Required Gates for This Change

| gate | tier | required | trigger | command/workflow | artifact |
|---|---:|---:|---|---|---|
| lint | 0 | yes | local / PR | `ruff check .` | — |
| type-check | 0 | informational | local / PR | `mypy src/` | — |
| cdd-kit-validate | 0 | yes | local / PR | `cdd-kit validate` | — |
| unit-mock-integration | 1 | yes | pull_request | `pytest -m "not (e2e or integration_real or stress or load or soak or multi_worker)" --ignore=tests/integration --ignore=tests/stress --ignore=tests/e2e --ignore=tests/manual -x` | junit XML |
| frontend-unit | 1 | yes | pull_request | `cd frontend && npm run test` | vitest report |
| css-governance | 1 | yes | pull_request | `cd frontend && npm run css:check` | governance report |
| frontend-type-check | 1 | informational | pull_request | `cd frontend && npm run type-check` | — |
| playwright-critical-journeys | 1 | yes | pull_request | existing `e2e-tests.yml` critical-journeys job | playwright trace |
| visual-regression | 2 | informational | pull_request | existing screenshot-diff job (production-history DataTable badge) | screenshot diff |

### Gates exercising new test-plan.md rows

- `unit-mock-integration` runs all tests in `tests/test_production_history_sql_runtime.py` (new `TestPartialMergeAggregation` class: AC-1 DuckDB path, AC-2 ABA, AC-3 strict-guard DuckDB, AC-4 pagination count, AC-5 CSV parity, AC-6 field presence, PH-06 parity) and `tests/test_production_history_service.py` (new `TestPandasFallbackAggregation` class: AC-1 pandas, AC-2 pandas ABA, AC-3 strict-guard + caplog INFO).
- `unit-mock-integration` also runs `tests/test_api_contract.py` additions: AC-4 pagination contract, AC-6 `partial_count` schema contract.
- `frontend-unit` runs `frontend/tests/legacy/production-history.test.js` additions: AC-6 badge renders / absent tests.

### Informational Gates

| gate | reason informational |
|---|---|
| visual-regression | Badge is a UI-only additive element; screenshot diff is a useful regression signal but not a merge blocker per Tier 2 policy. |
| playwright-e2e (new specs) | Excluded: existing prod-history e2e specs run as regression only; no new Playwright specs authored this change. |

### Excluded Gates (explicitly out of scope — task 2.6 skipped)

- monkey / data-boundary tests — Tier 2 exclusion; 5-key combination space covered by unit fixtures (see test-plan.md §Out of Scope)
- stress / load — Tier 4; not applicable
- soak — Tier 4; not applicable
- new nightly / manual dispatch gates — no new gate added per change-classification.md task 2.6

## CI/CD Workflow

No workflow file changes required. All gates listed above are already defined in:

- `.github/workflows/contract-driven-gates.yml` — `contract-and-fast-tests` job runs lint, cdd-kit validate, pytest unit-mock-integration
- `.github/workflows/backend-tests.yml` — `unit-and-integration-tests` job (Python 3.13 + Node 22)
- `.github/workflows/frontend-tests.yml` — `frontend-unit-tests` job (Node 22 + vue-tsc)
- `.github/workflows/e2e-tests.yml` — `e2e-critical` job (Playwright chromium)

The new test classes (`TestPartialMergeAggregation`, `TestPandasFallbackAggregation`) and contract assertions are in existing test files already covered by the `unit-mock-integration` pytest command. No include-path, marker, or ignore-list change is needed.

## Promotion Policy

Standard Tier 2 promotion path:

1. All required gates green on the PR.
2. Merge to `main`.
3. Auto-deploy to staging.
4. Manual smoke test on staging before promoting to production:
   - Open the production-history detail page with a date range known to contain lots with multiple partial trackouts.
   - Verify: (a) `partial_count` badge appears on at least one detail row, (b) row count is lower than the raw spool row count for the same range (aggregation is active), (c) CSV export contains a `PartialCount` column with values matching the badge on each row.
5. Promote to production after smoke test passes.

No informational gate (visual-regression) needs to clear before merge; it is a post-merge signal reviewed within 1 business day.

## Rollback Policy

This change is a pure view-layer and aggregation-logic change. The spool parquet schema is unchanged — no parquet cleanup is required on rollback (contrast with `prod-history-detail-raw-rows` which required `rm tmp/query_spool/production_history/*.parquet`).

Rollback steps:

1. Revert the PR commits on `main`; redeploy.
2. The `partial_count` field disappears from the API response. The frontend must handle this defensively (treat missing or absent `partial_count` as 1 and suppress the badge) — this is a design constraint for the frontend-engineer, not a rollback action.
3. No Redis key flush required (this change does not alter cache namespace or schema_version).
4. No Oracle schema change; no migration down-script needed.

If rollback occurs after a partial deploy (e.g., backend merged but frontend not yet built), the API returns `partial_count` but the frontend ignores it — safe interim state.

## Merge Eligibility

mergeable when: lint + cdd-kit-validate + unit-mock-integration + frontend-unit + css-governance + playwright-critical-journeys all green.
