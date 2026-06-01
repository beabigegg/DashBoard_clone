# CI/CD Gate Review

change-id: downtime-analysis-page
schema-version: 0.1.0
last-changed: 2026-05-29

## Required Gates for This Change

| gate | tier | required | trigger | command/workflow | artifact |
|---|---:|:---:|---|---|---|
| lint | 0 | yes | local / PR | `ruff check .` | — |
| contract-validate | 0 | yes | local / PR | `cdd-kit validate` | — |
| unit-mock-integration | 1 | yes | PR | `pytest tests/test_downtime_analysis_service.py tests/test_downtime_analysis_routes.py tests/test_api_contract.py tests/test_modernization_policy_hardening.py -x` (subset of full `unit-mock-integration` gate) | junit XML |
| frontend-unit | 1 | yes | PR | `cd frontend && npm run test` — picks up `frontend/src/downtime-analysis/__tests__/*.test.ts` via existing `src/**/*.test.ts` glob | vitest report |
| css-governance | 1 | yes | PR | `cd frontend && npm run css:check` — validates `.theme-downtime-analysis` scoping (Rule 6) | governance report |
| frontend-type-check | 2 | informational | PR | `cd frontend && npm run type-check` — `tsconfig.json` include gains `"src/downtime-analysis/**/*"` | — |
| playwright-downtime-analysis | 1 | yes | PR | `cd frontend && npx playwright test tests/playwright/downtime-analysis.spec.js` | playwright trace |
| playwright-resilience | 1 | yes | PR | `cd frontend && npx playwright test tests/playwright/resilience/` (existing gate; downtime resilience specs added to this directory) | playwright trace |
| playwright-data-boundary | 1 | yes | PR | `cd frontend && npx playwright test tests/playwright/data-boundary/` (existing gate; midnight-UTC DATE and CHAR trailing-space boundary specs added to this directory) | playwright trace |
| e2e-backend | 1 | yes | PR | `pytest tests/e2e/test_downtime_analysis_e2e.py -m local_e2e -x` | junit XML |

Informational gate (no merge block):

| gate | tier | required | trigger | command/workflow | artifact |
|---|---:|:---:|---|---|---|
| contract-validate | 2 | informational | PR | `cdd-kit validate` (CI run; local run is Tier 0 required) | — |

Gates NOT added (task 6.4 = skipped per change-classification.md):

- No new nightly (Tier 3) gate — `tests/e2e/test_downtime_analysis_e2e.py` runs under `local_e2e` marker (pre-merge); the real-Oracle integration path (`integration_real`) is deferred to the existing `nightly-integration` gate once the backend lands.
- No new weekly/soak (Tier 4) gate — stress/soak excluded per change-classification.md §Tasks Not Applicable.
- No new manual dispatch (Tier 5) gate.

## CI/CD Workflow

No new workflow files are created. All new tests plug into existing jobs:

### backend-tests.yml — `unit-and-integration-tests` job

Path triggers already cover new files via the existing globs:

```
src/mes_dashboard/services/**      # downtime_analysis_service.py
src/mes_dashboard/routes/**        # downtime_analysis_routes.py
src/mes_dashboard/sql/**           # downtime-analysis/*.sql
tests/**                           # tests/test_downtime_analysis_*.py
                                   # tests/test_api_contract.py (extended)
                                   # tests/test_modernization_policy_hardening.py (extended)
```

The `pytest` invocation already excludes `tests/e2e`, `tests/stress`, and `tests/integration` (real-infra), so the new `tests/e2e/test_downtime_analysis_e2e.py` file runs only when explicitly called (see `e2e-backend` gate above, which sets `-m local_e2e`). No change to the `backend-tests.yml` file is required.

### frontend-tests.yml — `frontend-unit-tests` job

Path triggers already cover:

```
frontend/src/**     # frontend/src/downtime-analysis/**
frontend/tests/**   # frontend/tests/playwright/downtime-analysis.spec.js
```

The `npm run test` (Vitest) step picks up `frontend/src/downtime-analysis/__tests__/*.test.ts` via the existing `src/**/*.test.ts` glob in `vitest.config.js` — no config change needed.

The `npm run css:check` step validates all `style.css` files including `frontend/src/downtime-analysis/style.css`. Rule 6 will enforce `.theme-downtime-analysis` top-level scoping.

The `npm run type-check` step (`vue-tsc --noEmit`, `continue-on-error: true`) will cover the new app once `"src/downtime-analysis/**/*"` is added to `tsconfig.json` `include` by the frontend-engineer. This is the only `tsconfig.json` change required; it matches the pattern used for all other migrated feature apps. No other workflow change is required.

A new Playwright spec `frontend/tests/playwright/downtime-analysis.spec.js` is added. It is invoked as a standalone step (`npx playwright test tests/playwright/downtime-analysis.spec.js`) to produce a named check (`playwright-downtime-analysis`) that branch protection can bind to. The `frontend-tests.yml` job must add this step alongside the existing `playwright-critical-journeys` step. See the workflow change below.

### Required workflow edit — frontend-tests.yml

Add the following step to the `frontend-unit-tests` job, after the existing CSS governance check step:

```yaml
      - name: Run Playwright downtime-analysis spec
        working-directory: frontend
        run: npx playwright test tests/playwright/downtime-analysis.spec.js
```

This produces the check name `Run Playwright downtime-analysis spec` (job: `frontend-unit-tests`). Branch protection binds to this name for the `playwright-downtime-analysis` required gate.

No other workflow file changes are required.

## Promotion Policy

Standard Tier 1 promotion applies:

- All required gates (lint, unit-mock-integration, frontend-unit, css-governance, playwright-downtime-analysis, playwright-resilience, playwright-data-boundary, e2e-backend) must be green on the PR before merge.
- The `frontend-type-check` gate is informational at merge time; promotion to required follows the standard Informational Gate Promotion Policy (20 calendar days / 60 runs, pass rate above threshold, runtime within limit, owner assigned) defined in `contracts/ci/ci-gate-contract.md §Informational Gate Promotion Policy`.
- No new deployment steps beyond the standard deploy checklist. Before serving traffic, verify:
  1. `docs/migration/full-modernization-architecture-blueprint/asset_readiness_manifest.json` contains `/downtime-analysis` entry pointing to the built dist asset. Missing entry crashes gunicorn via `_validate_in_scope_asset_readiness()`.
  2. `docs/migration/full-modernization-architecture-blueprint/route_scope_matrix.json` classifies `/downtime-analysis` as in-scope.
  3. `data/page_status.json` contains the `/downtime-analysis` page object with `drawer_id='drawer-2'`.
  4. `src/mes_dashboard/config/constants.py` contains `DOWNTIME_BRIDGE_VERSION` with its initial value (set at implementation time).

## Rollback Policy

### Normal code rollback (revert the feature PR)

1. Remove `/downtime-analysis` entry from `docs/migration/full-modernization-architecture-blueprint/asset_readiness_manifest.json` BEFORE gunicorn restart — a stale entry with no dist asset crashes gunicorn.
2. Remove `/downtime-analysis` entry from `docs/migration/full-modernization-architecture-blueprint/route_scope_matrix.json`.
3. Remove the `/downtime-analysis` page object from `data/page_status.json`.
4. Run `rm -rf tmp/query_spool/downtime_analysis/` — clears the downtime spool directory. This has no effect on `resource_dataset_*`, `production_history_*`, or any other service spool; namespaces are independent.
5. No Redis key cleanup required for the rollback itself — the spool version key (`DOWNTIME_BRIDGE_VERSION`) lives in Python constants, not Redis; stale Redis cache entries for the removed routes expire naturally.

### IT JOBID backfill runbook (post-deploy, no code rollback)

When IT backfills `SHIFT.JOBID` values after deploy (expected: ~50% of UDT events gain a direct JOBID match):

1. Bump `DOWNTIME_BRIDGE_VERSION` in `src/mes_dashboard/config/constants.py` (e.g., `"1.0.0"` → `"1.1.0"`). This changes the spool cache key so the next request triggers a spool rebuild from Oracle with the new JOBID data.
2. Deploy the constants-only change.
3. Optionally run `rm tmp/query_spool/downtime_analysis/*.parquet` to force immediate rebuild rather than waiting for the first cache miss. This is optional because the version-key mismatch handles invalidation automatically; the manual purge only shortens the staleness window.
4. No changes to `resource_dataset_*` or any other spool directory are needed — the `downtime_analysis_*` namespace is fully isolated.

### Parquet schema gate

Any PR that renames, adds, or removes a column in `downtime_analysis_service.py` spool write path MUST add `rm -f tmp/query_spool/downtime_analysis/*.parquet` to both deploy and rollback runbooks and update `contracts/data/data-shape-contract.md §3.12`.

## Merge Eligibility

blocked until all Tier 1 required gates are green:
- `unit-mock-integration` (pytest: test_downtime_analysis_service, test_downtime_analysis_routes, test_api_contract, test_modernization_policy_hardening)
- `frontend-unit` (vitest: formatDowntimeDate.test.ts, useBigCategory.test.ts, useFilterState.test.ts)
- `css-governance` (css:check Rule 6 on .theme-downtime-analysis)
- `playwright-downtime-analysis`
- `playwright-resilience` (including new downtime resilience specs)
- `playwright-data-boundary` (including midnight-UTC and CHAR trailing-space boundary specs)
- `e2e-backend` (test_downtime_analysis_e2e.py, local_e2e marker)

informational-risk: `frontend-type-check` may show type errors in `downtime-analysis/` until the frontend-engineer resolves `// TODO: type echarts callback` annotations; this does not block merge.

