# CI/CD Gate Plan

## Change ID
query-tool-subtab-cache

## Scope Summary
Pure frontend, client-side caching logic change confined to
`frontend/src/query-tool/composables/{useLotEquipmentQuery,useEquipmentQuery,useLotDetail}.ts`
and their test files (`frontend/tests/query-tool/`,
`frontend/tests/legacy/query-tool-composables.test.js`). No backend, no
API/contract change, no new endpoint, no new env var, no CSS/UI/visual
change, no DB migration, no dependency/lockfile change (per
change-classification.md `Required Contracts` — all `none`, and tasks 2.1-2.6,
4.1, 4.3, 4.4, 5.1-5.3 marked `skipped`/not-applicable). Existing workflows
already cover this surface; **no workflow changes are required**.

## Required Gates
| gate | tier | required | trigger | command/workflow | artifact |
|---|---:|---:|---|---|---|
| frontend unit tests (vitest) | 1 | yes | pull_request / push(main) | `.github/workflows/frontend-tests.yml` job `frontend-unit-tests` → `npm test` | AC-1..AC-7 covered by new/extended specs in `frontend/tests/query-tool/` (see test-plan.md once filled by test-strategist) |
| frontend legacy suite (node --test) | 1 | yes | pull_request / push(main) | `frontend-tests.yml` → `npm run test:legacy` | covers `frontend/tests/legacy/query-tool-composables.test.js` (AC-6 useLotDetail parity if fixed there) |
| CSS governance check | 1 | yes | pull_request / push(main) | `frontend-tests.yml` → `npm run css:check` | not touched by this change (no CSS edits) but runs as part of the same required job; must stay green |
| type-check (vue-tsc) | 2 | no (informational) | pull_request / push(main) | `frontend-tests.yml` step "Type check (vue-tsc --noEmit)" — `continue-on-error: true` | pre-existing informational step in the same job; not newly introduced by this change |
| existing Playwright specs (downtime-analysis, resource-history-async, production-achievement-async, db-scheduling, mid-section-defect) | 1/2 | yes (Tier1 specs) / informational (db-scheduling) | pull_request / push(main) | `frontend-tests.yml` (same job, later steps) | unaffected by this change; must stay green because they run in the same required job |
| contract-driven-gates | 1 | yes | pull_request / push(main,master) / workflow_dispatch / weekly schedule | `.github/workflows/contract-driven-gates.yml` job `contract-and-fast-tests` → `cdd-kit validate` + `cdd-kit validate --contracts` | confirms zero-contract claim holds (change-classification.md `Required Contracts: none` for API/CSS/Env/Data/Business/CI) |
| backend-tests | n/a | no — not triggered | — | `.github/workflows/backend-tests.yml` | path filters are `src/mes_dashboard/**`, `tests/**` (backend), `deploy/**` — none match this change's file set; confirmed not triggered |
| openapi-sync-gate | n/a | no — not triggered | — | `.github/workflows/openapi-sync.yml` | path filters are `contracts/api/**`, `contracts/openapi.json` — not touched |
| released-pages-hardening-gates | n/a | no — not triggered | — | `.github/workflows/released-pages-hardening-gates.yml` | path filters are `src/mes_dashboard/**` and `frontend/src/job-query/**` (a different feature module) plus specific backend test files — none match `frontend/src/query-tool/**` |
| e2e-tests, measure-stability, soak-tests, stress-tests | 3/4/5 | no — not triggered | workflow_dispatch / schedule only | `.github/workflows/{e2e-tests,measure-stability,soak-tests,stress-tests}.yml` | no path trigger at all (manual/scheduled only); irrelevant to this narrow client-side change |

## New Workflow Changes
None. Verified by inspecting path filters on every workflow in
`.github/workflows/`:
- `frontend-tests.yml` already filters on `frontend/src/**` and
  `frontend/tests/**`, which covers every file this change touches
  (`frontend/src/query-tool/composables/**`,
  `frontend/tests/query-tool/**`, `frontend/tests/legacy/query-tool-composables.test.js`).
- `contract-driven-gates.yml` has no path filter (runs on every push/PR) and
  already runs `cdd-kit validate` unconditionally.
- No other workflow's path filters overlap this change's file set (checked
  `backend-tests.yml`, `e2e-tests.yml`, `openapi-sync.yml`,
  `released-pages-hardening-gates.yml`, `measure-stability.yml`,
  `soak-tests.yml`, `stress-tests.yml` — none reference `frontend/src/query-tool/**`
  or `frontend/tests/query-tool/**`).

No new job, step, or path-filter edit is added to any workflow file. This
matches tasks.yml 4.4 ("CI/CD workflows", `skipped` — "no CI/CD workflow
change") and change-classification.md `Required Contracts: CI/CD: none`.

## Required Check Policy
Branch protection must keep the following as required status checks for
merge eligibility (both already required pre-change, unaffected by this
change):
- `frontend-unit-tests` (job in `frontend-tests.yml`) — no explicit `name:`
  key on the job, so GitHub uses the job id `frontend-unit-tests` as the
  check name; this is a stable, bindable check name.
- `contract-and-fast-tests` (job in `contract-driven-gates.yml`).

No new required check is introduced. No existing required check is removed
or relaxed.

## Informational Gate Promotion Policy
- `vue-tsc --noEmit` (type-check step, `continue-on-error: true`) stays
  informational. This change does not touch any `.vue` template or add new
  TypeScript surface beyond the three composables (already typed); no
  promotion trigger applies here.
- `db-scheduling` Playwright spec stays Tier 2 informational per its
  existing promotion rule (10 consecutive green PR runs) — unrelated to
  this change, not accelerated or reset by it.
- No new informational gate is introduced by this change, so no new
  promotion clock starts.

## Rollback Policy
- This is a pure frontend, client-side-only change with no schema, no API,
  no env var, and no deployed-artifact shape change. Rollback is a plain
  `git revert` of the composable changes; no data migration, no cache
  purge, no parquet/schema version bump, no worker/deploy-file rollback
  step is applicable (contrast with cache/spool changes in
  `docs/architecture/cache-spool-patterns.md`, which require explicit `rm`
  steps for parquet schema breaks — none apply here since no server-side
  spool or schema is touched).
- If the merged change causes stale-data regressions (AC-3/AC-4 cache
  invalidation bug), the safe rollback is: revert the composable commit(s)
  and redeploy the frontend bundle. No backend restart or Redis/DuckDB
  state cleanup is required, since caching lives entirely in
  in-memory composable state scoped to the live page session (per
  change-classification.md Clarifications: "no new storage, TTL, or env
  flag is introduced").

## Artifact Retention
No new CI artifact is produced by this change. Existing `frontend-tests.yml`
and `contract-driven-gates.yml` retention settings are unchanged (this
change adds no `actions/upload-artifact` step).

## Merge Eligibility Decision
mergeable — once `frontend-unit-tests` (frontend-tests.yml) and
`contract-and-fast-tests` (contract-driven-gates.yml) are green on the PR.
No Tier 3/4/5 nightly, weekly, or manual-dispatch gate is required before
merge for a change this narrow (see Notes below for the explicit N/A
rationale per tier).

## Nightly / Weekly / Manual Gates — N/A
- Tier 3 (nightly real-infra): N/A. This change has no backend/DB/Redis
  surface — nightly `backend-tests.yml` path filters do not match this
  change's files, and there is no real-infra dependency for client-side
  composable caching to validate overnight.
- Tier 4 (weekly soak/stress): N/A. `soak-tests.yml`/`stress-tests.yml` are
  schedule/dispatch-only and exercise server load paths; this change
  reduces client-triggered query volume (fewer duplicate requests), it
  does not add a new load surface to soak/stress against.
- Tier 5 (manual production-like dispatch): N/A. No deploy-shape, env, or
  infra change exists to dispatch-validate; `e2e-tests.yml` (manual
  dispatch against a running deployed server) remains available if a
  human wants to exercise the query-tool page end-to-end post-deploy, but
  it is not a required gate for this change.

This satisfies tasks.yml 6.4 ("Nightly/weekly/manual gates if required") —
mark `skipped` with reason "no nightly/weekly gates defined for this
change; existing Tier 1 gates (frontend-tests, contract-driven-gates) are
sufficient" once verification tasks are executed.

## Notes
- Reference test-plan.md rows / change-classification.md AC-1..AC-7 for the
  actual test assertions this change must satisfy — this file governs gate
  policy only, it does not restate test strategy.
- change-classification.md already classifies `CI/CD: none` under Required
  Contracts and marks tasks 4.3/4.4 not-applicable; this ci-gates.md
  confirms that conclusion by inspecting the actual workflow path filters
  rather than assuming it.
