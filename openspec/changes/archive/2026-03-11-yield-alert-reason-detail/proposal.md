## Why

「查看追溯」按鈕目前僅將使用者跳轉至 reject-history 頁面，無法直接提供原因明細。linkage analyze 步驟（`POST /api/yield-alert/analyze`）從未被前端觸發，導致所有告警列的「映射狀態」永遠顯示 `none`，對使用者毫無意義，且造成誤導。`DW_MES_LOTREJECTHISTORY` 已透過 `PJ_WORKORDER` 欄位與 ERP `WIP_ENTITY_NAME` 建立映射，可直接以 workorder + date 為鍵查詢 MES 報廢明細，無需跳轉。

## What Changes

- 新增 SQL: `yield_alert/reason_detail.sql`，查詢 `DWH.DW_MES_LOTREJECTHISTORY`，以 `PJ_WORKORDER` + `TXNDATE` 為篩選鍵，回傳 LOT 級別報廢明細（CONTAINERNAME、WORKCENTERNAME、LOSSREASONNAME、REJECT_TOTAL_QTY 等）。
- 新增後端 function: `query_reason_detail(workorder, date_bucket)` in `yield_alert_service.py`。
- 新增後端 endpoint: `GET /api/yield-alert/reason-detail`（params: `workorder`, `date_bucket`），直查 Oracle（不依賴 dataset cache）。
- 前端告警表格：
  - 移除「映射狀態」欄位（`match_status` / `match-pill`）。
  - 「查看追溯」改名為「查看原因」。
  - 點擊後 inline 展開該行下方的 MES 報廢明細子表格（不跳轉頁面）。
  - 再次點擊同一行則收合。
- 移除前端已無用的 `drilldownLoadingKey`、`openDrilldown`、`linkageWarning`、`buildDrilldownNotice` import。
- 移除前端對 `navigateToRuntimeRoute` 的使用（僅 drilldown 用到）。
- 後端既有 `/api/yield-alert/drilldown-context` endpoint 與 `execute_linkage_query` 仍保留（不刪除），但前端不再呼叫。

## Capabilities

### New Capabilities
- `yield-alert-reason-detail`: 提供以 workorder + date 為鍵的 MES 報廢明細查詢 API，及前端 inline 展開 UX。

### Modified Capabilities
- `yield-alert-center-api`: 新增 `GET /api/yield-alert/reason-detail` endpoint；既有 drilldown-context endpoint 保留但標記為 unused。
- `yield-alert-center-page`: 告警表格移除 match_status 欄位；「查看追溯」→「查看原因」；新增 inline 展開行為。

## Impact

- **New files**: `src/mes_dashboard/sql/yield_alert/reason_detail.sql`
- **Modified files**:
  - `src/mes_dashboard/services/yield_alert_service.py` — 新增 `query_reason_detail()`
  - `src/mes_dashboard/routes/yield_alert_routes.py` — 新增 endpoint、更新 import
  - `frontend/src/yield-alert-center/App.vue` — 狀態重構、表格欄位調整、inline 展開邏輯
  - `frontend/src/yield-alert-center/style.css` — 展開行樣式
- **Oracle dependency**: `DWH.DW_MES_LOTREJECTHISTORY`（已存在，`_compute_reject_linkage` 使用中）
- **No breaking changes**：既有 drilldown/analyze endpoints 保留；alert row schema 只移除 `match_status` 欄位（純減法）
