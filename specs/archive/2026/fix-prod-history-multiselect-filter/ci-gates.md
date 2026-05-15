---
change-id: fix-prod-history-multiselect-filter
schema-version: 0.1.0
tier: 2
---

# CI Gates — fix-prod-history-multiselect-filter

## Required (pre-merge / block PR)
- `cd frontend && npm run type-check` — TypeScript compile guard for `useFirstTierFilters.ts` and `MultiSelect.vue` edits.
- `cd frontend && npm run css:check` — CSS governance regression guard (no CSS edits expected).
- `cd frontend && npm run test` — Vitest + node:test unit (new `MultiSelect.test.ts` and extended `production-history.test.js`).
- `cd frontend && npx playwright test production-history-cross-filter.spec.ts` — extended E2E covering the multiselect commit-on-close flow.
- `cdd-kit validate` — contract validator regression guard.
- `cdd-kit gate fix-prod-history-multiselect-filter` — change-level gate.

## Informational (run but advisory)
- `ruff check .` — Python unaffected by this change; project-wide hygiene check.
- `mypy src/` — same rationale.

## Nightly / Weekly / Manual
- None. Tier-2 frontend-only fix; no nightly soak/stress requirement.

## CI/CD Workflow

### Trigger
- Pull-request open / synchronize against `main` triggers the PR workflow (frontend + CDD jobs).
- Push to `main` (post-merge) triggers the smoke-and-publish workflow.
- Manual `workflow_dispatch` available for re-running gates on demand.

### Job graph
On every pull request, GitHub Actions runs the six Required gates above in the frontend job (Node 22, `actions/setup-node@v4`) plus `cdd-kit validate` and `cdd-kit gate <id>` in the CDD job. The informational `ruff` / `mypy` jobs run in parallel but do not block merge. On push to `main`, the same Required gates re-run as a post-merge smoke before the static bundle is published to `src/mes_dashboard/static/dist/`.

## Promotion Policy
A green PR with all six Required gates passing and at least one human approver may be squash-merged to `main`. The post-merge workflow then rebuilds the frontend (`cd frontend && npm run build`) and the artifact is served by gunicorn at the next reload. No staging environment is gated for this tier-2 UI fix; main is production.

## Rollback Policy
Revert path is `git revert` of the merge commit followed by `cd frontend && npm run build` and a gunicorn reload. No post-deploy cleanup required — no DB schema, no parquet spool, no cache namespace, and no data migration are touched. Affected files are limited to `frontend/src/shared-ui/components/MultiSelect.vue`, `frontend/src/production-history/composables/useFirstTierFilters.ts`, `frontend/src/production-history/App.vue`, and the paired tests.

## Evidence Sources
- GitHub Actions run for the PR (frontend + CDD jobs).
- Playwright HTML report artifact uploaded by the E2E job.
- `cdd-kit gate fix-prod-history-multiselect-filter` stdout in the CDD job log.
