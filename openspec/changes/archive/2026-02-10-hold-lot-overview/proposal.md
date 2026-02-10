## Why

主管需要一個獨立頁面，專注於線上 Hold Lot 的全局觀。目前 WIP Overview 的 Pareto 圖混合在所有 WIP 資料中，而 Hold Detail 只能看單一 Hold Reason 的明細。缺少一個可以「一覽各站 Hold Lot 情況」的專用分析頁面，讓主管能快速掌握哪些站別、哪些原因造成最多 Hold，以及滯留嚴重程度。

## What Changes

- 新增 `/hold-overview` 頁面（Vue 3 SFC + ECharts TreeMap），獨立於現有 WIP Overview 和 Hold Detail
- 新增 Flask Blueprint 與 4 支 API endpoints（summary / matrix / treemap / lots）
- 頁面預設只顯示品質異常 Hold，可切換至非品質異常或全部
- 提供 Workcenter x Package Matrix（如 WIP Overview），數字可點擊篩選下方所有資料
- 提供 TreeMap 視覺化（WC → Reason 層級，面積=QTY，顏色=平均滯留天數）
- 提供 paginated Hold Lot 明細表
- 篩選 cascade 機制：Filter Bar → 全部重載；Matrix 點擊 → TreeMap + Table；TreeMap 點擊 → Table
- 新增 Vite multi-entry 設定

## Capabilities

### New Capabilities
- `hold-overview-page`: Hold Lot Overview 頁面的完整功能規格，包含篩選器、Summary Cards、Matrix、TreeMap、明細表及 filter cascade 互動邏輯
- `hold-overview-api`: Hold Overview 後端 API 端點（summary / matrix / treemap / lots），從 DWH.DW_MES_LOT_V 查詢 Hold Lot 資料

### Modified Capabilities
- `vue-vite-page-architecture`: 新增 `hold-overview` 作為 Vite multi-entry HTML entry point

## Impact

- **Backend（擴充現有）**: 擴充 `wip_service.py` 中 `get_hold_detail_summary()` 和 `get_hold_detail_lots()` — 將 `reason` 改為 optional 並新增 `hold_type` 參數，向後相容；擴充 `get_wip_matrix()` 新增 optional `reason` 參數
- **Backend（唯一新增函數）**: `get_hold_overview_treemap()` — WC × Reason 聚合 + avgAge 計算
- **Backend（新增路由）**: `src/mes_dashboard/routes/hold_overview_routes.py`（Flask Blueprint，4 支 API）
- **Frontend（直接複用）**: `hold-detail/SummaryCards.vue`、`wip-shared/Pagination.vue`、`useAutoRefresh`、`core/api.js`、`wip-shared/constants.js`
- **Frontend（基於現有擴充）**: 基於 `MatrixTable.vue` 建 `HoldMatrix.vue`（加 cell/column click）；基於 `hold-detail/LotTable.vue` 建 `LotTable.vue`（加 Hold Reason 欄位）
- **Frontend（全新元件）**: `HoldTreeMap.vue`、`FilterBar.vue`、`FilterIndicator.vue`
- **Vite Config**: `vite.config.js` 新增 `hold-overview` entry
- **Dependencies**: `echarts/charts` 的 `TreemapChart`（進入現有 `vendor-echarts` chunk）
- **Cache**: 完全複用現有 Redis cache + snapshot indexes（已有 `wip_status['HOLD']` 和 `hold_type['quality'|'non-quality']` 索引），零改動
- **SQL**: 不需新增 SQL 模板 — 複用現有 summary.sql / matrix.sql / detail.sql + QueryBuilder WHERE clause
