# UI Pattern Inventory (WIP / Resource / Hold / QC)

## Duplicated patterns observed

1. Filter bars:
   - `hold-overview/components/FilterBar.vue`
   - `hold-history/components/FilterBar.vue`
   - `resource-status/components/FilterBar.vue`
   - `resource-history/components/FilterBar.vue`
   - `mid-section-defect/components/FilterBar.vue`
2. KPI/Summary cards:
   - `wip-overview/components/SummaryCards.vue`
   - `wip-detail/components/SummaryCards.vue`
   - `hold-detail/components/SummaryCards.vue`
   - `hold-history/components/SummaryCards.vue`
   - `resource-status/components/SummaryCards.vue`
   - `resource-history/components/KpiCards.vue`
   - `mid-section-defect/components/KpiCards.vue`
3. Table + pagination shells:
   - `wip-detail/components/LotTable.vue`
   - `hold-detail/components/LotTable.vue`
   - `hold-overview/components/LotTable.vue`
   - `hold-history/components/DetailTable.vue`
   - `mid-section-defect/components/DetailTable.vue`
   - `qc-gate/components/LotTable.vue`
4. Multi-select and query controls:
   - `resource-shared/components/MultiSelect.vue`
   - `mid-section-defect/components/MultiSelect.vue`
5. Repeated status/badge presentation logic:
   - WIP/Hold status class mapping and local badge styles in multiple tables/cards.

## Consolidation targets

- Shared UI layer (`frontend/src/shared-ui/components`)
- Shared composables layer (`frontend/src/shared-composables`)
- Tailwind tokenized styles (`frontend/src/styles/tailwind.css`)

## First migration batch completed

- Unified pagination rendering for WIP/Hold/Mid-section detail tables through `PaginationControl` wrapper.
- Auto-refresh and autocomplete imports migrated to `shared-composables` entry points.
