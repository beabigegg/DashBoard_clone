# Archive: migrate-yield-alert-center-ts

## Change Summary

Migrated `frontend/src/yield-alert-center/` from JavaScript to TypeScript as Phase 3 of the project-wide TS migration. Renamed three JS composable/utility files to `.ts`, added `lang="ts"` to five Vue SFCs, and updated import specifiers in two test files that hard-referenced `.js` extensions. No API, backend, or runtime behavior was changed.

## Final Behavior

The yield-alert-center page loads and operates identically. Vite resolves `main.ts` transparently from the existing `index.html` `./main.js` entry. TypeScript now enforces types on `utils.ts` (three exported functions), `main.ts` (entry), and `useYieldAlertDuckDB.ts` (~562 lines of DuckDB-WASM composable logic).

## Final Contracts Updated

None. contract-reviewer confirmed no contracts reference the renamed JS filenames. All yield-alert API contract references describe backend endpoints, unaffected by a frontend file rename.

## Final Tests Added / Updated

- `frontend/tests/legacy/yield-alert-center-utils.test.js` — dropped `.js` from `utils` import specifier (line 8)
- `frontend/tests/abort/yield-alert-abort.test.js` — dropped `.js` from two dynamic `import()` calls (lines 106, 125)
- All other test files passed unmodified (AC-3, AC-4 verified)

## Final CI/CD Gates

| Gate | Result |
|---|---|
| Vitest suite (331 tests, 30 files) | PASS |
| Legacy node --test suite | PASS |
| vue-tsc --noEmit | PASS (0 errors) |
| cdd-kit gate | PASS |

Required CI gate: `frontend-tests.yml / frontend-unit-tests` (Node 22). Merged to main after CI green.

## Production Reality Findings

- `frontend/tsconfig.json` does not include `src/yield-alert-center` in its `include` array — pre-existing scope policy shared across all Phase 3 app migrations. Not introduced by this change.
- `vi.mock(...)` with `.js` specifiers for already-migrated `src/core/` files inside `yield-alert-abort.test.js` continues to resolve correctly post-rename. This is an established pattern — do NOT update those specifiers.
- `App.cross-filter.test.js` `vi.mock('...useYieldAlertDuckDB.js')` static mock also resolves correctly after rename — Vite's mock resolution handles `.js` → `.ts` transparently for static mocks.

## Lessons Promoted to Standards

- **CLAUDE.md** `## TypeScript Migration Rules`: Added rule distinguishing static `vi.mock()` (Vite resolves `.js` → `.ts` transparently; do NOT update specifiers) from dynamic `import()` (does NOT resolve transparently; must drop `.js` extension). Evidence: `test-plan.md` lines 40–46, `archive.md` §Production Reality Findings.

## Follow-up Work

- `frontend/tsconfig.json`: `src/yield-alert-center` is not yet in the `include` list. Future task: add it when all Phase 3 per-app migrations are complete and a single tsconfig expand pass is warranted.
- Remaining JS apps (Phase 3): `admin-dashboard`, `admin-performance`, `admin-user-usage-kpi`, `anomaly-overview`, `material-trace`, `mid-section-defect`, `portal`, `portal-shell`, `query-tool`, `tables`.

## Cold Data Warning

This archive is historical evidence. Current requirements live in `contracts/` and active project guidance (`CLAUDE.md`).
