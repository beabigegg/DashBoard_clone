# Change Request

## Original Request

Phase 3 TypeScript migration of the `frontend/src/resource-history/` app. Migrate all `.js` files to `.ts` and add `lang="ts"` to all `.vue` component `<script setup>` blocks. This is part of the ongoing phased TypeScript migration (Phase 1a core ✓, Phase 1b shared-composables ✓, Phase 1c shared-ui ✓, Phase 2 resource-shared/admin-shared partially done). Affected files: `main.js`, `useResourceHistoryDuckDB.js`, `App.vue`, and 7 components under `components/`. Imports from already-migrated modules (core, shared-composables, shared-ui, resource-shared) must have `.js` extension specifiers dropped.

## Business / User Goal

## Non-goals

## Constraints

## Known Context

## Open Questions

## Requested Delivery Date / Priority
