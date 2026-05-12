# Change Request

## Original Request

Migrate resource-shared/ to TypeScript (Phase 2, following Phase 1c migrate-shared-ui-ts).
Rename constants.js → constants.ts, convert HierarchyTable.vue and MultiSelect.vue to
`<script setup lang="ts">`, create an index.ts barrel, and fix stale .js import specifiers
in all resource-shared consumers.

## Business / User Goal

Advance the Phase 2 TypeScript migration plan. resource-shared/ contains shared constants
and two presentational components used by resource-history and resource-status. Migrating
this module eliminates implicit-any risk and enables strict-mode type checking for these
shared pieces.

## Non-goals

- No runtime behaviour change
- No API or CSS changes
- Not migrating resource-history/, resource-status/, or any other consumer module

## Constraints

- Must follow all CLAUDE.md TypeScript Migration Rules
- The legacy test `frontend/tests/legacy/resource-status.test.js` imports from
  `constants.js` via node --experimental-strip-types + ts-resolver-loader.mjs;
  the loader auto-remaps .js → .ts, so no change to the test file is needed
- No Python parity tests reference resource-shared (confirmed by audit)
- No `@ts-expect-error` or `as any` — core/ is fully migrated (Phase 1a)

## Known Context

- Scope: constants.js (7 exports + 3 functions), HierarchyTable.vue, MultiSelect.vue
- No existing barrel; need to create index.ts with 2 components + constants re-exports
- 5 stale .js specifiers in consumers (KpiCards.vue, StackedChart.vue, App.vue,
  EquipmentCard.vue, MatrixSection.vue) — must drop extension entirely
- Preceding migrations: Phase 1a core/ (21 modules), 1b shared-composables/ (11),
  1c shared-ui/ (22), 1d admin-shared/ (5)
- tsconfig.json currently includes src/core/**/* + src/shared-composables/**/* +
  src/shared-ui/**/* + src/admin-shared/**/*; needs src/resource-shared/**/*

## Open Questions

None.

## Requested Delivery Date / Priority

Same session as migrate-admin-shared-ts (Phase 2 batch).
