## 1. 後端：Hold Overview API 支援 WIP 篩選參數

- [x] 1.1 `wip_service.py` — `get_hold_detail_summary` 加入 workorder/lotid/pj_type/firstname/waferdesc 5 個 Optional[str] 參數，傳入 `_select_with_snapshot_indexes()` 和 Oracle fallback
- [x] 1.2 `wip_service.py` — `get_hold_detail_lots` 加入同樣 5 個參數，傳入 `_select_with_snapshot_indexes()` 和 Oracle fallback
- [x] 1.3 `hold_overview_routes.py` — 3 個 API (summary/matrix/lots) 從 request.args 解析 workorder/lotid/type/firstname/waferdesc 並傳入對應 service function

## 2. 共用基礎設施：ParetoSection 搬遷、CSS 抽取、HoldLotTable

- [x] 2.1 從 `wip-overview/style.css` 抽取 `.pareto-grid`、`.pareto-section`、`.pareto-header` 等柏拉圖相關 CSS 到新檔案 `wip-shared/pareto-styles.css`，原位改為 `@import`
- [x] 2.2 將 `wip-overview/components/ParetoSection.vue` 移至 `wip-shared/components/ParetoSection.vue`，WIP Overview import 路徑更新
- [x] 2.3 新增 `wip-shared/components/HoldLotTable.vue`：以 hold-overview LotTable 為基礎，新增 Spec 欄位形成 13 欄統一表格（LOTID, WORKORDER, QTY, Product, Package, Workcenter, Hold Reason, Spec, Age, Hold By, Dept, Hold Comment, Future Hold Comment）

## 3. WIP 即時概況：移除柏拉圖 + Hold 卡片改跳轉

- [x] 3.1 `wip-overview/App.vue` — 移除 hold ref、fetchHold()、splitHold computed、navigateToHoldDetail()、template 的 `<section class="pareto-grid">` 區塊、對應 import (splitHoldByType, ParetoSection)
- [x] 3.2 `wip-overview/App.vue` — 修改 `toggleStatusFilter()`：quality-hold → `navigateToRuntimeRoute('/hold-overview?hold_type=quality')`，non-quality-hold → `navigateToRuntimeRoute('/hold-overview?hold_type=non-quality')`，RUN/QUEUE 保持原行為

## 4. Hold 即時概況：加入柏拉圖

- [x] 4.1 `hold-overview/App.vue` — import ParetoSection（from wip-shared）、splitHoldByType（from wip-derive）、navigateToRuntimeRoute；新增 hold ref、fetchHold()、splitHold computed、showQualityPareto/showNonQualityPareto computed、navigateToHoldDetail()
- [x] 4.2 `hold-overview/App.vue` — loadAllData 的 Promise.all 加入 fetchHold(signal)，結果存入 hold.value
- [x] 4.3 `hold-overview/App.vue` — Template 在 Matrix 後加入 pareto-grid 區段，根據 holdType 條件顯示品質異常 / 非品質異常柏拉圖
- [x] 4.4 `hold-overview/style.css` — 頂部加入 `@import '../wip-shared/pareto-styles.css'`

## 5. Hold 即時概況：加入 WIP FilterPanel

- [x] 5.1 `hold-overview/App.vue` — import FilterPanel（from wip-overview/components）、buildWipOverviewQueryParams（from wip-derive）；新增 filters reactive state + filterOptions ref + debounce 機制
- [x] 5.2 `hold-overview/App.vue` — 新增 buildAllFilterParams() 合併 holdType/reason 與 WIP 6 欄位；更新 fetchSummary/fetchMatrix/fetchLots 改用 buildAllFilterParams()
- [x] 5.3 `hold-overview/App.vue` — 新增 loadFilterOptions() 呼叫 `/api/wip/meta/filter-options`（帶 status=HOLD + holdType）、applyFilters()、clearAllFilters()、onFilterDraftChange()
- [x] 5.4 `hold-overview/App.vue` — Template 在 FilterBar 前加入 FilterPanel 組件
- [x] 5.5 `hold-overview/App.vue` — updateUrlState() 加入 6 欄位序列化；onMounted 解析 URL 的 WIP 篩選參數
- [x] 5.6 `hold-overview/main.js` — 加入 `import '../resource-shared/styles.css'`（MultiSelect 需要）

## 6. Hold 即時概況：預設 holdType 改為 'all'

- [x] 6.1 `hold-overview/App.vue` — 所有 holdType 預設值和 fallback 從 'quality' 改為 'all'（filterBar initial、normalizeHoldType、buildFilterBarParams、handleFilterChange）
- [x] 6.2 `hold-overview/components/FilterBar.vue` — 所有 holdType 預設值和 fallback 從 'quality' 改為 'all'

## 7. Hold Detail：返回按鈕改指 Hold Overview + 共用 LotTable

- [x] 7.1 `hold-detail/App.vue` — 返回按鈕 navigateToRuntimeRoute 從 '/wip-overview' 改為 '/hold-overview'，按鈕文字改為 '← Hold Overview'
- [x] 7.2 `hold-detail/App.vue` — no-reason redirect 從 '/wip-overview' 改為 '/hold-overview'
- [x] 7.3 `hold-detail/App.vue` — import 改用 `HoldLotTable` from `'../wip-shared/components/HoldLotTable.vue'`，取代 `./components/LotTable.vue`
- [x] 7.4 `hold_routes.py` — server-side redirect 從 '/wip-overview' 改為 '/hold-overview'

## 8. Hold 即時概況：版面修正 + 共用 LotTable

- [x] 8.1 `hold-overview/style.css` — `.hold-overview-hold-type-group` flex 改為 `0 0 auto`；`.hold-type-segment` min-width 改為 320px
- [x] 8.2 `hold-overview/App.vue` — Template 加入 `.content-grid` wrapper 包裹 Matrix + Pareto + FilterIndicator + LotTable
- [x] 8.3 `hold-overview/App.vue` — LotTable import 改用 `HoldLotTable` from `'../wip-shared/components/HoldLotTable.vue'`

## 9. 驗證

- [x] 9.1 前端 `npm run build` 通過（確認無 import 路徑斷裂）
