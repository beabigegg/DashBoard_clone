## Context

`WIP 即時概況` 現在使用 4 個文字輸入框（WORKORDER/LOT ID/PACKAGE/TYPE）搭配 `/api/wip/meta/search` 即時建議。此模式在多條件操作時需要頻繁輸入，且首次進頁不會先拿到完整候選值。需求要改成可模糊搜尋的下拉清單，並新增 `FIRSTNAME`、`WAFERDESC` 兩個篩選維度，且篩選選項來源以快取為主。

## Goals / Non-Goals

**Goals**

- 將 WIP 概況篩選改成下拉可搜尋（參考設備即時概況「機台」篩選互動）
- 新增 `Wafer LOT(FIRSTNAME)`、`Wafer Type(WAFERDESC)` 篩選
- 所有篩選候選值可由快取一次取得，並支援首次載入預先填充
- 既有 summary/matrix/hold 查詢都能吃到新舊篩選條件

**Non-Goals**

- 不改 WIP Detail 頁面的篩選 UI（仍維持現有 autocomplete）
- 不移除既有 `/api/wip/meta/search`（保留向下相容）
- 不變更 WIP 指標計算邏輯（僅改篩選方式與欄位）

## Decisions

### D1: 新增 `GET /api/wip/meta/filter-options` 做「一次取齊」篩選選項

API 回傳：
- `workorders`
- `lotids`
- `packages`
- `types`
- `firstnames`
- `waferdescs`

資料來源優先順序：
1. WIP 快取衍生搜尋索引（`_get_wip_search_index`）
2. WIP 快取快照（必要時）
3. Oracle fallback（僅快取不可用時）

此設計讓前端在第一次查詢前就能載入完整下拉選項。

### D2: WIP 概況前端篩選改採 `MultiSelect`（可搜尋）

`frontend/src/wip-overview/components/FilterPanel.vue` 改為使用 `resource-shared/components/MultiSelect.vue`：
- 6 個篩選欄位皆為可搜尋下拉
- 支援多選（內部值為陣列）
- 顯示 active chips，移除 chip 會觸發重查

### D3: 篩選參數以 CSV 傳遞，服務層統一解析

API query 維持既有參數名稱（`workorder`, `lotid`, `package`, `type`）並新增：
- `firstname`
- `waferdesc`

多選由前端以逗號串接傳遞。服務層新增 CSV 解析 helper，將單值/多值統一轉成條件。

### D4: 搜尋索引與快照索引擴充 Wafer 欄位

`wip_service` 的衍生索引加入：
- `FIRSTNAME`
- `WAFERDESC`

確保：
- `meta/filter-options` 可直接由索引取值
- summary/matrix/hold 可在快取路徑下高效套用 Wafer 篩選

## Risks / Trade-offs

- **參數長度風險**：多選過多時 URL 長度增加；目前以一般 dashboard 操作量可接受。
- **跨頁一致性**：WIP Detail 未同步改成新 UI；但後端先支持新欄位，避免 overview drilldown 失真。
- **快取不可用場景**：filter-options 需 fallback 查詢，首次延遲可能上升。

## Validation Plan

- 單元測試：
  - `tests/test_wip_routes.py`：新增 `meta/filter-options` 與新參數傳遞驗證
  - `tests/test_wip_service.py`：新增 filter-options 來源與新欄位索引輸出驗證
  - `frontend/tests/wip-derive.test.js`：CSV/新欄位 query 參數組裝驗證
- 手動驗證：
  - 進入 `/wip-overview`，首次不查主資料也能看到下拉選項
  - 套用任一新舊篩選後 summary/matrix/hold 都一致變化
  - 下拉框可模糊搜尋、可多選、可清除
