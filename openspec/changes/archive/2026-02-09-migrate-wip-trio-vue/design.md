## Context

WIP 三頁（Overview、Detail、Hold Detail）是報表類核心頁面，合計 1,941 行 vanilla JS，目前透過 Jinja2 `_base.html` 載入 `window.MesApi` 和 `window.Toast` 全域物件。QC-GATE 和 Tables 頁面已成功遷移至純 Vite 架構，建立了 `send_from_directory` + `apiGet`/`apiPost` 模式。

三頁存在 drill-down 導覽關係：
- Overview → Detail：點擊 matrix workcenter，透過 URL params 傳遞 `workcenter` + 四個篩選條件
- Overview → Hold Detail：點擊 Pareto 柱/表格連結，透過 `?reason=` 傳遞

所有後端 API 均為 GET，無 CSRF 依賴，後端路由和 API 不需修改。

## Goals / Non-Goals

**Goals:**
- 三頁完全脫離 Jinja2 模板和 `window.MesApi` 依賴
- 保持現有功能完全一致（pixel-level 不要求，行為一致即可）
- 建立三頁共用的 CSS 變數和基礎樣式模組
- Hold Detail 新增自動刷新 + AbortController（與另兩頁一致）
- 保持三頁之間的 drill-down 導覽正常運作

**Non-Goals:**
- 不引入 Vue Router SPA 架構（三頁仍為獨立 HTML entry）
- 不引入 Pinia 狀態管理（composable 足夠）
- 不重構後端 API 或資料結構
- 不改變 portal iframe 嵌入機制
- 不引入 vue-echarts 套件（直接使用 echarts API，與 QC-GATE 模式一致）

## Decisions

### D1: 三頁保持獨立 entry（不合併為 SPA）

**選擇**：每頁獨立 `index.html` entry point，沿用 QC-GATE/Tables 模式。

**替代方案**：Vue Router SPA 將三頁合併為一個 entry。

**理由**：
- 三頁在 portal iframe 中各自獨立載入，SPA 無法帶來路由切換加速
- 獨立 entry 與既有遷移模式一致，降低風險
- 各頁 bundle 獨立，不會因一頁改動影響其他頁面的快取

### D2: Hold Detail 的 hold_type 判斷移至前端

**選擇**：在前端維護 `NON_QUALITY_HOLD_REASONS` 常數集合（11 個值），從 URL `?reason=` 讀取後在前端判斷。

**替代方案**：新增 API endpoint 回傳 hold_type 分類。

**理由**：
- 集合很小且穩定（11 個非品質原因值）
- 避免新增 API 的維護成本
- Summary API 已回傳足夠資訊，無需額外 round-trip
- 若未來集合需要動態管理，可改為從 config API 載入

### D3: 共用 CSS 提取為 `wip-shared.css`

**選擇**：建立 `frontend/src/wip-shared/styles.css`，包含三頁共用的 `:root` 變數、gradient header、loading overlay、card、button、pagination、responsive breakpoints。各頁 `style.css` 只包含頁面特有樣式，透過 `@import` 引入共用樣式。

**替代方案**：每頁複製一份完整 CSS。

**理由**：
- 三頁 CSS 基底高度重複（`:root` 變數、header、loading overlay、summary card 完全相同）
- 減少維護成本，修改一處即可影響三頁
- Vite 會將 `@import` 合併到各頁 bundle，不增加 HTTP 請求

### D4: Autocomplete 提取為共用 Vue composable

**選擇**：建立 `frontend/src/wip-shared/composables/useAutocomplete.js`，封裝 debounce 搜尋 + cross-filter + dropdown 狀態。Overview 和 Detail 共用。

**理由**：
- 兩頁的 autocomplete 邏輯幾乎相同（4 個欄位、cross-filter、debounce 300ms）
- 現有 `core/autocomplete.js` 提供底層函式，composable 封裝 Vue 反應式狀態
- Hold Detail 不使用 autocomplete，不受影響

### D5: ECharts 直接使用（不引入 vue-echarts）

**選擇**：與 QC-GATE 一致，在 Vue 元件中直接使用 `echarts.init()` + `onMounted`/`onUnmounted` 管理生命週期。

**理由**：
- QC-GATE 已建立此模式且運作良好
- 避免引入額外依賴
- Pareto 圖 click 事件需要 drill-down 到 `/hold-detail`，直接操作更靈活

### D6: Hold Detail Flask route 保持 server-side redirect

**選擇**：`/hold-detail` route 保留 server-side `reason` 參數驗證（缺少時 redirect 到 `/wip-overview`），驗證通過後 `send_from_directory` 回傳靜態 HTML。

**替代方案**：完全移除 server-side 驗證，在前端處理缺少 reason 的情況。

**理由**：
- 保持與現有行為一致（無 reason 時不顯示空白頁面）
- Server-side redirect 比前端 `window.location` 更快
- Blueprint 路由只需小幅修改

### D7: 元件拆分策略

**WIP Overview（App.vue + 5 元件）：**
- `FilterPanel.vue`：4 個 autocomplete 輸入 + filter tags
- `SummaryCards.vue`：2 個 KPI 卡片
- `StatusCards.vue`：4 個可點擊狀態卡片
- `MatrixTable.vue`：Workcenter × Package 交叉表
- `ParetoSection.vue`：Pareto 圖 + 明細表（品質/非品質各一個實例）

**WIP Detail（App.vue + 5 元件）：**
- `FilterPanel.vue`：4 個 autocomplete 輸入（與 Overview 共用 composable）
- `SummaryCards.vue`：5 個狀態 KPI 卡片
- `LotTable.vue`：sticky 欄位 + spec 動態欄 + 分頁
- `LotDetailPanel.vue`：inline 展開式 lot 明細面板
- `Pagination.vue`：分頁控制（可與 Hold Detail 共用）

**Hold Detail（App.vue + 5 元件）：**
- `SummaryCards.vue`：5 個 KPI 卡片
- `AgeDistribution.vue`：4 個可點擊 age 卡片
- `DistributionTable.vue`：Workcenter/Package 分佈表（2 個實例）
- `LotTable.vue`：10 欄 lot 明細表 + filter indicator
- `Pagination.vue`：分頁控制

## Risks / Trade-offs

**[Hold Detail reason redirect] → 前端 fallback**
`send_from_directory` 回傳靜態 HTML 後，前端需在 `onMounted` 中檢查 `URLSearchParams` 是否有 `reason`，若無則 `window.location.href = '/wip-overview'`。Server-side redirect 只在直接 URL 存取時作用，iframe 載入時也需要前端保護。

**[CSS 提取可能遺漏] → 逐頁驗證**
三頁 CSS 雖然高度重複但並非完全相同（如 Hold Detail header 用動態顏色、Detail 有 sticky column 樣式）。提取共用部分時需逐頁視覺驗證，確保沒有遺漏特有樣式。

**[NON_QUALITY_HOLD_REASONS 同步] → 單一來源**
前端維護的 11 個非品質原因值必須與後端 `sql/filters.py` 的 `NON_QUALITY_HOLD_REASONS` 保持一致。可在 `wip-shared/constants.js` 中建立，並在 code review 時交叉比對。

**[三頁同時遷移範圍較大] → 逐頁推進**
1,941 行一次遷移風險較高。實作順序建議：Hold Detail（最簡單 336 行） → Overview（核心頁面 784 行） → Detail（最複雜 821 行），每頁完成後即可獨立測試。
