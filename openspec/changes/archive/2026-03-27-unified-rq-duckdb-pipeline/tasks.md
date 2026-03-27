## 1. 基礎設施：Spool store / RQ pool / scheduler lock

- [x] 1.1 修改 `start_server.sh`：RQ worker 啟動時注入實際生效的 `DB_POOL_SIZE=2 DB_MAX_OVERFLOW=1`
- [x] 1.2 整理 `.env.example` 與文件：刪除或實作 `RQ_DB_*`，不得保留無效 env 名稱
- [x] 1.3 修改 `query_spool_store.py`：統一 spool TTL / size 設定命名，並支援 stage file metadata、namespace file listing、canonical query lookup
- [x] 1.4 新建 `src/mes_dashboard/core/spool_pipeline.py`：封裝多 stage job、stage spool、progress update、final metadata registration
- [x] 1.5 新建 `src/mes_dashboard/core/spool_warmup_scheduler.py`：加入 leader lock，避免每個 gunicorn worker 重複 enqueue warmup

## 2. Canonical dataset identity

- [x] 2.1 為 `reject-history`、`yield-alert`、`hold-overview` 定義 canonical warmup key 與 spool reuse contract
- [x] 2.2 為 `resource-history` 定義 canonical base dataset identity，將 filters 下沉到 DuckDB/view-time predicates，且 route contract 不變
- [x] 2.3 為 `production-history` 定義 on-demand canonical spool identity，確認 `pj_types` 契約如何保留，但不設計 warmup coverage
- [x] 2.4 為 `MSD` 定義 `trace_query_id` / `dataset_id`，供 summary / detail / export / spool reuse 共用
- [x] 2.5 為 `material-trace`、`query-tool trace` 定義 on-demand canonical query hash

## 3. Warmup 遷移

- [x] 3.1 先將 `reject_dataset`、`yield_alert_dataset`、`hold_dataset` 納入 spool warmup scheduler
- [x] 3.2 `cache_updater.py` 移除 reject / yield dataset warmup，保留 WIP / filter / reason / equipment 等非 spool warmup
- [x] 3.3 在 `resource-history` canonical base dataset 完成後，再把 `resource_dataset` 納入 warmup
- [x] 3.4 明確排除 `production-history` 啟動 warmup / 週期性 warmup，並補文件與測試避免未來誤加
- [x] 3.5 為 scheduler 補 unit test：leader lock、skip valid spool、sequential execution、interval refresh

## 4. Async job service / progress contract

- [x] 4.1 修改 `async_query_job_service.py`：支援 `stage`、`completed_stages`、canonical `query_id` / `dataset_id`
- [x] 4.2 修改 trace / generic job status endpoint：回傳 stage-aware progress
- [x] 4.3 新增 unit test：驗證 multi-stage progress 與 compatibility fields

## 5. MSD：staged trace、compatibility adapter、detail/export

- [x] 5.1 新建 `msd_duckdb_runtime.py`：以 DuckDB 讀 stage spool 計算 KPI / charts / daily trend / detail
- [x] 5.2 修改 `trace_routes.py` 的 MSD aggregation path：改由 `msd_duckdb_runtime` 從 spool 計算
- [x] 5.3 修改 `mid_section_defect_routes.py`：`/analysis/detail` 優先接受 `trace_query_id`，從 spool 讀取分頁與排序
- [x] 5.4 修改 `mid_section_defect_routes.py`：`/export` 從 spool + DuckDB 讀取並 streaming CSV
- [x] 5.5 將 `/api/mid-section-defect/analysis` 改為 compatibility adapter，內部導向新 pipeline；不得先刪 route
- [x] 5.6 更新 `ai_functions.yaml`：讓 AI consumer 使用新的 canonical query flow 或 compatibility adapter
- [x] 5.7 補 parity tests：summary / detail / export 對照 legacy 結果一致
- [x] 5.8 只有在 frontend、AI registry、tests、`contract/api_inventory.md` 全部完成遷移後，才移除 `/analysis` job endpoints 與 `msd_query_job_service.py`

## 6. Trace / EventFetcher / lineage

- [x] 6.1 修改 `trace_job_service.py`：trace events job 寫 stage spool metadata，而不是只存 chunked Redis result
- [x] 6.2 修改 `trace_routes.py`：events spool hit 直接回結果，spool miss 時走 async job；保留 compatibility 所需欄位
- [x] 6.3 修改 `event_fetcher.py`：支援 spool-oriented stage output，避免 large result 長時間停留在 Python memory
- [x] 6.4 當 trace events 全面切到 RQ/spool path 後，移除 `TRACE_EVENTS_CID_LIMIT` 與 sync RSS reject
- [x] 6.5 當 lineage 全面切到 RQ/spool path 後，移除 `LINEAGE_MAX_SEED_COUNT` 與 `LINEAGE_RSS_REJECT_MB`
  已完成：`/api/trace/lineage` 改為 canonical lineage query id 的 async-first 路徑，query-tool lineage composable 補 polling，`lineage_engine.py` 不再保留 web-worker admission guard
- [x] 6.5.1 盤點 `mid_section_defect_service.py` 中所有直接呼叫 `LineageEngine.resolve_full_genealogy()` / `resolve_forward_tree()` 的 compatibility path，確認 summary / detail / export 各自還有哪些入口會落回 legacy lineage
- [x] 6.5.2 將 `mid_section_defect_service.query_analysis()` 改為優先解析 canonical `trace_query_id` 並讀取 staged trace spool / `msd_duckdb_runtime`，不得在 web worker 重新執行 lineage heavy query
- [x] 6.5.3 若 compatibility request 尚未帶 `trace_query_id`，補一層 deterministic params -> canonical MSD dataset lookup；查不到時才允許 enqueue / 建立新 staged trace job，不得直接走 legacy sync lineage
- [x] 6.5.4 修改 MSD compatibility adapter 與相關 consumer/tests，確認 summary / detail / export 在無 `trace_query_id` 與有 `trace_query_id` 兩種情境下都不再直接呼叫 lineage engine
- [x] 6.5.5 當上述 compatibility path 全部切離 lineage sync path 後，再移除 `LINEAGE_MAX_SEED_COUNT`、`LINEAGE_RSS_REJECT_MB` 與對應 guard tests，並補新的 retirement/parity tests
- [x] 6.6 補 unit / integration tests：cache hit、spool hit、async status、large query acceptance、legacy guard retirement

## 7. Reject / resource / hold / production-history

- [x] 7.1 確認 reject 既有 spool + DuckDB 路徑可直接接入統一 spool metadata / warmup scheduler
- [x] 7.2 在 resource canonical base dataset 完成後，讓 `POST /api/resource/history/query` 維持同步 bootstrap contract 與既有前端參數/response，但底層走 unified spool pipeline
- [x] 7.3 在 production canonical spool identity 完成後，讓 `POST /api/production-history/query` 維持同步 bootstrap contract，但底層走 unified spool pipeline，且不接入 warmup scheduler
- [x] 7.4 hold dataset 接入統一 warmup 與 spool metadata
- [x] 7.5 只有在 reject 查詢完全使用 spool-safe path 後，才移除 `REJECT_QUERY_RSS_REJECT_MB` 與 route-level heavy query reject

## 8. Material trace

- [x] 8.1 修改 `material_trace_service.py`：查詢結果寫入 spool，分頁/排序/匯出改由 DuckDB runtime 處理
- [x] 8.2 新建 `material_trace_duckdb_runtime.py`
- [x] 8.3 修改 material trace routes 與 frontend：加入 async enqueue / polling contract
- [x] 8.4 在 async UX 與 parity test 完成後，移除 `_REVERSE_MAX_ROWS` / `_FORWARD_MAX_ROWS` / `_EXPORT_MAX_ROWS`

## 9. 契約、consumer、文件

- [x] 9.1 更新 `contract/api_inventory.md`：標記 compatibility endpoints、canonical query ids、async-capable routes
- [x] 9.2 更新相關 OpenSpec delta specs，避免寫出與現況不符的「立即刪除」或「所有 route 一律 202」
- [x] 9.3 清點並更新前端、AI function registry、unit tests、e2e tests 的 consumer 依賴

## 10. 驗證

- [x] 10.1 整合測試：MSD main query -> `trace_query_id` -> detail -> export 全鏈路
- [x] 10.2 整合測試：warmup scheduler 只由單一 leader enqueue
- [x] 10.3 整合測試：reject / yield / hold warmup 命中 spool，route 可直接回結果
- [x] 10.4 整合測試：resource / production 在 route contract 不變下，底層已走 unified spool pipeline
- [x] 10.5 整合測試：production-history 不會被 scheduler enqueue 進啟動 warmup 或週期 refresh
- [x] 10.6 整合測試：material trace async query / polling / export
- [x] 10.7 驗證所有 guard retirement 都發生在對應 legacy path 退場之後
