# Change Request

## Original Request

Migrate wip-shared/ to TypeScript (Phase 2, following Phase 1c migrate-shared-ui-ts and Phase 2
migrate-resource-shared-ts). Rename constants.js → .ts, composables/useAutocomplete.js → .ts,
composables/useAutoRefresh.js → .ts, convert 3 Vue SFCs to lang="ts", create an index.ts barrel,
fix stale .js specifiers in all consumers, and remove @ts-expect-error suppression lines that
were placed in shared-composables/ and shared-ui/ pending this migration.

## Business / User Goal

Complete the Phase 2 TypeScript migration batch. wip-shared/ contains shared constants,
composables (useAutocomplete, useAutoRefresh), and 3 presentational Vue components.
Migrating this module eliminates the @ts-expect-error workarounds that were explicitly placed
in shared-composables/useAutocomplete.ts and useAutoRefresh.ts, and shared-ui/PaginationControl.vue
as cross-phase placeholders for this migration.

## Non-goals

- No runtime behaviour change
- No API or CSS changes
- Not migrating wip-overview/, wip-detail/, hold-overview/, hold-detail/, or any other consumer module

## Constraints

- Must follow all CLAUDE.md TypeScript Migration Rules
- Remove @ts-expect-error lines from: shared-composables/useAutocomplete.ts,
  shared-composables/useAutoRefresh.ts, shared-ui/components/PaginationControl.vue
  (all three were placed explicitly pending this phase)
- Internal stale .js imports within migrated files must also be fixed (SFCs importing
  from core/ with .js extension that was migrated in Phase 1a/1b)
- No Python parity tests reference wip-shared (confirmed)

## Known Context

- Scope to migrate: constants.js (2 exports), composables/useAutocomplete.js (exported function),
  composables/useAutoRefresh.js (exported function), HoldLotTable.vue, Pagination.vue, ParetoSection.vue
- No existing barrel; need to create index.ts
- @ts-expect-error consumers (must clean up after migration):
  - shared-composables/useAutocomplete.ts line 2-3
  - shared-composables/useAutoRefresh.ts line 2-3
  - shared-ui/components/PaginationControl.vue line 4-5
- Stale .js specifiers in consumers (drop extension entirely):
  - hold-detail/App.vue: constants.js
  - shared-composables/useAutocomplete.ts: useAutocomplete.js
  - shared-composables/useAutoRefresh.ts: useAutoRefresh.js
- Internal stale .js imports within wip-shared files (drop extension):
  - HoldLotTable.vue: shared-composables/useSortableTable.js (Phase 1b migrated)
  - ParetoSection.vue: core/wip-derive.js (Phase 1a migrated)
  - useAutocomplete.js: core/autocomplete.js and core/api.js (Phase 1a migrated)
- tsconfig.json currently includes 5 scopes; needs src/wip-shared/**/*
- ci-gate-contract.md currently at 1.3.3; needs bump to 1.3.4

## Open Questions

None.

## Requested Delivery Date / Priority

Same session as migrate-admin-shared-ts and migrate-resource-shared-ts (Phase 2 batch).
