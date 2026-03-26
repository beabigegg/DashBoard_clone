## Why

WIP 即時概況目前使用文字輸入搭配動態 autocomplete，使用者在多條件查詢時容易反覆輸入且選項不一致。改為可搜尋的下拉清單並新增 Wafer 維度篩選，可降低操作成本、提升查詢一致性，且能直接利用既有快取資料來源。

## What Changes

- 將 WIP 即時概況篩選 UI 從文字 autocomplete 改為可模糊搜尋的下拉清單（對齊設備即時概況機台篩選互動）
- 新增兩個篩選欄位：`Wafer LOT`（資料欄位 `FIRSTNAME`）、`Wafer Type`（資料欄位 `WAFERDESC`）
- 新增 WIP 篩選選項 API，一次回傳舊有與新增篩選欄位的候選值，優先由 WIP 快取衍生索引提供
- WIP 概況查詢 API（summary/matrix/hold）納入 `firstname`、`waferdesc` 參數
- 前端初始化階段預先載入篩選選項（不需先觸發主查詢才有下拉選項）

## Capabilities

### New Capabilities

_(none)_

### Modified Capabilities

- `wip-overview-page`: 篩選互動改為可搜尋下拉並新增 Wafer 維度篩選，且篩選選項由快取驅動

## Impact

- **Frontend**
  - `frontend/src/wip-overview/App.vue`
  - `frontend/src/wip-overview/components/FilterPanel.vue`
  - `frontend/src/wip-overview/style.css`
  - `frontend/src/core/wip-derive.js`
  - `frontend/tests/wip-derive.test.js`
- **Backend**
  - `src/mes_dashboard/routes/wip_routes.py`
  - `src/mes_dashboard/services/wip_service.py`
  - `tests/test_wip_routes.py`
  - `tests/test_wip_service.py`
- **No breaking route removal**: 既有 API 與參數仍保持相容，新增參數採選填。
