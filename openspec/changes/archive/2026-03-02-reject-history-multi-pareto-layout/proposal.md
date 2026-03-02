## Why

目前報廢歷史的柏拉圖一次只顯示一個維度，需透過下拉選單切換，無法同時看到跨維度的分佈與交叉關係。改為同時顯示 6 個柏拉圖（3×2 grid），並支援跨圖即時聯動篩選——點擊任一柏拉圖的項目後，其餘 5 個柏拉圖即時重新計算（排除自身維度的篩選），下方明細表則套用所有維度的篩選結果。

## What Changes

### 前端
- 移除維度切換下拉選單（`ParetoSection.vue` 的 dimension selector）
- 新增 `ParetoGrid.vue` 元件，以 3 欄 grid 同時渲染 6 個獨立柏拉圖（不良原因、PACKAGE、TYPE、WORKFLOW、站點、機台）
- 每個柏拉圖支援多選（現有行為），點擊後即時聯動：
  - 其他 5 個柏拉圖重新計算（套用來自其他維度的選取，但不套用自身維度的選取）
  - 明細表套用所有 6 個維度的選取結果
- 選取狀態以 chip 顯示在明細表上方，按維度分組

### 後端
- 新增批次柏拉圖 API endpoint（`GET /api/reject-history/batch-pareto`），對快取中的 Pandas DataFrame 進行重算，一次回傳 6 個維度的柏拉圖資料（不重查 Oracle 資料庫）
- 每個維度的計算套用「排除自身」的交叉篩選邏輯：計算 Reason Pareto 時套用其他 5 維度的選取，但不套用 Reason 自身的選取
- 移除前端 client-side 的 reason Pareto 計算（統一由後端從快取計算）

### 移除
- 移除維度切換選單和 `onDimensionChange` 邏輯
- 移除現有的單維度 `fetchDimensionPareto` 流程

### 保留
- 保留 TOP20/全部顯示切換功能（TYPE、WORKFLOW、機台維度在 80% 過濾後仍可能有大量項目，TOP20 截斷對使用者仍有價值）

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `reject-history-api`: 新增批次柏拉圖 endpoint，支援跨維度交叉篩選
- `reject-history-page`: 柏拉圖從單維度切換改為 6 圖同時顯示 + 即時聯動

## Impact

- 前端：`App.vue`（狀態管理重構）、`ParetoSection.vue`（改為純展示元件）、新增 `ParetoGrid.vue`
- 後端：`reject_dataset_cache.py`（新增批次計算，資料來源為快取的 Pandas DataFrame）、`reject_history_routes.py`（新增 endpoint）
- API：新增 `GET /api/reject-history/batch-pareto` endpoint（cache-only，不查 Oracle）
- 無資料庫/SQL 變更
