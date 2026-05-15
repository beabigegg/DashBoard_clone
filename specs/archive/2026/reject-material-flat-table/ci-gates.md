---
change-id: reject-material-flat-table
schema-version: 0.1.0
last-changed: 2026-05-15
risk: low
tier: 3
---

# CI/CD Gate Plan: reject-material-flat-table

## Pre-Merge Required Gates

| gate | command | expected result |
|---|---|---|
| CSS governance | `cd frontend && npm run css:check` | exits 0, no violations |
| Vitest unit tests | `cd frontend && npm run test` | exits 0, all 331 tests pass |
| Playwright E2E — reject-material | `cd frontend && npx playwright test tests/playwright/reject-material-flat-table.spec.js` | exits 0, all assertions pass |

All three gates must pass before merge. No external services required.

## Informational Gates

| gate | command | notes |
|---|---|---|
| TypeScript type-check | `cd frontend && npm run type-check` | informational; continues on error |

## Gates Not Required

| gate | reason skipped |
|---|---|
| `pytest` (backend suite) | no backend changes |
| `ruff check .` / `mypy` | no Python changes |
| `cdd-kit validate` | no contract changes beyond CSS contract already updated |
| Visual regression | scoped CSS and class additions; no layout rework |
| Performance / stress / soak | pure frontend UI fix, no logic change |
| Nightly integration | no Oracle, Redis, or DuckDB involvement |

## CI/CD Workflow

No CI workflow file changes are required. The existing `frontend-unit-tests` and
`e2e-critical` jobs in `.github/workflows/frontend-tests.yml` and
`.github/workflows/contract-driven-gates.yml` already cover all pre-merge gates.

**Trigger**: all pre-merge gates are triggered automatically on pull request creation
and every subsequent push to the PR branch. No manual trigger required.

The new Playwright spec `reject-material-flat-table.spec.js` is picked up automatically by
the `playwright-critical-journeys` gate pattern. No new workflow steps, environment variables,
or deployment stages are introduced.

## Promotion Policy

This is a frontend-only change: scoped CSS padding fix, a class addition, a CSS rule
addition, and one new Playwright test file. No DB migration, no spool schema change, no env
var change, no new API endpoint.

Promote to `main` when all three pre-merge gates exit 0. Standard merge — no staging
deploy, no feature flag, no coordinated deploy window required. Frontend build runs as
part of the normal CI pipeline post-merge.

## Rollback Policy

Revert the four changed/new files:

1. `frontend/src/reject-history/components/DetailTable.vue` — revert scoped CSS padding override
2. `frontend/src/material-trace/App.vue` — revert class addition on card-body element
3. `frontend/src/material-trace/style.css` — revert padding override rule
4. `frontend/tests/playwright/reject-material-flat-table.spec.js` — delete new spec

No DB rollback, no spool parquet cleanup, no Redis key invalidation, no env change
required. A single `git revert` commit is sufficient.
