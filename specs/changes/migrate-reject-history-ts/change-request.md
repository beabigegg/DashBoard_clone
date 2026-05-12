# Change Request

## Original Request

Migrate `frontend/src/reject-history/` feature app to TypeScript. This is Phase 3, item #1 of the project-wide TypeScript migration plan (`ts-migration-plan.md`).

## Business / User Goal

Bring the highest-complexity feature app (App.vue 1370 lines, DuckDB composable, Pareto multi-dimensional filtering) under static type safety. Catch type-level bugs before they reach production and establish DuckDB typing patterns reusable by subsequent Phase 3 apps (`hold-history/`, `resource-history/`).

## Non-goals

- No behavior changes; the app must behave identically before and after migration.
- Do not migrate other feature apps (those are separate CDD changes).
- Do not introduce new features or refactors beyond what is required for the TypeScript conversion.

## Constraints

- `npm run type-check` must pass with zero errors scoped to `reject-history/` on completion.
- All existing Vitest tests must continue to pass.
- Follow CLAUDE.md TypeScript Migration Rules:
  - Drop `.js` extension specifiers inside SFCs (use bare specifiers for auto-resolution).
  - Temporary `any` must be annotated `// TODO: type <reason>`.
  - Audit Python parity tests if any `.js` → `.ts` renames affect paths referenced there.
  - Barrel `index.js → index.ts` must export all components (count before migration).
- Phase 1a–1c and Phase 2 shared layers are fully migrated; use their exported types directly.

## Known Context

- `frontend/src/reject-history/App.vue` is ~1370 lines — largest single file in the migration.
- App uses a DuckDB composable for local analytical queries (Pareto, multi-dimension filter).
- `wip-shared/`, `admin-shared/`, `resource-shared/` (Phase 2) are already TypeScript.
- `shared-ui/`, `shared-composables/`, `core/` (Phase 1) are already TypeScript.

## Open Questions

None.

## Requested Delivery Date / Priority

High priority — first Phase 3 app. No hard deadline.
