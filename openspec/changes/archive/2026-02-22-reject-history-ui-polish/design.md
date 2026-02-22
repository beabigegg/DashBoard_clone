## Context

The reject-history page is a monolithic `App.vue` (~968 lines template+script) with a co-located `style.css`. It was built quickly and works, but differs from the hold-history page (the maturity benchmark) in structure and several UI details. The hold-history page delegates to 7 sub-components and follows project-wide conventions (loading overlay, hover effects, Chinese pagination text, header refresh button).

The page imports `wip-shared/styles.css` for design tokens and global classes, and `resource-shared/components/MultiSelect.vue` for multi-select dropdowns — but also duplicates ~120 lines of MultiSelect CSS in its own `style.css`.

## Goals / Non-Goals

**Goals:**

- Match hold-history's visual baseline: loading overlay, table hover, Chinese pagination, header refresh button
- Extract App.vue into sub-components following hold-history's proven pattern
- Remove duplicated MultiSelect CSS
- Keep all existing functionality and API interactions unchanged

**Non-Goals:**

- Changing column names or data display (user explicitly excluded #1)
- Adding new features, APIs, or functional capabilities
- Migrating to Tailwind or shared-ui components (page stays on wip-shared CSS)
- Touching backend code

## Decisions

### D1: Component extraction mirrors hold-history's architecture

Extract into 5 sub-components under `frontend/src/reject-history/components/`:

| Component | Responsibility | hold-history equivalent |
|-----------|---------------|------------------------|
| `FilterPanel.vue` | Filter grid, checkboxes, action buttons, active chips | `FilterBar.vue` |
| `SummaryCards.vue` | 6 KPI cards with lane colors | `SummaryCards.vue` |
| `TrendChart.vue` | Quantity trend bar chart (vue-echarts) | `DailyTrend.vue` |
| `ParetoSection.vue` | Pareto chart + table side-by-side | `ReasonPareto.vue` |
| `DetailTable.vue` | Detail table + pagination | `DetailTable.vue` |

**Rationale**: The hold-history pattern is proven and familiar to the team. Same granularity, same naming convention.

### D2: State stays in App.vue, components receive props + emit events

App.vue keeps all reactive state (`filters`, `summary`, `trend`, `pareto`, `detail`, `loading`, etc.) and API functions. Sub-components are presentational. This matches hold-history exactly and avoids over-engineering with composables for a single-page report.

### D3: Remove duplicated MultiSelect CSS, rely on resource-shared import chain

The MultiSelect component from `resource-shared/components/MultiSelect.vue` already bundles its own styles. The ~120 lines duplicated in `reject-history/style.css` (`.multi-select`, `.multi-select-trigger`, `.multi-select-dropdown`, etc.) can be deleted.

**Risk**: If some pages import MultiSelect without importing `resource-shared/styles.css`, they break. But reject-history doesn't import resource-shared/styles.css either — the MultiSelect component uses scoped styles or injects its own. Verify before deleting.

### D4: Loading overlay uses existing wip-shared pattern

Add `<div v-if="loading.initial" class="loading-overlay"><span class="loading-spinner"></span></div>` after the `.dashboard` div, identical to hold-history. The `.loading-overlay` and `.loading-spinner` classes are already defined in `wip-shared/styles.css`.

## Risks / Trade-offs

- **[Risk] MultiSelect CSS deletion breaks styling** → Verify the MultiSelect component renders correctly after removing the duplicated CSS. If it doesn't, the component may need its own `<style scoped>` block or the import chain needs adjustment.
- **[Risk] Extraction introduces subtle regressions** → Each component boundary is a potential data-flow bug. Mitigate by keeping the extraction mechanical: cut template section → paste into component → add props/emits.
- **[Trade-off] No composable extraction** → The script logic stays in App.vue (400+ lines). This is acceptable for now — hold-history works the same way. Future refactoring can extract a `useRejectHistory` composable if needed.
