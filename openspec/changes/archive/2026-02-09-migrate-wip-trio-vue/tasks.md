## 1. Shared Infrastructure

- [x] 1.1 Create `frontend/src/wip-shared/styles.css` with shared CSS variables (`:root`), gradient header, loading overlay, summary card, button, pagination, filter indicator, and responsive breakpoints extracted from the three pages
- [x] 1.2 Create `frontend/src/wip-shared/constants.js` with `NON_QUALITY_HOLD_REASONS` set (11 values matching backend `sql/filters.py`)
- [x] 1.3 Create `frontend/src/wip-shared/composables/useAutoRefresh.js` composable encapsulating 10-min interval, visibility-change refresh, and AbortController cancellation
- [x] 1.4 Create `frontend/src/wip-shared/composables/useAutocomplete.js` composable wrapping `core/autocomplete.js` with Vue reactive state, debounce 300ms, cross-filter, and dropdown management
- [x] 1.5 Create `frontend/src/wip-shared/components/Pagination.vue` shared pagination component (Prev/Next buttons, page info display)

## 2. Hold Detail Page (336 lines → Vue 3)

- [x] 2.1 Create `frontend/src/hold-detail/index.html` Vite entry point and `main.js` Vue app bootstrap
- [x] 2.2 Create `frontend/src/hold-detail/App.vue` with URL reason parameter reading, hold_type classification via `NON_QUALITY_HOLD_REASONS`, dynamic gradient header, missing-reason redirect, and auto-refresh setup
- [x] 2.3 Create `frontend/src/hold-detail/components/SummaryCards.vue` (5 cards: Total Lots, Total QTY, 平均當站滯留, 最久當站滯留, 影響站群) calling `GET /api/wip/hold-detail/summary`
- [x] 2.4 Create `frontend/src/hold-detail/components/AgeDistribution.vue` (4 clickable age cards: 0-1天, 1-3天, 3-7天, 7+天) with toggle filter
- [x] 2.5 Create `frontend/src/hold-detail/components/DistributionTable.vue` (reusable for workcenter and package tables) with row click filter toggle, calling `GET /api/wip/hold-detail/distribution`
- [x] 2.6 Create `frontend/src/hold-detail/components/LotTable.vue` (10 columns with filter indicator bar, "×" clear button) calling `GET /api/wip/hold-detail/lots`
- [x] 2.7 Create `frontend/src/hold-detail/style.css` with page-specific styles (dynamic gradient, age cards, distribution tables) importing `wip-shared/styles.css`
- [x] 2.8 Update `hold_routes.py` Flask route: keep reason validation redirect, change `render_template` to `send_from_directory` for `static/dist/hold-detail.html`
- [x] 2.9 Delete `src/mes_dashboard/templates/hold_detail.html`
- [x] 2.10 Verify Hold Detail page: summary cards, age/workcenter/package filtering, lot table pagination, back navigation, auto-refresh, missing-reason redirect

## 3. WIP Overview Page (784 lines → Vue 3)

- [x] 3.1 Create `frontend/src/wip-overview/index.html` Vite entry point and `main.js` Vue app bootstrap
- [x] 3.2 Create `frontend/src/wip-overview/App.vue` with data loading orchestration (summary + matrix + hold), auto-refresh setup, and filter state management
- [x] 3.3 Create `frontend/src/wip-overview/components/FilterPanel.vue` (4 autocomplete inputs using `useAutocomplete` composable, active filter tags with remove buttons, apply/clear buttons)
- [x] 3.4 Create `frontend/src/wip-overview/components/SummaryCards.vue` (2 KPI cards: Total Lots, Total QTY with zh-TW number formatting and scale transition)
- [x] 3.5 Create `frontend/src/wip-overview/components/StatusCards.vue` (4 clickable status cards: RUN, QUEUE, 品質異常, 非品質異常 with dim/active toggle)
- [x] 3.6 Create `frontend/src/wip-overview/components/MatrixTable.vue` (workcenter × package cross-tab, sticky first column, Total row/column, workcenter click drill-down to `/wip-detail`)
- [x] 3.7 Create `frontend/src/wip-overview/components/ParetoSection.vue` (ECharts dual-axis Pareto chart + detail table, bar click drill-down to `/hold-detail`, "目前無資料" empty state) — used as 2 instances (quality/non-quality)
- [x] 3.8 Create `frontend/src/wip-overview/style.css` with page-specific styles importing `wip-shared/styles.css`
- [x] 3.9 Update `app.py` Flask route for `/wip-overview`: change `render_template` to `send_from_directory`
- [x] 3.10 Delete `src/mes_dashboard/templates/wip_overview.html`
- [x] 3.11 Verify Overview page: summary cards, status card filtering, matrix drill-down, Pareto chart rendering and drill-down, autocomplete filtering, auto-refresh

## 4. WIP Detail Page (821 lines → Vue 3)

- [x] 4.1 Create `frontend/src/wip-detail/index.html` Vite entry point and `main.js` Vue app bootstrap
- [x] 4.2 Create `frontend/src/wip-detail/App.vue` with URL parameter initialization (workcenter + 4 filters), workcenter fallback fetch, auto-refresh setup, and replaceState URL update
- [x] 4.3 Create `frontend/src/wip-detail/components/FilterPanel.vue` (4 autocomplete inputs using `useAutocomplete` composable, shared with Overview pattern)
- [x] 4.4 Create `frontend/src/wip-detail/components/SummaryCards.vue` (5 clickable status cards: Total Lots, RUN, QUEUE, 品質異常, 非品質異常 with dim/active toggle)
- [x] 4.5 Create `frontend/src/wip-detail/components/LotTable.vue` (4 sticky left columns with cascading left positions, dynamic spec columns, LOT ID click to open detail panel, status color coding)
- [x] 4.6 Create `frontend/src/wip-detail/components/LotDetailPanel.vue` (inline expandable panel with 4-column grid: 基本資訊, 產品資訊, 製程資訊, 物料資訊, conditional Hold/NCR sections)
- [x] 4.7 Create `frontend/src/wip-detail/style.css` with page-specific styles (sticky columns, spec column coloring, lot detail panel) importing `wip-shared/styles.css`
- [x] 4.8 Update `app.py` Flask route for `/wip-detail`: change `render_template` to `send_from_directory`
- [x] 4.9 Delete `src/mes_dashboard/templates/wip_detail.html`
- [x] 4.10 Verify Detail page: URL param initialization, workcenter fallback, summary card filtering, sticky table scrolling, lot detail panel, autocomplete filtering, pagination, auto-refresh

## 5. Vite Configuration & Build

- [x] 5.1 Update `vite.config.js`: change 3 entries from `main.js` to `index.html`, add `vendor-vue` chunk splitting rule, ensure `vendor-echarts` chunk includes Overview usage
- [x] 5.2 Update `package.json` build script to copy the 3 new HTML files to `static/dist/`
- [x] 5.3 Run `npm run build` and verify output includes `wip-overview.html/js/css`, `wip-detail.html/js/css`, `hold-detail.html/js/css` with correct chunk splitting

## 6. Integration & Cleanup

- [x] 6.1 Verify drill-down navigation: Overview → Detail (workcenter + filters URL params), Overview → Hold Detail (Pareto chart/table reason links)
- [x] 6.2 Verify back navigation: Detail → Overview, Hold Detail → Overview
- [x] 6.3 Verify portal iframe embedding works for all three pages
- [x] 6.4 Remove unused imports of `escapeHtml`/`safeText` from `core/table-tree.js` in hold-detail (Vue handles escaping)
- [x] 6.5 Verify all three pages render correctly at responsive breakpoints (1400px, 1000px, 768px)
