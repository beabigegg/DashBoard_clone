## Phase 1: Baseline 與契約對齊

- [ ] 1.1 建立重查詢頁面基線清單與現況矩陣（Query Tool / Trace / Reject / Material Trace / Yield Alert）
- [ ] 1.2 定義統一 overload 回應契約（status code、error code、retry headers、meta 欄位）
- [x] 1.3 補齊 `.env.example` heavy-query 參數（含 `QUERY_TOOL_RSS_REJECT_MB`）並文件化預設值

## Phase 2: Query Tool DuckDB/spool 降級

- [x] 2.1 新增 `src/mes_dashboard/services/query_tool_sql_runtime.py`（DuckDB on parquet spool）
- [x] 2.2 `get_lot_history_batch()` 導入 spool/DuckDB-first，pandas 為 fallback
- [x] 2.3 `get_lot_associations_batch()` 導入 spool/DuckDB-first，pandas 為 fallback
- [x] 2.4 RSS guard 改為「可降級優先」流程（可用 cache/spool 時不直接 reject）
- [x] 2.5 對低良率相關輸出套用 `WORKCENTER_GROUP` 彙整與 reject policy filter 對齊

## Phase 3: 其他重查詢頁面一致化

- [x] 3.1 `trace_routes.py`：sync guard 命中時優先轉 async job（可用時）
- [x] 3.2 `material_trace_routes.py`：`MemoryError` 由 400 改為 503 + Retry-After
- [x] 3.3 `reject_history_routes.py`：RSS/front-door reject 回應格式對齊統一契約
- [ ] 3.4 `yield_alert_routes.py`：overload meta/headers 與統一契約對齊

## Phase 4: 共用元件與觀測

- [ ] 4.1 新增共用 helper：heavy-query overload/fallback decision（cache/spool first）
- [ ] 4.2 新增/統一 log 欄位（guard_hit, fallback_used, runtime=duckdb|pandas, query_id）
- [ ] 4.3 新增 metrics（guard_reject_count、fallback_success_count、overload_503_rate）

## Phase 5: 測試與驗證

- [ ] 5.1 單元測試：DuckDB/pandas parity（數量、分頁、關鍵欄位一致）
- [ ] 5.2 路由測試：MemoryError/overload 回應碼與 headers 一致性
- [ ] 5.3 壓測驗證：高壓場景下 Query Tool/Trace 503 比例下降、成功率提升
- [x] 5.4 更新相關 OpenSpec spec delta（query-tool-lot-trace, trace-staged-api, reject-history-api, material-trace-api, yield-alert-center-api）
