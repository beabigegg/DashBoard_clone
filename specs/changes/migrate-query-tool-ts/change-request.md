# Change Request

## Original Request

Migrate the query-tool app from JavaScript to TypeScript (Phase 3 of the project-wide TS migration). All `.js` files under `frontend/src/query-tool/` — including composables, utils, and main.js — should be renamed to `.ts` and annotated with proper TypeScript types. Vue SFCs should use `<script lang="ts">`. The migration must pass `npm run type-check`, keep all existing tests green, and produce zero runtime regressions.

## Business / User Goal

Advance Phase 3 TypeScript migration coverage. Eliminate remaining JS files in the query-tool feature app so the codebase achieves full type safety for this module.

## Non-goals

- No feature changes or new functionality
- No refactoring of business logic beyond what is required for type annotations
- No changes to the Python backend

## Constraints

- Follow TypeScript Migration Rules in CLAUDE.md (e.g., `main.js` entry in `index.html` is intentionally left as `.js`; Vite resolves `.ts` at build time)
- `vi.mock()` static calls with `.js` specifiers do NOT need updating (Vite handles transparently)
- Dynamic `import('...file.js')` specifiers must drop the `.js` extension after rename
- For not-yet-migrated imports, use local interface + `// @ts-expect-error` + double-cast pattern
- Audit all Python test files for hardcoded `.js` paths when renaming

## Known Context

- JS files to migrate: `composables/useEquipmentQuery.js`, `useLotDetail.js`, `useLotEquipmentQuery.js`, `useLotLineage.js`, `useLotResolve.js`, `useReverseLineage.js`; `utils/csv.js`, `values.js`; `main.js`
- All Vue SFCs (`App.vue` + 13 components) need `<script lang="ts">` audit
- Previous Phase 3 migrations: yield-alert-center (complete), others archived

## Open Questions

None — migration rules are well-established in CLAUDE.md.

## Requested Delivery Date / Priority

Normal priority.
