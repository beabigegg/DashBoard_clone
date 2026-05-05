# Change Request

## Original Request

Phase 1a of the TypeScript migration plan: migrate all 21 `.js` files in `frontend/src/core/` to TypeScript. Establish `ApiResponse<T>` generic interface, convert `endpoint-schemas.js` runtime shapes to TS interfaces (while keeping runtime validation in `schema-guard`), and ensure `npm run type-check` (`vue-tsc --noEmit`) passes with 0 errors for `core/`. Phase 0 (toolchain: `tsconfig.json` with `strict: true`, `vite.config.ts`, `type-check` CI gate) is already complete.

## Business / User Goal

Establish the API type contract foundation that all feature apps will depend on. Once `core/` is typed, every feature app that imports from `core/` gets type inference and IDE autocompletion for free during their own migration phases.

## Non-goals

- Do not migrate any files outside `frontend/src/core/`
- Do not migrate `shared-composables/`, `shared-ui/`, or any feature app (those are Phase 1b/1c/2/3)
- Do not change runtime behavior of any module — rename + add types only
- Do not add `@ts-ignore` without a `// TODO:` comment explaining the gap

## Constraints

- `tsconfig.json` currently has `include: ["src/core/index.ts"]` (Phase 0 placeholder); must expand to `include: ["src/core/**/*"]` after migration
- Each temporary `any` must carry `// TODO: type <explanation>`
- Existing tests (`frontend/tests/core/`, `frontend/tests/schema-guard.test.js`, `frontend/tests/unwrap-api-result.test.js`, `frontend/tests/legacy/*.test.js`) must continue passing after rename
- `frontend/src/core/index.ts` already exists as a Phase 0 placeholder (re-export barrel)
- The `endpoint-schemas.js` runtime schema objects become TS interfaces; the runtime validation in `schema-guard.js` is preserved (dual-layer protection)

## Known Context

- `frontend/src/core/` has 21 `.js` files + 1 existing `index.ts` (placeholder)
- `frontend/tsconfig.json` is in place with `strict: true` (Phase 0 result, commit 71a27b6)
- CI gate `npm run type-check` exists and currently passes (0 files checked)
- Migration plan: `ts-migration-plan.md` in project root

## Open Questions

None — scope is fully defined by the migration plan.

## Requested Delivery Date / Priority

High — Phase 1a blocks Phase 1b, 1c, and all subsequent phases.
