## Context

`hold-overview/App.vue` 中的 `nextPage()` / `prevPage()` 呼叫 `loadLots()`，此函式設定 `lotsLoading = true`。`LotTable.vue` 收到 `loading=true` 時以 `v-if` 將整個表格替換為 "Loading..." 佔位文字，導致 DOM 高度急劇縮小，觸發瀏覽器將捲動位置重設至頁面頂端。

此問題與 wip-detail 頁面先前修復的問題完全相同（參見 `archive/2026-03-12-wip-detail-lot-pagination-fix`），可直接套用相同的修復模式。

## Goals / Non-Goals

**Goals:**
- 點擊 Next/Prev 後頁面捲動位置保持不變
- 翻頁期間表格現有內容保留在 DOM，以輕量 overlay 表示載入中
- 翻頁時不觸發 summary、matrix、hold（pareto）等上方區塊的重新整理
- 改動範圍最小化，套用已驗證的 wip-detail 修復模式

**Non-Goals:**
- 不變更初次載入或 filter apply 的行為（`lotsLoading` 隱藏表格在這些場景是合理的）
- 不實作前端分頁 cache
- 不改變 API 介面

## Decisions

### 1. 新增 `paginationLoading` 狀態，與 `lotsLoading` 分離

**決定：** 在 `App.vue` 新增 `paginationLoading` ref（boolean）。翻頁時只設定 `paginationLoading = true`，不設定 `lotsLoading`。

**理由：** `lotsLoading` 語意是「lot 資料尚不存在，需顯示佔位符」，適用於初次載入與 filter apply。翻頁時資料已存在，需要的是「原地刷新」語意。與 wip-detail 的 `tableLoading` / `paginationLoading` 分離模式一致。

**替代方案（否決）：**
- 在翻頁後手動還原 `window.scrollY`：hack，對 smooth-scroll 或 async 時序不穩定。
- 在 `loadLots()` 加 flag 跳過 `lotsLoading`：修改共用函式，影響 filter apply 等其他呼叫端。

### 2. 翻頁使用獨立的 `loadLotsPage()` 函式

**決定：** 新增 `loadLotsPage()` 函式，只設定 `paginationLoading`、呼叫 `fetchLots()`、更新 lots 資料。不設定 `lotsLoading`、不觸發其他區塊刷新。

**理由：** 與 `loadLots()` 分離，避免影響 filter apply、matrix click 等場景的現有行為。

### 3. LotTable 新增 `paginating` prop，顯示 overlay 而非替換內容

**決定：** `LotTable.vue` 接收 `paginating: Boolean` prop。當 `paginating=true` 時，在 `.table-container` 上加 `paginating` class，以 CSS 顯示半透明遮罩（`opacity: 0.5` + `pointer-events: none`），不改變表格 DOM 結構。`loading` prop 仍控制初次載入的佔位符行為（不變）。

**理由：** 保留表格 DOM 高度，瀏覽器不會重算捲動位置。與 wip-detail 的修復方式一致。

## Risks / Trade-offs

- **[Risk] `paginationLoading` overlay 期間使用者仍能捲動或操作其他區塊** → overlay 僅覆蓋 `.table-container`，以 `pointer-events: none` 阻止表格互動，其他區塊不受影響，這是預期行為。
- **[Risk] CSS 規則未正確 scope 到 `.theme-hold-overview`** → 將規則置於 `hold-overview/style.css` 並確認在 `.theme-hold-overview` scope 下。

## Migration Plan

純前端改動，無 API 變更，無需 migration plan。部署後直接生效。
