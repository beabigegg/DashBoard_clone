# Change Request

## Original Request

Phase 0 of TypeScript migration plan: add TypeScript toolchain (tsconfig and vite config).
Install `typescript`, `vue-tsc`, `@types/node`; add `tsconfig.json` with `strict: true` and
`allowJs: false` (initially including only `core/`); rename `vite.config.js` → `vite.config.ts`;
add `type-check` script (`vue-tsc --noEmit`) to `package.json`; wire `npm run type-check` gate in CI.
No business code is changed in this phase.

## Business / User Goal

Establish a TypeScript compilation environment as the foundation for a phased TS migration of the
frontend codebase (16 feature apps + shared layers). Phase 0 creates the tooling without touching
any business logic, so subsequent phases can migrate files one layer at a time with full type safety.

## Non-goals

- Migrating any `.js` → `.ts` source files (that is Phase 1a–3)
- Adding type annotations to existing JS code
- Changing any runtime behaviour

## Constraints

- Must not break existing `npm run dev`, `npm run build`, or Vitest test runs
- `tsconfig.json` must use `allowJs: false` so JS files are not accidentally type-checked
- CI gate must be added so regressions are caught immediately

## Known Context

- Frontend is Vue 3 + Vite; currently 100% JavaScript
- Migration plan documented in `ts-migration-plan.md` (project root)
- Phase ordering: Phase 0 → Phase 1a (core/) → Phase 1b (shared-composables/) → Phase 1c (shared-ui/) → …
- `vue-tsc` is the correct type-checker for Vue 3 SFCs

## Open Questions

None — scope is fully defined by ts-migration-plan.md Phase 0.

## Requested Delivery Date / Priority

High — this is a prerequisite for all subsequent TS migration phases.
