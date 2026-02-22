## 1. Quick visual fixes (no component extraction needed)

- [x] 1.1 Add `tbody tr:hover` background rule to `style.css` for `.detail-table` and `.pareto-table`
- [x] 1.2 Localize pagination: change "Prev" → "上一頁", "Next" → "下一頁", "Page X / Y · Total Z" → "第 X / Y 頁 · 共 Z 筆"
- [x] 1.3 Add loading overlay + spinner after `.dashboard` div (`<div v-if="loading.initial" class="loading-overlay">`)
- [x] 1.4 Add "重新整理" button in header-right area, wired to `applyFilters`
- [x] 1.5 Remove duplicated MultiSelect CSS (~120 lines of `.multi-select-*` rules) from `style.css`; verify MultiSelect still renders correctly

## 2. Extract sub-components from App.vue

- [x] 2.1 Create `components/FilterPanel.vue` — extract filter grid, checkbox row, action buttons, and active-filter chips section; props: `filters`, `options`, `loading`, `activeFilterChips`; emits: `apply`, `clear`, `remove-chip`, `export-csv`, `pareto-scope-toggle`
- [x] 2.2 Create `components/SummaryCards.vue` — extract `.summary-row` section; props: `cards`
- [x] 2.3 Create `components/TrendChart.vue` — extract trend chart `.card` section with ECharts registration and chart option computed internally; props: `items`, `loading`
- [x] 2.4 Create `components/ParetoSection.vue` — extract pareto chart + table `.card` section with ECharts registration and chart option computed internally; props: `items`, `detailReason`, `loading`; emits: `reason-click`
- [x] 2.5 Create `components/DetailTable.vue` — extract detail table + pagination; props: `items`, `pagination`, `loading`; emits: `go-to-page`

## 3. Rewire App.vue as orchestrator

- [x] 3.1 Replace inline template sections with sub-component tags, passing props and wiring emits
- [x] 3.2 Move ECharts `use()` registration and chart computed properties into their respective chart components
- [x] 3.3 Verify all interactions work: filter apply/clear, pareto click → detail filter, pagination, CSV export, refresh button

## 4. Verify and build

- [x] 4.1 Run `vite build` and confirm no compilation errors
- [x] 4.2 Visually verify: loading overlay, table hover, Chinese pagination, refresh button, pareto interaction, filter chips
