## 1. Production History — 後端 Job Service

- [x] 1.1 新增 `src/mes_dashboard/services/production_history_job_service.py`：照 `reject_query_job_service.py` 模板，實作 `enqueue_production_history_query()` 和 `execute_production_history_job()`
- [x] 1.2 在 `execute_production_history_job` 中呼叫現有 `query_production_history()`，加入 cache hit 快捷返回、`update_job_progress`、`complete_job` 流程
- [x] 1.3 新增環境變數：`PRODUCTION_HISTORY_ASYNC_ENABLED`、`PRODUCTION_HISTORY_WORKER_QUEUE`、`PRODUCTION_HISTORY_JOB_TTL_SECONDS`、`PRODUCTION_HISTORY_JOB_TIMEOUT_SECONDS`

## 2. Production History — 後端 Route 改造

- [x] 2.1 修改 `production_history_routes.py` 的 `api_production_history_query`：spool miss 時檢查 `is_async_available()`，走 async 回傳 202 + `{ async, job_id, status_url, dataset_id }`
- [x] 2.2 新增 `GET /api/production-history/job/<job_id>` status endpoint，呼叫 `get_job_status`
- [x] 2.3 移除 `heavy_query_overloaded` RuntimeError 處理區塊（被 worker 機制取代），保留 RQ 不可用時的同步回退路徑

## 3. Yield Alert — 後端 Job Service

- [x] 3.1 新增 `src/mes_dashboard/services/yield_alert_job_service.py`：照模板實作 `enqueue_yield_alert_query()` 和 `execute_yield_alert_job()`
- [x] 3.2 在 `execute_yield_alert_job` 中呼叫現有 `execute_primary_query()`，加入 cache hit 快捷返回、progress 更新、complete 流程
- [x] 3.3 新增環境變數：`YIELD_ALERT_ASYNC_ENABLED`、`YIELD_ALERT_WORKER_QUEUE`、`YIELD_ALERT_JOB_TTL_SECONDS`、`YIELD_ALERT_JOB_TIMEOUT_SECONDS`

## 4. Yield Alert — 後端 Route 改造

- [x] 4.1 修改 `yield_alert_routes.py` 的 `api_yield_alert_query`：spool miss 時走 async 回傳 202
- [x] 4.2 新增 `GET /api/yield-alert/job/<job_id>` status endpoint
- [x] 4.3 移除 `get_slow_query_active_count()` 快速拒絕區塊，保留 RQ 不可用時的同步回退路徑

## 5. RQ Monitor & 管理員儀錶板

- [x] 5.1 修正 `rq_monitor_service.py` 的 `_QUEUE_NAMES`：補上遺漏的 `msd-analysis`，並加入 `production-history-query` 和 `yield-alert-query`（共 5 個 queue）
- [x] 5.2 驗證 admin dashboard WorkerTab.vue 動態渲染正確：確認新 worker/queue 出現在 RQ Workers 表格和 Queue 列表中（WorkerTab 已是動態渲染 `rqWorkers` / `rqQueues`，無需改前端，但需 E2E 驗證）

## 6. 前端 — Production History

- [x] 6.1 修改 `frontend/src/production-history/composables/useProductionHistory.js`：import `pollJobUntilComplete`，在 `runQuery` 中處理 202 回應分支
- [x] 6.2 新增 `jobProgress` reactive 狀態和 AbortController 管理，支援取消 polling
- [x] 6.3 polling 完成後用返回的 `dataset_id` 調用現有 `fetchPage` / `fetchMatrix` 載入資料

## 7. 前端 — Yield Alert

- [x] 7.1 修改 `frontend/src/yield-alert-center/App.vue`：import `pollJobUntilComplete`，在查詢函數中處理 202 回應分支
- [x] 7.2 新增 `jobProgress` reactive 狀態和 AbortController 管理
- [x] 7.3 polling 完成後用返回的 `query_id` 調用現有 view/summary/trend 載入流程

## 8. Worker 管理 & 設定

- [x] 8.1 修改 `start_server.sh`：新增 production-history worker 管理函數段落（start/stop/status），照 reject worker 模板
- [x] 8.2 修改 `start_server.sh`：新增 yield-alert worker 管理函數段落
- [x] 8.3 在 `start_server.sh` 的 `start_all` / `stop_all` / `status_all` 中整合新 worker
- [x] 8.4 更新 `.env.example`：新增 `RQ_PRODUCTION_HISTORY_WORKER_ENABLED`、`RQ_YIELD_ALERT_WORKER_ENABLED` 及相關變數
- [x] 8.5 更新 `RQ_WORKER_COUNT_ESTIMATE` 預設值從 3 改為 5

## 9. 契約 & 文件

- [x] 9.1 更新 `contract/api_inventory.md`：新增 `GET /api/production-history/job/<job_id>` 和 `GET /api/yield-alert/job/<job_id>`
- [x] 9.2 更新 `contract/api_inventory.md`：標註 production-history/query 和 yield-alert/query 支援 202 回應碼

## 10. 測試

- [x] 10.1 新增 `tests/test_production_history_job_service.py`：測試 enqueue 成功/失敗、execute 的 cache hit/miss 路徑
- [x] 10.2 新增 `tests/test_yield_alert_job_service.py`：測試 enqueue 成功/失敗、execute 的 cache hit/miss 路徑
- [x] 10.3 為 production_history_routes 和 yield_alert_routes 的 202 分支新增 route 測試
- [x] 10.4 為兩個新 job status endpoint 新增 route 測試
