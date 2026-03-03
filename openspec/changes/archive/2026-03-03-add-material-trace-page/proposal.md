## Why

生產追溯過程中，工程師需要查詢「某個 LOT/工單在哪個站群組用了什麼原物料」以及「某批原物料被哪些 LOT 使用」。目前原物料消耗資訊散落在 Query Tool 的 LotDetail "原物料" tab 中，只能逐筆 LOT 查看，無法批量查詢或反向追溯。缺少專屬頁面讓原物料異常時的影響範圍評估非常耗時。

## What Changes

- 新增「原物料追溯查詢」獨立頁面，提供雙向查詢能力：
  - **正向查詢**：輸入 LOT ID 或工單號碼（多筆），查詢對應的原物料消耗記錄，可依站群組篩選
  - **反向查詢**：輸入原物料批號 MATERIALLOTNAME（多筆），查詢該批原物料被哪些 LOT 使用
- 結果表格含分頁、站群組篩選、CSV 匯出
- 後端新增 `/api/material-trace/query` 和 `/api/material-trace/export` API 端點
- 查詢資料來源：`DWH.DW_MES_LOTMATERIALSHISTORY`（1800 萬筆），利用既有索引（CONTAINERID, PJ_WORKORDER, MATERIALLOTNAME）
- 站群組對應透過 `filter_cache.get_workcenter_mapping()` 解析（與設備歷史績效共用同一份 mapping）

## Capabilities

### New Capabilities

- `material-trace-page`: 原物料追溯查詢頁面 — 前端 UI、查詢模式切換、結果表格、分頁、CSV 匯出
- `material-trace-api`: 原物料追溯 API — 正向/反向查詢端點、輸入驗證、結果分頁、匯出端點、rate limiting

### Modified Capabilities

（無既有 spec 需修改）

## Impact

- **新增後端服務** — `src/mes_dashboard/services/material_trace_service.py`：正向/反向查詢邏輯、站群組 enrichment
- **新增後端路由** — `src/mes_dashboard/routes/material_trace_routes.py`：API 端點註冊
- **新增 SQL** — `src/mes_dashboard/sql/material_trace/`：3 個查詢檔（forward_by_lot、forward_by_workorder、reverse_by_material_lot）
- **新增前端頁面** — `frontend/src/material-trace/`：App.vue + 子元件（FilterPanel、ResultTable）
- **新增前端入口** — `frontend/material-trace.html` + Vite entry
- **共用依賴** — `filter_cache.get_workcenter_mapping()` 提供站群組對應、`parseMultiLineInput()` 處理多筆輸入
- **資料庫** — 查詢 `DWH.DW_MES_LOTMATERIALSHISTORY`，使用既有索引，無 schema 變更
- **Sidebar** — 需在導覽列新增頁面入口
