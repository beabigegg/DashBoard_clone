## Why

WIP Dashboard 目前缺乏有效的篩選機制，使用者無法快速定位特定的 Lot 或 Work Order。此外，資料中包含 DUMMY lot（測試用途），會干擾實際生產數據的分析。需要增強篩選功能以提升使用者體驗與數據準確性。

## What Changes

- 預設排除 LOT ID 包含 "DUMMY" 的資料（適用於所有 WIP 查詢）
- 新增 WORKORDER 篩選器，支援模糊搜尋與下拉選單
- 新增 LOT ID 篩選器，支援模糊搜尋與下拉選單
- 頁面載入時預載選項清單供下拉選單使用
- 提供輸入框讓使用者透過模糊搜尋快速找出特定 LOT 或 WORKORDER

## Capabilities

### New Capabilities

- `wip-advanced-filter`: WIP 進階篩選功能，包含 WORKORDER 與 LOT ID 的模糊搜尋、預設 DUMMY 排除、autocomplete 下拉選單

### Modified Capabilities

- `wip-service`: 修改現有 WIP 查詢服務，加入 DUMMY 排除邏輯與新篩選參數支援

## Impact

- **後端服務**: `wip_service.py` - 修改所有查詢函數加入 DUMMY 排除，新增 `get_workorders()` 與 `get_lot_ids()` API
- **後端路由**: `wip_routes.py` - 新增 meta API 端點
- **前端頁面**: `wip_overview.html`, `wip_detail.html` - 新增篩選器 UI 與 autocomplete 元件
- **資料庫**: 無結構變更，僅查詢邏輯調整
