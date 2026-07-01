# CI/CD Gate Plan

## Change ID
yield-alert-kpi-csv-parity (Tier 2, medium risk, no new CI/CD surface per
change-classification.md tasks 2.6/4.4 = not applicable)

## Required Gates
| gate | tier | required | trigger | command/workflow | expected artifact |
|---|---:|---:|---|---|---|
| lint | 1 | yes | pull_request | `ruff check .` (backend-tests.yml) | job pass/fail |
| type-check | 1 | yes | pull_request | `npm run type-check` (frontend-tests.yml, vue-tsc --noEmit — App.vue touched) | job pass/fail |
| unit (backend) | 1 | yes | pull_request | `pytest tests/test_yield_alert_sql_runtime.py tests/test_yield_alert_service.py tests/test_yield_alert_routes.py -v` (backend-tests.yml `unit-and-integration-tests`) | pytest report |
| unit (frontend) | 1 | yes | pull_request | `npm run test` — `frontend/tests/yield-alert/App.csv-export.test.js` (frontend-tests.yml vitest step) | vitest report |
| contract | 1 | yes | pull_request | `pytest tests/test_yield_alert_contracts.py` + `cdd-kit validate --contracts` (contract-driven-gates.yml) | contract sample diff (test-plan.md AC-6/AC-7) |
| integration | 1 | yes | pull_request | `pytest tests/test_yield_alert_service.py::TestKpiCsvReconciliation` (test-plan.md AC-1/AC-4 row) | pytest report |
| data-boundary | 1 | yes | pull_request | `pytest tests/test_yield_alert_sql_runtime.py -k "double_count or department_name_split or naive_sum"` + CSV float-residue case in App.csv-export.test.js (test-plan.md data-boundary row) | pytest/vitest report |
| e2e-critical | 1 | no (deferred, optional) | pull_request | `frontend/tests/playwright/yield-alert-csv-export.spec.ts` — not authored for this change per test-plan.md "Out of Scope" | n/a |
| visual | 2 | n/a | — | no visual/layout change (change-classification: visual-review-report.md = no) | n/a |
| css:check | — | n/a | — | not relevant — no CSS files touched | n/a |
| resilience / fuzz / stress / soak | 3/4 | n/a | — | not required — no new spool-miss path or load surface (change-classification: stress-soak-report.md = no) | n/a |
| full pytest suite | informational | no | pull_request | `pytest tests/` (backend-tests.yml, already runs on every PR as the repo's standing gate) | pytest report, broader regression smoke |

## New Workflow Changes
None. No `.github/workflows/*.yml` or `Makefile` edits required — this change
reuses `backend-tests.yml` (`unit-and-integration-tests` job), `frontend-tests.yml`
(vitest + vue-tsc), and `contract-driven-gates.yml` (`cdd-kit validate --contracts`)
as-is. Matches change-classification.md: task 2.6 (CI/CD contract) and 4.4
(CI/CD workflows) are marked not-applicable — existing gates already cover the
required test families listed in test-plan.md.

## Required Check Policy
Branch protection already binds to the existing named jobs (`unit-and-integration-tests`,
`frontend-tests`, `contract-driven-gates`) — no new required-check names to register.
All rows marked `required: yes` above must pass before merge to main.

## Informational Gate Promotion Policy
The full `pytest tests/` run (informational row above) is not a new gate — it is
the existing standing CI job and already required in this repo's convention; it is
listed informationally here only to flag that it re-validates unrelated yield-alert
paths (`query_alert_candidates()` legacy pandas path, trend/heatmap) beyond this
change's bounded ladder. No flaky-test quarantine is introduced by this change.
No gate promotion (tier change) is proposed.

## Rollback Policy
Per design.md "Migration / Rollback": no schema, spool, or data migration — this
change touches in-memory DuckDB aggregation (`yield_alert_sql_runtime.py`) and one
frontend CSV formatter (`App.vue`) only. Rollback is a straight code revert of the
runtime, route, and Vue changes plus the YA-13 business-rules.md entry; no cache
purge or spool re-warm is needed. Feature flag `YIELD_ALERT_SQL_VIEW_ENABLED`
already gates the SQL-view path as a kill switch — if the rescoped KPI regresses
in production, disabling the flag falls back to the legacy `query_alert_candidates()`
path without a deploy.

## Artifact Retention
No new artifacts. Existing pytest/vitest CI logs and contract-sample diffs follow
repo-standard CI retention; no new `retention-days` overrides required.

## Merge Eligibility Decision
mergeable — contingent on all `required: yes` gates above passing
(`cdd-kit gate yield-alert-kpi-csv-parity` must pass), including regenerated
contract samples (`get_yield_alert_view.json`, `get_yield_alert_summary.json`)
showing only expected value drift, no shape drift (test-plan.md AC-7). No special
deployment sequencing needed since there is no schema/data migration to stage
ahead of the code deploy.

## Notes
See test-plan.md's "Acceptance Criteria → Test Mapping" and "Test Families
Required" tables for full test-file-to-AC traceability; this file states gate
policy only, not test strategy. Tasks 6.2/6.3 = done (Tier-1 ladder above is the
full required set); task 6.4 = skipped, no nightly/weekly/manual gate needed
(no new load, concurrency, or real-infra surface per change-classification.md).
