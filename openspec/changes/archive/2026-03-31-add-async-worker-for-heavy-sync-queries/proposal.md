## Why

Production History 和 Yield Alert 兩個頁面的主查詢目前在 Gunicorn worker 內同步阻塞執行 `read_sql_df_slow`，佔用 slow pool semaphore 槽位（prod=8）。多用戶同時查詢時會觸發 503 快速拒絕（`heavy_query_overloaded` / `slow_query_active_threshold`）——這本質上是「應該用 RQ worker 非同步處理但還沒做」的訊號。現有 reject-history、trace、MSD 三個 RQ worker 已證明 async spool 模式有效，基礎設施（`async_query_job_service`、`useAsyncJobPolling` composable）完全就位，只需複製模式即可覆蓋這兩個頁面。

## What Changes

- 新增 `production_history_job_service.py`：將 production-history 主查詢（BatchQueryEngine chunk 路徑）移至 RQ worker 背景執行
- 新增 `yield_alert_job_service.py`：將 yield-alert 主查詢移至 RQ worker 背景執行
- 修改 `production_history_routes.py`：spool miss 時回傳 202 + job_id，新增 `GET /api/production-history/job/<job_id>` status endpoint
- 修改 `yield_alert_routes.py`：spool miss 時回傳 202 + job_id，新增 `GET /api/yield-alert/job/<job_id>` status endpoint
- 修改 `start_server.sh`：新增兩個 RQ worker 管理函數（production-history-query、yield-alert-query queue）
- 修改前端 `useProductionHistory.js`：處理 202 回應 + `pollJobUntilComplete`
- 修改前端 `yield-alert-center/App.vue`：處理 202 回應 + `pollJobUntilComplete`
- 移除 yield_alert_routes 中的 `get_slow_query_active_count` 窮人限流（被 worker 機制取代）
- 移除 production_history_routes 中的 `heavy_query_overloaded` 窮人限流（被 worker 機制取代）
- 新增 `.env` / `.env.example` 環境變數（ENABLED flag、queue name、timeout、TTL）

## Capabilities

### New Capabilities
- `production-history-async-worker`: Production History 頁面的 RQ worker 非同步查詢機制（job service + route 202 + 前端 polling）
- `yield-alert-async-worker`: Yield Alert 頁面的 RQ worker 非同步查詢機制（job service + route 202 + 前端 polling）

### Modified Capabilities
- `async-query-job-service`: 新增兩個 consumer（production-history、yield-alert），無 API 變更，僅擴展使用範圍
- `slow-query-concurrency-control`: 兩個頁面從同步 slow pool 路徑移至 worker，降低 Gunicorn 端 slow pool 壓力

## Impact

- **後端新增檔案**: `services/production_history_job_service.py`、`services/yield_alert_job_service.py`
- **後端修改檔案**: `routes/production_history_routes.py`、`routes/yield_alert_routes.py`
- **前端修改檔案**: `production-history/composables/useProductionHistory.js`、`yield-alert-center/App.vue`
- **運維**: `start_server.sh` 新增 2 個 worker 管理段落；`.env.example` 新增 ~8 個環境變數
- **API 變更**: 兩個 query endpoint 從純 200 改為 200/202 雙回應碼；各新增 1 個 job status GET endpoint
- **依賴**: 無新依賴，複用現有 `async_query_job_service`、`rq`、`useAsyncJobPolling`
- **契約更新**: `contract/api_inventory.md` 需新增 2 個 job status endpoint
