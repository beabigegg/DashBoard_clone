## Why

目前專案僅在 `query-tool` 提供偏即時/點查型的報廢資訊，缺少可追蹤趨勢與績效的「報廢歷史」專用報表。資料評估也顯示 `DW_MES_LOTREJECTHISTORY` 同一 `HISTORYMAINLINEID` 會對應多筆原因紀錄，若直接加總 `MOVEINQTY` 會造成分母重複、報廢率失真；同時既有查詢對 reject/defect 命名語義不一致，容易誤解指標。現在應在既有 portal-shell + Vite + route contract 架構下，建立一個語義明確且可治理的歷史報表頁。

## What Changes

- 新增 `報廢歷史查詢` 頁面路由 `/reject-history`，採用既有 pure Vite + portal-shell native route 模式，納入抽屜導航與頁面治理。
- 新增後端 `reject-history` API 群組（摘要 KPI、日/週趨勢、原因 Pareto、明細、匯出），提供前端報表所需資料。
- 新增 `reject-history` service + SQL 模組，建立一致指標定義並明確拆分兩條指標線：
  - 扣帳報廢：`REJECT_TOTAL_QTY = REJECTQTY + STANDBYQTY + QTYTOPROCESS + INPROCESSQTY + PROCESSEDQTY`
  - 不扣帳報廢：`DEFECT_QTY = DEFECTQTY`
- 以事件層級去重規則處理分母（`MOVEIN_QTY` 以 `HISTORYMAINLINEID` 為主鍵去重），避免多原因拆單導致比率失真。
- 明確定義 UI/API/匯出欄位語義，避免沿用「defect=五欄合計」這類歷史命名混淆，確保報表對外語意一致。
- 不變更既有 `query-tool` 現有頁面行為與既有 API 回應欄位（此變更先聚焦新頁能力）。

## Capabilities

### New Capabilities
- `reject-history-page`: 新增報廢歷史查詢頁面，提供篩選、KPI、趨勢、原因分析、明細查詢與匯出。
- `reject-history-api`: 新增報廢歷史 API 能力與資料聚合邏輯，支援報表層的摘要、趨勢、Pareto、明細資料來源。
- `reject-metric-semantics`: 新增 reject/defect 指標語義規範，要求五個 reject 欄位合計與 `DEFECTQTY` 必須分開呈現、分開計算、分開命名。

### Modified Capabilities
- `unified-shell-route-coverage`: 新增 `/reject-history` 後，路由契約清單與前後端契約對照規則需同步更新。
- `vue-vite-page-architecture`: 新頁面需納入 Vite entry/output 與 Flask static HTML 服務規範，保持既有純 Vite 頁治理一致性。
- `field-name-consistency`: reject/defect 相關欄位在 UI、API、匯出命名需維持一致語義，避免跨頁面誤用。

## Impact

- 前端：
  - 新增 `frontend/src/reject-history/`（`App.vue`、`main.js`/`index.html`、components、composables、style）
  - 更新 `frontend/src/portal-shell/nativeModuleRegistry.js`
  - 更新 `frontend/src/portal-shell/routeContracts.js`
  - 更新 `frontend/vite.config.js`
- 後端：
  - 新增 `src/mes_dashboard/routes/reject_history_routes.py`
  - 新增 `src/mes_dashboard/services/reject_history_service.py`
  - 新增 `src/mes_dashboard/sql/reject_history/*.sql`
  - 更新 `src/mes_dashboard/routes/__init__.py`
  - 更新 `src/mes_dashboard/app.py`（`/reject-history` 靜態頁 route）
- 導航/治理：
  - 更新 `data/page_status.json`（drawer 與頁面可見性）
  - 更新 shell route contract 對應治理資產與測試基準
- 測試：
  - 新增 `tests/test_reject_history_service.py`
  - 新增 `tests/test_reject_history_routes.py`
  - 補充 route coverage / contract parity / e2e smoke
- 資料語義：
  - 報表需同時呈現 `REJECT_TOTAL_QTY`（扣帳報廢）與 `DEFECT_QTY`（不扣帳報廢）
  - 不以單一欄位混用兩種語義，避免誤判製程損失
- 依賴：
  - 不新增第三方套件，沿用現有 Flask + Vue + Vite + SQLLoader + QueryBuilder 架構
