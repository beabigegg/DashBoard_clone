---
change-id: migrate-query-tool-ts
archived: 2026-05-14
schema-version: 0.1.0
---

# Archive: migrate-query-tool-ts

## Change Summary

Migrated `frontend/src/query-tool/` from JavaScript to TypeScript as part of Phase 3 of the project-wide TS migration. Nine `.js` source files (6 composables, 2 utils, `main.js`) were renamed to `.ts` with full TypeScript type annotations. All 14 Vue SFCs (App.vue + 13 components) were audited and converted to `<script setup lang="ts">`. No business logic was changed; the migration is a pure rename with type annotations.

## Final Behavior

`frontend/src/query-tool/` now contains zero `.js` source files. The query-tool feature app is fully typed: `npm run type-check` exits 0 with no errors. All existing tests remain green and no runtime behavior changed.

## Final Contracts Updated

None — pure rename migration, no API, CSS, env, data shape, or business logic contract changes.

## Final Tests Added / Updated

No new tests added. Existing test suites confirmed green:
- Vitest unit tests: 331/331 pass (`npm run test`)
- Legacy node:test: 251/251 pass (`npm run test:legacy`)
- Python safety audit: all pass (`pytest tests/test_job_query_frontend_safety.py`)
- Static audit: `find frontend/src/query-tool -name "*.js"` → empty

Python safety tests had zero hardcoded `.js` paths referencing query-tool source files — no Python test updates were needed.

## Final CI/CD Gates

| gate | result |
|---|---|
| TypeScript type-check | 0 errors |
| Vitest unit tests | 331/331 |
| Legacy node:test | 251/251 |
| No stray JS files | empty |
| Python safety audit | pass |
| `cdd-kit gate` | pass |

## Production Reality Findings

- `ts-resolver-loader.mjs` in the legacy `node:test` runner transparently resolves `.js` import specifiers to `.ts` files — legacy test files required no import specifier updates.
- `vi.mock('...file.js')` static mock calls in Vitest continue to resolve correctly after rename — no updates needed (Vite handles transparently). Consistent with CLAUDE.md migration rules.
- Dynamic `import('...file.js')` in `LotJobsTable.vue` had the `.js` extension dropped — the only case where specifier update was required.
- `ci-gates.md` failed `cdd-kit gate` on the first run because the validator checks for the literal presence of "workflow", "promotion policy", and "rollback policy" in the file. Fixed by adding `## CI/CD Workflow`, `## Promotion Policy`, and `## Rollback Policy` sections. **This is a new, evidence-backed finding not yet documented in project guidance.**
- No `@ts-expect-error` / double-cast patterns were needed for cross-app imports — all composable and util imports are intra-app.
- `shared-ui/components/TimelineChart.vue` had a stale `@ts-expect-error` suppression that was removed as a side-effect of the migration (the suppressed error no longer exists after the query-tool rename).

## Lessons Promoted to Standards

1. **`ci-gates.md` literal section header requirement** → promoted to `CLAUDE.md` § CDD Kit Commands.
   `cdd-kit gate` checks for the literal strings "workflow", "promotion policy", and "rollback policy". Any ci-gates.md that omits dedicated `## CI/CD Workflow`, `## Promotion Policy`, and `## Rollback Policy` sections will fail gate validation regardless of content completeness.
   Evidence: `specs/changes/migrate-query-tool-ts/ci-gates.md` — gate failed on first run; passed after adding these three sections.

## Follow-up Work

- Remaining JS apps not yet migrated (Phase 3): `admin-dashboard`, `admin-performance`, `admin-user-usage-kpi`, `anomaly-overview`, `material-trace`, `mid-section-defect`, `portal`, `portal-shell`, `tables`.
- Playwright E2E informational gates (`query-tool.spec.js`, `query-tool-url-state.spec.js`) run nightly — not blocking.
- Manual browser smoke (lot trace + equipment query) should be verified post-deploy.

## Cold Data Warning

This archive is historical evidence. Current requirements live in `contracts/` and active project guidance (`CLAUDE.md`/`CODEX.md`).
