## Why

在 wip-detail 頁面的 Lot Details 表格中，點擊 Next/Prev 翻頁時，`nextPage()` / `prevPage()` 呼叫 `loadAllData(false)`，這會設定 `tableLoading = true` 使表格內容被替換為「Loading...」文字，造成頁面高度急劇縮小，瀏覽器因而將捲動位置重設到最上方。此行為嚴重影響使用體驗，尤其當使用者在表格下方的 LotDetailPanel 查看資料後進行翻頁時。

## What Changes

- `nextPage()` 和 `prevPage()` 改為呼叫 `loadTableOnly()` 而非 `loadAllData(false)`，翻頁時不觸發全頁資料刷新（避免不必要地重新整理 SummaryCards）
- 新增 `paginationLoading` 狀態，翻頁期間在表格上方顯示輕量 overlay（半透明遮罩），而非以 `tableLoading` 隱藏整個表格內容
- `LotTable.vue` 的 loading 邏輯改為：初次載入時隱藏表格顯示 "Loading..."；翻頁時保留表格現有內容並疊加半透明 overlay，防止 layout shift
- 翻頁時不重設 `selectedLotId`（保持 LotDetailPanel 的顯示狀態）

## Capabilities

### New Capabilities
- (none)

### Modified Capabilities
- `wip-detail-page`: 翻頁行為從全頁刷新改為局部更新——只更新 LotTable 資料，頁面捲動位置與 SummaryCards 保持不變

## Impact

- `frontend/src/wip-detail/App.vue` — `nextPage()` / `prevPage()` 邏輯修改；新增 `paginationLoading` 狀態
- `frontend/src/wip-detail/components/LotTable.vue` — 新增 `paginating` prop，loading 時保留表格 DOM 並疊加 overlay
- `openspec/specs/wip-detail-page/spec.md` — 更新翻頁行為的 requirement
