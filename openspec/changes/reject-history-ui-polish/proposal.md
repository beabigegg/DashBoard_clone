## Why

The reject-history page was shipped as a monolithic single-file implementation. While functional, it has visual inconsistencies with other mature report pages (hold-history, wip-overview) and is missing standard UX affordances. Aligning it now reduces user confusion when switching between report pages and improves maintainability.

## What Changes

- Add `tbody tr:hover` highlight and missing loading overlay/spinner to match hold-history baseline
- Localize pagination controls from English (Prev/Next/Page/Total) to Chinese (上一頁/下一頁/頁/共)
- Remove ~120 lines of duplicated MultiSelect CSS from `style.css` (already provided by `resource-shared/styles.css`)
- Add a "重新整理" (refresh) button in the header, consistent with hold-history
- Extract monolithic `App.vue` (~968 lines) into focused sub-components mirroring hold-history's architecture: `FilterPanel`, `SummaryCards`, `TrendChart`, `ParetoSection`, `DetailTable`

## Capabilities

### New Capabilities

_(none — no new functional capabilities are introduced)_

### Modified Capabilities

- `reject-history-page`: UI/UX polish — add loading overlay, hover effects, localized pagination, header refresh button, and modular component extraction

## Impact

- **Files modified**: `frontend/src/reject-history/App.vue`, `frontend/src/reject-history/style.css`
- **Files created**: `frontend/src/reject-history/components/FilterPanel.vue`, `SummaryCards.vue`, `TrendChart.vue`, `ParetoSection.vue`, `DetailTable.vue`
- **No API changes** — all backend endpoints remain untouched
- **No dependency changes** — continues using `vue-echarts`, `resource-shared/MultiSelect`
