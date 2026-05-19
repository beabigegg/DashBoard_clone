# CI/CD Gate Plan

## Change ID
admin-dashboard-ux

## Required Gates for This Change

| gate | tier | required | trigger | command/workflow | artifact |
|---|---:|:---:|---|---|---|
| vitest (unit + integration) | 1 | yes | pull_request | `cd frontend && npm test` | test run log |
| css-governance | 1 | yes | pull_request | `cd frontend && npm run css:check` | check output |
| type-check | 2 | informational | pull_request | `cd frontend && npm run type-check` | tsc output |

Gates not applicable to this change (Tier 3 UI-only, no backend, no E2E, no nightly/weekly/manual): contract, E2E, data-boundary, resilience, fuzz/monkey, nightly real-infra, soak, stress.

Test rows covered by the vitest gate: see test-plan.md AC-1 through AC-8 and all test files listed in the Test File Inventory.

## CI/CD Workflow

No new workflow files are required. All three gates are already executed by the existing `.github/workflows/frontend-tests.yml` workflow:

- **`Run vitest suite`** (`npm test`) — Tier 1 required; blocks merge on failure.
- **`CSS governance check`** (`npm run css:check`) — Tier 1 required; blocks merge on failure.
- **`Type check (vue-tsc --noEmit)`** (`npm run type-check`) — Tier 2 informational; `continue-on-error: true` is already set in the workflow; does not block merge.

The workflow triggers on `pull_request` and `push` to `main` with path filters covering `frontend/src/**`, which includes all files modified by this change (`frontend/src/admin-dashboard/` and `frontend/src/admin-shared/`).

No modifications to `.github/workflows/frontend-tests.yml` or any other workflow file are needed for this change.

### Concurrency
The existing workflow does not define a `concurrency` group. Because `frontend-tests.yml` runs on PR events, adding a concurrency block is advisable but out of scope for this change (no workflow modification is required by this gate plan).

### Caching
`actions/setup-node@v4` without `cache: npm` is used in the existing workflow. Node modules are re-installed via `npm ci` on each run. Adding npm caching is advisable but out of scope for this change.

## Required Status Check Policy

The following job name (as it appears in the workflow `name` field and step names) must be bound to branch protection on `main`:

- **`frontend-unit-tests`** — the single job in `frontend-tests.yml`; covers all three gate steps.

Branch protection must require this check to pass before merging any PR that touches `frontend/src/**`.

## Promotion Policy

This change is Tier 3 (frontend-only UX). There is no staging environment promotion step. Merge to `main` is the sole promotion gate.

Merge eligibility requires:
1. `frontend-unit-tests` job passes (vitest + css:check both green).
2. Type-check result reviewed but not blocking (informational only).
3. `visual-review-report.md` artifact present and approved by ui-ux-reviewer (see change-classification.md Optional Artifacts).
4. `cdd-kit gate admin-dashboard-ux --strict` passes locally (all section-6 tasks resolved).

## Rollback Policy

This change modifies only Vue SFC files and admin-shared component/composable TypeScript files within `frontend/src/admin-dashboard/` and `frontend/src/admin-shared/`. There are no backend changes, no database migrations, no spool schema changes, and no new npm packages.

Rollback procedure:
1. Revert the merge commit on `main` via `git revert <merge-sha>`.
2. Re-run `cd frontend && npm run build` to regenerate `src/mes_dashboard/static/dist/`.
3. Deploy the reverted build. No server restart, cache flush, or data cleanup is required.

No parquet cleanup is needed (admin-dashboard has no DuckDB spool).

## Artifact Retention

No new CI artifacts are produced beyond the standard job logs. Default GitHub Actions log retention (90 days) applies. The `visual-review-report.md` artifact is a file committed to the change directory, not a CI upload; it has no expiry.

## Merge Eligibility

**mergeable** — all required gates are served by the existing `frontend-tests.yml` workflow; no new workflow authoring is needed; informational type-check does not block merge.
