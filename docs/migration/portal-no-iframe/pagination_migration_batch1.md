# Shared Pagination Migration Batch 1

## Scope

Migrated pages/components:

- `wip-detail/components/LotTable.vue`
- `hold-detail/components/LotTable.vue`
- `hold-overview/components/LotTable.vue`
- `hold-history/components/DetailTable.vue`
- `mid-section-defect/components/DetailTable.vue`

## Change

- Replaced direct/inline pagination rendering with shared `PaginationControl`.
- Preserved existing page event contracts (`prev-page`, `next-page`).

## Visual parity checks

- Pagination visibility still depends on `totalPages > 1`.
- Prev/Next button enablement remains bounded by page range.
- Page info text format remains unchanged on migrated views.

## Removed duplicated artifacts

- Removed local Prev/Next markup and boundary logic from `hold-history/components/DetailTable.vue`.
- Consolidated pagination behavior into shared wrapper for this batch.
