## Why

歷史查詢頁面（reject-history、query-tool、hold-history、resource-history、job-query、excel-query、mid-section-defect）
目前共用 connection pool 的 55s `call_timeout`，前端也設有 60~120s AbortController timeout。
大範圍查詢（如長日期區間或大量 LOT）經常逼近或超過 timeout，使用者看到 "signal is aborted without reason" 錯誤。

歷史查詢屬於使用者手動觸發、非即時、可等待的操作，應採用獨立連線（`read_sql_df_slow`）配合
semaphore 並行控制，以「用時間換結果」的方式完成查詢，同時保護 connection pool 不被耗盡。

## What Changes

- 歷史查詢 service 從 `read_sql_df`（pool, 55s）遷移到 `read_sql_df_slow`（獨立連線, 300s）
- `read_sql_df_slow` 加入 global semaphore 限制並行數（預設 3），避免耗盡 Oracle 連線
- `read_sql_df_slow` 的 timeout 預設從寫死 120s 改為 config 驅動（預設 300s）
- Gunicorn worker timeout 從 130s 提升到 360s 以容納長查詢
- 前端歷史頁 timeout 統一提升到 360s（6 分鐘）
- 新增 `DB_SLOW_CALL_TIMEOUT_MS` 和 `DB_SLOW_MAX_CONCURRENT` 環境變數設定
- 即時監控頁（wip、hold-overview、resource-status 等）完全不受影響

## Capabilities

### New Capabilities

- `slow-query-concurrency-control`: `read_sql_df_slow` 的 semaphore 並行控制與 config 驅動 timeout

### Modified Capabilities

- `reject-history-api`: 底層 DB 查詢從 pooled 改為 dedicated slow connection
- `hold-history-api`: 底層 DB 查詢從 pooled 改為 dedicated slow connection
- `query-tool-lot-trace`: 移除 `read_sql_df_slow` 寫死的 120s timeout，改用 config 預設
- `reject-history-page`: 前端 API_TIMEOUT 從 60s 提升到 360s
- `hold-history-page`: 前端 API_TIMEOUT 從 60s 提升到 360s
- `resource-history-page`: 前端 API_TIMEOUT 從 60s 提升到 360s，後端遷移至 slow connection
- `query-tool-equipment`: 前端 timeout 從 120s 提升到 360s
- `progressive-trace-ux`: DEFAULT_STAGE_TIMEOUT_MS 從 60s 提升到 360s

## Impact

- **後端 services**：reject_history_service、reject_dataset_cache、hold_history_service、resource_history_service、job_query_service、excel_query_service、query_tool_service
- **核心模組**：database.py（semaphore + config）、settings.py（新設定）、gunicorn.conf.py（timeout）
- **前端頁面**：reject-history、mid-section-defect、hold-history、resource-history、query-tool（5 個 composable + 1 component）、job-query、excel-query
- **不影響**：即時監控頁（wip-overview、wip-detail、hold-overview、hold-detail、resource-status、admin-performance）
