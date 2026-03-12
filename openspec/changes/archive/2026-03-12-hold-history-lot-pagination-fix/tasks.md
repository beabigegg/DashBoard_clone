## 1. App.vue — 翻頁邏輯改寫

- [x] 1.1 在 `App.vue` 新增 `paginationLoading` ref（`const paginationLoading = ref(false)`）
- [x] 1.2 新增 `refreshViewPage()` 函式：設定 `paginationLoading = true`、呼叫 GET /view API（僅帶 list 相關參數）、更新 `detailData`、`finally` 設回 `false`（不設定 `loading.list`、不設定 `loading.global`）
- [x] 1.3 修改 `nextPage()`：移除 `void refreshView({ listOnly: true })`，改呼叫 `void refreshViewPage()`
- [x] 1.4 修改 `prevPage()`：移除 `void refreshView({ listOnly: true })`，改呼叫 `void refreshViewPage()`
- [x] 1.5 將 `paginationLoading` 作為 `paginating` prop 傳入 `DetailTable`

## 2. DetailTable.vue — Overlay 顯示

- [x] 2.1 新增 `paginating` prop（`type: Boolean, default: false`）
- [x] 2.2 在 `.detail-table-wrap` 加上 `:class="{ paginating: paginating }"` binding

## 3. style.css — Pagination CSS 規則

- [x] 3.1 在 `hold-history/style.css` 新增 `.detail-table-wrap.paginating` CSS 規則：`opacity: 0.5; pointer-events: none;`

## 4. 手動驗證

- [x] 4.1 翻頁後確認頁面捲動位置保持不變
- [x] 4.2 翻頁期間確認表格列保留在 DOM（半透明），不顯示 "Loading..." 佔位符
- [x] 4.3 翻頁後確認 SummaryCards、DailyTrend、ReasonPareto、DurationChart 沒有閃爍或重新載入的現象
- [x] 4.4 初次載入與 filter apply 確認仍正常顯示 "Loading..." 佔位符（未受影響）
