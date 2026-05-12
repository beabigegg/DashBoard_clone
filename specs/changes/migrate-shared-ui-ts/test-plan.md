---
change-id: migrate-shared-ui-ts
schema-version: 0.1.0
last-changed: 2026-05-12
risk: medium
tier: 2
---

# Test Plan: migrate-shared-ui-ts

## Acceptance Criteria → Test Mapping

| AC | criterion summary | test family | test file / command | tier |
|---|---|---|---|---|
| AC-1 | all 22 SFCs use `<script setup lang="ts">` | compile/contract | `cd frontend && npm run type-check` | 0 |
| AC-2 | all props use `defineProps<T>()` generic syntax | compile/contract | `cd frontend && npm run type-check` | 0 |
| AC-3 | `index.ts` re-exports all 22 components | compile/contract + audit/static | `npm run type-check`; manual grep for 22 names | 0 |
| AC-4 | `tsconfig.json` includes `"src/shared-ui/**/*"` | compile/contract | `npm run type-check` (would fail without include) | 0 |
| AC-5 | `npm run type-check` exits 0 | compile/contract | `cd frontend && npm run type-check` | 0 |
| AC-6 | `npm run build` succeeds | build | `cd frontend && npm run build` | 1 |
| AC-7 | Vitest suites pass | unit/integration | `cd frontend && npm run test` | 0 |
| AC-8 | pytest parity tests pass; no renamed `.js` path referenced | audit/static | `grep -r "shared-ui.*\.js" tests/**/*.py` — zero hits required; `pytest tests/test_frontend_compute_parity.py tests/test_frontend_duckdb_parity.py` | 0 |
| AC-9 | no bare `@ts-ignore`; every `@ts-expect-error` has comment | audit/static | `grep -rn "@ts-ignore\|@ts-expect-error" frontend/src/shared-ui/` | 0 |
| AC-10 | every `any` has `// TODO: type <description>` | audit/static | `grep -rn ": any\b\|as any\b" frontend/src/shared-ui/` | 0 |
| AC-11 | no `<template>` or `<style>` blocks modified | audit/static | `git diff --stat` against pre-migration snapshot | 0 |
| AC-12 | no runtime behavior change | unit | existing Vitest component suites (AC-7) | 0 |

## Test File Inventory

| file | what it covers | risk flags |
|---|---|---|
| `frontend/tests/components/DataTable.test.js` | DataTable props, loading state, column injection | DataTable imports `useSortableTable.js` — specifier must become `.ts` after source rename; test uses static `import DataTable from '../../src/shared-ui/components/DataTable.vue'` (safe, no `.js` resolution risk) |
| `frontend/tests/components/LoadingOverlay.test.js` | LoadingOverlay mount, tier prop | static `.vue` import; no risk |
| `frontend/tests/components/LoadingSpinner.test.js` | LoadingSpinner mount, size prop | static `.vue` import; no risk |
| `frontend/tests/legacy/loading-standardization.test.js` | text-search assertions on LoadingSpinner, LoadingOverlay, BlockLoadingState, MultiSelect, DataTable source content | reads raw `.vue` file via `readFileSync`; no module resolution — safe across rename; assertions check prop value strings, not `lang` attribute |
| `cd frontend && npm run type-check` (vue-tsc) | AC-1 through AC-5, AC-9, AC-10 | primary gate |
| `cd frontend && npm run build` | Vite resolution of `index.ts` barrel, all 22 component imports | secondary gate |
| `pytest tests/test_frontend_compute_parity.py` | parity compute tests | audited: zero `shared-ui/*.js` references; safe |
| `pytest tests/test_frontend_duckdb_parity.py` | parity DuckDB tests | audited: zero `shared-ui/*.js` references; safe |

## Test Families

| family | tier | description |
|---|---|---|
| compile/contract | 0 | `npm run type-check` — proves all 22 SFCs are valid TypeScript, tsconfig include is correct, props generics are well-formed; this single command is the primary gate for AC-1 through AC-5 |
| unit | 0 | Vitest component suites (DataTable, LoadingOverlay, LoadingSpinner) — mount-and-assert; prove no runtime behavior change (AC-12) |
| audit/static | 0 | grep-based checks: AC-8 Python `.js` path audit, AC-9 `@ts-expect-error` comments, AC-10 `any` comments, AC-11 template/style diff |
| build | 1 | `npm run build` — Vite production bundle; proves barrel re-exports resolve and no tree-shaking errors (AC-6) |

## Special Cases: Cross-Phase Import Specifiers

Two SFCs import from not-yet-migrated `.js` files. These require special handling before `type-check` can pass:

- `DataTable.vue` imports `useSortableTable` from `../../shared-composables/useSortableTable.js` — the source is already `.ts` (Phase 1b complete); update specifier to `.ts` or drop extension.
- `TimelineChart.vue` imports `formatDateTime`, `normalizeText`, `parseDateTime` from `../../query-tool/utils/values.js` — this file is not yet migrated; apply the declared-interface + `@ts-expect-error <not-yet-migrated: query-tool/utils phase>` + cast pattern per CLAUDE.md TypeScript Migration Rules.

## Out of Scope

- New unit tests for the 17 SFCs that lack existing Vitest coverage (AiChartRenderer, AiChatMessage, AiChatPanel, AiChatTrigger, Chip, DataTableColumn, EmptyState, ErrorBanner, FilterToolbar, MultiSelect, PageHeader, PaginationControl, SectionCard, SkeletonLoader, StatusBadge, SummaryCard, SummaryCardGroup, SummaryCardGroup, TimelineChart) — coverage gaps pre-exist this migration
- Renaming test files from `.test.js` to `.test.ts`
- E2E / Playwright tests — no runtime behavior change
- Migrating `query-tool/utils/values.js` or any other non-shared-ui file
- Completing the `index.ts` barrel to all 22 components is part of AC-3, but consumers that import components directly by path (`../shared-ui/components/X.vue`) require no specifier update

## Rollback Signal

If `npm run type-check` reports errors on N components after adding `lang="ts"`:

1. Revert those specific SFCs to `<script setup>` (drop `lang="ts"`).
2. Add `// @ts-expect-error <not-yet-migrated: shared-ui Phase 1c>` with cast at the import site in any cross-SFC consumer.
3. Re-run `npm run type-check` — remaining migrated SFCs must still exit 0.
4. Gate passes when all migrated SFCs are clean and reverted SFCs are tracked as follow-on tasks.

## Gate Command Sequence

```sh
grep -rn "@ts-ignore" frontend/src/shared-ui/         # must be zero
grep -rn "shared-ui.*\.js" tests/**/*.py               # must be zero
cd frontend && npm run type-check
cd frontend && npm run test
cd frontend && npm run build
```
