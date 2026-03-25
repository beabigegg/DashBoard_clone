## 0. Contract 先行校準（先做）

- [x] 0.1 統一 API 成功契約為 `{ success: true, data: ... }`，並在 route/service 實作中使用專案既有 response helpers，避免 `status: success` 舊格式混入。
- [x] 0.2 明確定義錯誤契約：validation error（400）、dataset expired（410, `dataset_expired`）、heavy-query overload（503 + `Retry-After` + `heavy_query_overloaded`）、memory guard overload（503 + `memory_guard_rejected`）。
- [x] 0.3 明確定義 filter 契約：`/page` 與 `/matrix` 共同使用 `{ workcenter_group, spec, equipment_id }`；`/export` 以平面 query params 傳遞相同語義（不使用巢狀 JSON query string）。
- [x] 0.4 定義 dataset 生命週期：query 回傳 TTL/expire meta；view 端點遇到過期 dataset 必須回 410 並提示前端重查。
- [x] 0.5 定義日期語義：`end_date_exclusive`（end_date + 1 day at 00:00）與 Asia/Taipei 時區處理規則。

## 1. Backend: SQL + Service 核心

- [x] 1.1 新增 `src/mes_dashboard/sql/production_history/main_query.sql`，實作主查詢 SQL（CONTAINER JOIN LOTWIPHISTORY + GROUP BY + 動態 WHERE placeholder）。
- [x] 1.2 新增 `src/mes_dashboard/services/production_history_service.py`，實作 `query_production_history` 主函式：參數驗證、QueryBuilder 組裝、`decompose_by_time_range` 時間分段、`execute_plan` 逐 chunk Oracle 查詢（含 chunk query function `_run_history_chunk`）、`merge_chunks_to_spool` 串流合併寫 Parquet、`register_spool_file` 註冊 spool、DuckDB 計算首頁結果 + Matrix 摘要。
- [x] 1.3 在 service 中實作 `_resolve_lot_ids_with_trace`，複用現有 `_trace_parents_for_equipment` 的 split chain trace 邏輯處理 LOT ID 輸入，並加上 max-depth / cycle guard。
- [x] 1.4 新增 `src/mes_dashboard/services/production_history_sql_runtime.py`，實作 DuckDB over Parquet 的衍生查詢：`compute_detail_page`（分頁）、`compute_matrix_summary`（三層聚合 + 月份計數）、`stream_export`（全量 CSV）。

## 2. Backend: 重查詢保護 + Feature Flags

- [x] 2.1 在 service 主查詢入口加入 `acquire_heavy_query_slot` / `release_heavy_query_slot` 全域並行控制（最多 3 slot）。
- [x] 2.2 chunk query function `_run_history_chunk` 使用 `read_sql_df_slow`（慢查詢連線池 + 信號量 + timeout）。
- [x] 2.3 新增 feature flags：`PROD_HISTORY_SQL_VIEW_ENABLED`、`PROD_HISTORY_ASYNC_ENABLED`（預留）、`PROD_HISTORY_ENGINE_GRAIN_DAYS`、`PROD_HISTORY_MAX_ROWS_PER_CHUNK`、`PROD_HISTORY_MAX_DATE_RANGE_DAYS`。
- [x] 2.4 在 `heavy_query_telemetry.py` 記錄 production-history 路由的 guard_reject / memory_error 計數；在端點中呼叫 `record_query_latency()`。

## 3. Backend: Routes + 註冊

- [x] 3.1 新增 `src/mes_dashboard/routes/production_history_routes.py`，實作 Blueprint `production_history_bp`（prefix `/api/production-history`），包含 `POST /query`、`POST /page`、`POST /matrix`、`GET /export` 四個端點。
- [x] 3.2 在 `src/mes_dashboard/routes/__init__.py` 中 import 並 register `production_history_bp`。
- [x] 3.3 更新 `contract/api_inventory.md`，新增 production-history 端點群組與成功/失敗契約說明。

## 4. Frontend: 頁面結構 + 元件

- [x] 4.1 建立 `frontend/src/production-history/` 目錄結構：`App.vue`、`main.js`、`style.css`。
- [x] 4.2 實作 `App.vue` 主頁面：篩選列（Type/日期必填 + 工單/Package/BOP/WC/EQP 可選）、查詢按鈕、上方 Matrix + 下方 TABLE 版面。
- [x] 4.3 實作 `components/ProductionMatrix.vue`：三層展開（WC Group → Spec → Equipment）、動態月份欄位、計數顯示、節點點選聯動。
- [x] 4.4 實作 `components/ProductionDetailTable.vue`：明細欄位（LotID/Pkg/BOP/Type/WaferLot/WC/Spec/EQP/TrackIn/TrackOut/InQTY/OutQTY）、交替行色、25/page 分頁、匯出按鈕。
- [x] 4.5 實作 `composables/useProductionHistory.js`：管理查詢狀態（loading/error/dataset_id）、呼叫 API（query/page/matrix/export）、Matrix 聯動過濾邏輯。
- [x] 4.6 前端處理 dataset 過期（410）與 overload（503）提示：顯示可重試訊息、必要時引導重新查詢。

## 5. Frontend: 路由註冊 + 樣式

- [x] 5.1 在 `nativeModuleRegistry.js` 新增 `/production-history` entry。
- [x] 5.2 在 `routeContracts.js` 新增路由契約（routeId: `production-history`, title: `生產歷程查詢`, renderMode: `native`）。
- [x] 5.3 在 `IN_SCOPE_REPORT_ROUTES` 新增 `/production-history`。
- [x] 5.4 實作 `style.css`，scope 在 `.theme-production-history` 下，包含 Matrix 展開樣式與 detail table 樣式。

## 6. 測試與契約驗證

- [x] 6.1 新增後端測試 `tests/test_production_history_routes.py`，覆蓋主查詢、分頁、Matrix、匯出端點。
- [x] 6.2 補齊錯誤契約測試：400 validation、410 dataset expired、503 heavy-query/memory overload（含 Retry-After）。
- [x] 6.3 補齊 filter 契約測試：`/page` 與 `/matrix` filter schema 一致、`/export` query 參數對應一致。
- [x] 6.4 補齊 trace guard 測試：max-depth、cycle 檢測與錯誤回應。
- [x] 6.5 更新 `contract/css_inventory.md`，新增 `production-history/style.css` 條目。
- [ ] 6.6 端對端驗證：前端完整流程（查詢 → Matrix 點選 → 分頁 → 匯出）與 dataset 過期重查流程。
