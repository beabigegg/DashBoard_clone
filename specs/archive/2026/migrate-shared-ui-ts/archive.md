---
change-id: migrate-shared-ui-ts
archived: 2026-05-12
---

# Archive — migrate-shared-ui-ts (Phase 1c)

## Change Summary

Phase 1c of the incremental TypeScript migration of `frontend/src/`. All 22 Vue SFCs in
`frontend/src/shared-ui/components/` were converted to `<script setup lang="ts">` with
`defineProps<T>()` generic syntax. `frontend/src/shared-ui/index.js` was deleted and replaced
with `index.ts` exporting all 22 components (the original barrel only exported 5). The
`tsconfig.json` `include` array was expanded to cover `src/shared-ui/**/*`, so `vue-tsc --strict`
now type-checks all three migrated scopes: `core`, `shared-composables`, and `shared-ui`.

## Final Behavior

`npm run type-check` now covers 54 modules across all three migrated scopes (21 core + 11
shared-composables + 22 shared-ui). Type check exits 0. `npm run test` passes 270/270. The
`shared-ui` public barrel exports all 22 components by name. No runtime behavior was changed.

## Final Contracts Updated

None. All contract sections were verify-only:
- `contracts/ci/ci-gate-contract.md` — verified; `frontend-type-check` remains informational
- `contracts/css/css-contract.md` — verified; no `@layer` or token edits
- `contracts/css/css-inventory.md` — verified; inventory entries unchanged

## Final Tests Added / Updated

No new test files added. Existing suite (270 tests) verified passing with the migrated SFCs.
The four existing component test files are unchanged:
- `frontend/tests/components/DataTable.test.js`
- `frontend/tests/components/LoadingOverlay.test.js`
- `frontend/tests/components/LoadingSpinner.test.js`
- `frontend/tests/legacy/loading-standardization.test.js`

## Final CI/CD Gates

| gate | tier | required | status |
|---|---:|---:|---|
| frontend-type-check | 0/1 | informational | passes (0 errors) |
| frontend-unit | 1 | yes | passes (270/270) |
| contract-validate | 0 | yes | passes |

## Production Reality Findings

1. **Original barrel was 77% incomplete.** `index.js` only exported 5/22 components (`DataTable`,
   `LoadingOverlay`, `LoadingSpinner`, `MultiSelect`, `SummaryCard`). The remaining 17 were only
   accessible via direct path imports. The new `index.ts` exports all 22 — this is a correctness
   fix bundled into the migration.

2. **Two @ts-expect-error suppressions needed for not-yet-migrated upstream imports:**
   - `TimelineChart.vue` → `query-tool/utils/values.js` (Phase 3 scope)
   - `PaginationControl.vue` → `wip-shared/components/BasePagination` (Phase 3 scope)
   Both follow the declared-interface + `@ts-expect-error <not-yet-migrated: … — Phase 3 scope>` + cast
   pattern established in Phase 1b.

3. **DataTable.vue had a stale `.js` extension** on its `useSortableTable` import. Phase 1b
   had already renamed the source to `.ts`; the SFC still referenced the old specifier. Fixed
   by dropping the extension entirely (TypeScript/Vite resolution finds `.ts` automatically).

4. **context-manifest.md path format**: Initial manifest used glob patterns
   (`frontend/src/core/**/*.ts`); `cdd-kit context check` rejects these. Must use
   directory-level paths (`frontend/src/core/`).

## Lessons Promoted to Standards

All three promoted to `CLAUDE.md`:

1. **Barrel completeness audit** → `## TypeScript Migration Rules`
   When renaming `index.js → index.ts`, count exports against directory component count; complete any partial barrel as part of migration.
   Evidence: `specs/changes/migrate-shared-ui-ts/qa-report.md` (AC-3), archive.md Finding #1.

2. **context-manifest.md path format** → `## Context Governance`
   Use directory-level paths in `## Allowed Paths`; glob patterns are rejected by `cdd-kit context check`.
   Evidence: archive.md Finding #4.

3. **Stale `.js` specifiers inside SFCs** → `## TypeScript Migration Rules`
   During migration, audit internal `.js` import specifiers in each SFC for already-migrated targets; drop extensions entirely (TypeScript/Vite auto-resolve `.ts`).
   Evidence: `specs/changes/migrate-shared-ui-ts/qa-report.md` (DataTable spot-check), archive.md Finding #3.

## Follow-up Work

- Phase 2: migrate `admin-shared/`, `resource-shared/`, `wip-shared/` feature-level shared
  directories (not yet scheduled)
- Phase 3: migrate `query-tool/utils/values.js` and `wip-shared/components/BasePagination` to
  remove the two `@ts-expect-error` suppressions in `TimelineChart.vue` and
  `PaginationControl.vue`

## Cold Data Warning

This archive is historical evidence. Current requirements live in `contracts/` and active
project guidance (`CLAUDE.md`).
