---
change-id: hold-history-detail-flat-table
schema-version: 0.1.0
last-changed: 2026-05-14
risk: low
tier: 1
---

# CI/CD Gate Plan: hold-history-detail-flat-table

## Pre-Merge Required Gates

| gate | command | expected result |
|---|---|---|
| CSS governance | `cd frontend && npm run css:check` | exits 0, no violations |
| Vitest unit tests | `cd frontend && npm run test` | exits 0, all tests pass |
| Playwright E2E — hold-history | `cd frontend && npx playwright test tests/playwright/hold-history-flat-table.spec.js` | exits 0, all assertions pass |
| Playwright E2E — hold-overview | `cd frontend && npx playwright test tests/playwright/hold-overview.spec.js` | exits 0, all assertions pass |

All four gates must pass before merge. No external services required.

## Informational Gates

| gate | command | notes |
|---|---|---|
| TypeScript type-check | `cd frontend && npm run type-check` | informational; continues on error |

## Gates Not Required

| gate | reason skipped |
|---|---|
| `pytest` (backend suite) | no backend changes |
| `ruff check .` / `mypy` | no Python changes |
| `cdd-kit validate` | no contract changes |
| Visual regression | scoped CSS and class additions; no layout rework |
| Performance / stress / soak | pure frontend UI fix, no logic change |
| Nightly integration | no Oracle, Redis, or DuckDB involvement |

## CI/CD Workflow

No CI workflow file changes are required. The existing `frontend-unit-tests` and
`e2e-critical` jobs in `.github/workflows/frontend-tests.yml` and
`.github/workflows/contract-driven-gates.yml` already cover all pre-merge gates.

**Trigger**: all pre-merge gates are triggered automatically on pull request creation
and every subsequent push to the PR branch. No manual trigger required.

The new Playwright spec `hold-history-flat-table.spec.js` is picked up automatically by
the `playwright-critical-journeys` gate pattern. The updated `hold-overview.spec.js`
is already listed in that gate's command. No new workflow steps, environment variables,
or deployment stages are introduced.

## Promotion Policy

This is a frontend-only change: scoped CSS padding fix, a class addition, a CSS rule
addition, and two Playwright test files. No DB migration, no spool schema change, no env
var change, no new API endpoint.

Promote to `main` when all four pre-merge gates exit 0. Standard merge — no staging
deploy, no feature flag, no coordinated deploy window required. Frontend build runs as
part of the normal CI pipeline post-merge.

## Rollback Policy

Revert the five changed/new files:

1. `frontend/src/hold-history/components/DetailTable.vue` — revert CSS padding fix
2. `frontend/src/hold-overview/App.vue` — revert class addition
3. `frontend/src/hold-overview/style.css` — revert CSS rule addition
4. `frontend/tests/playwright/hold-history-flat-table.spec.js` — delete new spec
5. `frontend/tests/playwright/hold-overview.spec.js` — revert assertion update

No DB rollback, no spool parquet cleanup, no Redis key invalidation, no env change
required. A single `git revert` commit is sufficient.
