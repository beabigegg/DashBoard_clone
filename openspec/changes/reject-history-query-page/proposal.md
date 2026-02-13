## Why

目前專案只有在 `query-tool` 的設備子頁籤提供報廢相關查詢，缺少一個可長期追蹤「報廢歷史」的專用報表頁。隨著既有架構已完成 portal-shell、route contract、Vite 多頁治理，現在適合用同一套架構新增 `報廢歷史查詢`，避免再引入獨立樣式或旁路流程。

## What Changes

- 新增 `報廢歷史查詢` 頁面路由 `/reject-history`，採用既有 pure Vite + portal-shell native route 模式。
- 新增後端 `reject-history` API 群組（摘要、趨勢、原因 Pareto、明細、匯出），提供前端報表所需資料。
- 新增 `reject-history` service + SQL 模組，統一計算：
  - 扣帳報廢：`REJECT_TOTAL_QTY = REJECTQTY + STANDBYQTY + QTYTOPROCESS + INPROCESSQTY + PROCESSEDQTY`
  - 不扣帳報廢：`DEFECT_QTY = DEFECTQTY`
- 將新頁面納入既有導航與契約治理（page registry、drawer、routeContracts、nativeModuleRegistry、shell coverage）。
- 補齊對應測試（API/服務單元測試、route contract 治理測試、必要的頁面整合測試）。

## Capabilities

### New Capabilities
- `reject-history-page`: 新增報廢歷史查詢頁面，提供篩選、KPI、趨勢、原因分析與明細查詢/匯出。
- `reject-history-api`: 新增報廢歷史 API 能力與資料聚合邏輯，定義扣帳報廢與不扣帳報廢的並列指標語義。

### Modified Capabilities
- `unified-shell-route-coverage`: 新增 `/reject-history` 後，路由契約清單與前後端契約對照規則需同步更新。
- `vue-vite-page-architecture`: 新頁面需納入 Vite entry/output 與 Flask static HTML 服務規範，保持既有純 Vite 頁治理一致性。

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
- 依賴：
  - 不新增第三方套件，沿用現有 Flask + Vue + Vite + SQLLoader + QueryBuilder 架構
