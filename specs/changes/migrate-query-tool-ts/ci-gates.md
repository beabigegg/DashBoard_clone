---
change-id: migrate-query-tool-ts
schema-version: 0.1.0
last-changed: 2026-05-14
risk: low
tier: 2
---

# CI/CD Gate Plan: migrate-query-tool-ts

## Pre-Merge Required Gates

| gate | command | expected result |
|---|---|---|
| TypeScript type-check | `cd frontend && npm run type-check` | exits 0, zero errors |
| Vitest unit tests | `cd frontend && npm run test` | exits 0, 331 tests pass |
| Legacy node:test suite | `cd frontend && npm run test:legacy` | exits 0, 251 tests pass |
| No stray JS files | `find frontend/src/query-tool -name "*.js"` | empty output (no files found) |
| Python safety audit | `pytest tests/test_job_query_frontend_safety.py` | exits 0, all tests pass |

All five gates must pass before merge. They are all fast (< 2 min total) and require no
external services.

## Informational Gates (Nightly Only)

| gate | spec file | notes |
|---|---|---|
| Playwright E2E — query tool | `frontend/tests/playwright/query-tool.spec.js` | browser required; run nightly |
| Playwright E2E — URL state | `frontend/tests/playwright/query-tool-url-state.spec.js` | browser required; run nightly |

These are informational only. A failure does not block merge; it triggers investigation.

## Gates Not Required

| gate | reason skipped |
|---|---|
| `pytest` (full backend suite) | no backend changes |
| `npm run css:check` | no style changes |
| `cdd-kit validate` | no contract changes |
| Visual regression | no UI changes |
| Performance / stress / soak | pure rename, no logic change |

## CI/CD Workflow

No CI workflow file changes are required. The existing `type-check` and `test` jobs in the CI
pipeline already cover all pre-merge gates for this change. The migration is frontend-source-only;
no new workflow steps, environment variables, or deployment stages are introduced.

## Promotion Policy

Promote to `main` when all five pre-merge gates exit 0. No staging deploy or feature flag needed —
the change is a pure source rename with no runtime behavior difference.

## Rollback Policy

Revert the migration commit. No data migrations, no schema changes, no deploy steps required.
`index.html` `./main.js` entries are unchanged (intentional; Vite resolves `.ts` at build time),
so rollback requires no additional HTML edits.
