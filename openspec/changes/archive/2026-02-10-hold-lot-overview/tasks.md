## 1. Backend — 擴充現有 Service 函數

- [x] 1.1 擴充 `get_hold_detail_summary()` 簽名：`reason` 改為 `Optional[str] = None`，新增 `hold_type: Optional[str] = None` 參數；reason=None 時聚合所有 HOLD lots；hold_type 過濾品質/非品質；cache path 和 Oracle fallback 都需支援；確保現有 Hold Detail 呼叫 `get_hold_detail_summary(reason='xxx')` 行為不變
- [x] 1.2 擴充 `get_hold_detail_lots()` 簽名：`reason` 改為 `Optional[str] = None`，新增 `hold_type: Optional[str] = None` 和 `treemap_reason: Optional[str] = None` 參數；reason=None 時返回所有 HOLD lots；treemap_reason 作為額外 HOLDREASONNAME 過濾（TreeMap 點擊篩選用）；增加 holdReason 欄位到 lot 回傳資料中；確保現有 Hold Detail 呼叫不受影響
- [x] 1.3 擴充 `get_wip_matrix()` 簽名：新增 `reason: Optional[str] = None` 參數，過濾 HOLDREASONNAME；cache path 用 DataFrame filter，Oracle fallback 用 QueryBuilder；reason=None 時行為不變，確保 WIP Overview 呼叫不受影響
- [x] 1.4 新增 `get_hold_overview_treemap()` 函數（唯一全新函數）：使用 `_select_with_snapshot_indexes(status='HOLD', hold_type=...)` 取得 HOLD DataFrame，按 (WORKCENTER_GROUP, HOLDREASONNAME) groupBy 聚合，回傳 `[{ workcenter, reason, lots, qty, avgAge }]`；接受 `hold_type`, `reason`, `workcenter`, `package` 參數；含 Oracle fallback

## 2. Backend — 路由

- [x] 2.1 建立 `src/mes_dashboard/routes/hold_overview_routes.py`，Flask Blueprint `hold_overview_bp`；頁面路由 `GET /hold-overview` 以 `send_from_directory` 提供 static Vite HTML，含 fallback HTML
- [x] 2.2 實作 `GET /api/hold-overview/summary`：解析 `hold_type`（預設 `quality`）和 `reason` query params，委派給擴充後的 `get_hold_detail_summary(reason=reason, hold_type=hold_type)`
- [x] 2.3 實作 `GET /api/hold-overview/matrix`：委派給現有 `get_wip_matrix(status='HOLD', hold_type=..., reason=...)`；套用 rate limiting (120 req/60s)
- [x] 2.4 實作 `GET /api/hold-overview/treemap`：解析 `hold_type`, `reason`, `workcenter`, `package` params，委派給 `get_hold_overview_treemap()`
- [x] 2.5 實作 `GET /api/hold-overview/lots`：解析所有 filter params + 分頁，委派給擴充後的 `get_hold_detail_lots(reason=reason, hold_type=hold_type, treemap_reason=treemap_reason, ...)`；套用 rate limiting (90 req/60s)；per_page 上限 200
- [x] 2.6 在 Flask app factory（`routes/__init__.py`）中註冊 `hold_overview_bp`

## 3. Backend — 向後相容驗證

- [x] 3.1 驗證 Hold Detail 頁面現有 3 支 API（summary/distribution/lots）在擴充後行為不變：`get_hold_detail_summary(reason='xxx')` 和 `get_hold_detail_lots(reason='xxx', ...)` 結果與擴充前一致
- [x] 3.2 驗證 WIP Overview 的 `get_wip_matrix()` 呼叫在新增 reason 參數後行為不變（reason=None 預設值）

## 4. Frontend — 腳手架

- [x] 4.1 建立 `frontend/src/hold-overview/` 目錄結構：`index.html`, `main.js`, `App.vue`, `style.css`, `components/`
- [x] 4.2 在 `vite.config.js` 的 input 加入 `'hold-overview': resolve(__dirname, 'src/hold-overview/index.html')`
- [x] 4.3 建立 `index.html`（Vue 3 mount point）、`main.js`（`createApp(App).mount('#app')`），import `style.css` 和 `wip-shared/styles.css`

## 5. Frontend — FilterBar（全新）

- [x] 5.1 建立 `components/FilterBar.vue`：Hold Type radio group（品質異常 default, 非品質異常, 全部）+ Reason dropdown（全部 + dynamic reasons）；emit `change` 事件帶 `{ holdType, reason }`

## 6. Frontend — SummaryCards（直接 import）

- [x] 6.1 在 App.vue 中直接 `import SummaryCards from '../hold-detail/components/SummaryCards.vue'`；props 形狀 `{ totalLots, totalQty, avgAge, maxAge, workcenterCount }` 完全相容，無需新建元件

## 7. Frontend — HoldMatrix（基於 MatrixTable 新建）

- [x] 7.1 建立 `components/HoldMatrix.vue`，以 `wip-overview/MatrixTable.vue` 為基礎：保留 matrix 渲染邏輯（sticky 首欄、Total row/column、"-" 零值、zh-TW 格式化）
- [x] 7.2 擴充互動：cell click → emit `{ workcenter, package }`、workcenter name/row total click → emit `{ workcenter }`、package header/column total click → emit `{ package }`；active cell/row/column highlight；toggle logic（再次點擊同一項 = 清除）

## 8. Frontend — HoldTreeMap（全新）

- [x] 8.1 建立 `components/HoldTreeMap.vue`：ECharts TreeMap，`import { TreemapChart } from 'echarts/charts'`；兩層結構（WC parent → Reason child）；面積=QTY；`visualMap` 色階 for avgAge（綠<1天, 黃1-3天, 橙3-7天, 紅>7天）
- [x] 8.2 實作 tooltip（workcenter, reason, lots, qty, avgAge）和 click handler → emit `{ workcenter, reason }`；toggle logic；"目前無 Hold 資料" empty state
- [x] 8.3 實作 `autoresize` 和 responsive height

## 9. Frontend — LotTable（基於 hold-detail/LotTable 新建）

- [x] 9.1 建立 `components/LotTable.vue`，以 `hold-detail/LotTable.vue` 為基礎：保留分頁邏輯（已 import `wip-shared/Pagination.vue`）、loading/error/empty 狀態、filter indicator；替換欄位：移除 Spec，新增 Hold Reason 欄位（holdReason）

## 10. Frontend — FilterIndicator（全新）

- [x] 10.1 建立 `components/FilterIndicator.vue`：顯示 active matrixFilter 和/或 treemapFilter 標籤，含 ✕ 清除按鈕；任一 cascade filter 啟用時顯示「清除所有篩選」按鈕

## 11. Frontend — App.vue 整合

- [x] 11.1 串接 App.vue：import 所有元件（SummaryCards 從 hold-detail import、其餘從 local components）；設定 reactive state for `filterBar`, `matrixFilter`, `treemapFilter`, `page`
- [x] 11.2 實作資料載入：`loadAllData()` 平行呼叫 4 支 API；`loadTreemapAndLots()` for matrix filter 變更；`loadLots()` for treemap filter 變更；使用 `useAutoRefresh` composable（從 `wip-shared/composables/useAutoRefresh.js` import）
- [x] 11.3 實作 filter cascade：filter bar 變更 → 清除 matrixFilter + treemapFilter → `loadAllData()`；matrix click → set matrixFilter, 清除 treemapFilter → `loadTreemapAndLots()`；treemap click → set treemapFilter → `loadLots()`
- [x] 11.4 實作 loading states（initialLoading overlay、refreshing indicator、refresh success/error）、error handling、手動重新整理按鈕、AbortController request cancellation
- [x] 11.5 從 treemap 資料的 distinct reasons 填充 Reason dropdown

## 12. Frontend — 樣式

- [x] 12.1 建立 `style.css`，沿用 `wip-overview/style.css` 和 `hold-detail/style.css` 的 pattern；包含 header、summary cards、matrix table、treemap section、lot table、filter indicator、filter bar、loading overlay、error banner 樣式

## 13. Build & 驗證

- [x] 13.1 執行 `npm --prefix frontend run build`，確認 `static/dist/` 生成 `hold-overview.html`, `hold-overview.js`, `hold-overview.css`
- [x] 13.2 驗證 Flask serve `/hold-overview` 正常，4 支 API endpoint 回應正確
- [x] 13.3 端對端測試：filter bar toggle → matrix click → treemap click → lot table cascade；驗證每層正確回應
- [x] 13.4 回歸測試：確認 Hold Detail 頁面（`/hold-detail?reason=xxx`）功能正常不受影響；確認 WIP Overview Matrix 功能正常不受影響
