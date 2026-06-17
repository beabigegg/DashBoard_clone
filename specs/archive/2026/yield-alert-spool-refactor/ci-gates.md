# CI/CD Gate Review — yield-alert-spool-refactor

change-id: yield-alert-spool-refactor
risk: high | tier: 1
last-changed: 2026-06-16

## Required Gates for This Change

| gate | tier | required | trigger | command/workflow | artifact |
|---|---:|:---:|---|---|---|
| lint | 0 | yes | local/PR | `ruff check .` | — |
| contract-validate | 0 | yes | local/PR | `cdd-kit validate` | — |
| openapi-sync | 0 | yes | local/PR | `cdd-kit openapi export --check` | — |
| response-shape-validate | 1 | yes | push/PR | `cdd-kit validate --contracts` | — |
| unit-mock-integration | 1 | yes | push/PR | `pytest -m "not (e2e or integration_real or stress or load or soak or multi_worker)" --ignore=tests/integration --ignore=tests/stress --ignore=tests/e2e --ignore=tests/manual -x` | junit XML |
| frontend-unit | 1 | yes | push/PR | `cd frontend && npm run test` | vitest report |
| css-governance | 1 | yes | push/PR | `cd frontend && npm run css:check` | governance report |
| frontend-type-check | 1 | informational | push/PR | `cd frontend && npm run type-check` | — |
| playwright-resilience | 1 | yes | PR | `cd frontend && npx playwright test tests/playwright/resilience/` (includes `test_spool_missing_returns_410_no_oracle_fallback`) | playwright trace |
| playwright-data-boundary | 1 | yes | PR | `cd frontend && npx playwright test tests/playwright/data-boundary/` | playwright trace |
| yield-alert-e2e | 1 | informational | PR | `pytest tests/e2e/test_yield_alert_e2e.py -m local_e2e` | playwright trace |
| visual-regression | 2 | informational | PR | Playwright screenshot diff (trend/cards/heatmap/alert table) | screenshot diff |
| nightly-integration | 3 | yes (nightly) | schedule/dispatch | `pytest tests/integration/ --run-integration-real -m "integration_real or multi_worker" -x` | test report |
| yield-alert-stress | 3 | yes (nightly) | schedule/dispatch | `pytest tests/stress/test_yield_alert_stress.py -m stress` | perf report |
| yield-alert-soak | 4 | yes (weekly) | schedule/dispatch | `pytest tests/integration/test_soak_workload.py --run-integration-real -m soak` (covers rq_yield_alert_worker warmup) | soak report |
| schema-version-pin | 5 | yes (manual pre-deploy) | manual dispatch | Verify `_SCHEMA_VERSION` bumped to target value in `yield_alert_dataset_cache.py` | operator sign-off |
| parquet-rollback-runbook | 5 | yes (manual pre-deploy) | manual dispatch | Verify deploy/rollback runbook contains `rm -f tmp/query_spool/yield_alert_dataset/*.parquet` | operator sign-off |

## Workflow

Affected workflow files (no new files required; existing gates cover all tiers):

- `.github/workflows/backend-tests.yml` — `unit-and-integration-tests` job runs `unit-mock-integration` gate; picks up new tests in `tests/test_yield_alert_routes.py`, `tests/test_yield_alert_dataset_cache.py`, `tests/test_yield_alert_service.py` automatically via existing pytest command. Deleted test (`test_compute_reject_linkage_batches_workorders_for_oracle_in_limit`) and updated test (`test_query_yield_trend_uses_movetxn_…`) require no workflow change — they are selected/excluded by the same marker filter.
- `.github/workflows/frontend-tests.yml` — `frontend-unit-tests` job picks up changes to `frontend/tests/validation/useYieldAlert.validation.test.js` and `frontend/tests/yield-alert/App.cross-filter.test.js` via `npm run test` with no filter change. `npx playwright install --with-deps chromium` step already present (per downtime-browser-duckdb note); verify it covers `test_yield_alert_e2e.py` Playwright invocations.
- `.github/workflows/contract-driven-gates.yml` — `contract-and-fast-tests` job runs `response-shape-validate` (`cdd-kit validate --contracts`) and `openapi-sync` (`cdd-kit openapi export --check`). Both must pass after `contract-reviewer` regenerates `contracts/openapi.json` and `tests/contract/response-samples.json` with the new `type` param and `source_code`/`lot` fields.

Concurrency (PR workflows):
```yaml
concurrency:
  group: ${{ github.ref }}
  cancel-in-progress: true
```

## Promotion Policy

A build is eligible for promotion to production when ALL of the following hold:

1. All Tier 1 required gates pass on the PR HEAD commit (unit-mock-integration, frontend-unit, css-governance, response-shape-validate, playwright-resilience, playwright-data-boundary).
2. `cdd-kit validate` and `cdd-kit openapi export --check` pass locally (Tier 0).
3. The Tier 2 visual-regression informational gate has been reviewed; any screenshot differences are documented in `visual-review-report.md`.
4. At least one nightly-integration run (Tier 3) has passed on or after the merge commit, confirming `yield-alert-stress` (`test_spool_build_latency_under_1m_rows`, `test_duckdb_view_query_p95_under_2x_volume`) are green.
5. `qa-reviewer` has signed off `qa-report.md` (correctness of GA%/GC% totals vs baseline — AC-3).
6. `regression-report.md` documents that GA% TX/SCRAP totals match the pre-refactor baseline (AC-3).
7. Manual Tier 5 pre-deploy checklist completed: `_SCHEMA_VERSION` bumped (AC-6), rollback `rm` command verified in runbook.

## Rollback Policy

**Zero-downtime rollback path:**
1. Revert the change commits on `main` (or deploy the previous release tag).
2. Run `rm -f tmp/query_spool/yield_alert_dataset/*.parquet` on every gunicorn host before restarting. Stale parquets with the new schema version will cause DuckDB read errors against the old code. This step is mandatory.
3. Reload/restart gunicorn. The old live Oracle query paths (trend.sql/summary.sql) are restored; no spool warmup is needed for rollback.
4. `rq_yield_alert_worker` warmup jobs in the RQ queue will be dequeued and fail gracefully (old code ignores unknown spool column); no RQ worker restart required unless the queue is saturated.

**Forward migration (preferred — no rollback needed):**
- Bumping `_SCHEMA_VERSION` in `yield_alert_dataset_cache.py` orphans all live parquets by cache key; new spool build begins automatically on next warmup cycle. No manual `rm` required if the schema-version key changes sufficiently.

**Tier 1 gate failure on main:** no new PRs may merge until the gate is green (per ci-gate-contract.md Required Check Policy).

**Tier 3/4 failure:** open incident ticket within 1 business day; triage and fix or demote to informational with owner + exit date.

## Merge Eligibility

**blocked** until all Tier 1 required gates pass AND Tier 5 manual checklist is confirmed pre-deploy.

Informational gates (frontend-type-check, yield-alert-e2e, visual-regression) do not block merge; failures must be documented.

---

References: test-plan.md (AC-1 through AC-8 rows), ci-gate-contract.md Gate Inventory, change-classification.md Required Tests.

