## 1. App.vue — 翻頁邏輯改寫

- [x] 1.1 在 `App.vue` 新增 `paginationLoading` ref（`const paginationLoading = ref(false)`）
- [x] 1.2 新增 `loadLotsPage()` 函式：設定 `paginationLoading = true`、呼叫 `fetchLots()`、更新 lots 資料、`finally` 設回 `false`（不設定 `lotsLoading`）
- [x] 1.3 修改 `nextPage()`：移除 `loadLots()` 呼叫，改呼叫 `loadLotsPage()`
- [x] 1.4 修改 `prevPage()`：移除 `loadLots()` 呼叫，改呼叫 `loadLotsPage()`
- [x] 1.5 將 `paginationLoading` 作為 `paginating` prop 傳入 `LotTable`

## 2. LotTable.vue — Overlay 顯示

- [x] 2.1 新增 `paginating` prop（`type: Boolean, default: false`）
- [x] 2.2 在 `.table-container` 加上 `:class="{ paginating: paginating }"` binding

## 3. style.css — Pagination CSS 規則

- [x] 3.1 在 `hold-overview/style.css` 的 `.theme-hold-overview` scope 下新增 `.table-container.paginating` CSS 規則：`opacity: 0.5; pointer-events: none;`

## 4. 手動驗證

- [x] 4.1 翻頁後確認頁面捲動位置保持不變
- [x] 4.2 翻頁期間確認表格列保留在 DOM（半透明），不顯示 "Loading..." 佔位符
- [x] 4.3 初次載入與 filter apply 確認仍正常顯示 "Loading..." 佔位符（未受影響）
- [x] 4.4 Matrix click / TreeMap click 後的 lot 刷新確認仍使用 `lotsLoading` 行為（未受影響）
