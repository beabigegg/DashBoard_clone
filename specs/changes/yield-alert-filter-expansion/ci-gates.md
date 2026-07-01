# CI/CD Gate Plan

## Change ID
yield-alert-filter-expansion (Tier 2, medium risk, module-level; no new endpoint/env var/concurrency wiring)

## Required Gates
| gate | tier | required | trigger | command/workflow | expected artifact |
|---|---:|---:|---|---|---|
| Backend unit tests (process_type enum validation, query_id hash disjointness, LIKE-pattern mutual exclusivity) — test-plan.md AC-2/AC-3 rows | 0 | yes | pull_request | `.github/workflows/backend-tests.yml` job `unit-and-integration-tests` → `pytest tests/ --ignore=tests/e2e --ignore=tests/stress` | pass/fail |
| Backend unit tests (`_query_filter_options()`/`compute_cross_filter_options()` departments dimension, spool vs filter_cache assertions) — test-plan.md AC-5/AC-8 rows | 0 | yes | pull_request | same job as above (file glob already includes `tests/test_yield_alert_*.py`) | pass/fail |
| Data-boundary (zero-row spool → empty not 500) — test-plan.md AC-7 row | 0 | yes | pull_request | same job as above | pass/fail |
| Frontend unit tests (vitest: selector 6-option render, force-requery watcher, WASM-parity departments) — test-plan.md AC-1/AC-4/AC-6 rows | 0 | yes | pull_request | `.github/workflows/frontend-tests.yml` job `frontend-unit-tests` → `npm test` (vitest auto-discovers `frontend/tests/**/*.test.js`, no per-file wiring needed) | pass/fail |
| CSS governance | 0 | yes | pull_request | `frontend-tests.yml` → `npm run css:check` | pass/fail |
| Frontend type-check | 0 | yes | pull_request | `frontend-tests.yml` → `npm run type-check` (currently `continue-on-error: true`, pre-existing repo-wide policy, not specific to this change) | pass/fail |
| Contract validation (API + data-shape §3.16.4/§3.16.5 + business-rules YA-02) | 1 | yes | pull_request/push main | `contract-driven-gates.yml` job `contract-and-fast-tests` → `cdd-kit validate` / `cdd-kit validate --contracts` | pass/fail |
| OpenAPI sync (both mirrors) | 1 | yes | paths: contracts/api/api-contract.md, contracts/openapi.json, contracts/api/openapi.json | `openapi-sync.yml` → `cdd-kit openapi export --check` (both `--out contracts/openapi.json` and `--out contracts/api/openapi.json`) | pass/fail |
| Integration (route-level workcenter_groups source swap, cross-filter narrowing both directions) — test-plan.md AC-5/AC-6/AC-8 rows | 1 | yes | pull_request | `backend-tests.yml` job `unit-and-integration-tests` (same pytest invocation; these are `tests/test_yield_alert_routes.py` / `test_yield_alert_sql_runtime.py` cases, not a separate job) | pass/fail |
| Contract sample capture (yield-alert response samples) | 1 | yes | pull_request | `backend-tests.yml` same job → `tests/contract/test_capture_samples.py` runs inside the full `pytest tests/` invocation | pass/fail |
| E2E: Playwright `yield-alert-center.spec.ts` (6-option selector, per-option query round trip) — test-plan.md AC-1/AC-4 rows | — | **not currently wired** | — | pre-existing gap: `frontend-tests.yml` only explicitly runs 4 named Playwright specs (downtime-analysis, resource-history-async, db-scheduling, mid-section-defect); `yield-alert-center.spec.ts` is not invoked by any workflow today | none (informational risk — see Notes) |
| E2E: py `tests/e2e/test_yield_alert_e2e.py` (new process_type values, zero-row case) — test-plan.md AC-4/AC-7 rows | 5 | no | workflow_dispatch only | `e2e-tests.yml` (manual dispatch against a running server; not part of PR-required checks, unchanged by this repo's existing policy for all `tests/e2e/`) | report |

## New Workflow Changes
None. This change rides the existing gate set. No new workflow YAML file, no new job, no new required-status-check name. Rationale: Tier 2, no new endpoint (contracts already expand existing `contracts/api/api-contract.md` in place), no new env var/flag, no new concurrency/queue wiring (confirmed: `yield_alert_routes.py` async branch at `is_async_available()` is pre-existing, untouched by this change). All new/updated test files listed in test-plan.md live under paths already covered by existing `paths:` triggers in `backend-tests.yml` (`src/mes_dashboard/{routes,services}/**`, `tests/**`) and `frontend-tests.yml` (`frontend/src/**`, `frontend/tests/**`), and vitest's `include` glob auto-discovers new/updated `*.test.js` files with no per-file CI edit required.

One pre-existing gap surfaced during this review (not introduced by this change, not fixed here — out of ci-cd-gatekeeper's scope-restriction to avoid scope creep on a Tier-2 change): `frontend/tests/playwright/yield-alert-center.spec.ts` is not invoked by any workflow. Test-plan.md AC-1/AC-4 E2E rows extend this spec's existing cases; those extended assertions will pass locally (`npx playwright test tests/playwright/yield-alert-center.spec.ts`) but will not run in CI until a maintainer adds an explicit step to `frontend-tests.yml` (same pattern as the `mid-section-defect.spec.ts` step). Flagging as informational risk per Merge Eligibility below; recommend a follow-up change to close this gap repo-wide rather than folding an unrelated CI-wiring fix into this change's diff.

## Required Check Policy
PR-required status checks (branch protection) unchanged by this change:
1. `unit-and-integration-tests` (backend-tests.yml)
2. `frontend-unit-tests` (frontend-tests.yml)
3. `contract-and-fast-tests` (contract-driven-gates.yml)
4. `openapi-sync` (openapi-sync.yml) — triggers only on contract/openapi path changes, which this change makes
5. `cdd-kit gate <change-id>` — local/pre-commit gate per this repo's CDD workflow

`real-infra-smoke` (backend-tests.yml) and `e2e-critical`/`scheduled-stress-soak` placeholders (contract-driven-gates.yml) remain informational/non-blocking for this change — no stress/soak/queue surface touched (change-classification.md: stress=no, soak=no).

## Informational Gate Promotion Policy
No informational gate is promoted or demoted by this change. `yield-alert-center.spec.ts` is not currently an informational CI gate either (it is simply absent from all workflows) — it cannot be "promoted" until it is first added as an informational (`continue-on-error: true`) step per this repo's standard 10-green-run promotion path (see `db-scheduling.spec.ts` precedent in frontend-tests.yml).

## Rollback Policy
No `_SCHEMA_VERSION` bump required. Confirmed against `src/mes_dashboard/services/yield_alert_dataset_cache.py`: `_CACHE_SCHEMA_VERSION = 5` (module constant) stays unchanged. `process_type` is an existing bind parameter (`_PRIMARY_DETAIL_SQL` `WHERE ... LIKE :process_type`, line ~127) and an existing stamped spool column (data-shape-contract.md §3.16.1 row 9, added by prior change `yield-alert-spool-refactor`) — this change only widens the accepted *value* domain (`GA%`/`GC%` → 6 values), it does not add, remove, or rename any spool column. `DEPARTMENT_NAME` (the column the workcenter_groups re-point reads) is also a pre-existing `_DETAIL_COLUMNS` entry, already written to every spool file today — the re-point is a read-side query change only, not a write-side schema change.

Because each `process_type` value already produces a distinct query_id / spool key (test-plan.md AC-3), rollback is a plain code revert:
1. Revert the commit(s) touching `yield_alert_routes.py` (request validation), `yield_alert_dataset_cache.py` (LIKE patterns), `yield_alert_sql_runtime.py` (workcenter_groups source), and `frontend/src/yield-alert-center/` (selector + `useYieldAlertDuckDB.ts`).
2. No `rm -f tmp/query_spool/yield_alert_dataset/*.parquet` needed — old GA%/GC% spool files remain valid and readable by the reverted code (no column change); new-process-type spool files simply become unreachable (no route accepts those `process_type` values post-revert) and age out by existing Redis TTL / spool GC, same as any abandoned cache key.
3. Revert `contracts/api/api-contract.md`, `contracts/data/data-shape-contract.md` §3.16.4/§3.16.5, `contracts/business/business-rules.md` YA-02, and regenerate both `contracts/openapi.json` and `contracts/api/openapi.json` in the same revert commit (openapi-sync gate enforces this).
4. Redeploy previous image. No database migration to undo, no manual parquet cleanup step in the rollback runbook.

## Artifact Retention
No new CI artifacts introduced. Existing `hypothesis-examples` / `*-logs` artifact upload steps in `backend-tests.yml` are untouched by this change; their retention-days settings are out of this change's scope.

## Merge Eligibility Decision
mergeable — all Tier-0/Tier-1 gates required for this change's test surface (pytest unit/integration/contract-sample, vitest, css:check, cdd-kit validate, openapi-sync) are already required-status checks and need no new workflow file or job.

informational-risk noted: `yield-alert-center.spec.ts` Playwright E2E coverage (test-plan.md AC-1/AC-4 E2E rows) is not executed by any CI workflow today (pre-existing gap, confirmed by grep across `.github/workflows/`). This does not block this change's merge eligibility — the same gap existed before this change and is not widened by it — but reviewers should not treat a green PR as proof the extended Playwright assertions actually ran in CI; verify locally (`cd frontend && npx playwright test tests/playwright/yield-alert-center.spec.ts`) before approval.

## Notes
- Test families/rows: test-plan.md §Acceptance Criteria → Test Mapping, §Test Families Required.
- Contract sample churn: per CLAUDE.md "Promoted Learnings" (full pytest run regenerates `tests/contract/samples/*`) — `git checkout tests/contract/samples/` then re-stage only yield-alert samples before commit; mechanism already documented there, not restated here.
- No CSS contract change, no env-contract change, no new Makefile target — confirmed via change-classification.md §Required Contracts (CSS: no, Env: none).
