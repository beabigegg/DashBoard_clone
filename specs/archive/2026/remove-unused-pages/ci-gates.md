# CI/CD Gate Review

change-id: remove-unused-pages

## Required Gates for This Change

| gate | tier | required | trigger | command/workflow | artifact |
|---|---:|---:|---|---|---|
| contract-validate | 0 | yes | local pre-PR | `cdd-kit validate` | — |
| unit-mock-integration | 1 | yes | PR | `pytest -m "not (e2e or integration_real or stress or load or soak or multi_worker)" --ignore=tests/integration --ignore=tests/stress --ignore=tests/e2e --ignore=tests/manual -x` | junit XML |
| frontend-unit | 1 | yes | PR | `cd frontend && npm run test` | vitest report |
| css-governance | 1 | yes | PR | `cd frontend && npm run css:check` | governance report |
| frontend-type-check | 1 | informational | PR | `cd frontend && npm run type-check` | — |
| build-verification | 1 | informational | PR | `cd frontend && npm run build` — inspect `dist/` for production-history present; tables/admin-performance/admin-user-usage-kpi absent (test-plan AC-3) | dist listing in agent log |

No Tier 3/4/5 gates apply to this change (test-plan "Out of Scope"; change-classification Tasks Not Applicable 6.4).

## CI/CD Workflow

No workflow file changes required. All gates above are already defined in `contracts/ci/ci-gate-contract.md` (schema-version 1.3.14) and exercised by the existing workflows:

- `.github/workflows/contract-driven-gates.yml` — runs `contract-validate`, `unit-mock-integration`
- `.github/workflows/frontend-tests.yml` — runs `frontend-unit`, `css-governance`, `frontend-type-check`
- `.github/workflows/backend-tests.yml` — runs `unit-mock-integration`

The `build-verification` gate is a manual inspection step; no workflow job change needed.

**Contract version bumps in this PR** (contract-reviewer mandate):
- `contracts/api/api-inventory.md`: 1.1.5 → 1.1.6 (remove tables endpoints)
- `contracts/css/css-inventory.md`: 1.2.0 → 1.2.1 (remove three removed-app style entries)
- `contracts/ci/ci-gate-contract.md`: 1.3.14 → 1.3.15 (patch; no gate tier or command change — this note documents removal of three frontend apps from build scope)

## Promotion Policy

Standard merge-to-main: all Tier 1 required gates must be green. The `frontend-type-check` and `build-verification` informational gates do not block merge but must be reviewed for unexpected failures before approving.

## Rollback Policy

No parquet or spool files are involved (query-tool and production-history have no on-disk spool for this change's scope). No deploy-day cleanup steps are required.

Rollback procedure: `git revert <merge-sha>` and re-deploy. The three removed app directories are recoverable from git history. Flask deprecated redirects for `/admin/performance` and `/admin/user-usage-kpi` are retained (non-goal), so bookmark breakage on rollback is nil.

## Merge Eligibility

mergeable — after all Tier 1 required gates pass: `pytest`, `npm run test`, `npm run css:check`, `cdd-kit validate`.
