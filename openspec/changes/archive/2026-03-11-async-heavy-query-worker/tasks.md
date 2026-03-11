## 1. Phase 0: 即時防護（Quick Win）

- [x] 1.1 在 `reject_history_routes.py` 的 `api_reject_history_query()` 加入 cache check → 並發檢查 → 503 快速拒絕邏輯（`HEAVY_QUERY_REJECT_THRESHOLD` 預設 4），503 回應使用 `error_response(SERVICE_UNAVAILABLE, ...)` 格式
- [x] 1.2 在 `reject_dataset_cache.py` 將 `REJECT_ENGINE_QUERY_WAIT_SECONDS` 預設從 180 改為 90
- [x] 1.3 在 yield-alert 和 mid-section-defect routes 同步加入 `get_slow_query_active_count()` 快速拒絕檢查
- [x] 1.4 將 `GUNICORN_WORKERS` 預設從 2 改為 3（更新 `gunicorn.conf.py` 和 `.env.example`）
- [x] 1.5 為 Phase 0 撰寫單元測試（503 拒絕、cache check 前置、wait timeout 行為）

## 2. 共用 Async Job 工具模組

- [x] 2.1 建立 `src/mes_dashboard/services/async_query_job_service.py`：`is_async_available()`、`enqueue_job()`、`get_job_status()`、`update_job_progress()`、`complete_job()`
- [x] 2.2 定義 Redis key 規範：`{prefix}:job:{job_id}:meta` HSET schema
- [x] 2.3 撰寫 `async_query_job_service` 單元測試（enqueue、status、progress、completion、health check）

## 3. Reject Query Job Worker

- [x] 3.1 從 `reject_dataset_cache.py` 的 `execute_primary_query()` 抽取核心查詢邏輯為可重用函式 `_execute_and_spool()`
- [x] 3.2 建立 `src/mes_dashboard/services/reject_query_job_service.py`：`should_use_async()`、`enqueue_reject_query()`、`execute_reject_query_job()`（RQ worker entry point）
- [x] 3.3 `execute_reject_query_job()` 整合 batch engine + spool + progress callback
- [x] 3.4 撰寫 `reject_query_job_service` 單元測試（async 判定、enqueue、worker 執行、失敗處理）

## 4. Route 修改（Reject-History）

- [x] 4.1 修改 `POST /api/reject-history/query`：加入 async 202 路徑，使用 `success_response(data, status_code=202)`
- [x] 4.2 新增 `GET /api/reject-history/job/<job_id>` 端點：使用 `success_response()` / `not_found_error()`，加 `@configured_rate_limit`
- [x] 4.3 確保所有新/修改 route 回應使用 `success_response()` / `error_response()` helpers（禁止手動 `jsonify()`），route handler 保持 thin（業務邏輯在 service 層）
- [x] 4.4 確保 short query（≤10 天）和 container mode 仍走同步路徑（向下相容）
- [x] 4.5 撰寫 route 層整合測試（202 回應、job status 輪詢、cache hit bypass、error envelope 格式驗證）
- [x] 4.6 更新 `test_api_contract.py` baseline（若 jsonify count 變動）
- [x] 4.7 更新 `contract/api_inventory.md`：在 `reject_history_routes.py` 的 standard-json scope 加入 `GET /api/reject-history/job/<job_id>` 端點，並備註 `POST /query` 可回 202（async job）

## 5. RQ Worker 部署設定

- [x] 5.1 修改 `scripts/start_server.sh`：新增 `rq-worker-reject` process（`RQ_REJECT_WORKER_ENABLED` 環境變數控制）
- [x] 5.2 確保 reject worker 和 trace worker 獨立啟動/停止
- [x] 5.3 更新 `.env.example` 加入所有新環境變數及說明

## 6. 前端修改

- [x] 6.1 建立 `frontend/src/shared-composables/useAsyncJobPolling.js`：從 `useTraceProgress.js` 抽取 `pollJobUntilComplete()` 通用函式
- [x] 6.2 修改 `frontend/src/reject-history/App.vue` 的 `executePrimaryQuery()`：加入 async 分支（檢查 resp.async → 輪詢 → 用 query_id 載入 /view）
- [x] 6.3 在 reject-history App.vue 加入進度 UI（reactive jobProgress state + loading overlay 進度文字 + 取消按鈕）
- [x] 6.4 重構 `useTraceProgress.js` 使用共用 `pollJobUntilComplete()`

## 7. 系統記憶體監控

- [x] 7.1 修改 `worker_memory_guard.py`：在 15 秒週期檢查中加入 `psutil.virtual_memory()` 系統記憶體檢查（>85% 警告+eviction、>92% 設置 pressure flag）
- [x] 7.2 修改 `health_routes.py`：`/health` 和 `/health/deep` 回應加入 `system_memory` 區塊
- [x] 7.3 修改 `metrics_history.py`：snapshot 加入 `system_mem_available_mb` 和 `system_mem_used_pct` 欄位
- [x] 7.4 在 `gunicorn.conf.py` 或 `start_server.sh` 加入啟動前記憶體餘裕檢查
- [x] 7.5 撰寫系統記憶體監控單元測試
- [x] 7.6 更新 `contract/api_inventory.md`：在 health-exception 區塊補充 `system_memory` 新增欄位的影響範圍與相容性說明（契約 6.4）

## 8. 全域並發限制器

- [x] 8.1 建立 `src/mes_dashboard/core/global_concurrency.py`：Redis sorted set + Lua script 實現 `acquire_heavy_query_slot()` / `release_heavy_query_slot()`
- [x] 8.2 整合到 RQ worker entry point 和 sync `execute_primary_query()` 路徑
- [x] 8.3 撰寫全域並發限制器單元測試（acquire、release、expire、fail-open）

## 9. Trace 重構（共用模組）

- [x] 9.1 重構 `trace_job_service.py` 委託 `async_query_job_service.py` 的 enqueue/status 函式
- [x] 9.2 確認 trace 功能無行為變更（回歸測試）

## 10. 整合驗證

- [x] 10.1 手動驗證：>10 天查詢收到 202 → 輪詢 job status → completed → /view 取得資料
- [x] 10.2 手動驗證：長查詢進行中，health check 和短查詢仍正常回應
- [x] 10.3 手動驗證：並發 4 個長查詢 → async 路徑全部 enqueue（RQ worker 串行處理 + global concurrency slot 控制）
- [x] 10.4 跑 `tests/stress/test_reject_history_stress.py` 確認系統不再假死（半年壓測通過：6/6 handled, 0 unexpected failures）
- [x] 10.5 檢查 `/health` 回應包含 `system_memory` 區塊且數值合理
