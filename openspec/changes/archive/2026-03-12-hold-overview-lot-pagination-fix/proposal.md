## Why

在 hold-overview 頁面的 Lot Details 表格中，點擊 Next/Prev 翻頁時，`nextPage()` / `prevPage()` 呼叫 `loadLots()`，這會設定 `lotsLoading = true` 使表格內容被替換為「Loading...」佔位文字，造成頁面高度急劇縮小，瀏覽器因而將捲動位置重設到最上方。此行為與 wip-detail 頁面先前修復的問題完全相同，需套用相同的修復模式。

## What Changes

- `nextPage()` 和 `prevPage()` 改為呼叫新的 `loadLotsPage()` 而非 `loadLots()`，翻頁時僅設定 `paginationLoading` 而非 `lotsLoading`
- 新增 `paginationLoading` 狀態，翻頁期間在表格上方顯示半透明 overlay（opacity: 0.5 + pointer-events: none），而非以 `lotsLoading` 隱藏整個表格內容
- `LotTable.vue` 新增 `paginating` prop：初次載入時仍顯示 "Loading..." 佔位文字；翻頁時保留表格現有內容並疊加半透明 overlay，防止 layout shift
- 新增 CSS 規則 `.table-container.paginating` 於 `style.css`

## Capabilities

### New Capabilities
- (none)

### Modified Capabilities
- `hold-overview-page`: 翻頁行為從設定 `lotsLoading` 隱藏表格改為局部 overlay 更新——保留表格 DOM，頁面捲動位置不變

## Impact

- `frontend/src/hold-overview/App.vue` — `nextPage()` / `prevPage()` 邏輯修改；新增 `paginationLoading` 狀態與 `loadLotsPage()` 函數
- `frontend/src/hold-overview/components/LotTable.vue` — 新增 `paginating` prop，翻頁時保留表格 DOM 並疊加 overlay
- `frontend/src/hold-overview/style.css` — 新增 `.table-container.paginating` CSS 規則
- `openspec/specs/hold-overview-page/spec.md` — 更新翻頁行為的 requirement
