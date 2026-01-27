## Why

目前 WIP Dashboard 的資料欄位與查詢邏輯與 IT 部門提供的 Power BI 標準定義不一致。IT 提供了 `DW_PJ_LOT_V` 的標準 SQL 欄位定義與 WIP Status 判斷邏輯，需要對齊以確保：
1. 資料定義一致性 - 與其他報表系統使用相同的欄位名稱與計算邏輯
2. WIP 狀態分類標準化 - 使用 IT 定義的 RUN/HOLD/QUEUE 三態分類
3. 提供主管更清楚的 WIP 狀態分布視覺化

## What Changes

- 採用 IT Power BI 的 WIP Status 三態判斷邏輯：
  - `RUN`: EquipmentCount > 0（在機台上運行中）
  - `HOLD`: EquipmentCount = 0 AND CurrentHoldCount > 0（暫停中）
  - `QUEUE`: EquipmentCount = 0 AND CurrentHoldCount = 0（等待中）
- 新增 IT SQL 中定義的欄位到 API 回傳（使用 camelCase）
- 前端顯示使用 IT 定義的正確名稱（如 "Run Card Lot ID"）
- Summary API 新增 `byWipStatus` 分組統計（每個狀態的 lots 數與 qty）
- 前端 WIP Overview 新增 RUN/QUEUE/HOLD 狀態卡片，lots 與 qty 數字同大顯示
- 保留現有的 `LOTID NOT LIKE '%DUMMY%'` 全域過濾條件

## Capabilities

### New Capabilities

- `wip-status-calculation`: WIP Status 三態計算邏輯（RUN/HOLD/QUEUE），基於 EquipmentCount 與 CurrentHoldCount 欄位判斷

### Modified Capabilities

- `wip-data-service`: 修改 WIP 查詢服務，新增 IT 定義的欄位、WIP Status 計算、Summary 分組統計
- `wip-overview`: 修改 WIP Overview 前端頁面，新增 WIP Status 狀態卡片顯示

## Impact

- **後端服務**: `wip_service.py`
  - 新增 WIP Status 計算邏輯到查詢
  - Summary API 新增 byWipStatus 分組回傳
  - Detail API 新增 IT 定義的欄位

- **後端路由**: `wip_routes.py`
  - 調整 API 回傳格式（camelCase 欄位名）

- **前端頁面**: `wip_overview.html`
  - 移除 Hold Lots / Hold QTY 兩個 KPI 卡片
  - 新增 RUN / QUEUE / HOLD 三個狀態卡片
  - 狀態卡片顯示 lots 數與 qty 數（同樣字體大小）

- **資料庫**: 無結構變更
  - 使用現有的 `DWH.DW_PJ_LOT_V` view
  - 新增查詢欄位：EQUIPMENTCOUNT, CURRENTHOLDCOUNT, QTY2 等
