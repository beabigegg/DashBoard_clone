# Change Request

## Original Request

Migrate `frontend/src/hold-history/` feature app to TypeScript. This is Phase 3, item #2 of the project-wide TypeScript migration plan (`ts-migration-plan.md`).

## Business / User Goal

Bring the hold-history app under static type safety. The app contains DuckDB composable logic and Future Hold accumulation logic (known semantic complexity around MES lot-release clearing `FUTUREHOLDCOMMENTS`). The `reject-history/` migration (item #1) is now archived and its DuckDB typing patterns are available as reference.

## Non-goals

- No behavior changes; the app must behave identically before and after migration.
- Do not migrate other feature apps (those are separate CDD changes).
- Do not introduce new features or refactors beyond what TypeScript conversion requires.

## Constraints

- `npm run type-check` must pass with zero errors scoped to `hold-history/` on completion.
- All existing Vitest tests must continue to pass.
- Follow CLAUDE.md TypeScript Migration Rules:
  - Drop `.js` extension specifiers inside SFCs (use bare specifiers for auto-resolution).
  - Temporary `any` must be annotated `// TODO: type <reason>`.
  - Audit Python parity tests if any `.js` → `.ts` renames affect paths referenced there.
  - Barrel `index.js → index.ts` must export all components (count before migration).
  - Do NOT update `index.html` entry-point references (Vite resolves `main.ts` correctly).
  - echarts callback params: annotate `// TODO: type echarts callback`, do not block.
- Phase 1a–1c (`core/`, `shared-composables/`, `shared-ui/`) and Phase 2 (`wip-shared/`, `admin-shared/`, `resource-shared/`) shared layers are fully TypeScript; use their exported types directly.

## Known Context

- App uses a DuckDB composable for local analytical queries (similar pattern to `reject-history/`).
- Future Hold accumulation logic: MES clears `FUTUREHOLDCOMMENTS` on lot release, causing historical value decay. This is a known semantic issue — do not change the business logic, only add types.
- `reject-history/` migration established DuckDB composable typing patterns reusable here.

## Open Questions

None.

## Requested Delivery Date / Priority

High priority — Phase 3 item #2. No hard deadline.
