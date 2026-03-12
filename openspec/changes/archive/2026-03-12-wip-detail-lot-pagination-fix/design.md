## Context

`wip-detail/App.vue` 中的 `nextPage()` / `prevPage()` 目前呼叫 `loadAllData(false)`，此函式會設定 `tableLoading = true`。`LotTable.vue` 收到 `loading=true` 時以 `v-if` 將整個表格替換為一行 "Loading..." 文字，導致 DOM 高度急劇縮小，觸發瀏覽器將捲動位置重設至頁面頂端。

此外，`loadAllData` 也會一併重新整理 `SummaryCards`（透過 `detailData.summary`），但翻頁時 summary 資料並不需要更新。

已有 `loadTableOnly()` 函式存在，但它同樣設定 `tableLoading = true`，無法解決 layout shift 問題。

## Goals / Non-Goals

**Goals:**
- 點擊 Next/Prev 後頁面捲動位置保持不變
- 翻頁期間表格現有內容保留在 DOM，以輕量 overlay 表示載入中
- 翻頁時不觸發 SummaryCards 重新整理
- 改動範圍最小化，不重構整體資料流

**Non-Goals:**
- 不變更初次載入或 filter apply 的行為（`tableLoading` 隱藏表格在這兩個場景是合理的）
- 不實作前端分頁 cache
- 不改變 API 介面

## Decisions

### 1. 新增 `paginationLoading` 狀態，與 `tableLoading` 分離

**決定：** 在 `App.vue` 新增 `paginationLoading` ref（boolean）。翻頁時只設定 `paginationLoading = true`，不設定 `tableLoading`。

**理由：** `tableLoading` 語意是「表格資料尚不存在，需顯示佔位符」，適用於初次載入與 filter apply。翻頁時資料已存在，需要的是「原地刷新」語意。分離兩個狀態可避免改動現有初次載入流程。

**替代方案（否決）：**
- 在翻頁後儲存並手動還原 `window.scrollY`：hack，對 smooth-scroll 或 async 時序不穩定。
- 在 `loadTableOnly()` 加 flag 跳過 `tableLoading`：修改共用函式，影響其他呼叫端。

### 2. 翻頁使用獨立的 `loadPageData()` 函式

**決定：** 新增 `loadPageData()` 函式，只設定 `paginationLoading`、呼叫 `fetchDetail()`、更新 `detailData`。不設定 `tableLoading`、不觸發 `refreshError`、不更新 `summary`（因為 `detailData` 整體仍替換，但 `SummaryCards` 依賴的 `summary` computed 不會因此消失）。

**備註：** `detailData` 替換後 `summary` computed 會更新。由於翻頁時 summary 實際上不變，這是可接受的輕微 re-render（SummaryCards 不會閃爍，因為值相同）。重點是避免 `tableLoading` 觸發 layout shift。

### 3. LotTable 新增 `paginating` prop，顯示 overlay 而非替換內容

**決定：** `LotTable.vue` 接收 `paginating: Boolean` prop。當 `paginating=true` 時，在 `.table-container` 上加 `paginating` class，以 CSS 顯示半透明遮罩（`opacity: 0.5` + `pointer-events: none`），不改變表格 DOM 結構。`loading` prop 仍控制初次載入的佔位符行為（不變）。

**理由：** 保留表格 DOM 高度，瀏覽器不會重算捲動位置。視覺上使用者能看到目前頁資料仍在，並知道正在載入。

### 4. 翻頁時保留 `selectedLotId` 清除行為

**決定：** `nextPage()` / `prevPage()` 繼續清除 `selectedLotId`。

**理由：** 翻頁後舊的 lotId 不會出現在新頁的列表中，保留高亮沒有意義，且 LotDetailPanel 仍會顯示舊資料容易造成混淆。

## Risks / Trade-offs

- **[Risk] `detailData` 替換仍觸發 SummaryCards re-render** → 因值相同不會有視覺閃爍，可接受。若日後需要最佳化，可將 table data 與 summary data 拆分為獨立 ref。
- **[Risk] `paginationLoading` overlay 期間使用者仍能點擊表格行** → 以 `pointer-events: none` 在 overlay 期間阻止互動。

## Migration Plan

純前端改動，無 API 變更，無需 migration plan。部署後直接生效。
