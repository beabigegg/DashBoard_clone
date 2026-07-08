# CI/CD Gate Plan

## Change ID
move-target-permissions-panel

## Required Gates
| gate | tier | required | trigger | command/workflow | expected artifact |
|---|---:|---:|---|---|---|
| type-check | 0 | yes | local/pull_request | `cd frontend && npm run type-check` | vue-tsc exit 0 (console pass/fail) |
| css-governance | 0 | yes | local/pull_request | `cd frontend && npm run css:check` | css-contract Rule 4.2/4.3/6 pass (AC-4) |
| unit | 0 | yes | local/pull_request | `cd frontend && npm run test` | vitest report / `test-evidence.yml` — covers test-plan.md rows: `admin-dashboard.test.js` (AC-1), `PermissionsTab.test.ts` (AC-1/2/3), `admin-dashboard-permissions-css-scope.test.js` (AC-4), `TargetPermissionsPanel.test.ts` relocated (AC-7), `portal-shell-wave-a-smoke.test.js` unchanged (AC-6) |
| build | 0/1 | yes | local/pull_request | `cd frontend && npm run build` | `frontend/dist/` — must succeed for both existing Vite entries `admin-dashboard` and `admin-pages` (no `vite.config.ts` `INPUT_MAP` change needed; both entries pre-exist per change-classification.md) |
| contract | 0 | yes (confirmation-only) | local/pull_request | `cdd-kit validate --contracts` | validation report confirming `contracts/api/api-contract.md` and `tests/contract/samples/get_admin_production_achievement_permissions.json` are byte-identical (AC-5) — no new sample expected |
| e2e-critical | 1 | yes | pull_request | Tier-1 Playwright job running `frontend/tests/playwright/admin-dashboard.spec.ts` and `frontend/tests/playwright/admin-pages.spec.ts` | `playwright-report/` — covers test-plan.md e2e rows for AC-1/2/3/4/7; both specs are already-named Tier-1 required targets per `contracts/ci/ci-gate-contract.md`, no new spec file or job registration needed |
| visual (computed-style) | 1 | yes | pull_request | folded into the same `admin-dashboard.spec.ts` Tier-1 run (test-plan.md "visual" row: `getComputedStyle` assertions on `.status-badge`/`.table-container` etc.) | `playwright-report/` — no separate informational job; complements (does not replace) the visual-reviewer screenshot bundle produced under task 5.2 |
| data-boundary | 0 | yes | local/pull_request | `cd frontend && npm run test` (includes `admin-dashboard-permissions-css-scope.test.js`) | vitest report — static assertion that `.theme-admin-dashboard` covers every relocated-panel CSS class (AC-4) |
| integration | n/a | no | — | — | no backend/integration surface touched (change-classification.md: "Impact Radius" is admin UI surface only) |
| resilience | n/a | no | — | — | no resilience surface introduced |
| fuzz/monkey | n/a | no | — | — | no new interaction complexity |
| stress | n/a | no | — | — | no load surface touched |
| soak | n/a | no | — | — | no load/refresh/long-running behavior touched |

## New Workflow Changes
None. This is a pure frontend relocation (no backend/API/env/DB surface, per change-classification.md). Existing CI already:
- builds both `admin-dashboard` and `admin-pages` Vite entries (`npm run build` covers both — no `vite.config.ts` `INPUT_MAP` edit, no new entry),
- runs `npm run test` / `npm run type-check` / `npm run css:check` across the whole `frontend/` tree (new/moved test files under `frontend/src/admin-dashboard/tabs/__tests__/` and `frontend/src/admin-dashboard/components/__tests__/` are picked up automatically by the existing Vitest glob config — no config change needed), and
- already names `admin-dashboard.spec.ts` and `admin-pages.spec.ts` as required Tier-1 Playwright targets per `contracts/ci/ci-gate-contract.md`.

No `.github/workflows/*.yml` or `Makefile` gate-target edits are made for this change. No new required-check name is introduced, so no branch-protection update is needed.

## Required Check Policy
PR merge eligibility requires all of the following green on the PR head commit: `type-check`, `css-governance`, `unit`, `build`, and the Tier-1 Playwright job covering both `admin-dashboard.spec.ts` and `admin-pages.spec.ts`. `contract` (confirmation-only `cdd-kit validate --contracts`) is required but expected to be a no-op pass since no contract file changes are expected for the API surface (only `css-contract.md`/`css-inventory.md` prose updates per change-classification.md, which are not schema-gated).

## Informational Gate Promotion Policy
No informational gates are added, promoted, or demoted by this change. The "visual" test-plan row (computed-style assertions) is folded into the existing required Tier-1 `admin-dashboard.spec.ts` run rather than split into a separate Tier-2 informational job, because it is a small, deterministic, non-flaky assertion set (no new external dependency, no timing-sensitive check) — it does not meet the bar for quarantine-style informational treatment.

## Rollback Policy
Pure UI relocation, no data/schema/deploy rollback needed:
- **Rollback mechanism**: revert the frontend commit(s) for this change (component move + tab wiring + CSS re-scope + test updates). No backend deploy, no DB migration, no Parquet/DuckDB schema, no env var, and no RQ worker is touched, so there is nothing to roll back outside the frontend build artifact.
- **Trigger conditions**: `admin-dashboard.spec.ts`/`admin-pages.spec.ts` Tier-1 failure post-merge, or a user-reported regression in the target-permissions whitelist UI (grant/toggle round-trip) surfaced after deploy.
- **Rollback scope**: revert restores `TargetPermissionsPanel.vue` to its prior location in `admin-pages` (if implementation-planner chose removal) and removes the new `admin-dashboard/tabs/` component; the backend endpoints (`GET`/`PUT /admin/api/production-achievement/permissions[/{user_identifier}]`) are unaffected in either direction, so rollback carries zero API/data risk.
- **No forward-only concern**: because no schema/parquet/env change ships with this change (per change-classification.md Required Contracts: Env/Data shape/Business logic all "none"), a straight `git revert` is sufficient — no rollback runbook `rm`/cache-purge step is required (contrast with parquet-schema changes per `docs/architecture/cache-spool-patterns.md`).

## Artifact Retention
No new artifact type is introduced. Reuse existing CI artifact retention settings for `playwright-report/` and vitest output already configured on the frontend workflow; no `retention-days` change is required.

## Merge Eligibility Decision
mergeable — contingent on: `type-check`, `css-governance`, `unit`, `build`, and Tier-1 `admin-dashboard.spec.ts`/`admin-pages.spec.ts` passing locally (tasks 6.2/6.3 in `tasks.yml` are marked `done` once these pass locally per CLAUDE.md promoted CDD-kit-operations learning). Task 6.4 (nightly/weekly/manual gates) is `skipped` — no nightly/weekly gate is defined for this surface, consistent with `tasks.yml`.

## Notes
- Reference `test-plan.md`'s Acceptance-Criteria→Test-Mapping table and Test Execution Ladder for the exact test files/commands; this document defines gate tiering and merge policy only, not test strategy.
- No `ci-gate-contract.md` edit is required for this change (change-classification.md: "CI/CD: none ... no `ci-gate-contract.md` change") — both `admin-dashboard.spec.ts` and `admin-pages.spec.ts` are pre-existing named Tier-1 targets.
