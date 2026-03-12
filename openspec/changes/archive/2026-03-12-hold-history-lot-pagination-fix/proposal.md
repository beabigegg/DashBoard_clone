## Why

在 hold-history 頁面的 Hold / Release 明細表格中，點擊 Next/Prev 翻頁時，`nextPage()` / `prevPage()` 呼叫 `refreshView({ listOnly: true })`，這會設定 `loading.list = true` 使表格內容被替換為「Loading...」佔位文字，造成頁面高度急劇縮小，瀏覽器因而將捲動位置重設到最上方。此行為與 wip-detail 和 hold-overview 頁面先前修復的問題完全相同，需套用相同的修復模式。

## What Changes

- `nextPage()` 和 `prevPage()` 改為呼叫新的 `refreshViewPage()` 而非 `refreshView({ listOnly: true })`，翻頁時僅設定 `paginationLoading` 而非 `loading.list`
- 新增 `paginationLoading` 狀態，翻頁期間在表格上方顯示半透明 overlay（opacity: 0.5 + pointer-events: none），而非以 `loading.list` 隱藏整個表格內容
- `DetailTable.vue` 新增 `paginating` prop：初次載入時仍顯示 "Loading..." 佔位文字；翻頁時保留表格現有內容並疊加半透明 overlay，防止 layout shift
- 新增 CSS 規則 `.detail-table-wrap.paginating` 於 `style.css`

## Capabilities

### New Capabilities
- (none)

### Modified Capabilities
- `hold-history-page`: 翻頁行為從設定 `loading.list` 隱藏表格改為局部 overlay 更新——保留表格 DOM，頁面捲動位置不變

## Impact

- `frontend/src/hold-history/App.vue` — `nextPage()` / `prevPage()` 邏輯修改；新增 `paginationLoading` 狀態與 `refreshViewPage()` 函數
- `frontend/src/hold-history/components/DetailTable.vue` — 新增 `paginating` prop，翻頁時保留表格 DOM 並疊加 overlay
- `frontend/src/hold-history/style.css` — 新增 `.detail-table-wrap.paginating` CSS 規則
- `openspec/specs/hold-history-page/spec.md` — 更新翻頁行為的 requirement
