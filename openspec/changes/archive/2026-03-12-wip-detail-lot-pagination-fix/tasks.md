## 1. App.vue — 翻頁邏輯改寫

- [x] 1.1 在 `App.vue` 新增 `paginationLoading` ref（`const paginationLoading = ref(false)`）
- [x] 1.2 新增 `loadPageData()` 函式：設定 `paginationLoading = true`、呼叫 `fetchDetail()`、更新 `detailData`、`finally` 設回 `false`（不設定 `tableLoading`、不設定 `refreshError`）
- [x] 1.3 修改 `nextPage()`：移除 `void loadAllData(false)`，改呼叫 `void loadPageData()`
- [x] 1.4 修改 `prevPage()`：移除 `void loadAllData(false)`，改呼叫 `void loadPageData()`
- [x] 1.5 將 `paginationLoading` 作為 `paginating` prop 傳入 `LotTable`

## 2. LotTable.vue — Overlay 顯示

- [x] 2.1 新增 `paginating` prop（`type: Boolean, default: false`）
- [x] 2.2 在 `.table-container` 加上 `:class="{ paginating: paginating }"` binding
- [x] 2.3 在 `wip-detail/style.css`（或 `wip-shared/styles.css`）的 `.theme-wip-detail` scope 下新增 `.table-container.paginating` CSS 規則：`opacity: 0.5; pointer-events: none; position: relative`

## 3. 手動驗證

- [x] 3.1 翻頁後確認頁面捲動位置保持不變
- [x] 3.2 翻頁期間確認表格列保留在 DOM（半透明），不顯示 "Loading..." 佔位符
- [x] 3.3 翻頁後確認 SummaryCards 數字沒有閃爍或重新載入的現象
- [x] 3.4 初次載入與 filter apply 確認仍正常顯示 "Loading..." 佔位符（未受影響）
