# CI/CD Gate Plan

## Change ID
migrate-yield-alert-center-ts

## Tier
1 — low-risk TypeScript migration; no behavior change, no backend change, no new packages.

## Summary
Pure TypeScript migration: 3 file renames (`.js → .ts`) and `lang="ts"` on 5 Vue SFCs.
No backend changes, no new packages, no schema changes, no parquet files.

---

## Required Gates (must be green before merge)

| Gate | Workflow | Job | Command | Pass Criterion |
|---|---|---|---|---|
| Vitest unit suite | `frontend-tests.yml` | `frontend-unit-tests` | `npm test` | 0 failures (331 tests across 30 files) |
| Legacy node --test suite | `frontend-tests.yml` | `frontend-unit-tests` | `npm run test:legacy` | 0 failures |
| Test discovery sanity | `frontend-tests.yml` | `frontend-unit-tests` | `find tests` count check | Vitest count > 0 AND legacy count > 0 |

Node version requirement: **Node 22** (`actions/setup-node@v4 / node-version: "22"`) — enforced in `frontend-tests.yml`.

---

## Informational Gates (non-blocking)

| Gate | Workflow | Job | Trigger | Notes |
|---|---|---|---|---|
| Type-check (`vue-tsc --noEmit`) | `frontend-tests.yml` | `frontend-unit-tests` | pull_request | `continue-on-error: true` in workflow — visible but non-blocking. Passes locally (0 errors). |
| Contract validation (`cdd-kit validate`) | `contract-driven-gates.yml` | `contract-and-fast-tests` | pull_request | Non-required status check. |
| Backend unit/integration | `backend-tests.yml` | `unit-and-integration-tests` | **Not triggered** — no `src/mes_dashboard/` paths touched | N/A for this PR. |
| E2E tests | `e2e-tests.yml` | `e2e-tests` | `workflow_dispatch` only | Not triggered by PR. |
| Nightly integration-real | `backend-tests.yml` | `nightly-integration-real` | `schedule` only | Not triggered by PR. |

**Type-check scope note:** `frontend/tsconfig.json` does not yet include `src/yield-alert-center/**/*` in its `include` array. The migrated files compile correctly when included in the Vite build graph, but `vue-tsc` does not independently verify them. This is pre-existing scope policy (yield-alert-center is not yet in the type-check include list); it does not block this migration since `npm run type-check` passes with zero errors on the currently scoped modules.

---

---

## Promotion Policy

Merge to `main` when `frontend-tests.yml / frontend-unit-tests` is fully green (Vitest suite + legacy suite + discovery check). No staging deployment required for a pure TypeScript rename — file renames do not affect runtime artifact paths (Vite resolves `.ts` transparently). All other CI jobs are informational or not triggered by this PR.

## Rollback Policy

`git revert <merge-sha>` is sufficient — single-step revert. No follow-up cleanup required (no schema changes, no parquet/spool files, no Redis key format changes, no new npm packages). Verify with `npm test` after revert to confirm the restored `.js` files are loadable.

## Merge Eligibility Decision

**Merge when:** `frontend-tests.yml / frontend-unit-tests` is fully green (Vitest suite + legacy suite + discovery check). All other jobs are informational or not triggered by this PR.
