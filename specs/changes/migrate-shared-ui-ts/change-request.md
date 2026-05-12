# Change Request

## Original Request

繼續使用 cdd-kit 進行 Phase 1c：migrate shared-ui/ components to TypeScript。

Affected surface: `frontend/src/shared-ui/` — 22 Vue SFCs + `index.js`
Desired behavior: Add `lang="ts"` to all SFCs, use `defineProps<T>()` generic syntax, convert `index.js → index.ts`
Success criterion: `tsconfig.json` includes `shared-ui/`, `vue-tsc --noEmit` passes with 0 errors

## Business / User Goal

Phase 1c of the TypeScript migration plan. Phase 1a (core/) and Phase 1b (shared-composables/) are complete. shared-ui/ hosts 22 shared components used by every feature app; adding static types to their props/emits enables IDE autocompletion and catch prop-contract violations at compile time rather than runtime.

## Non-goals

- Do not migrate feature app directories (Phase 3 scope)
- Do not migrate admin-shared/, resource-shared/, wip-shared/ (Phase 2 scope)
- Do not change any component logic or visual output
- Do not add new features or refactor component internals

## Constraints

- Each component must pass `vue-tsc --noEmit` under strict mode
- `@ts-ignore` is banned; `@ts-expect-error` allowed only with a comment describing the pending migration phase
- Any `any` must carry a `// TODO: type <description>` comment
- Phase 1a and 1b types (core/ and shared-composables/) are available for import

## Known Context

- Phase 1a complete: `frontend/src/core/` fully TypeScript
- Phase 1b complete: `frontend/src/shared-composables/` fully TypeScript
- tsconfig.json currently includes `core/` and `shared-composables/`; needs `shared-ui/` added
- Vue 3.5 `defineProps<T>()` generic syntax is the target pattern
- 22 components: AiChartRenderer, AiChatMessage, AiChatPanel, AiChatTrigger, BlockLoadingState, Chip, DataTableColumn, DataTable, EmptyState, ErrorBanner, FilterToolbar, LoadingOverlay, LoadingSpinner, MultiSelect, PageHeader, PaginationControl, SectionCard, SkeletonLoader, StatusBadge, SummaryCardGroup, SummaryCard, TimelineChart

## Open Questions

None — scope is well-defined by ts-migration-plan.md.

## Requested Delivery Date / Priority

High — shared-ui/ is a dependency for Phase 2 and Phase 3.
